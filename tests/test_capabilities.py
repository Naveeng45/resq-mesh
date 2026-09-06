from __future__ import annotations

import unittest

from app.capabilities import derive_required_capabilities, resolve_capability_code
from app.mission import Mission


class CapabilityRulesTest(unittest.TestCase):
    def test_thursday_distribution_maps_requests_to_roles(self) -> None:
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            deadline="2026-09-10T16:00:00-07:00",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
            constraints=["van certification required to drive"],
        )

        assessment = derive_required_capabilities(mission)

        self.assertEqual(
            [capability.code for capability in assessment.required_capabilities],
            ["van_certified_driver", "food_handler", "site_keyholder"],
        )
        self.assertEqual(
            assessment.rule_required_capability_codes,
            ["van_certified_driver", "food_handler", "site_keyholder"],
        )
        self.assertEqual(assessment.comparison_status, "aligned")
        self.assertFalse(assessment.needs_human_review)

    def test_doctrine_supplies_the_roles_when_the_coordinator_names_none(self) -> None:
        """The rules decide which roles a site needs, not the request wording."""

        mission = Mission(
            destination="Riverside Community Meals — Harbor",
            incident_type="thursday_distribution",
        )

        assessment = derive_required_capabilities(mission)

        self.assertEqual(
            set(assessment.rule_required_capability_codes),
            {"van_certified_driver", "food_handler", "site_keyholder"},
        )
        self.assertEqual(assessment.llm_requested_capability_codes, [])
        for capability in assessment.required_capabilities:
            self.assertGreaterEqual(capability.confidence, 0.8)
        self.assertFalse(assessment.needs_human_review)

    def test_coverage_type_outside_doctrine_requires_human_review(self) -> None:
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            incident_type="holiday_popup",
        )

        assessment = derive_required_capabilities(mission)

        self.assertEqual(assessment.required_capabilities, [])
        self.assertTrue(assessment.needs_human_review)
        self.assertIn("not in deterministic doctrine", " ".join(assessment.review_reasons))

    def test_missing_coverage_type_requires_human_review(self) -> None:
        mission = Mission(
            destination="Riverside Community Meals — West End",
            incident_type=None,
            requirements=["someone to help"],
        )

        assessment = derive_required_capabilities(mission)

        self.assertEqual(assessment.required_capabilities, [])
        self.assertTrue(assessment.needs_human_review)
        self.assertIn("incident_type is missing", " ".join(assessment.review_reasons))

    def test_unmappable_request_is_surfaced_rather_than_guessed(self) -> None:
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
            requirements=["forklift operator"],
        )

        assessment = derive_required_capabilities(mission)

        self.assertTrue(assessment.needs_human_review)
        self.assertIn("forklift operator", " ".join(assessment.review_reasons))


class CapabilitySynonymTest(unittest.TestCase):
    def test_coordinator_language_resolves_to_ontology_codes(self) -> None:
        self.assertEqual(resolve_capability_code("van driver"), "van_certified_driver")
        self.assertEqual(resolve_capability_code("packer"), "food_handler")
        self.assertEqual(resolve_capability_code("site lead"), "site_keyholder")
        self.assertEqual(resolve_capability_code("Site keyholder"), "site_keyholder")

    def test_unknown_language_resolves_to_nothing(self) -> None:
        self.assertIsNone(resolve_capability_code("forklift operator"))


if __name__ == "__main__":
    unittest.main()
