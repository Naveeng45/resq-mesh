"""Phase 1 — Typed domain contracts for joint planning and recovery.

These models represent the richer planning domain needed for coalition planning,
capability-aware assignment, counterfactual testing, and plan lifecycle.

They coexist with the original ``Mission``, ``Resource``, and ``CoalitionSolution``
models which remain the API-facing contracts. These contracts are the internal
representation used by the joint planner and recovery engine.

ALL data in fixtures is SIMULATED. Production rules require operator validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.pydantic_compat import CompatBaseModel


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

US_PACIFIC = timezone(timedelta(hours=-7), name="US/Pacific")


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class PlanStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    COMPLETED = "completed"


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TIMED_OUT = "timed_out"


class EventKind(str, Enum):
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    PLAN_PROPOSED = "plan_proposed"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    PLAN_SUPERSEDED = "plan_superseded"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    VOLUNTEER_CONFIRMED = "volunteer_confirmed"
    VOLUNTEER_DECLINED = "volunteer_declined"
    RECOVERY_TRIGGERED = "recovery_triggered"
    CONSTRAINT_VIOLATION = "constraint_violation"


class DataProvenance(str, Enum):
    """Whether a value comes from a live system or was synthesized for demo."""
    SIMULATED = "simulated"
    OPERATOR_PROVIDED = "operator_provided"
    LIVE_SYSTEM = "live_system"


# ---------------------------------------------------------------------------
# Time window
# ---------------------------------------------------------------------------


class TimeWindow(CompatBaseModel):
    """A timezone-aware interval. Both endpoints are required and tz-aware."""

    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _check_order_and_tz(self) -> TimeWindow:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("TimeWindow start and end must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("TimeWindow end must be after start")
        return self


# ---------------------------------------------------------------------------
# Travel estimate
# ---------------------------------------------------------------------------


class TravelEstimate(CompatBaseModel):
    """Travel time from a resource to a destination.

    Unknown travel time must NOT silently become zero; use ``unknown=True`` and
    ``estimated_minutes=None`` instead.
    """

    model_config = ConfigDict(extra="forbid")

    origin_id: str
    destination_id: str
    estimated_minutes: float | None = None
    distance_km: float | None = None
    unknown: bool = False
    provenance: DataProvenance = DataProvenance.SIMULATED

    @model_validator(mode="after")
    def _unknown_consistency(self) -> TravelEstimate:
        if self.unknown and self.estimated_minutes is not None:
            raise ValueError(
                "Travel estimate marked unknown but has estimated_minutes; "
                "set estimated_minutes=None or unknown=False"
            )
        if not self.unknown and self.estimated_minutes is None:
            raise ValueError(
                "Travel estimate is not marked unknown but estimated_minutes is None; "
                "set unknown=True or provide estimated_minutes"
            )
        return self


# ---------------------------------------------------------------------------
# Task (a unit of work within a mission)
# ---------------------------------------------------------------------------


class TaskDefinition(CompatBaseModel):
    """One task required by a mission (e.g. 'drive van', 'handle food')."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    label: str
    required_capability: str
    duration_minutes: float = Field(gt=0)
    time_window: TimeWindow | None = None
    depends_on: list[str] = Field(
        default_factory=list,
        description="Task IDs that must complete before this task can start.",
    )


# ---------------------------------------------------------------------------
# Mission (enriched)
# ---------------------------------------------------------------------------


class MissionSpec(CompatBaseModel):
    """A fully-typed mission specification for joint planning.

    Extends the original ``Mission`` with ID, version, location, timezone,
    time windows, structured tasks, and policy-approved flexibility.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    version: int = Field(default=1, ge=1)

    # Location
    destination: str
    destination_id: str
    location_coords: list[float] | None = Field(
        default=None,
        description="[lat, lng] — None when unknown.",
    )
    mission_timezone: str = Field(
        default="US/Pacific",
        description="IANA timezone name for this mission.",
    )

    # Time
    service_window: TimeWindow
    deadline: datetime

    # Requirements
    incident_type: str
    required_roles: list[str] = Field(
        default_factory=list,
        description="Capability codes required for this mission.",
    )
    tasks: list[TaskDefinition] = Field(default_factory=list)
    requested_quantity: int | None = Field(
        default=None, ge=0,
        description="Meals / items requested, when known.",
    )

    # Constraints and policy
    constraints: list[str] = Field(default_factory=list)
    permitted_start_adjustment_minutes: float = Field(
        default=0.0, ge=0.0,
        description="Operator-approved flexibility for start time shift.",
    )

    # Provenance
    provenance: DataProvenance = DataProvenance.SIMULATED

    @field_validator("deadline")
    @classmethod
    def _tz_aware_deadline(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("deadline must be timezone-aware")
        return v

    @field_validator("location_coords")
    @classmethod
    def _valid_coords(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != 2:
            raise ValueError("location_coords must be [lat, lng]")
        return v


# ---------------------------------------------------------------------------
# Volunteer (enriched)
# ---------------------------------------------------------------------------


class AvailabilityInterval(CompatBaseModel):
    """A window during which a volunteer is available."""

    model_config = ConfigDict(extra="forbid")

    window: TimeWindow
    provenance: DataProvenance = DataProvenance.SIMULATED


class Commitment(CompatBaseModel):
    """An accepted assignment binding a volunteer to a plan."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    mission_id: str
    task_id: str
    confirmation: ConfirmationStatus = ConfirmationStatus.PENDING


class VolunteerSpec(CompatBaseModel):
    """A volunteer with verified qualifications and availability.

    Qualifications and site permissions must be explicit — a volunteer without
    ``site_keyholder`` in ``capability_codes`` cannot open a site, even if they
    are listed on its roster.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    capability_codes: list[str] = Field(default_factory=list)
    availability_intervals: list[AvailabilityInterval] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    authorized_site_ids: list[str] = Field(
        default_factory=list,
        description="Site IDs this volunteer has access to. '*' means all.",
    )
    eligible_vehicle_ids: list[str] = Field(
        default_factory=list,
        description="Vehicle IDs this volunteer is certified to drive.",
    )
    opted_in: bool = False
    org: str = ""

    # Location freshness
    location_label: str = ""
    location_coords: list[float] | None = None
    location_updated_at: datetime | None = None
    travel_estimates: list[TravelEstimate] = Field(default_factory=list)

    provenance: DataProvenance = DataProvenance.SIMULATED

    def is_available_during(self, window: TimeWindow) -> bool:
        """True if at least one availability interval fully covers the window."""
        return any(
            interval.window.start <= window.start and interval.window.end >= window.end
            for interval in self.availability_intervals
        )

    def has_capability(self, code: str) -> bool:
        return code in self.capability_codes

    def has_site_access(self, site_id: str) -> bool:
        return "*" in self.authorized_site_ids or site_id in self.authorized_site_ids

    def overlapping_commitments(self, window: TimeWindow) -> list[Commitment]:
        """Return commitments whose task could overlap with the given window.

        Note: without task time windows stored on commitments, this returns
        all active commitments. The caller must cross-reference with plan data.
        """
        return [c for c in self.commitments if c.confirmation != ConfirmationStatus.DECLINED]


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------


class VehicleSpec(CompatBaseModel):
    """A vehicle with explicit capacity, availability, and driver eligibility."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    capacity: int = Field(ge=0)
    capacity_unit: str = Field(default="meals", description="Explicit unit for capacity.")
    availability_intervals: list[AvailabilityInterval] = Field(default_factory=list)
    eligible_driver_ids: list[str] = Field(
        default_factory=list,
        description="Volunteer IDs certified to drive this vehicle.",
    )
    equipment_capabilities: list[str] = Field(
        default_factory=list,
        description="E.g. ['refrigerated', 'wheelchair_lift'].",
    )
    org: str = ""
    provenance: DataProvenance = DataProvenance.SIMULATED

    def is_available_during(self, window: TimeWindow) -> bool:
        return any(
            interval.window.start <= window.start and interval.window.end >= window.end
            for interval in self.availability_intervals
        )

    def has_eligible_driver(self, volunteer_ids: list[str]) -> bool:
        """True if at least one of the given volunteers can drive this vehicle."""
        return bool(set(self.eligible_driver_ids) & set(volunteer_ids))


# ---------------------------------------------------------------------------
# Task Assignment (inside a plan)
# ---------------------------------------------------------------------------


class TaskAssignment(CompatBaseModel):
    """Assigns a volunteer (and optionally a vehicle) to a task in a plan."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    volunteer_id: str
    vehicle_id: str | None = None
    scheduled_window: TimeWindow
    confirmation: ConfirmationStatus = ConfirmationStatus.PENDING


# ---------------------------------------------------------------------------
# Constraint Violation
# ---------------------------------------------------------------------------


class ConstraintViolation(CompatBaseModel):
    """A specific constraint that is violated, with explanation."""

    model_config = ConfigDict(extra="forbid")

    constraint_type: str = Field(
        description="E.g. 'capability_gap', 'time_overlap', 'no_eligible_driver', 'site_access'.",
    )
    description: str
    affected_resource_ids: list[str] = Field(default_factory=list)
    affected_task_ids: list[str] = Field(default_factory=list)
    severity: Literal["blocking", "warning"] = "blocking"


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


class PlanSpec(CompatBaseModel):
    """A versioned assignment plan for a mission.

    A proposal is not an active plan. Approval is not volunteer acceptance.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    mission_id: str
    version: int = Field(default=1, ge=1)
    input_snapshot_version: int = Field(
        default=1, ge=1,
        description="Version of mission/resource data this plan was built from.",
    )

    # Assignments
    assignments: list[TaskAssignment] = Field(default_factory=list)

    # Constraint evaluation
    violations: list[ConstraintViolation] = Field(default_factory=list)
    is_feasible: bool = False
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "NOT_SOLVED"] = "NOT_SOLVED"
    objective_value: float | None = None

    # Lifecycle
    status: PlanStatus = PlanStatus.PROPOSED
    proposed_at: datetime = Field(default_factory=_utc_now)
    approved_at: datetime | None = None
    approved_by: str | None = None

    # Confirmations
    outstanding_confirmations: list[str] = Field(
        default_factory=list,
        description="Volunteer IDs that have not yet confirmed.",
    )

    # Provenance
    provenance: DataProvenance = DataProvenance.SIMULATED

    @property
    def all_confirmed(self) -> bool:
        return all(
            a.confirmation == ConfirmationStatus.ACCEPTED for a in self.assignments
        )


# ---------------------------------------------------------------------------
# Resource Unavailable Event
# ---------------------------------------------------------------------------


class ResourceUnavailableEvent(CompatBaseModel):
    """Records that a resource became unavailable."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    resource_id: str
    resource_type: Literal["volunteer", "vehicle"]
    reason: str
    occurred_at: datetime = Field(default_factory=_utc_now)
    affected_plan_ids: list[str] = Field(default_factory=list)
    affected_mission_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Recovery Proposal
# ---------------------------------------------------------------------------


class RecoveryProposal(CompatBaseModel):
    """A minimum-change replan proposal in response to a disruption."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    triggering_event_id: str
    original_plan_id: str
    proposed_plan: PlanSpec
    changes_summary: list[str] = Field(
        default_factory=list,
        description="Human-readable list of what changed.",
    )
    requires_approval: bool = True
    provenance: DataProvenance = DataProvenance.SIMULATED


# ---------------------------------------------------------------------------
# Approval Record
# ---------------------------------------------------------------------------


class ApprovalRecord(CompatBaseModel):
    """Records a human approval or rejection decision."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    plan_id: str
    decision: Literal["approved", "rejected"]
    decided_by: str
    decided_at: datetime = Field(default_factory=_utc_now)
    reason: str | None = None


# ---------------------------------------------------------------------------
# Mission Event (audit log)
# ---------------------------------------------------------------------------


class MissionEvent(CompatBaseModel):
    """An immutable event in a mission's lifecycle."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    mission_id: str
    kind: EventKind
    timestamp: datetime = Field(default_factory=_utc_now)
    payload: dict = Field(default_factory=dict)
    actor: str | None = None
    description: str = ""
