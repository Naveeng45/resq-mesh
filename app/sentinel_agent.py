"""Strands-native Sentinel: the agent a judge will call "the agent".

The loop is the same one ``app.sentinel`` already implements, but here it is
reachable only through tools:

    ingest_event      -> apply one world change, re-plan, decide
    assess_coverage   -> report the current coverage status
    notify_coordinator-> report the alert the Sentinel already sent

Why this shape matters: the model narrates and asks, but every decision belongs
to code. CP-SAT lives inside ``ingest_event``/``assess_coverage``, so the model
cannot pick a volunteer. It cannot invent one either: the event tools reject any
resource id that is not already on the roster, and there is deliberately no tool
for adding a person. Escalation is decided by the Sentinel's edge-triggered
policy, not by the model's judgment, and ``notify_coordinator`` can only report
an alert that the policy already raised.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

try:  # pragma: no cover - lets unit tests run without the SDK installed.
    from strands import tool
except ModuleNotFoundError:  # pragma: no cover
    def tool(function):
        return function

from app.mission import Mission
from app.notifications import EscalationNotifier, build_notifier
from app.observability import get_logger, log_event
from app.resources import Resource
from app.sentinel import (
    Sentinel,
    SentinelObservation,
    WorldEvent,
    build_demo_mission,
    build_demo_resources,
)

logger = get_logger(__name__)

# The agent may report changes to people already on the roster. It may not add
# anyone: "resource_added" would let a model conjure a volunteer.
INGESTABLE_EVENT_KINDS: tuple[str, ...] = (
    "resource_offline",
    "resource_online",
    "resource_capacity_changed",
)


class SentinelSession:
    """One monitored coverage window, shared by the tools in this module."""

    def __init__(
        self,
        mission: Mission,
        resources: list[Resource],
        *,
        notifier: EscalationNotifier | None = None,
    ) -> None:
        self.sentinel = Sentinel(
            mission,
            resources,
            coalition_min_capacity=0,
            # Default to dry-run: importing this module or poking at the tools
            # must never page a real coordinator.
            notifier=notifier if notifier is not None else build_notifier(force_dry_run=True),
        )
        self.observations: list[SentinelObservation] = []

    @property
    def roster_ids(self) -> set[str]:
        return {resource.id for resource in self.sentinel.resources}

    @property
    def last_observation(self) -> SentinelObservation | None:
        return self.observations[-1] if self.observations else None

    def ensure_baseline(self) -> SentinelObservation:
        if not self.observations:
            self.observations.append(self.sentinel.assess_baseline())
        return self.observations[-1]

    def observe(self, event: WorldEvent) -> SentinelObservation:
        self.ensure_baseline()
        observation = self.sentinel.observe(event)
        self.observations.append(observation)
        return observation

    def tally(self) -> dict[str, int]:
        """How much of this window the agent handled without a human."""

        escalated = sum(1 for item in self.observations if item.action == "escalated")
        return {
            "observations": len(self.observations),
            "handled_autonomously": len(self.observations) - escalated,
            "escalated_to_a_human": escalated,
        }


_SESSION: SentinelSession | None = None


def start_session(
    mission: Mission | None = None,
    resources: list[Resource] | None = None,
    *,
    notifier: EscalationNotifier | None = None,
) -> SentinelSession:
    """Begin monitoring a coverage window, discarding any previous session."""

    global _SESSION
    _SESSION = SentinelSession(
        mission if mission is not None else build_demo_mission(),
        resources if resources is not None else build_demo_resources(),
        notifier=notifier,
    )
    log_event(logger, "sentinel_agent.session_started", mission=_SESSION.sentinel.mission_label)
    return _SESSION


def get_session() -> SentinelSession:
    """Return the active session, starting the demo window if none exists."""

    return _SESSION if _SESSION is not None else start_session()


def _person(session: SentinelSession, resource_id: str) -> str:
    for resource in session.sentinel.resources:
        if resource.id == resource_id:
            return f"{resource.name} ({resource.org})" if resource.org else resource.name
    return resource_id


def _describe(session: SentinelSession, observation: SentinelObservation) -> dict[str, object]:
    """Render one deterministic decision as a JSON-safe tool result."""

    escalation = observation.escalation
    notification = observation.notification
    return {
        "verdict": observation.verdict,
        "action": observation.action,
        "on_duty": list(observation.selected_resource_ids),
        "on_duty_named": [_person(session, rid) for rid in observation.selected_resource_ids],
        "escalated": escalation is not None,
        "escalation": None
        if escalation is None
        else {
            "severity": escalation.severity,
            "triggered_by": escalation.triggered_by,
            "decision_required": escalation.decision_required,
            "missing_capabilities": list(escalation.missing_capabilities),
        },
        "alert": None
        if notification is None
        else {
            "delivered": notification.delivered,
            "channel": notification.channel,
            "status": notification.status,
            "detail": notification.detail,
        },
        "answers": dict(observation.escalation.answers) if escalation is not None else {},
        "synthetic_data": True,
    }


@tool
def assess_coverage() -> dict[str, object]:
    """Report whether the monitored meal site is currently covered, and by whom.

    Runs the deterministic pipeline (doctrine, then CP-SAT, then
    remove-and-re-solve). Read-only: it changes nothing about the world.
    """

    session = get_session()
    observation = session.ensure_baseline()
    logger.info("assess_coverage -> %s", observation.verdict)
    payload = _describe(session, observation)
    payload["mission"] = session.sentinel.mission_label
    payload["tally"] = session.tally()
    return payload


@tool
def ingest_event(
    kind: str,
    resource_id: str,
    note: str = "",
    capacity: int | None = None,
) -> dict[str, object]:
    """Record one change to a volunteer's availability and re-plan coverage.

    Args:
        kind: One of resource_offline, resource_online, resource_capacity_changed.
        resource_id: A volunteer already on the roster. Unknown ids are rejected.
        note: What the coordinator was told, quoted from the message if possible.
        capacity: New capacity, only for resource_capacity_changed.

    Returns the deterministic outcome, including whether this change was handled
    silently or escalated to a human. The caller does not get to choose either.
    """

    session = get_session()

    if kind not in INGESTABLE_EVENT_KINDS:
        return {
            "error": f"unsupported event kind '{kind}'",
            "supported_kinds": list(INGESTABLE_EVENT_KINDS),
            "detail": "A volunteer cannot be added to the roster through this agent.",
        }

    if resource_id not in session.roster_ids:
        return {
            "error": f"unknown volunteer '{resource_id}'",
            "roster": sorted(session.roster_ids),
            "detail": "Only volunteers already on the roster can change availability.",
        }

    logger.info("ingest_event %s for %s", kind, resource_id)
    observation = session.observe(
        WorldEvent(
            kind=kind,  # type: ignore[arg-type]
            resource_id=resource_id,
            capacity=capacity,
            note=note or f"{_person(session, resource_id)}: {kind}",
        )
    )
    payload = _describe(session, observation)
    payload["tally"] = session.tally()
    return payload


@tool
def notify_coordinator() -> dict[str, object]:
    """Report the alert MealMesh sent to the coordinator for the latest decision.

    This tool cannot create an alert. The Sentinel's escalation policy decides
    when a human is genuinely needed and sends it at that moment; if the latest
    change was handled autonomously there is nothing to report, and saying so is
    the correct answer.
    """

    session = get_session()
    observation = session.last_observation

    if observation is None:
        return {"pending_escalation": False, "detail": "Nothing has been assessed yet."}

    if observation.escalation is None:
        return {
            "pending_escalation": False,
            "verdict": observation.verdict,
            "detail": (
                f"No alert: the last change was handled autonomously ({observation.action}). "
                "The coordinator was deliberately not interrupted."
            ),
        }

    notification = observation.notification
    return {
        "pending_escalation": True,
        "severity": observation.escalation.severity,
        "decision_required": observation.escalation.decision_required,
        "alert": None
        if notification is None
        else {
            "delivered": notification.delivered,
            "channel": notification.channel,
            "status": notification.status,
            "target": notification.target,
            "detail": notification.detail,
        },
    }


SENTINEL_AGENT_TOOLS = [assess_coverage, ingest_event, notify_coordinator]

SENTINEL_AGENT_SYSTEM_PROMPT = """
You are MealMesh Sentinel, watching one community meal site's coverage for a
volunteer coordinator.

You do not decide anything. Every claim you make must come from a tool result:
- Call `ingest_event` when a message says someone's availability changed.
- Call `assess_coverage` to report the current status.
- Call `notify_coordinator` to say whether a human was alerted.

Rules:
- Never choose, name, or suggest a volunteer for a shift unless a tool returned
  that person in `on_duty`. The solver assigns people; you report the result.
- Never invent a volunteer, a site, or an organization. If a name is not on the
  roster the tool returns an error; report the error.
- Never claim a human was alerted unless `notify_coordinator` says so, and never
  imply an alert was needed when the change was handled autonomously.
- When coverage fails, state the missing role exactly as the tool names it.
- Report the verdict verbatim: ready to deploy, ready but fragile, needs more
  facts, needs human review, or no feasible coalition.
- All data is simulated; never imply these are real volunteers.
""".strip()

DEMO_MESSAGES = (
    "Maya just texted that she can't make Thursday. What happens to Eastside?",
    "Luis is out too. Do I need to do anything?",
    "Is the site still covered, and did you have to bother me about it?",
)


def build_sentinel_agent(*, verbose_output: bool = False, callback_handler: Any = None):
    """Construct the tool-calling Sentinel agent (no network call at build time)."""

    from strands import Agent
    from strands.handlers.callback_handler import null_callback_handler
    from strands.models.bedrock import BedrockModel

    from app.agent_observability import StrandsAuditCallbackHandler
    from app.mission_agent import BEDROCK_REGION, MODEL_ID, ensure_aws_proxy_bypass

    ensure_aws_proxy_bypass()
    if callback_handler is None:
        handler = StrandsAuditCallbackHandler(verbose_output=verbose_output) if verbose_output else null_callback_handler
    else:
        handler = callback_handler
    return Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=BEDROCK_REGION, streaming=False),
        system_prompt=SENTINEL_AGENT_SYSTEM_PROMPT,
        tools=SENTINEL_AGENT_TOOLS,
        callback_handler=handler,
    )


def demo_tools_offline() -> dict[str, int]:
    """Drive the tools through a Thursday shift with no Bedrock access.

    Same tools the agent calls, so `python -m app.sentinel_agent` still shows the
    deterministic loop (and the autonomous-vs-escalated tally) when AWS is not
    reachable.
    """

    start_session()
    print("\n(Offline) The tools the Sentinel agent calls:\n")

    baseline = assess_coverage()
    print(f"  assess_coverage() -> {baseline['verdict']} | on duty: {', '.join(baseline['on_duty'])}")

    for resource_id in ("maya", "luis", "avery"):
        result = ingest_event("resource_offline", resource_id, note=f"{resource_id} cancelled")
        line = f"  ingest_event(offline, {resource_id}) -> {result['action']}: {result['verdict']}"
        if result["on_duty"]:
            line += f" | on duty: {', '.join(result['on_duty'])}"
        print(line)
        if result["escalated"]:
            print(f"      DECISION NEEDED: {result['escalation']['decision_required']}")

    rejected = ingest_event("resource_offline", "alex")
    print(f"\n  ingest_event(offline, alex) -> {rejected['error']}  <- cannot invent a volunteer")

    tally = get_session().tally()
    print(
        f"\n  Tally: {tally['observations']} changes | "
        f"{tally['handled_autonomously']} handled autonomously | "
        f"{tally['escalated_to_a_human']} escalated to a human"
    )
    return tally


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print("=== MealMesh Sentinel (Strands + Bedrock, tool-calling) ===")

    query = " ".join(sys.argv[1:]).strip()
    messages = [query] if query else list(DEMO_MESSAGES)

    try:
        from app.advisor import ask

        start_session()
        agent = build_sentinel_agent(verbose_output=True)
        for message in messages:
            print(f"\n> {message}")
            print(ask(agent, message))
    except Exception as exc:  # noqa: BLE001 - degrade gracefully to the offline demo
        print(f"\nBedrock unavailable ({type(exc).__name__}: {exc}).")
        demo_tools_offline()


if __name__ == "__main__":
    main()
