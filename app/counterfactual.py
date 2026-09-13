"""Phase 3 — Counterfactual failure analysis.

For each critical resource, simulate its removal and test whether the mission
can still be completed. This module:

1. Clones the versioned planning snapshot (never mutates live state).
2. Removes one resource at a time.
3. Runs bounded recovery planning via the CP-SAT coalition planner.
4. Records feasibility, uncovered tasks, objective deltas, and bottleneck
   explanations.

Key distinctions:
- Robustness: the existing plan still works without the resource.
- Recoverability: a new feasible plan exists using available resources.
- Confirmed recovery: replacement participants have accepted (never claimed
  by this module — acceptance requires human confirmation).

ALL data is SIMULATED unless provenance says otherwise.
"""

from __future__ import annotations

import copy
import time
from typing import Literal

from pydantic import ConfigDict, Field

from app.coalition_planner import (
    CoalitionPlannerRequest,
    CoalitionPlannerResult,
    solve_coalition,
)
from app.contracts import (
    ConstraintViolation,
    DataProvenance,
    MissionSpec,
    PlanSpec,
    VehicleSpec,
    VolunteerSpec,
    _new_id,
    _utc_now,
)
from app.pydantic_compat import CompatBaseModel


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


class BottleneckExplanation(CompatBaseModel):
    """Structured explanation of why a resource is a bottleneck."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_type: Literal["volunteer", "vehicle"]
    resource_name: str
    capability_at_risk: list[str] = Field(
        default_factory=list,
        description="Capabilities that become uncoverable when this resource is removed.",
    )
    uncovered_task_ids: list[str] = Field(
        default_factory=list,
        description="Task IDs that cannot be assigned after removal.",
    )
    is_single_point_of_failure: bool = False
    explanation: str = Field(
        description="Human-readable explanation of the impact.",
    )


class ObjectiveDelta(CompatBaseModel):
    """Change in objective metrics between baseline and recovery plan."""

    model_config = ConfigDict(extra="forbid")

    baseline_objective: float | None = None
    recovery_objective: float | None = None
    additional_travel_minutes: float | None = Field(
        default=None,
        description="Extra travel time in the recovery plan vs baseline (simulated).",
    )
    completion_delay_minutes: float | None = Field(
        default=None,
        description="Delay in latest task completion (simulated).",
    )
    changed_assignment_count: int = 0


class CounterfactualScenario(CompatBaseModel):
    """Result of removing one resource and attempting recovery."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(default_factory=_new_id)
    removed_resource_id: str
    removed_resource_type: Literal["volunteer", "vehicle"]
    removed_resource_name: str

    # Impact classification
    recovery_status: Literal[
        "robust",           # Plan still works without reassignment
        "recoverable",      # New feasible plan found
        "infeasible",       # No recovery possible
        "unknown",          # Solver hit time limit or internal error
    ]
    mission_impact: str = Field(
        description="One-sentence summary of impact on the mission.",
    )

    # Recovery details
    recovery_plan: PlanSpec | None = None
    required_replacements: list[str] = Field(
        default_factory=list,
        description="Volunteer IDs that would need to confirm replacement assignments.",
    )
    uncovered_tasks: list[str] = Field(
        default_factory=list,
        description="Task IDs that cannot be covered after removal.",
    )
    infeasible_reasons: list[str] = Field(default_factory=list)

    # Metrics
    objective_delta: ObjectiveDelta | None = None
    bottleneck: BottleneckExplanation | None = None

    # Provenance
    snapshot_version: int
    evaluation_timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"] = "UNKNOWN"


class CounterfactualReport(CompatBaseModel):
    """Full counterfactual analysis across all tested resource removals."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(default_factory=_new_id)
    mission_id: str
    baseline_plan_id: str
    snapshot_version: int

    scenarios: list[CounterfactualScenario] = Field(default_factory=list)

    # Aggregate metrics
    total_scenarios: int = 0
    robust_count: int = 0
    recoverable_count: int = 0
    infeasible_count: int = 0
    unknown_count: int = 0

    single_points_of_failure: list[str] = Field(
        default_factory=list,
        description="Resource IDs whose removal makes the mission infeasible.",
    )

    # Interpretable summary
    summary: str = ""
    evaluation_duration_seconds: float = 0.0
    evaluation_timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    provenance: DataProvenance = DataProvenance.SIMULATED


# ---------------------------------------------------------------------------
# Analysis engine
# ---------------------------------------------------------------------------


def run_counterfactual_analysis(
    mission: MissionSpec,
    baseline_plan: PlanSpec,
    volunteers: list[VolunteerSpec],
    vehicles: list[VehicleSpec],
    resource_ids_to_test: list[str] | None = None,
    time_limit_seconds: float = 5.0,
) -> CounterfactualReport:
    """Run counterfactual analysis for each specified resource.

    If resource_ids_to_test is None, tests all volunteers assigned in the
    baseline plan. Does NOT mutate any input objects.

    Args:
        mission: The mission specification.
        baseline_plan: The current feasible plan to test against.
        volunteers: All available volunteers (including those not in the plan).
        vehicles: All available vehicles.
        resource_ids_to_test: Specific resource IDs to test. If None, tests
            all assigned volunteers in the baseline plan.
        time_limit_seconds: Per-scenario solver time limit.

    Returns:
        CounterfactualReport with per-scenario results and aggregate metrics.
    """
    start_time = time.monotonic()

    # Determine which resources to test
    if resource_ids_to_test is None:
        resource_ids_to_test = list(
            {a.volunteer_id for a in baseline_plan.assignments}
        )

    vol_by_id = {v.id: v for v in volunteers}
    veh_by_id = {v.id: v for v in vehicles}

    scenarios: list[CounterfactualScenario] = []

    for resource_id in resource_ids_to_test:
        # Determine resource type and name
        if resource_id in vol_by_id:
            resource_type: Literal["volunteer", "vehicle"] = "volunteer"
            resource_name = vol_by_id[resource_id].name
        elif resource_id in veh_by_id:
            resource_type = "vehicle"
            resource_name = veh_by_id[resource_id].name
        else:
            # Unknown resource — skip
            continue

        scenario = _evaluate_single_removal(
            mission=mission,
            baseline_plan=baseline_plan,
            volunteers=volunteers,
            vehicles=vehicles,
            removed_id=resource_id,
            removed_type=resource_type,
            removed_name=resource_name,
            time_limit_seconds=time_limit_seconds,
        )
        scenarios.append(scenario)

    elapsed = time.monotonic() - start_time

    # Aggregate
    robust = sum(1 for s in scenarios if s.recovery_status == "robust")
    recoverable = sum(1 for s in scenarios if s.recovery_status == "recoverable")
    infeasible = sum(1 for s in scenarios if s.recovery_status == "infeasible")
    unknown = sum(1 for s in scenarios if s.recovery_status == "unknown")
    spof = [s.removed_resource_id for s in scenarios if s.recovery_status == "infeasible"]

    # Build interpretable summary
    total = len(scenarios)
    summary_parts = []
    if recoverable + robust > 0:
        summary_parts.append(
            f"Recoverable in {recoverable + robust} of {total} "
            f"tested single-resource-loss scenarios"
        )
    if infeasible > 0:
        summary_parts.append(f"{infeasible} scenario{'s' if infeasible > 1 else ''} infeasible")
    if unknown > 0:
        summary_parts.append(f"{unknown} scenario{'s' if unknown > 1 else ''} unknown")
    if not summary_parts:
        summary_parts.append("No scenarios tested")

    summary = ". ".join(summary_parts) + "."

    return CounterfactualReport(
        mission_id=mission.id,
        baseline_plan_id=baseline_plan.id,
        snapshot_version=mission.version,
        scenarios=scenarios,
        total_scenarios=total,
        robust_count=robust,
        recoverable_count=recoverable,
        infeasible_count=infeasible,
        unknown_count=unknown,
        single_points_of_failure=spof,
        summary=summary,
        evaluation_duration_seconds=round(elapsed, 4),
        provenance=DataProvenance.SIMULATED,
    )


def _evaluate_single_removal(
    mission: MissionSpec,
    baseline_plan: PlanSpec,
    volunteers: list[VolunteerSpec],
    vehicles: list[VehicleSpec],
    removed_id: str,
    removed_type: Literal["volunteer", "vehicle"],
    removed_name: str,
    time_limit_seconds: float,
) -> CounterfactualScenario:
    """Evaluate the impact of removing a single resource.

    Deep-copies volunteer and vehicle lists to avoid mutating inputs.
    """
    # 1. Check robustness: is the removed resource even in the baseline plan?
    assigned_ids = {a.volunteer_id for a in baseline_plan.assignments}
    assigned_vehicle_ids = {a.vehicle_id for a in baseline_plan.assignments if a.vehicle_id}

    in_plan = (
        (removed_type == "volunteer" and removed_id in assigned_ids) or
        (removed_type == "vehicle" and removed_id in assigned_vehicle_ids)
    )

    if not in_plan:
        # Resource is not in the baseline plan — plan is robust to its loss
        return CounterfactualScenario(
            removed_resource_id=removed_id,
            removed_resource_type=removed_type,
            removed_resource_name=removed_name,
            recovery_status="robust",
            mission_impact=f"Removing {removed_name} has no impact — not assigned in the baseline plan.",
            snapshot_version=mission.version,
            solver_status="OPTIMAL",
        )

    # 2. Clone inputs and remove the resource
    remaining_volunteers = [
        _deep_copy_volunteer(v) for v in volunteers
        if not (removed_type == "volunteer" and v.id == removed_id)
    ]
    remaining_vehicles = [
        _deep_copy_vehicle(v) for v in vehicles
        if not (removed_type == "vehicle" and v.id == removed_id)
    ]

    # 3. Re-solve without the resource
    request = CoalitionPlannerRequest(
        mission=_deep_copy_mission(mission),
        volunteers=remaining_volunteers,
        vehicles=remaining_vehicles,
        max_alternatives=1,
        time_limit_seconds=time_limit_seconds,
    )

    result: CoalitionPlannerResult = solve_coalition(request)

    # 4. Classify result
    if result.solver_status == "UNKNOWN":
        return _build_unknown_scenario(
            removed_id, removed_type, removed_name, mission, result
        )

    if not result.feasible:
        return _build_infeasible_scenario(
            removed_id, removed_type, removed_name, mission,
            baseline_plan, volunteers, result,
        )

    # Feasible recovery found
    recovery_plan = result.alternatives[0].plan if result.alternatives else None
    return _build_recoverable_scenario(
        removed_id, removed_type, removed_name, mission,
        baseline_plan, recovery_plan, result,
    )


def _build_unknown_scenario(
    removed_id: str,
    removed_type: Literal["volunteer", "vehicle"],
    removed_name: str,
    mission: MissionSpec,
    result: CoalitionPlannerResult,
) -> CounterfactualScenario:
    return CounterfactualScenario(
        removed_resource_id=removed_id,
        removed_resource_type=removed_type,
        removed_resource_name=removed_name,
        recovery_status="unknown",
        mission_impact=(
            f"Solver could not determine recoverability after removing {removed_name} "
            f"within the time limit."
        ),
        snapshot_version=mission.version,
        solver_status="UNKNOWN",
    )


def _build_infeasible_scenario(
    removed_id: str,
    removed_type: Literal["volunteer", "vehicle"],
    removed_name: str,
    mission: MissionSpec,
    baseline_plan: PlanSpec,
    volunteers: list[VolunteerSpec],
    result: CoalitionPlannerResult,
) -> CounterfactualScenario:
    """Build scenario for infeasible recovery."""
    # Identify which tasks are uncovered
    uncovered = _identify_uncovered_tasks(
        removed_id, removed_type, mission, volunteers
    )
    # Build bottleneck explanation
    bottleneck = _build_bottleneck(
        removed_id, removed_type, removed_name, mission, volunteers, uncovered
    )

    return CounterfactualScenario(
        removed_resource_id=removed_id,
        removed_resource_type=removed_type,
        removed_resource_name=removed_name,
        recovery_status="infeasible",
        mission_impact=(
            f"Removing {removed_name} makes the mission infeasible. "
            f"{bottleneck.explanation}"
        ),
        uncovered_tasks=uncovered,
        infeasible_reasons=result.infeasible_reasons,
        bottleneck=bottleneck,
        snapshot_version=mission.version,
        solver_status="INFEASIBLE",
    )


def _build_recoverable_scenario(
    removed_id: str,
    removed_type: Literal["volunteer", "vehicle"],
    removed_name: str,
    mission: MissionSpec,
    baseline_plan: PlanSpec,
    recovery_plan: PlanSpec | None,
    result: CoalitionPlannerResult,
) -> CounterfactualScenario:
    """Build scenario for recoverable case."""
    delta = _compute_objective_delta(baseline_plan, recovery_plan)
    required_replacements = _find_replacements(baseline_plan, recovery_plan)

    return CounterfactualScenario(
        removed_resource_id=removed_id,
        removed_resource_type=removed_type,
        removed_resource_name=removed_name,
        recovery_status="recoverable",
        mission_impact=(
            f"Removing {removed_name} requires reassignment. "
            f"A recovery plan exists with {delta.changed_assignment_count} "
            f"changed assignment(s)."
        ),
        recovery_plan=recovery_plan,
        required_replacements=required_replacements,
        objective_delta=delta,
        snapshot_version=mission.version,
        solver_status=result.solver_status,
    )


# ---------------------------------------------------------------------------
# Helpers — deep copy (avoids mutating inputs)
# ---------------------------------------------------------------------------


def _deep_copy_volunteer(v: VolunteerSpec) -> VolunteerSpec:
    """Create an independent copy of a volunteer spec."""
    return VolunteerSpec.model_validate(v.model_dump(mode="json"))


def _deep_copy_vehicle(v: VehicleSpec) -> VehicleSpec:
    """Create an independent copy of a vehicle spec."""
    return VehicleSpec.model_validate(v.model_dump(mode="json"))


def _deep_copy_mission(m: MissionSpec) -> MissionSpec:
    """Create an independent copy of a mission spec."""
    return MissionSpec.model_validate(m.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Bottleneck identification
# ---------------------------------------------------------------------------


def _identify_uncovered_tasks(
    removed_id: str,
    removed_type: Literal["volunteer", "vehicle"],
    mission: MissionSpec,
    all_volunteers: list[VolunteerSpec],
) -> list[str]:
    """Identify tasks that become uncoverable after removing a resource."""
    uncovered: list[str] = []

    if removed_type != "volunteer":
        return uncovered

    # For each task, check if any OTHER opted-in volunteer can cover it
    remaining = [v for v in all_volunteers if v.id != removed_id and v.opted_in]

    for task in mission.tasks:
        capable_with_access = [
            v for v in remaining
            if v.has_capability(task.required_capability)
            and v.has_site_access(mission.destination_id)
        ]
        if task.time_window:
            capable_with_access = [
                v for v in capable_with_access
                if v.is_available_during(task.time_window)
            ]
        if not capable_with_access:
            uncovered.append(task.id)

    return uncovered


def _build_bottleneck(
    removed_id: str,
    removed_type: Literal["volunteer", "vehicle"],
    removed_name: str,
    mission: MissionSpec,
    all_volunteers: list[VolunteerSpec],
    uncovered_tasks: list[str],
) -> BottleneckExplanation:
    """Build a structured bottleneck explanation."""
    task_by_id = {t.id: t for t in mission.tasks}
    caps_at_risk = list({
        task_by_id[tid].required_capability
        for tid in uncovered_tasks
        if tid in task_by_id
    })

    if uncovered_tasks:
        task_labels = [
            f"'{task_by_id[tid].label}' ({task_by_id[tid].required_capability})"
            for tid in uncovered_tasks
            if tid in task_by_id
        ]
        explanation = (
            f"{removed_name} is the sole qualified and available resource for "
            f"{', '.join(task_labels)}. "
            f"No other opted-in volunteer can cover "
            f"{'this task' if len(task_labels) == 1 else 'these tasks'} "
            f"at site '{mission.destination_id}'."
        )
    else:
        explanation = (
            f"Removing {removed_name} creates an infeasible assignment problem "
            f"even though individual task coverage exists — the joint constraint "
            f"set (availability, site access, no double-booking) cannot be satisfied."
        )

    return BottleneckExplanation(
        resource_id=removed_id,
        resource_type=removed_type,
        resource_name=removed_name,
        capability_at_risk=caps_at_risk,
        uncovered_task_ids=uncovered_tasks,
        is_single_point_of_failure=True,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Objective delta computation
# ---------------------------------------------------------------------------


def _compute_objective_delta(
    baseline: PlanSpec,
    recovery: PlanSpec | None,
) -> ObjectiveDelta:
    """Compute the difference in objectives between baseline and recovery."""
    if recovery is None:
        return ObjectiveDelta()

    baseline_assignments = {a.task_id: a.volunteer_id for a in baseline.assignments}
    recovery_assignments = {a.task_id: a.volunteer_id for a in recovery.assignments}

    changed = sum(
        1 for tid in baseline_assignments
        if tid in recovery_assignments and baseline_assignments[tid] != recovery_assignments[tid]
    )
    # Also count tasks in recovery but not in baseline (shouldn't happen, but safe)
    for tid in recovery_assignments:
        if tid not in baseline_assignments:
            changed += 1

    # Objective delta (scaled values from solver — travel*100)
    baseline_obj = baseline.objective_value
    recovery_obj = recovery.objective_value

    additional_travel = None
    if baseline_obj is not None and recovery_obj is not None:
        # Objectives are travel_minutes * 100 + index tiebreaker
        # Approximate additional travel in minutes
        additional_travel = round((recovery_obj - baseline_obj) / 100.0, 1)

    return ObjectiveDelta(
        baseline_objective=baseline_obj,
        recovery_objective=recovery_obj,
        additional_travel_minutes=additional_travel,
        changed_assignment_count=changed,
    )


def _find_replacements(
    baseline: PlanSpec,
    recovery: PlanSpec | None,
) -> list[str]:
    """Find volunteer IDs that appear in recovery but not in baseline assignments."""
    if recovery is None:
        return []

    baseline_vols = {a.volunteer_id for a in baseline.assignments}
    recovery_vols = {a.volunteer_id for a in recovery.assignments}

    return sorted(recovery_vols - baseline_vols)


# ---------------------------------------------------------------------------
# Snapshot staleness check
# ---------------------------------------------------------------------------


def is_report_stale(
    report: CounterfactualReport,
    current_mission_version: int,
) -> bool:
    """A report is stale when the mission snapshot has changed since evaluation."""
    return report.snapshot_version != current_mission_version
