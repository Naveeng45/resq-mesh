from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from app.capabilities import resolve_capability_code as resolve_ontology_code
from app.pydantic_compat import CompatBaseModel


class Capability(CompatBaseModel):
    """A synthetic capability that a resource can provide."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    description: str
    synthetic_data: bool = True


class Resource(CompatBaseModel):
    """A synthetic volunteer or asset record used as deterministic world-state."""

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
    # Consent, not availability: an opted-in volunteer pre-authorized MealMesh to
    # fill a seat with them and send them the details without asking first.
    opted_in: bool = False
    org: str = ""
    synthetic_data: bool = True


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


CAPABILITY_CATALOG: tuple[Capability, ...] = (
    Capability(
        code="van_certified_driver",
        label="Van-certified driver",
        description="Drive a food-bank van for a community meal distribution.",
    ),
    Capability(
        code="food_handler",
        label="Food handler",
        description="Pack and handle food safely during a distribution.",
    ),
    Capability(
        code="site_keyholder",
        label="Site keyholder",
        description="Open, host, and secure a meal-distribution site.",
    ),
)


def _volunteer(
    resource_id: str,
    name: str,
    category: str,
    capability_code: str,
    location: str,
    org: str,
    reliability: float,
    *,
    opted_in: bool = True,
) -> Resource:
    """One volunteer row. Recruit-only people are also 'busy': a human must ask."""

    return Resource(
        id=resource_id,
        name=name,
        category=category,
        location=location,
        status="available" if opted_in else "busy",
        availability=opted_in,
        reliability=reliability,
        capacity=1,
        capacity_unit="site",
        capability_codes=[capability_code],
        opted_in=opted_in,
        org=org,
    )


def _van(resource_id: str, name: str, org: str, reliability: float) -> Resource:
    """A van is displayed as an asset; in v1 a driver already implies one."""

    return Resource(
        id=resource_id,
        name=name,
        category="van",
        location=org,
        status="available",
        availability=True,
        reliability=reliability,
        capacity=0,
        capacity_unit="asset",
        capability_codes=[],
        opted_in=True,
        org=org,
    )


RESOURCE_CATALOG: tuple[Resource, ...] = (
    # --- Van-certified drivers ---
    _volunteer("maya", "Maya Chen", "driver", "van_certified_driver", "Eastside", "Riverside Church", 0.96),
    _volunteer("luis", "Luis Okonkwo", "driver", "van_certified_driver", "Food bank bench", "Second Harvest", 0.93),
    _volunteer("avery", "Avery Reed", "driver", "van_certified_driver", "Food bank bench", "Second Harvest", 0.88),
    _volunteer("dana", "Dana Whitfield", "driver", "van_certified_driver", "Harbor", "Eastside Mutual Aid", 0.90),
    _volunteer("tariq", "Tariq Nasser", "driver", "van_certified_driver", "West End", "Second Harvest", 0.92),
    _volunteer("gina", "Gina Petrov", "driver", "van_certified_driver", "Church bench", "Riverside Church", 0.85),
    _volunteer(
        "jordan", "Jordan Hale", "driver", "van_certified_driver",
        "Recruit list", "Second Harvest", 0.91, opted_in=False,
    ),
    _volunteer(
        "marcus", "Marcus Bell", "driver", "van_certified_driver",
        "Recruit list", "Eastside Mutual Aid", 0.87, opted_in=False,
    ),
    # --- Food handlers ---
    _volunteer("priya", "Priya Shah", "food handler", "food_handler", "Eastside", "Riverside Church", 0.95),
    _volunteer("sam", "Sam Ortiz", "food handler", "food_handler", "Church bench", "Riverside Church", 0.92),
    _volunteer("riley", "Riley Morgan", "food handler", "food_handler", "Church bench", "Riverside Church", 0.87),
    _volunteer("hana", "Hana Suzuki", "food handler", "food_handler", "Harbor", "Eastside Mutual Aid", 0.94),
    _volunteer("diego", "Diego Ramos", "food handler", "food_handler", "West End", "Second Harvest", 0.90),
    _volunteer("bea", "Bea Lindqvist", "food handler", "food_handler", "Harbor", "Eastside Mutual Aid", 0.86),
    _volunteer(
        "tom", "Tom Fielding", "food handler", "food_handler",
        "Recruit list", "Riverside Church", 0.84, opted_in=False,
    ),
    # --- Site keyholders ---
    _volunteer("elena", "Elena Brooks", "site keyholder", "site_keyholder", "Eastside", "Riverside Church", 0.97),
    _volunteer("noah", "Noah Kim", "site keyholder", "site_keyholder", "Food bank bench", "Second Harvest", 0.90),
    _volunteer("carmen", "Carmen Diaz", "site keyholder", "site_keyholder", "Harbor", "Eastside Mutual Aid", 0.93),
    _volunteer("wes", "Wes Turner", "site keyholder", "site_keyholder", "West End", "Second Harvest", 0.89),
    _volunteer("fiona", "Fiona Adeyemi", "site keyholder", "site_keyholder", "Church bench", "Riverside Church", 0.84),
    # --- Assets ---
    _van("van-fb-1", "Food Bank Van 1", "Second Harvest", 0.94),
    _van("van-fb-2", "Food Bank Van 2", "Second Harvest", 0.90),
    _van("van-church-1", "Church Van", "Riverside Church", 0.92),
)


def list_capabilities() -> list[Capability]:
    """Return a copy of the synthetic capability catalog."""

    return [capability.model_copy(deep=True) for capability in CAPABILITY_CATALOG]


def list_resources() -> list[Resource]:
    """Return a copy of the synthetic resource catalog."""

    return [resource.model_copy(deep=True) for resource in RESOURCE_CATALOG]


def list_available_resources() -> list[Resource]:
    """Return resources available and pre-authorized for automatic assignment.

    This is the hard boundary around the solver: CP-SAT may only ever see people
    who opted in to being scheduled without being asked first.
    """

    return [
        resource
        for resource in list_resources()
        if resource.availability and resource.status == "available" and resource.opted_in
    ]


def list_recruit_candidates(capability_code: str) -> list[Resource]:
    """Return named, non-opted-in people a coordinator may choose to recruit."""

    return [
        resource
        for resource in list_resources()
        if not resource.opted_in and capability_code in resource.capability_codes
    ]


def resolve_capability_code(required_capability: str) -> str | None:
    """Normalize a requested capability into a known capability code."""

    code = resolve_ontology_code(required_capability)
    known_codes = {capability.code for capability in CAPABILITY_CATALOG}
    return code if code in known_codes else None


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
