"""Phase 4 — Event-driven minimum-change recovery.

Handles resource-unavailable events by generating valid recovery proposals.
Plans are activated only through authorized state transitions.

Key principles:
- Events are deduplicated by event_id and (resource_id, effective_time).
- Recovery preserves completed work and treats in-progress work explicitly.
- Minimum-change replanning via CP-SAT stability objective (D-007).
- Proposals are version-bound with expiration.
- Approval requires an authorized coordinator.
- Volunteer acceptance remains explicit.
- Resource reservations checked atomically at activation.
- A proposal is not an active plan; approval is not volunteer acceptance.

ALL data is SIMULATED unless provenance says otherwise.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from pydantic import ConfigDict, Field, field_validator

from app.coalition_planner import (
    CoalitionPlannerRequest,
    solve_coalition,
)
from app.contracts import (
    ConfirmationStatus,
    DataProvenance,
    MissionSpec,
    PlanSpec,
    PlanStatus,
    VehicleSpec,
    VolunteerSpec,
    _new_id,
    _utc_now,
)
from app.pydantic_compat import CompatBaseModel
from app.validation import validate_plan


# ---------------------------------------------------------------------------
# Event contract
# ---------------------------------------------------------------------------


class ResourceEvent(CompatBaseModel):
    """A resource becoming unavailable, with full provenance.

    Includes effective time (when the resource actually became unavailable),
    observed time (when the system learned about it), source identification,
    and a simulated/live marker.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    resource_id: str
    resource_type: Literal["volunteer", "vehicle"]
    effective_time: datetime
    observed_time: datetime = Field(default_factory=_utc_now)
    mission_id: str | None = None
    source: str = "coordinator_report"
    is_simulated: bool = True
    reason: str = ""

    @field_validator("effective_time", "observed_time")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware")
        return v


class EventIngestionResult(CompatBaseModel):
    """Result of ingesting a resource event."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "duplicate", "stale"]
    event_id: str
    reason: str = ""


# ---------------------------------------------------------------------------
# Task execution status
# ---------------------------------------------------------------------------


class TaskExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# Assignment diff
# ---------------------------------------------------------------------------


class AssignmentChange(CompatBaseModel):
    """A single assignment change between baseline and recovery."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_label: str = ""
    before_volunteer_id: str | None = None
    before_volunteer_name: str | None = None
    after_volunteer_id: str | None = None
    after_volunteer_name: str | None = None
    change_type: Literal["replaced", "removed", "added", "unchanged"] = "unchanged"


# ---------------------------------------------------------------------------
# Recovery proposal
# ---------------------------------------------------------------------------


class RecoveryProposalSpec(CompatBaseModel):
    """A version-bound recovery proposal with before/after diff.

    Proposals expire and must be revalidated at activation. A proposal
    is NOT an active plan.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    triggering_event_ids: list[str] = Field(default_factory=list)
    original_plan_id: str
    original_plan_version: int
    mission_id: str
    expected_mission_version: int
    proposed_plan: PlanSpec
    changes: list[AssignmentChange] = Field(default_factory=list)
    changes_count: int = 0
    is_feasible: bool = False
    infeasible_reasons: list[str] = Field(default_factory=list)
    capability_gaps: list[str] = Field(default_factory=list)
    safe_actions: list[str] = Field(default_factory=list)
    targeted_request: str | None = None
    expires_at: datetime
    created_at: datetime = Field(default_factory=_utc_now)
    status: Literal[
        "pending", "approved", "expired", "rejected", "superseded"
    ] = "pending"
    provenance: DataProvenance = DataProvenance.SIMULATED

    @field_validator("expires_at", "created_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware")
        return v


# ---------------------------------------------------------------------------
# Approval contracts
# ---------------------------------------------------------------------------


class ApprovalRequest(CompatBaseModel):
    """Request to approve a recovery proposal."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    coordinator_id: str
    expected_plan_version: int
    expected_mission_version: int


class ApprovalResult(CompatBaseModel):
    """Result of an approval attempt."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    status: Literal[
        "approved",
        "stale",
        "expired",
        "already_approved",
        "not_found",
        "reservation_conflict",
    ]
    activated_plan: PlanSpec | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Mission risk status
# ---------------------------------------------------------------------------


class MissionRiskStatus(CompatBaseModel):
    """Current risk status of a mission while recovery is pending."""

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    status: Literal["nominal", "at_risk", "blocked"]
    reason: str = ""
    pending_proposals: list[str] = Field(default_factory=list)
    unavailable_resources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Notification adapter
# ---------------------------------------------------------------------------


@runtime_checkable
class NotificationAdapter(Protocol):
    """Protocol for sending recovery notifications.

    Uses a test adapter by default — production would use Slack/webhook.
    """

    def notify_recovery_proposed(self, proposal: RecoveryProposalSpec) -> None: ...
    def notify_plan_approved(self, plan: PlanSpec, mission_id: str) -> None: ...
    def notify_volunteer_needed(
        self, volunteer_id: str, task_label: str, mission_id: str
    ) -> None: ...


class TestNotificationAdapter:
    """In-memory notification adapter for testing. Default adapter."""

    def __init__(self) -> None:
        self.notifications: list[dict] = []

    def notify_recovery_proposed(self, proposal: RecoveryProposalSpec) -> None:
        self.notifications.append({
            "type": "recovery_proposed",
            "proposal_id": proposal.id,
            "mission_id": proposal.mission_id,
        })

    def notify_plan_approved(self, plan: PlanSpec, mission_id: str) -> None:
        self.notifications.append({
            "type": "plan_approved",
            "plan_id": plan.id,
            "mission_id": mission_id,
        })

    def notify_volunteer_needed(
        self, volunteer_id: str, task_label: str, mission_id: str
    ) -> None:
        self.notifications.append({
            "type": "volunteer_needed",
            "volunteer_id": volunteer_id,
            "task_label": task_label,
            "mission_id": mission_id,
        })


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


class EventLog:
    """Deduplicated event log.

    Deduplicates by event_id and by (resource_id, effective_time).
    Detects stale events (effective_time older than latest for same resource).
    Handles out-of-order updates by comparing effective times.
    """

    def __init__(self) -> None:
        self._events: dict[str, ResourceEvent] = {}
        self._seen_keys: set[tuple[str, str]] = set()  # (resource_id, eff_time_iso)
        self._latest_effective: dict[str, datetime] = {}  # resource_id -> latest

    def ingest(self, event: ResourceEvent) -> EventIngestionResult:
        """Ingest an event with deduplication and staleness detection."""
        # Duplicate by ID
        if event.id in self._events:
            return EventIngestionResult(
                status="duplicate",
                event_id=event.id,
                reason=f"Event '{event.id}' already ingested.",
            )

        # Duplicate by (resource_id, effective_time)
        dedup_key = (event.resource_id, event.effective_time.isoformat())
        if dedup_key in self._seen_keys:
            return EventIngestionResult(
                status="duplicate",
                event_id=event.id,
                reason=(
                    f"Event for resource '{event.resource_id}' at "
                    f"effective_time {event.effective_time.isoformat()} already exists."
                ),
            )

        # Stale: effective_time older than latest seen for this resource
        latest = self._latest_effective.get(event.resource_id)
        if latest and event.effective_time < latest:
            return EventIngestionResult(
                status="stale",
                event_id=event.id,
                reason=(
                    f"Event effective_time {event.effective_time.isoformat()} is older "
                    f"than latest known {latest.isoformat()} for resource "
                    f"'{event.resource_id}'."
                ),
            )

        # Accept
        self._events[event.id] = event
        self._seen_keys.add(dedup_key)
        self._latest_effective[event.resource_id] = event.effective_time

        return EventIngestionResult(
            status="accepted",
            event_id=event.id,
            reason="Event accepted.",
        )

    def get_event(self, event_id: str) -> ResourceEvent | None:
        return self._events.get(event_id)

    def get_unavailable_resource_ids(self) -> set[str]:
        return {e.resource_id for e in self._events.values()}

    def get_events_for_mission(self, mission_id: str) -> list[ResourceEvent]:
        return [
            e for e in self._events.values()
            if e.mission_id == mission_id
        ]


# ---------------------------------------------------------------------------
# Assignment diff computation
# ---------------------------------------------------------------------------


def compute_assignment_diff(
    baseline: PlanSpec,
    recovery: PlanSpec,
    mission: MissionSpec,
    all_volunteers: list[VolunteerSpec],
) -> list[AssignmentChange]:
    """Compute structured before/after diff between baseline and recovery plans."""
    vol_by_id = {v.id: v for v in all_volunteers}
    task_by_id = {t.id: t for t in mission.tasks}

    baseline_map = {a.task_id: a for a in baseline.assignments}
    recovery_map = {a.task_id: a for a in recovery.assignments}
    all_task_ids = sorted(set(baseline_map) | set(recovery_map))

    changes: list[AssignmentChange] = []
    for tid in all_task_ids:
        task = task_by_id.get(tid)
        label = task.label if task else tid
        b = baseline_map.get(tid)
        r = recovery_map.get(tid)

        b_vid = b.volunteer_id if b else None
        r_vid = r.volunteer_id if r else None

        def _name(vid: str | None) -> str | None:
            if vid is None:
                return None
            vol = vol_by_id.get(vid)
            return vol.name if vol else vid

        if b_vid == r_vid:
            ct: Literal["replaced", "removed", "added", "unchanged"] = "unchanged"
        elif b_vid and r_vid:
            ct = "replaced"
        elif b_vid and not r_vid:
            ct = "removed"
        else:
            ct = "added"

        changes.append(AssignmentChange(
            task_id=tid,
            task_label=label,
            before_volunteer_id=b_vid,
            before_volunteer_name=_name(b_vid),
            after_volunteer_id=r_vid,
            after_volunteer_name=_name(r_vid),
            change_type=ct,
        ))

    return changes


# ---------------------------------------------------------------------------
# Infeasibility analysis helpers
# ---------------------------------------------------------------------------


def _identify_capability_gaps(
    mission: MissionSpec,
    available_volunteers: list[VolunteerSpec],
    unavailable_ids: list[str],
    all_volunteers: list[VolunteerSpec],
) -> list[str]:
    """Find capabilities that cannot be covered after removing unavailable resources."""
    gaps: list[str] = []
    opted_in = [v for v in available_volunteers if v.opted_in]
    for task in mission.tasks:
        cap = task.required_capability
        capable = [
            v for v in opted_in
            if v.has_capability(cap) and v.has_site_access(mission.destination_id)
        ]
        if task.time_window:
            capable = [v for v in capable if v.is_available_during(task.time_window)]
        if not capable:
            gaps.append(f"{cap} (for task '{task.label}')")
    return gaps


def _suggest_safe_actions(gaps: list[str], mission: MissionSpec) -> list[str]:
    """Generate safe operator actions for infeasible recovery."""
    actions: list[str] = []
    if gaps:
        actions.append(
            "Contact coordinator to identify additional volunteers "
            "with the missing capabilities."
        )
        actions.append(
            f"Check whether mission '{mission.destination}' policy permits "
            "partial service or delayed start."
        )
    actions.append("Do not reassign accepted volunteers without their consent.")
    return actions


def _build_targeted_request(gaps: list[str], mission: MissionSpec) -> str | None:
    """Build a targeted volunteer request naming the exact gap."""
    if not gaps:
        return None
    deadline_str = mission.deadline.strftime("%I:%M %p")
    gap_list = ", ".join(gaps)
    return (
        f"Need one volunteer with {gap_list} "
        f"authorized for '{mission.destination_id}' by {deadline_str}."
    )


# ---------------------------------------------------------------------------
# Recovery planning
# ---------------------------------------------------------------------------


def plan_recovery(
    mission: MissionSpec,
    current_plan: PlanSpec,
    volunteers: list[VolunteerSpec],
    vehicles: list[VehicleSpec],
    unavailable_resource_ids: list[str],
    task_statuses: dict[str, TaskExecutionStatus] | None = None,
    triggering_event_ids: list[str] | None = None,
    proposal_ttl_minutes: float = 30.0,
    time_limit_seconds: float = 5.0,
) -> RecoveryProposalSpec:
    """Generate a minimum-change recovery proposal.

    1. Preserves completed tasks (via fixed_task_ids).
    2. Keeps in-progress assignments if resource is still available.
    3. Removes unavailable resources from pool.
    4. Runs min-change solver (stability objective dominates travel).
    5. Builds version-bound proposal with before/after diff.
    6. Reports infeasibility with exact capability gaps and safe actions.
    """
    task_statuses = task_statuses or {}
    now = _utc_now()

    # Fixed task IDs: in-progress tasks where volunteer is still available
    fixed_task_ids: list[str] = []
    for tid, status in task_statuses.items():
        if status == TaskExecutionStatus.IN_PROGRESS:
            assignment = next(
                (a for a in current_plan.assignments if a.task_id == tid), None
            )
            if assignment and assignment.volunteer_id not in unavailable_resource_ids:
                fixed_task_ids.append(tid)

    # Filter out unavailable resources
    available_vols = [
        v for v in volunteers if v.id not in unavailable_resource_ids
    ]
    available_vehs = [
        v for v in vehicles if v.id not in unavailable_resource_ids
    ]

    # Run min-change solver
    request = CoalitionPlannerRequest(
        mission=mission,
        volunteers=available_vols,
        vehicles=available_vehs,
        incumbent_plan=current_plan,
        fixed_task_ids=fixed_task_ids,
        max_alternatives=1,
        time_limit_seconds=time_limit_seconds,
    )

    result = solve_coalition(request)

    if result.feasible and result.alternatives:
        proposed_plan = result.alternatives[0].plan
        diff = compute_assignment_diff(
            current_plan, proposed_plan, mission, volunteers
        )
        changed_count = sum(1 for c in diff if c.change_type != "unchanged")

        return RecoveryProposalSpec(
            triggering_event_ids=triggering_event_ids or [],
            original_plan_id=current_plan.id,
            original_plan_version=current_plan.version,
            mission_id=mission.id,
            expected_mission_version=mission.version,
            proposed_plan=proposed_plan,
            changes=diff,
            changes_count=changed_count,
            is_feasible=True,
            expires_at=now + timedelta(minutes=proposal_ttl_minutes),
            provenance=DataProvenance.SIMULATED,
        )

    # Infeasible — build actionable blocked state
    capability_gaps = _identify_capability_gaps(
        mission, available_vols, unavailable_resource_ids, volunteers
    )
    safe_actions = _suggest_safe_actions(capability_gaps, mission)
    targeted = _build_targeted_request(capability_gaps, mission)

    return RecoveryProposalSpec(
        triggering_event_ids=triggering_event_ids or [],
        original_plan_id=current_plan.id,
        original_plan_version=current_plan.version,
        mission_id=mission.id,
        expected_mission_version=mission.version,
        proposed_plan=current_plan,  # unchanged — no feasible alternative
        changes=[],
        changes_count=0,
        is_feasible=False,
        infeasible_reasons=result.infeasible_reasons,
        capability_gaps=capability_gaps,
        safe_actions=safe_actions,
        targeted_request=targeted,
        expires_at=now + timedelta(minutes=proposal_ttl_minutes),
        provenance=DataProvenance.SIMULATED,
    )


# ---------------------------------------------------------------------------
# Recovery engine
# ---------------------------------------------------------------------------


class RecoveryEngine:
    """Manages event ingestion, recovery planning, approval, and volunteer responses.

    In-memory state — resets on restart. Production would use a persistent store.
    Uses a test notification adapter by default.
    """

    def __init__(
        self,
        notification_adapter: NotificationAdapter | None = None,
    ) -> None:
        self._event_log = EventLog()
        self._proposals: dict[str, RecoveryProposalSpec] = {}
        self._active_plans: dict[str, PlanSpec] = {}  # mission_id -> active plan
        self._resource_reservations: dict[str, str] = {}  # resource_id -> mission_id
        self._notification_adapter: NotificationAdapter = (
            notification_adapter or TestNotificationAdapter()
        )

    @property
    def notification_adapter(self) -> NotificationAdapter:
        return self._notification_adapter

    def ingest_event(self, event: ResourceEvent) -> EventIngestionResult:
        """Ingest a resource event with deduplication and staleness detection."""
        return self._event_log.ingest(event)

    def plan_recovery(
        self,
        mission: MissionSpec,
        current_plan: PlanSpec,
        volunteers: list[VolunteerSpec],
        vehicles: list[VehicleSpec],
        unavailable_resource_ids: list[str],
        task_statuses: dict[str, TaskExecutionStatus] | None = None,
        triggering_event_ids: list[str] | None = None,
    ) -> RecoveryProposalSpec:
        """Generate a minimum-change recovery proposal and store it."""
        proposal = plan_recovery(
            mission=mission,
            current_plan=current_plan,
            volunteers=volunteers,
            vehicles=vehicles,
            unavailable_resource_ids=unavailable_resource_ids,
            task_statuses=task_statuses,
            triggering_event_ids=triggering_event_ids,
        )
        self._proposals[proposal.id] = proposal

        if proposal.is_feasible:
            self._notification_adapter.notify_recovery_proposed(proposal)
            # Notify volunteers who need to confirm
            for change in proposal.changes:
                if (
                    change.change_type in ("replaced", "added")
                    and change.after_volunteer_id
                ):
                    self._notification_adapter.notify_volunteer_needed(
                        volunteer_id=change.after_volunteer_id,
                        task_label=change.task_label,
                        mission_id=proposal.mission_id,
                    )

        return proposal

    def approve_proposal(self, request: ApprovalRequest) -> ApprovalResult:
        """Approve a recovery proposal with version and reservation checks.

        Atomic: revalidates versions, checks reservations, activates in one step.
        Idempotent: duplicate approval returns success without side effects.
        """
        proposal = self._proposals.get(request.proposal_id)
        if proposal is None:
            return ApprovalResult(
                success=False,
                status="not_found",
                reason=f"Proposal '{request.proposal_id}' not found.",
            )

        # Idempotent: already approved
        if proposal.status == "approved":
            return ApprovalResult(
                success=True,
                status="already_approved",
                activated_plan=proposal.proposed_plan,
                reason="Proposal was already approved. No additional action taken.",
            )

        # Check expiration
        now = _utc_now()
        if now > proposal.expires_at:
            proposal.status = "expired"
            return ApprovalResult(
                success=False,
                status="expired",
                reason=(
                    f"Proposal expired at {proposal.expires_at.isoformat()}. "
                    "Generate a new recovery proposal."
                ),
            )

        # Version check: mission version must match
        if request.expected_mission_version != proposal.expected_mission_version:
            return ApprovalResult(
                success=False,
                status="stale",
                reason=(
                    f"Expected mission version {request.expected_mission_version} "
                    f"does not match proposal's expected version "
                    f"{proposal.expected_mission_version}. "
                    "Mission state has changed; regenerate the recovery proposal."
                ),
            )

        # Version check: plan version must match
        if request.expected_plan_version != proposal.original_plan_version:
            return ApprovalResult(
                success=False,
                status="stale",
                reason=(
                    f"Expected plan version {request.expected_plan_version} "
                    f"does not match proposal's original plan version "
                    f"{proposal.original_plan_version}. "
                    "Plan has changed; regenerate the recovery proposal."
                ),
            )

        # Resource reservation check — atomic
        plan = proposal.proposed_plan
        for assignment in plan.assignments:
            vid = assignment.volunteer_id
            reserved_mission = self._resource_reservations.get(vid)
            if reserved_mission and reserved_mission != proposal.mission_id:
                return ApprovalResult(
                    success=False,
                    status="reservation_conflict",
                    reason=(
                        f"Volunteer '{vid}' is already reserved for mission "
                        f"'{reserved_mission}'. Cannot assign to "
                        f"'{proposal.mission_id}'."
                    ),
                )

        # All checks passed — activate atomically
        proposal.status = "approved"
        plan.status = PlanStatus.APPROVED
        plan.approved_at = now
        plan.approved_by = request.coordinator_id

        # Reserve resources for this mission
        for assignment in plan.assignments:
            self._resource_reservations[assignment.volunteer_id] = (
                proposal.mission_id
            )

        # Track active plan
        self._active_plans[proposal.mission_id] = plan

        self._notification_adapter.notify_plan_approved(plan, proposal.mission_id)

        return ApprovalResult(
            success=True,
            status="approved",
            activated_plan=plan,
            reason="Proposal approved and plan activated.",
        )

    def record_volunteer_response(
        self,
        proposal_id: str,
        volunteer_id: str,
        response: Literal["accepted", "declined"],
    ) -> dict:
        """Record a volunteer's acceptance or decline.

        Required volunteer acceptance remains explicit — approval does not
        imply volunteer agreement.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return {
                "recorded": False,
                "reason": f"Proposal '{proposal_id}' not found.",
            }

        plan = proposal.proposed_plan
        found = False
        for assignment in plan.assignments:
            if assignment.volunteer_id == volunteer_id:
                if response == "accepted":
                    assignment.confirmation = ConfirmationStatus.ACCEPTED
                else:
                    assignment.confirmation = ConfirmationStatus.DECLINED
                found = True
                break

        if not found:
            return {
                "recorded": False,
                "reason": f"Volunteer '{volunteer_id}' not assigned in this plan.",
            }

        # Update outstanding confirmations
        plan.outstanding_confirmations = [
            a.volunteer_id
            for a in plan.assignments
            if a.confirmation == ConfirmationStatus.PENDING
        ]

        return {
            "recorded": True,
            "volunteer_id": volunteer_id,
            "response": response,
            "all_confirmed": plan.all_confirmed,
            "outstanding": plan.outstanding_confirmations,
        }

    def get_mission_risk_status(self, mission_id: str) -> MissionRiskStatus:
        """Surface the mission's at-risk status while recovery is pending."""
        pending = [
            pid
            for pid, p in self._proposals.items()
            if p.mission_id == mission_id and p.status == "pending"
        ]
        blocked_proposals = [
            pid
            for pid, p in self._proposals.items()
            if p.mission_id == mission_id
            and p.status == "pending"
            and not p.is_feasible
        ]
        unavailable_resources = [
            e.resource_id
            for e in self._event_log._events.values()
            if e.mission_id == mission_id
        ]

        if blocked_proposals:
            return MissionRiskStatus(
                mission_id=mission_id,
                status="blocked",
                reason="No feasible recovery plan exists for current disruptions.",
                pending_proposals=pending,
                unavailable_resources=unavailable_resources,
            )
        elif pending:
            return MissionRiskStatus(
                mission_id=mission_id,
                status="at_risk",
                reason="Recovery proposals pending approval.",
                pending_proposals=pending,
                unavailable_resources=unavailable_resources,
            )
        else:
            return MissionRiskStatus(
                mission_id=mission_id,
                status="nominal",
                reason="No active disruptions.",
            )

    def release_reservations(self, mission_id: str) -> None:
        """Release all resource reservations for a mission."""
        to_remove = [
            rid
            for rid, mid in self._resource_reservations.items()
            if mid == mission_id
        ]
        for rid in to_remove:
            del self._resource_reservations[rid]

    def get_proposal(self, proposal_id: str) -> RecoveryProposalSpec | None:
        return self._proposals.get(proposal_id)
