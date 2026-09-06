from __future__ import annotations

import unittest

from app.mission import Mission
from app.resources import Resource
from app.sentinel import (
    Sentinel,
    WorldEvent,
    apply_event,
    build_demo_mission,
    build_demo_resources,
    render_sentinel_log,
    run_sentinel_demo,
)


def _driver(resource_id: str) -> Resource:
    return Resource(
        id=resource_id, name=resource_id, category="driver", location="Meal program",
        status="available", availability=True, reliability=0.9,
        capacity=1, capacity_unit="site", capability_codes=["van_certified_driver"],
        opted_in=True, org="Test org",
    )


def _handler(resource_id: str) -> Resource:
    return Resource(
        id=resource_id, name=resource_id, category="food handler", location="Meal program",
        status="available", availability=True, reliability=0.9,
        capacity=1, capacity_unit="site", capability_codes=["food_handler"],
        opted_in=True, org="Test org",
    )


def _keyholder(resource_id: str) -> Resource:
    return Resource(
        id=resource_id, name=resource_id, category="site keyholder", location="Meal program",
        status="available", availability=True, reliability=0.9,
        capacity=1, capacity_unit="site", capability_codes=["site_keyholder"],
        opted_in=True, org="Test org",
    )


class ApplyEventTest(unittest.TestCase):
    def test_offline_is_pure_and_marks_unavailable(self) -> None:
        catalog = [_driver("driver-1")]
        updated = apply_event(catalog, WorldEvent(kind="resource_offline", resource_id="driver-1"))
        self.assertTrue(catalog[0].availability)  # input untouched
        self.assertFalse(updated[0].availability)
        self.assertEqual(updated[0].status, "offline")

    def test_resource_added_appends(self) -> None:
        catalog = [_driver("driver-1")]
        updated = apply_event(catalog, WorldEvent(kind="resource_added", resource=_driver("driver-2")))
        self.assertEqual({r.id for r in updated}, {"driver-1", "driver-2"})


class SentinelPolicyTest(unittest.TestCase):
    def _sentinel(self, resources: list[Resource]) -> Sentinel:
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
        )
        if not any("site_keyholder" in resource.capability_codes for resource in resources):
            resources = resources + [_keyholder("k1"), _keyholder("k2")]
        return Sentinel(mission, resources, coalition_min_capacity=0)

    def test_baseline_healthy_is_silent(self) -> None:
        sentinel = self._sentinel([_driver("d1"), _driver("d2"), _handler("h1"), _handler("h2")])
        observation = sentinel.assess_baseline()
        self.assertEqual(observation.verdict, "ready to deploy")
        self.assertEqual(observation.action, "silent")
        self.assertIsNone(observation.escalation)

    def test_recruit_only_volunteer_never_reaches_solver(self) -> None:
        opted_driver = _driver("opted-driver")
        recruit_only = _driver("recruit-only")
        recruit_only.opted_in = False
        sentinel = self._sentinel(
            [opted_driver, recruit_only, _handler("h1"), _handler("h2")]
        )

        observation = sentinel.assess_baseline()

        self.assertIn("opted-driver", observation.selected_resource_ids)
        self.assertNotIn("recruit-only", observation.selected_resource_ids)

    def test_absorbable_loss_recomposes_silently(self) -> None:
        sentinel = self._sentinel([_driver("d1"), _driver("d2"), _driver("d3"), _handler("h1"), _handler("h2")])
        sentinel.assess_baseline()
        active_driver = sentinel.current_selected_of_capability("van_certified_driver")

        observation = sentinel.observe(WorldEvent(kind="resource_offline", resource_id=active_driver))
        self.assertEqual(observation.verdict, "ready to deploy")
        self.assertEqual(observation.action, "auto_recomposed")
        self.assertIsNone(observation.escalation)
        self.assertNotIn(active_driver, observation.selected_resource_ids)

    def test_losing_redundancy_escalates_as_fragile_warning(self) -> None:
        sentinel = self._sentinel([_driver("d1"), _driver("d2"), _handler("h1"), _handler("h2")])
        sentinel.assess_baseline()
        active_driver = sentinel.current_selected_of_capability("van_certified_driver")

        observation = sentinel.observe(WorldEvent(kind="resource_offline", resource_id=active_driver))
        self.assertEqual(observation.verdict, "ready but fragile")
        self.assertEqual(observation.action, "escalated")
        self.assertIsNotNone(observation.escalation)
        self.assertEqual(observation.escalation.severity, "warning")

    def test_losing_all_of_capability_escalates_critical_with_missing(self) -> None:
        sentinel = self._sentinel([_driver("d1"), _handler("h1"), _handler("h2")])
        sentinel.assess_baseline()

        observation = sentinel.observe(WorldEvent(kind="resource_offline", resource_id="d1"))
        self.assertEqual(observation.verdict, "no feasible coalition")
        self.assertEqual(observation.action, "escalated")
        self.assertEqual(observation.escalation.severity, "critical")
        self.assertIn("van_certified_driver", observation.escalation.missing_capabilities)

    def test_no_repeat_escalation_while_staying_in_same_bad_tier(self) -> None:
        sentinel = self._sentinel([_driver("d1"), _handler("h1"), _handler("h2")])
        sentinel.assess_baseline()

        first = sentinel.observe(WorldEvent(kind="resource_offline", resource_id="d1"))
        self.assertEqual(first.action, "escalated")  # became infeasible

        # A further unrelated loss keeps it infeasible - no new decision needed.
        second = sentinel.observe(WorldEvent(kind="resource_offline", resource_id="h1"))
        self.assertEqual(second.verdict, "no feasible coalition")
        self.assertEqual(second.action, "silent")
        self.assertIsNone(second.escalation)

    def test_recovery_reports_resolved(self) -> None:
        sentinel = self._sentinel([_driver("d1"), _driver("d2"), _handler("h1"), _handler("h2")])
        sentinel.assess_baseline()  # fully redundant -> ready to deploy
        active_driver = sentinel.current_selected_of_capability("van_certified_driver")

        degraded = sentinel.observe(WorldEvent(kind="resource_offline", resource_id=active_driver))
        self.assertEqual(degraded.verdict, "ready but fragile")

        recovered = sentinel.observe(WorldEvent(kind="resource_online", resource_id=active_driver))
        self.assertEqual(recovered.verdict, "ready to deploy")
        self.assertEqual(recovered.action, "resolved")


class SentinelDemoTest(unittest.TestCase):
    def test_demo_tells_the_full_arc(self) -> None:
        observations = run_sentinel_demo()
        actions = [o.action for o in observations]
        # silent absorb happens before the first escalation
        self.assertIn("auto_recomposed", actions)
        self.assertIn("escalated", actions)
        self.assertIn(actions[-1], {"improved", "resolved"})

    def test_demo_has_a_critical_infeasible_escalation(self) -> None:
        observations = run_sentinel_demo()
        criticals = [o for o in observations if o.escalation and o.escalation.severity == "critical"]
        self.assertTrue(criticals)
        self.assertIn("van_certified_driver", criticals[0].escalation.missing_capabilities)
        self.assertIn("Ask Jordan", criticals[0].escalation.decision_required)

    def test_render_contains_headline_and_summary(self) -> None:
        text = render_sentinel_log(run_sentinel_demo())
        self.assertIn("MealMesh SENTINEL", text)
        self.assertIn("DECISION NEEDED", text)
        self.assertIn("handled autonomously", text)

    def test_demo_builders_are_consistent(self) -> None:
        self.assertEqual(build_demo_mission().incident_type, "thursday_distribution")
        self.assertEqual(len(build_demo_resources()), 9)

    def test_demo_hits_four_autonomous_two_escalated(self) -> None:
        observations = run_sentinel_demo()
        escalated = sum(observation.escalation is not None for observation in observations)
        self.assertEqual((len(observations) - escalated, escalated), (4, 2))


if __name__ == "__main__":
    unittest.main()
