from __future__ import annotations

from typing import Literal

from ortools.sat.python import cp_model
from pydantic import ConfigDict, Field

from app.pydantic_compat import CompatBaseModel
from app.resources import Resource, list_resources


class CoalitionRequest(CompatBaseModel):
    """Inputs to the deterministic coalition optimizer."""

    model_config = ConfigDict(extra="forbid")

    required_capabilities: list[str] = Field(default_factory=list)
    minimum_total_capacity: int = Field(default=0, ge=0)


class CoalitionSolution(CompatBaseModel):
    """Result returned by the CP-SAT solver."""

    model_config = ConfigDict(extra="forbid")

    feasible: bool
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
    selected_resources: list[Resource] = Field(default_factory=list)
    selected_resource_ids: list[str] = Field(default_factory=list)
    selected_count: int
    total_capacity: int
    objective_value: int | None = None
    constraint_explanations: list[str] = Field(default_factory=list)
    infeasible_reason: str | None = None


def describe_constraints(request: CoalitionRequest) -> list[str]:
    """Return the hard constraints and objective in plain English."""

    explanations = [
        "Availability constraint: resources marked unavailable are forced to zero, so the solver cannot select them.",
        "Capability coverage constraint: every required capability must be covered by at least one selected resource.",
        "Capacity constraint: the coalition's total capacity must meet or exceed the requested minimum.",
        "Objective: among all feasible coalitions, choose the one with the fewest selected resources.",
    ]

    if request.required_capabilities:
        explanations.insert(
            1,
            "Required capabilities for this request: " + ", ".join(request.required_capabilities),
        )

    if request.minimum_total_capacity:
        explanations.insert(
            3,
            f"Requested minimum total capacity: {request.minimum_total_capacity}.",
        )

    return explanations


def solve_resource_coalition(
    request: CoalitionRequest,
    resources: list[Resource] | None = None,
) -> CoalitionSolution:
    """Solve a small coalition-selection problem with CP-SAT."""

    catalog = list_resources() if resources is None else [resource.model_copy(deep=True) for resource in resources]
    model = cp_model.CpModel()
    selection_vars = {
        resource.id: model.NewBoolVar(f"select_{resource.id}")
        for resource in catalog
    }

    for resource in catalog:
        if not resource.availability or resource.status != "available":
            model.Add(selection_vars[resource.id] == 0)

    for capability in request.required_capabilities:
        capable_resources = [
            resource.id
            for resource in catalog
            if capability in resource.capability_codes
        ]
        if not capable_resources:
            return CoalitionSolution(
                feasible=False,
                solver_status="INFEASIBLE",
                selected_resources=[],
                selected_resource_ids=[],
                selected_count=0,
                total_capacity=0,
                objective_value=None,
                constraint_explanations=describe_constraints(request),
                infeasible_reason=f"No resource in the catalog can provide the required capability '{capability}'.",
            )
        model.Add(sum(selection_vars[resource_id] for resource_id in capable_resources) >= 1)

    total_capacity = sum(
        (resource.capacity or 0) * selection_vars[resource.id]
        for resource in catalog
    )
    model.Add(total_capacity >= request.minimum_total_capacity)

    model.Minimize(sum(selection_vars.values()))

    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    solver_status_map = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
    }
    solver_status = solver_status_map.get(status, "UNKNOWN")
    explanations = describe_constraints(request)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return CoalitionSolution(
            feasible=False,
            solver_status=solver_status,
            selected_resources=[],
            selected_resource_ids=[],
            selected_count=0,
            total_capacity=0,
            objective_value=None,
            constraint_explanations=explanations,
            infeasible_reason="No feasible coalition satisfies all hard constraints.",
        )

    selected_resources = [
        resource
        for resource in catalog
        if solver.Value(selection_vars[resource.id]) == 1
    ]
    selected_resource_ids = [resource.id for resource in selected_resources]
    selected_count = len(selected_resources)
    solved_total_capacity = sum(resource.capacity or 0 for resource in selected_resources)

    return CoalitionSolution(
        feasible=True,
        solver_status=solver_status,
        selected_resources=selected_resources,
        selected_resource_ids=selected_resource_ids,
        selected_count=selected_count,
        total_capacity=solved_total_capacity,
        objective_value=int(solver.ObjectiveValue()),
        constraint_explanations=explanations,
        infeasible_reason=None,
    )
