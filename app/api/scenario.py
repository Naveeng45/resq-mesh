"""Curated synthetic community-meal scenario for the MealMesh dashboard.

Everything here is SIMULATED data for the demo. Coordinates sit over a real
city so the map shows familiar streets, but the sites, volunteers, and their
positions are invented.

The program runs three weekly sites staffed by twenty volunteers from three
partner organizations. Two boundaries are enforced before CP-SAT ever runs:
only volunteers who opted in may be assigned silently (recruit-only people such
as Jordan wait for a human to ask), and only volunteers on a site's roster may
be assigned to that site.
"""

from __future__ import annotations

from typing import Iterable

from app.config import carto_tile_config
from app.hypergraph import CoalitionHyperedge
from app.mission import Mission
from app.resources import Resource

# --- Geography (synthetic positions over Sacramento) ---------------------------

REGION = {
    "center": [38.5816, -121.4944],
    "zoom": 12,
    "label": "Riverside meal sites (SIMULATED)",
}

# One row per resource: id, name, kind (map icon), capability, capacity, unit,
# reliability, base location label, and [lat, lng].
_RESOURCE_SPEC: tuple[dict, ...] = (
    # --- Van-certified drivers ---
    {
        "id": "maya", "name": "Maya Chen", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.96, "location": "Eastside", "coords": [38.574, -121.462],
        "org": "Riverside Church", "opted_in": True,
    },
    {
        "id": "luis", "name": "Luis Okonkwo", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.93, "location": "Food bank bench", "coords": [38.596, -121.505],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "avery", "name": "Avery Reed", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.88, "location": "Food bank bench", "coords": [38.604, -121.514],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "dana", "name": "Dana Whitfield", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.90, "location": "Harbor", "coords": [38.589, -121.528],
        "org": "Eastside Mutual Aid", "opted_in": True,
    },
    {
        "id": "tariq", "name": "Tariq Nasser", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.92, "location": "West End", "coords": [38.579, -121.545],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "gina", "name": "Gina Petrov", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.85, "location": "Church bench", "coords": [38.556, -121.492],
        "org": "Riverside Church", "opted_in": True,
    },
    {
        "id": "jordan", "name": "Jordan Hale", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.91, "location": "Recruit list", "coords": [38.610, -121.520],
        "org": "Second Harvest", "opted_in": False, "availability": False,
    },
    {
        "id": "marcus", "name": "Marcus Bell", "kind": "driver",
        "capability": "van_certified_driver", "capacity": 1, "unit": "site",
        "reliability": 0.87, "location": "Recruit list", "coords": [38.614, -121.511],
        "org": "Eastside Mutual Aid", "opted_in": False, "availability": False,
    },
    # --- Food handlers ---
    {
        "id": "priya", "name": "Priya Shah", "kind": "food",
        "capability": "food_handler", "capacity": 1, "unit": "site",
        "reliability": 0.95, "location": "Eastside", "coords": [38.568, -121.470],
        "org": "Riverside Church", "opted_in": True,
    },
    {
        "id": "sam", "name": "Sam Ortiz", "kind": "food",
        "capability": "food_handler", "capacity": 1, "unit": "site",
        "reliability": 0.92, "location": "Church bench", "coords": [38.557, -121.485],
        "org": "Riverside Church", "opted_in": True,
    },
    {
        "id": "riley", "name": "Riley Morgan", "kind": "food",
        "capability": "food_handler", "capacity": 1, "unit": "site",
        "reliability": 0.87, "location": "Church bench", "coords": [38.550, -121.495],
        "org": "Riverside Church", "opted_in": True,
    },
    {
        "id": "hana", "name": "Hana Suzuki", "kind": "food",
        "capability": "food_handler", "capacity": 1, "unit": "site",
        "reliability": 0.94, "location": "Harbor", "coords": [38.584, -121.534],
        "org": "Eastside Mutual Aid", "opted_in": True,
    },
    {
        "id": "diego", "name": "Diego Ramos", "kind": "food",
        "capability": "food_handler", "capacity": 1, "unit": "site",
        "reliability": 0.90, "location": "West End", "coords": [38.573, -121.551],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "bea", "name": "Bea Lindqvist", "kind": "food",
        "capability": "food_handler", "capacity": 1, "unit": "site",
        "reliability": 0.86, "location": "Harbor", "coords": [38.591, -121.538],
        "org": "Eastside Mutual Aid", "opted_in": True,
    },
    {
        "id": "tom", "name": "Tom Fielding", "kind": "food",
        "capability": "food_handler", "capacity": 1, "unit": "site",
        "reliability": 0.84, "location": "Recruit list", "coords": [38.546, -121.504],
        "org": "Riverside Church", "opted_in": False, "availability": False,
    },
    # --- Site keyholders ---
    {
        "id": "elena", "name": "Elena Brooks", "kind": "keyholder",
        "capability": "site_keyholder", "capacity": 1, "unit": "site",
        "reliability": 0.97, "location": "Eastside", "coords": [38.577, -121.455],
        "org": "Riverside Church", "opted_in": True,
    },
    {
        "id": "noah", "name": "Noah Kim", "kind": "keyholder",
        "capability": "site_keyholder", "capacity": 1, "unit": "site",
        "reliability": 0.90, "location": "Food bank bench", "coords": [38.603, -121.495],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "carmen", "name": "Carmen Diaz", "kind": "keyholder",
        "capability": "site_keyholder", "capacity": 1, "unit": "site",
        "reliability": 0.93, "location": "Harbor", "coords": [38.587, -121.541],
        "org": "Eastside Mutual Aid", "opted_in": True,
    },
    {
        "id": "wes", "name": "Wes Turner", "kind": "keyholder",
        "capability": "site_keyholder", "capacity": 1, "unit": "site",
        "reliability": 0.89, "location": "West End", "coords": [38.570, -121.556],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "fiona", "name": "Fiona Adeyemi", "kind": "keyholder",
        "capability": "site_keyholder", "capacity": 1, "unit": "site",
        "reliability": 0.84, "location": "Church bench", "coords": [38.552, -121.478],
        "org": "Riverside Church", "opted_in": True,
    },
    # --- Assets (decorative in v1: a driver already implies a van) ---
    {
        "id": "van-fb-1", "name": "Food Bank Van 1", "kind": "van",
        "capability": None, "capacity": 0, "unit": "asset",
        "reliability": 0.94, "location": "Second Harvest", "coords": [38.599, -121.500],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "van-fb-2", "name": "Food Bank Van 2", "kind": "van",
        "capability": None, "capacity": 0, "unit": "asset",
        "reliability": 0.90, "location": "Second Harvest", "coords": [38.594, -121.498],
        "org": "Second Harvest", "opted_in": True,
    },
    {
        "id": "van-church-1", "name": "Church Van", "kind": "van",
        "capability": None, "capacity": 0, "unit": "asset",
        "reliability": 0.92, "location": "Riverside Church", "coords": [38.561, -121.474],
        "org": "Riverside Church", "opted_in": True,
    },
)

RESOURCE_META: dict[str, dict] = {spec["id"]: spec for spec in _RESOURCE_SPEC}

DESTINATIONS: tuple[dict, ...] = (
    {
        "id": "eastside", "name": "Riverside Community Meals — Eastside", "kind": "site",
        "population": 180, "note": "Thursday distribution · opens 4:00pm.",
        "coords": [38.572, -121.458], "primary": True,
    },
    {
        "id": "harbor", "name": "Riverside Community Meals — Harbor", "kind": "site",
        "population": 120, "note": "Thursday distribution · opens 4:30pm.",
        "coords": [38.586, -121.532], "primary": False,
    },
    {
        "id": "west-end", "name": "Riverside Community Meals — West End", "kind": "site",
        "population": 95, "note": "Thursday distribution · opens 5:00pm.",
        "coords": [38.576, -121.548], "primary": False,
    },
)

DESTINATION_COORDS: dict[str, list[float]] = {d["name"].lower(): d["coords"] for d in DESTINATIONS}

# Which site rosters each person signed up for. Volunteers commit to sites they
# can actually reach; the two organization benches ("*") float across all sites.
_SITE_MEMBERSHIP: dict[str, tuple[str, ...]] = {
    "maya": ("eastside",),
    "priya": ("eastside",),
    "elena": ("eastside",),
    "dana": ("harbor",),
    "hana": ("harbor",),
    "bea": ("harbor",),
    "carmen": ("harbor",),
    "tariq": ("west-end",),
    "diego": ("west-end",),
    "wes": ("west-end",),
    # Food-bank bench — drives to any site.
    "luis": ("*",),
    "avery": ("*",),
    "noah": ("*",),
    # Church bench — the two sites on their side of the river.
    "gina": ("eastside", "west-end"),
    "sam": ("eastside", "west-end"),
    "riley": ("eastside", "west-end"),
    "fiona": ("eastside", "west-end"),
    # Recruit-only candidates and shared assets.
    "jordan": ("*",),
    "marcus": ("*",),
    "tom": ("*",),
    "van-fb-1": ("*",),
    "van-fb-2": ("*",),
    "van-church-1": ("*",),
}


def resource_sites(resource_id: str) -> list[str]:
    """Site ids this resource is on the roster for ("*" means every site)."""

    sites = _SITE_MEMBERSHIP.get(resource_id, ("*",))
    if "*" in sites:
        return [destination["id"] for destination in DESTINATIONS]
    return list(sites)


def _build_resources() -> list[Resource]:
    resources: list[Resource] = []
    for spec in _RESOURCE_SPEC:
        resources.append(
            Resource(
                id=spec["id"],
                name=spec["name"],
                category=spec["kind"],
                location=spec["location"],
                status="available" if spec.get("availability", True) else "busy",
                availability=spec.get("availability", True),
                reliability=spec["reliability"],
                capacity=spec["capacity"],
                capacity_unit=spec["unit"],
                capability_codes=[spec["capability"]] if spec["capability"] else [],
                opted_in=spec["opted_in"],
                org=spec["org"],
            )
        )
    return resources


SCENARIO_RESOURCES: tuple[Resource, ...] = tuple(_build_resources())


SCENARIO_HYPEREDGES: tuple[CoalitionHyperedge, ...] = (
    CoalitionHyperedge(
        id="eastside_meal_delivery",
        mission_id="thursday_eastside",
        mission_label="Thursday Eastside distribution",
        resource_ids=["maya", "priya", "elena"],
        emergent_capability_code="meal_delivery",
        emergent_capability_label="Meal delivery",
        explanation="A driver, food handler, and keyholder together can open and run Eastside.",
    ),
    CoalitionHyperedge(
        id="eastside_bench_delivery",
        mission_id="thursday_eastside",
        mission_label="Thursday Eastside distribution",
        resource_ids=["luis", "sam", "noah"],
        emergent_capability_code="meal_delivery",
        emergent_capability_label="Meal delivery",
        explanation="Opted-in volunteers across both organizations can recompose the full site team.",
    ),
    CoalitionHyperedge(
        id="harbor_meal_delivery",
        mission_id="thursday_harbor",
        mission_label="Thursday Harbor distribution",
        resource_ids=["dana", "hana", "carmen"],
        emergent_capability_code="meal_delivery",
        emergent_capability_label="Meal delivery",
        explanation="Harbor's own three volunteers cover the site without borrowing from Eastside.",
    ),
    CoalitionHyperedge(
        id="west_end_meal_delivery",
        mission_id="thursday_west_end",
        mission_label="Thursday West End distribution",
        resource_ids=["tariq", "diego", "wes"],
        emergent_capability_code="meal_delivery",
        emergent_capability_label="Meal delivery",
        explanation="West End's own three volunteers, backed by the food-bank bench if one drops.",
    ),
)


PRESET_MISSIONS: tuple[dict, ...] = (
    {
        "id": "thursday_eastside",
        "label": "Thursday Eastside distribution",
        "min_capacity": 0,
        "mission": {
            "destination": "Riverside Community Meals — Eastside",
            "deadline": "2026-09-10T16:00:00-07:00",
            "incident_type": "thursday_distribution",
            "requirements": ["van driver", "packer", "site lead"],
            "constraints": ["van certification required to drive"],
        },
    },
    {
        "id": "thursday_harbor",
        "label": "Thursday Harbor distribution",
        "min_capacity": 0,
        "mission": {
            "destination": "Riverside Community Meals — Harbor",
            "deadline": "2026-09-10T16:30:00-07:00",
            "incident_type": "thursday_distribution",
            "requirements": ["van driver", "packer", "site lead"],
            "constraints": ["van certification required to drive"],
        },
    },
    {
        "id": "thursday_west_end",
        "label": "Thursday West End distribution",
        "min_capacity": 0,
        "mission": {
            "destination": "Riverside Community Meals — West End",
            "deadline": "2026-09-10T17:00:00-07:00",
            "incident_type": "thursday_distribution",
            "requirements": ["van driver", "packer", "site lead"],
            "constraints": ["van certification required to drive"],
        },
    },
)

CAPABILITY_LABELS: dict[str, str] = {
    "van_certified_driver": "Van-certified driver",
    "food_handler": "Food handler",
    "site_keyholder": "Site keyholder",
}

# CP-SAT only minimizes the number of people, so many coalitions tie on cost and
# the catalog order decides between them. Listing the floating benches first and
# each site's own volunteers last makes the solver settle on the local team,
# which is both stable between runs and what a coordinator would expect.
_SOLVER_ROSTER_ORDER = {
    resource_id: index
    for index, resource_id in enumerate(
        [
            # floating benches
            "gina", "riley", "sam", "fiona", "luis", "avery", "noah",
            # recruit-only candidates (never assignable without a human)
            "jordan", "marcus", "tom",
            # site teams
            "dana", "bea", "hana", "carmen",
            "tariq", "diego", "wes",
            "maya", "priya", "elena",
            # assets
            "van-fb-1", "van-fb-2", "van-church-1",
        ]
    )
}


def site_roster_ids(destination: str | None) -> set[str] | None:
    """Ids signed up for one site, or ``None`` when the site is unknown.

    Volunteers commit to the sites they can actually reach; the two org benches
    float across all of them. The solver has no notion of distance, so the
    roster is scoped before CP-SAT rather than modelled as a constraint.
    """

    if not destination:
        return None
    site = next((d for d in DESTINATIONS if d["name"].lower() == destination.strip().lower()), None)
    if site is None:
        return None
    return {spec["id"] for spec in _RESOURCE_SPEC if site["id"] in resource_sites(spec["id"])}


def build_catalog(failed_ids: Iterable[str] = (), destination: str | None = None) -> list[Resource]:
    """Return the scenario catalog with the given resources marked offline."""

    failed = set(failed_ids)
    roster = site_roster_ids(destination)
    catalog: list[Resource] = []
    for resource in SCENARIO_RESOURCES:
        if roster is not None and resource.id not in roster:
            continue
        clone = resource.model_copy(deep=True)
        if clone.id in failed:
            clone.availability = False
            clone.status = "offline"
        catalog.append(clone)
    # Keep the canned replay stable while CP-SAT remains the sole selector.
    return sorted(catalog, key=lambda resource: _SOLVER_ROSTER_ORDER[resource.id])


def destination_coords(name: str | None) -> list[float] | None:
    """Look up coordinates for a destination name, if known."""

    if not name:
        return None
    return DESTINATION_COORDS.get(name.strip().lower())


def resolve_destination(name: str | None) -> dict | None:
    """Always place a destination on the map.

    Known scenario sites use their simulated coordinates; any other name is
    pinned at the simulated region center and flagged
    ``approx`` so the UI can label it "simulated location" instead of showing
    nothing.
    """

    if not name or not name.strip():
        return None
    coords = DESTINATION_COORDS.get(name.strip().lower())
    if coords is not None:
        return {"name": name, "coords": coords, "approx": False}
    return {"name": name, "coords": list(REGION["center"]), "approx": True}


def preset_mission(preset_id: str) -> Mission | None:
    for preset in PRESET_MISSIONS:
        if preset["id"] == preset_id:
            return Mission.model_validate(preset["mission"])
    return None


def scenario_payload() -> dict:
    """Full world description for the frontend to render the map + panels."""

    resources = []
    for resource in SCENARIO_RESOURCES:
        meta = RESOURCE_META[resource.id]
        data = resource.model_dump()
        data.update(
            {
                "kind": meta["kind"],
                "lat": meta["coords"][0],
                "lng": meta["coords"][1],
                "sites": resource_sites(resource.id),
            }
        )
        resources.append(data)

    return {
        "simulated": True,
        "region": REGION,
        "map": carto_tile_config(),
        "resources": resources,
        "destinations": [dict(d) for d in DESTINATIONS],
        "hyperedges": [edge.model_dump() for edge in SCENARIO_HYPEREDGES],
        "presets": [dict(p) for p in PRESET_MISSIONS],
        "capabilityLabels": CAPABILITY_LABELS,
    }
