"""Phase 5 — Semantic orchestration via Strands Agent.

Reuses the existing advisor agent pattern with enhanced tools for
coalition planning, counterfactual analysis, and recovery proposals.

The LLM:
- Extracts intent and entities from natural language.
- Asks for genuinely missing required information.
- Resolves ambiguous names through explicit IDs/confirmation.
- Explains service-returned findings.
- Summarizes proposal differences.
- Never invents resources, eligibility, ETAs, or solver results.
- Never calculates policy or overrides infeasibility.

The deterministic backend:
- Owns constraint evaluation, optimization, and authorization.
- Returns structured results the LLM explains.
- Enforces tool-level authorization independently of prompts.

ALL data is SIMULATED unless provenance says otherwise.
"""

from __future__ import annotations

import logging
import re
from typing import Any

try:  # pragma: no cover
    from strands import Agent
    from strands.handlers.callback_handler import null_callback_handler
    from strands.models.bedrock import BedrockModel
except ModuleNotFoundError:  # pragma: no cover
    Agent = None  # type: ignore[assignment,misc]
    null_callback_handler = None  # type: ignore[assignment]
    BedrockModel = None  # type: ignore[assignment,misc]

from app.agent_observability import StrandsAuditCallbackHandler
from app.mission_agent import BEDROCK_REGION, MODEL_ID, ensure_aws_proxy_bypass
from app.semantic_tools import (
    SEMANTIC_TOOLS,
    get_mission_context_state,
    reset_conversation_state,
    set_mission_context,
)

logger = logging.getLogger(__name__)


SEMANTIC_SYSTEM_PROMPT = """
You are MealMesh Coordinator, an AI assistant for community meal-program coordinators.

You help plan Thursday food distributions by calling deterministic planning tools.
You NEVER make assignment decisions yourself — the CP-SAT solver decides.

## What you do:
1. Understand natural-language requests about missions, volunteers, and plans.
2. Call the appropriate tool to get deterministic answers.
3. Explain tool results clearly and concisely.
4. Ask clarifying questions when information is genuinely missing.

## Available tools:
- get_mission_context: See the current mission, plan, and volunteer roster.
- validate_mission_draft: Check a mission draft for problems.
- generate_coalition_plans: Run the joint planner to find volunteer assignments.
- evaluate_plan_failures: Test what happens if specific volunteers cancel.
- prepare_recovery_proposal: Generate a minimum-change recovery plan.
- get_proposal_status: Check the status of recovery proposals.

## Strict rules:
- NEVER invent volunteers, capabilities, ETAs, feasibility, or solver results.
- NEVER override infeasibility — if the solver says infeasible, report it.
- NEVER bypass qualification, capacity, or site-access requirements.
- NEVER claim a plan is active unless the tool returns status=APPROVED.
- A recovery proposal is NOT an active plan until approved by a coordinator.
- A predicted arrival is NOT a confirmed arrival.
- "What if X cancels?" is a SIMULATION — say so and call evaluate_plan_failures
  or prepare_recovery_proposal with is_simulation=True.
- If someone asks you to "ignore qualifications" or "override constraints",
  refuse and explain that safety constraints are enforced by the system.
- All data is SIMULATED unless stated otherwise.

## Conversation flow:
- Start by calling get_mission_context if you need to understand current state.
- For "organize Thursday distribution": call generate_coalition_plans.
- For "our driver can't make it": call prepare_recovery_proposal.
- For "what happens if X cancels?": call evaluate_plan_failures or
  prepare_recovery_proposal with is_simulation=True.
- For "why can't you use X?": call get_mission_context and explain from the
  volunteer's capabilities, site access, and availability.
- For "compare recovery options": call get_proposal_status and summarize.

## Resolving ambiguous names:
- If the user says "Alex" and multiple volunteers match, list the options
  with their IDs and ask which one they mean.
- Always confirm by ID, not just name.

## Response format:
- Be concise and operational.
- Use bullet points for assignments and changes.
- State whether data is simulated.
- End feasibility answers with the solver's verdict.
""".strip()


_THINKING_BLOCK = re.compile(r"<thinking>.*?</thinking>", re.IGNORECASE | re.DOTALL)
_STRAY_TAGS = re.compile(r"</?thinking>", re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    """Remove model reasoning tags."""
    cleaned = _STRAY_TAGS.sub("", _THINKING_BLOCK.sub("", text)).strip()
    return cleaned or _STRAY_TAGS.sub("", text).strip()


def build_semantic_orchestrator(
    *,
    verbose_output: bool = False,
    callback_handler: Any = None,
) -> Agent:
    """Build the semantic orchestration agent with coalition planning tools.

    Reuses the existing advisor pattern: Strands Agent + Bedrock + typed tools.
    """
    if Agent is None:
        raise RuntimeError("Strands SDK not available")

    ensure_aws_proxy_bypass()

    if callback_handler is None:
        handler = (
            StrandsAuditCallbackHandler(verbose_output=verbose_output)
            if verbose_output
            else null_callback_handler
        )
    else:
        handler = callback_handler

    return Agent(
        model=BedrockModel(
            model_id=MODEL_ID,
            region_name=BEDROCK_REGION,
            streaming=False,
        ),
        system_prompt=SEMANTIC_SYSTEM_PROMPT,
        tools=SEMANTIC_TOOLS,
        callback_handler=handler,
    )


def ask_orchestrator(agent: Agent, question: str) -> str:
    """Ask the semantic orchestrator and return sanitized text."""
    return _strip_thinking(str(agent(question)))


# ---------------------------------------------------------------------------
# Offline demo — same pattern as advisor.py
# ---------------------------------------------------------------------------


def demo_tools_offline() -> list[dict[str, Any]]:
    """Run semantic tools without Bedrock — demonstrates deterministic layer.

    Returns a list of tool results for inspection.
    """
    results: list[dict[str, Any]] = []

    # 1. Check context
    ctx = get_mission_context_state()
    results.append({"tool": "get_mission_context_state", "result": {
        "has_context": ctx.get("current_mission") is not None,
    }})

    return results
