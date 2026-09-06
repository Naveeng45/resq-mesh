# Deploy RESQ-Mesh to Amazon Bedrock AgentCore Runtime

This hosts RESQ-Mesh behind **AgentCore Runtime**. The deterministic core does
not change — AgentCore only adds hosted transport, auth, scaling, and
observability. The CP-SAT pipeline still owns every decision.

## What's here

| File | Purpose |
|---|---|
| `agent_entrypoint.py` | The runtime entrypoint. `handle(payload)` routes to the deterministic pipeline (`assess`) or the tool-calling Advisor (`ask`). |
| `requirements-agentcore.txt` | App deps + `bedrock-agentcore` + the starter toolkit. |
| `Dockerfile` | linux/arm64 image (AgentCore requirement). |

## Test locally (no AWS needed)

The `assess` action is fully deterministic and offline:

```bash
python deploy/agentcore/agent_entrypoint.py
# -> {"verdict": "...", "answers": {...}, "selected_resource_ids": [...], ...}
```

## Deploy (from the repo root)

Prereqs: AWS credentials configured, and Bedrock model access enabled for
`us.amazon.nova-lite-v1:0` in your region.

```bash
pip install -r deploy/agentcore/requirements-agentcore.txt

# 1. Configure (generates the AgentCore config + an execution role on first run)
agentcore configure --entrypoint deploy/agentcore/agent_entrypoint.py

# 2. Build (arm64) and deploy to AgentCore Runtime
agentcore launch

# 3. Invoke the deployed agent
agentcore invoke '{"action": "assess", "mission": {"destination": "Willow Creek", "incident_type": "flood", "requirements": ["boat", "medical team"]}}'
agentcore invoke '{"action": "ask", "question": "What single failure breaks the flood plan?"}'
```

`agentcore launch` builds the arm64 image (via CodeBuild — no local Docker
required), pushes to ECR, and deploys. To build the image yourself instead:

```bash
docker buildx build --platform linux/arm64 -f deploy/agentcore/Dockerfile -t resq-mesh-agentcore .
```

## IAM (execution role) — minimum

The runtime's execution role needs:

- `bedrock:InvokeModel` on the Nova-lite model (for the Advisor path only; the
  `assess` path calls no AWS services).
- CloudWatch Logs write access for observability.

`agentcore configure` can create a suitable role automatically on first run.

## How the local observability maps

The pipeline already emits a `trace_id` and structured JSON events
(`app/observability.py`). Under AgentCore these map onto OpenTelemetry spans →
CloudWatch / X-Ray. See `docs/architecture.md` for the full mapping table.
