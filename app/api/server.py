"""FastAPI backend + static dashboard for MealMesh.

Run:
    uvicorn app.api.server:app --reload
Then open http://localhost:8000

Endpoints:
    GET  /               -> the dashboard (index.html)
    GET  /api/scenario   -> world: resources, destinations, hyperedges, presets
    POST /api/plan       -> run the deterministic pipeline for a mission + failures
    POST /api/extract    -> natural language -> structured Mission (Bedrock, w/ fallback)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.scenario import (
    SCENARIO_HYPEREDGES,
    build_catalog,
    resolve_destination,
    scenario_payload,
)
from app.mission import Mission
from app.orchestration import run_pipeline

app = FastAPI(title="MealMesh", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PlanRequest(BaseModel):
    mission: dict
    failed_resource_ids: list[str] = Field(default_factory=list)
    min_capacity: int | None = None


class ExtractRequest(BaseModel):
    query: str


class AdvisorRequest(BaseModel):
    question: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/scenario")
def get_scenario() -> dict:
    return scenario_payload()


@app.get("/api/sentinel")
def get_sentinel(notify: bool = False) -> dict:
    """Replay the autonomous background-monitoring loop (the 'Agent for Humans' core).

    The sentinel watches world-state changes and applies a deterministic escalation
    policy: stay silent, auto-recompose silently when a loss can be absorbed, and
    escalate to a human ONLY when a genuine decision is required. The LLM is never
    in this loop. Returns the full timeline so the dashboard can replay it.

    ``summary.notifications`` reports where escalations are routed (Slack /
    webhook / not configured) without ever exposing the webhook URL.

    This is a *replay* of a canned timeline, so by default it renders the alerts
    it would send without sending them — browsing the dashboard can never spam a
    real channel. Pass ``?notify=true`` to actually deliver (used for a live demo).
    """
    from app.notifications import build_notifier
    from app.sentinel import build_demo_mission, run_sentinel_demo

    notifier = build_notifier(force_dry_run=not notify)
    observations = run_sentinel_demo(notifier=notifier)
    escalated = sum(1 for observation in observations if observation.escalation is not None)
    delivered = sum(
        1
        for observation in observations
        if observation.notification is not None and observation.notification.delivered
    )
    return {
        "mission": build_demo_mission().model_dump(mode="json"),
        "observations": [observation.model_dump(mode="json") for observation in observations],
        "summary": {
            "total": len(observations),
            "autonomous": len(observations) - escalated,
            "escalated": escalated,
            "delivered": delivered,
            "notifications": notifier.describe(),
        },
    }


@app.post("/api/plan")
def post_plan(request: PlanRequest) -> dict:
    mission = Mission.model_validate(request.mission)
    catalog = build_catalog(request.failed_resource_ids, destination=mission.destination)

    result = run_pipeline(
        mission,
        resources=catalog,
        hyperedges=list(SCENARIO_HYPEREDGES),
        include_resilience=True,
        include_hypergraph=True,
        coalition_min_capacity=request.min_capacity or 0,
    )

    return {
        "result": result.model_dump(mode="json"),
        "failed_resource_ids": list(request.failed_resource_ids),
        "destination": resolve_destination(mission.destination),
    }


@app.post("/api/extract")
def post_extract(request: ExtractRequest) -> dict:
    from app.mission_agent import build_agent, build_demo_mission, ensure_aws_proxy_bypass

    ensure_aws_proxy_bypass()
    try:
        agent = build_agent(verbose_output=False)
        result = agent(request.query)
        mission = result.structured_output
        return {
            "mission": mission.model_dump(mode="json"),
            "used_llm": True,
            "message": "Extracted by Amazon Bedrock (Nova-lite).",
        }
    except Exception as exc:  # noqa: BLE001 - surface any failure as a graceful fallback
        return {
            "mission": build_demo_mission().model_dump(mode="json"),
            "used_llm": False,
            "message": f"LLM unavailable ({type(exc).__name__}); using the local demo mission.",
        }


@app.post("/api/advisor")
def post_advisor(request: AdvisorRequest) -> dict:
    """Ask the tool-calling Advisor agent (Strands + Bedrock).

    The agent answers by calling deterministic tools; the CP-SAT pipeline still
    owns every decision. Falls back gracefully when Bedrock is unreachable.
    """
    from app.advisor import ask, build_advisor
    from app.mission_agent import ensure_aws_proxy_bypass

    ensure_aws_proxy_bypass()
    try:
        agent = build_advisor(verbose_output=False)
        answer = ask(agent, request.question)
        return {"answer": answer, "used_llm": True, "tools": list(agent.tool_names)}
    except Exception as exc:  # noqa: BLE001 - graceful fallback, mirrors /api/extract
        return {
            "answer": (
                f"Advisor unavailable ({type(exc).__name__}). This feature needs AWS "
                "Bedrock access. The deterministic pipeline and Sentinel still work offline."
            ),
            "used_llm": False,
            "tools": [],
        }
