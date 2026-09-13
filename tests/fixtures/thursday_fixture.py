"""SIMULATED Thursday distribution fixture for Phase 1 contract tests.

ALL DATA IS SYNTHETIC. No real food-safety policy is represented. Operational
requirements are configured placeholders requiring operator validation before
any production use.

This fixture provides:
- One church site (Eastside)
- One vehicle (Church Van)
- Several volunteers with overlapping capabilities
- Explicit task durations and travel-time estimates
- At least one valid plan
- At least one impossible plan
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.contracts import (
    ApprovalRecord,
    AvailabilityInterval,
    Commitment,
    ConfirmationStatus,
    ConstraintViolation,
    DataProvenance,
    MissionEvent,
    MissionSpec,
    PlanSpec,
    PlanStatus,
    RecoveryProposal,
    ResourceUnavailableEvent,
    TaskAssignment,
    TaskDefinition,
    TimeWindow,
    TravelEstimate,
    VehicleSpec,
    VolunteerSpec,
    EventKind,
)

# ---------------------------------------------------------------------------
# Timezone and base times — ALL SIMULATED
# ---------------------------------------------------------------------------

SIMULATED_TZ = timezone(timedelta(hours=-7), name="US/Pacific")

# Thursday 2026-09-10 at 4:00 PM Pacific
THURSDAY_BASE = datetime(2026, 9, 10, 16, 0, 0, tzinfo=SIMULATED_TZ)
THURSDAY_END = THURSDAY_BASE + timedelta(hours=3)  # 7:00 PM

SERVICE_WINDOW = TimeWindow(start=THURSDAY_BASE, end=THURSDAY_END)

# Availability window: volunteers available 3:00 PM – 8:00 PM
AVAIL_START = THURSDAY_BASE - timedelta(hours=1)  # 3:00 PM
AVAIL_END = THURSDAY_END + timedelta(hours=1)  # 8:00 PM
FULL_AVAIL_WINDOW = TimeWindow(start=AVAIL_START, end=AVAIL_END)

# A tight availability that doesn't cover the full service window
PARTIAL_AVAIL_START = THURSDAY_BASE + timedelta(minutes=30)  # 4:30 PM
PARTIAL_AVAIL = TimeWindow(start=PARTIAL_AVAIL_START, end=AVAIL_END)


# ---------------------------------------------------------------------------
# Mission — SIMULATED
# ---------------------------------------------------------------------------


def build_eastside_mission() -> MissionSpec:
    """Eastside Thursday distribution mission."""
    drive_task = TaskDefinition(
        id="task-drive",
        label="Drive van to Eastside",
        required_capability="van_certified_driver",
        duration_minutes=30,
        time_window=TimeWindow(
            start=THURSDAY_BASE - timedelta(minutes=30),
            end=THURSDAY_BASE,
        ),
    )
    handle_task = TaskDefinition(
        id="task-handle",
        label="Handle food at Eastside",
        required_capability="food_handler",
        duration_minutes=120,
        time_window=TimeWindow(
            start=THURSDAY_BASE,
            end=THURSDAY_BASE + timedelta(hours=2),
        ),
        depends_on=["task-drive"],
    )
    unlock_task = TaskDefinition(
        id="task-unlock",
        label="Open Eastside site",
        required_capability="site_keyholder",
        duration_minutes=15,
        time_window=TimeWindow(
            start=THURSDAY_BASE - timedelta(minutes=15),
            end=THURSDAY_BASE,
        ),
    )
    return MissionSpec(
        id="mission-eastside-thu",
        version=1,
        destination="Riverside Community Meals — Eastside",
        destination_id="eastside",
        location_coords=[38.572, -121.458],
        mission_timezone="US/Pacific",
        service_window=SERVICE_WINDOW,
        deadline=THURSDAY_BASE,
        incident_type="thursday_distribution",
        required_roles=["van_certified_driver", "food_handler", "site_keyholder"],
        tasks=[drive_task, handle_task, unlock_task],
        requested_quantity=180,
        constraints=["Van certification required to drive"],
        permitted_start_adjustment_minutes=15.0,
        provenance=DataProvenance.SIMULATED,
    )


# ---------------------------------------------------------------------------
# Vehicle — SIMULATED
# ---------------------------------------------------------------------------


def build_church_van() -> VehicleSpec:
    return VehicleSpec(
        id="van-church-1",
        name="Church Van (SIMULATED)",
        capacity=200,
        capacity_unit="meals",
        availability_intervals=[
            AvailabilityInterval(
                window=TimeWindow(
                    start=THURSDAY_BASE - timedelta(hours=2),
                    end=THURSDAY_END + timedelta(hours=1),
                ),
            ),
        ],
        eligible_driver_ids=["maya", "gina"],  # Only these two are certified for it
        equipment_capabilities=[],
        org="Riverside Church",
        provenance=DataProvenance.SIMULATED,
    )


# ---------------------------------------------------------------------------
# Volunteers — SIMULATED
# ---------------------------------------------------------------------------


def _travel(vol_id: str, dest_id: str, minutes: float) -> TravelEstimate:
    return TravelEstimate(
        origin_id=vol_id,
        destination_id=dest_id,
        estimated_minutes=minutes,
        distance_km=round(minutes * 0.8, 1),  # rough simulated conversion
        provenance=DataProvenance.SIMULATED,
    )


def _unknown_travel(vol_id: str, dest_id: str) -> TravelEstimate:
    return TravelEstimate(
        origin_id=vol_id,
        destination_id=dest_id,
        unknown=True,
        provenance=DataProvenance.SIMULATED,
    )


def build_volunteers() -> list[VolunteerSpec]:
    """Build the synthetic volunteer roster.

    Maya: driver + keyholder, local to Eastside, certified for Church Van.
    Priya: food handler, local to Eastside.
    Elena: site keyholder, local to Eastside.
    Gina: driver, church bench, certified for Church Van.
    Sam: food handler, church bench.
    Luis: driver, food-bank bench (has BOTH driver + handler capabilities).
    """
    return [
        VolunteerSpec(
            id="maya",
            name="Maya Chen (SIMULATED)",
            capability_codes=["van_certified_driver"],
            availability_intervals=[AvailabilityInterval(window=FULL_AVAIL_WINDOW)],
            authorized_site_ids=["eastside"],
            eligible_vehicle_ids=["van-church-1"],
            opted_in=True,
            org="Riverside Church",
            location_label="Eastside",
            location_coords=[38.574, -121.462],
            location_updated_at=THURSDAY_BASE - timedelta(hours=2),
            travel_estimates=[_travel("maya", "eastside", 8)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="priya",
            name="Priya Shah (SIMULATED)",
            capability_codes=["food_handler"],
            availability_intervals=[AvailabilityInterval(window=FULL_AVAIL_WINDOW)],
            authorized_site_ids=["eastside"],
            opted_in=True,
            org="Riverside Church",
            location_label="Eastside",
            location_coords=[38.568, -121.470],
            location_updated_at=THURSDAY_BASE - timedelta(hours=2),
            travel_estimates=[_travel("priya", "eastside", 5)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="elena",
            name="Elena Brooks (SIMULATED)",
            capability_codes=["site_keyholder"],
            availability_intervals=[AvailabilityInterval(window=FULL_AVAIL_WINDOW)],
            authorized_site_ids=["eastside"],
            opted_in=True,
            org="Riverside Church",
            location_label="Eastside",
            location_coords=[38.577, -121.455],
            location_updated_at=THURSDAY_BASE - timedelta(hours=2),
            travel_estimates=[_travel("elena", "eastside", 3)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="gina",
            name="Gina Petrov (SIMULATED)",
            capability_codes=["van_certified_driver"],
            availability_intervals=[AvailabilityInterval(window=FULL_AVAIL_WINDOW)],
            authorized_site_ids=["eastside", "west-end"],
            eligible_vehicle_ids=["van-church-1"],
            opted_in=True,
            org="Riverside Church",
            location_label="Church bench",
            location_coords=[38.556, -121.492],
            location_updated_at=THURSDAY_BASE - timedelta(hours=2),
            travel_estimates=[_travel("gina", "eastside", 18)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="sam",
            name="Sam Ortiz (SIMULATED)",
            capability_codes=["food_handler"],
            availability_intervals=[AvailabilityInterval(window=FULL_AVAIL_WINDOW)],
            authorized_site_ids=["eastside", "west-end"],
            opted_in=True,
            org="Riverside Church",
            location_label="Church bench",
            location_coords=[38.557, -121.485],
            location_updated_at=THURSDAY_BASE - timedelta(hours=2),
            travel_estimates=[_travel("sam", "eastside", 15)],
            provenance=DataProvenance.SIMULATED,
        ),
        # Luis has BOTH driver + handler — used to test driving/handling separation
        VolunteerSpec(
            id="luis",
            name="Luis Okonkwo (SIMULATED)",
            capability_codes=["van_certified_driver", "food_handler"],
            availability_intervals=[AvailabilityInterval(window=FULL_AVAIL_WINDOW)],
            authorized_site_ids=["*"],  # floating bench
            eligible_vehicle_ids=[],  # NOT certified for Church Van
            opted_in=True,
            org="Second Harvest",
            location_label="Food bank bench",
            location_coords=[38.596, -121.505],
            location_updated_at=THURSDAY_BASE - timedelta(hours=2),
            travel_estimates=[_travel("luis", "eastside", 22)],
            provenance=DataProvenance.SIMULATED,
        ),
        # Jordan: recruit-only, not opted in
        VolunteerSpec(
            id="jordan",
            name="Jordan Hale (SIMULATED)",
            capability_codes=["van_certified_driver"],
            availability_intervals=[AvailabilityInterval(window=FULL_AVAIL_WINDOW)],
            authorized_site_ids=["*"],
            opted_in=False,
            org="Second Harvest",
            location_label="Recruit list",
            location_coords=[38.610, -121.520],
            travel_estimates=[_unknown_travel("jordan", "eastside")],
            provenance=DataProvenance.SIMULATED,
        ),
    ]


# ---------------------------------------------------------------------------
# Valid plan — SIMULATED
# ---------------------------------------------------------------------------


def build_valid_plan(mission: MissionSpec | None = None) -> PlanSpec:
    """A valid plan: Maya drives, Priya handles food, Elena opens site."""
    m = mission or build_eastside_mission()
    tasks = {t.id: t for t in m.tasks}

    return PlanSpec(
        id="plan-valid-001",
        mission_id=m.id,
        version=1,
        input_snapshot_version=m.version,
        assignments=[
            TaskAssignment(
                task_id="task-drive",
                volunteer_id="maya",
                vehicle_id="van-church-1",
                scheduled_window=tasks["task-drive"].time_window,
            ),
            TaskAssignment(
                task_id="task-handle",
                volunteer_id="priya",
                scheduled_window=tasks["task-handle"].time_window,
            ),
            TaskAssignment(
                task_id="task-unlock",
                volunteer_id="elena",
                scheduled_window=tasks["task-unlock"].time_window,
            ),
        ],
        is_feasible=True,
        solver_status="OPTIMAL",
        status=PlanStatus.PROPOSED,
        outstanding_confirmations=["maya", "priya", "elena"],
        provenance=DataProvenance.SIMULATED,
    )


# ---------------------------------------------------------------------------
# Impossible plan — SIMULATED
# ---------------------------------------------------------------------------


def build_impossible_plan_no_driver(mission: MissionSpec | None = None) -> PlanSpec:
    """Impossible: assigns Luis (not eligible for Church Van) as driver with the van."""
    m = mission or build_eastside_mission()
    tasks = {t.id: t for t in m.tasks}

    return PlanSpec(
        id="plan-impossible-001",
        mission_id=m.id,
        version=1,
        input_snapshot_version=m.version,
        assignments=[
            TaskAssignment(
                task_id="task-drive",
                volunteer_id="luis",
                vehicle_id="van-church-1",  # Luis is NOT eligible for this van
                scheduled_window=tasks["task-drive"].time_window,
            ),
            TaskAssignment(
                task_id="task-handle",
                volunteer_id="priya",
                scheduled_window=tasks["task-handle"].time_window,
            ),
            TaskAssignment(
                task_id="task-unlock",
                volunteer_id="elena",
                scheduled_window=tasks["task-unlock"].time_window,
            ),
        ],
        is_feasible=False,
        solver_status="NOT_SOLVED",
        status=PlanStatus.PROPOSED,
        provenance=DataProvenance.SIMULATED,
    )


def build_impossible_plan_overlap(mission: MissionSpec | None = None) -> PlanSpec:
    """Impossible: assigns Luis to both driving and handling simultaneously."""
    m = mission or build_eastside_mission()
    tasks = {t.id: t for t in m.tasks}

    # Make driving overlap with handling (both during the service window)
    overlap_window = TimeWindow(
        start=THURSDAY_BASE,
        end=THURSDAY_BASE + timedelta(hours=1),
    )

    return PlanSpec(
        id="plan-impossible-002",
        mission_id=m.id,
        version=1,
        input_snapshot_version=m.version,
        assignments=[
            TaskAssignment(
                task_id="task-drive",
                volunteer_id="luis",
                scheduled_window=overlap_window,
            ),
            TaskAssignment(
                task_id="task-handle",
                volunteer_id="luis",
                scheduled_window=overlap_window,
            ),
            TaskAssignment(
                task_id="task-unlock",
                volunteer_id="elena",
                scheduled_window=tasks["task-unlock"].time_window,
            ),
        ],
        is_feasible=False,
        solver_status="NOT_SOLVED",
        status=PlanStatus.PROPOSED,
        provenance=DataProvenance.SIMULATED,
    )


# ---------------------------------------------------------------------------
# Event / recovery fixtures — SIMULATED
# ---------------------------------------------------------------------------


def build_maya_unavailable_event() -> ResourceUnavailableEvent:
    return ResourceUnavailableEvent(
        id="evt-maya-unavail",
        resource_id="maya",
        resource_type="volunteer",
        reason="Called in sick (SIMULATED)",
        affected_plan_ids=["plan-valid-001"],
        affected_mission_ids=["mission-eastside-thu"],
    )


def build_recovery_proposal() -> RecoveryProposal:
    """Recovery: replace Maya with Gina as driver."""
    m = build_eastside_mission()
    tasks = {t.id: t for t in m.tasks}

    recovery_plan = PlanSpec(
        id="plan-recovery-001",
        mission_id=m.id,
        version=2,
        input_snapshot_version=m.version,
        assignments=[
            TaskAssignment(
                task_id="task-drive",
                volunteer_id="gina",  # Gina replaces Maya
                vehicle_id="van-church-1",
                scheduled_window=tasks["task-drive"].time_window,
            ),
            TaskAssignment(
                task_id="task-handle",
                volunteer_id="priya",
                scheduled_window=tasks["task-handle"].time_window,
            ),
            TaskAssignment(
                task_id="task-unlock",
                volunteer_id="elena",
                scheduled_window=tasks["task-unlock"].time_window,
            ),
        ],
        is_feasible=True,
        solver_status="OPTIMAL",
        status=PlanStatus.PROPOSED,
        outstanding_confirmations=["gina"],
        provenance=DataProvenance.SIMULATED,
    )

    return RecoveryProposal(
        id="recovery-001",
        triggering_event_id="evt-maya-unavail",
        original_plan_id="plan-valid-001",
        proposed_plan=recovery_plan,
        changes_summary=[
            "Replaced Maya (unavailable) with Gina as van driver.",
            "Gina is certified for Church Van and authorized for Eastside.",
        ],
        requires_approval=True,
        provenance=DataProvenance.SIMULATED,
    )


def build_sample_mission_events() -> list[MissionEvent]:
    """A sequence of events for the Eastside mission lifecycle."""
    mission_id = "mission-eastside-thu"
    return [
        MissionEvent(
            id="mevt-001",
            mission_id=mission_id,
            kind=EventKind.PLAN_PROPOSED,
            description="Initial plan proposed with Maya, Priya, Elena.",
            actor="system",
        ),
        MissionEvent(
            id="mevt-002",
            mission_id=mission_id,
            kind=EventKind.RESOURCE_UNAVAILABLE,
            payload={"resource_id": "maya", "reason": "Called in sick (SIMULATED)"},
            description="Maya became unavailable.",
            actor="system",
        ),
        MissionEvent(
            id="mevt-003",
            mission_id=mission_id,
            kind=EventKind.RECOVERY_TRIGGERED,
            payload={"recovery_id": "recovery-001"},
            description="Recovery proposal generated: Gina replaces Maya.",
            actor="system",
        ),
    ]
