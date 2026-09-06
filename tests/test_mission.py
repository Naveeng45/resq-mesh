from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.mission import Mission, review_mission


EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "examples" / "structured_missions.json"


class MissionStructuredOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.examples = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))

    def test_examples_file_has_five_entries(self) -> None:
        self.assertEqual(len(self.examples), 5)

    def test_valid_coverage_request_is_ready(self) -> None:
        example = next(item for item in self.examples if item["id"] == "valid_thursday_eastside")
        mission = Mission.model_validate(example["mission"])

        self.assertEqual(review_mission(mission).model_dump(), example["review"])
        self.assertEqual(mission.destination, "Riverside Community Meals — Eastside")
        self.assertEqual(mission.incident_type, "thursday_distribution")

    def test_ambiguous_site_flags_the_missing_site(self) -> None:
        example = next(item for item in self.examples if item["id"] == "ambiguous_site")
        mission = Mission.model_validate(example["mission"])

        review = review_mission(mission)
        self.assertEqual(review.model_dump(), example["review"])
        self.assertIsNone(mission.destination)
        self.assertEqual(review.missing_critical_facts, ["destination"])

    def test_missing_service_time_is_still_plannable(self) -> None:
        """"Thursday at Harbor" is enough to derive roles and solve."""

        example = next(item for item in self.examples if item["id"] == "incomplete_deadline")
        mission = Mission.model_validate(example["mission"])

        review = review_mission(mission)
        self.assertEqual(review.model_dump(), example["review"])
        self.assertIsNone(mission.deadline)
        self.assertEqual(review.status, "ready")

    def test_missing_coverage_window_needs_clarification(self) -> None:
        example = next(item for item in self.examples if item["id"] == "missing_coverage_window")
        mission = Mission.model_validate(example["mission"])

        review = review_mission(mission)
        self.assertEqual(review.model_dump(), example["review"])
        self.assertEqual(review.missing_critical_facts, ["incident_type"])

    def test_extraction_keeps_constraints_as_stated_facts(self) -> None:
        example = next(item for item in self.examples if item["id"] == "ready_with_constraints")
        mission = Mission.model_validate(example["mission"])

        self.assertEqual(review_mission(mission).status, "ready")
        self.assertIn("Maya is unavailable", mission.constraints)


if __name__ == "__main__":
    unittest.main()
