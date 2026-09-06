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
from app.resources import list_available_resources
from app.solver import CoalitionRequest, solve_resource_coalition


logger = logging.getLogger(__name__)


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _final_verdict(
    review_status: str,
    coalition_feasible: bool | None,
    include_resilience: bool,
) -> str:
    if review_status != "ready":
        return "needs more facts"
    if coalition_feasible is False:
        return "no feasible coalition"
    if include_resilience:
        return "ready with resilience check"
    return "ready to deploy"


def _mission_card(mission: Mission, review_status: str, coalition: object | None) -> str:
    coalition_text = "not selected" if coalition is None else "selected"
    destination = mission.destination or "unknown site"
    incident = mission.incident_type or "unknown coverage type"
    return f"{destination} | {incident} | review={review_status} | coalition={coalition_text}"


def _prompt_for_query(value: str | None) -> str:
    if value:
        return value.strip()

    try:
        query = input("Describe the coverage you need: ").strip()
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
        "destination": "Which meal site should I plan for?",
        "deadline": "What time does the site need to be covered?",
        "incident_type": "What kind of coverage is this (for example thursday_distribution)?",
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
    agent = build_agent(verbose_output=False)
    logger.debug("Sending CLI query: %s", query)

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


def run_cli(query: str, *, include_resilience: bool = False) -> None:
    mission = extract_mission(query)
    review = review_mission(mission)
    capability_assessment = derive_required_capabilities(mission)

    coalition = None
    if not review.missing_critical_facts and not capability_assessment.needs_human_review:
        coalition = solve_resource_coalition(
            CoalitionRequest(
                required_capabilities=capability_assessment.rule_required_capability_codes,
                minimum_total_capacity=0,
            ),
            resources=list_available_resources(),
        )

    report = None
    if include_resilience and coalition is not None and coalition.feasible:
        report = replan(
            CoalitionRequest(
                required_capabilities=capability_assessment.rule_required_capability_codes,
                minimum_total_capacity=0,
            ),
            coalition,
            resources=list_available_resources(),
        )

    print("=== MealMesh CLI ===")
    print("Mission card:", _mission_card(mission, review.status, coalition))
    print(
        "Mission:",
        f"{mission.destination or 'unknown'} | {mission.incident_type or 'unknown'} | requirements={_join(mission.requirements)}",
    )
    print(f"Review: {review.status}")
    if review.missing_critical_facts:
        print("Missing facts:", _join(review.missing_critical_facts))
    print("Capabilities:", _join([capability.code for capability in capability_assessment.required_capabilities]))

    if coalition is None:
        if review.missing_critical_facts or capability_assessment.needs_human_review:
            print("Coalition: skipped because the mission needs human review")
        else:
            print("Coalition: skipped because no feasible coalition was found")
    else:
        print(
            "Coalition:",
            f"{_join(coalition.selected_resource_ids)} | total_capacity={coalition.total_capacity} | {coalition.solver_status}",
        )

    if not include_resilience:
        print("Resilience: disabled (pass --replan to simulate resource loss)")
        print("Final verdict:", _final_verdict(review.status, coalition.feasible if coalition else None, False))
        return

    if report is None:
        print("Resilience: skipped because no feasible baseline coalition was available")
        print("Final verdict:", _final_verdict(review.status, coalition.feasible if coalition else None, True))
        return

    print("Overall:", report.overall_classification)
    print(
        "Failures:",
        f"recoverable={_join(report.recoverable_failure_ids)} | mission_breaking={_join(report.mission_breaking_failure_ids)}",
    )
    print("Summary:", report.summary)
    print("Final verdict:", _final_verdict(review.status, coalition.feasible if coalition else None, True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MealMesh CLI demo.")
    parser.add_argument(
        "query",
        nargs="?",
        help="Coverage request to analyze. If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--replan",
        action="store_true",
        help="Run the counterfactual failure and replan analysis after the coalition is built.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    query = _prompt_for_query(args.query)
    run_cli(query, include_resilience=args.replan)


if __name__ == "__main__":
    main()
