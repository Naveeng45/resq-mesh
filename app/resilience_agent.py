from __future__ import annotations

import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.capabilities import derive_required_capabilities
from app.mission import Mission
from app.resilience import replan
from app.resources import Resource
from app.solver import CoalitionRequest, solve_resource_coalition

logger = logging.getLogger(__name__)


def _print_section(title: str, value: object) -> None:
    print(f"\n{title}")
    print(value)


def build_demo_resources() -> list[Resource]:
    return [
        Resource(
            id="flood-boat",
            name="Flood Boat",
            category="water rescue",
            location="Dock A",
            status="available",
            availability=True,
            reliability=0.93,
            capacity=4,
            capacity_unit="people",
            capability_codes=["flood_access"],
        ),
        Resource(
            id="med-team",
            name="Medical Team",
            category="field care",
            location="Clinic",
            status="available",
            availability=True,
            reliability=0.96,
            capacity=4,
            capacity_unit="patients",
            capability_codes=["field_triage"],
        ),
        Resource(
            id="comms-kit",
            name="Communications Kit",
            category="communications",
            location="Command Post",
            status="available",
            availability=True,
            reliability=0.91,
            capacity=1,
            capacity_unit="units",
            capability_codes=["communications"],
        ),
        Resource(
            id="backup-boat",
            name="Backup Flood Boat",
            category="water rescue",
            location="Dock B",
            status="available",
            availability=True,
            reliability=0.88,
            capacity=4,
            capacity_unit="people",
            capability_codes=["flood_access"],
        ),
        Resource(
            id="backup-med",
            name="Backup Medical Team",
            category="field care",
            location="Clinic B",
            status="available",
            availability=True,
            reliability=0.89,
            capacity=4,
            capacity_unit="patients",
            capability_codes=["field_triage"],
        ),
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mission = Mission(
        destination="Willow Creek",
        deadline="2026-09-06T18:00:00-07:00",
        incident_type="flood",
        requirements=["boat", "medical team", "communications"],
        constraints=["roads remain blocked"],
    )
    capability_assessment = derive_required_capabilities(mission)
    resources = build_demo_resources()
    baseline = solve_resource_coalition(
        CoalitionRequest(
            required_capabilities=capability_assessment.rule_required_capability_codes,
            minimum_total_capacity=9,
        ),
        resources=resources,
    )
    report = replan(
        CoalitionRequest(
            required_capabilities=capability_assessment.rule_required_capability_codes,
            minimum_total_capacity=9,
        ),
        baseline,
        resources=resources,
    )

    print("=== RESQ-Mesh Lesson 07 Demo ===")
    _print_section("1) Baseline coalition", baseline.model_dump())
    _print_section("2) Resilience report", report.model_dump())


if __name__ == "__main__":
    main()
