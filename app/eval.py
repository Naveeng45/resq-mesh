"""Lesson 10 - deterministic regression evaluation over golden scenarios.

Loads ``examples/golden_scenarios.json``, runs each mission through the
deterministic pipeline (no LLM), and checks the pipeline's verdict, coalition
state, selected resources, and missing capabilities against the recorded
expectations. Because the pipeline is deterministic, this doubles as both a
regression guard and a mission-feasibility-correctness metric for the writeup.

Run: python -m app.eval
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ConfigDict, Field

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.mission import Mission
from app.orchestration import OrchestrationResult, run_pipeline
from app.pydantic_compat import CompatBaseModel
from app.resilience_agent import build_demo_resources
from app.resources import Resource, list_resources

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "examples" / "golden_scenarios.json"


class ScenarioResult(CompatBaseModel):
    """Pass/fail outcome for one golden scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str
    passed: bool
    verdict: str
    expected_verdict: str
    mismatches: list[str] = Field(default_factory=list)


class EvalReport(CompatBaseModel):
    """Aggregate golden-eval report."""

    model_config = ConfigDict(extra="forbid")

    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[ScenarioResult] = Field(default_factory=list)


def _load_catalog(scenario: dict) -> list[Resource] | None:
    """Resolve a scenario's resource catalog (inline list or named builtin)."""

    if "resources" in scenario:
        return [Resource.model_validate(item) for item in scenario["resources"]]
    name = scenario.get("catalog")
    if name == "demo":
        return build_demo_resources()
    if name == "default":
        return list_resources()
    return None  # run_pipeline defaults to the standard catalog


def load_scenarios(path: Path = GOLDEN_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _coalition_state(result: OrchestrationResult) -> str:
    if result.coalition is None:
        return "none"
    return "feasible" if result.coalition.feasible else "infeasible"


def evaluate_scenario(scenario: dict) -> ScenarioResult:
    """Run one scenario through the pipeline and diff it against expectations."""

    mission = Mission.model_validate(scenario["mission"])
    resources = _load_catalog(scenario)
    result = run_pipeline(
        mission,
        resources=resources,
        include_resilience=scenario.get("include_resilience", True),
        include_hypergraph=False,
        coalition_min_capacity=scenario.get("coalition_min_capacity", 0),
    )
    expected = scenario["expected"]
    mismatches: list[str] = []

    if result.verdict != expected["verdict"]:
        mismatches.append(f"verdict: got '{result.verdict}', expected '{expected['verdict']}'")

    expected_coalition = expected.get("coalition", "none")
    actual_coalition = _coalition_state(result)
    if actual_coalition != expected_coalition:
        mismatches.append(f"coalition: got '{actual_coalition}', expected '{expected_coalition}'")

    if "selected_resource_ids" in expected:
        actual_ids = sorted(result.coalition.selected_resource_ids) if result.coalition else []
        if actual_ids != sorted(expected["selected_resource_ids"]):
            mismatches.append(f"selected: got {actual_ids}, expected {sorted(expected['selected_resource_ids'])}")

    if "missing_capabilities" in expected:
        actual_missing = sorted(result.missing_capabilities)
        if actual_missing != sorted(expected["missing_capabilities"]):
            mismatches.append(
                f"missing_capabilities: got {actual_missing}, "
                f"expected {sorted(expected['missing_capabilities'])}"
            )

    return ScenarioResult(
        id=scenario["id"],
        passed=not mismatches,
        verdict=result.verdict,
        expected_verdict=expected["verdict"],
        mismatches=mismatches,
    )


def run_golden_eval(path: Path = GOLDEN_PATH) -> EvalReport:
    """Evaluate every golden scenario and return an aggregate report."""

    scenarios = load_scenarios(path)
    results = [evaluate_scenario(scenario) for scenario in scenarios]
    passed = sum(1 for result in results if result.passed)
    total = len(results)
    return EvalReport(
        total=total,
        passed=passed,
        failed=total - passed,
        pass_rate=round(passed / total, 4) if total else 0.0,
        results=results,
    )


def main() -> None:
    report = run_golden_eval()
    print("=== MealMesh golden eval ===")
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.id}: {result.verdict}")
        for mismatch in result.mismatches:
            print(f"        - {mismatch}")
    print(f"\n{report.passed}/{report.total} passed (pass_rate={report.pass_rate}).")
    if report.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
