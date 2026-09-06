"""Escalation notifications — routing a Sentinel decision to a real human channel.

The Sentinel's whole promise is *"you only hear from me when a human is needed."*
That promise is only real if the alert actually leaves the process. This module
is the delivery leg: it turns an :class:`app.sentinel.Escalation` into a Slack
message or a generic JSON webhook POST.

Design constraints (they mirror the rest of MealMesh):

- **Deterministic.** Payload formatting is a pure function of the escalation. No
  LLM is involved in deciding *whether* to alert or *what* the alert says — the
  CP-SAT pipeline already decided that.
- **Config-driven, no-op if unconfigured.** With no environment variables set,
  :class:`EscalationNotifier` is a silent no-op. The demo never needs a webhook.
- **Never breaks the loop.** A dead webhook, a proxy, a timeout, an offline
  laptop — every transport failure is caught, logged, and reported as a failed
  ``NotificationResult``. Monitoring must not stop because Slack is down.
- **Stdlib only.** ``urllib.request`` rather than a new dependency, with the
  sender injected so tests never touch the network.

Configuration (all optional, read from the environment or ``.env``)::

    RESQ_NOTIFY_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
    RESQ_NOTIFY_WEBHOOK_URL=https://ops.example.org/resq-mesh/escalations
    RESQ_NOTIFY_MIN_SEVERITY=review        # review | warning | critical
    RESQ_NOTIFY_DRY_RUN=false              # render + log, never send
    RESQ_NOTIFY_TIMEOUT_SECONDS=5.0
    RESQ_NOTIFY_CHANNEL_LABEL=#meal-coverage     # display only

Preview exactly what the demo escalations would send, with no network::

    python -m app.notifications
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Literal

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.observability import get_logger, log_event
from app.pydantic_compat import CompatBaseModel

logger = get_logger(__name__)

Severity = Literal["review", "warning", "critical"]
Channel = Literal["slack", "webhook", "none"]
DeliveryStatus = Literal[
    "sent",
    "dry_run",
    "skipped_unconfigured",
    "skipped_below_threshold",
    "failed",
]

# Higher = more urgent. Used for the RESQ_NOTIFY_MIN_SEVERITY threshold.
SEVERITY_RANK: dict[str, int] = {"review": 0, "warning": 1, "critical": 2}

_SEVERITY_EMOJI: dict[str, str] = {"review": "🔎", "warning": "⚠️", "critical": "🚨"}
_ALLOWED_SCHEMES = ("https://", "http://")

# A payload sender: (url, payload) -> None. Raises on failure.
Sender = Callable[[str, dict], None]


class NotificationSettings(BaseSettings):
    """Environment-driven notification config. Every field is optional."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="resq_notify_",
        extra="ignore",
    )

    slack_webhook_url: str = ""
    webhook_url: str = ""
    min_severity: Severity = "review"
    dry_run: bool = False
    timeout_seconds: float = 5.0
    channel_label: str = ""

    @property
    def channel(self) -> Channel:
        """The channel that will be used. Slack wins if both are configured."""

        if self.slack_webhook_url.strip():
            return "slack"
        if self.webhook_url.strip():
            return "webhook"
        return "none"

    @property
    def configured(self) -> bool:
        return self.channel != "none"

    @property
    def target_url(self) -> str:
        if self.channel == "slack":
            return self.slack_webhook_url.strip()
        if self.channel == "webhook":
            return self.webhook_url.strip()
        return ""

    def describe_target(self) -> str:
        """A safe, human-readable target description that never leaks the URL."""

        if self.channel_label.strip():
            return self.channel_label.strip()
        if self.channel == "slack":
            return "Slack incoming webhook"
        if self.channel == "webhook":
            return "HTTP webhook"
        return "not configured"


class NotificationResult(CompatBaseModel):
    """The outcome of trying to deliver one escalation. Never an exception."""

    model_config = ConfigDict(extra="forbid")

    delivered: bool
    channel: Channel
    status: DeliveryStatus
    target: str = ""
    detail: str = ""


# --------------------------------------------------------------------------- #
# Payload formatting — pure functions of the escalation.
# --------------------------------------------------------------------------- #


def render_text(escalation, *, mission_label: str = "") -> str:
    """Render the escalation as a single plain-text alert line.

    Used for Slack's notification fallback text, for the generic webhook
    payload, and for the CLI/dry-run preview.
    """

    emoji = _SEVERITY_EMOJI.get(escalation.severity, "•")
    scope = f" · {mission_label}" if mission_label else ""
    return (
        f"{emoji} MealMesh: community meal coverage needs you{scope} — "
        f"{escalation.verdict}. Trigger: {escalation.triggered_by}. "
        f"{escalation.decision_required}"
    )


def format_slack_payload(escalation, *, mission_label: str = "") -> dict:
    """Build a Slack incoming-webhook payload (Block Kit + fallback text)."""

    text = render_text(escalation, mission_label=mission_label)
    emoji = _SEVERITY_EMOJI.get(escalation.severity, "•")

    fields = [
        {"type": "mrkdwn", "text": f"*Verdict*\n{escalation.verdict}"},
        {"type": "mrkdwn", "text": f"*Triggered by*\n{escalation.triggered_by}"},
    ]
    if escalation.missing_capabilities:
        fields.append(
            {
                "type": "mrkdwn",
                "text": "*Missing capability*\n" + ", ".join(escalation.missing_capabilities),
            }
        )
    if escalation.trace_id:
        fields.append({"type": "mrkdwn", "text": f"*Trace*\n`{escalation.trace_id}`"})

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Decision needed ({escalation.severity})",
                "emoji": True,
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": escalation.decision_required}},
        {"type": "section", "fields": fields},
    ]

    what_if = escalation.answers.get("WHAT IF")
    if what_if:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"*WHAT IF:* {what_if}"}]}
        )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "Decided by the CP-SAT solver, not a language model · "
                        "all data simulated · MealMesh only auto-assigns opted-in volunteers."
                    ),
                }
            ],
        }
    )

    payload: dict = {"text": text, "blocks": blocks}
    if mission_label:
        payload["username"] = f"MealMesh Sentinel · {mission_label}"
    return payload


def format_webhook_payload(escalation, *, mission_label: str = "") -> dict:
    """Build a generic JSON webhook payload (stable, machine-readable shape)."""

    return {
        "source": "mealmesh-sentinel",
        "type": "escalation",
        "severity": escalation.severity,
        "verdict": escalation.verdict,
        "triggered_by": escalation.triggered_by,
        "decision_required": escalation.decision_required,
        "missing_capabilities": list(escalation.missing_capabilities),
        "answers": dict(escalation.answers),
        "trace_id": escalation.trace_id,
        "mission": mission_label,
        "text": render_text(escalation, mission_label=mission_label),
        "synthetic_data": True,
    }


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #


def _post_json(url: str, payload: dict, *, timeout: float) -> None:
    """POST ``payload`` as JSON. Raises on any transport or non-2xx response."""

    if not url.startswith(_ALLOWED_SCHEMES):
        raise ValueError("notification URL must start with https:// or http://")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "mealmesh-sentinel/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-configured URL
        status = getattr(response, "status", 200)
        if not 200 <= int(status) < 300:
            raise urllib.error.HTTPError(url, int(status), "unexpected status", response.headers, None)


class EscalationNotifier:
    """Delivers Sentinel escalations to a configured human channel.

    A no-op when nothing is configured, so the offline demo is unaffected.
    Delivery failures are swallowed — monitoring must outlive its notifier.
    """

    def __init__(
        self,
        settings: NotificationSettings | None = None,
        *,
        sender: Sender | None = None,
    ) -> None:
        self.settings = settings if settings is not None else NotificationSettings()
        self._sender = sender

    # -- introspection used by the API/dashboard -------------------------- #

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def describe(self) -> dict:
        """A safe summary for the API. Never includes the webhook URL itself."""

        return {
            "configured": self.settings.configured,
            "channel": self.settings.channel,
            "target": self.settings.describe_target(),
            "dry_run": self.settings.dry_run,
            "min_severity": self.settings.min_severity,
        }

    # -- delivery ---------------------------------------------------------- #

    def build_payload(self, escalation, *, mission_label: str = "") -> dict:
        """Return the exact payload that would be POSTed for ``escalation``."""

        if self.settings.channel == "slack":
            return format_slack_payload(escalation, mission_label=mission_label)
        return format_webhook_payload(escalation, mission_label=mission_label)

    def notify(self, escalation, *, mission_label: str = "") -> NotificationResult:
        """Deliver one escalation. Always returns; never raises."""

        settings = self.settings
        channel = settings.channel
        target = settings.describe_target()

        if SEVERITY_RANK[escalation.severity] < SEVERITY_RANK[settings.min_severity]:
            return NotificationResult(
                delivered=False,
                channel=channel,
                status="skipped_below_threshold",
                target=target,
                detail=(
                    f"severity '{escalation.severity}' is below the configured "
                    f"minimum '{settings.min_severity}'"
                ),
            )

        if channel == "none":
            return NotificationResult(
                delivered=False,
                channel="none",
                status="skipped_unconfigured",
                target=target,
                detail="no notification channel configured (set RESQ_NOTIFY_SLACK_WEBHOOK_URL or RESQ_NOTIFY_WEBHOOK_URL)",
            )

        payload = self.build_payload(escalation, mission_label=mission_label)

        if settings.dry_run:
            log_event(
                logger,
                "notification.dry_run",
                channel=channel,
                severity=escalation.severity,
                verdict=escalation.verdict,
            )
            return NotificationResult(
                delivered=False,
                channel=channel,
                status="dry_run",
                target=target,
                detail="RESQ_NOTIFY_DRY_RUN is set; payload rendered but not sent",
            )

        def default_sender(url: str, body: dict) -> None:
            _post_json(url, body, timeout=settings.timeout_seconds)

        sender: Sender = self._sender if self._sender is not None else default_sender

        try:
            sender(settings.target_url, payload)
        except Exception as exc:  # noqa: BLE001 - a failed alert must never stop monitoring
            log_event(
                logger,
                "notification.failed",
                channel=channel,
                severity=escalation.severity,
                error=f"{type(exc).__name__}: {exc}",
            )
            return NotificationResult(
                delivered=False,
                channel=channel,
                status="failed",
                target=target,
                detail=f"{type(exc).__name__}: {exc}",
            )

        log_event(
            logger,
            "notification.sent",
            channel=channel,
            severity=escalation.severity,
            verdict=escalation.verdict,
        )
        return NotificationResult(
            delivered=True,
            channel=channel,
            status="sent",
            target=target,
            detail=f"escalation delivered to {target}",
        )


def build_notifier(
    sender: Sender | None = None, *, force_dry_run: bool = False
) -> EscalationNotifier:
    """Build a notifier from the current environment (a no-op if unconfigured).

    ``force_dry_run`` renders payloads without sending them regardless of
    ``RESQ_NOTIFY_DRY_RUN``. Used by replay surfaces (the dashboard's canned
    Sentinel timeline) so browsing the demo can never spam a real channel.
    """

    settings = NotificationSettings()
    if force_dry_run:
        settings = settings.model_copy(update={"dry_run": True})
    return EscalationNotifier(settings, sender=sender)


def describe_notification_channel() -> dict:
    """Channel summary for the dashboard/API, without leaking the webhook URL."""

    return build_notifier().describe()


# --------------------------------------------------------------------------- #
# Preview: exactly what the demo timeline would send, with zero network.
# --------------------------------------------------------------------------- #


def preview_demo_notifications() -> str:
    """Render the payloads the demo's escalations would deliver.

    Uses the real formatter for whichever channel is configured, defaulting to
    the generic webhook shape when nothing is set — so this always works offline.
    """

    from app.sentinel import build_demo_mission, run_sentinel_demo

    notifier = build_notifier()
    described = notifier.describe()
    mission = build_demo_mission()
    mission_label = f"{mission.destination} ({mission.incident_type})"

    lines: list[str] = [
        "=== MealMesh coverage notifications (preview) ===",
        "",
        f"Channel:      {described['channel']}",
        f"Target:       {described['target']}",
        f"Min severity: {described['min_severity']}    Dry run: {described['dry_run']}",
        "",
    ]
    if not described["configured"]:
        lines += [
            "Nothing is configured, so the Sentinel will NOT send anything (by design).",
            "Set RESQ_NOTIFY_SLACK_WEBHOOK_URL or RESQ_NOTIFY_WEBHOOK_URL to enable delivery.",
            "Below is the generic webhook payload each escalation would produce.",
            "",
        ]

    escalations = [
        observation.escalation
        for observation in run_sentinel_demo()
        if observation.escalation is not None
    ]
    if not escalations:
        lines.append("No escalations in the demo timeline.")
        return "\n".join(lines) + "\n"

    for index, escalation in enumerate(escalations, start=1):
        payload = notifier.build_payload(escalation, mission_label=mission_label)
        lines.append(f"--- escalation {index}/{len(escalations)} · {escalation.severity} ---")
        lines.append(render_text(escalation, mission_label=mission_label))
        lines.append("")
        lines.append(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        lines.append("")

    lines.append(
        f"{len(escalations)} escalation(s) would be delivered. "
        "Everything else the Sentinel saw was handled autonomously and sent nothing."
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    print(preview_demo_notifications())


if __name__ == "__main__":
    main()
