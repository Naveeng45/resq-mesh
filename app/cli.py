from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.capabilities import derive_required_capabilities
from app.mission import Mission, review_mission
from app.mission_agent import build_agent, build_demo_mission
from app.resilience import replan
from app.resources import list_resources
from app.solver import CoalitionRequest, solve_resource_coalition


logger = logging.getLogger(__name__)


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _prompt_for_query(value: str | None) -> str:
    if value:
        return value.strip()

    try:
        query = input("Describe the incident: ").strip()
    except EOFError as exc:  # pragma: no cover - interactive fallback
        raise SystemExit("No query provided.") from exc

    if not query:
        raise SystemExit("No query provided.")
    return query


def _prompt_for_mission_clarification(mission: Mission) -> Mission:
    review = review_mission(mission)
    if not review.missing_critical_facts:
        return mission

    print("I need one or two missing facts before I can plan:")
    updated_data = mission.model_dump()
    prompts = {
        "destination": "What destination or affected location should I use?",
        "deadline": "What is the deadline or target time?",
        "incident_type": "What type of incident is this?",
    }

    for field_name in review.missing_critical_facts:
        while True:
            try:
                answer = input(f"{prompts[field_name]} ").strip()
            except EOFError as exc:  # pragma: no cover - interactive fallback
                raise SystemExit("Clarification was interrupted.") from exc
            if not answer:
                print("Please enter a value.")
                continue

            updated_data[field_name] = answer
            try:
                return Mission.model_validate(updated_data)
            except Exception as exc:  # pragma: no cover - interactive recovery path
                print(f"That value did not parse cleanly: {exc}")

    return mission


def extract_mission(query: str, *, allow_demo_fallback: bool = True) -> Mission:
    agent = build_agent()
    logger.info("Sending CLI query: %s", query)

    try:
        result = agent(query)
    except NoCredentialsError as exc:
        print("Bedrock request failed: Unable to locate credentials")
        if allow_demo_fallback:
            print("Using the local demo mission so you can still try the CLI.")
            return build_demo_mission()
        raise SystemExit(1) from exc
    except (BotoCoreError, ClientError) as exc:
        print(f"Bedrock request failed: {exc}")
        if allow_demo_fallback:
            print("Using the local demo mission so you can still try the CLI.")
            return build_demo_mission()
        raise SystemExit(1) from exc

    return result.structured_output


def run_cli(query: str) -> None:
    mission = extract_mission(query)
    review = review_mission(mission)
    if review.missing_critical_facts:
        mission = _prompt_for_mission_clarification(mission)
        review = review_mission(mission)
    capability_assessment = derive_required_capabilities(mission)

    coalition = None
    if not review.missing_critical_facts and not capability_assessment.needs_human_review:
        coalition = solve_resource_coalition(
            CoalitionRequest(
                required_capabilities=capability_assessment.rule_required_capability_codes,
                minimum_total_capacity=8,
            )
        )

    report = None
    if coalition is not None and coalition.feasible:
        report = replan(
            CoalitionRequest(
                required_capabilities=capability_assessment.rule_required_capability_codes,
                minimum_total_capacity=9,
            ),
            coalition,
            resources=list_resources(),
        )

    print("=== RESQ-Mesh CLI ===")
    print(
        "Mission:",
        f"{mission.destination or 'unknown'} | {mission.incident_type or 'unknown'} | requirements={_join(mission.requirements)}",
    )
    print(f"Review: {review.status}")
    print("Capabilities:", _join([capability.code for capability in capability_assessment.required_capabilities]))

    if coalition is None:
        print("Coalition: skipped because the mission needs human review")
    else:
        print(
            "Coalition:",
            f"{_join(coalition.selected_resource_ids)} | total_capacity={coalition.total_capacity} | {coalition.solver_status}",
        )

    if report is None:
        print("Resilience: skipped because no feasible baseline coalition was available")
        return

    print("Overall:", report.overall_classification)
    print(
        "Failures:",
        f"recoverable={_join(report.recoverable_failure_ids)} | mission_breaking={_join(report.mission_breaking_failure_ids)}",
    )
    print("Summary:", report.summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RESQ-Mesh CLI demo.")
    parser.add_argument(
        "query",
        nargs="?",
        help="Incident description to analyze. If omitted, you will be prompted.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    query = _prompt_for_query(args.query)
    run_cli(query)


if __name__ == "__main__":
    main()
