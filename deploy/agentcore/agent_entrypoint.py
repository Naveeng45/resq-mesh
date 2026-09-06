"""Amazon Bedrock AgentCore Runtime entrypoint for MealMesh.

This hosts MealMesh behind AgentCore Runtime without changing the core: the
deterministic CP-SAT pipeline still owns every decision. AgentCore only provides
the hosted transport, auth, scaling, and observability.

Payload actions
---------------
    {"action": "assess", "mission": {...}}   -> deterministic pipeline (no LLM)
    {"action": "ask", "question": "..."}     -> tool-calling Advisor (Bedrock)
    (anything else)                          -> assess the Thursday Eastside window

The "assess" path needs no AWS at all, so this file is runnable and testable
locally:

    python deploy/agentcore/agent_entrypoint.py            # prints a sample result

Deploy (from the repo root)
---------------------------
    pip install -r deploy/agentcore/requirements-agentcore.txt
    agentcore configure --entrypoint deploy/agentcore/agent_entrypoint.py
    agentcore launch                # builds (arm64) + deploys to AgentCore Runtime
    agentcore invoke '{"action": "assess", "mission": {"destination": "Riverside Community Meals — Eastside", "incident_type": "thursday_distribution"}}'
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the repo importable whether run as a module, a script, or inside the
# AgentCore container.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _assess(mission_payload: dict) -> dict:
    """Run the deterministic pipeline. No LLM, no network."""

    from app.mission import Mission
    from app.orchestration import render_report, run_pipeline

    data = mission_payload or {}
    mission = Mission(
        destination=data.get("destination", "Riverside Community Meals — Eastside"),
        incident_type=data.get("incident_type", "thursday_distribution"),
        requirements=data.get("requirements", ["van driver", "packer", "site lead"]),
        constraints=data.get("constraints", ["van certification required to drive"]),
    )
    result = run_pipeline(
        mission,
        include_resilience=True,
        include_hypergraph=False,
        coalition_min_capacity=int(data.get("min_capacity", 0)),
    )
    return {
        "verdict": result.verdict,
        "answers": result.answers,
        "selected_resource_ids": (
            result.coalition.selected_resource_ids if result.coalition else []
        ),
        "missing_capabilities": result.missing_capabilities,
        "trace_id": result.trace_id,
        "report": render_report(result),
    }


def _ask(question: str) -> dict:
    """Answer via the tool-calling Advisor agent (Strands + Bedrock)."""

    from app.advisor import ask, build_advisor

    agent = build_advisor(verbose_output=False)
    return {"answer": ask(agent, question), "tools": list(agent.tool_names)}


def handle(payload: dict | None) -> dict:
    """Route an AgentCore payload to the right handler. Pure and testable."""

    payload = payload or {}
    action = payload.get("action")
    question = payload.get("question") or payload.get("prompt")

    if action == "ask" or (action is None and question):
        return _ask(question or "")
    return _assess(payload.get("mission", {}))


# --- AgentCore wiring (optional import so the file runs without the SDK) ------
try:
    from bedrock_agentcore import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context=None):  # noqa: ANN001 - AgentCore signature
        return handle(payload)

    _HAS_AGENTCORE = True
except ModuleNotFoundError:  # pragma: no cover - exercised only outside the container
    app = None
    _HAS_AGENTCORE = False


if __name__ == "__main__":
    if _HAS_AGENTCORE:
        app.run()  # starts the AgentCore Runtime HTTP server (inside the container)
    else:
        sample = handle(
            {
                "action": "assess",
                "mission": {
                    "destination": "Riverside Community Meals — Eastside",
                    "incident_type": "thursday_distribution",
                },
            }
        )
        print(json.dumps(sample, indent=2))
