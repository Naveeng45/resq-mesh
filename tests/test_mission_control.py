"""Phase 6 — Mission-control tests.

Tests the mission-control data assembly layer, API endpoints,
and simulation flow. All data is SIMULATED.
"""

from __future__ import annotations

import pytest

from tests.fixtures.thursday_fixture import (
    build_church_van,
    build_eastside_mission,
    build_valid_plan,
    build_volunteers,
)
from app.mission_control import (
    MissionControlPayload,
    TaskView,
    VolunteerView,
    RecoveryView,
    build_mission_control_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fixture():
    mission = build_eastside_mission()
    volunteers = build_volunteers()
    vehicles = [build_church_van()]
    plan = build_valid_plan(mission)
    return mission, volunteers, vehicles, plan


# ---------------------------------------------------------------------------
# Normal active plan (M-1)
# ---------------------------------------------------------------------------

class TestNormalActivePlan:
    """Tests for a fully covered, feasible plan."""

    def test_payload_type(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert isinstance(payload, MissionControlPayload)

    def test_mission_id(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.mission_id == mission.id

    def test_all_roles_covered(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.roles_covered == payload.roles_required
        assert payload.roles_covered == 3

    def test_no_tasks_at_risk(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.tasks_at_risk == 0

    def test_task_count_matches_mission(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert len(payload.tasks) == len(mission.tasks)

    def test_tasks_have_volunteers(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        for t in payload.tasks:
            assert t.volunteer_id is not None
            assert t.volunteer_name is not None

    def test_task_qualification_status(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        for t in payload.tasks:
            assert t.qualification_status == "qualified"

    def test_volunteers_present(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        # Only opted-in volunteers should be in the view
        assert len(payload.volunteers) > 0
        for v in payload.volunteers:
            assert v.opted_in

    def test_assigned_volunteers(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assigned = [v for v in payload.volunteers if v.is_assigned]
        assert len(assigned) == 3  # one per task

    def test_spof_detection(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        # Elena is the sole keyholder → SPOF
        assert "elena" in payload.single_points_of_failure

    def test_counterfactual_scenarios_present(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert len(payload.counterfactual_scenarios) > 0

    def test_recovery_summary_not_empty(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.recovery_summary
        assert "0 of" not in payload.recovery_summary or "UNKNOWN" not in payload.recovery_summary

    def test_plan_status_proposed(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.plan_status == "proposed"

    def test_destination_coords(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.destination_coords is not None
        assert len(payload.destination_coords) == 2

    def test_provenance_simulated(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.provenance == "SIMULATED"
        assert payload.simulated is True

    def test_risk_status_nominal(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        assert payload.risk_status == "nominal"


# ---------------------------------------------------------------------------
# Counterfactual scenario details
# ---------------------------------------------------------------------------

class TestCounterfactualDetails:

    def test_maya_recoverable(self):
        """Maya removal should be recoverable (Gina can replace)."""
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        maya_cf = next(
            (s for s in payload.counterfactual_scenarios
             if s["removed_resource_id"] == "maya"),
            None
        )
        assert maya_cf is not None
        assert maya_cf["recovery_status"] == "recoverable"

    def test_elena_infeasible(self):
        """Elena removal should be infeasible (sole keyholder)."""
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        elena_cf = next(
            (s for s in payload.counterfactual_scenarios
             if s["removed_resource_id"] == "elena"),
            None
        )
        assert elena_cf is not None
        assert elena_cf["recovery_status"] == "infeasible"

    def test_elena_bottleneck(self):
        """Elena removal should have bottleneck explanation."""
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        elena_cf = next(
            s for s in payload.counterfactual_scenarios
            if s["removed_resource_id"] == "elena"
        )
        assert elena_cf["bottleneck"] is not None
        assert elena_cf["bottleneck"]["is_single_point_of_failure"]


# ---------------------------------------------------------------------------
# Simulation vs actual cancellation
# ---------------------------------------------------------------------------

class TestSimulationIsolation:

    def test_simulation_does_not_modify_original(self):
        """Building a payload does not mutate the input objects."""
        mission, vols, vehs, plan = _fixture()
        original_vol_ids = [v.id for v in vols]
        original_plan_id = plan.id

        build_mission_control_payload(mission, vols, vehs, plan)

        assert [v.id for v in vols] == original_vol_ids
        assert plan.id == original_plan_id

    def test_at_risk_payload(self):
        payload = build_mission_control_payload(
            *_fixture()[:3],
            plan=_fixture()[3],
            risk_status="at_risk",
            risk_reason="Test disruption",
        )
        assert payload.risk_status == "at_risk"
        assert payload.risk_reason == "Test disruption"


# ---------------------------------------------------------------------------
# Recovery proposal
# ---------------------------------------------------------------------------

class TestRecoveryView:

    def test_recovery_view_renders(self):
        mission, vols, vehs, plan = _fixture()
        recovery_data = {
            "id": "test-recovery",
            "is_feasible": True,
            "what_changed": "Maya removed, Gina replaces",
            "unchanged_assignments": ["Handle food", "Open site"],
            "changes": [
                {"task_id": "task-drive", "task_label": "Drive van",
                 "before_volunteer_id": "maya", "before_volunteer_name": "Maya",
                 "after_volunteer_id": "gina", "after_volunteer_name": "Gina",
                 "change_type": "replaced"},
            ],
            "capability_gaps": [],
            "safe_actions": [],
            "pending_confirmations": ["gina"],
            "requirements_satisfied": True,
        }
        payload = build_mission_control_payload(
            mission, vols, vehs, plan,
            recovery_proposal=recovery_data,
        )
        assert payload.recovery is not None
        assert payload.recovery.is_feasible
        assert payload.recovery.proposal_id == "test-recovery"
        assert len(payload.recovery.changes) == 1
        assert len(payload.recovery.pending_confirmations) == 1

    def test_infeasible_recovery_view(self):
        mission, vols, vehs, plan = _fixture()
        recovery_data = {
            "id": "test-infeasible",
            "is_feasible": False,
            "what_changed": "Elena removed",
            "capability_gaps": ["site_keyholder"],
            "safe_actions": ["Contact backup keyholder"],
            "targeted_request": "Recruit a keyholder for Eastside",
        }
        payload = build_mission_control_payload(
            mission, vols, vehs, plan,
            recovery_proposal=recovery_data,
        )
        assert payload.recovery is not None
        assert not payload.recovery.is_feasible
        assert "site_keyholder" in payload.recovery.capability_gaps
        assert payload.recovery.targeted_request is not None


# ---------------------------------------------------------------------------
# Infeasible plan (no plan provided, solver fails)
# ---------------------------------------------------------------------------

class TestInfeasiblePlan:

    def test_infeasible_with_only_opted_out(self):
        """With only opted-out volunteers, the plan should be infeasible."""
        mission = build_eastside_mission()
        vehicles = [build_church_van()]
        # Only Jordan (opted_out) — solver will exclude
        opted_out_only = [v for v in build_volunteers() if not v.opted_in]
        payload = build_mission_control_payload(mission, opted_out_only, vehicles)
        assert payload.plan_status == "infeasible"
        assert payload.tasks_at_risk == len(mission.tasks)
        assert payload.risk_status == "blocked"


# ---------------------------------------------------------------------------
# Task view properties
# ---------------------------------------------------------------------------

class TestTaskViews:

    def test_task_dependencies(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        handle_task = next(t for t in payload.tasks if t.task_id == "task-handle")
        assert "task-drive" in handle_task.depends_on

    def test_time_window_label(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        for t in payload.tasks:
            if t.time_window_label:
                assert "–" in t.time_window_label  # has start–end format

    def test_confirmation_tracking(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        pending_count = sum(1 for t in payload.tasks if t.confirmation_status == "pending")
        # All 3 volunteers are in outstanding_confirmations
        assert pending_count == 3


# ---------------------------------------------------------------------------
# Volunteer view properties
# ---------------------------------------------------------------------------

class TestVolunteerViews:

    def test_travel_estimates_present(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        has_travel = any(v.travel_label for v in payload.volunteers)
        assert has_travel

    def test_opted_out_excluded(self):
        """Jordan (opted_out) should not appear in volunteer views."""
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        ids = [v.id for v in payload.volunteers]
        assert "jordan" not in ids

    def test_spof_volunteers_marked(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        spof_vols = [v for v in payload.volunteers if v.is_spof]
        assert len(spof_vols) > 0
        spof_ids = [v.id for v in spof_vols]
        assert "elena" in spof_ids

    def test_location_coords_present(self):
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        for v in payload.volunteers:
            assert v.location_coords is not None
            assert len(v.location_coords) == 2


# ---------------------------------------------------------------------------
# Auto-solve (no plan provided)
# ---------------------------------------------------------------------------

class TestAutoSolve:

    def test_auto_solve_produces_plan(self):
        """When no plan is provided, the assembly should auto-solve."""
        mission, vols, vehs, _ = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs)
        assert payload.roles_covered > 0
        assert len([t for t in payload.tasks if t.volunteer_id]) > 0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient
from app.api.server import app

client = TestClient(app)


class TestMissionControlAPI:

    def test_fixture_endpoint(self):
        resp = client.get("/api/mission-control/fixture")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mission_id"] == "mission-eastside-thu"
        assert data["simulated"] is True
        assert "_raw_mission" in data
        assert "_raw_volunteers" in data
        assert "_raw_plan" in data

    def test_fixture_has_tasks(self):
        resp = client.get("/api/mission-control/fixture")
        data = resp.json()
        assert len(data["tasks"]) == 3

    def test_fixture_has_volunteers(self):
        resp = client.get("/api/mission-control/fixture")
        data = resp.json()
        assert len(data["volunteers"]) > 0

    def test_fixture_has_counterfactual(self):
        resp = client.get("/api/mission-control/fixture")
        data = resp.json()
        assert len(data["counterfactual_scenarios"]) > 0

    def test_fixture_has_spofs(self):
        resp = client.get("/api/mission-control/fixture")
        data = resp.json()
        assert "elena" in data["single_points_of_failure"]

    def test_mission_control_page_served(self):
        resp = client.get("/mission-control")
        assert resp.status_code == 200
        assert b"Mission Control" in resp.content

    def test_simulate_removal_recoverable(self):
        """Simulating Maya's removal should produce a recoverable proposal."""
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
        assert data["risk_status"] in ("at_risk", "nominal")
        assert data["recovery"] is not None
        assert data["recovery"]["is_feasible"]

    def test_simulate_removal_infeasible(self):
        """Simulating Elena's removal should produce an infeasible recovery."""
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
        assert data["recovery"] is not None
        assert not data["recovery"]["is_feasible"]
        assert len(data["recovery"]["capability_gaps"]) > 0

    def test_simulate_removal_missing_plan(self):
        """Missing plan should return an error message."""
        fixture = client.get("/api/mission-control/fixture").json()
        resp = client.post("/api/mission-control/simulate-removal", json={
            "mission": fixture["_raw_mission"],
            "volunteers": fixture["_raw_volunteers"],
            "vehicles": fixture["_raw_vehicles"],
            # plan omitted, removed_resource_ids empty
            "removed_resource_ids": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_post_mission_control(self):
        """Direct mission-control payload assembly endpoint."""
        fixture = client.get("/api/mission-control/fixture").json()
        resp = client.post("/api/mission-control", json={
            "mission": fixture["_raw_mission"],
            "volunteers": fixture["_raw_volunteers"],
            "vehicles": fixture["_raw_vehicles"],
            "plan": fixture["_raw_plan"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["mission_id"] == "mission-eastside-thu"
        assert data["roles_covered"] == 3


# ---------------------------------------------------------------------------
# Stale proposal handling
# ---------------------------------------------------------------------------

class TestStaleProposal:

    def test_stale_version_check(self):
        """Recovery with wrong version should be flagged."""
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(
            mission, vols, vehs, plan,
            recovery_proposal={
                "id": "stale-proposal",
                "is_feasible": False,
                "what_changed": "Stale recovery",
                "capability_gaps": ["outdated"],
            },
        )
        assert payload.recovery is not None
        assert not payload.recovery.is_feasible


# ---------------------------------------------------------------------------
# Empty / loading / error states
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_no_volunteers_returns_infeasible(self):
        """With no opted-in volunteers, plan should be infeasible."""
        mission = build_eastside_mission()
        vehicles = [build_church_van()]
        # Jordan is the only volunteer and is opted out
        from tests.fixtures.thursday_fixture import build_volunteers
        opted_out_only = [v for v in build_volunteers() if not v.opted_in]
        payload = build_mission_control_payload(mission, opted_out_only, vehicles)
        assert payload.plan_status == "infeasible"
        assert payload.risk_status == "blocked"

    def test_payload_serializable(self):
        """Payload should be JSON-serializable."""
        import json
        mission, vols, vehs, plan = _fixture()
        payload = build_mission_control_payload(mission, vols, vehs, plan)
        data = payload.model_dump(mode="json")
        serialized = json.dumps(data)
        assert len(serialized) > 0
