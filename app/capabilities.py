from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from app.mission import Mission
from app.pydantic_compat import CompatBaseModel


class CapabilityDefinition(CompatBaseModel):
    """A capability in the small deterministic meal-program ontology."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    description: str


class RequiredCapability(CompatBaseModel):
    """A capability required for a coverage window, derived by deterministic rules."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_facts: list[str] = Field(default_factory=list)


class CapabilityAssessment(CompatBaseModel):
    """Rule-derived requirements plus a comparison with LLM-extracted requests."""

    model_config = ConfigDict(extra="forbid")

    required_capabilities: list[RequiredCapability] = Field(default_factory=list)
    llm_requested_capability_codes: list[str] = Field(default_factory=list)
    rule_required_capability_codes: list[str] = Field(default_factory=list)
    comparison_status: Literal["aligned", "broader_than_requests", "narrower_than_requests", "not_comparable"]
    needs_human_review: bool
    review_reasons: list[str] = Field(default_factory=list)


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


# Three roles, because a meal site opens only when all three are present: someone
# who may legally drive the van, someone who may legally handle the food, and
# someone who can unlock the building.
CAPABILITY_ONTOLOGY: tuple[CapabilityDefinition, ...] = (
    CapabilityDefinition(
        code="van_certified_driver",
        label="Van-certified driver",
        description="Cleared to drive the food-bank van to a distribution site.",
    ),
    CapabilityDefinition(
        code="food_handler",
        label="Food handler",
        description="Certified to pack and serve food safely at a site.",
    ),
    CapabilityDefinition(
        code="site_keyholder",
        label="Site keyholder",
        description="Holds building access to open, host, and close a site.",
    ),
)

CAPABILITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "van_certified_driver": (
        "driver",
        "van driver",
        "van",
        "van cert",
        "van certified",
        "van-certified driver",
        "delivery driver",
    ),
    "food_handler": (
        "packer",
        "food handler",
        "food safety",
        "server",
        "kitchen help",
        "meal packer",
    ),
    "site_keyholder": (
        "site lead",
        "keyholder",
        "key holder",
        "site keyholder",
        "site host",
        "building access",
    ),
}

# Every coverage type this program runs needs all three roles. Doctrine is a
# lookup table on purpose: a coordinator can read it, and so can a judge.
INCIDENT_CAPABILITY_DEFAULTS: dict[str, tuple[str, ...]] = {
    "thursday_distribution": ("van_certified_driver", "food_handler", "site_keyholder"),
    "meal_service": ("van_certified_driver", "food_handler", "site_keyholder"),
    "pantry": ("van_certified_driver", "food_handler", "site_keyholder"),
}


def list_capabilities() -> list[CapabilityDefinition]:
    """Return a copy of the small ontology."""

    return [capability.model_copy(deep=True) for capability in CAPABILITY_ONTOLOGY]


def resolve_capability_code(text: str) -> str | None:
    """Map coordinator language to an ontology code when the match is exact enough."""

    normalized = _normalize_text(text)
    for capability in CAPABILITY_ONTOLOGY:
        if normalized in {
            _normalize_text(capability.code),
            _normalize_text(capability.label),
        }:
            return capability.code

    for code, synonyms in CAPABILITY_SYNONYMS.items():
        if normalized in {_normalize_text(term) for term in synonyms}:
            return code
    return None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = _normalize_text(text)
    return any(term in normalized for term in terms)


def _add_required_capability(
    required: list[RequiredCapability],
    code: str,
    reason: str,
    confidence: float,
    source_facts: list[str],
) -> None:
    for existing in required:
        if existing.code == code:
            existing.confidence = max(existing.confidence, confidence)
            existing.source_facts = list(dict.fromkeys(existing.source_facts + source_facts))
            if reason not in existing.reason:
                existing.reason = f"{existing.reason}; {reason}"
            return

    capability = next(item for item in CAPABILITY_ONTOLOGY if item.code == code)
    required.append(
        RequiredCapability(
            code=capability.code,
            label=capability.label,
            reason=reason,
            confidence=confidence,
            source_facts=list(dict.fromkeys(source_facts)),
        )
    )


def _requested_capability_codes(mission: Mission) -> list[str]:
    codes: list[str] = []
    for request in mission.requirements:
        code = resolve_capability_code(request)
        if code is not None and code not in codes:
            codes.append(code)
    return codes


def derive_required_capabilities(mission: Mission) -> CapabilityAssessment:
    """Turn extracted coverage facts into required roles using deterministic rules.

    The language model never reaches this function's output path: it supplies
    facts, and these rules decide which roles a site needs. Anything the rules
    cannot anchor is flagged for human review instead of guessed.
    """

    required: list[RequiredCapability] = []
    review_reasons: list[str] = []

    coverage_type = _normalize_text(mission.incident_type or "")
    doctrine_codes = INCIDENT_CAPABILITY_DEFAULTS.get(coverage_type, ())
    for code in doctrine_codes:
        _add_required_capability(
            required,
            code,
            f"Every {coverage_type.replace('_', ' ')} needs this role to open the site.",
            0.9,
            [f"incident_type={mission.incident_type}"],
        )

    # An explicitly named role is a stronger signal than doctrine alone.
    for code, synonyms in CAPABILITY_SYNONYMS.items():
        matching_facts = [
            fact for fact in mission.requirements if _contains_any(fact, synonyms)
        ]
        if matching_facts:
            _add_required_capability(
                required,
                code,
                "The coordinator explicitly asked for this role.",
                0.95,
                matching_facts,
            )

    requested_codes = _requested_capability_codes(mission)
    # Keep required roles in ontology order so "what is missing" reads the same
    # way every time (driver, then handler, then keyholder).
    order = {capability.code: index for index, capability in enumerate(CAPABILITY_ONTOLOGY)}
    required.sort(key=lambda capability: order[capability.code])
    rule_codes = [capability.code for capability in required]

    if mission.incident_type is None:
        review_reasons.append("incident_type is missing, so the rules cannot anchor the coverage window.")
    elif not doctrine_codes:
        review_reasons.append(
            f"Coverage type '{mission.incident_type}' is not in deterministic doctrine."
        )

    if not required:
        review_reasons.append("No capability rule matched the extracted facts.")

    unresolved_requests = [
        request for request in mission.requirements if resolve_capability_code(request) is None
    ]
    if unresolved_requests:
        review_reasons.append(
            "Some extracted request terms do not map cleanly to the capability ontology: "
            + ", ".join(unresolved_requests)
        )

    if any(capability.confidence < 0.8 for capability in required):
        review_reasons.append("At least one derived capability is low-confidence and should be reviewed.")

    requested_set = set(requested_codes)
    rule_set = set(rule_codes)
    if requested_set and rule_set:
        if requested_set == rule_set:
            comparison_status: Literal["aligned", "broader_than_requests", "narrower_than_requests", "not_comparable"] = "aligned"
        elif rule_set.issuperset(requested_set):
            comparison_status = "broader_than_requests"
        elif rule_set.issubset(requested_set):
            comparison_status = "narrower_than_requests"
        else:
            comparison_status = "not_comparable"
    else:
        comparison_status = "not_comparable"

    needs_human_review = bool(review_reasons)

    return CapabilityAssessment(
        required_capabilities=required,
        llm_requested_capability_codes=requested_codes,
        rule_required_capability_codes=rule_codes,
        comparison_status=comparison_status,
        needs_human_review=needs_human_review,
        review_reasons=review_reasons,
    )
