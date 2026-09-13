# MealMesh — Test Matrix

## Existing Coverage (137 tests, all passing)

| Test File | Count | Scope |
|---|---|---|
| `test_solver.py` | ~10 | Feasible/infeasible coalitions, capability coverage, capacity constraints |
| `test_resilience.py` | ~8 | Recoverable/mission-breaking failures, unmet capability reporting |
| `test_capabilities.py` | ~12 | Doctrine rules, synonym resolution, human review triggers |
| `test_mission.py` | ~6 | Mission validation, critical fact detection |
| `test_orchestration.py` | ~10 | Full pipeline wiring, verdicts, answer generation |
| `test_golden.py` | ~8 | Golden scenario regression (deterministic expected outputs) |
| `test_hypergraph.py` | ~6 | Emergent capabilities, projection graph, lambda2 |
| `test_sentinel.py` | ~12 | Sentinel timeline, edge-triggered escalation, action classification |
| `test_sentinel_agent.py` | ~4 | Sentinel demo rendering |
| `test_notifications.py` | ~10 | Slack/webhook payload formatting, delivery status, dry run |
| `test_tools.py` | ~6 | Strands tool wrappers, availability filtering |
| `test_api.py` | ~8 | FastAPI endpoint responses, error handling |
| `test_advisor.py` | ~6 | Advisor tool invocation, thinking-tag stripping |
| `test_guardrails.py` | ~8 | Injection detection, input sanitization, truncation |
| `test_reliability.py` | ~8 | Retry backoff, circuit breaker state transitions |
| `test_observability.py` | ~6 | Trace ID, JSON log formatting |
| `test_agent_observability.py` | ~4 | Audit callback handler |
| `test_agentcore.py` | ~3 | AgentCore entrypoint (offline) |
| `test_break_the_plan.py` | ~4 | Break-the-plan narrative steps |
| `test_eval.py` | ~2 | Evaluation framework |

## Baseline Test Run

```
$ .venv/bin/python3 -m pytest tests/ -v
137 passed in 34.35s
```

All 137 tests pass. No pre-existing failures. No skipped tests.

## Required Acceptance Scenarios (Phase 1+)

### Phase 1: Joint Solver

| ID | Scenario | Expected |
|---|---|---|
| J-1 | Three Thursday sites, sufficient volunteers on each roster | Joint feasible; each volunteer assigned to exactly one site |
| J-2 | Two sites need the same floating-bench driver (Luis) | Joint solver assigns Luis to one site, Avery to the other; both feasible |
| J-3 | Same as J-2 but independent solving | Independent solving assigns Luis to both — demonstrates the failure |
| J-4 | Not enough volunteers across all sites | Joint infeasible; report which site and which capability is uncovered |
| J-5 | One site has no rostered keyholder | That site infeasible; other sites unaffected |
| J-6 | Feature flag off | Existing per-site behavior unchanged; all 137 tests still pass |

### Phase 2: Travel Time

| ID | Scenario | Expected |
|---|---|---|
| T-1 | All volunteers within deadline | Joint feasible with travel times in response |
| T-2 | Nearest volunteer exceeds deadline, farther volunteer makes it | Solver picks the farther but on-time volunteer |
| T-3 | No volunteer can make the deadline for one site | That site infeasible; travel time cited as reason |

### Phase 3: Bottleneck

| ID | Scenario | Expected |
|---|---|---|
| B-1 | Remove a non-bottleneck volunteer | Joint replan succeeds; no sites affected |
| B-2 | Remove the only driver on Eastside's roster | Eastside infeasible; bench driver pulled from Harbor; Harbor now at risk |
| B-3 | Cascading failure: removing one volunteer makes two sites infeasible | Both sites reported; explanation names the cascading dependency |

### Phase 4: Minimum-Change Replan

| ID | Scenario | Expected |
|---|---|---|
| R-1 | One cancellation, bench has a direct replacement | Exactly one assignment changes |
| R-2 | One cancellation, replacement requires cascading reassignment | Minimum changes reported; fewer than from-scratch solve |
| R-3 | No feasible replan | Report infeasible with missing capabilities |

### Phase 5: Approval

| ID | Scenario | Expected |
|---|---|---|
| A-1 | Propose → Approve | State transitions correctly |
| A-2 | Propose → Reject → Re-propose | New plan created; old plan stays rejected |
| A-3 | Attempt to activate without approval | Rejected; state unchanged |

### Phase 6: Map

| ID | Scenario | Expected |
|---|---|---|
| M-1 | Joint plan displayed | Cross-site dependency edges visible |
| M-2 | Toggle volunteer offline | Recovery overlay shows proposed replacement before approval |
| M-3 | Bottleneck volunteer highlighted | Pulsing indicator on single-point-of-failure volunteers |

### Phase 7: Agent Tools

| ID | Scenario | Expected |
|---|---|---|
| AG-1 | "Can all three sites open Thursday?" | Agent calls `assess_joint_coverage`, reports joint verdict |
| AG-2 | "What happens if Luis cancels?" | Agent calls `simulate_cancellation`, reports affected sites and replan |
| AG-3 | Bedrock unavailable | Graceful fallback to offline tool demo |
