from __future__ import annotations

import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.solver import CoalitionRequest, solve_resource_coalition


logger = logging.getLogger(__name__)

PROMPT = "Flood waters have isolated Willow Creek. Select the smallest feasible coalition with flood access and field triage for at least 8 total capacity."


def _print_section(title: str, value: object) -> None:
    print(f"\n{title}")
    print(value)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("Running deterministic coalition solver for lesson 06")
    print("=== RESQ-Mesh Lesson 06 Demo ===")
    print(f"Request: {PROMPT}")

    request = CoalitionRequest(
        required_capabilities=["flood_access", "field_triage"],
        minimum_total_capacity=8,
    )
    solution = solve_resource_coalition(request)

    _print_section("1) Constraint explanations", solution.constraint_explanations)
    _print_section("2) Feasible", solution.feasible)
    _print_section("3) Solver status", solution.solver_status)
    _print_section("4) Selected resource IDs", solution.selected_resource_ids)
    _print_section("5) Selected count", solution.selected_count)
    _print_section("6) Total capacity", solution.total_capacity)
    _print_section("7) Objective value", solution.objective_value)

    if solution.infeasible_reason:
        _print_section("8) Infeasible reason", solution.infeasible_reason)
    else:
        print("\n8) Infeasible reason")
        print("None")


if __name__ == "__main__":
    main()
