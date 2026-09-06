from __future__ import annotations

import logging

try:  # pragma: no cover - lets unit tests run without the SDK installed.
    from strands import tool
except ModuleNotFoundError:  # pragma: no cover
    def tool(function):
        return function

from app.mission import Mission
from app.orchestration import run_pipeline
from app.resources import (
    get_resources_by_required_capability as query_resources_by_required_capability,
    list_available_resources,
)

logger = logging.getLogger(__name__)


@tool
def assess_incident(
    destination: str,
    incident_type: str,
    requirements: list[str] | None = None,
    constraints: list[str] | None = None,
    deadline: str | None = None,
) -> dict[str, object]:
    """Decide whether a meal site can be covered, and by whom.

    This is the only path to a coverage decision. The deterministic pipeline
    derives the required roles, CP-SAT picks the volunteers from the opted-in
    bench, and remove-and-re-solve reports what one cancellation would break.
    The caller reports this output; it never makes the decision itself.
    """

    logger.info("assess_incident called for destination=%s type=%s", destination, incident_type)
    mission = Mission(
        destination=destination,
        incident_type=incident_type,
        requirements=list(requirements or []),
        constraints=list(constraints or []),
        deadline=deadline,
    )
    result = run_pipeline(
        mission,
        resources=list_available_resources(),
        include_resilience=True,
        include_hypergraph=False,
        coalition_min_capacity=0,
    )
    coalition = result.coalition
    logger.info("assess_incident verdict=%s", result.verdict)
    return {
        "verdict": result.verdict,
        "feasible": bool(coalition and coalition.feasible),
        "selected_resource_ids": list(coalition.selected_resource_ids) if coalition else [],
        "required_capabilities": list(result.capability_assessment.rule_required_capability_codes),
        "missing_capabilities": list(result.missing_capabilities),
        "answers": dict(result.answers),
        "synthetic_data": True,
    }


@tool
def get_available_resources() -> dict[str, list[dict[str, object]]]:
    """Return the MealMesh volunteers who opted in and are available right now."""

    logger.info("get_available_resources called")
    resources = list_available_resources()
    logger.info("get_available_resources returning %d resources", len(resources))
    return {"resources": [resource.model_dump() for resource in resources]}


@tool
def get_resources_by_required_capability(
    required_capability: str,
) -> dict[str, object]:
    """Return opted-in volunteers who can cover one required meal-program role."""

    logger.info(
        "get_resources_by_required_capability called for capability=%s",
        required_capability,
    )
    resources = query_resources_by_required_capability(required_capability)
    logger.info(
        "get_resources_by_required_capability returning %d resources",
        len(resources),
    )
    return {
        "required_capability": required_capability,
        "resources": [resource.model_dump() for resource in resources],
    }
