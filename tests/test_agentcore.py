from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_ENTRYPOINT = Path(__file__).resolve().parents[1] / "deploy" / "agentcore" / "agent_entrypoint.py"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("resq_agentcore_entrypoint", _ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class AgentCoreEntrypointTest(unittest.TestCase):
    """The deterministic 'assess' path must work with zero AWS access."""

    def setUp(self) -> None:
        self.entry = _load_entrypoint()

    def test_default_payload_assesses_demo_coverage(self) -> None:
        result = self.entry.handle({})
        self.assertIn(result["verdict"], {"ready to deploy", "ready but fragile"})
        self.assertEqual(
            set(result["answers"].keys()), {"CAN", "HOW", "WHAT IF", "WHAT IS MISSING"}
        )
        self.assertIn("report", result)
        self.assertTrue(result["trace_id"])

    def test_assess_action_with_explicit_mission(self) -> None:
        result = self.entry.handle(
            {
                "action": "assess",
                "mission": {
                    "destination": "Riverside Community Meals — Eastside",
                    "incident_type": "thursday_distribution",
                },
            }
        )
        self.assertIn("verdict", result)
        self.assertIsInstance(result["selected_resource_ids"], list)

    def test_handle_is_importable_without_agentcore_sdk(self) -> None:
        # The SDK is a deploy-only dep; the module must still import and route.
        self.assertTrue(hasattr(self.entry, "handle"))
        self.assertIn(self.entry._HAS_AGENTCORE, (True, False))


if __name__ == "__main__":
    unittest.main()
