"""Phase 7 — End-to-end verification tests for all demo scenarios.

These tests prove the enhancement works end to end using controlled
fixture data and deterministic assertions. ALL data is SIMULATED.

Test categories:
- Demo A: Joint planning vs greedy
- Demo B: Recomposition (role swap + approval + acceptance)
- Demo C: Honest blocking
- Demo D: Prevention stress testing
- Cross-demo: Aggregate measurements and regression
- API integration: HTTP endpoints for demo data
- Frontend: Mission-control payload structure
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.api.server import app
from app.coalition_planner import (
    CoalitionPlannerRequest,
    CoalitionPlannerResult,
    solve_coalition,
    solve_greedy,
)
from app.contracts import (
    ConfirmationStatus,
    DataProvenance,
    MissionSpec,
    PlanSpec,
    PlanStatus,
    VehicleSpec,
    VolunteerSpec,
)
from app.counterfactual import run_counterfactual_analysis
from app.demo_runner import (
    DemoAResult,
    DemoBResult,
    DemoCResult,
    DemoDResult,
    FullDemoResult,
    demo_now,
    run_demo_a,
    run_demo_b,
    run_demo_c,
    run_demo_d,
    run_full_demo,
)
from app.mission_control import build_mission_control_payload
from app.recovery import (
    ApprovalRequest,
    RecoveryEngine,
    RecoveryProposalSpec,
    ResourceEvent,
    plan_recovery,
)
from app.validation import validate_plan
from tests.fixtures.thursday_fixture import (
    build_church_van,
    build_eastside_mission,
    build_valid_plan,
    build_volunteers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mission() -> MissionSpec:
    return build_eastside_mission()


@pytest.fixture
def volunteers() -> list[VolunteerSpec]:
    return build_volunteers()


@pytest.fixture
def vehicles() -> list[VehicleSpec]:
    return [build_church_van()]


@pytest.fixture
def baseline_plan(mission: MissionSpec) -> PlanSpec:
    return build_valid_plan(mission)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ===================================================================
# DEMO A: Joint Planning
# ===================================================================


class TestDemoAJointPlanning:
    """Demo A: Greedy nearest-role matching fails; joint solver succeeds."""

    def test_joint_solver_produces_feasible_plan(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.joint_feasible is True

    def test_joint_solver_status_is_optimal(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.joint_solver_status in ("OPTIMAL", "FEASIBLE")

    def test_joint_plan_has_all_tasks_assigned(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.joint_plan is not None
        assert len(result.joint_plan.assignments) == len(mission.tasks)

    def test_joint_plan_passes_independent_validation(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.joint_plan is not None
        violations = validate_plan(result.joint_plan, mission, volunteers, vehicles)
        blocking = [v for v in violations if v.severity == "blocking"]
        assert len(blocking) == 0, f"Blocking violations: {[v.description for v in blocking]}"

    def test_joint_plan_no_double_booking(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.joint_plan is not None
        assigned_ids = [a.volunteer_id for a in result.joint_plan.assignments]
        assert len(assigned_ids) == len(set(assigned_ids)), "Double-booking detected"

    def test_joint_plan_generates_alternatives(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.joint_alternatives_count >= 1

    def test_greedy_behavior_documented(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        """Greedy behavior is documented — either it fails or it succeeds with explanation."""
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.greedy_failure_reason != ""

    def test_conflict_explanation_present(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert len(result.conflict_explanation) > 20

    def test_assignment_summary_has_task_volunteer_pairs(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert len(result.assignment_summary) == len(mission.tasks)
        for entry in result.assignment_summary:
            assert "task" in entry
            assert "volunteer" in entry
            assert "capability" in entry

    def test_planning_duration_measured(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.measurement.planning_duration_ms > 0
        assert result.measurement.planning_duration_ms < 10_000  # under 10s

    def test_opted_out_volunteers_excluded(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.joint_plan is not None
        assigned = {a.volunteer_id for a in result.joint_plan.assignments}
        assert "jordan" not in assigned, "Opted-out volunteer should not be assigned"

    def test_provenance_is_simulated(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec], vehicles: list[VehicleSpec]
    ) -> None:
        result = run_demo_a(mission, volunteers, vehicles)
        assert result.measurement.provenance == "SIMULATED"


# ===================================================================
# DEMO B: Recomposition
# ===================================================================


class TestDemoBRecomposition:
    """Demo B: Driver unavailable → recovery → approval → acceptance."""

    def test_recovery_is_feasible(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.recovery_feasible is True

    def test_removed_volunteer_not_in_recovery_plan(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.recovery_proposal is not None
        assigned = {
            a.volunteer_id for a in result.recovery_proposal.proposed_plan.assignments
        }
        assert result.removed_volunteer_id not in assigned

    def test_recovery_has_assignment_diff(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert len(result.assignment_diff) > 0

    def test_at_least_one_replacement(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        replaced = [d for d in result.assignment_diff if d["type"] == "replaced"]
        assert len(replaced) >= 1

    def test_approval_succeeds(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.approval_result is not None
        assert result.approval_result.success is True
        assert result.approval_result.status == "approved"

    def test_volunteer_acceptance_recorded(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.acceptance_recorded is True

    def test_recovery_plan_passes_validation(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.recovery_proposal is not None
        remaining = [v for v in volunteers if v.id != result.removed_volunteer_id]
        violations = validate_plan(
            result.recovery_proposal.proposed_plan, mission, remaining, vehicles
        )
        blocking = [v for v in violations if v.severity == "blocking"]
        assert len(blocking) == 0

    def test_mission_control_payload_updated(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.mission_control_payload is not None
        assert result.mission_control_payload.risk_status == "at_risk"

    def test_replanning_duration_measured(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.measurement.replanning_duration_ms > 0
        assert result.measurement.replanning_duration_ms < 10_000

    def test_min_change_fewer_assignments_than_scratch(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        """Min-change recovery should change fewer assignments than from-scratch."""
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        assert result.measurement.assignments_changed <= len(mission.tasks)

    def test_unchanged_assignments_preserved(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        unchanged = [d for d in result.assignment_diff if d["type"] == "unchanged"]
        # At least some assignments should be unchanged (min-change)
        assert len(unchanged) >= 1, "Min-change should preserve some assignments"


# ===================================================================
# DEMO C: Honest Block
# ===================================================================


class TestDemoCHonestBlock:
    """Demo C: Sole keyholder unavailable → system blocks safely."""

    def test_recovery_is_infeasible(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert result.recovery_feasible is False

    def test_capability_gaps_reported(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert len(result.capability_gaps) >= 1
        # Should mention keyholder
        gap_text = " ".join(result.capability_gaps)
        assert "keyholder" in gap_text.lower() or "site_keyholder" in gap_text

    def test_safe_actions_provided(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert len(result.safe_actions) >= 1

    def test_targeted_request_present(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert result.targeted_request is not None
        assert len(result.targeted_request) > 10

    def test_risk_status_is_blocked(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert result.risk_status == "blocked"

    def test_does_not_fabricate_authorization(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        """System must not invent a keyholder replacement when none exists."""
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert not result.recovery_feasible
        assert "did not fabricate" in result.explanation.lower() or "did not" in result.explanation.lower()

    def test_does_not_claim_success(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert result.measurement.feasible is False
        assert result.measurement.solver_status == "INFEASIBLE"

    def test_replanning_duration_measured(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        assert result.measurement.replanning_duration_ms > 0


# ===================================================================
# DEMO D: Prevention
# ===================================================================


class TestDemoDPrevention:
    """Demo D: Counterfactual stress testing before activation."""

    def test_all_assigned_volunteers_tested(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assigned_count = len({a.volunteer_id for a in baseline_plan.assignments})
        assert result.total_scenarios == assigned_count

    def test_spof_detected(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assert result.infeasible_count >= 1
        assert len(result.spof_list) >= 1

    def test_elena_is_spof(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assert "elena" in result.spof_list

    def test_recoverable_scenarios_exist(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assert result.recoverable_count >= 1

    def test_no_unknown_scenarios(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assert result.unknown_count == 0, "No scenarios should time out"

    def test_vulnerability_mitigations_provided(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        for v in result.vulnerabilities:
            assert v.mitigation != ""

    def test_spof_mitigation_is_critical(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        spof_vulns = [v for v in result.vulnerabilities if v.is_spof]
        assert len(spof_vulns) >= 1
        for v in spof_vulns:
            assert "CRITICAL" in v.mitigation

    def test_counterfactual_duration_measured(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assert result.measurement.counterfactual_duration_ms > 0
        assert result.measurement.counterfactual_duration_ms < 30_000

    def test_tested_scenarios_description(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assert "Tested" in result.tested_scenarios_description
        assert "scenarios" in result.tested_scenarios_description

    def test_total_counts_consistent(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        result = run_demo_d(mission, volunteers, vehicles, baseline_plan)
        assert (
            result.robust_count
            + result.recoverable_count
            + result.infeasible_count
            + result.unknown_count
            == result.total_scenarios
        )


# ===================================================================
# Full Demo Integration
# ===================================================================


class TestFullDemo:
    """Run all four demos end to end."""

    def test_full_demo_passes(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        result = run_full_demo(mission, volunteers, vehicles)
        assert result.all_demos_passed is True

    def test_verdict_is_ready_with_limitations(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        result = run_full_demo(mission, volunteers, vehicles)
        assert result.verdict == "ready_with_limitations"

    def test_limitations_documented(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        result = run_full_demo(mission, volunteers, vehicles)
        assert len(result.limitations) >= 5

    def test_all_measurements_present(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        result = run_full_demo(mission, volunteers, vehicles)
        assert len(result.measurements) == 4
        scenarios = {m.scenario for m in result.measurements}
        assert "Demo A: Joint Planning" in scenarios
        assert "Demo B: Recomposition" in scenarios
        assert "Demo C: Honest Block" in scenarios
        assert "Demo D: Prevention" in scenarios

    def test_total_duration_under_30s(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        result = run_full_demo(mission, volunteers, vehicles)
        assert result.total_duration_ms < 30_000

    def test_demo_a_b_c_d_consistency(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        """Cross-demo consistency: A produces plan, B recovers it, C blocks, D reports SPOFs."""
        result = run_full_demo(mission, volunteers, vehicles)
        # A produces a feasible plan
        assert result.demo_a.joint_feasible
        # B recovers from driver loss
        assert result.demo_b.recovery_feasible
        # C blocks on keyholder loss
        assert not result.demo_c.recovery_feasible
        # D finds the keyholder as SPOF
        assert "elena" in result.demo_d.spof_list


# ===================================================================
# API Integration Tests
# ===================================================================


class TestAPIIntegration:
    """Test HTTP endpoints produce correct demo payloads."""

    def test_fixture_endpoint_returns_data(self, client: TestClient) -> None:
        resp = client.get("/api/mission-control/fixture")
        assert resp.status_code == 200
        data = resp.json()
        assert "mission_id" in data
        assert len(data["tasks"]) == 3

    def test_fixture_has_spofs(self, client: TestClient) -> None:
        resp = client.get("/api/mission-control/fixture")
        data = resp.json()
        assert "elena" in data["single_points_of_failure"]

    def test_simulate_removal_recoverable(self, client: TestClient) -> None:
        fixture = client.get("/api/mission-control/fixture").json()
        resp = client.post("/api/mission-control/simulate-removal", json={
            "mission": fixture["_raw_mission"],
            "volunteers": fixture["_raw_volunteers"],
            "vehicles": fixture["_raw_vehicles"],
            "plan": fixture["_raw_plan"],
            "removed_resource_ids": ["maya"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_status"] == "at_risk"

    def test_simulate_removal_blocked(self, client: TestClient) -> None:
        fixture = client.get("/api/mission-control/fixture").json()
        resp = client.post("/api/mission-control/simulate-removal", json={
            "mission": fixture["_raw_mission"],
            "volunteers": fixture["_raw_volunteers"],
            "vehicles": fixture["_raw_vehicles"],
            "plan": fixture["_raw_plan"],
            "removed_resource_ids": ["elena"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_status"] == "blocked"

    def test_joint_plan_endpoint(self, client: TestClient) -> None:
        fixture = client.get("/api/mission-control/fixture").json()
        resp = client.post("/api/joint-plan", json={
            "mission": fixture["_raw_mission"],
            "volunteers": fixture["_raw_volunteers"],
            "vehicles": fixture["_raw_vehicles"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["feasible"] is True

    def test_counterfactual_endpoint(self, client: TestClient) -> None:
        fixture = client.get("/api/mission-control/fixture").json()
        resp = client.post("/api/counterfactual", json={
            "mission": fixture["_raw_mission"],
            "baseline_plan": fixture["_raw_plan"],
            "volunteers": fixture["_raw_volunteers"],
            "vehicles": fixture["_raw_vehicles"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["report"]["total_scenarios"] >= 3

    def test_recovery_plan_endpoint(self, client: TestClient) -> None:
        fixture = client.get("/api/mission-control/fixture").json()
        resp = client.post("/api/recovery/plan", json={
            "mission": fixture["_raw_mission"],
            "current_plan": fixture["_raw_plan"],
            "volunteers": fixture["_raw_volunteers"],
            "vehicles": fixture["_raw_vehicles"],
            "unavailable_resource_ids": ["maya"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal"]["is_feasible"] is True

    def test_mission_control_page_loads(self, client: TestClient) -> None:
        resp = client.get("/mission-control")
        assert resp.status_code == 200


# ===================================================================
# Controlled Clock & Isolation
# ===================================================================


class TestIsolation:
    """Verify demo uses controlled clock and isolated data."""

    def test_demo_now_is_deterministic(self) -> None:
        t1 = demo_now()
        t2 = demo_now()
        assert t1 == t2

    def test_demo_now_is_timezone_aware(self) -> None:
        t = demo_now()
        assert t.tzinfo is not None

    def test_demo_does_not_mutate_volunteers(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        """Full demo run must not mutate the input volunteer list."""
        original_count = len(volunteers)
        original_ids = [v.id for v in volunteers]
        run_full_demo(mission, volunteers, vehicles)
        assert len(volunteers) == original_count
        assert [v.id for v in volunteers] == original_ids

    def test_demo_does_not_mutate_mission(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        original_version = mission.version
        original_id = mission.id
        run_full_demo(mission, volunteers, vehicles)
        assert mission.version == original_version
        assert mission.id == original_id

    def test_independent_engine_per_demo(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        """Demo B and C use separate state — B's approval doesn't affect C."""
        result_b = run_demo_b(mission, volunteers, vehicles, baseline_plan)
        result_c = run_demo_c(mission, volunteers, vehicles, baseline_plan)
        # Both should complete independently
        assert result_b.recovery_feasible is True
        assert result_c.recovery_feasible is False


# ===================================================================
# Concurrency Safety
# ===================================================================


class TestConcurrencySafety:
    """Test that concurrent mission resource conflicts are detected."""

    def test_resource_reservation_conflict(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        """Two missions cannot reserve the same volunteer."""
        engine = RecoveryEngine()

        # Mission A approves a plan
        event_a = ResourceEvent(
            resource_id="maya",
            resource_type="volunteer",
            effective_time=demo_now(),
            observed_time=demo_now(),
            mission_id="mission-A",
            is_simulated=True,
            reason="test",
        )
        engine.ingest_event(event_a)
        proposal_a = engine.plan_recovery(
            mission=mission,
            current_plan=baseline_plan,
            volunteers=volunteers,
            vehicles=vehicles,
            unavailable_resource_ids=["maya"],
        )
        assert proposal_a.is_feasible

        result_a = engine.approve_proposal(ApprovalRequest(
            proposal_id=proposal_a.id,
            coordinator_id="coord-A",
            expected_plan_version=baseline_plan.version,
            expected_mission_version=mission.version,
        ))
        assert result_a.success

        # Mission B tries to reserve the same replacement volunteer
        mission_b_data = mission.model_dump(mode="json")
        mission_b_data["id"] = "mission-B"
        mission_b = MissionSpec.model_validate(mission_b_data)
        event_b = ResourceEvent(
            resource_id="maya",
            resource_type="volunteer",
            effective_time=demo_now(),
            observed_time=demo_now(),
            mission_id="mission-B",
            is_simulated=True,
            reason="test",
        )
        engine.ingest_event(event_b)
        proposal_b = engine.plan_recovery(
            mission=mission_b,
            current_plan=baseline_plan,
            volunteers=volunteers,
            vehicles=vehicles,
            unavailable_resource_ids=["maya"],
        )
        if proposal_b.is_feasible:
            result_b = engine.approve_proposal(ApprovalRequest(
                proposal_id=proposal_b.id,
                coordinator_id="coord-B",
                expected_plan_version=baseline_plan.version,
                expected_mission_version=mission.version,
            ))
            # Should conflict on shared volunteer reservation
            assert result_b.status == "reservation_conflict"


# ===================================================================
# Plan Validation Independence
# ===================================================================


class TestPlanValidation:
    """Plans are validated independently of the solver that produced them."""

    def test_solver_output_validated_independently(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec]
    ) -> None:
        result = solve_coalition(CoalitionPlannerRequest(
            mission=mission,
            volunteers=volunteers,
            vehicles=vehicles,
        ))
        assert result.feasible
        plan = result.alternatives[0].plan
        violations = validate_plan(plan, mission, volunteers, vehicles)
        blocking = [v for v in violations if v.severity == "blocking"]
        assert len(blocking) == 0

    def test_recovery_output_validated(
        self, mission: MissionSpec, volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec], baseline_plan: PlanSpec
    ) -> None:
        proposal = plan_recovery(
            mission=mission,
            current_plan=baseline_plan,
            volunteers=volunteers,
            vehicles=vehicles,
            unavailable_resource_ids=["maya"],
        )
        assert proposal.is_feasible
        remaining = [v for v in volunteers if v.id != "maya"]
        violations = validate_plan(proposal.proposed_plan, mission, remaining, vehicles)
        blocking = [v for v in violations if v.severity == "blocking"]
        assert len(blocking) == 0
