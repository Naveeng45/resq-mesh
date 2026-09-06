from __future__ import annotations

import logging
import sys
from itertools import combinations
from pathlib import Path
from typing import Literal

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import hypernetx as hnx
import networkx as nx
import numpy as np
from pydantic import ConfigDict, Field

from app.mission import Mission
from app.pydantic_compat import CompatBaseModel
from app.resources import Resource
from app.solver import CoalitionRequest, CoalitionSolution, solve_resource_coalition

logger = logging.getLogger(__name__)


class CoalitionHyperedge(CompatBaseModel):
    """A coalition of resources that unlocks an emergent capability."""

    model_config = ConfigDict(extra="forbid")

    id: str
    mission_id: str
    mission_label: str
    resource_ids: list[str] = Field(default_factory=list)
    emergent_capability_code: str
    emergent_capability_label: str
    explanation: str


class EmergentCapability(CompatBaseModel):
    """A capability that appears only when a coalition hyperedge exists."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    resource_ids: list[str] = Field(default_factory=list)
    explanation: str


class HypergraphMetrics(CompatBaseModel):
    """Structural metrics for the projected coalition graph."""

    model_config = ConfigDict(extra="forbid")

    node_count: int
    hyperedge_count: int
    pairwise_edge_count: int
    connected_components: int
    lambda2: float
    isolated_nodes: list[str] = Field(default_factory=list)


class HypergraphReport(CompatBaseModel):
    """A compact lesson report tying the solver to the hypergraph view."""

    model_config = ConfigDict(extra="forbid")

    mission: Mission
    coalition_request: CoalitionRequest
    selected_solution: CoalitionSolution
    resources: list[Resource] = Field(default_factory=list)
    hyperedges: list[CoalitionHyperedge] = Field(default_factory=list)
    selected_hyperedge: CoalitionHyperedge | None = None
    emergent_capabilities: list[EmergentCapability] = Field(default_factory=list)
    hypergraph_node_ids: list[str] = Field(default_factory=list)
    hypergraph_edge_ids: list[str] = Field(default_factory=list)
    projection_edges: list[tuple[str, str]] = Field(default_factory=list)
    metrics: HypergraphMetrics
    summary: str
    structural_note: str


def build_demo_resources() -> list[Resource]:
    """Create a tiny deterministic catalog: one volunteer per required role.

    Deliberately minimal, so the resilience layer has no backups to find and the
    demo shows what "one cancellation closes the site" looks like.
    """

    return [
        Resource(
            id="maya",
            name="Maya Chen",
            category="driver",
            location="Eastside",
            status="available",
            availability=True,
            reliability=0.96,
            capacity=1,
            capacity_unit="site",
            capability_codes=["van_certified_driver"],
            opted_in=True,
            org="Riverside Church",
        ),
        Resource(
            id="priya",
            name="Priya Shah",
            category="food handler",
            location="Eastside",
            status="available",
            availability=True,
            reliability=0.95,
            capacity=1,
            capacity_unit="site",
            capability_codes=["food_handler"],
            opted_in=True,
            org="Riverside Church",
        ),
        Resource(
            id="elena",
            name="Elena Brooks",
            category="site keyholder",
            location="Eastside",
            status="available",
            availability=True,
            reliability=0.97,
            capacity=1,
            capacity_unit="site",
            capability_codes=["site_keyholder"],
            opted_in=True,
            org="Riverside Church",
        ),
    ]


def build_demo_mission() -> Mission:
    """Provide a concrete Thursday coverage window for the walkthrough."""

    return Mission(
        destination="Riverside Community Meals — Eastside",
        deadline="2026-09-10T16:00:00-07:00",
        incident_type="thursday_distribution",
        requirements=["van driver", "packer", "site lead"],
        constraints=["van certification required to drive"],
    )


def build_demo_hyperedges() -> list[CoalitionHyperedge]:
    """Define coalition units where the capability only appears in combination."""

    return [
        CoalitionHyperedge(
            id="eastside_meal_delivery",
            mission_id="thursday_eastside",
            mission_label="Thursday Eastside distribution",
            resource_ids=["maya", "priya", "elena"],
            emergent_capability_code="meal_delivery",
            emergent_capability_label="Meal delivery",
            explanation=(
                "A van-certified driver, a food handler, and a site keyholder together can "
                "open and run Eastside; no one of them can serve a meal alone."
            ),
        ),
    ]


def build_hypernetx_hypergraph(hyperedges: list[CoalitionHyperedge]) -> hnx.Hypergraph:
    """Build the HyperNetX object from the coalition definitions."""

    edge_map = {edge.id: set(edge.resource_ids) for edge in hyperedges}
    return hnx.Hypergraph(edge_map)


def build_projection_graph(resources: list[Resource], hyperedges: list[CoalitionHyperedge]) -> nx.Graph:
    """Project the hypergraph into a pairwise graph for structural metrics."""

    graph = nx.Graph()
    graph.add_nodes_from(resource.id for resource in resources)
    for edge in hyperedges:
        for left, right in combinations(sorted(set(edge.resource_ids)), 2):
            graph.add_edge(left, right, hyperedge_id=edge.id)
    return graph


def compute_lambda2(graph: nx.Graph) -> float:
    """Compute the second-smallest Laplacian eigenvalue for a graph."""

    if graph.number_of_nodes() < 2 or graph.number_of_edges() == 0:
        return 0.0
    if not nx.is_connected(graph):
        return 0.0

    laplacian = nx.laplacian_matrix(graph, nodelist=sorted(graph.nodes())).astype(float).toarray()
    eigenvalues = np.linalg.eigvalsh(laplacian)
    if len(eigenvalues) < 2:
        return 0.0
    return float(eigenvalues[1])


def _isolated_nodes(graph: nx.Graph) -> list[str]:
    return sorted(node for node, degree in graph.degree() if degree == 0)


def find_selected_hyperedge(
    selected_resource_ids: list[str],
    hyperedges: list[CoalitionHyperedge],
) -> CoalitionHyperedge | None:
    """Match the solver-selected coalition to a hyperedge if the sets align."""

    selected_set = set(selected_resource_ids)
    for edge in hyperedges:
        if set(edge.resource_ids) == selected_set:
            return edge
    return None


def build_emergent_capabilities(
    resources: list[Resource],
    hyperedges: list[CoalitionHyperedge],
) -> list[EmergentCapability]:
    """Return the capabilities that exist only on coalition hyperedges."""

    individually_owned_codes = {
        capability_code
        for resource in resources
        for capability_code in resource.capability_codes
    }

    emergent_capabilities: list[EmergentCapability] = []
    for edge in hyperedges:
        if edge.emergent_capability_code in individually_owned_codes:
            continue
        emergent_capabilities.append(
            EmergentCapability(
                code=edge.emergent_capability_code,
                label=edge.emergent_capability_label,
                resource_ids=list(edge.resource_ids),
                explanation=edge.explanation,
            )
        )
    return emergent_capabilities


def build_hypergraph_report(
    mission: Mission,
    request: CoalitionRequest,
    selected_solution: CoalitionSolution,
    resources: list[Resource],
    hyperedges: list[CoalitionHyperedge],
) -> HypergraphReport:
    """Project an already-solved coalition onto the coalition hypergraph.

    Representation only: the solver has already chosen the team, and this layer
    explains the choice (which coalition unit it is, which capability only exists
    because the group exists). It never changes the assignment.
    """

    hypergraph = build_hypernetx_hypergraph(hyperedges)
    projection_graph = build_projection_graph(resources, hyperedges)
    selected_hyperedge = find_selected_hyperedge(selected_solution.selected_resource_ids, hyperedges)
    emergent_capabilities = build_emergent_capabilities(resources, hyperedges)
    structural_note = (
        "lambda2 is a structural connectivity metric for the projected graph; "
        "it does not replace explicit remove-and-re-solve tests for operational criticality."
    )
    summary = (
        f"Solver coalition {', '.join(selected_solution.selected_resource_ids)} maps to "
        f"{selected_hyperedge.id if selected_hyperedge else 'no matching hyperedge'}."
    )

    return HypergraphReport(
        mission=mission,
        coalition_request=request,
        selected_solution=selected_solution,
        resources=resources,
        hyperedges=hyperedges,
        selected_hyperedge=selected_hyperedge,
        emergent_capabilities=emergent_capabilities,
        hypergraph_node_ids=sorted(list(hypergraph.nodes)),
        hypergraph_edge_ids=sorted(list(hypergraph.edges)),
        projection_edges=sorted((min(left, right), max(left, right)) for left, right in projection_graph.edges()),
        metrics=HypergraphMetrics(
            node_count=projection_graph.number_of_nodes(),
            hyperedge_count=len(hyperedges),
            pairwise_edge_count=projection_graph.number_of_edges(),
            connected_components=nx.number_connected_components(projection_graph) if projection_graph.number_of_nodes() else 0,
            lambda2=compute_lambda2(projection_graph),
            isolated_nodes=_isolated_nodes(projection_graph),
        ),
        summary=summary,
        structural_note=structural_note,
    )


def build_demo_report() -> HypergraphReport:
    """Run the demo and package the structural results."""

    mission = build_demo_mission()
    resources = build_demo_resources()
    hyperedges = build_demo_hyperedges()
    request = CoalitionRequest(
        required_capabilities=["van_certified_driver", "food_handler", "site_keyholder"],
        minimum_total_capacity=0,
    )
    selected_solution = solve_resource_coalition(request, resources=resources)
    if not selected_solution.feasible:
        raise ValueError("The demo coalition should be feasible.")

    return build_hypergraph_report(mission, request, selected_solution, resources, hyperedges)


def _print_section(title: str, payload: object) -> None:
    print(f"\n{title}")
    print(payload)


def run_hypergraph_demo() -> HypergraphReport:
    """Print a small hypergraph walkthrough of the Thursday coalition."""

    report = build_demo_report()
    print("=== MealMesh coalition hypergraph ===")
    _print_section("1) Mission", report.mission.model_dump())
    _print_section("2) Solver coalition", report.selected_solution.model_dump())
    _print_section("3) HyperNetX nodes", report.hypergraph_node_ids)
    _print_section("4) HyperNetX hyperedges", report.hypergraph_edge_ids)
    _print_section("5) Coalition hyperedges", [edge.model_dump() for edge in report.hyperedges])
    _print_section("6) Emergent capabilities", [capability.model_dump() for capability in report.emergent_capabilities])
    _print_section("7) Projection edges", report.projection_edges)
    _print_section("8) Structural metrics", report.metrics.model_dump())
    _print_section("9) Structural note", report.structural_note)
    _print_section("10) Summary", report.summary)
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_hypergraph_demo()


if __name__ == "__main__":
    main()
