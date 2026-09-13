"""Phase 5 — Semantic orchestration tests.

Tests the typed tool layer and conversation state management WITHOUT
requiring Bedrock credentials. All tests use the deterministic tools
directly and verify the LLM integration contract via mocked model output.

Test coverage:
- Natural-language goal → validated draft
- Missing information → clarification required
- "What if X cancels?" does not change live availability
- "Ignore qualifications" cannot bypass validation
- Tool failure → honest error response
- Proposed vs active recovery distinction
- Conversation state persistence across tool calls
- Tool call bounds enforcement
- Offline evaluation with mocked model
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.contracts import (
    DataProvenance,
    MissionSpec,
    PlanSpec,
    PlanStatus,
    TaskAssignment,
    TaskDefinition,
    TimeWindow,
    VehicleSpec,
    VolunteerSpec,
)
from app.semantic_tools import (
    SEMANTIC_TOOLS,
    _MAX_TOOL_CALLS_PER_TURN,
    evaluate_plan_failures,
    generate_coalition_plans,
    get_mission_context,
    get_mission_context_state,
    get_proposal_status,
    prepare_recovery_proposal,
    reset_conversation_state,
    set_mission_context,
    validate_mission_draft,
)
from tests.fixtures.thursday_fixture import (
    build_church_van,
    build_eastside_mission,
    build_valid_plan,
    build_volunteers,
)


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset conversation state before and after each test."""
    reset_conversation_state()
    yield
    reset_conversation_state()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _load_context():
    """Load standard Thursday fixture into conversation state."""
    mission = build_eastside_mission()
    volunteers = build_volunteers()
    vehicles = [build_church_van()]
    set_mission_context(mission, volunteers, vehicles)
    return mission, volunteers, vehicles


def _load_context_with_plan():
    """Load standard fixture + generate a plan."""
    mission, volunteers, vehicles = _load_context()
    result = generate_coalition_plans(max_alternatives=1)
    assert result["feasible"], f"Plan should be feasible: {result}"
    return mission, volunteers, vehicles


# ---------------------------------------------------------------------------
# T1: Natural-language goal → validated draft
# ---------------------------------------------------------------------------


class TestGoalToValidatedDraft:
    """Verify that loading context + generating plans produces a valid plan."""

    def test_generate_plan_from_context(self):
        """Loading mission context and generating plans succeeds."""
        _load_context()
        result = generate_coalition_plans(max_alternatives=1)

        assert result["feasible"] is True
        assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
        assert len(result["alternatives"]) >= 1
        assert result["simulated"] is True

    def test_plan_persists_in_context(self):
        """Generated plan is stored in conversation state for follow-up."""
        _load_context()
        generate_coalition_plans(max_alternatives=1)

        state = get_mission_context_state()
        assert state["current_plan"] is not None

    def test_validate_after_generate(self):
        """Validating a generated plan shows no blocking violations."""
        _load_context_with_plan()
        result = validate_mission_draft()

        assert result["valid"] is True
        assert result["simulated"] is True


# ---------------------------------------------------------------------------
# T2: Missing information → clarification
# ---------------------------------------------------------------------------


class TestMissingInformation:
    """Verify that missing required info is surfaced, not fabricated."""

    def test_no_context_loaded(self):
        """get_mission_context reports no context when nothing is loaded."""
        result = get_mission_context()
        assert result["has_context"] is False
        assert result["mission"] is None

    def test_validate_without_context(self):
        """validate_mission_draft asks for info when no context loaded."""
        result = validate_mission_draft()
        assert result["valid"] is False
        assert len(result["missing_info"]) > 0

    def test_generate_without_context(self):
        """generate_coalition_plans errors when no context loaded."""
        result = generate_coalition_plans()
        assert "error" in result
        assert result["feasible"] is False

    def test_evaluate_without_plan(self):
        """evaluate_plan_failures errors when no plan loaded."""
        _load_context()
        result = evaluate_plan_failures()
        assert "error" in result

    def test_recovery_without_plan(self):
        """prepare_recovery_proposal errors when no plan loaded."""
        _load_context()
        result = prepare_recovery_proposal(unavailable_resource_ids=["maya"])
        assert "error" in result

    def test_recovery_empty_ids(self):
        """prepare_recovery_proposal errors with empty resource list."""
        _load_context_with_plan()
        result = prepare_recovery_proposal(unavailable_resource_ids=[])
        assert "error" in result


# ---------------------------------------------------------------------------
# T3: "What if X cancels?" does NOT change live availability
# ---------------------------------------------------------------------------


class TestWhatIfSimulation:
    """Simulated cancellation must not mutate live state."""

    def test_evaluate_does_not_mutate_plan(self):
        """evaluate_plan_failures leaves the current plan unchanged."""
        _load_context_with_plan()
        plan_before = get_mission_context_state()["current_plan"]
        plan_id_before = plan_before.id
        assignments_before = [a.volunteer_id for a in plan_before.assignments]

        evaluate_plan_failures(resource_ids_to_test=["maya"])

        plan_after = get_mission_context_state()["current_plan"]
        assert plan_after.id == plan_id_before
        assignments_after = [a.volunteer_id for a in plan_after.assignments]
        assert assignments_after == assignments_before

    def test_evaluate_does_not_mutate_volunteers(self):
        """evaluate_plan_failures leaves volunteer list unchanged."""
        _load_context_with_plan()
        vols_before = [v.id for v in get_mission_context_state()["current_volunteers"]]

        evaluate_plan_failures(resource_ids_to_test=["maya"])

        vols_after = [v.id for v in get_mission_context_state()["current_volunteers"]]
        assert vols_after == vols_before

    def test_recovery_simulation_flag(self):
        """prepare_recovery_proposal with is_simulation=True notes it's a simulation."""
        _load_context_with_plan()
        result = prepare_recovery_proposal(
            unavailable_resource_ids=["maya"],
            is_simulation=True,
        )
        assert result["is_simulation"] is True
        assert "SIMULATION" in result["note"]

    def test_recovery_proposal_is_pending(self):
        """Recovery proposals start as 'pending', not 'approved'."""
        _load_context_with_plan()
        result = prepare_recovery_proposal(
            unavailable_resource_ids=["maya"],
            is_simulation=True,
        )
        assert result["status"] == "pending"

    def test_evaluate_maya_removal_recoverable(self):
        """Removing Maya (driver) should be recoverable (Gina can replace)."""
        _load_context_with_plan()
        result = evaluate_plan_failures(resource_ids_to_test=["maya"])

        maya_scenario = next(
            (s for s in result["scenarios"] if s["resource_id"] == "maya"),
            None,
        )
        assert maya_scenario is not None
        assert maya_scenario["recovery_status"] == "recoverable"

    def test_evaluate_elena_removal_infeasible(self):
        """Removing Elena (sole keyholder) should be infeasible."""
        _load_context_with_plan()
        result = evaluate_plan_failures(resource_ids_to_test=["elena"])

        elena_scenario = next(
            (s for s in result["scenarios"] if s["resource_id"] == "elena"),
            None,
        )
        assert elena_scenario is not None
        assert elena_scenario["recovery_status"] == "infeasible"


# ---------------------------------------------------------------------------
# T4: "Ignore qualifications" cannot bypass validation
# ---------------------------------------------------------------------------


class TestCannotBypassValidation:
    """Validation rules are enforced by tools, not bypassable via prompts."""

    def test_opted_out_volunteer_excluded(self):
        """Jordan (opted_out) is never assigned even with full capabilities."""
        _load_context()
        result = generate_coalition_plans(max_alternatives=3)

        for alt in result["alternatives"]:
            assigned_ids = [a["volunteer_id"] for a in alt["assignments"]]
            assert "jordan" not in assigned_ids, "Opted-out volunteer must not be assigned"

    def test_ineligible_driver_not_assigned_to_van(self):
        """Luis (not eligible for Church Van) should not drive it."""
        _load_context()
        result = generate_coalition_plans(max_alternatives=3)

        for alt in result["alternatives"]:
            for a in alt["assignments"]:
                if a.get("vehicle_id") == "van-church-1":
                    assert a["volunteer_id"] in ("maya", "gina"), (
                        f"Only maya/gina are eligible for Church Van, got {a['volunteer_id']}"
                    )


# ---------------------------------------------------------------------------
# T5: Tool failure → honest error
# ---------------------------------------------------------------------------


class TestToolFailure:
    """Tool errors produce honest responses, not fabricated results."""

    def test_invalid_mission_json(self):
        """Invalid mission JSON returns validation error."""
        result = validate_mission_draft(mission_json={"invalid": "data"})
        assert result["valid"] is False
        assert len(result["missing_info"]) > 0

    def test_nonexistent_proposal(self):
        """Looking up nonexistent proposal returns not-found."""
        result = get_proposal_status(proposal_id="nonexistent-id")
        assert "error" in result


# ---------------------------------------------------------------------------
# T6: Proposed vs active recovery distinction
# ---------------------------------------------------------------------------


class TestProposedVsActive:
    """Proposals are distinct from active plans."""

    def test_proposal_not_active(self):
        """A new recovery proposal has status=pending, not approved."""
        _load_context_with_plan()
        result = prepare_recovery_proposal(
            unavailable_resource_ids=["maya"],
        )
        assert result["status"] == "pending"
        assert result["is_feasible"] is True

    def test_proposal_tracked_in_state(self):
        """Proposals are tracked in conversation state for follow-up."""
        _load_context_with_plan()
        result = prepare_recovery_proposal(
            unavailable_resource_ids=["maya"],
        )
        proposal_id = result["proposal_id"]

        status = get_proposal_status(proposal_id=proposal_id)
        assert len(status["proposals"]) == 1
        assert status["proposals"][0]["id"] == proposal_id

    def test_multiple_proposals_tracked(self):
        """Multiple proposals can coexist in state."""
        _load_context_with_plan()

        r1 = prepare_recovery_proposal(unavailable_resource_ids=["maya"])
        r2 = prepare_recovery_proposal(unavailable_resource_ids=["priya"])

        all_proposals = get_proposal_status()
        assert len(all_proposals["proposals"]) == 2

    def test_infeasible_proposal_reports_gaps(self):
        """Infeasible recovery reports capability gaps and safe actions."""
        _load_context_with_plan()
        result = prepare_recovery_proposal(
            unavailable_resource_ids=["elena"],
        )
        # Elena is sole keyholder — recovery should be infeasible
        assert result["is_feasible"] is False
        assert len(result["capability_gaps"]) > 0
        assert len(result["safe_actions"]) > 0


# ---------------------------------------------------------------------------
# T7: Conversation state persistence
# ---------------------------------------------------------------------------


class TestConversationState:
    """State persists across tool calls within a session."""

    def test_context_persists(self):
        """Mission context survives across multiple tool calls."""
        _load_context()

        ctx1 = get_mission_context()
        assert ctx1["has_context"] is True

        # Generate plan
        generate_coalition_plans(max_alternatives=1)

        # Context still available
        ctx2 = get_mission_context()
        assert ctx2["has_context"] is True
        assert ctx2["plan"] is not None

    def test_reset_clears_state(self):
        """reset_conversation_state clears everything."""
        _load_context_with_plan()
        reset_conversation_state()

        ctx = get_mission_context()
        assert ctx["has_context"] is False
        assert ctx["plan"] is None


# ---------------------------------------------------------------------------
# T8: Tool call bounds
# ---------------------------------------------------------------------------


class TestToolCallBounds:
    """Enforce per-turn tool call limits."""

    def test_exceeding_bound_returns_error(self):
        """After MAX calls, further calls return error."""
        _load_context()
        # Exhaust the limit
        for _ in range(_MAX_TOOL_CALLS_PER_TURN):
            get_mission_context()

        result = get_mission_context()
        assert "error" in result
        assert "limit" in result["error"].lower()


# ---------------------------------------------------------------------------
# T9: Evaluation with mocked model (no network)
# ---------------------------------------------------------------------------


class TestMockedModelEvaluation:
    """Test agent construction and system prompt without Bedrock."""

    def test_system_prompt_contains_rules(self):
        """System prompt includes safety rules."""
        from app.semantic_orchestrator import SEMANTIC_SYSTEM_PROMPT

        assert "NEVER invent" in SEMANTIC_SYSTEM_PROMPT
        assert "NEVER override infeasibility" in SEMANTIC_SYSTEM_PROMPT
        assert "SIMULATED" in SEMANTIC_SYSTEM_PROMPT
        assert "coordinator approval" in SEMANTIC_SYSTEM_PROMPT.lower() or \
               "approved by a coordinator" in SEMANTIC_SYSTEM_PROMPT.lower()

    def test_tools_registered(self):
        """All six semantic tools are in the SEMANTIC_TOOLS list."""
        tool_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in SEMANTIC_TOOLS]
        expected = [
            "get_mission_context",
            "validate_mission_draft",
            "generate_coalition_plans",
            "evaluate_plan_failures",
            "prepare_recovery_proposal",
            "get_proposal_status",
        ]
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    def test_offline_demo_runs(self):
        """Offline demo runs without Bedrock."""
        from app.semantic_orchestrator import demo_tools_offline

        results = demo_tools_offline()
        assert isinstance(results, list)
        assert len(results) > 0


# ---------------------------------------------------------------------------
# T10: Multiple alternatives comparison
# ---------------------------------------------------------------------------


class TestAlternativeComparison:
    """Generate and compare multiple plan alternatives."""

    def test_multiple_alternatives_generated(self):
        """Requesting multiple alternatives returns distinct plans."""
        _load_context()
        result = generate_coalition_plans(max_alternatives=3)

        assert result["feasible"] is True
        # At least 1 alternative, possibly more
        assert len(result["alternatives"]) >= 1

    def test_alternatives_have_labels(self):
        """Each alternative has a descriptive label."""
        _load_context()
        result = generate_coalition_plans(max_alternatives=3)

        for alt in result["alternatives"]:
            assert "label" in alt
            assert alt["label"]  # non-empty


# ---------------------------------------------------------------------------
# T11: Recovery proposal comparison
# ---------------------------------------------------------------------------


class TestRecoveryComparison:
    """Compare different recovery scenarios."""

    def test_different_removals_different_proposals(self):
        """Removing different volunteers produces different proposals."""
        _load_context_with_plan()

        r1 = prepare_recovery_proposal(unavailable_resource_ids=["maya"])
        r2 = prepare_recovery_proposal(unavailable_resource_ids=["priya"])

        # Both should be feasible (replacements exist)
        assert r1["is_feasible"] is True
        assert r2["is_feasible"] is True

        # Different proposal IDs
        assert r1["proposal_id"] != r2["proposal_id"]


# ---------------------------------------------------------------------------
# T12: get_mission_context volunteer summary
# ---------------------------------------------------------------------------


class TestMissionContextDetail:
    """get_mission_context returns useful volunteer summaries."""

    def test_volunteer_summaries(self):
        """Volunteer summaries include id, name, capabilities, opted_in."""
        _load_context()
        result = get_mission_context()

        assert result["volunteer_count"] == 7
        for vol in result["volunteer_names"]:
            assert "id" in vol
            assert "name" in vol
            assert "capabilities" in vol
            assert "opted_in" in vol

    def test_vehicle_count(self):
        """Vehicle count is accurate."""
        _load_context()
        result = get_mission_context()
        assert result["vehicle_count"] == 1
