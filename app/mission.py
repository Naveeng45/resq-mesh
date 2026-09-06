from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.pydantic_compat import CompatBaseModel

CRITICAL_MISSION_FIELDS: tuple[str, ...] = ("destination", "deadline", "incident_type")


class Mission(CompatBaseModel):
    """Structured incident facts extracted from a natural-language request."""

    model_config = ConfigDict(extra="forbid")

    destination: str | None = Field(
        default=None,
        description="Destination or affected location mentioned by the user. Use null if missing.",
    )
    deadline: datetime | None = Field(
        default=None,
        description="Explicit deadline or target time in ISO 8601 form. Use null if missing.",
    )
    incident_type: str | None = Field(
        default=None,
        description="Incident type stated by the user, such as flood. Use null if missing.",
    )
    requirements: list[str] = Field(
        default_factory=list,
        description="Explicit resources or needs mentioned by the user. These are facts, not approved doctrine.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints, limits, or blockers mentioned by the user.",
    )


class MissionReview(CompatBaseModel):
    """Deterministic validation outcome for a structured mission."""

    status: Literal["ready", "needs_clarification"]
    missing_critical_facts: list[str] = Field(default_factory=list)


def review_mission(mission: Mission) -> MissionReview:
    """Apply deterministic validation rules to the extracted facts."""

    missing = [
        field_name
        for field_name in CRITICAL_MISSION_FIELDS
        if getattr(mission, field_name) in (None, "")
    ]
    return MissionReview(
        status="ready" if not missing else "needs_clarification",
        missing_critical_facts=missing,
    )
