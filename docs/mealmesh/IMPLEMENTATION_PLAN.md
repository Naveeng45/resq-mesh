# MealMesh Enhancement — Implementation Plan

## Guiding Principle

Existing allocation stays available. Enhanced planner is introduced alongside it. Domain services remain authoritative. The current map and app shell are reused. No broad rewrite.

## Phase 1: Multi-Site Joint Coalition Solver

**Goal**: Replace independent per-site solving with a joint optimizer that assigns volunteers across all three Thursday sites simultaneously, preventing double-assignment.

**Why first**: This is the foundational constraint violation. Independent solving lets the same volunteer be "assigned" to two sites. Every subsequent enhancement (travel time, bottleneck analysis, replanning) depends on having a single joint feasible coalition.

**Scope**:
- `app/solver.py`: Add `JointCoalitionRequest` (list of site missions) and `JointCoalitionSolution`. Extend CP-SAT model with cross-site exclusivity constraints (each volunteer assigned to at most one site).
- `app/api/scenario.py`: Add `POST /api/joint-plan` endpoint.
- Feature flag: `MEALMESH_JOINT_PLANNING=true` env var. When false, existing per-site behavior is unchanged.
- Tests: Joint feasible, joint infeasible (not enough volunteers across sites), and the demonstrating scenario (see below).
- No UI changes in this phase.

**Demonstrating scenario**: Eastside and Harbor both need a driver. Only two opted-in drivers are on both rosters (e.g., Luis and Avery on the floating bench). Independent solving picks Luis for Eastside and Luis for Harbor — infeasible in reality. Joint solving assigns Luis to Eastside and Avery to Harbor.

## Phase 2: Travel-Time-Aware Assignment

**Goal**: Add simulated travel time between volunteer locations and destinations. The solver uses travel time as a soft cost or hard deadline constraint.

**Scope**:
- `app/travel.py`: Haversine distance → simulated travel time (labeled as simulated). Travel-time matrix for all resource-destination pairs.
- Extend `JointCoalitionRequest` with optional deadline per site.
- Solver: Add travel-time cost to objective, or hard constraint (resource must arrive before deadline).
- API: Include travel times in plan response.
- Tests: Deadline-feasible, deadline-infeasible cases.

**Depends on**: Phase 1 (joint model).

## Phase 3: Bottleneck Explanation and Counterfactual Testing

**Goal**: For each joint coalition, identify which resources are single points of failure across the multi-site plan. Explain in human terms why removing a resource breaks coverage and which sites are affected.

**Scope**:
- Extend `app/resilience.py`: Multi-site counterfactual testing. Remove one resource, re-solve the joint problem. Report which sites become infeasible and what capability is uncovered.
- `app/bottleneck.py`: Bottleneck classification — "Maya is the only Eastside-rostered driver; losing her requires pulling Luis from Harbor, which leaves Harbor without a driver."
- LLM generates human-readable explanation from the deterministic bottleneck data.
- Tests: Single-point-of-failure detection, cascading failure across sites.

**Depends on**: Phase 1 (joint model).

## Phase 4: Minimum-Change Replanning

**Goal**: When a volunteer cancels, find the replacement plan that changes the fewest assignments from the current plan, rather than re-solving from scratch.

**Scope**:
- Extend joint solver with a "stability" objective term: minimize the number of changed assignments relative to the baseline.
- `app/replan.py`: Given a baseline joint plan and a set of newly-unavailable resources, solve for the minimum-change replacement.
- Report which assignments changed and why.
- Tests: Minimum-change vs. from-scratch comparison.

**Depends on**: Phase 1, Phase 3.

## Phase 5: Human Approval Workflow

**Goal**: Plans are proposals until a coordinator approves them. Approval transitions the plan from PROPOSED to APPROVED. Approved plans can trigger notifications to opted-in volunteers.

**Scope**:
- `app/plan_state.py`: State machine: `PROPOSED → APPROVED → ACTIVE → COMPLETED`. Only `APPROVED` can activate notifications.
- API: `POST /api/plan/{id}/approve`, `POST /api/plan/{id}/reject`.
- In-memory plan store (no database; state resets on restart; documented limitation).
- Sentinel integration: Sentinel can propose re-plans but cannot approve them.
- Tests: State transitions, rejection, re-proposal after rejection.

**Depends on**: Phase 4.

## Phase 6: Enhanced Map — Dependency and Recovery Visualization

**Goal**: The map shows mission dependencies (which volunteers are shared across sites), bottleneck indicators, and recovery proposals when a volunteer is toggled offline.

**Scope**:
- Frontend: Draw cross-site dependency edges on the map (e.g., Luis serves as backup for both Eastside and Harbor). Color-code by fragility.
- Bottleneck markers: Pulsing indicator on single-point-of-failure volunteers.
- Recovery overlay: When a volunteer is toggled offline, show the minimum-change replan as ghost assignments (proposed replacements in a different style) before approval.
- Hypergraph panel: Multi-site hyperedges showing cross-site coalition dependencies.

**Depends on**: Phase 3, Phase 4, Phase 5.

## Phase 7: Strands Agent Integration for Coalition Advisory

**Goal**: The Advisor agent can answer multi-site joint-planning questions ("Can all three Thursday sites open?", "What happens if Luis cancels?") using the joint solver as a tool.

**Scope**:
- New tool: `assess_joint_coverage` — runs the joint solver across all sites and returns the combined result with bottleneck analysis.
- New tool: `simulate_cancellation` — removes a named volunteer and returns the minimum-change replan.
- Advisor system prompt update: Teach the agent about joint planning without letting it make decisions.
- Tests: Tool invocation, fallback when Bedrock is unreachable.

**Depends on**: Phase 1, Phase 3, Phase 4.

## Dependency Graph

```
Phase 1 (Joint Solver) ──┬── Phase 2 (Travel Time)
                          ├── Phase 3 (Bottleneck) ──┬── Phase 4 (Min-Change Replan) ── Phase 5 (Approval)
                          │                          └── Phase 6 (Enhanced Map)
                          └── Phase 7 (Agent Integration)
```

Phase 2 is independent of Phases 3–7. Phases 3 and 7 can proceed in parallel after Phase 1.
