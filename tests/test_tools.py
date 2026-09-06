from __future__ import annotations

import unittest

from app.resources import (
    get_resources_by_required_capability,
    list_available_resources,
    list_recruit_candidates,
    list_resources,
)
from app.tools import (
    assess_incident,
    get_available_resources,
    get_resources_by_required_capability as get_resources_by_required_capability_tool,
)

RECRUIT_ONLY_IDS = {"jordan", "marcus", "tom"}


class AvailableResourceTest(unittest.TestCase):
    def test_returns_only_available_opted_in_records(self) -> None:
        payload = get_available_resources()

        self.assertTrue(payload["resources"])
        for resource in payload["resources"]:
            self.assertTrue(resource["availability"])
            self.assertEqual(resource["status"], "available")
            self.assertTrue(resource["opted_in"])
            self.assertTrue(resource["synthetic_data"])

    def test_recruit_only_volunteers_are_never_offered_to_the_solver(self) -> None:
        """The consent boundary: CP-SAT may only see people who opted in."""

        available_ids = {resource.id for resource in list_available_resources()}

        self.assertTrue(RECRUIT_ONLY_IDS.isdisjoint(available_ids))
        self.assertIn("maya", available_ids)

    def test_recruit_only_volunteers_still_exist_for_a_human_to_ask(self) -> None:
        all_ids = {resource.id for resource in list_resources()}
        self.assertTrue(RECRUIT_ONLY_IDS.issubset(all_ids))

        candidates = list_recruit_candidates("van_certified_driver")
        candidate_ids = {resource.id for resource in candidates}

        self.assertIn("jordan", candidate_ids)
        self.assertNotIn("maya", candidate_ids)
        for candidate in candidates:
            self.assertFalse(candidate.opted_in)


class CapabilityLookupTest(unittest.TestCase):
    def test_lookup_accepts_coordinator_language(self) -> None:
        payload = get_resources_by_required_capability_tool("van driver")
        ids = [resource["id"] for resource in payload["resources"]]

        self.assertEqual(payload["required_capability"], "van driver")
        self.assertIn("maya", ids)
        self.assertNotIn("jordan", ids)

    def test_lookup_excludes_people_who_did_not_opt_in(self) -> None:
        drivers = get_resources_by_required_capability("van_certified_driver")
        ids = {resource.id for resource in drivers}

        self.assertIn("luis", ids)
        self.assertTrue(RECRUIT_ONLY_IDS.isdisjoint(ids))

    def test_unknown_capability_returns_nothing(self) -> None:
        self.assertEqual(get_resources_by_required_capability("forklift"), [])


class AssessIncidentToolTest(unittest.TestCase):
    def test_tool_returns_a_decision_not_a_suggestion(self) -> None:
        decision = assess_incident(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
        )

        self.assertIn(decision["verdict"], {"ready to deploy", "ready but fragile"})
        self.assertTrue(decision["feasible"])
        self.assertTrue(decision["selected_resource_ids"])
        self.assertEqual(decision["missing_capabilities"], [])
        self.assertEqual(
            set(decision["answers"].keys()), {"CAN", "HOW", "WHAT IF", "WHAT IS MISSING"}
        )

    def test_coverage_type_outside_doctrine_is_escalated_not_planned(self) -> None:
        decision = assess_incident(
            destination="Riverside Community Meals — Eastside",
            incident_type="holiday_popup",
        )

        self.assertEqual(decision["verdict"], "needs human review")
        self.assertEqual(decision["selected_resource_ids"], [])


if __name__ == "__main__":
    unittest.main()
