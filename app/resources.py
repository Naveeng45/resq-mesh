from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from app.pydantic_compat import CompatBaseModel


class Capability(CompatBaseModel):
    """A synthetic capability that a resource can provide."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    description: str
    synthetic_data: bool = True


class Resource(CompatBaseModel):
    """A synthetic resource record used as deterministic world-state."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    location: str
    status: Literal["available", "maintenance", "offline", "busy"]
    availability: bool
    reliability: float = Field(ge=0.0, le=1.0)
    capacity: int | None = Field(default=None, ge=0)
    capacity_unit: str | None = None
    capability_codes: list[str] = Field(default_factory=list)
    synthetic_data: bool = True


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


CAPABILITY_CATALOG: tuple[Capability, ...] = (
    Capability(
        code="road_transport",
        label="Road Transport",
        description="Move supplies and personnel on passable roads.",
    ),
    Capability(
        code="flood_access",
        label="Flood Access",
        description="Reach or operate in flooded areas.",
    ),
    Capability(
        code="field_triage",
        label="Field Triage",
        description="Assess and stabilize patients on site.",
    ),
    Capability(
        code="communications",
        label="Communications",
        description="Provide emergency communication support.",
    ),
)


RESOURCE_CATALOG: tuple[Resource, ...] = (
    Resource(
        id="truck-01",
        name="Heavy Rescue Truck",
        category="ground transport",
        location="Albany Depot",
        status="available",
        availability=True,
        reliability=0.96,
        capacity=1200,
        capacity_unit="kg",
        capability_codes=("road_transport",),
    ),
    Resource(
        id="boat-07",
        name="Flood Rescue Boat",
        category="water rescue",
        location="Harbor Dock",
        status="maintenance",
        availability=False,
        reliability=0.74,
        capacity=8,
        capacity_unit="people",
        capability_codes=("flood_access",),
    ),
    Resource(
        id="drone-02",
        name="High-Water Drone",
        category="aerial support",
        location="Airfield Hangar",
        status="available",
        availability=True,
        reliability=0.89,
        capacity=2,
        capacity_unit="people",
        capability_codes=("flood_access",),
    ),
    Resource(
        id="med-team-alpha",
        name="Medical Team Alpha",
        category="field care",
        location="North Clinic",
        status="available",
        availability=True,
        reliability=0.91,
        capacity=6,
        capacity_unit="patients",
        capability_codes=("field_triage",),
    ),
    Resource(
        id="satcom-01",
        name="Satellite Comms Kit",
        category="communications",
        location="Command Post",
        status="available",
        availability=True,
        reliability=0.86,
        capacity=None,
        capacity_unit=None,
        capability_codes=("communications",),
    ),
)


def list_capabilities() -> list[Capability]:
    """Return a copy of the synthetic capability catalog."""

    return [capability.model_copy(deep=True) for capability in CAPABILITY_CATALOG]


def list_resources() -> list[Resource]:
    """Return a copy of the synthetic resource catalog."""

    return [resource.model_copy(deep=True) for resource in RESOURCE_CATALOG]


def list_available_resources() -> list[Resource]:
    """Return only resources that are currently available."""

    return [
        resource
        for resource in list_resources()
        if resource.availability and resource.status == "available"
    ]


def resolve_capability_code(required_capability: str) -> str | None:
    """Normalize a requested capability into a known capability code."""

    normalized = _normalize_text(required_capability)
    for capability in CAPABILITY_CATALOG:
        if normalized in {
            _normalize_text(capability.code),
            _normalize_text(capability.label),
        }:
            return capability.code
    return None


def get_resources_by_required_capability(required_capability: str) -> list[Resource]:
    """Return available resources that explicitly advertise the requested capability."""

    capability_code = resolve_capability_code(required_capability)
    if capability_code is None:
        return []

    return [
        resource
        for resource in list_available_resources()
        if capability_code in resource.capability_codes
    ]
