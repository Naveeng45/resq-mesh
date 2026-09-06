from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.handlers.callback_handler import PrintingCallbackHandler, null_callback_handler

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.capabilities import derive_required_capabilities
from app.mission import Mission, review_mission
from app.solver import CoalitionRequest, solve_resource_coalition

logger = logging.getLogger(__name__)

MODEL_ID = "us.amazon.nova-lite-v1:0"
BEDROCK_REGION = "us-east-1"
PROMPT = (
    "We need Thursday coverage at Riverside Community Meals — Eastside by "
    "2026-09-10T16:00:00-07:00: a van driver, a packer, and a site lead. "
    "Whoever drives has to be van certified."
)
SYSTEM_PROMPT = """
You extract coverage facts from a natural-language request.
Only capture facts explicitly stated by the user.
If a critical fact is missing or vague, set it to null instead of inventing it.
Do not infer which roles are required, do not choose volunteers, and do not plan coverage.
Never invent a volunteer, a site, or an organization that the user did not mention.
Return only the structured facts.
""".strip()

# Corporate proxies intercept TLS, which breaks both Bedrock calls and localhost
# traffic. urllib folds NO_PROXY and no_proxy into one lower-cased dict, so both
# spellings must agree or the escalation webhook can silently take the proxy.
_AWS_PROXY_BYPASS_ENTRIES: tuple[str, ...] = (".amazonaws.com", "127.0.0.1", "localhost")


def ensure_aws_proxy_bypass() -> None:
    """Add AWS and loopback hosts to NO_PROXY without dropping existing entries."""

    existing: list[str] = []
    for variable in ("NO_PROXY", "no_proxy"):
        for entry in os.environ.get(variable, "").split(","):
            cleaned = entry.strip()
            if cleaned and cleaned not in existing:
                existing.append(cleaned)

    for entry in _AWS_PROXY_BYPASS_ENTRIES:
        if entry not in existing:
            existing.append(entry)

    merged = ",".join(existing)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def build_demo_mission() -> Mission:
    """Provide a local fallback so the demo still runs with no Bedrock access."""

    return Mission(
        destination="Riverside Community Meals — Eastside",
        deadline="2026-09-10T16:00:00-07:00",
        incident_type="thursday_distribution",
        requirements=["van driver", "packer", "site lead"],
        constraints=["van certification required to drive"],
    )


def _print_section(title: str, payload: dict[str, object]) -> None:
    print(f"\n{title}")
    for key, value in payload.items():
        if key == "required_capabilities" and isinstance(value, list):
            print("  required_capabilities:")
            for capability in value:
                print(
                    "    - "
                    f"{capability['code']}: {capability['label']} "
                    f"(confidence {capability['confidence']})"
                )
            continue
        if key == "selected_resources" and isinstance(value, list):
            print("  selected_resources:")
            for resource in value:
                print(
                    "    - "
                    f"{resource['id']}: {resource['name']} "
                    f"(capacity {resource['capacity']})"
                )
            continue
        print(f"  {key}: {value}")


def build_agent(*, verbose_output: bool = False) -> Agent:
    callback_handler = (
        PrintingCallbackHandler(verbose_tool_use=True) if verbose_output else null_callback_handler
    )
    return Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=BEDROCK_REGION, streaming=False),
        system_prompt=SYSTEM_PROMPT,
        structured_output_model=Mission,
        callback_handler=callback_handler,
    )


def run_mission_to_coalition_demo(mission: Mission | None = None) -> None:
    if mission is None:
        agent = build_agent(verbose_output=True)
        logger.info("Sending mission request: %s", PROMPT)

        try:
            result = agent(PROMPT)
        except NoCredentialsError:
            print("Bedrock request failed: Unable to locate credentials")
            print("Using the local demo mission so you can still see the solver output.")
            result = None
        except (BotoCoreError, ClientError) as exc:
            print(f"Bedrock request failed: {exc}")
            print("Using the local demo mission so you can still see the solver output.")
            result = None
        except Exception as exc:
            print(f"Agent invocation failed: {exc}")
            raise

        mission = result.structured_output if result is not None else build_demo_mission()
    else:
        logger.info("Using deterministic demo mission: %s", mission.model_dump())

    review = review_mission(mission)
    capability_assessment = derive_required_capabilities(mission)
    coalition_solution = None

    if not review.missing_critical_facts and not capability_assessment.needs_human_review:
        coalition_solution = solve_resource_coalition(
            CoalitionRequest(
                required_capabilities=capability_assessment.rule_required_capability_codes,
                minimum_total_capacity=8,
            )
        )

    logger.info("Mission status: %s", review.status)
    print("\n=== MealMesh: extracted facts to coverage plan ===")
    _print_section("1) Extracted facts", mission.model_dump())
    _print_section("2) Mission review", review.model_dump())
    _print_section("3) Rule-derived capabilities", capability_assessment.model_dump())

    if capability_assessment.needs_human_review:
        print("\nHuman review: required")
        if capability_assessment.review_reasons:
            print("Reasons:")
            for reason in capability_assessment.review_reasons:
                print(f"  - {reason}")
    else:
        print("\nHuman review: not required")

    if coalition_solution is None:
        print("\n4) Coalition solver")
        print("  Skipped because the mission needs human review or is missing critical facts.")
    else:
        _print_section("4) Coalition solver", coalition_solution.model_dump())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_mission_to_coalition_demo()


if __name__ == "__main__":
    main()
