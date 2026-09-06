# RESQ-Mesh Architecture

## Core principle

> **LLM understands. Domain rules validate. Hypergraph represents. Math solver
> decides. Resilience engine stress-tests. Human approves. Agent orchestrates.**

The LLM never allocates scarce or safety-critical resources. It only turns
natural language into structured facts. Every decision after that is
deterministic and testable.

## Data flow

```text
Natural language incident
        │
        ▼
[guardrails]  app/guardrails.py        strip/flag prompt injection, bound size
        │
        ▼
[LLM extract] app/mission_agent.py     Strands + Bedrock -> Mission (facts only)
        │
        ▼
[HITL review] app/mission.py           missing critical facts? -> ask a human
        │
        ▼
[capabilities] app/capabilities.py     deterministic doctrine: facts -> required caps
        │
        ▼
[solver]      app/solver.py            OR-Tools CP-SAT -> feasible coalition
        │
        ▼
[resilience]  app/resilience.py        remove each resource & re-solve
        │
        ▼
[hypergraph]  app/hypergraph.py        emergent capabilities + structural metrics
        │
        ▼
[orchestrator] app/orchestration.py    single wiring point -> OrchestrationResult
        │
        ▼
Answers: CAN? HOW? WHAT IF? WHAT IS MISSING?  +  Verdict
```

`app/orchestration.run_pipeline` is the single deterministic wiring point. The
LLM is called only in the extract step; the pipeline itself is pure and unit
tested (`tests/test_orchestration.py`, `tests/test_golden.py`).

## Trust boundary

| Layer | Probabilistic? | Can allocate resources? |
|---|---|---|
| Guardrails | no | no |
| LLM extraction | **yes** | **no** (facts only) |
| Mission review (HITL) | no | no (gates the flow) |
| Capability rules | no | no (derives requirements) |
| CP-SAT solver | no | **yes** (this is the decision authority) |
| Resilience engine | no | no (stress-tests the decision) |
| Human approval | human | approves before any simulated execution |

Structured Pydantic models (`extra="forbid"`) sit on every boundary so the
probabilistic and deterministic halves cannot pass each other malformed data.

## Observability (Lesson 10)

- `app/observability.py` provides a `trace_id` bound per mission run, structured
  JSON log events (`configure_logging(json_format=True)`), and a `traced_stage`
  context manager that records per-stage duration.
- `run_pipeline` binds a `trace_id`, emits `pipeline.start` / `pipeline.finish`
  events, and returns the `trace_id` on `OrchestrationResult` for correlation.
- These events map 1:1 onto OpenTelemetry spans if/when this is deployed to
  AgentCore.

## Reliability & security (Lesson 10)

- `app/reliability.py`: `retry_call` (bounded exponential backoff) and a
  three-state `CircuitBreaker` wrap the Bedrock call in `app/cli.py`. A hard
  outage fails fast to the local demo mission instead of hanging.
- `app/guardrails.py`: prompt-injection screening + input bounding before the LLM.
- Strict tool/output schemas: `Mission` and all solver models forbid extra fields.

## Escalation notifications

`app/notifications.py` is the delivery leg of the Sentinel's promise. It turns an
`Escalation` into a Slack Block Kit message or a generic JSON webhook POST
(stdlib `urllib`, injectable sender, no new dependency).

| Property | Why |
|---|---|
| Deterministic | Payloads are a pure function of the escalation. No LLM decides whether to alert or what the alert says. |
| No-op if unconfigured | Zero env vars → nothing is sent. The offline demo is unaffected. |
| Never breaks the loop | Every transport failure is caught, logged as `notification.failed`, and returned as a `NotificationResult`. Monitoring outlives its notifier. |
| Escalations only | `silent` / `auto_recomposed` / `improved` / `resolved` deliberately send nothing. |
| Replay-safe | `run_sentinel_demo()` and `GET /api/sentinel` default to dry-run, so a canned replay can never page an on-call human (`?notify=true` opts in). |
| URL never leaks | `describe()` returns a channel label only; the dashboard never sees the webhook. |

Config is env-driven (`RESQ_NOTIFY_*`, see `.env.example`), including a
`min_severity` threshold and a dry-run switch.

## Conversational Advisor (tool-calling agent)

`app/advisor.py` is a Strands ReAct agent that answers a coordinator's
natural-language questions by **calling tools** — `assess_incident` (runs the
CP-SAT pipeline), `get_available_resources`, and
`get_resources_by_required_capability`. The trust boundary holds: the tools make
every decision; the model orchestrates and explains, and never allocates. This is
the same principle as the extraction path, exposed as a multi-tool agent. Exposed
at `POST /api/advisor` and as `python -m app.advisor`.

## AgentCore deployment (scaffolded)

**The deployment path is built, not just documented — see
[`deploy/agentcore/`](../deploy/agentcore/).** `agent_entrypoint.py` exposes the
deterministic pipeline (`assess`, offline-capable) and the Advisor (`ask`,
Bedrock) behind AgentCore Runtime; a `Dockerfile` (arm64) and deploy guide ship
alongside it. The deterministic path is unit-tested with zero AWS
(`tests/test_agentcore.py`). Deploy with `agentcore configure && agentcore
launch`.

The mapping from local to hosted is direct:

| Local today | AgentCore target |
|---|---|
| `app/orchestration.run_pipeline` | agent entrypoint behind AgentCore Runtime |
| `app/mission_agent` (Strands + Bedrock) | same Strands agent, hosted model |
| `app/observability` JSON events | OpenTelemetry spans -> CloudWatch/X-Ray |
| `retry_call` + `CircuitBreaker` | same boundaries + AgentCore retry policy |
| `app/eval` golden scenarios | pre-deploy regression gate in CI |
| in-memory catalog | external resource service / DynamoDB |

Nothing in the deterministic core needs to change to deploy; only the transport
and hosting around it.
