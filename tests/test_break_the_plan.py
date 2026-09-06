from __future__ import annotations

import unittest

from app.break_the_plan import render_break_the_plan, run_break_the_plan

DRIVER_IDS = {"maya", "luis"}


class BreakThePlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.steps = run_break_the_plan()

    def test_three_steps_initial_recompose_break(self) -> None:
        self.assertEqual(len(self.steps), 3)

    def test_initial_plan_covers_all_three_roles(self) -> None:
        initial = self.steps[0]
        self.assertIsNone(initial.failed_resource_id)
        self.assertTrue(initial.solution.feasible)
        selected = set(initial.solution.selected_resource_ids)
        self.assertIn("priya", selected)
        self.assertIn("elena", selected)
        self.assertEqual(len(selected & DRIVER_IDS), 1)

    def test_first_cancel_recomposes_onto_the_other_driver(self) -> None:
        initial_driver = (set(self.steps[0].solution.selected_resource_ids) & DRIVER_IDS).pop()
        recomposed = self.steps[1]
        self.assertEqual(recomposed.failed_resource_id, initial_driver)
        self.assertTrue(recomposed.solution.feasible)
        selected = set(recomposed.solution.selected_resource_ids)
        self.assertEqual(selected & DRIVER_IDS, DRIVER_IDS - {initial_driver})
        self.assertNotIn(initial_driver, selected)

    def test_second_failure_is_infeasible_and_names_missing_capability(self) -> None:
        broken = self.steps[2]
        self.assertIn(broken.failed_resource_id, DRIVER_IDS)
        self.assertFalse(broken.solution.feasible)
        self.assertEqual(broken.missing_capabilities, ["van_certified_driver"])

    def test_render_contains_the_headline_and_missing_capability(self) -> None:
        text = render_break_the_plan(self.steps)
        self.assertIn("BREAK THE PLAN", text)
        self.assertIn("Missing capability: Van-certified driver", text)


if __name__ == "__main__":
    unittest.main()
