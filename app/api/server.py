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
from app.coalition_planner import (
    CoalitionPlannerRequest,
    solve_coalition,
)
from app.counterfactual import run_counterfactual_analysis
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


class JointPlanRequest(BaseModel):
    """Request body for the joint coalition planner endpoint."""
    mission: dict
    volunteers: list[dict]
    vehicles: list[dict] = Field(default_factory=list)
    max_alternatives: int = 3
    time_limit_seconds: float = 10.0


@app.post("/api/joint-plan")
def post_joint_plan(request: JointPlanRequest) -> dict:
    """Solve a joint coalition assignment using the deterministic CP-SAT planner.

    This endpoint selects volunteers JOINTLY across all tasks, preventing
    double-booking and enforcing capability, site-access, vehicle-driver
    compatibility, and availability constraints simultaneously.

    Requires feature flag MEALMESH_JOINT_PLANNING=true (defaults to true).
    """
    import os

    from app.contracts import MissionSpec, VehicleSpec, VolunteerSpec

    if os.environ.get("MEALMESH_JOINT_PLANNING", "true").lower() != "true":
        return {
            "error": "Joint planning is disabled. Set MEALMESH_JOINT_PLANNING=true to enable.",
            "feasible": False,
        }

    mission = MissionSpec.model_validate(request.mission)
    volunteers = [VolunteerSpec.model_validate(v) for v in request.volunteers]
    vehicles = [VehicleSpec.model_validate(v) for v in request.vehicles]

    planner_request = CoalitionPlannerRequest(
        mission=mission,
        volunteers=volunteers,
        vehicles=vehicles,
        max_alternatives=request.max_alternatives,
        time_limit_seconds=request.time_limit_seconds,
    )

    result = solve_coalition(planner_request)

    return {
        "result": result.model_dump(mode="json"),
        "simulated": True,
    }


class CounterfactualRequest(BaseModel):
    """Request body for counterfactual failure analysis."""
    mission: dict
    baseline_plan: dict
    volunteers: list[dict]
    vehicles: list[dict] = Field(default_factory=list)
    resource_ids_to_test: list[str] | None = None
    time_limit_seconds: float = 5.0


@app.post("/api/counterfactual")
def post_counterfactual(request: CounterfactualRequest) -> dict:
    """Run counterfactual failure analysis on a baseline plan.

    For each specified resource, simulates removal and tests whether
    the mission can still be completed. Does not mutate live state.
    """
    from app.contracts import MissionSpec, PlanSpec, VehicleSpec, VolunteerSpec

    mission = MissionSpec.model_validate(request.mission)
    baseline = PlanSpec.model_validate(request.baseline_plan)
    volunteers = [VolunteerSpec.model_validate(v) for v in request.volunteers]
    vehicles = [VehicleSpec.model_validate(v) for v in request.vehicles]

    report = run_counterfactual_analysis(
        mission=mission,
        baseline_plan=baseline,
        volunteers=volunteers,
        vehicles=vehicles,
        resource_ids_to_test=request.resource_ids_to_test,
        time_limit_seconds=request.time_limit_seconds,
    )

    return {
        "report": report.model_dump(mode="json"),
        "simulated": True,
    }


class RecoveryEventRequest(BaseModel):
    """Request to ingest a resource unavailability event."""
    event: dict


class RecoveryPlanRequest(BaseModel):
    """Request to generate a recovery proposal."""
    mission: dict
    current_plan: dict
    volunteers: list[dict]
    vehicles: list[dict] = Field(default_factory=list)
    unavailable_resource_ids: list[str]
    task_statuses: dict[str, str] | None = None
    triggering_event_ids: list[str] | None = None


class RecoveryApprovalRequest(BaseModel):
    """Request to approve a recovery proposal."""
    proposal_id: str
    coordinator_id: str
    expected_plan_version: int
    expected_mission_version: int


# In-memory recovery engine — resets on restart
_recovery_engine = None


def _get_recovery_engine():
    global _recovery_engine
    if _recovery_engine is None:
        from app.recovery import RecoveryEngine
        _recovery_engine = RecoveryEngine()
    return _recovery_engine


@app.post("/api/recovery/event")
def post_recovery_event(request: RecoveryEventRequest) -> dict:
    """Ingest a resource unavailability event with deduplication."""
    from app.recovery import ResourceEvent

    engine = _get_recovery_engine()
    event = ResourceEvent.model_validate(request.event)
    result = engine.ingest_event(event)
    return {"result": result.model_dump(mode="json"), "simulated": True}


@app.post("/api/recovery/plan")
def post_recovery_plan(request: RecoveryPlanRequest) -> dict:
    """Generate a minimum-change recovery proposal."""
    from app.contracts import MissionSpec, PlanSpec, VehicleSpec, VolunteerSpec
    from app.recovery import TaskExecutionStatus

    engine = _get_recovery_engine()
    mission = MissionSpec.model_validate(request.mission)
    current_plan = PlanSpec.model_validate(request.current_plan)
    volunteers = [VolunteerSpec.model_validate(v) for v in request.volunteers]
    vehicles = [VehicleSpec.model_validate(v) for v in request.vehicles]

    task_statuses = None
    if request.task_statuses:
        task_statuses = {
            tid: TaskExecutionStatus(s) for tid, s in request.task_statuses.items()
        }

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=current_plan,
        volunteers=volunteers,
        vehicles=vehicles,
        unavailable_resource_ids=request.unavailable_resource_ids,
        task_statuses=task_statuses,
        triggering_event_ids=request.triggering_event_ids,
    )

    return {"proposal": proposal.model_dump(mode="json"), "simulated": True}


@app.post("/api/recovery/approve")
def post_recovery_approve(request: RecoveryApprovalRequest) -> dict:
    """Approve a recovery proposal with version and reservation checks."""
    from app.recovery import ApprovalRequest

    engine = _get_recovery_engine()
    result = engine.approve_proposal(ApprovalRequest(
        proposal_id=request.proposal_id,
        coordinator_id=request.coordinator_id,
        expected_plan_version=request.expected_plan_version,
        expected_mission_version=request.expected_mission_version,
    ))
    return {"result": result.model_dump(mode="json"), "simulated": True}


@app.get("/api/recovery/risk/{mission_id}")
def get_recovery_risk(mission_id: str) -> dict:
    """Get the current risk status of a mission."""
    engine = _get_recovery_engine()
    status = engine.get_mission_risk_status(mission_id)
    return {"status": status.model_dump(mode="json"), "simulated": True}


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
    from app.agent_observability import StrandsAuditCallbackHandler
    from app.mission_agent import ensure_aws_proxy_bypass

    ensure_aws_proxy_bypass()
    audit_handler = StrandsAuditCallbackHandler(verbose_output=False)
    try:
        agent = build_advisor(verbose_output=False, callback_handler=audit_handler)
        answer = ask(agent, request.question)
        return {
            "answer": answer,
            "used_llm": True,
            "tools": list(agent.tool_names),
            "audit_summary": audit_handler.summary().model_dump(mode="json"),
        }
    except Exception as exc:  # noqa: BLE001 - graceful fallback, mirrors /api/extract
        return {
            "answer": (
                f"Advisor unavailable ({type(exc).__name__}). This feature needs AWS "
                "Bedrock access. The deterministic pipeline and Sentinel still work offline."
            ),
            "used_llm": False,
            "tools": [],
            "audit_summary": None,
        }


# ---------------------------------------------------------------------------
# Phase 5: Semantic orchestration endpoints
# ---------------------------------------------------------------------------


class SemanticRequest(BaseModel):
    """Natural-language request for the semantic orchestrator."""
    question: str
    mission: dict | None = None
    volunteers: list[dict] | None = None
    vehicles: list[dict] | None = None


class SemanticContextRequest(BaseModel):
    """Load mission context for semantic orchestration."""
    mission: dict
    volunteers: list[dict]
    vehicles: list[dict] = Field(default_factory=list)
    plan: dict | None = None


@app.post("/api/semantic/context")
def post_semantic_context(request: SemanticContextRequest) -> dict:
    """Load mission context for the semantic orchestrator.

    Call this before /api/semantic to set up the mission, volunteers,
    vehicles, and optionally a current plan.
    """
    from app.contracts import MissionSpec, PlanSpec, VehicleSpec, VolunteerSpec
    from app.semantic_tools import set_mission_context

    mission = MissionSpec.model_validate(request.mission)
    volunteers = [VolunteerSpec.model_validate(v) for v in request.volunteers]
    vehicles = [VehicleSpec.model_validate(v) for v in request.vehicles]
    plan = PlanSpec.model_validate(request.plan) if request.plan else None

    set_mission_context(mission, volunteers, vehicles, plan)

    return {
        "status": "context_loaded",
        "mission_id": mission.id,
        "volunteer_count": len(volunteers),
        "vehicle_count": len(vehicles),
        "has_plan": plan is not None,
        "simulated": True,
    }


@app.post("/api/semantic")
def post_semantic(request: SemanticRequest) -> dict:
    """Ask the semantic orchestrator a natural-language question.

    The orchestrator uses typed tools to call deterministic backend services.
    The LLM explains results but never makes assignment decisions.

    Optionally include mission/volunteers/vehicles to set context inline.
    Falls back gracefully when Bedrock is unreachable.
    """
    from app.agent_observability import StrandsAuditCallbackHandler
    from app.contracts import MissionSpec, PlanSpec, VehicleSpec, VolunteerSpec
    from app.mission_agent import ensure_aws_proxy_bypass
    from app.semantic_orchestrator import ask_orchestrator, build_semantic_orchestrator
    from app.semantic_tools import reset_conversation_state, set_mission_context

    # Load inline context if provided
    if request.mission is not None:
        mission = MissionSpec.model_validate(request.mission)
        volunteers = [
            VolunteerSpec.model_validate(v) for v in (request.volunteers or [])
        ]
        vehicles = [
            VehicleSpec.model_validate(v) for v in (request.vehicles or [])
        ]
        set_mission_context(mission, volunteers, vehicles)

    ensure_aws_proxy_bypass()
    audit_handler = StrandsAuditCallbackHandler(verbose_output=False)
    try:
        agent = build_semantic_orchestrator(
            verbose_output=False, callback_handler=audit_handler
        )
        answer = ask_orchestrator(agent, request.question)
        return {
            "answer": answer,
            "used_llm": True,
            "tools": list(agent.tool_names),
            "audit_summary": audit_handler.summary().model_dump(mode="json"),
            "simulated": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "answer": (
                f"Semantic orchestrator unavailable ({type(exc).__name__}). "
                "This feature needs AWS Bedrock access. "
                "The deterministic tools still work via /api/joint-plan, "
                "/api/counterfactual, and /api/recovery/* endpoints."
            ),
            "used_llm": False,
            "tools": [],
            "audit_summary": None,
            "simulated": True,
        }


@app.post("/api/semantic/reset")
def post_semantic_reset() -> dict:
    """Reset semantic orchestrator conversation state."""
    from app.semantic_tools import reset_conversation_state

    reset_conversation_state()
    return {"status": "reset", "simulated": True}


@app.get("/api/proposal/{proposal_id}")
def get_proposal(proposal_id: str) -> dict:
    """Get the status of a recovery proposal from semantic orchestrator state."""
    from app.semantic_tools import get_mission_context_state

    state = get_mission_context_state()
    proposals = state.get("current_proposals", {})
    proposal = proposals.get(proposal_id)

    if proposal is None:
        return {"error": f"Proposal '{proposal_id}' not found.", "simulated": True}

    return {
        "proposal": proposal.model_dump(mode="json"),
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Phase 6: Mission-control endpoints
# ---------------------------------------------------------------------------


class MissionControlRequest(BaseModel):
    """Request body for mission-control assembly."""
    mission: dict
    volunteers: list[dict]
    vehicles: list[dict] = Field(default_factory=list)
    plan: dict | None = None
    removed_resource_ids: list[str] = Field(default_factory=list)


@app.post("/api/mission-control")
def post_mission_control(request: MissionControlRequest) -> dict:
    """Assemble the full mission-control view for the UI.

    Returns joint plan, counterfactual analysis, task assignments,
    volunteer markers, SPOFs, and recovery data in a single payload.
    """
    from app.contracts import MissionSpec, PlanSpec, VehicleSpec, VolunteerSpec
    from app.mission_control import build_mission_control_payload

    mission = MissionSpec.model_validate(request.mission)
    volunteers = [VolunteerSpec.model_validate(v) for v in request.volunteers]
    vehicles = [VehicleSpec.model_validate(v) for v in request.vehicles]
    plan = PlanSpec.model_validate(request.plan) if request.plan else None

    payload = build_mission_control_payload(
        mission=mission,
        volunteers=volunteers,
        vehicles=vehicles,
        plan=plan,
    )

    return payload.model_dump(mode="json")


@app.post("/api/mission-control/simulate-removal")
def post_simulate_removal(request: MissionControlRequest) -> dict:
    """Simulate removing resources and return the impact + recovery proposal.

    This is a SIMULATION — live state is not mutated.
    """
    from app.contracts import MissionSpec, PlanSpec, VehicleSpec, VolunteerSpec
    from app.mission_control import build_mission_control_payload
    from app.recovery import RecoveryEngine

    mission = MissionSpec.model_validate(request.mission)
    volunteers = [VolunteerSpec.model_validate(v) for v in request.volunteers]
    vehicles = [VehicleSpec.model_validate(v) for v in request.vehicles]
    plan = PlanSpec.model_validate(request.plan) if request.plan else None

    if not request.removed_resource_ids or plan is None:
        return {"error": "removed_resource_ids and plan are required", "simulated": True}

    # Use a fresh engine for simulation isolation
    engine = RecoveryEngine()
    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=plan,
        volunteers=volunteers,
        vehicles=vehicles,
        unavailable_resource_ids=request.removed_resource_ids,
    )

    # Build recovery view data
    recovery_data = {
        "id": proposal.id,
        "is_feasible": proposal.is_feasible,
        "what_changed": f"Removed: {', '.join(request.removed_resource_ids)}",
        "unchanged_assignments": [
            c.task_label for c in proposal.changes
            if c.change_type == "unchanged"
        ],
        "changes": [c.model_dump(mode="json") for c in proposal.changes],
        "capability_gaps": list(proposal.capability_gaps),
        "safe_actions": list(proposal.safe_actions),
        "targeted_request": proposal.targeted_request,
        "pending_confirmations": list(proposal.proposed_plan.outstanding_confirmations)
        if proposal.proposed_plan else [],
        "requirements_satisfied": proposal.is_feasible and not proposal.capability_gaps,
        "expires_label": proposal.expires_at.strftime("%H:%M %Z")
        if proposal.expires_at else None,
    }

    # Rebuild the mission-control payload with updated plan
    remaining_vols = [v for v in volunteers if v.id not in request.removed_resource_ids]
    payload = build_mission_control_payload(
        mission=mission,
        volunteers=remaining_vols,
        vehicles=vehicles,
        plan=proposal.proposed_plan if proposal.is_feasible else plan,
        recovery_proposal=recovery_data,
        risk_status="at_risk" if proposal.is_feasible else "blocked",
        risk_reason=f"Resource(s) removed: {', '.join(request.removed_resource_ids)}"
        + (f" — {'; '.join(proposal.capability_gaps)}" if proposal.capability_gaps else ""),
    )

    return payload.model_dump(mode="json")


@app.get("/api/mission-control/fixture")
def get_mission_control_fixture() -> dict:
    """Return the Thursday fixture data formatted for the mission-control UI.

    This endpoint provides a ready-to-render demo payload without requiring
    the caller to assemble mission/volunteer/vehicle data manually.

    Includes _raw_* fields for the simulation endpoint to re-use.
    """
    from tests.fixtures.thursday_fixture import (
        build_church_van,
        build_eastside_mission,
        build_valid_plan,
        build_volunteers,
    )
    from app.mission_control import build_mission_control_payload

    mission = build_eastside_mission()
    volunteers = build_volunteers()
    vehicles = [build_church_van()]
    plan = build_valid_plan(mission)

    payload = build_mission_control_payload(
        mission=mission,
        volunteers=volunteers,
        vehicles=vehicles,
        plan=plan,
    )

    result = payload.model_dump(mode="json")
    # Attach raw serialized data for simulation round-trips
    result["_raw_mission"] = mission.model_dump(mode="json")
    result["_raw_volunteers"] = [v.model_dump(mode="json") for v in volunteers]
    result["_raw_vehicles"] = [v.model_dump(mode="json") for v in vehicles]
    result["_raw_plan"] = plan.model_dump(mode="json")
    return result


@app.get("/mission-control")
def mission_control_page() -> FileResponse:
    """Serve the mission-control dashboard."""
    return FileResponse(STATIC_DIR / "mission-control.html")


@app.get("/api/agent/audit")
def get_agent_audit() -> dict:
    """Return accumulated Strands agent execution audit logs."""
    from app.agent_observability import get_global_audit_trail

    return {"records": get_global_audit_trail()}


@app.delete("/api/agent/audit")
def delete_agent_audit() -> dict:
    """Clear accumulated Strands agent execution audit logs."""
    from app.agent_observability import clear_global_audit_trail

    clear_global_audit_trail()
    return {"status": "cleared"}
