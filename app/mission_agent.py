from __future__ import annotations

import logging
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from strands import Agent
from strands.models.bedrock import BedrockModel

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.capabilities import derive_required_capabilities
from app.mission import Mission, review_mission
from app.solver import CoalitionRequest, solve_resource_coalition

logger = logging.getLogger(__name__)

MODEL_ID = "us.amazon.nova-lite-v1:0"
BEDROCK_REGION = "us-east-1"
PROMPT = (
    "Flood waters have isolated Willow Creek. Send the boat and medical team "
    "to the marina by 2026-09-06T18:00:00-07:00. Roads remain blocked."
)
SYSTEM_PROMPT = """
You extract incident facts from a natural-language request.
Only capture facts explicitly stated by the user.
If a critical fact is missing or vague, set it to null instead of inventing it.
Do not infer operational doctrine, do not choose resources, and do not optimize a response.
Return only the structured facts.
""".strip()


def build_demo_mission() -> Mission:
    """Provide a local fallback so the Lesson 05 -> Lesson 06 demo still runs offline."""

    return Mission(
        destination="Willow Creek",
        deadline="2026-09-06T18:00:00-07:00",
        incident_type="flood",
        requirements=["boat", "medical team"],
        constraints=["roads remain blocked"],
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


def build_agent() -> Agent:
    return Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=BEDROCK_REGION, streaming=False),
        system_prompt=SYSTEM_PROMPT,
        structured_output_model=Mission,
    )


def run_mission_to_coalition_demo() -> None:
    agent = build_agent()
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
    print("\n=== RESQ-Mesh Lesson 05 to Lesson 06 Demo ===")
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
