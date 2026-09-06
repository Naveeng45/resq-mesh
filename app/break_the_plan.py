"""MealMesh "BREAK THE PLAN" demo.

Tells the four-question story with no math jargon:

    1. Build an initial feasible plan.
    2. Break it (a resource is lost) and watch the system recompose.
    3. Break it again until no coalition exists, and name the single missing
       capability that would make the mission feasible again.

Everything here is deterministic (CP-SAT + capability rules). The LLM is not
involved. The demo is tie-break independent: it fails whichever driver the solver
actually selected, so the recompose is always meaningful. Run:

    python -m app.break_the_plan
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.capabilities import CAPABILITY_ONTOLOGY, derive_required_capabilities
from app.mission import Mission
from app.resources import Resource
from app.solver import CoalitionRequest, CoalitionSolution, solve_resource_coalition

MIN_TOTAL_CAPACITY = 0


@dataclass
class BreakStep:
    """One step of the narrative: a (re)plan after zero or more failures."""

    title: str
    failed_resource_id: str | None
    solution: CoalitionSolution
    missing_capabilities: list[str] = field(default_factory=list)


def build_scenario_mission() -> Mission:
    return Mission(
        destination="Riverside Community Meals — Eastside",
        deadline="2026-09-10T16:00:00-07:00",
        incident_type="thursday_distribution",
        requirements=["van driver", "packer", "site lead"],
        constraints=["van certification required to drive"],
    )


def build_scenario_resources() -> list[Resource]:
    """Assigned volunteers plus one opted-in driver so one cancel is recoverable."""

    return [
        Resource(
            id="maya", name="Maya Chen", category="driver", location="Eastside",
            status="available", availability=True, reliability=0.90,
            capacity=1, capacity_unit="site", capability_codes=["van_certified_driver"],
            opted_in=True, org="Riverside Church",
        ),
        Resource(
            id="luis", name="Luis Okonkwo", category="driver", location="Food bank bench",
            status="available", availability=True, reliability=0.86,
            capacity=1, capacity_unit="site", capability_codes=["van_certified_driver"],
            opted_in=True, org="Second Harvest",
        ),
        Resource(
            id="priya", name="Priya Shah", category="food handler", location="Eastside",
            status="available", availability=True, reliability=0.95,
            capacity=1, capacity_unit="site", capability_codes=["food_handler"],
            opted_in=True, org="Riverside Church",
        ),
        Resource(
            id="elena", name="Elena Brooks", category="site keyholder", location="Eastside",
            status="available", availability=True, reliability=0.97,
            capacity=1, capacity_unit="site", capability_codes=["site_keyholder"],
            opted_in=True, org="Riverside Church",
        ),
    ]


def _capability_label(code: str) -> str:
    for capability in CAPABILITY_ONTOLOGY:
        if capability.code == code:
            return capability.label
    return code


def _name_of(catalog: list[Resource], resource_id: str | None) -> str:
    for resource in catalog:
        if resource.id == resource_id:
            return resource.name
    return resource_id or "unknown"


def _unmet_capabilities(required_codes: list[str], catalog: list[Resource]) -> list[str]:
    available: set[str] = set()
    for resource in catalog:
        if resource.availability and resource.status == "available":
            available.update(resource.capability_codes)
    return [code for code in required_codes if code not in available]


def _fail_resource(catalog: list[Resource], resource_id: str | None) -> None:
    for resource in catalog:
        if resource.id == resource_id:
            resource.availability = False
            resource.status = "offline"
            return


def _selected_driver(solution: CoalitionSolution, driver_ids: set[str]) -> str | None:
    for resource_id in solution.selected_resource_ids:
        if resource_id in driver_ids:
            return resource_id
    return None


def run_break_the_plan() -> list[BreakStep]:
    """Return the ordered narrative steps for the demo (initial + two failures)."""

    mission = build_scenario_mission()
    required_codes = derive_required_capabilities(mission).rule_required_capability_codes
    request = CoalitionRequest(required_capabilities=required_codes, minimum_total_capacity=MIN_TOTAL_CAPACITY)

    catalog = build_scenario_resources()
    driver_ids = {
        resource.id for resource in catalog
        if "van_certified_driver" in resource.capability_codes
    }
    steps: list[BreakStep] = []

    # 1) Initial plan.
    initial = solve_resource_coalition(request, resources=catalog)
    steps.append(BreakStep(title="Initial plan", failed_resource_id=None, solution=initial))

    # 2) Cancel whichever driver the solver chose -> recompose onto the bench.
    first_driver = _selected_driver(initial, driver_ids)
    _fail_resource(catalog, first_driver)
    recomposed = solve_resource_coalition(request, resources=catalog)
    steps.append(
        BreakStep(
            title=f"Break the plan: {_name_of(catalog, first_driver)} cancels",
            failed_resource_id=first_driver,
            solution=recomposed,
        )
    )

    # 3) Cancel the remaining driver too -> Eastside cannot open.
    second_driver = _selected_driver(recomposed, driver_ids)
    _fail_resource(catalog, second_driver)
    broken = solve_resource_coalition(request, resources=catalog)
    missing = [] if broken.feasible else _unmet_capabilities(required_codes, catalog)
    steps.append(
        BreakStep(
            title=f"Break the plan again: {_name_of(catalog, second_driver)} cancels",
            failed_resource_id=second_driver,
            solution=broken,
            missing_capabilities=missing,
        )
    )

    return steps


def render_break_the_plan(steps: list[BreakStep]) -> str:
    """Render the narrative as a scannable, jargon-free report."""

    lines: list[str] = ["=== MealMesh — BREAK THE PLAN ===", ""]
    mission = build_scenario_mission()
    lines.append(f"Coverage: {mission.destination} — Thursday 4:00pm.")
    lines.append("")

    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}) {step.title}")
        solution = step.solution
        if solution.feasible:
            lines.append(
                "   Plan: "
                + (", ".join(solution.selected_resource_ids) or "none")
                + f" | total_capacity={solution.total_capacity} | coverage=100%"
            )
        else:
            lines.append("   No feasible coalition.")
            if step.missing_capabilities:
                labels = ", ".join(_capability_label(code) for code in step.missing_capabilities)
                lines.append(f"   Missing capability: {labels}")
            elif solution.infeasible_reason:
                lines.append(f"   Reason: {solution.infeasible_reason}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    print(render_break_the_plan(run_break_the_plan()))


if __name__ == "__main__":
    main()
