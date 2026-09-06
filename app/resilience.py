from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from app.capabilities import CAPABILITY_ONTOLOGY, resolve_capability_code
from app.pydantic_compat import CompatBaseModel
from app.resources import Resource, list_resources
from app.solver import CoalitionRequest, CoalitionSolution, solve_resource_coalition


class ReplanScenario(CompatBaseModel):
    """One counterfactual failure case for a selected resource."""

    model_config = ConfigDict(extra="forbid")

    failed_resource_id: str
    failed_resource_name: str
    classification: Literal["recoverable", "mission_breaking"]
    recoverable: bool
    original_selected_resource_ids: list[str] = Field(default_factory=list)
    replacement_selected_resource_ids: list[str] = Field(default_factory=list)
    dropped_resource_ids: list[str] = Field(default_factory=list)
    added_resource_ids: list[str] = Field(default_factory=list)
    unmet_capabilities: list[str] = Field(default_factory=list)
    replacement_solution: CoalitionSolution | None = None
    replacement_summary: str


class ResilienceReport(CompatBaseModel):
    """Summary of how the plan behaves when selected resources fail."""

    model_config = ConfigDict(extra="forbid")

    baseline_selected_resource_ids: list[str] = Field(default_factory=list)
    total_selected_resources: int
    recoverable_failure_ids: list[str] = Field(default_factory=list)
    mission_breaking_failure_ids: list[str] = Field(default_factory=list)
    overall_classification: Literal["recoverable", "mission_breaking"]
    scenarios: list[ReplanScenario] = Field(default_factory=list)
    summary: str


def _capability_label(code: str) -> str:
    for capability in CAPABILITY_ONTOLOGY:
        if capability.code == code:
            return capability.label
    return code


def _find_unmet_capabilities(
    request: CoalitionRequest,
    resources: list[Resource],
) -> list[str]:
    available_codes: set[str] = set()
    for resource in resources:
        if not resource.availability or resource.status != "available":
            continue
        available_codes.update(resource.capability_codes)

    return [
        capability
        for capability in request.required_capabilities
        if resolve_capability_code(capability) not in available_codes
    ]


def _clone_with_failure(resources: list[Resource], failed_resource_id: str) -> list[Resource]:
    cloned_resources = [resource.model_copy(deep=True) for resource in resources]
    for resource in cloned_resources:
        if resource.id == failed_resource_id:
            resource.availability = False
            resource.status = "offline"
            break
    return cloned_resources


def _replacement_summary(
    failed_resource_id: str,
    feasible: bool,
    replacement_ids: list[str],
    unmet_capabilities: list[str],
) -> str:
    if feasible:
        return (
            f"Resource {failed_resource_id} can be replaced with "
            f"{', '.join(replacement_ids) if replacement_ids else 'an empty coalition'}."
        )

    if unmet_capabilities:
        labels = ", ".join(_capability_label(code) for code in unmet_capabilities)
        return f"Resource {failed_resource_id} is mission-breaking because these capabilities are now uncovered: {labels}."

    return f"Resource {failed_resource_id} is mission-breaking because no feasible replacement coalition exists."


def replan(
    request: CoalitionRequest,
    baseline_solution: CoalitionSolution,
    resources: list[Resource] | None = None,
) -> ResilienceReport:
    """Run counterfactual failure tests for each selected resource."""

    if not baseline_solution.feasible:
        raise ValueError("baseline_solution must be feasible before replanning")

    catalog = list_resources() if resources is None else [resource.model_copy(deep=True) for resource in resources]
    scenarios: list[ReplanScenario] = []
    recoverable_ids: list[str] = []
    mission_breaking_ids: list[str] = []

    for failed_resource_id in baseline_solution.selected_resource_ids:
        failed_resource = next(resource for resource in catalog if resource.id == failed_resource_id)
        failed_catalog = _clone_with_failure(catalog, failed_resource_id)
        replacement_solution = solve_resource_coalition(request, resources=failed_catalog)
        unmet_capabilities = [] if replacement_solution.feasible else _find_unmet_capabilities(request, failed_catalog)

        replacement_ids = replacement_solution.selected_resource_ids if replacement_solution.feasible else []
        dropped_ids = sorted(set(baseline_solution.selected_resource_ids) - set(replacement_ids))
        added_ids = sorted(set(replacement_ids) - set(baseline_solution.selected_resource_ids))
        recoverable = replacement_solution.feasible
        classification: Literal["recoverable", "mission_breaking"] = "recoverable" if recoverable else "mission_breaking"

        if recoverable:
            recoverable_ids.append(failed_resource_id)
        else:
            mission_breaking_ids.append(failed_resource_id)

        scenarios.append(
            ReplanScenario(
                failed_resource_id=failed_resource_id,
                failed_resource_name=failed_resource.name,
                classification=classification,
                recoverable=recoverable,
                original_selected_resource_ids=list(baseline_solution.selected_resource_ids),
                replacement_selected_resource_ids=replacement_ids,
                dropped_resource_ids=dropped_ids,
                added_resource_ids=added_ids,
                unmet_capabilities=unmet_capabilities,
                replacement_solution=replacement_solution if recoverable else None,
                replacement_summary=_replacement_summary(
                    failed_resource_id,
                    recoverable,
                    replacement_ids,
                    unmet_capabilities,
                ),
            )
        )

    overall_classification: Literal["recoverable", "mission_breaking"]
    if mission_breaking_ids:
        overall_classification = "mission_breaking"
    else:
        overall_classification = "recoverable"

    summary = (
        f"{len(recoverable_ids)} of {len(scenarios)} selected resources have recoverable failures."
        if recoverable_ids
        else "Every selected resource failure breaks the mission."
    )
    if mission_breaking_ids:
        summary += f" Mission-breaking resources: {', '.join(mission_breaking_ids)}."

    return ResilienceReport(
        baseline_selected_resource_ids=list(baseline_solution.selected_resource_ids),
        total_selected_resources=baseline_solution.selected_count,
        recoverable_failure_ids=recoverable_ids,
        mission_breaking_failure_ids=mission_breaking_ids,
        overall_classification=overall_classification,
        scenarios=scenarios,
        summary=summary,
    )
