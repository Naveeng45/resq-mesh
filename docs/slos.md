# RESQ-Mesh SLOs & Production Controls

All targets are for the **deterministic pipeline** (`run_pipeline`), which
excludes the external Bedrock call. Numbers are hackathon-scoped starting points,
not contractual commitments.

## Service level objectives

| SLO | Target | How it is measured |
|---|---|---|
| Pipeline availability (local) | 99.9% | pipeline is pure; only crashes count |
| Pipeline latency (P95, excl. LLM) | < 250 ms | small CP-SAT model, ~5 resources |
| Mission-feasibility correctness | 100% on golden set | `python -m app.eval` (5/5) |
| Verdict-branch coverage | all 5 branches | `tests/test_golden.py` |
| LLM extraction success (when Bedrock reachable) | > 95% | callback + fallback logging |

Verdict branches covered by golden scenarios: `ready to deploy`,
`ready but fragile`, `no feasible coalition`, `needs more facts`,
`needs human review`.

## Observability

- One `trace_id` per mission run, returned on `OrchestrationResult.trace_id`.
- Structured JSON logs via `app/observability.configure_logging(json_format=True)`.
- Per-stage timings via `traced_stage`; `pipeline.start` / `pipeline.finish`
  events carry verdict, feasibility, and selected resources.

## Security controls

- **Prompt-injection defense**: `app/guardrails.sanitize_incident_text` flags
  instruction-override, role-override, prompt-exfiltration, role-tag injection,
  and known jailbreak markers; strips control characters; bounds length to 2000
  chars.
- **Strict schemas**: every model uses `extra="forbid"`; the LLM returns only the
  `Mission` schema and cannot emit resource allocations.
- **No credentials in code**: secrets come from `.env` (git-ignored) via
  `app/config.py`.
- **LLM is not the optimizer**: even a fully successful injection cannot allocate
  resources; that authority lives only in CP-SAT.

## Cost controls

- Model `us.amazon.nova-lite-v1:0` (small, low cost) for fact extraction only.
- Single LLM call per mission (one extraction), no agent-loop tool churn.
- `streaming=False` and `null_callback_handler` in non-verbose paths.
- Circuit breaker prevents cost/latency amplification during a Bedrock outage.

## Reliability boundaries

- `retry_call`: up to 3 attempts, exponential backoff (0.5s, 1.0s), retries only
  transient `ClientError`.
- `CircuitBreaker`: opens after 3 consecutive failures, 30s cooldown, half-open
  probe; falls back to the local demo mission when open.
