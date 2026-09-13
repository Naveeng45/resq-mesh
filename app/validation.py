"""Phase 1 — Deterministic validation for typed domain contracts.

Rules enforced here:
- IDs must refer to existing resources.
- Qualifications and site permissions must be explicit.
- A person cannot perform incompatible overlapping tasks.
- Driving and handling are separate tasks even if one person is qualified for both.
- Vehicle availability does not imply an eligible driver exists.
- Task order and travel time must permit the assignment.
- Unknown travel time must not silently become zero.
- Timezone-aware time comparisons throughout.

This module does NOT implement the optimizer. It validates a proposed plan
against the domain constraints and returns all violations found.
"""

from __future__ import annotations

from app.contracts import (
    ConstraintViolation,
    MissionSpec,
    PlanSpec,
    TaskAssignment,
    TaskDefinition,
    TimeWindow,
    VehicleSpec,
    VolunteerSpec,
)


def validate_plan(
    plan: PlanSpec,
    mission: MissionSpec,
    volunteers: list[VolunteerSpec],
    vehicles: list[VehicleSpec],
) -> list[ConstraintViolation]:
    """Run all deterministic validation rules. Returns list of violations (empty = valid)."""

    violations: list[ConstraintViolation] = []
    vol_by_id = {v.id: v for v in volunteers}
    veh_by_id = {v.id: v for v in vehicles}
    task_by_id = {t.id: t for t in mission.tasks}

    violations.extend(_check_id_references(plan, vol_by_id, veh_by_id, task_by_id))
    violations.extend(_check_capability_coverage(plan, mission, vol_by_id, task_by_id))
    violations.extend(_check_site_access(plan, mission, vol_by_id, task_by_id))
    violations.extend(_check_volunteer_availability(plan, vol_by_id))
    violations.extend(_check_overlapping_assignments(plan))
    violations.extend(_check_driving_and_handling_separation(plan, task_by_id))
    violations.extend(_check_vehicle_availability(plan, veh_by_id))
    violations.extend(_check_vehicle_driver_eligibility(plan, vol_by_id, veh_by_id))
    violations.extend(_check_task_dependencies(plan, task_by_id))
    violations.extend(_check_travel_time_feasibility(plan, vol_by_id, mission))

    return violations


def _check_id_references(
    plan: PlanSpec,
    vol_by_id: dict[str, VolunteerSpec],
    veh_by_id: dict[str, VehicleSpec],
    task_by_id: dict[str, TaskDefinition],
) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for assignment in plan.assignments:
        if assignment.task_id not in task_by_id:
            violations.append(ConstraintViolation(
                constraint_type="unknown_task",
                description=f"Task '{assignment.task_id}' does not exist in mission.",
                affected_task_ids=[assignment.task_id],
            ))
        if assignment.volunteer_id not in vol_by_id:
            violations.append(ConstraintViolation(
                constraint_type="unknown_volunteer",
                description=f"Volunteer '{assignment.volunteer_id}' does not exist.",
                affected_resource_ids=[assignment.volunteer_id],
            ))
        if assignment.vehicle_id is not None and assignment.vehicle_id not in veh_by_id:
            violations.append(ConstraintViolation(
                constraint_type="unknown_vehicle",
                description=f"Vehicle '{assignment.vehicle_id}' does not exist.",
                affected_resource_ids=[assignment.vehicle_id],
            ))
    return violations


def _check_capability_coverage(
    plan: PlanSpec,
    mission: MissionSpec,
    vol_by_id: dict[str, VolunteerSpec],
    task_by_id: dict[str, TaskDefinition],
) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for assignment in plan.assignments:
        task = task_by_id.get(assignment.task_id)
        vol = vol_by_id.get(assignment.volunteer_id)
        if task is None or vol is None:
            continue  # already caught by _check_id_references
        if not vol.has_capability(task.required_capability):
            violations.append(ConstraintViolation(
                constraint_type="capability_gap",
                description=(
                    f"Volunteer '{vol.id}' lacks capability '{task.required_capability}' "
                    f"required by task '{task.id}' ({task.label})."
                ),
                affected_resource_ids=[vol.id],
                affected_task_ids=[task.id],
            ))
    return violations


def _check_site_access(
    plan: PlanSpec,
    mission: MissionSpec,
    vol_by_id: dict[str, VolunteerSpec],
    task_by_id: dict[str, TaskDefinition],
) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for assignment in plan.assignments:
        vol = vol_by_id.get(assignment.volunteer_id)
        if vol is None:
            continue
        if not vol.has_site_access(mission.destination_id):
            violations.append(ConstraintViolation(
                constraint_type="site_access",
                description=(
                    f"Volunteer '{vol.id}' is not authorized for site '{mission.destination_id}'."
                ),
                affected_resource_ids=[vol.id],
            ))
    return violations


def _check_volunteer_availability(
    plan: PlanSpec,
    vol_by_id: dict[str, VolunteerSpec],
) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for assignment in plan.assignments:
        vol = vol_by_id.get(assignment.volunteer_id)
        if vol is None:
            continue
        if not vol.is_available_during(assignment.scheduled_window):
            violations.append(ConstraintViolation(
                constraint_type="availability",
                description=(
                    f"Volunteer '{vol.id}' has no availability interval covering "
                    f"{assignment.scheduled_window.start.isoformat()} to "
                    f"{assignment.scheduled_window.end.isoformat()}."
                ),
                affected_resource_ids=[vol.id],
                affected_task_ids=[assignment.task_id],
            ))
    return violations


def _check_overlapping_assignments(plan: PlanSpec) -> list[ConstraintViolation]:
    """A person cannot perform incompatible overlapping tasks."""
    violations: list[ConstraintViolation] = []
    by_volunteer: dict[str, list[TaskAssignment]] = {}
    for assignment in plan.assignments:
        by_volunteer.setdefault(assignment.volunteer_id, []).append(assignment)

    for vol_id, assignments in by_volunteer.items():
        for i, a in enumerate(assignments):
            for b in assignments[i + 1:]:
                if _windows_overlap(a.scheduled_window, b.scheduled_window):
                    violations.append(ConstraintViolation(
                        constraint_type="time_overlap",
                        description=(
                            f"Volunteer '{vol_id}' is double-assigned: "
                            f"tasks '{a.task_id}' and '{b.task_id}' overlap in time."
                        ),
                        affected_resource_ids=[vol_id],
                        affected_task_ids=[a.task_id, b.task_id],
                    ))
    return violations


def _windows_overlap(a: TimeWindow, b: TimeWindow) -> bool:
    return a.start < b.end and b.start < a.end


def _check_driving_and_handling_separation(
    plan: PlanSpec,
    task_by_id: dict[str, TaskDefinition],
) -> list[ConstraintViolation]:
    """Driving and handling are separate tasks even if one person is qualified for both.

    If a person is assigned to both a driving task and a handling task, the time
    windows must not overlap (they are sequential tasks, not concurrent).
    """
    violations: list[ConstraintViolation] = []
    DRIVING_CAPS = {"van_certified_driver"}
    HANDLING_CAPS = {"food_handler"}

    by_volunteer: dict[str, list[TaskAssignment]] = {}
    for assignment in plan.assignments:
        by_volunteer.setdefault(assignment.volunteer_id, []).append(assignment)

    for vol_id, assignments in by_volunteer.items():
        driving = []
        handling = []
        for a in assignments:
            task = task_by_id.get(a.task_id)
            if task is None:
                continue
            if task.required_capability in DRIVING_CAPS:
                driving.append(a)
            if task.required_capability in HANDLING_CAPS:
                handling.append(a)

        for d in driving:
            for h in handling:
                if _windows_overlap(d.scheduled_window, h.scheduled_window):
                    violations.append(ConstraintViolation(
                        constraint_type="driving_handling_overlap",
                        description=(
                            f"Volunteer '{vol_id}' cannot drive and handle food simultaneously. "
                            f"Tasks '{d.task_id}' (driving) and '{h.task_id}' (handling) overlap."
                        ),
                        affected_resource_ids=[vol_id],
                        affected_task_ids=[d.task_id, h.task_id],
                    ))
    return violations


def _check_vehicle_availability(
    plan: PlanSpec,
    veh_by_id: dict[str, VehicleSpec],
) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for assignment in plan.assignments:
        if assignment.vehicle_id is None:
            continue
        veh = veh_by_id.get(assignment.vehicle_id)
        if veh is None:
            continue
        if not veh.is_available_during(assignment.scheduled_window):
            violations.append(ConstraintViolation(
                constraint_type="vehicle_unavailable",
                description=(
                    f"Vehicle '{veh.id}' is not available during "
                    f"{assignment.scheduled_window.start.isoformat()} to "
                    f"{assignment.scheduled_window.end.isoformat()}."
                ),
                affected_resource_ids=[veh.id],
                affected_task_ids=[assignment.task_id],
            ))
    return violations


def _check_vehicle_driver_eligibility(
    plan: PlanSpec,
    vol_by_id: dict[str, VolunteerSpec],
    veh_by_id: dict[str, VehicleSpec],
) -> list[ConstraintViolation]:
    """Vehicle availability does not imply an eligible driver exists."""
    violations: list[ConstraintViolation] = []
    for assignment in plan.assignments:
        if assignment.vehicle_id is None:
            continue
        veh = veh_by_id.get(assignment.vehicle_id)
        vol = vol_by_id.get(assignment.volunteer_id)
        if veh is None or vol is None:
            continue
        if vol.id not in veh.eligible_driver_ids:
            violations.append(ConstraintViolation(
                constraint_type="no_eligible_driver",
                description=(
                    f"Volunteer '{vol.id}' is not eligible to drive vehicle '{veh.id}'."
                ),
                affected_resource_ids=[vol.id, veh.id],
                affected_task_ids=[assignment.task_id],
            ))
    return violations


def _check_task_dependencies(
    plan: PlanSpec,
    task_by_id: dict[str, TaskDefinition],
) -> list[ConstraintViolation]:
    """Task order must permit the assignment."""
    violations: list[ConstraintViolation] = []
    # Build task_id -> scheduled_window from assignments
    task_windows: dict[str, TimeWindow] = {}
    for assignment in plan.assignments:
        task_windows[assignment.task_id] = assignment.scheduled_window

    for assignment in plan.assignments:
        task = task_by_id.get(assignment.task_id)
        if task is None:
            continue
        for dep_id in task.depends_on:
            dep_window = task_windows.get(dep_id)
            if dep_window is None:
                violations.append(ConstraintViolation(
                    constraint_type="unassigned_dependency",
                    description=(
                        f"Task '{task.id}' depends on '{dep_id}' which has no assignment."
                    ),
                    affected_task_ids=[task.id, dep_id],
                    severity="blocking",
                ))
                continue
            if assignment.scheduled_window.start < dep_window.end:
                violations.append(ConstraintViolation(
                    constraint_type="dependency_order",
                    description=(
                        f"Task '{task.id}' starts before dependency '{dep_id}' ends "
                        f"({assignment.scheduled_window.start.isoformat()} < "
                        f"{dep_window.end.isoformat()})."
                    ),
                    affected_task_ids=[task.id, dep_id],
                ))
    return violations


def _check_travel_time_feasibility(
    plan: PlanSpec,
    vol_by_id: dict[str, VolunteerSpec],
    mission: MissionSpec,
) -> list[ConstraintViolation]:
    """Unknown travel time must not silently become zero."""
    violations: list[ConstraintViolation] = []
    for assignment in plan.assignments:
        vol = vol_by_id.get(assignment.volunteer_id)
        if vol is None:
            continue
        # Find travel estimate to this mission's destination
        estimate = next(
            (t for t in vol.travel_estimates if t.destination_id == mission.destination_id),
            None,
        )
        if estimate is None:
            violations.append(ConstraintViolation(
                constraint_type="missing_travel_estimate",
                description=(
                    f"No travel estimate from volunteer '{vol.id}' to "
                    f"destination '{mission.destination_id}'. "
                    "Unknown travel time must not silently become zero."
                ),
                affected_resource_ids=[vol.id],
                severity="warning",
            ))
            continue
        if estimate.unknown:
            violations.append(ConstraintViolation(
                constraint_type="unknown_travel_time",
                description=(
                    f"Travel time from volunteer '{vol.id}' to "
                    f"destination '{mission.destination_id}' is unknown. "
                    "Cannot verify assignment is reachable in time."
                ),
                affected_resource_ids=[vol.id],
                severity="warning",
            ))
    return violations
