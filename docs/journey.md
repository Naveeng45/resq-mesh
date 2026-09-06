# Build Journey

RESQ-Mesh was built in layered steps. Each step was independently testable, and
each one defends a single idea: **the language model interprets, but never
decides.** This is the story of how the pieces came together — and why an
emergency-coordination tool is a good fit for *Agents for Humans*.

> The finished product framing lives in the top-level [`README.md`](../README.md).
> This document is the "how we got here" for judges and for a build-journey post.

## Why this shape

Emergency coordinators drown in routine status changes — a boat goes down for
maintenance, a team returns, a road reopens. Almost all of those changes don't
require a human. A few of them break the plan and need a decision *now*. The
whole design pushes toward one goal: **handle the routine silently, surface the
real decisions.** The autonomous **Sentinel** (`app/sentinel.py`) is where that
goal becomes a running agent.

## The layers

### 04 · Resource catalog — `app/resources.py`, `app/tools.py`
Deterministic world-state a planner can query without asking the LLM to invent
facts. `Resource`/`Capability` models with `availability`, `status`,
`reliability`, `location`, `capacity`. Every record is tagged
`synthetic_data=True`. Availability filtering happens in Python, so unavailable
resources never reach the planner. Strands `@tool` wrappers expose the catalog.

### 05 · Goal → capabilities — `app/capabilities.py`, `app/mission.py`
The trust boundary. The LLM extracts incident *facts* into a `Mission`;
deterministic rules (`derive_required_capabilities`) decide which capabilities
the mission *requires*. Low-confidence or unknown incidents route to human
review. The model is a translator, not a commander.

### 06 · CP-SAT solver — `app/solver.py`
An OR-Tools constraint solver chooses a feasible coalition: one binary variable
per resource, hard constraints for capability coverage / capacity / availability,
objective = fewest resources. Feasibility and infeasibility are *proven*, not
generated. This is the decision authority.

### 07 · Failure & replan — `app/resilience.py`
Counterfactual robustness: remove each selected resource and re-solve. Classify
every single-loss as recoverable or mission-breaking, and name the unmet
capability when replanning fails.

### 08 · Hypergraph model — `app/hypergraph.py`
Some capabilities only exist when resources operate *together* (a boat + a medic
= flood evacuation). Coalition units become hyperedges carrying emergent
capabilities; a projected graph yields structural metrics (`lambda2`). Explicitly
a representation layer — criticality still comes from remove-and-re-solve.

### 09 · Orchestration & HITL — `app/orchestration.py`, `app/cli.py`
One wiring point chains every layer: `Mission → review → capabilities → CP-SAT →
resilience → hypergraph → answers + verdict`. Missing critical facts
short-circuit before the solver runs. Answers the four questions: **CAN / HOW /
WHAT IF / WHAT IS MISSING.**

### 10 · Productionization — observability, guardrails, reliability, eval
- `app/observability.py` — a `trace_id` per run, structured JSON logs, per-stage timings.
- `app/guardrails.py` — prompt-injection screening + input bounding before the LLM.
- `app/reliability.py` — `retry_call` (backoff) + `CircuitBreaker` around Bedrock.
- `app/eval.py` + `examples/golden_scenarios.json` — a deterministic regression eval that doubles as a feasibility-correctness metric.
- `app/break_the_plan.py` — the headline "recompose, then name what's missing" demo.

### The Sentinel — `app/sentinel.py`
The layer that makes RESQ-Mesh an *Agent for Humans*. It watches world-state
changes, re-runs the deterministic pipeline on each one, and applies an
edge-triggered escalation policy: **silent** when nothing meaningful changed,
**auto-recompose** when it can absorb a loss, **escalate** only when a genuine
decision is needed, and **resolved/improved** when a human's action restores the
mission. The LLM is never in this loop.

### Reaching the human — `app/notifications.py`
An escalation nobody receives isn't an escalation. Configuring one environment
variable routes escalations — *and only escalations* — to Slack or a JSON
webhook. The interesting constraints were the negative ones: it must no-op when
unconfigured (the demo has to work offline), a dead webhook must never stop
monitoring, and a canned replay of the demo timeline must never page a real
on-call human. So delivery is dry-run by default everywhere except an explicit
`--notify` / `?notify=true`, and every transport failure is caught and reported
rather than raised.

## What each step proves

| Step | Guarantee it defends |
|---|---|
| 04 Catalog | The planner reads facts; it never fabricates availability. |
| 05 Capabilities | The LLM cannot expand the mission or invent doctrine. |
| 06 Solver | Allocation is proven feasible/infeasible, not generated. |
| 07 Resilience | The plan is tested against loss before it is trusted. |
| 08 Hypergraph | Coalition structure is explicit, not implicit. |
| 09 Orchestration | One deterministic, unit-tested flow; humans gate gaps. |
| 10 Productionization | Observable, guarded, reliable, regression-tested. |
| Sentinel | Routine handled silently; humans see only real decisions. |
| Notifications | The decision actually reaches a human — and a broken channel never stops the watch. |

## Run the journey

```bash
python -m app.agent            # end-to-end pipeline on one world
python -m app.break_the_plan   # recompose, then name the missing capability
python -m app.sentinel         # the autonomous background-monitoring loop
python -m app.notifications    # preview the alerts an escalation would send
python -m app.advisor          # tool-calling Advisor agent (Strands + Bedrock)
python -m app.eval             # golden regression eval (all verdict branches)
python -m pytest -q            # full test suite

python deploy/agentcore/agent_entrypoint.py   # AgentCore entrypoint (deterministic, offline)
```

## Beyond the lessons

Two layers extend the build for *Agents for Humans*:

- **Advisor** (`app/advisor.py`) — a Strands ReAct agent that answers a
  coordinator's questions by calling deterministic tools (`assess_incident`,
  catalog lookups). The model explains; the tools decide.
- **AgentCore deploy** (`deploy/agentcore/`) — a runtime entrypoint, arm64
  Dockerfile, and deploy guide that host the same core behind Bedrock AgentCore
  without changing a line of the decision logic.
