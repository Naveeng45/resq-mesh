from __future__ import annotations

import unittest

from app.resources import Resource
from app.solver import CoalitionRequest, solve_resource_coalition


class CoalitionSolverTest(unittest.TestCase):
    def test_solver_finds_minimal_feasible_coalition(self) -> None:
        resources = [
            Resource(
                id="boat-01",
                name="Flood Boat",
                category="water rescue",
                location="Dock A",
                status="available",
                availability=True,
                reliability=0.9,
                capacity=4,
                capacity_unit="people",
                capability_codes=["flood_access"],
            ),
            Resource(
                id="med-01",
                name="Medical Team",
                category="field care",
                location="Clinic",
                status="available",
                availability=True,
                reliability=0.95,
                capacity=6,
                capacity_unit="patients",
                capability_codes=["field_triage"],
            ),
            Resource(
                id="truck-01",
                name="Rescue Truck",
                category="ground transport",
                location="Depot",
                status="available",
                availability=True,
                reliability=0.98,
                capacity=12,
                capacity_unit="people",
                capability_codes=["flood_access", "field_triage"],
            ),
            Resource(
                id="boat-02",
                name="Spare Boat",
                category="water rescue",
                location="Dock B",
                status="maintenance",
                availability=False,
                reliability=0.5,
                capacity=4,
                capacity_unit="people",
                capability_codes=["flood_access"],
            ),
        ]

        solution = solve_resource_coalition(
            CoalitionRequest(
                required_capabilities=["flood_access", "field_triage"],
                minimum_total_capacity=10,
            ),
            resources=resources,
        )

        self.assertTrue(solution.feasible)
        self.assertEqual(solution.solver_status, "OPTIMAL")
        self.assertEqual(solution.selected_resource_ids, ["truck-01"])
        self.assertEqual(solution.selected_count, 1)
        self.assertEqual(solution.total_capacity, 12)
        self.assertEqual(
            solution.constraint_explanations,
            [
                "Availability constraint: resources marked unavailable are forced to zero, so the solver cannot select them.",
                "Required capabilities for this request: flood_access, field_triage",
                "Capability coverage constraint: every required capability must be covered by at least one selected resource.",
                "Requested minimum total capacity: 10.",
                "Capacity constraint: the coalition's total capacity must meet or exceed the requested minimum.",
                "Objective: among all feasible coalitions, choose the one with the fewest selected resources.",
            ],
        )

    def test_solver_returns_infeasible_when_capability_is_missing(self) -> None:
        resources = [
            Resource(
                id="truck-01",
                name="Rescue Truck",
                category="ground transport",
                location="Depot",
                status="available",
                availability=True,
                reliability=0.98,
                capacity=12,
                capacity_unit="people",
                capability_codes=["road_transport"],
            ),
        ]

        solution = solve_resource_coalition(
            CoalitionRequest(required_capabilities=["flood_access"], minimum_total_capacity=1),
            resources=resources,
        )

        self.assertFalse(solution.feasible)
        self.assertEqual(solution.solver_status, "INFEASIBLE")
        self.assertEqual(solution.selected_resources, [])
        self.assertEqual(solution.selected_resource_ids, [])
        self.assertIn("No resource in the catalog can provide", solution.infeasible_reason or "")

    def test_solver_returns_infeasible_when_only_matching_resource_is_unavailable(self) -> None:
        resources = [
            Resource(
                id="boat-01",
                name="Flood Boat",
                category="water rescue",
                location="Dock A",
                status="maintenance",
                availability=False,
                reliability=0.9,
                capacity=4,
                capacity_unit="people",
                capability_codes=["flood_access"],
            ),
        ]

        solution = solve_resource_coalition(
            CoalitionRequest(required_capabilities=["flood_access"], minimum_total_capacity=1),
            resources=resources,
        )

        self.assertFalse(solution.feasible)
        self.assertIn("hard constraints", solution.infeasible_reason or "")
        self.assertEqual(solution.selected_count, 0)


if __name__ == "__main__":
    unittest.main()
