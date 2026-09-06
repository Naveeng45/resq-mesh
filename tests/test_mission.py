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

    def test_valid_mission_is_ready(self) -> None:
        example = next(item for item in self.examples if item["id"] == "valid_flood_response")
        mission = Mission.model_validate(example["mission"])

        self.assertEqual(review_mission(mission).model_dump(), example["review"])
        self.assertEqual(mission.destination, "Willow Creek")
        self.assertEqual(mission.incident_type, "flood")

    def test_ambiguous_mission_flags_missing_fields(self) -> None:
        example = next(item for item in self.examples if item["id"] == "ambiguous_destination")
        mission = Mission.model_validate(example["mission"])

        review = review_mission(mission)
        self.assertEqual(review.model_dump(), example["review"])
        self.assertIsNone(mission.destination)
        self.assertIsNone(mission.deadline)

    def test_incomplete_mission_flags_deadline(self) -> None:
        example = next(item for item in self.examples if item["id"] == "incomplete_deadline")
        mission = Mission.model_validate(example["mission"])

        review = review_mission(mission)
        self.assertEqual(review.model_dump(), example["review"])
        self.assertEqual(review.missing_critical_facts, ["deadline"])


if __name__ == "__main__":
    unittest.main()

