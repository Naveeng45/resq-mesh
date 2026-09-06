from __future__ import annotations

import logging

try:  # pragma: no cover - lets unit tests run without the SDK installed.
    from strands import tool
except ModuleNotFoundError:  # pragma: no cover
    def tool(function):
        return function

from app.resources import (
    get_resources_by_required_capability as query_resources_by_required_capability,
    list_available_resources,
)

logger = logging.getLogger(__name__)


@tool
def get_available_resources() -> dict[str, list[dict[str, object]]]:
    """Return only currently available RESQ-Mesh resources."""

    logger.info("get_available_resources called")
    resources = list_available_resources()
    logger.info("get_available_resources returning %d resources", len(resources))
    return {"resources": [resource.model_dump() for resource in resources]}


@tool
def get_resources_by_required_capability(
    required_capability: str,
) -> dict[str, object]:
    """Return available resources that explicitly provide a capability."""

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
