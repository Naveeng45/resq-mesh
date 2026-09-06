from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from app.mission import Mission
from app.pydantic_compat import CompatBaseModel


class CapabilityDefinition(CompatBaseModel):
    """A capability in the lesson's small deterministic ontology."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    description: str


class RequiredCapability(CompatBaseModel):
    """A capability required for a mission, derived by deterministic rules."""

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


CAPABILITY_ONTOLOGY: tuple[CapabilityDefinition, ...] = (
    CapabilityDefinition(
        code="flood_access",
        label="Flood Access",
        description="Reach isolated areas or operate where roads are blocked by water.",
    ),
    CapabilityDefinition(
        code="field_triage",
        label="Field Triage",
        description="Assess and stabilize patients on site.",
    ),
    CapabilityDefinition(
        code="road_transport",
        label="Road Transport",
        description="Move people or supplies by road when routes are passable.",
    ),
    CapabilityDefinition(
        code="communications",
        label="Communications",
        description="Provide emergency communication support.",
    ),
)

CAPABILITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "flood_access": (
        "boat",
        "watercraft",
        "flood boat",
        "flood access",
        "water access",
    ),
    "field_triage": (
        "medical team",
        "medic",
        "medical",
        "triage",
        "patient care",
    ),
    "road_transport": (
        "truck",
        "vehicle",
        "ground transport",
        "road transport",
    ),
    "communications": (
        "radio",
        "comms",
        "communications",
        "satcom",
    ),
}


def list_capabilities() -> list[CapabilityDefinition]:
    """Return a copy of the small ontology."""

    return [capability.model_copy(deep=True) for capability in CAPABILITY_ONTOLOGY]


def resolve_capability_code(text: str) -> str | None:
    """Map user language to an ontology code when the match is exact enough."""

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
    """Turn extracted facts into mission requirements using deterministic rules."""

    required: list[RequiredCapability] = []
    review_reasons: list[str] = []

    flood_signals: list[str] = []
    if mission.incident_type and _normalize_text(mission.incident_type) == "flood":
        flood_signals.append(f"incident_type={mission.incident_type}")
    for fact in (mission.constraints + mission.requirements):
        if _contains_any(
            fact,
            (
                "flood",
                "floodwater",
                "flood water",
                "waterlogged",
                "isolated",
                "blocked road",
                "roads blocked",
                "road blocked",
                "boat",
                "watercraft",
            ),
        ):
            flood_signals.append(fact)
    if flood_signals:
        flood_confidence = 0.95 if any("boat" in _normalize_text(fact) for fact in mission.requirements) else 0.72
        _add_required_capability(
            required,
            "flood_access",
            "Flood or water blockage signals indicate a need for access to isolated terrain.",
            flood_confidence,
            flood_signals,
        )

    if any(
        _contains_any(
            fact,
            (
                "medical team",
                "medic",
                "medical",
                "triage",
                "patient",
                "patients",
                "casualty",
                "clinic",
            ),
        )
        for fact in mission.requirements
    ):
        _add_required_capability(
            required,
            "field_triage",
            "The user explicitly asked for medical support.",
            0.95,
            [fact for fact in mission.requirements if _contains_any(fact, ("medical", "triage", "patient", "clinic"))],
        )

    if any(
        _contains_any(fact, ("truck", "vehicle", "ground transport", "road transport"))
        for fact in mission.requirements
    ):
        _add_required_capability(
            required,
            "road_transport",
            "The user explicitly asked for road-based transport.",
            0.95,
            [fact for fact in mission.requirements if _contains_any(fact, ("truck", "vehicle", "ground transport", "road transport"))],
        )

    if any(_contains_any(fact, ("radio", "comms", "communications", "satcom")) for fact in mission.requirements):
        _add_required_capability(
            required,
            "communications",
            "The user explicitly asked for communications support.",
            0.95,
            [fact for fact in mission.requirements if _contains_any(fact, ("radio", "comms", "communications", "satcom"))],
        )

    requested_codes = _requested_capability_codes(mission)
    rule_codes = [capability.code for capability in required]

    if mission.incident_type is None:
        review_reasons.append("incident_type is missing, so the rules cannot anchor the response.")

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
