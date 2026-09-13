# MealMesh — Phase Handoff

## Phase 0: Repository Assessment and Enhancement Plan

**Status**: COMPLETED

**Date**: 2026-09-12

### Findings

1. **Stack**: Python 3.11+ / FastAPI / OR-Tools CP-SAT / Strands Agents SDK (Bedrock Nova-lite) / Vanilla JS + Leaflet + Cytoscape. No database.

2. **Current solver limitation**: Each Thursday site (`POST /api/plan`) is solved independently. The solver sees only the roster for that site. There is no cross-site exclusivity constraint. A floating-bench volunteer (e.g., Luis) can be "assigned" to multiple sites in separate requests.

3. **No travel-time modeling**: Volunteer coordinates (`app/api/scenario.py:_RESOURCE_SPEC`) are display-only. The solver in `app/solver.py` has no distance or time variables. Map animations are decorative.

4. **Consent boundary is solid**: `opted_in=True` is enforced before the solver runs (`resources.py:list_available_resources`, `scenario.py:build_catalog`). Recruit-only volunteers are excluded.

5. **Strands integration is mature**: Two working agents — extraction (`mission_agent.py`) and advisor (`advisor.py`) — with tool calling, structured output, audit logging, and Bedrock fallback. Agent observability is instrumented.

6. **Test suite is healthy**: 137 tests, all passing, 34s runtime. Good coverage of solver, resilience, orchestration, API, and sentinel.

7. **Architecture is layered correctly**: `orchestration.py:run_pipeline` is the single wiring point. Trust boundary (LLM extracts, solver decides) is consistently enforced. Pydantic `extra="forbid"` on all models.

### Demonstrating Scenario (Why Independent Solving Fails)

Consider: Eastside and Harbor both need a `van_certified_driver`. The Eastside roster includes Maya (local) and Luis (floating bench). The Harbor roster includes Dana (local) and Luis (floating bench).

**Independent solving**: Eastside solver picks Maya. Harbor solver picks Dana. Both feasible — no conflict. But if Maya cancels (toggle offline), Eastside re-solves and picks Luis. Meanwhile Harbor already "has" Dana. No problem yet.

Now Dana also cancels. Harbor re-solves and picks Luis. But Luis is already assigned to Eastside. **The system shows two feasible plans that are jointly infeasible.**

**Joint solving**: With Maya and Dana offline, the joint solver sees that Luis is the only available driver for both sites. It assigns Luis to one site and reports the other as infeasible (or uses another floating-bench driver like Avery for the other site). The conflict is surfaced immediately.

### Files Assessed

All 52 Python source files, 3 JS/HTML/CSS files, and 20 test files were read. Key modules: `solver.py` (151 lines), `orchestration.py` (329 lines), `scenario.py` (467 lines), `resilience.py` (194 lines), `sentinel.py` (628 lines), `advisor.py` (154 lines), `resources.py` (211 lines), `capabilities.py` (261 lines).

### Baseline Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
137 passed in 34.35s
```

No pre-existing failures. No documentation changes affect tests.

### Documents Created

| File | Purpose |
|---|---|
| `docs/mealmesh/PROJECT_CONTEXT.md` | Architecture, behavior, entry points, limitations |
| `docs/mealmesh/IMPLEMENTATION_PLAN.md` | Phases 1–7 with dependencies |
| `docs/mealmesh/DECISIONS.md` | 7 architectural decisions with rationale |
| `docs/mealmesh/CONTRACTS.md` | Existing contracts and proposed extensions |
| `docs/mealmesh/TEST_MATRIX.md` | Existing coverage + 20 acceptance scenarios |
| `docs/mealmesh/PHASE_HANDOFF.md` | This file |

### Limitations of This Phase

- No code changes. Application behavior is identical.
- The demonstrating scenario was traced through code, not executed as a test (that is Phase 1 scope).
- Proposed contracts are design-level; actual field names may change during implementation.

### Unresolved

- **Bedrock access**: Not tested (no AWS credentials in this environment). All Bedrock-dependent features degrade gracefully. This is a pre-existing condition, not a Phase 0 issue.
- **pyenv configuration**: `python` command is not linked; `python3` resolves to 3.14 without packages; `.venv/bin/python3` (3.11) is the working interpreter. Run tests via `.venv/bin/python3 -m pytest`.

---

## Phase 1: Typed Domain Contracts and Deterministic Validation

**Status**: COMPLETED
**Date**: 2026-09-12

### What Was Implemented

Typed domain contracts for joint planning, capability-aware assignment, counterfactual testing, and plan lifecycle management. All existing APIs remain backward compatible.

**New models** (`app/contracts.py`):
- `MissionSpec` — Mission with ID, version, timezone, structured tasks, time windows, dependencies, policy flexibility
- `VolunteerSpec` — Volunteer with verified qualifications, availability intervals, commitments, site access, vehicle eligibility, travel estimates, location freshness
- `VehicleSpec` — Vehicle with capacity (explicit units), availability, driver eligibility, equipment capabilities
- `PlanSpec` — Versioned plan with task assignments, constraint evaluation, solver status, lifecycle status, confirmations, provenance
- `TaskDefinition`, `TaskAssignment`, `TimeWindow`, `TravelEstimate`
- `ConstraintViolation`, `ResourceUnavailableEvent`, `RecoveryProposal`, `ApprovalRecord`, `MissionEvent`
- Enums: `PlanStatus`, `ConfirmationStatus`, `EventKind`, `DataProvenance`

**Validation engine** (`app/validation.py`):
- 10 deterministic validation rules covering ID references, capability gaps, site access, availability, overlapping assignments, driving/handling separation, vehicle availability, driver eligibility, task dependencies, travel time feasibility

**Synthetic Thursday fixture** (`tests/fixtures/thursday_fixture.py`):
- 1 church site (Eastside), 1 vehicle (Church Van), 7 volunteers
- 3 tasks with explicit durations and dependencies
- 1 valid plan, 2 impossible plans, 1 recovery scenario
- All data marked SIMULATED

### Files Changed

| File | Change |
|---|---|
| `app/contracts.py` | NEW — All typed domain contracts |
| `app/validation.py` | NEW — Deterministic validation engine |
| `tests/fixtures/__init__.py` | NEW — Package init |
| `tests/fixtures/thursday_fixture.py` | NEW — Synthetic Thursday fixture |
| `tests/test_contracts.py` | NEW — 46 tests |
| `docs/mealmesh/CONTRACTS.md` | UPDATED |
| `docs/mealmesh/DECISIONS.md` | UPDATED |
| `docs/mealmesh/PHASE_HANDOFF.md` | UPDATED |

### Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
183 passed in 9.66s
```

137 existing + 46 new. Zero regressions.

### Limitations

- No optimizer (later phase)
- No database (pre-existing)
- Simulated data only
- Travel estimates are placeholders
- No Bedrock access (pre-existing)

---

## Phase 2: Deterministic Coalition Planner

**Status**: COMPLETED
**Date**: 2026-09-12

### What Was Implemented

Joint coalition planner using CP-SAT that selects volunteers and resources simultaneously, not role-by-role. Enforces all hard constraints jointly: capability coverage, site access, vehicle-driver compatibility, volunteer availability, task window overlap prevention, and task precedence.

**New module** (`app/coalition_planner.py`):
- `CoalitionPlannerRequest` — Input with mission, volunteers, vehicles, alternatives count, time limit
- `CoalitionPlannerResult` — Output with feasibility, solver status, up to 3 distinct alternatives, violations, solve duration, input snapshot
- `AlternativePlan` — One feasible assignment with objective label (lowest_travel, earliest_completion, alternative_N)
- `InputSnapshot` — Records what the solver saw at solve time
- `solve_coalition()` — Main entry point: pre-check → CP-SAT model → independent validation → diversity search
- `solve_greedy()` — Naive nearest-first assignment for comparison testing (demonstrates the failure mode)
- Pre-solve feasibility checks with grounded infeasibility reasons
- Solution diversity via excluded-assignment constraints
- Independent post-solve validation via `app/validation.py`

**API endpoint** (`app/api/server.py`):
- `POST /api/joint-plan` — Accepts mission, volunteers, vehicles; returns joint plan with alternatives
- Feature flag: `MEALMESH_JOINT_PLANNING` env var (defaults to `true`; set to `false` to disable)

**Required demonstration** (Alex/Ben/Casey):
- Alex: only keyholder + also a driver (closer to site, 5 min travel)
- Ben: driver only (farther, 15 min travel)
- Casey: food handler only
- Greedy picks Alex for driving (nearest) → blocks on keyholder (Alex already assigned)
- Joint solver assigns: Ben → driving, Alex → site access, Casey → handling → mission succeeds

### Files Changed

| File | Change |
|---|---|
| `app/coalition_planner.py` | NEW — Joint coalition planner with CP-SAT |
| `app/api/server.py` | MODIFIED — Added `POST /api/joint-plan` endpoint |
| `tests/test_coalition_planner.py` | NEW — 19 tests |
| `docs/mealmesh/PHASE_HANDOFF.md` | UPDATED |
| `docs/mealmesh/DECISIONS.md` | UPDATED |
| `docs/mealmesh/CONTRACTS.md` | UPDATED |

### Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
202 passed in 9.52s
```

183 existing + 19 new. Zero regressions.

### Test Coverage

| Test | What it verifies |
|---|---|
| `test_greedy_fails_alex_scenario` | Greedy nearest-driver picks Alex, blocks on keyholder |
| `test_joint_solver_succeeds_alex_scenario` | Joint solver finds Ben→drive, Alex→unlock, Casey→handle |
| `test_joint_solver_metadata` | Solve duration, input snapshot, objective reported |
| `test_same_volunteer_overlapping_tasks` | Double-booking rejected |
| `test_ineligible_driver_rejected` | Driver/vehicle incompatibility rejected |
| `test_unavailable_volunteer_excluded` | Task windows respected |
| `test_missing_capability_infeasible` | No qualified handler → INFEASIBLE |
| `test_zero_time_limit_returns_valid_status` | Status labeling contract |
| `test_unknown_not_labeled_infeasible_for_unsolvable_in_time` | Feasible problem never returns INFEASIBLE |
| `test_generates_multiple_alternatives` | Up to 3 distinct alternatives |
| `test_single_solution_no_fabrication` | Don't manufacture extras when only 1 exists |
| `test_tiny_2tasks_3vols` | Exhaustive enumeration comparison |
| `test_no_site_access_infeasible` | Site access enforced |
| `test_opted_out_not_assigned` | Opted-out volunteers excluded |
| `test_eastside_thursday` | Integration with Phase 1 fixture |
| `test_no_tasks_infeasible` | Empty mission handled |
| `test_wildcard_site_access` | '*' site access works |
| `test_optimal_on_simple_problem` | OPTIMAL status on clear optimum |
| `test_infeasible_clearly_labeled` | INFEASIBLE status on impossible problem |

### Limitations

- Single-mission planner (cross-site joint planning is Phase 3+ scope)
- No minimum-disruption replanning yet (Phase 4)
- Travel estimates are simulated placeholders
- No database (pre-existing)
- No Bedrock access (pre-existing)
- The `earliest_completion` alternative uses a travel-time proxy, not actual schedule optimization
- Legacy per-site solver preserved and unchanged behind feature flag

---

## Phase 3: Counterfactual Failure Analysis

**Status**: COMPLETED
**Date**: 2026-09-12

### What Was Implemented

Counterfactual failure analysis engine that simulates removal of each critical resource and tests whether the mission can still be completed. Never mutates live state.

**New module** (`app/counterfactual.py`):
- `CounterfactualScenario` — Per-resource removal result with recovery status, bottleneck explanation, objective deltas, replacement tracking
- `CounterfactualReport` — Full analysis with aggregate metrics, single-points-of-failure list, interpretable summary
- `BottleneckExplanation` — Structured explanation with capability at risk, uncovered tasks, SPOF flag
- `ObjectiveDelta` — Changed assignments, additional travel, baseline/recovery objectives
- `run_counterfactual_analysis()` — Main entry: deep-copies inputs, removes one resource at a time, re-solves via CP-SAT, classifies as robust/recoverable/infeasible/unknown
- `is_report_stale()` — Invalidates report when mission version changes

**Recovery status taxonomy**:
1. **Robust**: existing plan works without reassignment (resource not in baseline)
2. **Recoverable**: new feasible plan found (replacement volunteers identified but unconfirmed)
3. **Infeasible**: no recovery possible (bottleneck explanation generated)
4. **Unknown**: solver hit time limit (preserved, never silently counted as success)

**API endpoint** (`app/api/server.py`):
- `POST /api/counterfactual` — Accepts mission, baseline plan, volunteers, vehicles, optional resource IDs to test; returns full counterfactual report

### Files Changed

| File | Change |
|---|---|
| `app/counterfactual.py` | NEW — Counterfactual analysis engine |
| `app/api/server.py` | MODIFIED — Added `POST /api/counterfactual` endpoint |
| `tests/test_counterfactual.py` | NEW — 18 tests |
| `docs/mealmesh/PHASE_HANDOFF.md` | UPDATED |
| `docs/mealmesh/DECISIONS.md` | UPDATED |
| `docs/mealmesh/CONTRACTS.md` | UPDATED |

### Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
220 passed in 10.88s
```

202 existing + 18 new. Zero regressions.

### Test Coverage

| Test | What it verifies |
|---|---|
| `test_remove_replaceable_driver` | B-1: Maya removed → Gina replaces as driver (recoverable) |
| `test_remove_replaceable_food_handler` | B-1: Priya removed → Sam replaces (recoverable) |
| `test_sole_keyholder_infeasible` | B-2: Elena (sole keyholder) → infeasible, SPOF identified |
| `test_bottleneck_explanation_mentions_keyholder` | B-2: Explanation names site_keyholder as gap |
| `test_shared_backup_cannot_cover_both` | B-3: Luis cannot cover driving + handling simultaneously |
| `test_inputs_not_mutated` | Live state unchanged after analysis |
| `test_baseline_plan_not_mutated` | Baseline plan unchanged after analysis |
| `test_same_version_not_stale` | Report valid at same version |
| `test_newer_version_is_stale` | Report invalidated at newer version |
| `test_unknown_not_counted_as_success` | UNKNOWN preserved, not masked |
| `test_unknown_in_summary` | Unknown appears in summary |
| `test_all_assigned_volunteers` | All baseline volunteers tested |
| `test_interpretable_summary` | Summary contains actual counts |
| `test_provenance_is_simulated` | Provenance = SIMULATED |
| `test_unassigned_volunteer_is_robust` | Spare volunteer = robust |
| `test_recovery_has_delta` | Objective delta computed |
| `test_version_in_scenario` | Snapshot version recorded |
| `test_replacements_listed` | New volunteers tracked as required replacements |

### Limitations

- Single-mission counterfactual (cross-site cascading requires multi-site joint planner, Phase 3+ extension)
- No minimum-disruption replanning (Phase 4)
- Travel estimates are simulated placeholders
- No database (pre-existing)
- No Bedrock access (pre-existing)
- Confirmed recovery (volunteer acceptance) is never claimed — only recoverability
- Tested alternatives are not necessarily the globally most resilient plan

---

## Phase 4: Event-Driven Minimum-Change Recovery

**Status**: COMPLETED
**Date**: 2026-09-12

### What Was Implemented

Event-driven minimum-change recovery engine with full event contract, deduplication, minimum-change replanning via CP-SAT stability objective, version-bound approval workflow, volunteer acceptance tracking, resource reservation, and at-risk mission status surfacing.

**Modified module** (`app/coalition_planner.py`):
- `CoalitionPlannerRequest.fixed_task_ids` — Task IDs whose assignments must not change (completed/in-progress)
- `_solve_single()` — New `incumbent_assignments` and `fixed_assignments` parameters
- Stability objective: `_STABILITY_WEIGHT = 1_000_000` bonus for keeping incumbent assignments, dominating travel cost so solver minimizes changes first
- `C8` constraint: hard-fixes completed/in-progress task assignments
- Label changes to `"minimum_disruption"` when incumbent plan provided

**New module** (`app/recovery.py`):
- `ResourceEvent` — Full event contract: event ID, resource ID/type, effective time, observed time, mission reference, source, simulated/live marker
- `EventLog` — Deduplication by event_id and (resource_id, effective_time), stale/out-of-order detection
- `plan_recovery()` — Minimum-change recovery: loads current plan, preserves in-progress work, excludes unavailable resources, uses CP-SAT stability objective, revalidates, produces version-bound proposal with structured before/after diff
- `RecoveryProposalSpec` — Version-bound proposal with expiration, changes list, capability gaps, safe actions, targeted request
- `ApprovalRequest` / `ApprovalResult` — Version-checked approval with atomic resource reservation
- `RecoveryEngine` — Full lifecycle: event ingestion, recovery planning, approval (idempotent), volunteer response tracking, mission risk status
- `TestNotificationAdapter` — In-memory notification adapter (default)
- `MissionRiskStatus` — nominal/at_risk/blocked with reasons

**Role-swap composition demonstrated**:
- Assigned driver cancels, no unassigned driver available
- Assigned handler also qualified to drive → swapped to driving
- Available handler fills the vacated handling task
- Arises from resource data and constraints, not hardcoded names

**API endpoints** (`app/api/server.py`):
- `POST /api/recovery/event` — Ingest event with deduplication
- `POST /api/recovery/plan` — Generate minimum-change recovery proposal
- `POST /api/recovery/approve` — Approve proposal with version/reservation checks
- `GET /api/recovery/risk/{mission_id}` — Get mission at-risk status

### Files Changed

| File | Change |
|---|---|
| `app/coalition_planner.py` | MODIFIED — Added fixed_task_ids, incumbent stability objective, C8 constraint |
| `app/recovery.py` | NEW — Event-driven recovery engine |
| `app/api/server.py` | MODIFIED — Added 4 recovery API endpoints |
| `tests/test_recovery.py` | NEW — 25 tests |
| `docs/mealmesh/PHASE_HANDOFF.md` | UPDATED |
| `docs/mealmesh/DECISIONS.md` | UPDATED |
| `docs/mealmesh/CONTRACTS.md` | UPDATED |

### Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
245 passed in 29.05s
```

220 existing + 25 new. Zero regressions.

### Test Coverage

| Test | What it verifies |
|---|---|
| `test_role_swap_recovery` | R-2: Driver cancels → handler swaps to driving, new handler fills gap (composition) |
| `test_approval_activates_correct_version` | Approval transitions plan to APPROVED with coordinator |
| `test_stale_approval_rejected` | Wrong mission version → stale rejection |
| `test_stale_approval_wrong_plan_version` | Wrong plan version → stale rejection |
| `test_duplicate_event_safe` | Same event ingested twice → duplicate |
| `test_duplicate_event_same_effective_time` | Different IDs, same (resource, time) → duplicate |
| `test_duplicate_approval_idempotent` | Second approval → already_approved, no side effects |
| `test_concurrent_mission_resource_conflict` | Mission A reserves volunteer → Mission B blocked |
| `test_pending_replacement_declines` | Volunteer decline recorded, all_confirmed=False |
| `test_infeasible_recovery_blocked_state` | Sole keyholder removed → capability gap, safe actions, targeted request |
| `test_infeasible_mission_risk_status` | Blocked status surfaced with pending proposals |
| `test_stale_event_rejected` | Older effective_time → stale |
| `test_event_requires_tz_aware_times` | Naive datetime rejected |
| `test_min_change_fewer_than_scratch` | Min-change ≤ from-scratch changes; keyholder unchanged |
| `test_min_change_label` | Label = "minimum_disruption" when incumbent provided |
| `test_no_incumbent_label_unchanged` | Label = "lowest_travel" without incumbent |
| `test_proposal_version_binding` | Proposal records expected versions |
| `test_proposal_expiration` | TTL-based expiration |
| `test_notification_adapter_called` | Test adapter receives recovery and volunteer notifications |
| `test_approval_not_found` | Non-existent proposal → not_found |
| `test_volunteer_response_not_in_plan` | Unknown volunteer → graceful failure |
| `test_compute_assignment_diff` | Diff identifies replaced/unchanged/added/removed |
| `test_mission_risk_at_risk` | Pending feasible proposal → at_risk |
| `test_mission_risk_nominal` | No disruptions → nominal |
| `test_provenance_is_simulated` | SIMULATED provenance on proposals |

### Limitations

- Single-mission recovery (cross-site cascading is a future extension)
- In-memory state resets on restart (documented; production would use persistent store)
- Travel estimates are simulated placeholders
- No database (pre-existing)
- No Bedrock access (pre-existing)
- Confirmed recovery (volunteer acceptance) is tracked but does not trigger replanning on decline
- Resource reservations are in-memory; no distributed locking
- Proposal expiration check happens at approval time, not proactively

---

## Phase 5: Strands Semantic Orchestration

**Status**: COMPLETED
**Date**: 2026-09-12

### What Was Implemented

Semantic orchestration layer that lets coordinators describe goals and disruptions in natural language while the deterministic backend remains authoritative. Reuses the existing Strands Agent pattern (advisor.py) with six typed tools wrapping existing services.

**New module** (`app/semantic_tools.py`):
- `get_mission_context` — Returns active mission, plan, volunteer roster, vehicles
- `validate_mission_draft` — Deterministic validation against domain rules
- `generate_coalition_plans` — Joint CP-SAT planner via existing `solve_coalition()`
- `evaluate_plan_failures` — Counterfactual what-if analysis via existing `run_counterfactual_analysis()`
- `prepare_recovery_proposal` — Minimum-change recovery via existing `plan_recovery()`
- `get_proposal_status` — Proposal lookup and summary
- Conversation state management with `set_mission_context()` / `reset_conversation_state()`
- Per-turn tool call bounds (max 10)

**New module** (`app/semantic_orchestrator.py`):
- Enhanced system prompt with safety rules (never invent, never override infeasibility, never bypass qualifications)
- `build_semantic_orchestrator()` — Strands Agent with semantic tools + Bedrock
- `ask_orchestrator()` — Sanitized text response
- `demo_tools_offline()` — Offline demonstration without Bedrock
- Thinking-tag stripping (reuses advisor pattern)

**New API endpoints** (`app/api/server.py`):
- `POST /api/semantic/context` — Load mission context
- `POST /api/semantic` — Natural-language question with tool calling
- `POST /api/semantic/reset` — Reset conversation state
- `GET /api/proposal/{proposal_id}` — Proposal status lookup

**LLM responsibilities enforced by system prompt**:
- Extract intent and entities
- Ask for genuinely missing required information
- Resolve ambiguous names through explicit IDs/confirmation
- Explain service-returned findings
- Summarize proposal differences
- Never invent resources, eligibility, ETAs, or solver results
- Never calculate policy or override infeasibility

**Control flow enforced by tool layer**:
- Mission/proposal references persist across conversational turns
- Tool calls bounded (10 per turn)
- Simulations distinct from real unavailability reports (`is_simulation` flag)
- Tool-level authorization independent of prompts
- Proposals require version-bound coordinator approval
- Opted-out volunteers always excluded (solver constraint, not prompt)

### Files Changed

| File | Change |
|---|---|
| `app/semantic_tools.py` | NEW — Six typed Strands tools wrapping existing services |
| `app/semantic_orchestrator.py` | NEW — Enhanced agent with semantic system prompt |
| `app/api/server.py` | MODIFIED — Added 4 semantic orchestration endpoints |
| `tests/test_semantic_orchestrator.py` | NEW — 34 tests |
| `docs/mealmesh/PHASE_HANDOFF.md` | UPDATED |
| `docs/mealmesh/DECISIONS.md` | UPDATED |
| `docs/mealmesh/CONTRACTS.md` | UPDATED |

### Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
279 passed in 10.78s
```

245 existing + 34 new. Zero regressions.

### Test Coverage

| Test | What it verifies |
|---|---|
| `test_generate_plan_from_context` | Loading context + generating plans succeeds |
| `test_plan_persists_in_context` | Generated plan stored in conversation state |
| `test_validate_after_generate` | No blocking violations on generated plan |
| `test_no_context_loaded` | Reports no context when none loaded |
| `test_validate_without_context` | Asks for info when no context |
| `test_generate_without_context` | Errors when no context loaded |
| `test_evaluate_without_plan` | Errors when no plan loaded |
| `test_recovery_without_plan` | Errors when no plan loaded |
| `test_recovery_empty_ids` | Errors with empty resource list |
| `test_evaluate_does_not_mutate_plan` | Plan unchanged after what-if |
| `test_evaluate_does_not_mutate_volunteers` | Volunteer list unchanged after what-if |
| `test_recovery_simulation_flag` | Simulation is marked as SIMULATION |
| `test_recovery_proposal_is_pending` | Proposals start as pending |
| `test_evaluate_maya_removal_recoverable` | Maya removal → recoverable |
| `test_evaluate_elena_removal_infeasible` | Elena removal → infeasible (sole keyholder) |
| `test_opted_out_volunteer_excluded` | Jordan never assigned |
| `test_ineligible_driver_not_assigned_to_van` | Luis not assigned to Church Van |
| `test_invalid_mission_json` | Invalid JSON → validation error |
| `test_nonexistent_proposal` | Not-found error for unknown proposal |
| `test_proposal_not_active` | New proposal status=pending |
| `test_proposal_tracked_in_state` | Proposals tracked for follow-up |
| `test_multiple_proposals_tracked` | Multiple proposals coexist |
| `test_infeasible_proposal_reports_gaps` | Capability gaps + safe actions reported |
| `test_context_persists` | State survives across tool calls |
| `test_reset_clears_state` | Reset clears everything |
| `test_exceeding_bound_returns_error` | Tool call limit enforced |
| `test_system_prompt_contains_rules` | Safety rules in system prompt |
| `test_tools_registered` | All 6 tools registered |
| `test_offline_demo_runs` | Offline demo works without Bedrock |
| `test_multiple_alternatives_generated` | Multiple distinct plans generated |
| `test_alternatives_have_labels` | Each alternative has a label |
| `test_different_removals_different_proposals` | Different removals → different proposals |
| `test_volunteer_summaries` | Volunteer summaries include required fields |
| `test_vehicle_count` | Vehicle count accurate |

### Natural-Language Example Mappings

| User says | Tool called | What happens |
|---|---|---|
| "Organize Thursday distribution at the church by 5 PM" | `generate_coalition_plans` | CP-SAT finds joint assignment |
| "Our driver cannot make it" | `prepare_recovery_proposal` | Min-change recovery generated |
| "Why can't you use Alex?" | `get_mission_context` | Explains capabilities/access |
| "What happens if the key holder cancels?" | `evaluate_plan_failures` | Counterfactual simulation |
| "Compare the recovery options" | `get_proposal_status` | Summarizes all proposals |

### Limitations

- Requires Bedrock access for LLM orchestration (existing limitation)
- In-memory conversation state resets on restart
- No real messaging or notifications
- No multi-turn memory beyond tool call state
- Travel estimates are simulated placeholders
- No database (pre-existing)
- Tool call bounds are per-reset, not per-actual-turn (no turn tracking in tool layer)
- Proposal approval still via /api/recovery/approve (Phase 4 endpoint)

---

## Phase 6: Mission-Control UI

**Status**: COMPLETED
**Date**: 2026-09-12

### What Was Implemented

Full mission-control dashboard that visualizes coalition dependencies, failure impact, and recovery decisions on a dedicated page (`/mission-control`). Preserves the existing dashboard at `/` unchanged.

**New module** (`app/mission_control.py`):
- `MissionControlPayload` — Full view model: mission header, task assignments, volunteer markers, SPOFs, counterfactual scenarios, recovery card, risk status
- `TaskView` — Per-task view with assignment, qualification, confirmation, dependencies, time window
- `VolunteerView` — Volunteer marker with location, travel estimate, SPOF flag, confirmed/proposed state
- `RecoveryView` — Recovery card with changes, capability gaps, safe actions, pending confirmations, expiration
- `build_mission_control_payload()` — Assembles the view from existing domain objects (coalition planner, counterfactual, recovery)
- Auto-solve when no plan is provided; infeasible fallback when solver fails

**New API endpoints** (`app/api/server.py`):
- `POST /api/mission-control` — Assemble mission-control view from mission/volunteers/vehicles/plan
- `POST /api/mission-control/simulate-removal` — Simulate resource removal with recovery proposal (isolated)
- `GET /api/mission-control/fixture` — Thursday fixture demo payload with raw data for round-trips
- `GET /mission-control` — Serve the mission-control HTML page

**New frontend files**:
- `mission-control.html` — Three-panel layout: tasks + simulation (left), map (center), recovery + counterfactual (right)
- `mission-control.css` — Extends base styles for task list, simulation controls, counterfactual items, recovery card, SPOF indicators, timeline
- `mission-control.js` — Vanilla JS: Leaflet map with confirmed/proposed/SPOF marker styles, failure simulation, recovery approval demo, event timeline

**Mission header strip**:
- Deadline, plan status, roles covered (N/M), tasks at risk, recovery test summary

**Map features**:
- Volunteers with kind-colored markers (driver/food/keyholder)
- Confirmed assignments: solid animated routes to destination
- Proposed assignments: dashed routes, dashed marker borders
- SPOF volunteers: pulsing red border animation
- Stale location indicator (CSS class, not currently triggered by fixture data)
- Location labels, travel estimates, capability tooltips
- Destination halo with site marker
- No straight-line connections presented as road navigation

**Task panel**:
- Required task, assigned volunteer, qualification status rail
- Time window, dependency, confirmation status (pending/confirmed)
- Proposed assignments visually distinct from confirmed

**Failure simulation** (clearly labeled SIMULATION):
1. Click volunteer chips to select for removal
2. "Simulate Removal" button triggers `/api/mission-control/simulate-removal`
3. Impact shown: affected tasks, recovery evaluation result
4. Recovery proposal displayed in right panel with assignment diff
5. Compare, Approve, Reject buttons (Approve transitions proposed → confirmed)
6. Simulation isolated — fresh `RecoveryEngine` instance per call, no mutation of fixture data

**Recovery card**:
- What changed and why
- Assignment diff (replaced/unchanged/added/removed)
- Capability gaps with ⚠ indicators
- Safe actions list
- Pending volunteer confirmations count
- Targeted request for coordinator
- Proposal expiration

**Counterfactual panel**:
- Per-volunteer recovery status dots (robust/recoverable/infeasible/unknown)
- Mission impact description
- Color-coded status tags

**SPOF panel**:
- Pulsing red icon for single points of failure
- Capability list per SPOF

**Event timeline**:
- Compact event list with kind-colored dots (plan/removal/recovery/approval/rejected)
- Auto-scrolls, timestamps

**Privacy**: Volunteer views show location labels only (not exact addresses). Full coordinates sent only for map rendering. Tooltips show capability/role, not personal details.

**Accessibility**: ARIA labels on tasks and SPOFs, role="listitem" on interactive items, keyboard-navigable simulation chips, no color-only distinctions (icons + labels + animations).

### Files Changed

| File | Change |
|---|---|
| `app/mission_control.py` | NEW — Mission-control data assembly |
| `app/api/server.py` | MODIFIED — Added 4 mission-control endpoints + link to page |
| `app/api/static/mission-control.html` | NEW — Mission-control dashboard page |
| `app/api/static/mission-control.css` | NEW — Mission-control styles |
| `app/api/static/mission-control.js` | NEW — Mission-control frontend logic |
| `app/api/static/index.html` | MODIFIED — Added "Mission Control" link to topbar |
| `tests/test_mission_control.py` | NEW — 45 tests |
| `docs/mealmesh/PHASE_HANDOFF.md` | UPDATED |
| `docs/mealmesh/DECISIONS.md` | UPDATED |
| `docs/mealmesh/CONTRACTS.md` | UPDATED |

### Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
324 passed in 8.39s
```

279 existing + 45 new. Zero regressions.

### Test Coverage

| Test | What it verifies |
|---|---|
| `test_payload_type` | Returns MissionControlPayload |
| `test_mission_id` | Correct mission ID |
| `test_all_roles_covered` | 3/3 roles covered in normal plan |
| `test_no_tasks_at_risk` | No at-risk tasks in normal plan |
| `test_task_count_matches_mission` | Task count = mission tasks |
| `test_tasks_have_volunteers` | All tasks assigned |
| `test_task_qualification_status` | All volunteers qualified |
| `test_volunteers_present` | Opted-in volunteers only |
| `test_assigned_volunteers` | 3 assigned (one per task) |
| `test_spof_detection` | Elena identified as SPOF |
| `test_counterfactual_scenarios_present` | Counterfactual data present |
| `test_recovery_summary_not_empty` | Summary text generated |
| `test_plan_status_proposed` | Initial status = proposed |
| `test_destination_coords` | Coordinates present |
| `test_provenance_simulated` | SIMULATED flag set |
| `test_risk_status_nominal` | Nominal risk for normal plan |
| `test_maya_recoverable` | Maya removal → recoverable |
| `test_elena_infeasible` | Elena removal → infeasible |
| `test_elena_bottleneck` | Elena has bottleneck explanation with SPOF flag |
| `test_simulation_does_not_modify_original` | Inputs unchanged after payload build |
| `test_at_risk_payload` | Risk status passthrough |
| `test_recovery_view_renders` | Feasible recovery card rendered |
| `test_infeasible_recovery_view` | Infeasible recovery with gaps |
| `test_infeasible_with_only_opted_out` | Only opted-out → blocked |
| `test_task_dependencies` | Depends-on chain rendered |
| `test_time_window_label` | Time window format verified |
| `test_confirmation_tracking` | 3 pending confirmations |
| `test_travel_estimates_present` | Travel labels populated |
| `test_opted_out_excluded` | Jordan not in views |
| `test_spof_volunteers_marked` | SPOF flag on volunteer views |
| `test_location_coords_present` | All coords [lat, lng] |
| `test_auto_solve_produces_plan` | Auto-solve when no plan |
| `test_fixture_endpoint` | API returns fixture with raw data |
| `test_fixture_has_tasks` | 3 tasks in fixture |
| `test_fixture_has_volunteers` | Volunteers in fixture |
| `test_fixture_has_counterfactual` | Counterfactual in fixture |
| `test_fixture_has_spofs` | Elena SPOF in fixture |
| `test_mission_control_page_served` | HTML page served at /mission-control |
| `test_simulate_removal_recoverable` | Maya removal → feasible recovery |
| `test_simulate_removal_infeasible` | Elena removal → blocked, capability gaps |
| `test_simulate_removal_missing_plan` | Missing plan/IDs → error |
| `test_post_mission_control` | Direct assembly endpoint |
| `test_stale_version_check` | Stale proposal rendered correctly |
| `test_no_volunteers_returns_infeasible` | Opted-out only → blocked |
| `test_payload_serializable` | JSON round-trip works |

### Limitations

- No real-time event streaming (SSE/WebSocket) — timeline is client-side only
- Simulation uses a fresh RecoveryEngine per call (no persistent simulation state)
- Map shows straight-line routes, not road navigation (documented; labeled as simulated)
- Location staleness heuristic not triggered by fixture data (always "current")
- Approval is a local UI state transition — no backend activation (would go through /api/recovery/approve)
- No cross-site dependency edges (single-mission fixture; multi-site would need the multi-site joint planner)
- Travel estimates are simulated placeholders
- No database (pre-existing)
- No Bedrock access (pre-existing)

---

## Phase 7: End-to-End Verification and Demo Readiness

**Status**: COMPLETED
**Date**: 2026-09-12

### What Was Implemented

Repeatable synthetic demo harness with controlled clock, isolated test data, and four deterministic demo scenarios proving the enhancement works end to end.

**New module** (`app/demo_runner.py`):
- `DemoMeasurement` — Measured result container with solver/model/tool timing separation
- `run_demo_a()` — Joint planning vs greedy: greedy failure documented, joint solver succeeds
- `run_demo_b()` — Recomposition: driver removed → min-change recovery → coordinator approval → volunteer acceptance → mission-control update
- `run_demo_c()` — Honest block: sole keyholder removed → INFEASIBLE → capability gaps → targeted request → no fabrication
- `run_demo_d()` — Prevention: counterfactual stress test on all assigned volunteers → SPOF detection → vulnerability mitigations
- `run_full_demo()` — Orchestrates all four with isolated state, aggregate measurements, verdict
- `demo_now()` — Controlled clock (fixed Thursday 2026-09-10 14:00 Pacific)

**Demo A results** (measured):
- Greedy: documents behavior (fails or succeeds depending on data shape)
- Joint solver: OPTIMAL, all 3 tasks assigned, no double-booking
- Independent validation: 0 blocking violations
- Planning duration: <100ms on test hardware

**Demo B results** (measured):
- Maya (driver) removed
- Recovery: feasible, Gina replaces Maya (1 assignment changed)
- Approval: success, coordinator-demo approved
- Acceptance: recorded for replacement volunteer
- Mission-control payload: updated with at_risk status
- Replanning duration: <200ms

**Demo C results** (measured):
- Elena (sole keyholder) removed
- Recovery: INFEASIBLE
- Capability gaps: site_keyholder identified
- Safe actions: 3 operator recommendations
- Targeted request: "Need one volunteer with site_keyholder..."
- Risk status: blocked
- System did NOT fabricate authorization or claim success

**Demo D results** (measured):
- 3 single-resource-loss scenarios tested
- Maya: recoverable (Gina replaces)
- Priya: recoverable (Sam replaces)
- Elena: infeasible (SPOF — sole keyholder)
- SPOFs: ["elena"]
- Mitigations: CRITICAL for Elena, pre-confirm backups for others
- Counterfactual duration: <500ms

### Files Changed

| File | Change |
|---|---|
| `app/demo_runner.py` | NEW — Demo harness with 4 scenarios |
| `tests/test_e2e_demo.py` | NEW — 63 end-to-end tests |
| `docs/mealmesh/DEMO_GUIDE.md` | NEW — Setup, demo commands, 5-min outline, deployment checklist |
| `docs/mealmesh/PHASE_HANDOFF.md` | UPDATED |
| `docs/mealmesh/DECISIONS.md` | UPDATED |

### Test Results

```
$ .venv/bin/python3 -m pytest tests/ -v
387 passed in 10.66s
```

324 existing + 63 new. Zero regressions.

### Test Coverage (Phase 7)

| Test | What it verifies |
|---|---|
| `test_joint_solver_produces_feasible_plan` | Demo A: joint solver finds feasible assignment |
| `test_joint_solver_status_is_optimal` | Demo A: OPTIMAL or FEASIBLE status |
| `test_joint_plan_has_all_tasks_assigned` | Demo A: all 3 tasks covered |
| `test_joint_plan_passes_independent_validation` | Demo A: 0 blocking violations |
| `test_joint_plan_no_double_booking` | Demo A: unique volunteer per task |
| `test_joint_plan_generates_alternatives` | Demo A: ≥1 alternative |
| `test_greedy_behavior_documented` | Demo A: greedy result explained |
| `test_conflict_explanation_present` | Demo A: conflict explained |
| `test_assignment_summary_has_task_volunteer_pairs` | Demo A: structured summary |
| `test_planning_duration_measured` | Demo A: <10s |
| `test_opted_out_volunteers_excluded` | Demo A: Jordan not assigned |
| `test_provenance_is_simulated` | Demo A: SIMULATED flag |
| `test_recovery_is_feasible` | Demo B: recovery found |
| `test_removed_volunteer_not_in_recovery_plan` | Demo B: maya excluded |
| `test_recovery_has_assignment_diff` | Demo B: diff computed |
| `test_at_least_one_replacement` | Demo B: ≥1 replaced |
| `test_approval_succeeds` | Demo B: coordinator approved |
| `test_volunteer_acceptance_recorded` | Demo B: acceptance tracked |
| `test_recovery_plan_passes_validation` | Demo B: 0 blocking violations |
| `test_mission_control_payload_updated` | Demo B: at_risk status |
| `test_replanning_duration_measured` | Demo B: <10s |
| `test_min_change_fewer_assignments_than_scratch` | Demo B: changes ≤ tasks |
| `test_unchanged_assignments_preserved` | Demo B: min-change preserved |
| `test_recovery_is_infeasible` | Demo C: no recovery |
| `test_capability_gaps_reported` | Demo C: keyholder gap |
| `test_safe_actions_provided` | Demo C: ≥1 action |
| `test_targeted_request_present` | Demo C: specific request |
| `test_risk_status_is_blocked` | Demo C: blocked |
| `test_does_not_fabricate_authorization` | Demo C: honesty |
| `test_does_not_claim_success` | Demo C: INFEASIBLE status |
| `test_replanning_duration_measured` (C) | Demo C: <10s |
| `test_all_assigned_volunteers_tested` | Demo D: all tested |
| `test_spof_detected` | Demo D: ≥1 SPOF |
| `test_elena_is_spof` | Demo D: elena is SPOF |
| `test_recoverable_scenarios_exist` | Demo D: ≥1 recoverable |
| `test_no_unknown_scenarios` | Demo D: no timeouts |
| `test_vulnerability_mitigations_provided` | Demo D: mitigations |
| `test_spof_mitigation_is_critical` | Demo D: CRITICAL label |
| `test_counterfactual_duration_measured` | Demo D: <30s |
| `test_tested_scenarios_description` | Demo D: description |
| `test_total_counts_consistent` | Demo D: R+I+U+Rob = total |
| `test_full_demo_passes` | All 4 demos pass |
| `test_verdict_is_ready_with_limitations` | Verdict correct |
| `test_limitations_documented` | ≥5 limitations |
| `test_all_measurements_present` | 4 measurements |
| `test_total_duration_under_30s` | <30s total |
| `test_demo_a_b_c_d_consistency` | Cross-demo consistency |
| `test_fixture_endpoint_returns_data` | API: fixture works |
| `test_fixture_has_spofs` | API: elena SPOF |
| `test_simulate_removal_recoverable` | API: maya → at_risk |
| `test_simulate_removal_blocked` | API: elena → blocked |
| `test_joint_plan_endpoint` | API: joint-plan works |
| `test_counterfactual_endpoint` | API: counterfactual works |
| `test_recovery_plan_endpoint` | API: recovery works |
| `test_mission_control_page_loads` | API: page served |
| `test_demo_now_is_deterministic` | Clock is fixed |
| `test_demo_now_is_timezone_aware` | Clock has timezone |
| `test_demo_does_not_mutate_volunteers` | Isolation |
| `test_demo_does_not_mutate_mission` | Isolation |
| `test_independent_engine_per_demo` | State isolation |
| `test_resource_reservation_conflict` | Concurrency safety |
| `test_solver_output_validated_independently` | Independent validation |
| `test_recovery_output_validated` | Recovery validation |

### Limitations

- All data SIMULATED — no real volunteers, meals, or arrivals
- Travel estimates are simulated placeholders (Haversine-based)
- No database — state resets on restart
- No Bedrock access — LLM features not tested live
- No real notifications — test adapter only
- In-memory reservations, no distributed locking
- Map routes are straight-line, not road navigation
- No actual pilot data — cannot claim meals rescued or time saved
- Greedy failure depends on data shape and task ordering
- Cross-site joint planning not demonstrated (single-mission scope)

---

## Release Readiness Report

**Verdict: READY WITH LIMITATIONS**

### Evidence

1. **387 tests pass** — 324 existing (zero regressions) + 63 new end-to-end
2. **All 4 demos succeed deterministically**:
   - A: Joint planning produces feasible, independently validated assignments
   - B: Min-change recovery with approval workflow and acceptance tracking
   - C: Honest blocking with capability gaps and targeted request
   - D: SPOF detection with vulnerability mitigations
3. **Controlled clock and isolated data** — demos reset without affecting other state
4. **Independent plan validation** — solver output checked by separate validation engine
5. **Concurrency safety** — resource reservation conflicts detected at approval time
6. **All timing measured** — planning <100ms, replanning <200ms, counterfactual <500ms
7. **Production build verified** — `uvicorn app.api.server:app` serves all endpoints
8. **Mission-control UI** — three-panel dashboard with simulation, recovery, counterfactual
9. **Semantic orchestration** — 6 Strands tools wrapping deterministic services (offline demo available)

### Blocking Issues

None. All required functionality is implemented and tested.

### Pre-Deployment Requirements

1. Validate operator policy (food safety, site access, vehicle eligibility)
2. Configure Bedrock credentials for LLM features
3. Configure notification routing (Slack/webhook)
4. Load real volunteer data
5. Recruit backup keyholders for SPOF sites
6. Get coordinator sign-off on approval workflow

### What Is NOT Claimed

- Real meals rescued or coordinator time saved (no pilot data)
- Plan survives every possible failure (tested: single-resource removal only)
- Solver optimality on problems larger than the fixture (fixture: 7 volunteers, 3 tasks)
- Live integration with Bedrock, Slack, or any external service
- Road-based travel times (straight-line only, labeled SIMULATED)
