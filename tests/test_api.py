from __future__ import annotations

import unittest

from app.api.scenario import PRESET_MISSIONS, build_catalog, scenario_payload, site_roster_ids
from app.api.server import PlanRequest, get_scenario, get_sentinel, post_plan


def _eastside_mission() -> dict:
    return next(p for p in PRESET_MISSIONS if p["id"] == "thursday_eastside")["mission"]


class ApiTest(unittest.TestCase):
    def test_scenario_payload_shape(self) -> None:
        payload = scenario_payload()
        self.assertTrue(payload["simulated"])
        self.assertEqual(len(payload["resources"]), 23)
        self.assertEqual(len(payload["destinations"]), 3)
        self.assertTrue(payload["hyperedges"])
        # every resource carries coordinates, a kind, and its site rosters
        site_ids = {destination["id"] for destination in payload["destinations"]}
        for resource in payload["resources"]:
            self.assertIn("lat", resource)
            self.assertIn("lng", resource)
            self.assertIn("kind", resource)
            self.assertTrue(resource["sites"])
            self.assertLessEqual(set(resource["sites"]), site_ids)

    def test_each_site_draws_on_its_own_roster(self) -> None:
        """A site may only be staffed by volunteers who signed up for it."""

        for preset in PRESET_MISSIONS:
            destination = preset["mission"]["destination"]
            roster = site_roster_ids(destination)
            self.assertIsNotNone(roster)
            self.assertEqual({r.id for r in build_catalog(destination=destination)}, roster)

            response = post_plan(PlanRequest(mission=preset["mission"], failed_resource_ids=[], min_capacity=0))
            result = response["result"]
            self.assertTrue(result["coalition"]["feasible"])
            self.assertLessEqual(set(result["coalition"]["selected_resource_ids"]), roster)

    def test_plan_initial_is_feasible(self) -> None:
        response = post_plan(PlanRequest(mission=_eastside_mission(), failed_resource_ids=[], min_capacity=0))
        result = response["result"]
        self.assertTrue(result["coalition"]["feasible"])
        self.assertEqual(result["verdict"], "ready to deploy")
        self.assertIsNotNone(response["destination"])

    def test_break_the_plan_recomposes_then_fails(self) -> None:
        mission = _eastside_mission()

        # Maya cancels -> the opted-in driver bench keeps Eastside feasible.
        one_down = post_plan(PlanRequest(mission=mission, failed_resource_ids=["maya"], min_capacity=0))
        self.assertTrue(one_down["result"]["coalition"]["feasible"])
        self.assertNotIn("maya", one_down["result"]["coalition"]["selected_resource_ids"])

        # Lose every opted-in driver on the Eastside roster -> infeasible with a
        # named missing role. Jordan is recruit-only, so he cannot fill the gap.
        all_drivers_down = post_plan(
            PlanRequest(
                mission=mission,
                failed_resource_ids=["maya", "luis", "avery", "gina"],
                min_capacity=0,
            )
        )
        result = all_drivers_down["result"]
        self.assertFalse(result["coalition"]["feasible"])
        self.assertEqual(result["verdict"], "no feasible coalition")
        self.assertIn("van_certified_driver", result["missing_capabilities"])

    def test_get_scenario_endpoint(self) -> None:
        self.assertEqual(get_scenario()["region"]["zoom"], scenario_payload()["region"]["zoom"])

    def test_sentinel_timeline_escalates_only_on_decisions(self) -> None:
        payload = get_sentinel()
        summary = payload["summary"]
        observations = payload["observations"]

        # the full monitoring narrative is returned for replay
        self.assertEqual(summary["total"], len(observations))
        self.assertEqual(summary["autonomous"] + summary["escalated"], summary["total"])

        # the point of the feature: most events are handled silently; only
        # genuine decisions escalate, and at least one does (infeasible mission).
        self.assertGreater(summary["autonomous"], summary["escalated"])
        self.assertGreaterEqual(summary["escalated"], 1)

        # an escalation only ever accompanies the "escalated" action, and it
        # carries a human-readable decision.
        for observation in observations:
            if observation["escalation"] is not None:
                self.assertEqual(observation["action"], "escalated")
                self.assertTrue(observation["escalation"]["decision_required"])

        # The human recruit restores coverage, though it may remain fragile.
        self.assertIn(observations[-1]["verdict"], {"ready to deploy", "ready but fragile"})

    def test_sentinel_reports_the_notification_channel_without_leaking_it(self) -> None:
        summary = get_sentinel()["summary"]
        notifications = summary["notifications"]

        self.assertIn(notifications["channel"], ("none", "slack", "webhook"))
        self.assertIn("min_severity", notifications)
        # the webhook URL must never reach the browser
        self.assertNotIn("http", str(notifications))

    def test_sentinel_replay_is_dry_run_and_delivers_nothing(self) -> None:
        payload = get_sentinel()

        self.assertTrue(payload["summary"]["notifications"]["dry_run"])
        self.assertEqual(payload["summary"]["delivered"], 0)
        for observation in payload["observations"]:
            notification = observation["notification"]
            self.assertEqual(notification is not None, observation["escalation"] is not None)
            if notification is not None:
                self.assertFalse(notification["delivered"])


if __name__ == "__main__":
    unittest.main()
