from __future__ import annotations

from app.capabilities import derive_required_capabilities
from app.hypergraph import build_demo_report
from app.mission import Mission, review_mission
from app.mission_agent import build_demo_mission
from app.resilience import replan
from app.resilience_agent import build_demo_resources
from app.solver import CoalitionRequest, solve_resource_coalition


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def run_full_demo() -> None:
    """Run the full MealMesh demo in a concise presentation format."""

    print("=== MealMesh End-to-End Demo ===")

    print("\nPhase 1: Mission to Coalition")
    mission = build_demo_mission()
    review = review_mission(mission)
    capabilities = derive_required_capabilities(mission)
    coalition = solve_resource_coalition(
        CoalitionRequest(
            required_capabilities=capabilities.rule_required_capability_codes,
            minimum_total_capacity=0,
        )
    )
    print(
        "Mission:",
        f"{mission.destination} | {mission.incident_type} | requirements={_join(mission.requirements)}",
    )
    print(f"Review: {review.status}")
    print("Capabilities:", _join([capability.code for capability in capabilities.required_capabilities]))
    print(
        "Coalition:",
        f"{_join(coalition.selected_resource_ids)} | total_capacity={coalition.total_capacity} | {coalition.solver_status}",
    )

    print("\nPhase 2: Cancellation and Replan")
    resilience_mission = Mission(
        destination="Riverside Community Meals — Eastside",
        deadline="2026-09-10T16:00:00-07:00",
        incident_type="thursday_distribution",
        requirements=["van driver", "packer", "site lead"],
        constraints=["van certification required to drive"],
    )
    resilience_capabilities = derive_required_capabilities(resilience_mission)
    resilience_request = CoalitionRequest(
        required_capabilities=resilience_capabilities.rule_required_capability_codes,
        minimum_total_capacity=0,
    )
    resources = build_demo_resources()
    baseline = solve_resource_coalition(resilience_request, resources=resources)
    report = replan(resilience_request, baseline, resources=resources)
    print("Baseline:", _join(report.baseline_selected_resource_ids))
    print("Overall:", report.overall_classification)
    print(
        "Failures:",
        f"recoverable={_join(report.recoverable_failure_ids)} | mission_breaking={_join(report.mission_breaking_failure_ids)}",
    )
    print("Summary:", report.summary)

    print("\nPhase 3: Hypergraph Model")
    hypergraph_report = build_demo_report()
    print(
        "Coalition hyperedge:",
        hypergraph_report.selected_hyperedge.id if hypergraph_report.selected_hyperedge else "none",
    )
    print(
        "Emergent capabilities:",
        _join([capability.code for capability in hypergraph_report.emergent_capabilities]),
    )
    print(
        "Structural metrics:",
        f"components={hypergraph_report.metrics.connected_components} | "
        f"lambda2={hypergraph_report.metrics.lambda2}",
    )
    print("Structural note:", hypergraph_report.structural_note)


if __name__ == "__main__":
    run_full_demo()
