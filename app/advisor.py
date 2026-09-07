"""Conversational Advisor — a Strands ReAct agent for meal-program coordinators.

The Advisor answers natural-language questions ("Can Eastside open Thursday?",
"What breaks the plan?", "What are we missing?") by **calling tools**
and relaying their results in plain English.

The trust boundary is intact. The deterministic tools make every decision:

    - `assess_incident`  -> runs the CP-SAT pipeline; the solver decides feasibility,
                            allocation, and what is missing.
    - `get_available_resources` / `get_resources_by_required_capability`
                         -> read the deterministic resource catalog.

The model orchestrates and explains; it never allocates a resource itself. This
is the "LLM as an interface to deterministic authority" pattern — the same
principle as the rest of MealMesh, now exposed as a real multi-tool agent.

Run:
    python -m app.advisor                                  # scripted demo
    python -m app.advisor "Can Eastside open Thursday?"
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from typing import Any

from strands import Agent
from strands.handlers.callback_handler import null_callback_handler
from strands.models.bedrock import BedrockModel

from app.agent_observability import StrandsAuditCallbackHandler, ToolTraceCallbackHandler
from app.mission_agent import BEDROCK_REGION, MODEL_ID, ensure_aws_proxy_bypass
from app.tools import (
    assess_incident,
    get_available_resources,
    get_resources_by_required_capability,
)

logger = logging.getLogger(__name__)

ADVISOR_TOOLS = [assess_incident, get_available_resources, get_resources_by_required_capability]

ADVISOR_SYSTEM_PROMPT = """
You are MealMesh Advisor, an assistant for a community meal-program coordinator.

You do NOT decide anything yourself. To answer any question about feasibility,
which resources to use, resilience, or what is missing, you MUST call the
`assess_incident` tool and report exactly what it returns. Use
`get_available_resources` and `get_resources_by_required_capability` to answer
questions about the current catalog.

Rules:
- Never invent resources, capacities, availability, or a plan. Only report tool output.
- Never choose a volunteer or claim coverage unless a tool returned that decision.
- When a site is uncovered, state the named missing capability from the tool.
- Be concise and operational. End feasibility answers with the verdict verbatim.
- All data is simulated; do not imply it reflects real assets.
""".strip()

DEMO_QUESTIONS = (
    "Can Riverside Community Meals — Eastside open Thursday with a van driver, packer, and site lead?",
    "What single volunteer cancellation would leave Eastside uncovered?",
    "Which opted-in volunteers can provide a van-certified driver right now?",
)


def build_advisor(*, verbose_output: bool = False, callback_handler: Any = None) -> Agent:
    """Construct the tool-calling Advisor agent (no network call at build time)."""

    ensure_aws_proxy_bypass()
    if callback_handler is None:
        handler = StrandsAuditCallbackHandler(verbose_output=verbose_output) if verbose_output else null_callback_handler
    else:
        handler = callback_handler
    return Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=BEDROCK_REGION, streaming=False),
        system_prompt=ADVISOR_SYSTEM_PROMPT,
        tools=ADVISOR_TOOLS,
        callback_handler=handler,
    )


_THINKING_BLOCK = re.compile(r"<thinking>.*?</thinking>", re.IGNORECASE | re.DOTALL)
_STRAY_TAGS = re.compile(r"</?thinking>", re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    """Remove any model reasoning tags so only the operational answer is shown."""

    cleaned = _STRAY_TAGS.sub("", _THINKING_BLOCK.sub("", text)).strip()
    # If the whole answer was inside a reasoning block, fall back to the raw text
    # with tags removed rather than returning an empty string.
    return cleaned or _STRAY_TAGS.sub("", text).strip()


def ask(agent: Agent, question: str) -> str:
    """Ask the Advisor a question and return its final, sanitized text answer."""

    return _strip_thinking(str(agent(question)))


def demo_tools_offline() -> None:
    """Show the deterministic grounding without any network call.

    Runs the same tools the Advisor would call, so `python -m app.advisor` still
    demonstrates the tool layer when AWS/Bedrock is not reachable.
    """

    print("\n(Offline) Deterministic tools the Advisor calls:\n")
    decision = assess_incident(
        destination="Riverside Community Meals — Eastside",
        incident_type="thursday_distribution",
        requirements=["van driver", "packer", "site lead"],
    )
    print("  assess_incident(Eastside, thursday_distribution, [van driver, packer, site lead]):")
    print(f"    verdict: {decision['verdict']}")
    print(f"    CAN?    {decision['answers']['CAN']}")
    print(f"    HOW?    {decision['answers']['HOW']}")
    print(f"    WHAT IF? {decision['answers']['WHAT IF']}")
    print(f"    WHAT IS MISSING? {decision['answers']['WHAT IS MISSING']}")

    drivers = get_resources_by_required_capability("van_certified_driver")
    ids = [r["id"] for r in drivers["resources"]]
    print(f"\n  get_resources_by_required_capability(van_certified_driver) -> {ids or 'none available'}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print("=== MealMesh Advisor (Strands + Bedrock, tool-calling) ===")

    query = " ".join(sys.argv[1:]).strip()
    questions = [query] if query else list(DEMO_QUESTIONS)

    try:
        agent = build_advisor(verbose_output=True)
        for question in questions:
            print(f"\n> {question}")
            print(ask(agent, question))
    except Exception as exc:  # noqa: BLE001 - degrade gracefully to the offline demo
        print(f"\nBedrock unavailable ({type(exc).__name__}: {exc}).")
        demo_tools_offline()


if __name__ == "__main__":
    main()
