from __future__ import annotations

import unittest

import networkx as nx

from app.hypergraph import (
    CoalitionHyperedge,
    build_demo_hyperedges,
    build_demo_report,
    build_demo_resources,
    build_projection_graph,
    compute_lambda2,
    find_selected_hyperedge,
)
from app.resources import Resource
from app.solver import CoalitionRequest, solve_resource_coalition


class HypergraphTest(unittest.TestCase):
    def test_solver_coalition_maps_to_a_hyperedge(self) -> None:
        resources = build_demo_resources()
        request = CoalitionRequest(
            required_capabilities=["van_certified_driver", "food_handler", "site_keyholder"],
            minimum_total_capacity=0,
        )
        solution = solve_resource_coalition(request, resources=resources)
        hyperedges = build_demo_hyperedges()

        selected_hyperedge = find_selected_hyperedge(solution.selected_resource_ids, hyperedges)

        self.assertTrue(solution.feasible)
        self.assertIsNotNone(selected_hyperedge)
        self.assertEqual(selected_hyperedge.id, "eastside_meal_delivery")
        self.assertEqual(selected_hyperedge.resource_ids, ["maya", "priya", "elena"])

    def test_report_exposes_an_emergent_capability_owned_by_no_single_node(self) -> None:
        """Serving a meal is a property of the group, not of any volunteer."""

        report = build_demo_report()

        emergent_codes = [capability.code for capability in report.emergent_capabilities]
        owned_codes = {
            capability_code
            for resource in report.resources
            for capability_code in resource.capability_codes
        }

        self.assertIn("meal_delivery", emergent_codes)
        self.assertNotIn("meal_delivery", owned_codes)
        self.assertEqual(report.selected_hyperedge.id if report.selected_hyperedge else None, "eastside_meal_delivery")
        self.assertGreater(report.metrics.lambda2, 0.0)
        self.assertEqual(report.metrics.connected_components, 1)

    def test_lambda2_drops_to_zero_for_a_disconnected_projection(self) -> None:
        resources = [
            Resource(
                id="a",
                name="A",
                category="test",
                location="one",
                status="available",
                availability=True,
                reliability=1.0,
                capacity=1,
                capacity_unit="units",
                capability_codes=["cap_a"],
            ),
            Resource(
                id="b",
                name="B",
                category="test",
                location="two",
                status="available",
                availability=True,
                reliability=1.0,
                capacity=1,
                capacity_unit="units",
                capability_codes=["cap_b"],
            ),
            Resource(
                id="c",
                name="C",
                category="test",
                location="three",
                status="available",
                availability=True,
                reliability=1.0,
                capacity=1,
                capacity_unit="units",
                capability_codes=["cap_c"],
            ),
        ]
        hyperedges = [
            CoalitionHyperedge(
                id="pair_ab",
                mission_id="test_mission",
                mission_label="Test mission",
                resource_ids=["a", "b"],
                emergent_capability_code="ab_combo",
                emergent_capability_label="AB Combo",
                explanation="A and B together create a valid coalition unit.",
            )
        ]

        graph = build_projection_graph(resources, hyperedges)

        self.assertEqual(compute_lambda2(graph), 0.0)
        self.assertEqual(nx.number_connected_components(graph), 2)


if __name__ == "__main__":
    unittest.main()
