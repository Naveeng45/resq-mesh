from __future__ import annotations

import unittest

from app.resources import Resource
from app.resilience import replan
from app.solver import CoalitionRequest, solve_resource_coalition


class ResilienceReplanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.resources = [
            Resource(
                id="flood-boat",
                name="Flood Boat",
                category="water rescue",
                location="Dock A",
                status="available",
                availability=True,
                reliability=0.93,
                capacity=4,
                capacity_unit="people",
                capability_codes=["flood_access"],
            ),
            Resource(
                id="med-team",
                name="Medical Team",
                category="field care",
                location="Clinic",
                status="available",
                availability=True,
                reliability=0.96,
                capacity=4,
                capacity_unit="patients",
                capability_codes=["field_triage"],
            ),
            Resource(
                id="comms-kit",
                name="Communications Kit",
                category="communications",
                location="Command Post",
                status="available",
                availability=True,
                reliability=0.91,
                capacity=1,
                capacity_unit="units",
                capability_codes=["communications"],
            ),
            Resource(
                id="backup-boat",
                name="Backup Flood Boat",
                category="water rescue",
                location="Dock B",
                status="available",
                availability=True,
                reliability=0.88,
                capacity=4,
                capacity_unit="people",
                capability_codes=["flood_access"],
            ),
            Resource(
                id="backup-med",
                name="Backup Medical Team",
                category="field care",
                location="Clinic B",
                status="available",
                availability=True,
                reliability=0.89,
                capacity=4,
                capacity_unit="patients",
                capability_codes=["field_triage"],
            ),
        ]
        self.request = CoalitionRequest(
            required_capabilities=["flood_access", "field_triage", "communications"],
            minimum_total_capacity=9,
        )

    def test_replan_marks_recoverable_and_mission_breaking_failures(self) -> None:
        baseline = solve_resource_coalition(self.request, resources=self.resources)

        self.assertTrue(baseline.feasible)
        self.assertEqual(baseline.selected_resource_ids, ["flood-boat", "med-team", "comms-kit"])

        report = replan(self.request, baseline, resources=self.resources)

        self.assertEqual(report.overall_classification, "mission_breaking")
        self.assertEqual(report.baseline_selected_resource_ids, ["flood-boat", "med-team", "comms-kit"])
        self.assertEqual(report.recoverable_failure_ids, ["flood-boat", "med-team"])
        self.assertEqual(report.mission_breaking_failure_ids, ["comms-kit"])
        self.assertEqual(len(report.scenarios), 3)

        flood_scenario = next(item for item in report.scenarios if item.failed_resource_id == "flood-boat")
        self.assertTrue(flood_scenario.recoverable)
        self.assertEqual(flood_scenario.classification, "recoverable")
        self.assertEqual(flood_scenario.replacement_selected_resource_ids, ["med-team", "comms-kit", "backup-boat"])
        self.assertEqual(flood_scenario.added_resource_ids, ["backup-boat"])
        self.assertEqual(flood_scenario.dropped_resource_ids, ["flood-boat"])

        comms_scenario = next(item for item in report.scenarios if item.failed_resource_id == "comms-kit")
        self.assertFalse(comms_scenario.recoverable)
        self.assertEqual(comms_scenario.classification, "mission_breaking")
        self.assertIn("communications", comms_scenario.unmet_capabilities)
        self.assertIsNone(comms_scenario.replacement_solution)
        self.assertIn("uncovered", comms_scenario.replacement_summary)

    def test_replan_requires_a_feasible_baseline(self) -> None:
        infeasible_baseline = solve_resource_coalition(
            CoalitionRequest(
                required_capabilities=["communications"],
                minimum_total_capacity=10,
            ),
            resources=[
                Resource(
                    id="comms-kit",
                    name="Communications Kit",
                    category="communications",
                    location="Command Post",
                    status="available",
                    availability=True,
                    reliability=0.91,
                    capacity=1,
                    capacity_unit="units",
                    capability_codes=["communications"],
                ),
            ],
        )

        self.assertFalse(infeasible_baseline.feasible)

        with self.assertRaises(ValueError):
            replan(self.request, infeasible_baseline, resources=self.resources)


if __name__ == "__main__":
    unittest.main()
