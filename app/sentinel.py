"""Autonomous MealMesh sentinel for community meal coverage.

This is the layer that makes MealMesh match the hackathon theme: an agent that
*quietly handles routine work in the background and only alerts a human when a
genuine decision is needed.*

The sentinel watches world-state changes (a volunteer cancels, returns, or is
recruited). On every change it re-runs the full
deterministic pipeline and then applies a deterministic escalation policy:

    - stays SILENT when nothing meaningful changed,
    - AUTO-RECOMPOSES silently when it can absorb a loss (feasible + resilient),
    - ESCALATES to a human only on a genuine decision (fragile / infeasible /
      needs review / needs facts),
    - reports IMPROVED / RESOLVED when a human's action restores the mission.

Escalations are edge-triggered: the sentinel alerts when things get *worse*, not
on every tick, so it does not spam the human. The LLM is never in this loop -
only the deterministic pipeline decides.

When a notification channel is configured (see ``app/notifications.py``),
escalations - and *only* escalations - are delivered to a real human channel:
Slack or a generic JSON webhook. With nothing configured it is a silent no-op,
so the offline demo is unaffected. Run:

    python -m app.sentinel
    python -m app.notifications   # preview the payloads an escalation would send
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.capabilities import CAPABILITY_ONTOLOGY
from app.mission import Mission
from app.notifications import EscalationNotifier, NotificationResult, build_notifier
from app.observability import configure_logging, get_logger, log_event, new_trace_id
from app.orchestration import OrchestrationResult, run_pipeline
from app.pydantic_compat import CompatBaseModel
from app.resources import Resource

logger = get_logger(__name__)

# Higher rank = worse. Used for edge-triggered escalation (alert on worsening).
_VERDICT_RANK: dict[str, int] = {
    "ready to deploy": 0,
    "needs more facts": 1,
    "needs human review": 2,
    "ready but fragile": 3,
    "no feasible coalition": 4,
}

_VERDICT_SEVERITY: dict[str, str] = {
    "needs more facts": "review",
    "needs human review": "review",
    "ready but fragile": "warning",
    "no feasible coalition": "critical",
}

EventKind = Literal[
    "baseline",
    "resource_offline",
    "resource_online",
    "resource_capacity_changed",
    "resource_added",
]

Action = Literal["silent", "auto_recomposed", "escalated", "improved", "resolved"]


class WorldEvent(CompatBaseModel):
    """A single observed change to the world the sentinel is monitoring."""

    model_config = ConfigDict(extra="forbid")

    kind: EventKind
    resource_id: str | None = None
    capacity: int | None = None
    resource: Resource | None = None
    note: str = ""


class Escalation(CompatBaseModel):
    """A human-facing alert: raised only when a genuine decision is needed."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["review", "warning", "critical"]
    verdict: str
    triggered_by: str
    decision_required: str
    answers: dict[str, str] = Field(default_factory=dict)
    missing_capabilities: list[str] = Field(default_factory=list)
    trace_id: str | None = None


class SentinelObservation(CompatBaseModel):
    """The sentinel's decision about one observed event."""

    model_config = ConfigDict(extra="forbid")

    event: WorldEvent
    verdict: str
    action: Action
    selected_resource_ids: list[str] = Field(default_factory=list)
    escalation: Escalation | None = None
    # Set only when an escalation was raised: the outcome of trying to reach a
    # human. ``None`` everywhere else, which is the point - silent handling
    # sends nothing at all.
    notification: NotificationResult | None = None


def _capability_label(code: str) -> str:
    for capability in CAPABILITY_ONTOLOGY:
        if capability.code == code:
            return capability.label
    return code


def apply_event(catalog: list[Resource], event: WorldEvent) -> list[Resource]:
    """Return a new catalog with ``event`` applied (pure - no mutation of input)."""

    updated = [resource.model_copy(deep=True) for resource in catalog]

    if event.kind == "resource_offline":
        for resource in updated:
            if resource.id == event.resource_id:
                resource.availability = False
                resource.status = "offline"
    elif event.kind == "resource_online":
        for resource in updated:
            if resource.id == event.resource_id:
                resource.availability = True
                resource.status = "available"
    elif event.kind == "resource_capacity_changed":
        for resource in updated:
            if resource.id == event.resource_id and event.capacity is not None:
                resource.capacity = event.capacity
    elif event.kind == "resource_added" and event.resource is not None:
        updated.append(event.resource.model_copy(deep=True))

    return updated


def _decision_text(result: OrchestrationResult, resources: list[Resource]) -> str:
    verdict = result.verdict
    if verdict == "no feasible coalition":
        if result.missing_capabilities:
            labels = ", ".join(_capability_label(code) for code in result.missing_capabilities)
            recruits = [
                resource.name.split()[0]
                for resource in resources
                if not resource.opted_in
                and any(code in resource.capability_codes for code in result.missing_capabilities)
            ]
            recruit_text = f" Ask {recruits[0]}, or call Second Harvest." if recruits else " Call Second Harvest."
            return f"Eastside 4pm would be uncovered. Missing capability: {labels}.{recruit_text}"
        return result.answers.get("WHAT IS MISSING", "No feasible coalition exists.")
    if verdict == "ready but fragile":
        ids = result.resilience.mission_breaking_failure_ids if result.resilience else []
        if ids:
            return (
                "Eastside is covered, but the plan is fragile. Losing any of ["
                + ", ".join(ids)
                + "] would uncover the site. Recruit one more opted-in backup."
            )
        return "Eastside is covered but fragile; recruit one more opted-in backup."
    if verdict == "needs human review":
        reasons = result.capability_assessment.review_reasons
        return "Human doctrine call needed: " + ("; ".join(reasons) if reasons else "capability assessment is ambiguous.")
    if verdict == "needs more facts":
        missing = result.review.missing_critical_facts
        return "Missing critical facts: " + (", ".join(missing) if missing else "unknown")
    return "No decision required."


class Sentinel:
    """Stateful monitor that decides, per event, whether a human is needed."""

    def __init__(
        self,
        mission: Mission,
        resources: list[Resource],
        *,
        coalition_min_capacity: int = 0,
        replan_min_capacity: int | None = None,
        notifier: EscalationNotifier | None = None,
    ) -> None:
        self.mission = mission
        self.resources = [resource.model_copy(deep=True) for resource in resources]
        self.coalition_min_capacity = coalition_min_capacity
        self.replan_min_capacity = replan_min_capacity
        self.trace_id = new_trace_id()
        # Built from the environment by default; a no-op when nothing is configured.
        self.notifier = notifier if notifier is not None else build_notifier()
        self._last_result: OrchestrationResult | None = None
        self._last_rank = 0

    @property
    def mission_label(self) -> str:
        """Short human label for the monitored mission, used in alerts."""

        parts = [part for part in (self.mission.destination, self.mission.incident_type) if part]
        if len(parts) == 2:
            return f"{parts[0]} ({parts[1]})"
        return parts[0] if parts else "unnamed mission"

    def current_selected_of_capability(self, capability_code: str) -> str | None:
        """Return the id of a currently-selected resource providing ``capability_code``."""

        if self._last_result is None or self._last_result.coalition is None:
            return None
        for resource in self._last_result.coalition.selected_resources:
            if capability_code in resource.capability_codes:
                return resource.id
        return None

    def assess_baseline(self) -> SentinelObservation:
        """Run the initial assessment before any events arrive."""

        return self._assess(WorldEvent(kind="baseline", note="initial assessment"))

    def observe(self, event: WorldEvent) -> SentinelObservation:
        """Apply an event, re-plan, and decide whether to escalate."""

        self.resources = apply_event(self.resources, event)
        return self._assess(event)

    def _assess(self, event: WorldEvent) -> SentinelObservation:
        # Consent is a hard boundary around the solver: CP-SAT may choose only
        # volunteers who pre-authorized this coverage window. Keep the full
        # roster in ``self.resources`` so deterministic escalation copy can
        # still name recruit-only candidates such as Jordan.
        assignable_resources = [
            resource for resource in self.resources if resource.opted_in
        ]
        result = run_pipeline(
            self.mission,
            resources=assignable_resources,
            include_resilience=True,
            include_hypergraph=False,
            coalition_min_capacity=self.coalition_min_capacity,
            replan_min_capacity=self.replan_min_capacity,
            trace_id=self.trace_id,
        )
        observation = self._decide(event, result)
        self._last_result = result
        self._last_rank = _VERDICT_RANK[result.verdict]

        # Reach a human ONLY on an escalation. Silent / auto-recomposed /
        # improved / resolved outcomes deliberately send nothing.
        if observation.escalation is not None:
            observation.notification = self.notifier.notify(
                observation.escalation, mission_label=self.mission_label
            )

        log_event(
            logger,
            f"sentinel.{observation.action}",
            verdict=result.verdict,
            event_kind=event.kind,
            escalated=observation.escalation is not None,
            notified=bool(observation.notification and observation.notification.delivered),
        )
        return observation

    def _decide(self, event: WorldEvent, result: OrchestrationResult) -> SentinelObservation:
        rank = _VERDICT_RANK[result.verdict]
        prev_rank = self._last_rank
        had_prev = self._last_result is not None

        new_selected = result.coalition.selected_resource_ids if result.coalition else []
        prev_selected = (
            self._last_result.coalition.selected_resource_ids
            if had_prev and self._last_result and self._last_result.coalition
            else []
        )

        if rank == 0:
            if had_prev and prev_rank > 0:
                action: Action = "resolved"
            elif had_prev and set(new_selected) != set(prev_selected):
                action = "auto_recomposed"
            else:
                action = "silent"
            return SentinelObservation(
                event=event, verdict=result.verdict, action=action, selected_resource_ids=new_selected
            )

        # rank > 0: escalate only when things got worse (edge-triggered).
        if rank > prev_rank:
            escalation = Escalation(
                severity=_VERDICT_SEVERITY[result.verdict],  # type: ignore[arg-type]
                verdict=result.verdict,
                triggered_by=event.note or f"{event.kind}:{event.resource_id or ''}".rstrip(":"),
                decision_required=_decision_text(result, self.resources),
                answers=result.answers,
                missing_capabilities=result.missing_capabilities,
                trace_id=result.trace_id,
            )
            return SentinelObservation(
                event=event,
                verdict=result.verdict,
                action="escalated",
                selected_resource_ids=new_selected,
                escalation=escalation,
            )

        # Still degraded but no worse: improved (partial recovery) or already-alerted.
        action = "improved" if rank < prev_rank else "silent"
        return SentinelObservation(
            event=event, verdict=result.verdict, action=action, selected_resource_ids=new_selected
        )


# --------------------------------------------------------------------------- #
# Demo: Thursday Eastside community meal coverage monitored over time.
# --------------------------------------------------------------------------- #


def build_demo_mission() -> Mission:
    return Mission(
        destination="Riverside Community Meals — Eastside",
        deadline="2026-09-10T16:00:00-07:00",
        incident_type="thursday_distribution",
        requirements=["van driver", "packer", "site lead"],
        constraints=["van certification required to drive"],
    )


def _volunteer(
    resource_id: str,
    name: str,
    capability_code: str,
    org: str,
    *,
    opted_in: bool = True,
    reliability: float = 0.9,
) -> Resource:
    return Resource(
        id=resource_id,
        name=name,
        category=capability_code,
        location="Eastside" if resource_id in {"maya", "priya", "elena"} else f"{org} bench",
        status="available" if opted_in else "busy",
        availability=opted_in,
        reliability=reliability,
        capacity=1,
        capacity_unit="site",
        capability_codes=[capability_code],
        opted_in=opted_in,
        org=org,
    )


def build_demo_resources() -> list[Resource]:
    """Synthetic Eastside roster with opted-in depth and one recruit-only driver."""

    return [
        _volunteer("avery", "Avery Reed", "van_certified_driver", "Second Harvest", reliability=0.88),
        _volunteer("luis", "Luis Okonkwo", "van_certified_driver", "Second Harvest", reliability=0.93),
        _volunteer("maya", "Maya Chen", "van_certified_driver", "Riverside Church", reliability=0.96),
        _volunteer("jordan", "Jordan Hale", "van_certified_driver", "Second Harvest", opted_in=False, reliability=0.91),
        _volunteer("riley", "Riley Morgan", "food_handler", "Riverside Church", reliability=0.87),
        _volunteer("sam", "Sam Ortiz", "food_handler", "Riverside Church", reliability=0.92),
        _volunteer("priya", "Priya Shah", "food_handler", "Riverside Church", reliability=0.95),
        _volunteer("noah", "Noah Kim", "site_keyholder", "Second Harvest", reliability=0.90),
        _volunteer("elena", "Elena Brooks", "site_keyholder", "Riverside Church", reliability=0.97),
    ]


def run_sentinel_demo(*, notifier: EscalationNotifier | None = None) -> list[SentinelObservation]:
    """Drive the sentinel through a realistic degradation-and-recovery timeline.

    This is a *canned replay*, so it defaults to a dry-run notifier: it renders
    the alerts it would send but never delivers them. Replaying the demo (in
    tests, in the dashboard, in a preview) can therefore never page a real
    on-call human. Pass an explicit ``notifier`` to deliver for real.
    """

    sentinel = Sentinel(
        build_demo_mission(),
        build_demo_resources(),
        coalition_min_capacity=0,
        notifier=notifier if notifier is not None else build_notifier(force_dry_run=True),
    )
    observations: list[SentinelObservation] = [sentinel.assess_baseline()]

    # 1) Maya cancels. The opted-in driver bench absorbs it without a page.
    observations.append(
        sentinel.observe(
            WorldEvent(
                kind="resource_offline",
                resource_id="maya",
                note="Maya cancels for Thursday Eastside — Luis is available on the opted-in bench",
            )
        )
    )

    # 2) Priya cancels. Sam covers the food-handler role silently.
    observations.append(
        sentinel.observe(
            WorldEvent(
                kind="resource_offline",
                resource_id="priya",
                note="Priya cancels for Thursday Eastside — Sam is available on the opted-in bench",
            )
        )
    )

    # 3) Luis cancels. Avery can still drive, but the last reserve is now gone.
    observations.append(
        sentinel.observe(
            WorldEvent(
                kind="resource_offline",
                resource_id="luis",
                note="Luis cancels — Eastside is down to its last opted-in driver",
            )
        )
    )

    # 4) The remaining opted-in driver cancels: now the site would be uncovered.
    observations.append(
        sentinel.observe(
            WorldEvent(kind="resource_offline", resource_id="avery", note="Avery becomes unavailable")
        )
    )

    # 5) The coordinator recruits Jordan; the sentinel improves coverage.
    observations.append(
        sentinel.observe(
            WorldEvent(
                kind="resource_added",
                resource=_volunteer(
                    "jordan-recruited",
                    "Jordan Hale",
                    "van_certified_driver",
                    "Second Harvest",
                    opted_in=True,
                    reliability=0.91,
                ),
                note="Coordinator recruits Jordan for Thursday Eastside",
            )
        )
    )

    return observations


_ACTION_TAG: dict[str, str] = {
    "silent": "[ ok ]  silent",
    "auto_recomposed": "[auto]  recomposed silently",
    "escalated": "[!!!!]  ESCALATED",
    "improved": "[ up ]  improved",
    "resolved": "[ ok ]  RESOLVED",
}


_NOTIFICATION_TAG: dict[str, str] = {
    "sent": "notified",
    "dry_run": "not sent (dry run)",
    "skipped_unconfigured": "no channel configured - would notify",
    "skipped_below_threshold": "below the configured severity threshold",
    "failed": "DELIVERY FAILED (monitoring continues)",
}


def _notification_line(notification: NotificationResult | None) -> str | None:
    """Render one human-readable delivery line for an escalation, if any."""

    if notification is None:
        return None
    tag = _NOTIFICATION_TAG.get(notification.status, notification.status)
    if notification.status == "skipped_unconfigured":
        return f"    -> {tag}"
    return f"    -> {tag}: {notification.target} ({notification.channel})"


def _resource_directory(observations: list[SentinelObservation]) -> dict[str, Resource]:
    """Map every id seen in the replay (roster + recruited people) to its record."""

    directory = {resource.id: resource for resource in build_demo_resources()}
    for observation in observations:
        if observation.event.resource is not None:
            directory[observation.event.resource.id] = observation.event.resource
    return directory


def _describe_person(directory: dict[str, Resource], resource_id: str) -> str:
    resource = directory.get(resource_id)
    if resource is None:
        return resource_id
    return f"{resource.name} ({resource.org})" if resource.org else resource.name


def _render_roster(on_duty: list[str]) -> list[str]:
    """List everyone the coordinator has, and what MealMesh may do with them."""

    lines = [
        "Roster — who exists, and what the agent is allowed to do with them:",
    ]
    for capability in CAPABILITY_ONTOLOGY:
        people = [
            resource
            for resource in build_demo_resources()
            if capability.code in resource.capability_codes
        ]
        if not people:
            continue
        lines.append(f"  {capability.label}")

        def _status(resource: Resource) -> tuple[int, str]:
            if resource.id in on_duty:
                return 0, "scheduled for Thursday Eastside"
            if resource.opted_in:
                return 1, "opted-in bench: the agent may fill this seat silently"
            return 2, "recruit only: a human must ask; never auto-assigned"

        for resource in sorted(people, key=lambda person: _status(person)[0]):
            lines.append(f"    - {resource.name} ({resource.org}) — {_status(resource)[1]}")
    lines.append("")
    return lines


def render_sentinel_log(observations: list[SentinelObservation]) -> str:
    """Render the monitoring timeline as a scannable, demo-ready report."""

    mission = build_demo_mission()
    directory = _resource_directory(observations)
    baseline_plan = observations[0].selected_resource_ids if observations else []

    lines: list[str] = [
        "=== MealMesh SENTINEL (autonomous community meal coverage) ===",
        "",
        "The job: one volunteer coordinator keeps a weekly meal site staffed.",
        "The problem: most 'I can't make Thursday' texts are routine. A few mean the",
        "site cannot open, and by the time a human notices it is too late to fix.",
        "The agent: refill the seat from the opted-in bench without asking anyone;",
        "speak up only when the site would actually go uncovered.",
        "",
        f"Coverage window: {mission.destination} — Thursday 4:00pm.",
        f"Every seat must be filled: {', '.join(mission.requirements)}.",
        "Policy: work silently; alert a human only when a site would go uncovered.",
        "Data: SIMULATED volunteers, organizations, and sites.",
        "",
    ]
    lines += _render_roster(baseline_plan)

    escalations = 0
    autonomous = 0
    delivered = 0
    previous_plan: list[str] = []
    for index, observation in enumerate(observations):
        header = "baseline" if observation.event.kind == "baseline" else (observation.event.note or observation.event.kind)
        lines.append(f"- {header}")
        tag = _ACTION_TAG.get(observation.action, observation.action)
        plan = ", ".join(observation.selected_resource_ids) or "none"
        lines.append(f"    {tag} | verdict: {observation.verdict} | plan: {plan}")

        added = [rid for rid in observation.selected_resource_ids if rid not in previous_plan]
        dropped = [rid for rid in previous_plan if rid not in observation.selected_resource_ids]
        if index > 0 and added and dropped:
            lines.append(
                "    who moved: "
                + ", ".join(_describe_person(directory, rid) for rid in added)
                + " takes over from "
                + ", ".join(_describe_person(directory, rid) for rid in dropped)
            )

        if observation.escalation is not None:
            escalations += 1
            escalation = observation.escalation
            lines.append(f"    -> DECISION NEEDED ({escalation.severity}): {escalation.decision_required}")
            lines.append("    coordinator: phone buzzes — only a human can add a new person")
            notification_line = _notification_line(observation.notification)
            if notification_line is not None:
                lines.append(notification_line)
            if observation.notification is not None and observation.notification.delivered:
                delivered += 1
        elif observation.action in ("silent", "auto_recomposed", "improved", "resolved"):
            autonomous += 1
            if observation.action in ("improved", "resolved"):
                lines.append("    coordinator: their recruit landed — coverage restored, no new alert")
            else:
                lines.append("    coordinator: nothing sent — the site stays covered by itself")
        previous_plan = observation.selected_resource_ids
        lines.append("")

    lines.append(
        f"Summary: {len(observations)} observations | "
        f"{autonomous} handled autonomously | {escalations} escalated to a human | "
        f"{delivered} alert(s) delivered."
    )
    lines += [
        "",
        "Why this is the point:",
        f"  - {autonomous} changes were absorbed in the background; the coordinator never saw them.",
        f"  - {escalations} interruptions were real, and each one named the missing role and who to ask.",
        "  - A language model read the messages. It never picked a volunteer:",
        "    the CP-SAT solver chose every seat, and only from people who opted in.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    """Run the demo timeline.

    ``--notify`` opts in to real delivery through the configured channel; by
    default the demo is a dry run so it can be replayed freely.
    """

    configure_logging(level=logging.WARNING, json_format=False)
    live = "--notify" in sys.argv[1:]
    notifier = build_notifier() if live else None
    print(render_sentinel_log(run_sentinel_demo(notifier=notifier)))


if __name__ == "__main__":
    main()
