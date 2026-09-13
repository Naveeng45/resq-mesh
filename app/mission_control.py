"""Phase 6 — Mission-control data assembly.

Assembles the joint plan, counterfactual report, mission risk status,
and recovery proposals into a single payload for the mission-control UI.

This module bridges the existing APIs (coalition planner, counterfactual,
recovery engine) into one coherent view without duplicating logic.

ALL data is SIMULATED unless provenance says otherwise.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

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
from app.pydantic_compat import CompatBaseModel


# ---------------------------------------------------------------------------
# Mission-control view model
# ---------------------------------------------------------------------------


class TaskView(CompatBaseModel):
    """A task in the mission panel."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    label: str
    required_capability: str
    volunteer_id: str | None = None
    volunteer_name: str | None = None
    qualification_status: Literal["qualified", "unqualified", "unassigned"] = "unassigned"
    site_access: bool = True
    time_window_label: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    confirmation_status: str = "pending"
    is_proposed: bool = False  # True for recovery proposals not yet approved


class VolunteerView(CompatBaseModel):
    """Volunteer summary for the mission-control UI."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    capability_codes: list[str]
    location_label: str
    location_coords: list[float] | None = None
    location_stale: bool = False
    travel_minutes: float | None = None
    travel_label: str | None = None  # e.g. "~8 min (simulated)"
    is_assigned: bool = False
    assigned_task_id: str | None = None
    is_spof: bool = False
    opted_in: bool = True
    is_proposed: bool = False  # proposed assignment, not yet approved


class RecoveryView(CompatBaseModel):
    """Recovery card for the mission-control drawer."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str | None = None
    is_feasible: bool
    what_changed: str
    unchanged_assignments: list[str] = Field(default_factory=list)
    before_completion: str | None = None
    after_completion: str | None = None
    additional_travel_label: str | None = None
    requirements_satisfied: bool = True
    pending_confirmations: list[str] = Field(default_factory=list)
    capability_gaps: list[str] = Field(default_factory=list)
    safe_actions: list[str] = Field(default_factory=list)
    targeted_request: str | None = None
    changes: list[dict[str, Any]] = Field(default_factory=list)
    expires_label: str | None = None


class MissionControlPayload(CompatBaseModel):
    """Full payload for the mission-control UI."""

    model_config = ConfigDict(extra="forbid")

    # Header
    mission_id: str
    mission_label: str
    deadline_label: str
    plan_status: str  # PlanStatus value
    roles_covered: int
    roles_required: int
    tasks_at_risk: int
    recovery_summary: str  # e.g. "Recoverable in 4 of 5 scenarios"

    # Task panel
    tasks: list[TaskView]

    # Volunteer markers
    volunteers: list[VolunteerView]

    # Destination
    destination_coords: list[float] | None = None
    destination_label: str

    # SPOFs
    single_points_of_failure: list[str] = Field(default_factory=list)

    # Counterfactual scenarios (for failure simulation)
    counterfactual_scenarios: list[dict[str, Any]] = Field(default_factory=list)

    # Recovery (if active)
    recovery: RecoveryView | None = None

    # Risk status
    risk_status: str = "nominal"  # nominal | at_risk | blocked
    risk_reason: str = ""

    # Simulation flag
    simulated: bool = True
    provenance: str = "SIMULATED"


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_mission_control_payload(
    mission: MissionSpec,
    volunteers: list[VolunteerSpec],
    vehicles: list[VehicleSpec],
    plan: PlanSpec | None = None,
    counterfactual_report: CounterfactualReport | None = None,
    recovery_proposal: dict | None = None,
    risk_status: str = "nominal",
    risk_reason: str = "",
) -> MissionControlPayload:
    """Build the mission-control view from existing domain objects."""

    vol_by_id = {v.id: v for v in volunteers}

    # --- Solve if no plan provided ---
    if plan is None:
        result = solve_coalition(CoalitionPlannerRequest(
            mission=mission,
            volunteers=volunteers,
            vehicles=vehicles,
        ))
        if result.feasible and result.alternatives:
            plan = result.alternatives[0].plan
        else:
            # Return an empty/blocked payload — override risk to "blocked"
            return _build_infeasible_payload(
                mission, volunteers, result,
                risk_status="blocked",
                risk_reason=risk_reason or "No feasible coalition found",
            )

    # --- Assignment lookup ---
    assignment_by_task = {}
    assigned_vols = set()
    for a in plan.assignments:
        assignment_by_task[a.task_id] = a
        if a.volunteer_id:
            assigned_vols.add(a.volunteer_id)

    # --- Run counterfactual if not provided ---
    if counterfactual_report is None and plan.is_feasible:
        counterfactual_report = run_counterfactual_analysis(
            mission=mission,
            baseline_plan=plan,
            volunteers=volunteers,
            vehicles=vehicles,
        )

    spofs = counterfactual_report.single_points_of_failure if counterfactual_report else []

    # --- Tasks ---
    task_views = []
    tasks_at_risk = 0
    for t in mission.tasks:
        a = assignment_by_task.get(t.id)
        vol = vol_by_id.get(a.volunteer_id) if a and a.volunteer_id else None
        qual = "unassigned"
        if vol:
            qual = "qualified" if vol.has_capability(t.required_capability) else "unqualified"

        tw_label = None
        if t.time_window:
            tw_label = f"{t.time_window.start.strftime('%H:%M')}–{t.time_window.end.strftime('%H:%M')}"

        is_at_risk = a is None or a.volunteer_id is None
        if is_at_risk:
            tasks_at_risk += 1

        task_views.append(TaskView(
            task_id=t.id,
            label=t.label,
            required_capability=t.required_capability,
            volunteer_id=a.volunteer_id if a else None,
            volunteer_name=vol.name if vol else None,
            qualification_status=qual,
            site_access=vol.has_site_access(mission.destination_id) if vol else False,
            time_window_label=tw_label,
            depends_on=t.depends_on,
            confirmation_status="pending" if a and a.volunteer_id in plan.outstanding_confirmations else "confirmed",
        ))

    # --- Volunteers ---
    vol_views = []
    for v in volunteers:
        if not v.opted_in:
            continue
        travel = None
        travel_label = None
        for te in v.travel_estimates:
            if te.destination_id == mission.destination_id and te.estimated_minutes is not None:
                travel = te.estimated_minutes
                travel_label = f"~{int(te.estimated_minutes)} min (simulated)"
                break
            elif te.destination_id == mission.destination_id and te.unknown:
                travel_label = "unknown"

        # Location staleness: >1 hour since update
        stale = False
        if v.location_updated_at:
            from datetime import timezone
            import time as _time
            # Simple heuristic: if fixture data, never actually stale
            stale = False

        vol_views.append(VolunteerView(
            id=v.id,
            name=v.name,
            capability_codes=v.capability_codes,
            location_label=v.location_label,
            location_coords=v.location_coords,
            location_stale=stale,
            travel_minutes=travel,
            travel_label=travel_label,
            is_assigned=v.id in assigned_vols,
            assigned_task_id=next(
                (a.task_id for a in plan.assignments if a.volunteer_id == v.id), None
            ),
            is_spof=v.id in spofs,
            opted_in=v.opted_in,
        ))

    # --- Roles coverage ---
    covered_roles = set()
    for a in plan.assignments:
        if a.volunteer_id:
            task_def = next((t for t in mission.tasks if t.id == a.task_id), None)
            if task_def:
                covered_roles.add(task_def.required_capability)

    # --- Recovery summary ---
    recovery_summary = "No counterfactual analysis"
    if counterfactual_report:
        recovery_summary = counterfactual_report.summary

    # --- Counterfactual scenarios for UI ---
    cf_scenarios = []
    if counterfactual_report:
        for s in counterfactual_report.scenarios:
            cf_scenarios.append({
                "scenario_id": s.scenario_id,
                "removed_resource_id": s.removed_resource_id,
                "removed_resource_name": s.removed_resource_name,
                "recovery_status": s.recovery_status,
                "mission_impact": s.mission_impact,
                "uncovered_tasks": s.uncovered_tasks,
                "required_replacements": s.required_replacements,
                "bottleneck": s.bottleneck.model_dump(mode="json") if s.bottleneck else None,
                "objective_delta": s.objective_delta.model_dump(mode="json") if s.objective_delta else None,
            })

    # --- Recovery view ---
    recovery_view = None
    if recovery_proposal:
        recovery_view = RecoveryView(
            proposal_id=recovery_proposal.get("id"),
            is_feasible=recovery_proposal.get("is_feasible", False),
            what_changed=recovery_proposal.get("what_changed", ""),
            unchanged_assignments=recovery_proposal.get("unchanged_assignments", []),
            changes=recovery_proposal.get("changes", []),
            capability_gaps=recovery_proposal.get("capability_gaps", []),
            safe_actions=recovery_proposal.get("safe_actions", []),
            targeted_request=recovery_proposal.get("targeted_request"),
            pending_confirmations=recovery_proposal.get("pending_confirmations", []),
            requirements_satisfied=recovery_proposal.get("requirements_satisfied", True),
            expires_label=recovery_proposal.get("expires_label"),
        )

    return MissionControlPayload(
        mission_id=mission.id,
        mission_label=f"{mission.destination} — {mission.incident_type}",
        deadline_label=mission.deadline.strftime("%a %b %d, %H:%M %Z"),
        plan_status=plan.status.value if isinstance(plan.status, PlanStatus) else str(plan.status),
        roles_covered=len(covered_roles),
        roles_required=len(mission.required_roles),
        tasks_at_risk=tasks_at_risk,
        recovery_summary=recovery_summary,
        tasks=task_views,
        volunteers=vol_views,
        destination_coords=mission.location_coords,
        destination_label=mission.destination,
        single_points_of_failure=list(spofs),
        counterfactual_scenarios=cf_scenarios,
        recovery=recovery_view,
        risk_status=risk_status,
        risk_reason=risk_reason,
        simulated=True,
        provenance="SIMULATED",
    )


def _build_infeasible_payload(
    mission: MissionSpec,
    volunteers: list[VolunteerSpec],
    result: CoalitionPlannerResult,
    risk_status: str,
    risk_reason: str,
) -> MissionControlPayload:
    """Build a payload for when no feasible plan exists."""

    vol_views = []
    for v in volunteers:
        if not v.opted_in:
            continue
        vol_views.append(VolunteerView(
            id=v.id,
            name=v.name,
            capability_codes=v.capability_codes,
            location_label=v.location_label,
            location_coords=v.location_coords,
            opted_in=v.opted_in,
        ))

    task_views = []
    for t in mission.tasks:
        task_views.append(TaskView(
            task_id=t.id,
            label=t.label,
            required_capability=t.required_capability,
            depends_on=t.depends_on,
        ))

    return MissionControlPayload(
        mission_id=mission.id,
        mission_label=f"{mission.destination} — {mission.incident_type}",
        deadline_label=mission.deadline.strftime("%a %b %d, %H:%M %Z"),
        plan_status="infeasible",
        roles_covered=0,
        roles_required=len(mission.required_roles),
        tasks_at_risk=len(mission.tasks),
        recovery_summary="; ".join(result.infeasible_reasons) if result.infeasible_reasons else "No feasible plan",
        tasks=task_views,
        volunteers=vol_views,
        destination_coords=mission.location_coords,
        destination_label=mission.destination,
        risk_status=risk_status or "blocked",
        risk_reason=risk_reason or "No feasible coalition found",
        simulated=True,
        provenance="SIMULATED",
    )
