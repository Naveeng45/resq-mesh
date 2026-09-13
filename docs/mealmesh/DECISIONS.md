# MealMesh — Architectural Decisions

## D-001: Joint solver extends existing CP-SAT, not a new engine

**Decision**: Extend `app/solver.py` with multi-site constraints in the same CP-SAT model rather than introducing a new optimization library, graph database, or external solver.

**Rationale**: OR-Tools CP-SAT is already installed, tested, and understood. The joint problem is still a small binary program (≤23 resources × 3 sites = 69 variables). CP-SAT handles this trivially. Adding cross-site exclusivity is one `model.Add()` per resource.

**Alternatives rejected**:
- **Separate solver per site + post-hoc deconfliction**: Fragile; deconfliction can make both sites infeasible when joint solving would find a solution.
- **Graph database (Neo4j)**: Over-engineering for 23 resources and 3 sites. Adds a dependency, deployment complexity, and a new data layer. The hypergraph module already handles structural representation.
- **MIP solver (Gurobi/CPLEX)**: Commercial license. CP-SAT is sufficient for this problem size.

**Status**: Proposed (Phase 0).

---

## D-002: Feature flag, not branch, for joint planning

**Decision**: Use an environment variable (`MEALMESH_JOINT_PLANNING`) to enable the joint solver. Existing per-site behavior remains the default.

**Rationale**: The hackathon demo must work at any commit. A feature flag lets us merge incrementally without breaking the existing dashboard or test suite. The flag is checked in the API layer; the solver module supports both modes unconditionally.

**Alternatives rejected**:
- **Feature branch merge at the end**: Risk of large merge conflicts. Harder to test incrementally.
- **API versioning (`/v2/plan`)**: Adds permanent API surface. The flag is transient — once joint planning is validated, it becomes the default.

**Status**: Proposed (Phase 0).

---

## D-003: Simulated travel time, not live routing

**Decision**: Use Haversine distance × a configurable speed factor for travel-time estimates. Label all times as "SIMULATED."

**Rationale**: The coordinates are synthetic (Sacramento overlay). Live routing (OSRM, Google Maps) would require API keys, network access, and would return nonsensical results for invented positions. Haversine is deterministic, testable, and honest.

**Alternatives rejected**:
- **OSRM / Google Maps API**: Requires external service, API key, and network. Results meaningless for synthetic coordinates.
- **No travel time at all**: The prompt requires travel-time-aware assignment. Simulated is the honest middle ground.

**Status**: Proposed (Phase 0).

---

## D-004: In-memory plan state, not a database

**Decision**: Plan approval state lives in a Python dict. Resets on server restart.

**Rationale**: The app has no database today. Adding one for a hackathon demo introduces deployment complexity, migration logic, and a new failure mode. The limitation is documented. If deployed to production, the plan store would move to DynamoDB or a similar service — the state machine and API contract are the same.

**Alternatives rejected**:
- **SQLite**: Adds `sqlite3` usage, schema migration, and file-system state. Marginal benefit for a demo.
- **Redis**: External service dependency. Overkill for ≤10 concurrent plans.

**Status**: Proposed (Phase 0).

---

## D-005: Strands Agents SDK remains the agent framework

**Decision**: Use Strands Agents SDK for all agent interactions (extraction, advisor, future joint-planning tools). Do not introduce LangChain, CrewAI, or another agent framework.

**Rationale**: Strands is already integrated (`app/advisor.py`, `app/mission_agent.py`, `app/tools.py`). It supports tool calling, structured output, and callback handlers. The codebase has working patterns for Bedrock fallback. Introducing a second framework would create redundant abstractions and dependency conflicts.

**Status**: Confirmed (existing).

---

## D-006: Solver owns all assignment decisions

**Decision**: The CP-SAT solver is the sole authority for which volunteers are assigned. The LLM never selects, ranks, or recommends specific volunteers. It only extracts facts and explains solver output.

**Rationale**: This is the existing trust boundary (`docs/architecture.md`). Volunteer assignment is a safety-critical decision (consent, qualification, capacity). Deterministic solvers produce auditable, reproducible results. LLMs do not.

**Status**: Confirmed (existing).

---

## D-007: Minimum-change replanning via solver objective, not heuristic

**Decision**: Minimum-change replanning adds a secondary objective term to the CP-SAT model (minimize Hamming distance from baseline assignments) rather than using a greedy heuristic.

**Rationale**: CP-SAT already optimizes. Adding a weighted stability term is one line of code. A heuristic (e.g., "keep all non-failed assignments, fill gaps greedily") can miss solutions the solver would find and cannot prove optimality.

**Alternatives rejected**:
- **Greedy slot-fill**: Simpler but can produce suboptimal or infeasible results when cascading changes are needed.
- **Constraint: fix all non-failed assignments**: Too rigid; sometimes moving a non-failed volunteer to a different site is the only feasible option.

**Status**: Proposed (Phase 0).

---

## D-008: Typed contracts coexist with original models

**Decision**: Phase 1 contracts (`app/contracts.py`) are a parallel module. Original `Mission`, `Resource`, `CoalitionSolution` remain unchanged and continue to serve existing API endpoints.

**Rationale**: The original models are the API-facing contracts used by the dashboard, CLI, and Strands tools. Replacing them would break backward compatibility across 137 tests and 5 API endpoints. The new typed contracts (`MissionSpec`, `VolunteerSpec`, `VehicleSpec`, `PlanSpec`) are richer representations for the joint planner. A bridge layer (future phase) will translate between the two when the joint planner's output needs to be served through existing APIs.

**Alternatives rejected**:
- **Extend original models in-place**: Would require all existing tests and consumers to handle new required fields. High regression risk.
- **Subclass original models**: Pydantic `extra="forbid"` on the originals prevents subclassing with new fields cleanly.

**Status**: Implemented (Phase 1).

---

## D-009: Validation is deterministic and separate from optimization

**Decision**: `app/validation.py` validates a proposed plan against domain constraints without solving. It returns `ConstraintViolation` objects. The optimizer (future phase) generates feasible plans; the validator checks them.

**Rationale**: Separation of concerns. Validation is fast, deterministic, and testable without CP-SAT. It can run on human-authored plans, recovery proposals, or solver output. The optimizer can use the validator to post-check its own solutions.

**Status**: Implemented (Phase 1).

---

## D-010: Travel time must not silently become zero

**Decision**: `TravelEstimate` enforces that `unknown=True` requires `estimated_minutes=None` and vice versa. The validator flags missing or unknown travel estimates rather than treating them as zero.

**Rationale**: The current system has no travel-time modeling (Phase 0 finding #3). When travel time is added, defaulting unknowns to zero would allow the solver to assign volunteers who cannot physically reach the site in time. The explicit `unknown` flag forces the system to surface uncertainty rather than hiding it.

**Status**: Implemented (Phase 1).

---

## D-011: Joint planner is a new module, not an extension of solver.py

**Decision**: Create `app/coalition_planner.py` as a separate module rather than extending `app/solver.py`. The new planner uses Phase 1 typed contracts (`MissionSpec`, `VolunteerSpec`, `VehicleSpec`, `PlanSpec`) while the original solver uses the original contracts (`Resource`, `CoalitionRequest`, `CoalitionSolution`).

**Rationale**: The original `solve_resource_coalition()` operates on `Resource` objects with a flat capability model and no time windows, task structure, or site access. The joint planner needs task-level assignment with overlapping-window prevention, vehicle-driver compatibility, and site access — none of which fit into the original contract without breaking it. A separate module keeps both paths working independently.

**Alternatives rejected**:
- **Extend solver.py**: Would require the original solver to understand `MissionSpec`/`VolunteerSpec` contracts, breaking the 10 existing solver tests.
- **Replace solver.py**: The original solver is used by `run_pipeline()` and all existing API endpoints. Replacing it breaks 137+ tests.

**Status**: Implemented (Phase 2).

---

## D-012: Greedy solver for comparison testing only

**Decision**: Include `solve_greedy()` in the coalition planner module for testing purposes only. It demonstrates the failure mode that joint planning fixes (the Alex/Ben/Casey scenario).

**Rationale**: The Phase 2 requirements explicitly demand a test where "independent nearest-driver assignment chooses Alex and blocks" and "joint planning assigns Ben to driving." The greedy solver makes this testable without requiring the legacy per-site solver to understand typed contracts.

**Status**: Implemented (Phase 2).

---

## D-013: Solution diversity via excluded-assignment constraints

**Decision**: Generate multiple distinct alternatives by adding excluded-assignment constraints to the CP-SAT model (the sum of matching variables from a previous solution must be strictly less than the number of tasks).

**Rationale**: This is the standard approach for enumerating distinct solutions in CP-SAT. Each subsequent solve excludes all previously found assignment patterns. The solver still optimizes the objective within the remaining feasible space, so alternatives are "next-best" solutions.

**Alternatives rejected**:
- **Solution callbacks**: CP-SAT supports `SearchForAllSolutions`, but it enumerates ALL solutions without objective optimization, producing too many trivially different results.
- **Random restarts**: Non-deterministic; different runs produce different alternatives.

**Status**: Implemented (Phase 2).

---

## D-014: Counterfactual analysis deep-copies inputs, never mutates

**Decision**: `run_counterfactual_analysis()` deep-copies all volunteer, vehicle, and mission objects before removing resources and re-solving. The caller's state is never modified.

**Rationale**: Simulation must be side-effect-free. The analysis may run while the live plan is active. Mutating volunteer lists or mission specs during analysis would corrupt live state and violate the "analysis leaves live state unchanged" requirement.

**Status**: Implemented (Phase 3).

---

## D-015: Four-state recovery classification (robust/recoverable/infeasible/unknown)

**Decision**: Each counterfactual scenario is classified as one of four states: robust (not in plan), recoverable (solver found a new feasible plan), infeasible (no recovery possible), or unknown (solver time limit hit). Unknown is never silently counted as success or failure.

**Rationale**: The prompt distinguishes robustness from recoverability from confirmed recovery. "Unknown" preserves solver uncertainty rather than fabricating a result. The interpretable summary reports exact counts per category.

**Alternatives rejected**:
- **Binary feasible/infeasible**: Loses the robust vs. recoverable distinction and hides solver timeouts.
- **Probability/confidence**: The prompt explicitly forbids fabricating confidence or probability from tested scenarios.

**Status**: Implemented (Phase 3).

---

## D-016: Bottleneck explanation is structural, not LLM-generated

**Decision**: `BottleneckExplanation` is built deterministically from constraint analysis (which capabilities become uncoverable, which tasks have no remaining qualified volunteers). The LLM is not used for bottleneck identification.

**Rationale**: Bottleneck identification is a set-cover question (which tasks have zero qualified remaining volunteers after removal). This is fully deterministic. Using the LLM would add latency, non-determinism, and a Bedrock dependency for a structural question.

**Status**: Implemented (Phase 3).

---

## D-017: Stability objective via large negative bonus, not separate objective

**Decision**: When an incumbent plan is provided, add a `-1,000,000` bonus per kept assignment variable to the CP-SAT minimize objective. This makes deviation from the incumbent cost more than any possible travel-time difference, achieving lexicographic priority (stability first, travel second) within a single objective function.

**Rationale**: CP-SAT supports only one objective function. True lexicographic optimization would require multiple solve passes. The large-weight approach achieves the same result for practical problem sizes: max travel cost per task ≈ 99,900 (999 min × 100 scale), so a 1,000,000 weight per task dominates.

**Alternatives rejected**:
- **Multi-pass solve**: First minimize changes (primary), then minimize travel with changes fixed (secondary). Correct but doubles solve time and adds complexity. Unnecessary for problem sizes under 100 variables.
- **Greedy slot-fill**: Per D-007, greedy can miss solutions the solver would find.

**Status**: Implemented (Phase 4).

---

## D-018: Event deduplication by (event_id) and (resource_id, effective_time)

**Decision**: Events are deduplicated by two keys: the event ID (exact duplicate detection) and the tuple (resource_id, effective_time) (semantic duplicate detection). Events with effective_time older than the latest known for a resource are classified as stale.

**Rationale**: Multiple systems may report the same unavailability. ID-based dedup catches exact retransmissions. Semantic dedup catches reports from different sources about the same underlying event. Stale detection prevents out-of-order updates from overwriting newer state.

**Status**: Implemented (Phase 4).

---

## D-019: Approval is atomic with revalidation and reservation

**Decision**: When a coordinator approves a recovery proposal, the engine atomically (1) checks version match, (2) checks expiration, (3) checks resource reservations across missions, and (4) activates the plan. If any check fails, no state changes.

**Rationale**: Stale proposals (where the mission or resource state has changed since the proposal was generated) must be rejected rather than silently activated with wrong assumptions. Resource reservation prevents double-booking across concurrent missions. Idempotent duplicate approval prevents side effects from retransmission.

**Status**: Implemented (Phase 4).

---

## D-020: Role-swap composition arises from solver constraints, not hardcoded logic

**Decision**: The recovery engine does not implement role-swap detection as a separate algorithm. Instead, the min-change CP-SAT solver naturally discovers role swaps when they are the minimum-change feasible solution. The incumbent stability objective keeps unaffected assignments stable while the solver freely reassigns affected tasks.

**Rationale**: Hardcoding role-swap logic would only handle known patterns. The solver handles arbitrary compositions: role swaps, multi-hop cascades, and combinations thereof. The test verifies the solver discovers the swap from data and constraints without prescribing the specific volunteers.

**Status**: Implemented (Phase 4).

---

## D-021: Reuse single advisor agent with enhanced tools, not specialist agents

**Decision**: Phase 5 adds typed tools to one Strands Agent rather than creating separate specialist agents (planner agent, recovery agent, counterfactual agent). The existing advisor pattern (one agent, multiple tools, deterministic backend) is extended.

**Rationale**: The Strands SDK routes tool calls via the model's tool-use protocol. Adding tools to one agent is sufficient — the model selects the appropriate tool based on the question. Multiple agents would require an orchestration layer to route between them, adding complexity without benefit. The existing advisor.py proves this pattern works.

**Alternatives rejected**:
- **Multi-agent with router**: Adds a routing agent that must understand all sub-agents. More complex, more latency, same deterministic backend.
- **LangChain/CrewAI**: Per D-005, Strands is the agent framework. No second framework.

**Status**: Implemented (Phase 5).

---

## D-022: Tool-level authorization independent of prompts

**Decision**: Tool-level constraints (opted_in filtering, site access, vehicle eligibility) are enforced by the deterministic service layer, not by the system prompt. The prompt instructs the model not to bypass constraints, but enforcement does not rely on prompt compliance.

**Rationale**: Prompts are advisory. A sufficiently creative prompt injection could instruct the model to "ignore safety constraints." The tools call `solve_coalition()` which enforces all constraints in the CP-SAT model regardless of what the model asks for. The validation layer (`validate_plan()`) independently re-checks any proposed plan.

**Status**: Implemented (Phase 5).

---

## D-023: Conversation state is in-memory, tool-scoped, not agent-scoped

**Decision**: Conversation state (current mission, plan, proposals) is stored in a module-level dict in `semantic_tools.py`, not inside the Strands Agent instance. Tools read/write this state directly.

**Rationale**: Strands Agents are stateless between invocations — they don't persist tool results across calls. Module-level state lets tools share context (e.g., `generate_coalition_plans` stores the plan, `evaluate_plan_failures` reads it). The state resets on process restart (documented limitation, same as D-004).

**Alternatives rejected**:
- **Database-backed state**: Per D-004, no database in this project.
- **Agent memory/context window**: Strands doesn't persist structured tool state across turns natively.

**Status**: Implemented (Phase 5).

---

## D-024: Simulation vs live cancellation explicitly flagged

**Decision**: `prepare_recovery_proposal` accepts an `is_simulation` boolean (default True). The tool response includes the flag and a human-readable note. Simulations do not mark resources as actually unavailable.

**Rationale**: "What happens if Maya cancels?" must not make Maya actually unavailable. The flag makes the distinction explicit at the tool contract level, not just in the prompt. The system prompt reinforces this, but the tool enforces it by not calling any state-mutation endpoint.

**Status**: Implemented (Phase 5).

---

## D-025: Mission-control is a separate page, not a modal or tab

**Decision**: Phase 6 adds `/mission-control` as a separate HTML page with its own JS/CSS, rather than integrating into the existing dashboard as a tab, modal, or panel swap.

**Rationale**: The existing dashboard (`/`) serves the original per-site planning flow with 863 lines of JS. Embedding the mission-control layout (three-panel with simulation controls, recovery drawer, event timeline) would require extensive state management conflicts. A separate page reuses the same CSS variables and map patterns but has independent lifecycle. A link in the topbar connects the two views. Both pages share `styles.css` for consistent palette.

**Alternatives rejected**:
- **Tab in existing page**: Complex state interaction between legacy plan/render cycle and new mission-control state.
- **Modal overlay**: Screen real estate insufficient for three-panel mission-control layout.

**Status**: Implemented (Phase 6).

---

## D-026: Simulation endpoint uses fresh RecoveryEngine per call

**Decision**: `/api/mission-control/simulate-removal` creates a new `RecoveryEngine()` instance per call rather than using the global `_recovery_engine`.

**Rationale**: Simulation must be isolated from production state. The global engine accumulates events, reservations, and proposals across calls. A fresh engine ensures simulation cannot interfere with the real engine state, and repeated simulations don't accumulate stale proposals. The isolation is enforced at the API layer, not just the frontend.

**Status**: Implemented (Phase 6).

---

## D-027: Mission-control payload assembles existing services, not new computation

**Decision**: `build_mission_control_payload()` calls `solve_coalition()` and `run_counterfactual_analysis()` — the same functions used by the Phase 2/3 API endpoints. No new solver logic or constraint model was introduced.

**Rationale**: The mission-control view is a presentation concern. The domain logic is already tested (202 tests across Phases 2-5). Re-implementing or duplicating solver logic for the UI layer would create divergence risk. The assembly function transforms domain results into view models only.

**Status**: Implemented (Phase 6).

---

## D-028: Demo harness uses controlled clock, not system time

**Decision**: `demo_now()` returns a fixed Thursday timestamp (2026-09-10 14:00 Pacific). All demo scenarios use this timestamp for event creation and availability checking.

**Rationale**: Repeatable demos require deterministic time. System clock would make tests flaky and demo results non-reproducible. The controlled clock is explicit and timezone-aware. Tests verify it is deterministic.

**Status**: Implemented (Phase 7).

---

## D-029: Each demo uses isolated engine state

**Decision**: Demo B creates its own `RecoveryEngine` instance. Demo C calls `plan_recovery()` directly (stateless). Demo D calls `run_counterfactual_analysis()` directly. No shared mutable state between demos.

**Rationale**: Cross-demo contamination would make results order-dependent and non-reproducible. Each demo must produce the same result regardless of which other demos ran before it. Tests verify this: B's approval does not affect C's blocking behavior.

**Status**: Implemented (Phase 7).

---

## D-030: Vulnerability mitigations are structural, not LLM-generated

**Decision**: Demo D's `ResourceVulnerability.mitigation` is built from the counterfactual recovery status (infeasible → CRITICAL, recoverable → pre-confirm, robust → no action). No LLM call is involved.

**Rationale**: Same principle as D-016. Mitigation advice is deterministic based on the recovery classification. LLM generation would add latency and non-determinism for a structural question.

**Status**: Implemented (Phase 7).
