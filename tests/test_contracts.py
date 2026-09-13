"""Phase 1 — Schema, validation, and fixture tests for typed domain contracts.

Tests cover:
- Model construction and serialization
- TimeWindow ordering and timezone enforcement
- TravelEstimate unknown-consistency invariant
- Volunteer capability/availability/site-access queries
- Vehicle driver eligibility
- Full validation pipeline on valid and impossible plans
- Backward compatibility: existing models unchanged
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.contracts import (
    ApprovalRecord,
    AvailabilityInterval,
    Commitment,
    ConfirmationStatus,
    ConstraintViolation,
    DataProvenance,
    EventKind,
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
)
from app.validation import validate_plan
from tests.fixtures.thursday_fixture import (
    FULL_AVAIL_WINDOW,
    SERVICE_WINDOW,
    SIMULATED_TZ,
    THURSDAY_BASE,
    build_church_van,
    build_eastside_mission,
    build_impossible_plan_no_driver,
    build_impossible_plan_overlap,
    build_maya_unavailable_event,
    build_recovery_proposal,
    build_sample_mission_events,
    build_valid_plan,
    build_volunteers,
)


class TimeWindowTest(unittest.TestCase):

    def test_valid_window(self) -> None:
        w = TimeWindow(
            start=datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
            end=datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(w)

    def test_end_before_start_raises(self) -> None:
        with self.assertRaises(ValueError):
            TimeWindow(
                start=datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc),
                end=datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
            )

    def test_equal_start_end_raises(self) -> None:
        t = datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            TimeWindow(start=t, end=t)

    def test_naive_datetime_raises(self) -> None:
        with self.assertRaises(ValueError):
            TimeWindow(
                start=datetime(2026, 9, 10, 16, 0),  # naive
                end=datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc),
            )


class TravelEstimateTest(unittest.TestCase):

    def test_known_travel(self) -> None:
        t = TravelEstimate(
            origin_id="maya", destination_id="eastside",
            estimated_minutes=8.0, distance_km=6.4,
        )
        self.assertFalse(t.unknown)

    def test_unknown_travel(self) -> None:
        t = TravelEstimate(
            origin_id="jordan", destination_id="eastside",
            unknown=True,
        )
        self.assertIsNone(t.estimated_minutes)

    def test_unknown_with_minutes_raises(self) -> None:
        with self.assertRaises(ValueError):
            TravelEstimate(
                origin_id="x", destination_id="y",
                estimated_minutes=10.0, unknown=True,
            )

    def test_not_unknown_without_minutes_raises(self) -> None:
        with self.assertRaises(ValueError):
            TravelEstimate(
                origin_id="x", destination_id="y",
                unknown=False,
                # estimated_minutes omitted -> None
            )


class MissionSpecTest(unittest.TestCase):

    def test_build_eastside_mission(self) -> None:
        m = build_eastside_mission()
        self.assertEqual(m.destination_id, "eastside")
        self.assertEqual(len(m.tasks), 3)
        self.assertEqual(m.requested_quantity, 180)
        self.assertEqual(m.provenance, DataProvenance.SIMULATED)

    def test_naive_deadline_raises(self) -> None:
        with self.assertRaises(ValueError):
            MissionSpec(
                destination="Test", destination_id="test",
                service_window=SERVICE_WINDOW,
                deadline=datetime(2026, 9, 10, 16, 0),  # naive
                incident_type="test",
            )

    def test_task_dependencies(self) -> None:
        m = build_eastside_mission()
        handle = next(t for t in m.tasks if t.id == "task-handle")
        self.assertIn("task-drive", handle.depends_on)

    def test_serialization_roundtrip(self) -> None:
        m = build_eastside_mission()
        data = m.model_dump(mode="json")
        m2 = MissionSpec.model_validate(data)
        self.assertEqual(m.id, m2.id)
        self.assertEqual(len(m.tasks), len(m2.tasks))


class VolunteerSpecTest(unittest.TestCase):

    def test_build_volunteers(self) -> None:
        vols = build_volunteers()
        self.assertEqual(len(vols), 7)
        maya = next(v for v in vols if v.id == "maya")
        self.assertTrue(maya.has_capability("van_certified_driver"))
        self.assertFalse(maya.has_capability("food_handler"))

    def test_availability_check(self) -> None:
        vols = build_volunteers()
        maya = next(v for v in vols if v.id == "maya")
        self.assertTrue(maya.is_available_during(SERVICE_WINDOW))

    def test_site_access(self) -> None:
        vols = build_volunteers()
        maya = next(v for v in vols if v.id == "maya")
        self.assertTrue(maya.has_site_access("eastside"))
        self.assertFalse(maya.has_site_access("harbor"))

    def test_wildcard_site_access(self) -> None:
        vols = build_volunteers()
        luis = next(v for v in vols if v.id == "luis")
        self.assertTrue(luis.has_site_access("eastside"))
        self.assertTrue(luis.has_site_access("harbor"))
        self.assertTrue(luis.has_site_access("any-site"))

    def test_jordan_not_opted_in(self) -> None:
        vols = build_volunteers()
        jordan = next(v for v in vols if v.id == "jordan")
        self.assertFalse(jordan.opted_in)

    def test_luis_dual_capability(self) -> None:
        vols = build_volunteers()
        luis = next(v for v in vols if v.id == "luis")
        self.assertTrue(luis.has_capability("van_certified_driver"))
        self.assertTrue(luis.has_capability("food_handler"))


class VehicleSpecTest(unittest.TestCase):

    def test_build_church_van(self) -> None:
        van = build_church_van()
        self.assertEqual(van.capacity, 200)
        self.assertEqual(van.capacity_unit, "meals")

    def test_driver_eligibility(self) -> None:
        van = build_church_van()
        self.assertTrue(van.has_eligible_driver(["maya", "priya"]))
        self.assertFalse(van.has_eligible_driver(["luis", "priya"]))

    def test_vehicle_availability(self) -> None:
        van = build_church_van()
        self.assertTrue(van.is_available_during(SERVICE_WINDOW))


class PlanSpecTest(unittest.TestCase):

    def test_valid_plan_structure(self) -> None:
        plan = build_valid_plan()
        self.assertEqual(len(plan.assignments), 3)
        self.assertEqual(plan.status, PlanStatus.PROPOSED)
        self.assertFalse(plan.all_confirmed)

    def test_impossible_plan_no_driver(self) -> None:
        plan = build_impossible_plan_no_driver()
        self.assertFalse(plan.is_feasible)

    def test_impossible_plan_overlap(self) -> None:
        plan = build_impossible_plan_overlap()
        self.assertFalse(plan.is_feasible)


class ValidationTest(unittest.TestCase):
    """Tests for the deterministic validation pipeline."""

    def setUp(self) -> None:
        self.mission = build_eastside_mission()
        self.volunteers = build_volunteers()
        self.vehicles = [build_church_van()]

    def test_valid_plan_passes(self) -> None:
        plan = build_valid_plan(self.mission)
        violations = validate_plan(plan, self.mission, self.volunteers, self.vehicles)
        # Only expected: travel-time warnings (Priya/Elena have estimates, Maya has estimate)
        blocking = [v for v in violations if v.severity == "blocking"]
        self.assertEqual(blocking, [], f"Unexpected blocking violations: {blocking}")

    def test_impossible_plan_no_driver_detected(self) -> None:
        plan = build_impossible_plan_no_driver(self.mission)
        violations = validate_plan(plan, self.mission, self.volunteers, self.vehicles)
        types = [v.constraint_type for v in violations]
        self.assertIn("no_eligible_driver", types)

    def test_impossible_plan_overlap_detected(self) -> None:
        plan = build_impossible_plan_overlap(self.mission)
        violations = validate_plan(plan, self.mission, self.volunteers, self.vehicles)
        types = [v.constraint_type for v in violations]
        self.assertIn("time_overlap", types)
        self.assertIn("driving_handling_overlap", types)

    def test_unknown_volunteer_detected(self) -> None:
        plan = build_valid_plan(self.mission)
        # Mutate: replace volunteer with non-existent ID
        plan.assignments[0].volunteer_id = "nonexistent"
        violations = validate_plan(plan, self.mission, self.volunteers, self.vehicles)
        types = [v.constraint_type for v in violations]
        self.assertIn("unknown_volunteer", types)

    def test_capability_gap_detected(self) -> None:
        plan = build_valid_plan(self.mission)
        # Assign Priya (food_handler) to driving task
        plan.assignments[0].volunteer_id = "priya"
        plan.assignments[0].vehicle_id = None  # remove van to isolate capability check
        violations = validate_plan(plan, self.mission, self.volunteers, self.vehicles)
        types = [v.constraint_type for v in violations]
        self.assertIn("capability_gap", types)

    def test_site_access_violation(self) -> None:
        # Build a plan where Maya (only authorized for eastside) is assigned
        # to a mission at a site she's not authorized for
        mission = build_eastside_mission()
        mission.destination_id = "harbor"  # Maya not authorized
        plan = build_valid_plan(mission)
        violations = validate_plan(plan, mission, self.volunteers, self.vehicles)
        types = [v.constraint_type for v in violations]
        # Maya and Elena are only authorized for eastside, Priya only for eastside
        self.assertIn("site_access", types)

    def test_dependency_order_violation(self) -> None:
        plan = build_valid_plan(self.mission)
        # Make handling start before driving ends (violates depends_on)
        drive_assignment = next(a for a in plan.assignments if a.task_id == "task-drive")
        handle_assignment = next(a for a in plan.assignments if a.task_id == "task-handle")
        # Swap windows so handling starts before driving
        handle_assignment.scheduled_window = TimeWindow(
            start=drive_assignment.scheduled_window.start,
            end=drive_assignment.scheduled_window.start + timedelta(hours=2),
        )
        violations = validate_plan(plan, self.mission, self.volunteers, self.vehicles)
        types = [v.constraint_type for v in violations]
        self.assertIn("dependency_order", types)

    def test_missing_travel_estimate_warning(self) -> None:
        # Remove travel estimates from a volunteer
        vols = build_volunteers()
        priya = next(v for v in vols if v.id == "priya")
        priya.travel_estimates = []
        plan = build_valid_plan(self.mission)
        violations = validate_plan(plan, self.mission, vols, self.vehicles)
        warnings = [v for v in violations if v.constraint_type == "missing_travel_estimate"]
        priya_warnings = [w for w in warnings if "priya" in w.affected_resource_ids]
        self.assertTrue(len(priya_warnings) > 0)

    def test_unknown_travel_time_warning(self) -> None:
        # Use Jordan (has unknown travel) in place of Maya
        vols = build_volunteers()
        jordan = next(v for v in vols if v.id == "jordan")
        jordan.authorized_site_ids = ["eastside"]
        jordan.opted_in = True
        plan = build_valid_plan(self.mission)
        plan.assignments[0].volunteer_id = "jordan"
        plan.assignments[0].vehicle_id = None  # Jordan not eligible
        violations = validate_plan(plan, self.mission, vols, self.vehicles)
        types = [v.constraint_type for v in violations]
        self.assertIn("unknown_travel_time", types)


class EventModelsTest(unittest.TestCase):

    def test_resource_unavailable_event(self) -> None:
        evt = build_maya_unavailable_event()
        self.assertEqual(evt.resource_id, "maya")
        self.assertEqual(evt.resource_type, "volunteer")

    def test_recovery_proposal(self) -> None:
        rp = build_recovery_proposal()
        self.assertEqual(rp.original_plan_id, "plan-valid-001")
        self.assertTrue(rp.requires_approval)
        self.assertTrue(rp.proposed_plan.is_feasible)

    def test_mission_events(self) -> None:
        events = build_sample_mission_events()
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].kind, EventKind.PLAN_PROPOSED)

    def test_approval_record(self) -> None:
        ar = ApprovalRecord(
            plan_id="plan-valid-001",
            decision="approved",
            decided_by="coordinator@example.com",
            reason="Looks good (SIMULATED)",
        )
        self.assertEqual(ar.decision, "approved")


class BackwardCompatibilityTest(unittest.TestCase):
    """Existing models remain unchanged and functional."""

    def test_original_mission_still_works(self) -> None:
        from app.mission import Mission, review_mission

        m = Mission(
            destination="Riverside Community Meals — Eastside",
            deadline=datetime(2026, 9, 10, 16, 0, 0, tzinfo=SIMULATED_TZ),
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
            constraints=["van certification required to drive"],
        )
        review = review_mission(m)
        self.assertEqual(review.status, "ready")

    def test_original_resource_still_works(self) -> None:
        from app.resources import Resource

        r = Resource(
            id="test-r", name="Test", category="driver",
            location="Test", status="available", availability=True,
            reliability=0.9, capacity=1, capacity_unit="site",
            capability_codes=["van_certified_driver"], opted_in=True,
        )
        self.assertEqual(r.id, "test-r")

    def test_original_solver_still_works(self) -> None:
        from app.resources import Resource
        from app.solver import CoalitionRequest, solve_resource_coalition

        resources = [
            Resource(
                id="driver-1", name="Driver 1", category="driver",
                location="Test", status="available", availability=True,
                reliability=0.9, capability_codes=["van_certified_driver"],
                opted_in=True,
            ),
        ]
        sol = solve_resource_coalition(
            CoalitionRequest(required_capabilities=["van_certified_driver"]),
            resources=resources,
        )
        self.assertTrue(sol.feasible)

    def test_original_orchestration_still_works(self) -> None:
        from app.mission import Mission
        from app.orchestration import run_pipeline
        from app.resources import Resource

        mission = Mission(
            destination="Test Site",
            incident_type="thursday_distribution",
        )
        resources = [
            Resource(
                id="d1", name="D1", category="driver", location="A",
                status="available", availability=True, reliability=0.9,
                capability_codes=["van_certified_driver"], opted_in=True,
            ),
            Resource(
                id="h1", name="H1", category="food handler", location="A",
                status="available", availability=True, reliability=0.9,
                capability_codes=["food_handler"], opted_in=True,
            ),
            Resource(
                id="k1", name="K1", category="keyholder", location="A",
                status="available", availability=True, reliability=0.9,
                capability_codes=["site_keyholder"], opted_in=True,
            ),
        ]
        result = run_pipeline(
            mission, resources=resources,
            include_resilience=False, include_hypergraph=False,
        )
        self.assertEqual(result.verdict, "ready to deploy")


class SerializationTest(unittest.TestCase):
    """All new models roundtrip through JSON serialization."""

    def test_mission_spec_roundtrip(self) -> None:
        m = build_eastside_mission()
        data = m.model_dump(mode="json")
        self.assertIsInstance(data, dict)
        m2 = MissionSpec.model_validate(data)
        self.assertEqual(m.id, m2.id)

    def test_volunteer_spec_roundtrip(self) -> None:
        vols = build_volunteers()
        for v in vols:
            data = v.model_dump(mode="json")
            v2 = VolunteerSpec.model_validate(data)
            self.assertEqual(v.id, v2.id)

    def test_vehicle_spec_roundtrip(self) -> None:
        van = build_church_van()
        data = van.model_dump(mode="json")
        v2 = VehicleSpec.model_validate(data)
        self.assertEqual(van.id, v2.id)

    def test_plan_spec_roundtrip(self) -> None:
        plan = build_valid_plan()
        data = plan.model_dump(mode="json")
        p2 = PlanSpec.model_validate(data)
        self.assertEqual(plan.id, p2.id)
        self.assertEqual(len(plan.assignments), len(p2.assignments))

    def test_constraint_violation_roundtrip(self) -> None:
        cv = ConstraintViolation(
            constraint_type="test",
            description="Test violation",
            affected_resource_ids=["a"],
        )
        data = cv.model_dump(mode="json")
        cv2 = ConstraintViolation.model_validate(data)
        self.assertEqual(cv.constraint_type, cv2.constraint_type)


if __name__ == "__main__":
    unittest.main()
