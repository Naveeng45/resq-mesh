from __future__ import annotations

import unittest

from app.notifications import EscalationNotifier, NotificationSettings
from app.sentinel_agent import (
    INGESTABLE_EVENT_KINDS,
    SENTINEL_AGENT_SYSTEM_PROMPT,
    SENTINEL_AGENT_TOOLS,
    assess_coverage,
    build_sentinel_agent,
    get_session,
    ingest_event,
    notify_coordinator,
    start_session,
)

RECRUIT_ONLY_ID = "jordan"
EASTSIDE_OPTED_IN_DRIVERS = ("maya", "luis", "avery")


def _capturing_notifier() -> tuple[EscalationNotifier, list[dict]]:
    """A notifier that records payloads instead of reaching the network."""

    sent: list[dict] = []

    def sender(url: str, payload: dict) -> None:
        sent.append(payload)

    notifier = EscalationNotifier(
        settings=NotificationSettings(webhook_url="https://ops.example.org/hook", dry_run=False),
        sender=sender,
    )
    return notifier, sent


class SentinelToolBoundaryTest(unittest.TestCase):
    """CP-SAT must be reachable only through a tool, and only it may assign."""

    def setUp(self) -> None:
        start_session()

    def test_baseline_reports_a_covered_site(self) -> None:
        result = assess_coverage()

        self.assertEqual(result["verdict"], "ready to deploy")
        self.assertTrue(result["on_duty"])
        self.assertFalse(result["escalated"])
        self.assertTrue(result["synthetic_data"])

    def test_cancellation_is_backfilled_without_a_human(self) -> None:
        assess_coverage()

        result = ingest_event("resource_offline", "maya", note="Maya cancelled")

        self.assertIn(result["action"], {"silent", "auto_recomposed"})
        self.assertFalse(result["escalated"])
        self.assertNotIn("maya", result["on_duty"])
        self.assertTrue(result["on_duty"])

    def test_losing_every_opted_in_driver_escalates_and_names_the_role(self) -> None:
        assess_coverage()
        for driver in EASTSIDE_OPTED_IN_DRIVERS:
            result = ingest_event("resource_offline", driver)

        self.assertTrue(result["escalated"])
        self.assertEqual(result["verdict"], "no feasible coalition")
        self.assertIn("van_certified_driver", result["escalation"]["missing_capabilities"])
        self.assertIn("Van-certified driver", result["escalation"]["decision_required"])

    def test_recruit_only_volunteer_is_never_assigned_by_the_agent_path(self) -> None:
        """Consent survives the wrapper: Jordan is named, never scheduled."""

        assess_coverage()
        seen_on_duty: set[str] = set()
        for driver in EASTSIDE_OPTED_IN_DRIVERS:
            seen_on_duty.update(ingest_event("resource_offline", driver)["on_duty"])

        self.assertNotIn(RECRUIT_ONLY_ID, seen_on_duty)
        # ...but a human is told exactly who to ask.
        self.assertIn("Jordan", notify_coordinator()["decision_required"])


class SentinelGuardrailTest(unittest.TestCase):
    """The model must not be able to invent world state through these tools."""

    def setUp(self) -> None:
        start_session()
        assess_coverage()

    def test_unknown_volunteer_is_rejected_without_changing_the_plan(self) -> None:
        before = assess_coverage()["on_duty"]

        result = ingest_event("resource_offline", "alex")

        self.assertIn("unknown volunteer", result["error"])
        self.assertNotIn("action", result)
        self.assertEqual(assess_coverage()["on_duty"], before)

    def test_there_is_no_tool_for_adding_a_volunteer(self) -> None:
        self.assertNotIn("resource_added", INGESTABLE_EVENT_KINDS)

        result = ingest_event("resource_added", "someone_new")

        self.assertIn("unsupported event kind", result["error"])
        self.assertEqual(result["supported_kinds"], list(INGESTABLE_EVENT_KINDS))

    def test_system_prompt_forbids_choosing_or_inventing_people(self) -> None:
        prompt = SENTINEL_AGENT_SYSTEM_PROMPT.lower()

        self.assertIn("never choose", prompt)
        self.assertIn("never invent a volunteer", prompt)
        self.assertIn("simulated", prompt)

    def test_agent_exposes_exactly_the_three_deterministic_tools(self) -> None:
        names = {getattr(t, "__name__", getattr(t, "tool_name", "")) for t in SENTINEL_AGENT_TOOLS}

        self.assertEqual(names, {"assess_coverage", "ingest_event", "notify_coordinator"})

    def test_strands_agent_actually_registers_the_tools(self) -> None:
        """Offline wiring check: constructing the agent makes no network call."""

        agent = build_sentinel_agent()

        self.assertEqual(
            set(agent.tool_names), {"assess_coverage", "ingest_event", "notify_coordinator"}
        )


class NotifyCoordinatorTest(unittest.TestCase):
    """Alerts are raised by policy, not by the model's discretion."""

    def test_silent_handling_reports_no_alert(self) -> None:
        start_session()
        assess_coverage()

        ingest_event("resource_offline", "maya")
        report = notify_coordinator()

        self.assertFalse(report["pending_escalation"])
        self.assertIn("handled autonomously", report["detail"])

    def test_escalation_is_delivered_once_by_the_sentinel_not_the_model(self) -> None:
        notifier, sent = _capturing_notifier()
        start_session(notifier=notifier)
        assess_coverage()

        for driver in EASTSIDE_OPTED_IN_DRIVERS:
            ingest_event("resource_offline", driver)

        delivered_count = len(sent)
        self.assertGreaterEqual(delivered_count, 1)

        report = notify_coordinator()
        self.assertTrue(report["pending_escalation"])
        self.assertTrue(report["alert"]["delivered"])
        # Reporting the alert must not re-send it.
        notify_coordinator()
        self.assertEqual(len(sent), delivered_count)

    def test_tally_separates_autonomous_work_from_human_decisions(self) -> None:
        """Depth is absorbed silently; running out of depth is a human's call."""

        start_session()
        assess_coverage()

        first = ingest_event("resource_offline", "maya")
        self.assertFalse(first["escalated"])

        # Only Avery is left driving, so the site is covered but one cancellation
        # from closing — that is worth interrupting a human for.
        second = ingest_event("resource_offline", "luis")
        self.assertTrue(second["escalated"])
        self.assertEqual(second["verdict"], "ready but fragile")
        self.assertEqual(second["escalation"]["severity"], "warning")

        tally = get_session().tally()
        self.assertEqual(tally["observations"], 3)
        self.assertEqual(tally["handled_autonomously"], 2)
        self.assertEqual(tally["escalated_to_a_human"], 1)


if __name__ == "__main__":
    unittest.main()
