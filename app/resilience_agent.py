from __future__ import annotations

import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.capabilities import derive_required_capabilities
from app.mission import Mission
from app.resilience import ResilienceReport, replan
from app.resources import Resource
from app.solver import CoalitionRequest, solve_resource_coalition

logger = logging.getLogger(__name__)


def _print_section(title: str, value: object) -> None:
    print(f"\n{title}")
    print(value)


def _volunteer(
    resource_id: str,
    name: str,
    category: str,
    capability_code: str,
    location: str,
    org: str,
    reliability: float,
) -> Resource:
    return Resource(
        id=resource_id,
        name=name,
        category=category,
        location=location,
        status="available",
        availability=True,
        reliability=reliability,
        capacity=1,
        capacity_unit="site",
        capability_codes=[capability_code],
        opted_in=True,
        org=org,
    )


def build_demo_resources() -> list[Resource]:
    """A Thursday roster with a backup driver and packer, but only one keyholder.

    That asymmetry is the point: losing the driver is recoverable, losing the
    keyholder closes the site.
    """

    return [
        _volunteer("maya", "Maya Chen", "driver", "van_certified_driver", "Eastside", "Riverside Church", 0.96),
        _volunteer("priya", "Priya Shah", "food handler", "food_handler", "Eastside", "Riverside Church", 0.95),
        _volunteer("elena", "Elena Brooks", "site keyholder", "site_keyholder", "Eastside", "Riverside Church", 0.97),
        _volunteer("luis", "Luis Okonkwo", "driver", "van_certified_driver", "Food bank bench", "Second Harvest", 0.93),
        _volunteer("sam", "Sam Ortiz", "food handler", "food_handler", "Church bench", "Riverside Church", 0.92),
    ]


def run_resilience_demo(*, include_summary: bool = True) -> ResilienceReport:
    mission = Mission(
        destination="Riverside Community Meals — Eastside",
        deadline="2026-09-10T16:00:00-07:00",
        incident_type="thursday_distribution",
        requirements=["van driver", "packer", "site lead"],
        constraints=["van certification required to drive"],
    )
    capability_assessment = derive_required_capabilities(mission)
    resources = build_demo_resources()
    baseline = solve_resource_coalition(
        CoalitionRequest(
            required_capabilities=capability_assessment.rule_required_capability_codes,
            minimum_total_capacity=0,
        ),
        resources=resources,
    )
    report = replan(
        CoalitionRequest(
            required_capabilities=capability_assessment.rule_required_capability_codes,
            minimum_total_capacity=0,
        ),
        baseline,
        resources=resources,
    )

    print("=== MealMesh: what one cancellation would do ===")
    _print_section("1) Baseline coalition", baseline.model_dump())
    _print_section("2) Resilience report", report.model_dump())
    if include_summary:
        print("\nResilience summary")
        print(report.summary)
        print(f"Overall classification: {report.overall_classification}")
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_resilience_demo()


if __name__ == "__main__":
    main()
