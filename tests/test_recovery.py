"""Phase 4 — Tests for event-driven minimum-change recovery.

Required scenarios:
1. Driver cancellation repaired by role swapping
2. Approval activates the correct version
3. Stale approval rejected
4. Duplicate event/approval safe
5. Concurrent missions cannot reserve the same resource
6. Pending replacement declines
7. No feasible recovery produces an actionable blocked state

Additional coverage:
- Event dedup by effective_time
- Stale event rejected
- Min-change fewer than from-scratch
- Mission risk status
- Notification adapter integration
- Completed/in-progress task preservation

ALL DATA IS SIMULATED.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.contracts import (
    AvailabilityInterval,
    ConfirmationStatus,
    DataProvenance,
    MissionSpec,
    PlanSpec,
    PlanStatus,
    TaskAssignment,
    TaskDefinition,
    TimeWindow,
    TravelEstimate,
    VehicleSpec,
    VolunteerSpec,
)
from app.recovery import (
    ApprovalRequest,
    AssignmentChange,
    EventLog,
    MissionRiskStatus,
    RecoveryEngine,
    RecoveryProposalSpec,
    ResourceEvent,
    TaskExecutionStatus,
    TestNotificationAdapter,
    compute_assignment_diff,
    plan_recovery,
)

# ---------------------------------------------------------------------------
# Shared time constants — ALL SIMULATED
# ---------------------------------------------------------------------------

TZ = timezone(timedelta(hours=-7), name="US/Pacific")
BASE = datetime(2026, 9, 10, 16, 0, 0, tzinfo=TZ)
END = BASE + timedelta(hours=3)
SERVICE = TimeWindow(start=BASE, end=END)
AVAIL = TimeWindow(start=BASE - timedelta(hours=1), end=END + timedelta(hours=1))

# Task windows
DRIVE_WIN = TimeWindow(start=BASE - timedelta(minutes=30), end=BASE)
HANDLE_WIN = TimeWindow(start=BASE, end=BASE + timedelta(hours=2))
UNLOCK_WIN = TimeWindow(start=BASE - timedelta(minutes=15), end=BASE)


def _travel(vol_id: str, dest: str, mins: float) -> TravelEstimate:
    return TravelEstimate(
        origin_id=vol_id,
        destination_id=dest,
        estimated_minutes=mins,
        distance_km=round(mins * 0.8, 1),
        provenance=DataProvenance.SIMULATED,
    )


def _avail() -> list[AvailabilityInterval]:
    return [AvailabilityInterval(window=AVAIL)]


# ---------------------------------------------------------------------------
# Role-swap scenario fixtures
# ---------------------------------------------------------------------------


def _role_swap_mission() -> MissionSpec:
    """Mission requiring driver, handler, keyholder.

    Drive and handle tasks OVERLAP so the same person cannot do both.
    This forces role-swap composition when the assigned driver cancels.
    """
    # Drive and handle run concurrently during the service window
    concurrent_win = TimeWindow(start=BASE, end=BASE + timedelta(hours=2))
    return MissionSpec(
        id="mission-swap",
        version=1,
        destination="Swap Site (SIMULATED)",
        destination_id="swap-site",
        mission_timezone="US/Pacific",
        service_window=SERVICE,
        deadline=BASE,
        incident_type="thursday_distribution",
        required_roles=["van_certified_driver", "food_handler", "site_keyholder"],
        tasks=[
            TaskDefinition(
                id="t-drive",
                label="Drive van",
                required_capability="van_certified_driver",
                duration_minutes=120,
                time_window=concurrent_win,
            ),
            TaskDefinition(
                id="t-handle",
                label="Handle food",
                required_capability="food_handler",
                duration_minutes=120,
                time_window=concurrent_win,
            ),
            TaskDefinition(
                id="t-unlock",
                label="Open site",
                required_capability="site_keyholder",
                duration_minutes=15,
                time_window=UNLOCK_WIN,
            ),
        ],
        provenance=DataProvenance.SIMULATED,
    )


def _role_swap_volunteers() -> list[VolunteerSpec]:
    """Volunteers for role-swap scenario.

    Alpha: driver only (will cancel)
    Beta: driver + handler (currently handling; can swap to driving)
    Gamma: keyholder (unaffected)
    Delta: handler only (available, not assigned; can replace Beta)
    """
    return [
        VolunteerSpec(
            id="alpha",
            name="Alpha (SIMULATED)",
            capability_codes=["van_certified_driver"],
            availability_intervals=_avail(),
            authorized_site_ids=["swap-site"],
            opted_in=True,
            travel_estimates=[_travel("alpha", "swap-site", 10)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="beta",
            name="Beta (SIMULATED)",
            capability_codes=["van_certified_driver", "food_handler"],
            availability_intervals=_avail(),
            authorized_site_ids=["swap-site"],
            opted_in=True,
            travel_estimates=[_travel("beta", "swap-site", 12)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="gamma",
            name="Gamma (SIMULATED)",
            capability_codes=["site_keyholder"],
            availability_intervals=_avail(),
            authorized_site_ids=["swap-site"],
            opted_in=True,
            travel_estimates=[_travel("gamma", "swap-site", 5)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="delta",
            name="Delta (SIMULATED)",
            capability_codes=["food_handler"],
            availability_intervals=_avail(),
            authorized_site_ids=["swap-site"],
            opted_in=True,
            travel_estimates=[_travel("delta", "swap-site", 8)],
            provenance=DataProvenance.SIMULATED,
        ),
    ]


def _role_swap_baseline(mission: MissionSpec) -> PlanSpec:
    """Baseline: Alpha=drive, Beta=handle, Gamma=unlock.

    Uses task time windows from the mission (drive and handle are concurrent).
    """
    task_windows = {t.id: t.time_window for t in mission.tasks}
    return PlanSpec(
        id="plan-swap-baseline",
        mission_id=mission.id,
        version=1,
        input_snapshot_version=mission.version,
        assignments=[
            TaskAssignment(
                task_id="t-drive",
                volunteer_id="alpha",
                scheduled_window=task_windows["t-drive"],
            ),
            TaskAssignment(
                task_id="t-handle",
                volunteer_id="beta",
                scheduled_window=task_windows["t-handle"],
            ),
            TaskAssignment(
                task_id="t-unlock",
                volunteer_id="gamma",
                scheduled_window=task_windows["t-unlock"],
            ),
        ],
        is_feasible=True,
        solver_status="OPTIMAL",
        status=PlanStatus.PROPOSED,
        outstanding_confirmations=["alpha", "beta", "gamma"],
        provenance=DataProvenance.SIMULATED,
    )


# ---------------------------------------------------------------------------
# Test 1: Driver cancellation repaired by role swapping
# ---------------------------------------------------------------------------


def test_role_swap_recovery():
    """Alpha (driver) cancels. No other pure driver available.
    Beta (handler, also qualified to drive) swaps to driving.
    Delta (handler) fills Beta's original handling task.
    Gamma (keyholder) remains unchanged.

    This arises from resource data and constraints, not hardcoded names.
    """
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
        triggering_event_ids=["evt-alpha-cancel"],
    )

    assert proposal.is_feasible
    assert proposal.changes_count >= 1

    # Verify the recovery plan
    plan = proposal.proposed_plan
    assignment_map = {a.task_id: a.volunteer_id for a in plan.assignments}

    # Alpha must NOT be assigned (unavailable)
    assert "alpha" not in assignment_map.values()

    # All tasks assigned
    assert set(assignment_map.keys()) == {"t-drive", "t-handle", "t-unlock"}

    # Driver must have van_certified_driver capability
    driver_vol = next(v for v in vols if v.id == assignment_map["t-drive"])
    assert driver_vol.has_capability("van_certified_driver")

    # Handler must have food_handler capability
    handler_vol = next(v for v in vols if v.id == assignment_map["t-handle"])
    assert handler_vol.has_capability("food_handler")

    # Keyholder unchanged (minimum change)
    assert assignment_map["t-unlock"] == "gamma"

    # The solver should use role swap: Beta drives, Delta handles
    # (Beta is the only remaining volunteer with driver capability)
    assert assignment_map["t-drive"] == "beta"
    assert assignment_map["t-handle"] == "delta"

    # Verify diff structure
    changes_by_task = {c.task_id: c for c in proposal.changes}
    assert changes_by_task["t-drive"].change_type == "replaced"
    assert changes_by_task["t-unlock"].change_type == "unchanged"


# ---------------------------------------------------------------------------
# Test 2: Approval activates the correct version
# ---------------------------------------------------------------------------


def test_approval_activates_correct_version():
    """Approve a recovery proposal. Plan transitions to APPROVED with correct coordinator."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    assert proposal.is_feasible
    assert proposal.status == "pending"

    result = engine.approve_proposal(ApprovalRequest(
        proposal_id=proposal.id,
        coordinator_id="coordinator-jane",
        expected_plan_version=baseline.version,
        expected_mission_version=mission.version,
    ))

    assert result.success
    assert result.status == "approved"
    assert result.activated_plan is not None
    assert result.activated_plan.status == PlanStatus.APPROVED
    assert result.activated_plan.approved_by == "coordinator-jane"

    # Proposal status updated
    stored = engine.get_proposal(proposal.id)
    assert stored is not None
    assert stored.status == "approved"


# ---------------------------------------------------------------------------
# Test 3: Stale approval rejected
# ---------------------------------------------------------------------------


def test_stale_approval_rejected():
    """Approve with wrong mission version → stale."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    assert proposal.is_feasible

    # Approve with wrong mission version
    result = engine.approve_proposal(ApprovalRequest(
        proposal_id=proposal.id,
        coordinator_id="coordinator-jane",
        expected_plan_version=baseline.version,
        expected_mission_version=999,  # wrong version
    ))

    assert not result.success
    assert result.status == "stale"
    assert "version" in result.reason.lower()


def test_stale_approval_wrong_plan_version():
    """Approve with wrong plan version → stale."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    result = engine.approve_proposal(ApprovalRequest(
        proposal_id=proposal.id,
        coordinator_id="coordinator-jane",
        expected_plan_version=999,  # wrong plan version
        expected_mission_version=mission.version,
    ))

    assert not result.success
    assert result.status == "stale"


# ---------------------------------------------------------------------------
# Test 4: Duplicate event/approval safe
# ---------------------------------------------------------------------------


def test_duplicate_event_safe():
    """Ingesting the same event twice returns 'duplicate'."""
    log = EventLog()
    event = ResourceEvent(
        id="evt-dup-1",
        resource_id="alpha",
        resource_type="volunteer",
        effective_time=BASE,
        source="test",
        reason="Cancelled (SIMULATED)",
    )

    r1 = log.ingest(event)
    assert r1.status == "accepted"

    r2 = log.ingest(event)
    assert r2.status == "duplicate"


def test_duplicate_event_same_effective_time():
    """Two events with different IDs but same (resource, effective_time) → duplicate."""
    log = EventLog()
    event1 = ResourceEvent(
        id="evt-a",
        resource_id="alpha",
        resource_type="volunteer",
        effective_time=BASE,
        source="source-1",
        reason="Reason 1",
    )
    event2 = ResourceEvent(
        id="evt-b",
        resource_id="alpha",
        resource_type="volunteer",
        effective_time=BASE,
        source="source-2",
        reason="Reason 2",
    )

    r1 = log.ingest(event1)
    assert r1.status == "accepted"

    r2 = log.ingest(event2)
    assert r2.status == "duplicate"


def test_duplicate_approval_idempotent():
    """Approving the same proposal twice returns 'already_approved'."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    approve_req = ApprovalRequest(
        proposal_id=proposal.id,
        coordinator_id="coordinator-jane",
        expected_plan_version=baseline.version,
        expected_mission_version=mission.version,
    )

    r1 = engine.approve_proposal(approve_req)
    assert r1.success
    assert r1.status == "approved"

    r2 = engine.approve_proposal(approve_req)
    assert r2.success
    assert r2.status == "already_approved"
    assert r2.activated_plan is not None


# ---------------------------------------------------------------------------
# Test 5: Concurrent missions cannot reserve the same resource
# ---------------------------------------------------------------------------


def _second_mission() -> tuple[MissionSpec, list[VolunteerSpec], PlanSpec]:
    """A second mission using the same Beta volunteer."""
    mission = MissionSpec(
        id="mission-harbor",
        version=1,
        destination="Harbor Site (SIMULATED)",
        destination_id="harbor",
        mission_timezone="US/Pacific",
        service_window=SERVICE,
        deadline=BASE,
        incident_type="thursday_distribution",
        required_roles=["van_certified_driver", "food_handler"],
        tasks=[
            TaskDefinition(
                id="t2-drive",
                label="Drive to Harbor",
                required_capability="van_certified_driver",
                duration_minutes=30,
                time_window=DRIVE_WIN,
            ),
            TaskDefinition(
                id="t2-handle",
                label="Handle food at Harbor",
                required_capability="food_handler",
                duration_minutes=120,
                time_window=HANDLE_WIN,
                depends_on=["t2-drive"],
            ),
        ],
        provenance=DataProvenance.SIMULATED,
    )

    vols = [
        VolunteerSpec(
            id="beta",  # same volunteer as mission A
            name="Beta (SIMULATED)",
            capability_codes=["van_certified_driver", "food_handler"],
            availability_intervals=_avail(),
            authorized_site_ids=["*"],
            opted_in=True,
            travel_estimates=[_travel("beta", "harbor", 15)],
            provenance=DataProvenance.SIMULATED,
        ),
        VolunteerSpec(
            id="echo",
            name="Echo (SIMULATED)",
            capability_codes=["food_handler"],
            availability_intervals=_avail(),
            authorized_site_ids=["harbor"],
            opted_in=True,
            travel_estimates=[_travel("echo", "harbor", 10)],
            provenance=DataProvenance.SIMULATED,
        ),
    ]

    baseline = PlanSpec(
        id="plan-harbor-baseline",
        mission_id=mission.id,
        version=1,
        input_snapshot_version=mission.version,
        assignments=[
            TaskAssignment(
                task_id="t2-drive",
                volunteer_id="beta",
                scheduled_window=DRIVE_WIN,
            ),
            TaskAssignment(
                task_id="t2-handle",
                volunteer_id="echo",
                scheduled_window=HANDLE_WIN,
            ),
        ],
        is_feasible=True,
        solver_status="OPTIMAL",
        status=PlanStatus.PROPOSED,
        provenance=DataProvenance.SIMULATED,
    )

    return mission, vols, baseline


def test_concurrent_mission_resource_conflict():
    """Mission A reserves Beta. Mission B cannot also reserve Beta."""
    engine = RecoveryEngine()

    # --- Mission A: approve plan that includes Beta ---
    mission_a = _role_swap_mission()
    vols_a = _role_swap_volunteers()
    baseline_a = _role_swap_baseline(mission_a)

    proposal_a = engine.plan_recovery(
        mission=mission_a,
        current_plan=baseline_a,
        volunteers=vols_a,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )
    assert proposal_a.is_feasible

    r1 = engine.approve_proposal(ApprovalRequest(
        proposal_id=proposal_a.id,
        coordinator_id="coordinator-jane",
        expected_plan_version=baseline_a.version,
        expected_mission_version=mission_a.version,
    ))
    assert r1.success

    # Beta is now reserved for mission-swap
    assert "beta" in engine._resource_reservations

    # --- Mission B: try to approve plan that also uses Beta ---
    mission_b, vols_b, baseline_b = _second_mission()

    proposal_b = engine.plan_recovery(
        mission=mission_b,
        current_plan=baseline_b,
        volunteers=vols_b,
        vehicles=[],
        unavailable_resource_ids=[],
    )

    # proposal_b might use beta (solver picks from available)
    # Force the scenario: directly check reservation at approval time
    # The proposal's plan assignments include beta
    plan_b_vols = {a.volunteer_id for a in proposal_b.proposed_plan.assignments}

    if "beta" in plan_b_vols:
        r2 = engine.approve_proposal(ApprovalRequest(
            proposal_id=proposal_b.id,
            coordinator_id="coordinator-bob",
            expected_plan_version=baseline_b.version,
            expected_mission_version=mission_b.version,
        ))
        assert not r2.success
        assert r2.status == "reservation_conflict"
        assert "beta" in r2.reason
    else:
        # If solver didn't pick beta, verify reservation is still held
        assert engine._resource_reservations.get("beta") == "mission-swap"


# ---------------------------------------------------------------------------
# Test 6: Pending replacement declines
# ---------------------------------------------------------------------------


def test_pending_replacement_declines():
    """Volunteer in recovery plan declines. Plan reflects the decline."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )
    assert proposal.is_feasible

    # Approve the proposal
    engine.approve_proposal(ApprovalRequest(
        proposal_id=proposal.id,
        coordinator_id="coordinator-jane",
        expected_plan_version=baseline.version,
        expected_mission_version=mission.version,
    ))

    # Find a replacement volunteer (one who changed in the plan)
    replaced_changes = [
        c for c in proposal.changes if c.change_type == "replaced"
    ]
    assert len(replaced_changes) > 0

    replacement_vol_id = replaced_changes[0].after_volunteer_id
    assert replacement_vol_id is not None

    # Volunteer declines
    result = engine.record_volunteer_response(
        proposal_id=proposal.id,
        volunteer_id=replacement_vol_id,
        response="declined",
    )

    assert result["recorded"]
    assert result["response"] == "declined"
    assert not result["all_confirmed"]

    # Verify assignment confirmation updated
    plan = proposal.proposed_plan
    declined_assignment = next(
        a for a in plan.assignments if a.volunteer_id == replacement_vol_id
    )
    assert declined_assignment.confirmation == ConfirmationStatus.DECLINED


# ---------------------------------------------------------------------------
# Test 7: No feasible recovery produces an actionable blocked state
# ---------------------------------------------------------------------------


def test_infeasible_recovery_blocked_state():
    """Remove sole keyholder. Recovery is infeasible with capability gap reported."""
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    # Gamma is the sole keyholder
    proposal = plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["gamma"],
    )

    assert not proposal.is_feasible
    assert proposal.changes_count == 0

    # Must report the exact capability gap
    assert len(proposal.capability_gaps) > 0
    assert any("site_keyholder" in gap for gap in proposal.capability_gaps)

    # Must suggest safe actions
    assert len(proposal.safe_actions) > 0

    # Must build a targeted request
    assert proposal.targeted_request is not None
    assert "site_keyholder" in proposal.targeted_request
    assert "swap-site" in proposal.targeted_request

    # Infeasible reasons from solver
    assert len(proposal.infeasible_reasons) > 0


def test_infeasible_mission_risk_status():
    """Mission with infeasible recovery shows blocked status."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    # Ingest event
    event = ResourceEvent(
        id="evt-gamma-cancel",
        resource_id="gamma",
        resource_type="volunteer",
        effective_time=BASE,
        mission_id=mission.id,
        source="test",
        reason="Cancelled (SIMULATED)",
    )
    engine.ingest_event(event)

    # Plan recovery (will be infeasible)
    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["gamma"],
        triggering_event_ids=[event.id],
    )

    assert not proposal.is_feasible

    # Check mission risk status
    risk = engine.get_mission_risk_status(mission.id)
    assert risk.status == "blocked"
    assert len(risk.pending_proposals) > 0


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------


def test_stale_event_rejected():
    """Event with older effective_time than latest → stale."""
    log = EventLog()

    newer = ResourceEvent(
        id="evt-new",
        resource_id="alpha",
        resource_type="volunteer",
        effective_time=BASE + timedelta(hours=1),
        source="test",
    )
    older = ResourceEvent(
        id="evt-old",
        resource_id="alpha",
        resource_type="volunteer",
        effective_time=BASE,  # older than evt-new
        source="test",
    )

    r1 = log.ingest(newer)
    assert r1.status == "accepted"

    r2 = log.ingest(older)
    assert r2.status == "stale"


def test_event_requires_tz_aware_times():
    """Events with naive datetimes are rejected."""
    with pytest.raises(ValueError, match="timezone-aware"):
        ResourceEvent(
            resource_id="alpha",
            resource_type="volunteer",
            effective_time=datetime(2026, 9, 10, 16, 0, 0),  # naive
        )


def test_min_change_fewer_than_scratch():
    """Min-change recovery changes fewer assignments than from-scratch solve."""
    from app.coalition_planner import CoalitionPlannerRequest, solve_coalition

    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    # Min-change recovery (with incumbent)
    available = [v for v in vols if v.id != "alpha"]
    min_change_req = CoalitionPlannerRequest(
        mission=mission,
        volunteers=available,
        vehicles=[],
        incumbent_plan=baseline,
        max_alternatives=1,
        time_limit_seconds=5.0,
    )
    min_change_result = solve_coalition(min_change_req)

    # From-scratch solve (no incumbent)
    scratch_req = CoalitionPlannerRequest(
        mission=mission,
        volunteers=available,
        vehicles=[],
        max_alternatives=1,
        time_limit_seconds=5.0,
    )
    scratch_result = solve_coalition(scratch_req)

    assert min_change_result.feasible
    assert scratch_result.feasible

    # Count changes from baseline
    baseline_map = {a.task_id: a.volunteer_id for a in baseline.assignments}

    min_plan = min_change_result.alternatives[0].plan
    min_changes = sum(
        1 for a in min_plan.assignments
        if baseline_map.get(a.task_id) != a.volunteer_id
    )

    scratch_plan = scratch_result.alternatives[0].plan
    scratch_changes = sum(
        1 for a in scratch_plan.assignments
        if baseline_map.get(a.task_id) != a.volunteer_id
    )

    # Min-change should have <= changes than from-scratch
    assert min_changes <= scratch_changes

    # And specifically: Gamma (keyholder) should be unchanged in min-change
    min_map = {a.task_id: a.volunteer_id for a in min_plan.assignments}
    assert min_map["t-unlock"] == "gamma"


def test_min_change_label():
    """When incumbent_plan is provided, the label is 'minimum_disruption'."""
    from app.coalition_planner import CoalitionPlannerRequest, solve_coalition

    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    available = [v for v in vols if v.id != "alpha"]
    req = CoalitionPlannerRequest(
        mission=mission,
        volunteers=available,
        vehicles=[],
        incumbent_plan=baseline,
        max_alternatives=1,
    )
    result = solve_coalition(req)
    assert result.feasible
    assert result.alternatives[0].label == "minimum_disruption"


def test_no_incumbent_label_unchanged():
    """Without incumbent_plan, the label remains 'lowest_travel'."""
    from app.coalition_planner import CoalitionPlannerRequest, solve_coalition

    mission = _role_swap_mission()
    vols = _role_swap_volunteers()

    req = CoalitionPlannerRequest(
        mission=mission,
        volunteers=vols,
        vehicles=[],
        max_alternatives=1,
    )
    result = solve_coalition(req)
    assert result.feasible
    assert result.alternatives[0].label == "lowest_travel"


def test_proposal_version_binding():
    """Proposal records expected mission and plan versions."""
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    assert proposal.expected_mission_version == mission.version
    assert proposal.original_plan_version == baseline.version
    assert proposal.original_plan_id == baseline.id
    assert proposal.mission_id == mission.id


def test_proposal_expiration():
    """Proposals have an expiration time."""
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
        proposal_ttl_minutes=30.0,
    )

    assert proposal.expires_at > proposal.created_at
    delta = proposal.expires_at - proposal.created_at
    assert 29 <= delta.total_seconds() / 60 <= 31  # ~30 minutes


def test_notification_adapter_called():
    """Test notification adapter receives recovery and volunteer notifications."""
    adapter = TestNotificationAdapter()
    engine = RecoveryEngine(notification_adapter=adapter)
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    assert proposal.is_feasible
    # Should have at least a recovery_proposed notification
    assert any(n["type"] == "recovery_proposed" for n in adapter.notifications)
    # Should have volunteer_needed notifications for changed assignments
    vol_needed = [n for n in adapter.notifications if n["type"] == "volunteer_needed"]
    assert len(vol_needed) > 0


def test_approval_not_found():
    """Approving a non-existent proposal returns not_found."""
    engine = RecoveryEngine()
    result = engine.approve_proposal(ApprovalRequest(
        proposal_id="nonexistent",
        coordinator_id="jane",
        expected_plan_version=1,
        expected_mission_version=1,
    ))
    assert not result.success
    assert result.status == "not_found"


def test_volunteer_response_not_in_plan():
    """Recording a response for a volunteer not in the plan fails gracefully."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    result = engine.record_volunteer_response(
        proposal_id=proposal.id,
        volunteer_id="nonexistent",
        response="accepted",
    )
    assert not result["recorded"]


def test_compute_assignment_diff():
    """Diff correctly identifies replaced, unchanged, added, removed."""
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    # Create a recovery plan where drive and handle changed
    concurrent_win = TimeWindow(start=BASE, end=BASE + timedelta(hours=2))
    recovery = PlanSpec(
        id="plan-recovery",
        mission_id=mission.id,
        version=2,
        input_snapshot_version=mission.version,
        assignments=[
            TaskAssignment(
                task_id="t-drive",
                volunteer_id="beta",
                scheduled_window=concurrent_win,
            ),
            TaskAssignment(
                task_id="t-handle",
                volunteer_id="delta",
                scheduled_window=concurrent_win,
            ),
            TaskAssignment(
                task_id="t-unlock",
                volunteer_id="gamma",
                scheduled_window=UNLOCK_WIN,
            ),
        ],
        is_feasible=True,
        solver_status="OPTIMAL",
        provenance=DataProvenance.SIMULATED,
    )

    diff = compute_assignment_diff(baseline, recovery, mission, vols)

    by_task = {c.task_id: c for c in diff}
    assert by_task["t-drive"].change_type == "replaced"
    assert by_task["t-drive"].before_volunteer_id == "alpha"
    assert by_task["t-drive"].after_volunteer_id == "beta"
    assert by_task["t-handle"].change_type == "replaced"
    assert by_task["t-unlock"].change_type == "unchanged"


def test_mission_risk_at_risk():
    """Mission with pending feasible proposal shows at-risk status."""
    engine = RecoveryEngine()
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    event = ResourceEvent(
        id="evt-alpha",
        resource_id="alpha",
        resource_type="volunteer",
        effective_time=BASE,
        mission_id=mission.id,
        source="test",
    )
    engine.ingest_event(event)

    engine.plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
        triggering_event_ids=[event.id],
    )

    risk = engine.get_mission_risk_status(mission.id)
    assert risk.status == "at_risk"
    assert "alpha" in risk.unavailable_resources


def test_mission_risk_nominal():
    """Mission with no disruptions shows nominal status."""
    engine = RecoveryEngine()
    risk = engine.get_mission_risk_status("mission-clean")
    assert risk.status == "nominal"


def test_provenance_is_simulated():
    """All recovery proposals carry SIMULATED provenance."""
    mission = _role_swap_mission()
    vols = _role_swap_volunteers()
    baseline = _role_swap_baseline(mission)

    proposal = plan_recovery(
        mission=mission,
        current_plan=baseline,
        volunteers=vols,
        vehicles=[],
        unavailable_resource_ids=["alpha"],
    )

    assert proposal.provenance == DataProvenance.SIMULATED
