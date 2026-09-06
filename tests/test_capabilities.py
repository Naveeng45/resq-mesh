from __future__ import annotations

import unittest

from app.capabilities import derive_required_capabilities
from app.mission import Mission


class CapabilityRulesTest(unittest.TestCase):
    def test_known_flood_response_maps_requests_to_capabilities(self) -> None:
        mission = Mission(
            destination="Willow Creek",
            deadline="2026-09-06T18:00:00-07:00",
            incident_type="flood",
            requirements=["boat", "medical team"],
            constraints=["roads remain blocked"],
        )

        assessment = derive_required_capabilities(mission)

        self.assertEqual(
            [capability.code for capability in assessment.required_capabilities],
            ["flood_access", "field_triage"],
        )
        self.assertEqual(
            assessment.llm_requested_capability_codes,
            ["flood_access", "field_triage"],
        )
        self.assertEqual(
            assessment.rule_required_capability_codes,
            ["flood_access", "field_triage"],
        )
        self.assertEqual(assessment.comparison_status, "aligned")
        self.assertFalse(assessment.needs_human_review)

    def test_low_confidence_case_requires_human_review(self) -> None:
        mission = Mission(
            destination="East Clinic",
            deadline="2026-09-06T09:00:00-07:00",
            incident_type="flood",
            requirements=[],
            constraints=["roads remain blocked"],
        )

        assessment = derive_required_capabilities(mission)

        self.assertEqual(
            [capability.code for capability in assessment.required_capabilities],
            ["flood_access"],
        )
        self.assertLess(assessment.required_capabilities[0].confidence, 0.8)
        self.assertTrue(assessment.needs_human_review)
        self.assertIn("low-confidence", " ".join(assessment.review_reasons))

    def test_unknown_case_requires_human_review(self) -> None:
        mission = Mission(
            destination="Harbor Point",
            deadline="2026-09-06T12:00:00-07:00",
            incident_type=None,
            requirements=["send help"],
            constraints=[],
        )

        assessment = derive_required_capabilities(mission)

        self.assertEqual(assessment.required_capabilities, [])
        self.assertTrue(assessment.needs_human_review)
        self.assertIn("incident_type is missing", " ".join(assessment.review_reasons))


if __name__ == "__main__":
    unittest.main()
