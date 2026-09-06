"""Single wiring point for the MealMesh deterministic pipeline.

This module chains every layer the lessons built into one flow:

    Mission (facts)          -> app.mission.review_mission        (HITL gate)
      -> Capabilities        -> app.capabilities                 (domain rules)
        -> Coalition         -> app.solver (CP-SAT)              (math decides)
          -> Resilience      -> app.resilience (remove & re-solve)
            -> Hypergraph    -> app.hypergraph                   (representation)

The LLM never runs here. Callers pass in an already-extracted ``Mission`` (from
``app.mission_agent`` in production, or a fixture in demos/tests). Everything in
this module is deterministic, so it is safe to unit-test and safe to trust for
resource allocation. It answers the four project questions:

    CAN?              Is there a feasible coalition?
    HOW?              Which resources, at what capacity?
    WHAT IF?          What breaks the plan if a resource is lost?
    WHAT IS MISSING?  If infeasible, what facts/capabilities are needed?
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from app.capabilities import CAPABILITY_ONTOLOGY, CapabilityAssessment, derive_required_capabilities
from app.hypergraph import CoalitionHyperedge, HypergraphReport, build_hypergraph_report
from app.mission import Mission, MissionReview, review_mission
from app.observability import get_logger, get_trace_id, log_event, new_trace_id, set_trace_id
from app.pydantic_compat import CompatBaseModel
from app.resilience import ResilienceReport, replan
from app.resources import Resource, list_resources
from app.solver import CoalitionRequest, CoalitionSolution, solve_resource_coalition

logger = get_logger(__name__)

# Capability coverage is the binding constraint for a general mission. A capacity
# floor is scenario-specific (e.g. "move >= N people"), so it defaults to 0 and
# callers pass an explicit floor only when the mission actually implies one.
DEFAULT_COALITION_MIN_CAPACITY = 0


class OrchestrationResult(CompatBaseModel):
    """The full deterministic pipeline output for one mission."""

    model_config = ConfigDict(extra="forbid")

    mission: Mission
    review: MissionReview
    capability_assessment: CapabilityAssessment
    coalition: CoalitionSolution | None = None
    resilience: ResilienceReport | None = None
    hypergraph: HypergraphReport | None = None
    missing_capabilities: list[str] = Field(default_factory=list)
    verdict: str
    answers: dict[str, str] = Field(default_factory=dict)
    trace_id: str | None = None


def _capability_label(code: str) -> str:
    for capability in CAPABILITY_ONTOLOGY:
        if capability.code == code:
            return capability.label
    return code


def _unmet_capabilities(required_codes: list[str], catalog: list[Resource]) -> list[str]:
    """Required capabilities that no currently-available resource can provide."""

    available: set[str] = set()
    for resource in catalog:
        if resource.availability and resource.status == "available":
            available.update(resource.capability_codes)
    return [code for code in required_codes if code not in available]


def _verdict(
    review: MissionReview,
    assessment: CapabilityAssessment,
    coalition: CoalitionSolution | None,
    resilience: ResilienceReport | None,
) -> str:
    if review.status != "ready":
        return "needs more facts"
    if assessment.needs_human_review:
        return "needs human review"
    if coalition is None or not coalition.feasible:
        return "no feasible coalition"
    if resilience is not None and resilience.overall_classification == "mission_breaking":
        return "ready but fragile"
    return "ready to deploy"


def _answer_can(coalition: CoalitionSolution | None, review: MissionReview, assessment: CapabilityAssessment) -> str:
    if review.status != "ready":
        return "Unknown - mission is missing critical facts."
    if assessment.needs_human_review:
        return "Unknown - capability assessment needs human review."
    if coalition is None:
        return "Unknown - no coalition was solved."
    return "Yes." if coalition.feasible else "No feasible coalition exists."


def _answer_how(coalition: CoalitionSolution | None) -> str:
    if coalition is None or not coalition.feasible:
        return "n/a - no feasible coalition."
    resources = ", ".join(coalition.selected_resource_ids) or "none"
    return f"{resources} (total_capacity={coalition.total_capacity}, {coalition.solver_status})."


def _answer_what_if(resilience: ResilienceReport | None) -> str:
    if resilience is None:
        return "Not analyzed."
    breaking = ", ".join(resilience.mission_breaking_failure_ids) or "none"
    return f"Overall {resilience.overall_classification}; mission-breaking resources: {breaking}."


def _answer_what_is_missing(
    review: MissionReview,
    assessment: CapabilityAssessment,
    coalition: CoalitionSolution | None,
    resilience: ResilienceReport | None,
    missing_capabilities: list[str],
) -> str:
    if review.status != "ready":
        return "Facts: " + (", ".join(review.missing_critical_facts) or "unknown")
    if assessment.needs_human_review:
        return "Review: " + ("; ".join(assessment.review_reasons) or "human review required")
    if coalition is None:
        return "No coalition was solved."
    if not coalition.feasible:
        if missing_capabilities:
            return "Missing capability: " + ", ".join(_capability_label(code) for code in missing_capabilities)
        return coalition.infeasible_reason or "No feasible coalition satisfies the hard constraints."
    if resilience is not None and resilience.mission_breaking_failure_ids:
        return (
            "Plan is fragile - losing any of: "
            + ", ".join(resilience.mission_breaking_failure_ids)
            + " leaves capabilities uncovered."
        )
    return "Nothing - mission is feasible and resilient."


def run_pipeline(
    mission: Mission,
    *,
    resources: list[Resource] | None = None,
    hyperedges: list[CoalitionHyperedge] | None = None,
    include_resilience: bool = True,
    include_hypergraph: bool = True,
    coalition_min_capacity: int = DEFAULT_COALITION_MIN_CAPACITY,
    replan_min_capacity: int | None = None,
    trace_id: str | None = None,
) -> OrchestrationResult:
    """Run every deterministic layer for one mission and return a combined result.

    Args:
        mission: Structured incident facts (already extracted; no LLM here).
        resources: World-state catalog. Defaults to the synthetic catalog.
        hyperedges: Coalition-unit catalog for the hypergraph view. If omitted,
            the hypergraph layer is skipped (a catalog with no defined coalition
            units has nothing meaningful to project).
        include_resilience: Run remove-and-re-solve failure analysis.
        include_hypergraph: Build the hypergraph representation.
        coalition_min_capacity: Minimum total capacity the coalition must meet.
        replan_min_capacity: Capacity threshold for replanning. Defaults to
            ``coalition_min_capacity`` so the baseline and its replacements are
            judged against the same bar.
    """

    active_trace_id = set_trace_id(trace_id or get_trace_id() or new_trace_id())
    log_event(
        logger,
        "pipeline.start",
        destination=mission.destination,
        incident_type=mission.incident_type,
    )

    catalog = list_resources() if resources is None else resources
    review = review_mission(mission)
    capability_assessment = derive_required_capabilities(mission)
    required_codes = capability_assessment.rule_required_capability_codes

    coalition: CoalitionSolution | None = None
    if review.status == "ready" and not capability_assessment.needs_human_review and required_codes:
        coalition = solve_resource_coalition(
            CoalitionRequest(
                required_capabilities=required_codes,
                minimum_total_capacity=coalition_min_capacity,
            ),
            resources=catalog,
        )

    resilience: ResilienceReport | None = None
    if include_resilience and coalition is not None and coalition.feasible:
        effective_replan_capacity = (
            coalition_min_capacity if replan_min_capacity is None else replan_min_capacity
        )
        resilience = replan(
            CoalitionRequest(
                required_capabilities=required_codes,
                minimum_total_capacity=effective_replan_capacity,
            ),
            coalition,
            resources=catalog,
        )

    hypergraph: HypergraphReport | None = None
    if include_hypergraph and hyperedges and coalition is not None and coalition.feasible:
        hypergraph = build_hypergraph_report(
            mission,
            CoalitionRequest(
                required_capabilities=required_codes,
                minimum_total_capacity=coalition_min_capacity,
            ),
            coalition,
            catalog,
            hyperedges,
        )

    missing_capabilities: list[str] = []
    if coalition is not None and not coalition.feasible:
        missing_capabilities = _unmet_capabilities(required_codes, catalog)

    verdict = _verdict(review, capability_assessment, coalition, resilience)
    log_event(
        logger,
        "pipeline.finish",
        verdict=verdict,
        feasible=bool(coalition and coalition.feasible),
        selected=coalition.selected_resource_ids if coalition else [],
    )
    answers = {
        "CAN": _answer_can(coalition, review, capability_assessment),
        "HOW": _answer_how(coalition),
        "WHAT IF": _answer_what_if(resilience),
        "WHAT IS MISSING": _answer_what_is_missing(
            review, capability_assessment, coalition, resilience, missing_capabilities
        ),
    }

    return OrchestrationResult(
        mission=mission,
        review=review,
        capability_assessment=capability_assessment,
        coalition=coalition,
        resilience=resilience,
        hypergraph=hypergraph,
        missing_capabilities=missing_capabilities,
        verdict=verdict,
        answers=answers,
        trace_id=active_trace_id,
    )


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def render_report(result: OrchestrationResult) -> str:
    """Render the pipeline result as a scannable text report."""

    mission = result.mission
    lines: list[str] = ["=== MealMesh ===", ""]

    lines.append(
        "Mission: "
        f"{mission.destination or 'unknown'} | {mission.incident_type or 'unknown'} | "
        f"requirements={_join(mission.requirements)}"
    )
    lines.append(f"Review: {result.review.status}")
    if result.review.missing_critical_facts:
        lines.append(f"Missing facts: {_join(result.review.missing_critical_facts)}")
    lines.append(
        "Capabilities: "
        + _join([capability.code for capability in result.capability_assessment.required_capabilities])
    )
    if result.capability_assessment.needs_human_review:
        lines.append("Human review: required")
        for reason in result.capability_assessment.review_reasons:
            lines.append(f"  - {reason}")

    lines.append("")
    if result.coalition is None:
        lines.append("Coalition: skipped (mission needs human review or is missing facts)")
    elif not result.coalition.feasible:
        lines.append(f"Coalition: INFEASIBLE - {result.coalition.infeasible_reason}")
    else:
        lines.append(
            "Coalition: "
            f"{_join(result.coalition.selected_resource_ids)} | "
            f"total_capacity={result.coalition.total_capacity} | {result.coalition.solver_status}"
        )

    if result.resilience is not None:
        lines.append("")
        lines.append(f"Resilience: {result.resilience.overall_classification}")
        lines.append(
            "  recoverable="
            f"{_join(result.resilience.recoverable_failure_ids)} | "
            f"mission_breaking={_join(result.resilience.mission_breaking_failure_ids)}"
        )
        lines.append(f"  {result.resilience.summary}")

    if result.hypergraph is not None:
        report = result.hypergraph
        lines.append("")
        lines.append(
            "Hypergraph: coalition hyperedge="
            + (report.selected_hyperedge.id if report.selected_hyperedge else "none")
        )
        lines.append(
            "  emergent_capabilities="
            + _join([capability.code for capability in report.emergent_capabilities])
        )
        lines.append(
            "  structural: components="
            f"{report.metrics.connected_components} | lambda2={report.metrics.lambda2}"
        )

    lines.append("")
    lines.append("Answers:")
    for question, answer in result.answers.items():
        lines.append(f"  {question}? {answer}")
    lines.append("")
    lines.append(f"Verdict: {result.verdict}")

    return "\n".join(lines)
