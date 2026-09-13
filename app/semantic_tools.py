"""Phase 5 — Strands tools for semantic orchestration.

Typed tool wrappers around existing deterministic services. Each tool:
1. Accepts structured parameters from the agent.
2. Delegates to the authoritative backend service.
3. Returns structured results the agent explains (never invents).

The LLM extracts intent and entities; these tools own decisions.

ALL data is SIMULATED unless provenance says otherwise.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

try:  # pragma: no cover
    from strands import tool
except ModuleNotFoundError:  # pragma: no cover
    def tool(func=None, **kwargs):  # type: ignore[assignment]
        if func is not None:
            return func
        return lambda f: f

from app.coalition_planner import (
    CoalitionPlannerRequest,
    CoalitionPlannerResult,
    solve_coalition,
)
from app.contracts import (
    DataProvenance,
    MissionSpec,
    PlanSpec,
    PlanStatus,
    VehicleSpec,
    VolunteerSpec,
)
from app.counterfactual import (
    CounterfactualReport,
    run_counterfactual_analysis,
)
from app.recovery import (
    ApprovalRequest,
    ApprovalResult,
    RecoveryEngine,
    RecoveryProposalSpec,
    ResourceEvent,
    plan_recovery,
)
from app.validation import validate_plan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared in-memory state for conversational persistence
# ---------------------------------------------------------------------------

_conversation_state: dict[str, Any] = {
    "current_mission": None,
    "current_plan": None,
    "current_volunteers": None,
    "current_vehicles": None,
    "current_proposals": {},       # proposal_id -> RecoveryProposalSpec
    "current_counterfactual": None,
}

# Tool call tracking for bounds enforcement
_tool_call_counter: dict[str, int] = {}
_MAX_TOOL_CALLS_PER_TURN = 10


def reset_conversation_state() -> None:
    """Reset all conversational state. Used by tests and between sessions."""
    _conversation_state.update({
        "current_mission": None,
        "current_plan": None,
        "current_volunteers": None,
        "current_vehicles": None,
        "current_proposals": {},
        "current_counterfactual": None,
    })
    _tool_call_counter.clear()


def set_mission_context(
    mission: MissionSpec,
    volunteers: list[VolunteerSpec],
    vehicles: list[VehicleSpec],
    plan: PlanSpec | None = None,
) -> None:
    """Set conversation context from outside (e.g., API layer or test setup)."""
    _conversation_state["current_mission"] = mission
    _conversation_state["current_volunteers"] = volunteers
    _conversation_state["current_vehicles"] = vehicles
    if plan is not None:
        _conversation_state["current_plan"] = plan


def get_mission_context_state() -> dict[str, Any]:
    """Return current conversation state (read-only snapshot)."""
    return dict(_conversation_state)


def _check_tool_call_bound(tool_name: str) -> dict | None:
    """Enforce per-turn tool call limits. Returns error dict if exceeded."""
    total = sum(_tool_call_counter.values())
    if total >= _MAX_TOOL_CALLS_PER_TURN:
        return {
            "error": f"Tool call limit reached ({_MAX_TOOL_CALLS_PER_TURN} per turn). "
            "Please refine your question.",
            "tool": tool_name,
        }
    _tool_call_counter[tool_name] = _tool_call_counter.get(tool_name, 0) + 1
    return None


# ---------------------------------------------------------------------------
# Tool: get_mission_context
# ---------------------------------------------------------------------------


@tool
def get_mission_context() -> dict[str, Any]:
    """Return the current mission, plan, volunteer roster, and vehicles.

    Call this first to understand what mission is active, who is assigned,
    and what resources are available. All data is SIMULATED.

    Returns a dict with:
    - mission: the active MissionSpec (or null if none set)
    - plan: the current PlanSpec (or null)
    - volunteer_count: number of volunteers in roster
    - volunteer_names: list of {id, name, capabilities, opted_in}
    - vehicle_count: number of vehicles
    - has_context: whether a mission context is loaded
    - simulated: always true
    """
    logger.info("get_mission_context called")
    bound_err = _check_tool_call_bound("get_mission_context")
    if bound_err:
        return bound_err

    mission = _conversation_state.get("current_mission")
    plan = _conversation_state.get("current_plan")
    volunteers = _conversation_state.get("current_volunteers") or []
    vehicles = _conversation_state.get("current_vehicles") or []

    vol_summaries = [
        {
            "id": v.id,
            "name": v.name,
            "capabilities": v.capability_codes,
            "opted_in": v.opted_in,
            "site_access": v.authorized_site_ids,
        }
        for v in volunteers
    ]

    return {
        "mission": mission.model_dump(mode="json") if mission else None,
        "plan": plan.model_dump(mode="json") if plan else None,
        "volunteer_count": len(volunteers),
        "volunteer_names": vol_summaries,
        "vehicle_count": len(vehicles),
        "has_context": mission is not None,
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Tool: validate_mission_draft
# ---------------------------------------------------------------------------


@tool
def validate_mission_draft(
    mission_json: dict | None = None,
) -> dict[str, Any]:
    """Validate the current or provided mission draft against domain rules.

    Checks task definitions, time windows, capability requirements, and
    volunteer/vehicle coverage. Returns violations (blocking/warning).
    Does NOT run the solver — only deterministic validation.

    Args:
        mission_json: Optional mission dict to validate. If None, uses
            the current mission context.

    Returns dict with:
    - valid: bool — no blocking violations
    - violations: list of constraint violations
    - missing_info: list of missing required fields
    - simulated: true
    """
    logger.info("validate_mission_draft called")
    bound_err = _check_tool_call_bound("validate_mission_draft")
    if bound_err:
        return bound_err

    if mission_json is not None:
        try:
            mission = MissionSpec.model_validate(mission_json)
        except Exception as exc:
            return {
                "valid": False,
                "violations": [],
                "missing_info": [f"Invalid mission format: {exc}"],
                "simulated": True,
            }
    else:
        mission = _conversation_state.get("current_mission")
        if mission is None:
            return {
                "valid": False,
                "violations": [],
                "missing_info": [
                    "No mission context loaded. Provide mission details: "
                    "destination, date/time, and required roles."
                ],
                "simulated": True,
            }

    plan = _conversation_state.get("current_plan")
    volunteers = _conversation_state.get("current_volunteers") or []
    vehicles = _conversation_state.get("current_vehicles") or []

    # Check for genuinely missing info
    missing: list[str] = []
    if not mission.destination:
        missing.append("destination (which church/site?)")
    if not mission.tasks:
        missing.append("tasks (what roles are needed?)")
    if mission.deadline is None:
        missing.append("deadline (by when?)")

    if missing:
        return {
            "valid": False,
            "violations": [],
            "missing_info": missing,
            "simulated": True,
        }

    # Run validation if we have a plan
    violations_list: list[dict] = []
    if plan is not None:
        violations = validate_plan(plan, mission, volunteers, vehicles)
        violations_list = [v.model_dump(mode="json") for v in violations]

    blocking = [v for v in violations_list if v.get("severity") == "blocking"]

    return {
        "valid": len(blocking) == 0,
        "violations": violations_list,
        "missing_info": [],
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Tool: generate_coalition_plans
# ---------------------------------------------------------------------------


@tool
def generate_coalition_plans(
    max_alternatives: int = 3,
    time_limit_seconds: float = 10.0,
) -> dict[str, Any]:
    """Run the joint coalition planner on the current mission context.

    Uses CP-SAT to find feasible volunteer assignments that jointly satisfy
    all constraints: capabilities, site access, vehicle eligibility,
    availability windows, and no double-booking.

    Args:
        max_alternatives: How many distinct plans to generate (1-10, default 3).
        time_limit_seconds: Solver time limit (default 10s).

    Returns dict with:
    - feasible: bool
    - solver_status: OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN
    - alternatives: list of plans with assignments and labels
    - violations: list of constraint violations if infeasible
    - infeasible_reasons: list of reasons if infeasible
    - simulated: true
    """
    logger.info("generate_coalition_plans called")
    bound_err = _check_tool_call_bound("generate_coalition_plans")
    if bound_err:
        return bound_err

    mission = _conversation_state.get("current_mission")
    if mission is None:
        return {
            "error": "No mission context loaded. Call get_mission_context first "
            "or provide mission details.",
            "feasible": False,
            "simulated": True,
        }

    volunteers = _conversation_state.get("current_volunteers") or []
    vehicles = _conversation_state.get("current_vehicles") or []

    max_alternatives = max(1, min(10, max_alternatives))

    request = CoalitionPlannerRequest(
        mission=mission,
        volunteers=volunteers,
        vehicles=vehicles,
        max_alternatives=max_alternatives,
        time_limit_seconds=time_limit_seconds,
    )

    result: CoalitionPlannerResult = solve_coalition(request)

    # Persist the best plan in conversation state
    if result.feasible and result.alternatives:
        best_plan = result.alternatives[0].plan
        _conversation_state["current_plan"] = best_plan

    return {
        "feasible": result.feasible,
        "solver_status": result.solver_status,
        "alternatives": [
            {
                "label": alt.label,
                "objective_value": alt.objective_value,
                "objective_description": alt.objective_description,
                "assignments": [
                    {
                        "task_id": a.task_id,
                        "volunteer_id": a.volunteer_id,
                        "vehicle_id": a.vehicle_id,
                    }
                    for a in alt.plan.assignments
                ],
            }
            for alt in result.alternatives
        ],
        "violations": [v.model_dump(mode="json") for v in result.violations],
        "infeasible_reasons": result.infeasible_reasons,
        "solve_duration_seconds": result.solve_duration_seconds,
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Tool: evaluate_plan_failures
# ---------------------------------------------------------------------------


@tool
def evaluate_plan_failures(
    resource_ids_to_test: list[str] | None = None,
    time_limit_seconds: float = 5.0,
) -> dict[str, Any]:
    """Run counterfactual what-if analysis: what happens if a resource cancels?

    For each specified resource (or all assigned resources if none specified),
    simulates removal and tests whether the mission can still be completed.
    DOES NOT change any live state — this is a pure simulation.

    Args:
        resource_ids_to_test: Specific volunteer/vehicle IDs to test.
            If None, tests all volunteers in the current plan.
        time_limit_seconds: Per-scenario solver time limit.

    Returns dict with:
    - scenarios: per-resource results (robust/recoverable/infeasible/unknown)
    - single_points_of_failure: IDs whose loss breaks the mission
    - summary: human-readable summary
    - simulated: true
    """
    logger.info("evaluate_plan_failures called with resource_ids=%s", resource_ids_to_test)
    bound_err = _check_tool_call_bound("evaluate_plan_failures")
    if bound_err:
        return bound_err

    mission = _conversation_state.get("current_mission")
    plan = _conversation_state.get("current_plan")

    if mission is None or plan is None:
        return {
            "error": "No mission and plan loaded. Generate a plan first.",
            "simulated": True,
        }

    volunteers = _conversation_state.get("current_volunteers") or []
    vehicles = _conversation_state.get("current_vehicles") or []

    report: CounterfactualReport = run_counterfactual_analysis(
        mission=mission,
        baseline_plan=plan,
        volunteers=volunteers,
        vehicles=vehicles,
        resource_ids_to_test=resource_ids_to_test,
        time_limit_seconds=time_limit_seconds,
    )

    # Persist for later reference
    _conversation_state["current_counterfactual"] = report

    return {
        "total_scenarios": report.total_scenarios,
        "robust_count": report.robust_count,
        "recoverable_count": report.recoverable_count,
        "infeasible_count": report.infeasible_count,
        "unknown_count": report.unknown_count,
        "single_points_of_failure": report.single_points_of_failure,
        "scenarios": [
            {
                "resource_id": s.removed_resource_id,
                "resource_name": s.removed_resource_name,
                "recovery_status": s.recovery_status,
                "mission_impact": s.mission_impact,
                "required_replacements": s.required_replacements,
                "bottleneck": s.bottleneck.model_dump(mode="json") if s.bottleneck else None,
            }
            for s in report.scenarios
        ],
        "summary": report.summary,
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Tool: prepare_recovery_proposal
# ---------------------------------------------------------------------------


@tool
def prepare_recovery_proposal(
    unavailable_resource_ids: list[str],
    is_simulation: bool = True,
) -> dict[str, Any]:
    """Generate a minimum-change recovery proposal after resource cancellations.

    Creates a version-bound proposal that preserves as many existing assignments
    as possible. The proposal must be APPROVED by a coordinator before activation.

    IMPORTANT: if is_simulation=True (default), this is a what-if analysis that
    does NOT mark any resource as actually unavailable. Only set is_simulation=False
    when reporting a real cancellation.

    Args:
        unavailable_resource_ids: List of volunteer/vehicle IDs that are unavailable.
        is_simulation: If True, this is a hypothetical what-if test (default True).

    Returns dict with:
    - proposal_id: ID for approval tracking
    - is_feasible: whether a recovery plan was found
    - changes: list of assignment changes (before/after)
    - changes_count: number of changed assignments
    - capability_gaps: missing capabilities if infeasible
    - safe_actions: recommended operator actions if infeasible
    - targeted_request: specific volunteer request if infeasible
    - status: "pending" (requires coordinator approval)
    - simulated: true
    """
    logger.info(
        "prepare_recovery_proposal called, unavailable=%s, simulation=%s",
        unavailable_resource_ids,
        is_simulation,
    )
    bound_err = _check_tool_call_bound("prepare_recovery_proposal")
    if bound_err:
        return bound_err

    mission = _conversation_state.get("current_mission")
    plan = _conversation_state.get("current_plan")

    if mission is None or plan is None:
        return {
            "error": "No mission and plan loaded. Generate a plan first.",
            "simulated": True,
        }

    if not unavailable_resource_ids:
        return {
            "error": "No resource IDs provided. Specify which volunteers/vehicles "
            "are unavailable.",
            "simulated": True,
        }

    volunteers = _conversation_state.get("current_volunteers") or []
    vehicles = _conversation_state.get("current_vehicles") or []

    proposal: RecoveryProposalSpec = plan_recovery(
        mission=mission,
        current_plan=plan,
        volunteers=volunteers,
        vehicles=vehicles,
        unavailable_resource_ids=unavailable_resource_ids,
    )

    # Track proposal
    _conversation_state["current_proposals"][proposal.id] = proposal

    return {
        "proposal_id": proposal.id,
        "is_feasible": proposal.is_feasible,
        "changes": [c.model_dump(mode="json") for c in proposal.changes],
        "changes_count": proposal.changes_count,
        "infeasible_reasons": proposal.infeasible_reasons,
        "capability_gaps": proposal.capability_gaps,
        "safe_actions": proposal.safe_actions,
        "targeted_request": proposal.targeted_request,
        "status": proposal.status,
        "is_simulation": is_simulation,
        "expires_at": proposal.expires_at.isoformat(),
        "note": (
            "This is a SIMULATION — no live state changed."
            if is_simulation
            else "This is a LIVE recovery proposal. Requires coordinator approval."
        ),
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Tool: get_proposal_status
# ---------------------------------------------------------------------------


@tool
def get_proposal_status(
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """Check the status of a recovery proposal.

    Args:
        proposal_id: The proposal ID to look up. If None, returns all
            active proposals for the current mission.

    Returns dict with:
    - proposals: list of {id, status, is_feasible, changes_count, expires_at}
    - simulated: true
    """
    logger.info("get_proposal_status called for proposal_id=%s", proposal_id)
    bound_err = _check_tool_call_bound("get_proposal_status")
    if bound_err:
        return bound_err

    proposals = _conversation_state.get("current_proposals", {})

    if proposal_id is not None:
        proposal = proposals.get(proposal_id)
        if proposal is None:
            return {
                "proposals": [],
                "error": f"Proposal '{proposal_id}' not found.",
                "simulated": True,
            }
        return {
            "proposals": [_summarize_proposal(proposal)],
            "simulated": True,
        }

    # All proposals for current mission
    mission = _conversation_state.get("current_mission")
    mission_id = mission.id if mission else None

    result = [
        _summarize_proposal(p)
        for p in proposals.values()
        if mission_id is None or p.mission_id == mission_id
    ]

    return {
        "proposals": result,
        "simulated": True,
    }


def _summarize_proposal(p: RecoveryProposalSpec) -> dict:
    return {
        "id": p.id,
        "status": p.status,
        "is_feasible": p.is_feasible,
        "changes_count": p.changes_count,
        "changes": [
            {
                "task_label": c.task_label,
                "before": c.before_volunteer_name,
                "after": c.after_volunteer_name,
                "type": c.change_type,
            }
            for c in p.changes
        ],
        "capability_gaps": p.capability_gaps,
        "expires_at": p.expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# All semantic tools for agent registration
# ---------------------------------------------------------------------------

SEMANTIC_TOOLS = [
    get_mission_context,
    validate_mission_draft,
    generate_coalition_plans,
    evaluate_plan_failures,
    prepare_recovery_proposal,
    get_proposal_status,
]
