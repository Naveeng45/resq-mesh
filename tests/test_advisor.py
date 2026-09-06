from __future__ import annotations

import os
import unittest
import urllib.request
from unittest import mock

from app.advisor import ADVISOR_TOOLS, _strip_thinking, build_advisor
from app.mission_agent import ensure_aws_proxy_bypass
from app.tools import (
    assess_incident,
    get_available_resources,
    get_resources_by_required_capability,
)


class AssessIncidentToolTest(unittest.TestCase):
    """The tool the Advisor calls must make the decision deterministically."""

    def test_thursday_eastside_is_feasible(self) -> None:
        decision = assess_incident(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
        )
        self.assertIn(decision["verdict"], {"ready to deploy", "ready but fragile"})
        self.assertTrue(decision["selected_resource_ids"])
        self.assertEqual(decision["missing_capabilities"], [])
        self.assertIn("CAN", decision["answers"])

    def test_answers_cover_the_four_questions(self) -> None:
        decision = assess_incident(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
        )
        self.assertEqual(
            set(decision["answers"].keys()), {"CAN", "HOW", "WHAT IF", "WHAT IS MISSING"}
        )

    def test_capability_lookup_excludes_unavailable(self) -> None:
        drivers = get_resources_by_required_capability("van_certified_driver")
        ids = [r["id"] for r in drivers["resources"]]
        self.assertIn("luis", ids)
        self.assertNotIn("jordan", ids)

    def test_available_resources_are_all_available(self) -> None:
        payload = get_available_resources()
        for resource in payload["resources"]:
            self.assertTrue(resource["availability"])
            self.assertEqual(resource["status"], "available")
            self.assertTrue(resource["opted_in"])


class AdvisorWiringTest(unittest.TestCase):
    """The agent must actually register the tools (offline; no Bedrock call)."""

    def test_advisor_registers_all_tools(self) -> None:
        agent = build_advisor()
        names = set(agent.tool_names)
        self.assertIn("assess_incident", names)
        self.assertIn("get_available_resources", names)
        self.assertIn("get_resources_by_required_capability", names)

    def test_advisor_tool_list_matches(self) -> None:
        self.assertEqual(len(ADVISOR_TOOLS), 3)


class ProxyBypassTest(unittest.TestCase):
    """Adding the AWS bypass must not drop entries that were already there.

    ``urllib`` folds NO_PROXY and no_proxy into one lower-cased dict, so writing
    only one of them can silently route localhost / intranet traffic (including
    Sentinel escalation webhooks) through an intercepting corporate proxy.
    """

    def test_existing_entries_survive_and_both_vars_agree(self) -> None:
        with mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost"}, clear=False):
            os.environ.pop("no_proxy", None)

            ensure_aws_proxy_bypass()

            self.assertEqual(os.environ["NO_PROXY"], os.environ["no_proxy"])
            entries = os.environ["NO_PROXY"].split(",")
            self.assertIn("127.0.0.1", entries)
            self.assertIn("localhost", entries)
            self.assertIn(".amazonaws.com", entries)

    def test_localhost_is_still_bypassed_after_the_call(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"HTTP_PROXY": "http://proxy.invalid:8080", "NO_PROXY": "127.0.0.1,localhost"},
            clear=False,
        ):
            os.environ.pop("no_proxy", None)

            ensure_aws_proxy_bypass()

            self.assertTrue(urllib.request.proxy_bypass("127.0.0.1"))

    def test_is_idempotent(self) -> None:
        with mock.patch.dict(os.environ, {"NO_PROXY": "localhost"}, clear=False):
            os.environ.pop("no_proxy", None)

            ensure_aws_proxy_bypass()
            ensure_aws_proxy_bypass()

            self.assertEqual(os.environ["NO_PROXY"].count(".amazonaws.com"), 1)


class StripThinkingTest(unittest.TestCase):
    """Model reasoning tags must never leak into the shown answer."""

    def test_removes_thinking_block(self) -> None:
        raw = "<thinking>internal reasoning here</thinking>The mission is feasible."
        self.assertEqual(_strip_thinking(raw), "The mission is feasible.")

    def test_removes_stray_tags(self) -> None:
        self.assertEqual(_strip_thinking("<thinking>only reasoning"), "only reasoning")

    def test_passes_clean_text_through(self) -> None:
        self.assertEqual(_strip_thinking("Ready but fragile."), "Ready but fragile.")


if __name__ == "__main__":
    unittest.main()
