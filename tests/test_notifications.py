from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.mission import Mission
from app.notifications import (
    EscalationNotifier,
    NotificationSettings,
    build_notifier,
    format_slack_payload,
    format_webhook_payload,
    preview_demo_notifications,
    render_text,
)
from app.resources import Resource
from app.sentinel import Escalation, Sentinel, WorldEvent, run_sentinel_demo

SLACK_URL = "https://hooks.slack.example/services/T000/B000/xxx"
WEBHOOK_URL = "https://meals.example.org/mealmesh/escalations"
MISSION_LABEL = "Riverside Community Meals — Eastside (thursday_distribution)"


class RecordingSender:
    """Test double for the transport: records calls, never touches the network."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.raises = raises

    def __call__(self, url: str, payload: dict) -> None:
        self.calls.append((url, payload))
        if self.raises is not None:
            raise self.raises


def _escalation(severity: str = "critical") -> Escalation:
    return Escalation(
        severity=severity,  # type: ignore[arg-type]
        verdict="no feasible coalition",
        triggered_by="Avery becomes unavailable",
        decision_required="Eastside would be uncovered. Ask Jordan, or call Second Harvest.",
        answers={"CAN": "No.", "WHAT IF": "Nothing left to lose."},
        missing_capabilities=["van_certified_driver"],
        trace_id="abc123def456",
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


class SettingsTest(unittest.TestCase):
    def test_unconfigured_reports_no_channel(self) -> None:
        settings = NotificationSettings(slack_webhook_url="", webhook_url="")
        self.assertEqual(settings.channel, "none")
        self.assertFalse(settings.configured)
        self.assertEqual(settings.target_url, "")

    def test_slack_wins_when_both_are_set(self) -> None:
        settings = NotificationSettings(slack_webhook_url=SLACK_URL, webhook_url=WEBHOOK_URL)
        self.assertEqual(settings.channel, "slack")
        self.assertEqual(settings.target_url, SLACK_URL)

    def test_describe_target_never_leaks_the_url(self) -> None:
        settings = NotificationSettings(slack_webhook_url=SLACK_URL, channel_label="#meal-coverage")
        described = EscalationNotifier(settings).describe()
        self.assertEqual(described["target"], "#meal-coverage")
        self.assertNotIn(SLACK_URL, str(described))


class PayloadFormattingTest(unittest.TestCase):
    def test_render_text_names_verdict_and_trigger(self) -> None:
        text = render_text(_escalation(), mission_label=MISSION_LABEL)
        self.assertIn(MISSION_LABEL, text)
        self.assertIn("no feasible coalition", text)
        self.assertIn("Avery becomes unavailable", text)

    def test_slack_payload_has_fallback_text_and_blocks(self) -> None:
        payload = format_slack_payload(_escalation(), mission_label=MISSION_LABEL)
        self.assertIn("text", payload)
        self.assertTrue(payload["blocks"])
        self.assertEqual(payload["blocks"][0]["type"], "header")
        rendered = str(payload)
        self.assertIn("van_certified_driver", rendered)
        self.assertIn("abc123def456", rendered)
        # The trust boundary is stated in the alert a human actually reads.
        self.assertIn("CP-SAT solver, not a language model", rendered)

    def test_slack_payload_omits_missing_capability_field_when_empty(self) -> None:
        escalation = _escalation("warning")
        escalation.missing_capabilities = []
        payload = format_slack_payload(escalation)
        self.assertNotIn("Missing capability", str(payload))

    def test_webhook_payload_is_machine_readable_and_marked_synthetic(self) -> None:
        payload = format_webhook_payload(_escalation(), mission_label=MISSION_LABEL)
        self.assertEqual(payload["source"], "mealmesh-sentinel")
        self.assertEqual(payload["severity"], "critical")
        self.assertEqual(payload["missing_capabilities"], ["van_certified_driver"])
        self.assertTrue(payload["synthetic_data"])

    def test_formatting_is_deterministic(self) -> None:
        first = format_webhook_payload(_escalation())
        second = format_webhook_payload(_escalation())
        self.assertEqual(first, second)


class NotifierDeliveryTest(unittest.TestCase):
    def test_unconfigured_is_a_silent_no_op(self) -> None:
        sender = RecordingSender()
        notifier = EscalationNotifier(NotificationSettings(slack_webhook_url="", webhook_url=""), sender=sender)

        result = notifier.notify(_escalation())

        self.assertFalse(result.delivered)
        self.assertEqual(result.status, "skipped_unconfigured")
        self.assertEqual(result.channel, "none")
        self.assertEqual(sender.calls, [])

    def test_slack_delivery_posts_block_kit_to_the_slack_url(self) -> None:
        sender = RecordingSender()
        notifier = EscalationNotifier(NotificationSettings(slack_webhook_url=SLACK_URL), sender=sender)

        result = notifier.notify(_escalation(), mission_label=MISSION_LABEL)

        self.assertTrue(result.delivered)
        self.assertEqual(result.status, "sent")
        self.assertEqual(result.channel, "slack")
        self.assertEqual(len(sender.calls), 1)
        url, payload = sender.calls[0]
        self.assertEqual(url, SLACK_URL)
        self.assertIn("blocks", payload)

    def test_generic_webhook_delivery_posts_the_json_shape(self) -> None:
        sender = RecordingSender()
        notifier = EscalationNotifier(NotificationSettings(webhook_url=WEBHOOK_URL), sender=sender)

        result = notifier.notify(_escalation())

        self.assertTrue(result.delivered)
        self.assertEqual(result.channel, "webhook")
        url, payload = sender.calls[0]
        self.assertEqual(url, WEBHOOK_URL)
        self.assertEqual(payload["type"], "escalation")

    def test_min_severity_threshold_suppresses_lower_severities(self) -> None:
        sender = RecordingSender()
        notifier = EscalationNotifier(
            NotificationSettings(slack_webhook_url=SLACK_URL, min_severity="critical"), sender=sender
        )

        suppressed = notifier.notify(_escalation("warning"))
        self.assertEqual(suppressed.status, "skipped_below_threshold")
        self.assertEqual(sender.calls, [])

        passed = notifier.notify(_escalation("critical"))
        self.assertEqual(passed.status, "sent")
        self.assertEqual(len(sender.calls), 1)

    def test_dry_run_renders_but_never_sends(self) -> None:
        sender = RecordingSender()
        notifier = EscalationNotifier(
            NotificationSettings(slack_webhook_url=SLACK_URL, dry_run=True), sender=sender
        )

        result = notifier.notify(_escalation())

        self.assertFalse(result.delivered)
        self.assertEqual(result.status, "dry_run")
        self.assertEqual(sender.calls, [])

    def test_transport_failure_is_swallowed_and_reported(self) -> None:
        sender = RecordingSender(raises=TimeoutError("connection timed out"))
        notifier = EscalationNotifier(NotificationSettings(webhook_url=WEBHOOK_URL), sender=sender)

        result = notifier.notify(_escalation())  # must not raise

        self.assertFalse(result.delivered)
        self.assertEqual(result.status, "failed")
        self.assertIn("TimeoutError", result.detail)

    def test_build_notifier_force_dry_run_overrides_config(self) -> None:
        sender = RecordingSender()
        notifier = build_notifier(sender, force_dry_run=True)
        notifier.settings = NotificationSettings(slack_webhook_url=SLACK_URL).model_copy(
            update={"dry_run": True}
        )

        result = notifier.notify(_escalation())

        self.assertEqual(result.status, "dry_run")
        self.assertEqual(sender.calls, [])


class SentinelWiringTest(unittest.TestCase):
    def _sentinel(self, resources: list[Resource], notifier: EscalationNotifier) -> Sentinel:
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
        )
        resources = resources + [_keyholder("k1"), _keyholder("k2")]
        return Sentinel(mission, resources, coalition_min_capacity=0, notifier=notifier)

    def _notifier(self, sender: RecordingSender) -> EscalationNotifier:
        return EscalationNotifier(NotificationSettings(webhook_url=WEBHOOK_URL), sender=sender)

    def test_mission_label_combines_destination_and_incident(self) -> None:
        sender = RecordingSender()
        sentinel = self._sentinel([_driver("d1"), _handler("h1")], self._notifier(sender))
        self.assertEqual(sentinel.mission_label, MISSION_LABEL)

    def test_silent_and_auto_recompose_send_nothing(self) -> None:
        sender = RecordingSender()
        sentinel = self._sentinel(
            [_driver("d1"), _driver("d2"), _driver("d3"), _handler("h1"), _handler("h2")],
            self._notifier(sender),
        )

        baseline = sentinel.assess_baseline()
        self.assertEqual(baseline.action, "silent")
        self.assertIsNone(baseline.notification)

        active = sentinel.current_selected_of_capability("van_certified_driver")
        recomposed = sentinel.observe(WorldEvent(kind="resource_offline", resource_id=active))

        self.assertEqual(recomposed.action, "auto_recomposed")
        self.assertIsNone(recomposed.notification)
        self.assertEqual(sender.calls, [])

    def test_escalation_delivers_exactly_one_alert(self) -> None:
        sender = RecordingSender()
        sentinel = self._sentinel(
            [_driver("d1"), _driver("d2"), _handler("h1"), _handler("h2")],
            self._notifier(sender),
        )
        self.assertEqual(sentinel.assess_baseline().action, "silent")  # healthy: sends nothing

        active = sentinel.current_selected_of_capability("van_certified_driver")
        observation = sentinel.observe(
            WorldEvent(kind="resource_offline", resource_id=active, note="driver cancellation")
        )

        self.assertEqual(observation.action, "escalated")
        self.assertIsNotNone(observation.notification)
        self.assertTrue(observation.notification.delivered)
        self.assertEqual(len(sender.calls), 1)
        _, payload = sender.calls[0]
        self.assertEqual(payload["severity"], "warning")
        self.assertEqual(payload["mission"], MISSION_LABEL)
        self.assertEqual(payload["triggered_by"], "driver cancellation")

    def test_repeat_degradation_in_the_same_tier_does_not_re_alert(self) -> None:
        sender = RecordingSender()
        sentinel = self._sentinel(
            [_driver("d1"), _driver("d2"), _handler("h1"), _handler("h2")],
            self._notifier(sender),
        )
        sentinel.assess_baseline()

        active = sentinel.current_selected_of_capability("van_certified_driver")
        first = sentinel.observe(WorldEvent(kind="resource_offline", resource_id=active))
        self.assertEqual(first.action, "escalated")  # became fragile

        # Losing a spare food handler keeps it fragile - no new decision, no new alert.
        second = sentinel.observe(WorldEvent(kind="resource_offline", resource_id="h1"))
        self.assertEqual(second.verdict, "ready but fragile")
        self.assertIsNone(second.notification)
        self.assertEqual(len(sender.calls), 1)

    def test_a_dead_channel_never_stops_monitoring(self) -> None:
        sender = RecordingSender(raises=ConnectionError("webhook unreachable"))
        sentinel = self._sentinel(
            [_driver("d1"), _driver("d2"), _handler("h1"), _handler("h2")],
            self._notifier(sender),
        )
        sentinel.assess_baseline()

        active = sentinel.current_selected_of_capability("van_certified_driver")
        observation = sentinel.observe(WorldEvent(kind="resource_offline", resource_id=active))

        self.assertEqual(observation.action, "escalated")
        self.assertFalse(observation.notification.delivered)
        self.assertEqual(observation.notification.status, "failed")

        # The loop keeps working: a recovery is still assessed correctly.
        recovered = sentinel.observe(WorldEvent(kind="resource_online", resource_id=active))
        self.assertEqual(recovered.verdict, "ready to deploy")
        self.assertEqual(recovered.action, "resolved")

    def test_default_sentinel_notifier_exists_and_leaks_no_url(self) -> None:
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
        )
        sentinel = Sentinel(
            mission,
            [_driver("d1"), _handler("h1"), _keyholder("k1")],
            coalition_min_capacity=0,
        )

        self.assertIsInstance(sentinel.notifier, EscalationNotifier)
        described = sentinel.notifier.describe()
        self.assertIn(described["channel"], ("none", "slack", "webhook"))
        self.assertNotIn("http", str(described))

    def test_explicitly_unconfigured_sentinel_sends_nothing_at_all(self) -> None:
        sender = RecordingSender()
        notifier = EscalationNotifier(NotificationSettings(slack_webhook_url="", webhook_url=""), sender=sender)
        mission = Mission(
            destination="Riverside Community Meals — Eastside",
            incident_type="thursday_distribution",
            requirements=["van driver", "packer", "site lead"],
        )
        sentinel = Sentinel(
            mission,
            [_driver("d1"), _handler("h1"), _keyholder("k1")],
            coalition_min_capacity=0,
            notifier=notifier,
        )

        sentinel.assess_baseline()
        observation = sentinel.observe(WorldEvent(kind="resource_offline", resource_id="d1"))

        self.assertEqual(observation.action, "escalated")
        self.assertEqual(observation.notification.status, "skipped_unconfigured")
        self.assertEqual(sender.calls, [])


class DemoAndPreviewTest(unittest.TestCase):
    def test_demo_notifies_only_on_escalations(self) -> None:
        sender = RecordingSender()
        notifier = EscalationNotifier(NotificationSettings(slack_webhook_url=SLACK_URL), sender=sender)

        observations = run_sentinel_demo(notifier=notifier)
        escalations = [o for o in observations if o.escalation is not None]
        notified = [o for o in observations if o.notification is not None]

        self.assertTrue(escalations)
        self.assertEqual(len(notified), len(escalations))
        self.assertEqual(len(sender.calls), len(escalations))

    def test_demo_replay_never_delivers_by_default(self) -> None:
        """A canned replay must never page a real human, however the env is set."""

        observations = run_sentinel_demo()
        delivered = [
            o for o in observations if o.notification is not None and o.notification.delivered
        ]
        self.assertEqual(delivered, [])

    def test_preview_runs_offline_and_shows_a_payload(self) -> None:
        text = preview_demo_notifications()
        self.assertIn("coverage notifications (preview)", text)
        self.assertIn("mealmesh-sentinel", text)
        self.assertIn("van_certified_driver", text)


class _CaptureHandler(BaseHTTPRequestHandler):
    """Loopback webhook receiver: records one JSON body and returns 200."""

    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0))
        type(self).received.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:  # silence test output
        return


class RealTransportTest(unittest.TestCase):
    """Exercises the *unmocked* urllib transport against a loopback server.

    Everything else mocks the sender, so this is the one test that proves the
    real delivery path works. It binds 127.0.0.1 on an ephemeral port and never
    touches the public network.
    """

    def setUp(self) -> None:
        _CaptureHandler.received = []
        self.server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_real_post_reaches_the_receiver(self) -> None:
        notifier = EscalationNotifier(NotificationSettings(webhook_url=self.url))

        result = notifier.notify(_escalation(), mission_label=MISSION_LABEL)

        self.assertTrue(result.delivered)
        self.assertEqual(result.status, "sent")
        self.assertEqual(len(_CaptureHandler.received), 1)
        body = _CaptureHandler.received[0]
        self.assertEqual(body["severity"], "critical")
        self.assertEqual(body["missing_capabilities"], ["van_certified_driver"])
        self.assertEqual(body["mission"], MISSION_LABEL)

    def test_unreachable_host_fails_softly(self) -> None:
        notifier = EscalationNotifier(
            NotificationSettings(webhook_url="http://127.0.0.1:1/dead", timeout_seconds=1.0)
        )

        result = notifier.notify(_escalation())  # must not raise

        self.assertFalse(result.delivered)
        self.assertEqual(result.status, "failed")

    def test_non_http_scheme_is_rejected(self) -> None:
        notifier = EscalationNotifier(NotificationSettings(webhook_url="file:///etc/passwd"))

        result = notifier.notify(_escalation())

        self.assertEqual(result.status, "failed")
        self.assertIn("https://", result.detail)
        self.assertEqual(_CaptureHandler.received, [])


if __name__ == "__main__":
    unittest.main()
