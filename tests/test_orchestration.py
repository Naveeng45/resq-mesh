from __future__ import annotations

import unittest

from app.hypergraph import build_demo_hyperedges, build_demo_mission, build_demo_resources
from app.mission import Mission
from app.orchestration import render_report, run_pipeline
from app.resources import Resource


class OrchestrationPipelineTest(unittest.TestCase):
    def test_full_pipeline_wires_every_layer_on_the_demo_world(self) -> None:
        result = run_pipeline(
            build_demo_mission(),
            resources=build_demo_resources(),
            hyperedges=build_demo_hyperedges(),
            include_resilience=True,
            include_hypergraph=True,
            coalition_min_capacity=0,
        )

        # Mission -> Capabilities
        self.assertEqual(result.review.status, "ready")
        derived = {c.code for c in result.capability_assessment.required_capabilities}
        self.assertEqual(derived, {"van_certified_driver", "food_handler", "site_keyholder"})

        # Capabilities -> Coalition (CP-SAT)
        self.assertIsNotNone(result.coalition)
        self.assertTrue(result.coalition.feasible)
        self.assertEqual(set(result.coalition.selected_resource_ids), {"maya", "priya", "elena"})

        # Coalition -> Resilience (this minimal hypergraph fixture has no backups)
        self.assertIsNotNone(result.resilience)
        self.assertEqual(result.resilience.overall_classification, "mission_breaking")
        self.assertEqual(
            set(result.resilience.mission_breaking_failure_ids),
            {"maya", "priya", "elena"},
        )

        # Coalition -> Hypergraph (same coalition, mapped to a hyperedge)
        self.assertIsNotNone(result.hypergraph)
        self.assertEqual(result.hypergraph.selected_hyperedge.id, "eastside_meal_delivery")
        emergent = {c.code for c in result.hypergraph.emergent_capabilities}
        self.assertIn("meal_delivery", emergent)

        self.assertEqual(result.verdict, "ready but fragile")
        self.assertTrue(result.answers["CAN"].startswith("Yes"))

    def test_missing_facts_short_circuits_before_the_solver(self) -> None:
        result = run_pipeline(Mission(), include_hypergraph=True, hyperedges=build_demo_hyperedges())

        self.assertEqual(result.review.status, "needs_clarification")
        self.assertIsNone(result.coalition)
        self.assertIsNone(result.resilience)
        self.assertIsNone(result.hypergraph)
        self.assertEqual(result.verdict, "needs more facts")

    def test_infeasible_coalition_reports_missing_capability(self) -> None:
        no_driver = [
            Resource(
                id="sam",
                name="Sam Ortiz",
                category="food handler",
                location="Eastside",
                status="available",
                availability=True,
                reliability=0.9,
                capacity=1,
                capacity_unit="site",
                capability_codes=["food_handler"],
                opted_in=True,
                org="Riverside Church",
            ),
            Resource(
                id="elena",
                name="Elena Brooks",
                category="site keyholder",
                location="Eastside",
                status="available",
                availability=True,
                reliability=0.9,
                capacity=1,
                capacity_unit="site",
                capability_codes=["site_keyholder"],
                opted_in=True,
                org="Riverside Church",
            ),
        ]
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            deadline="2026-09-10T16:00:00-07:00",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
        )

        result = run_pipeline(mission, resources=no_driver, coalition_min_capacity=0)

        self.assertIsNotNone(result.coalition)
        self.assertFalse(result.coalition.feasible)
        self.assertIsNone(result.resilience)
        self.assertIsNone(result.hypergraph)
        self.assertEqual(result.verdict, "no feasible coalition")
        self.assertIn("van_certified_driver", result.missing_capabilities)
        self.assertIn("Van-certified driver", result.answers["WHAT IS MISSING"])

    def test_render_report_is_a_scannable_string(self) -> None:
        result = run_pipeline(
            build_demo_mission(),
            resources=build_demo_resources(),
            hyperedges=build_demo_hyperedges(),
        )
        text = render_report(result)

        self.assertIn("=== MealMesh ===", text)
        self.assertIn("Coalition:", text)
        self.assertIn("Verdict:", text)


if __name__ == "__main__":
    unittest.main()
