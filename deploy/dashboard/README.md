# Live demo hosting (MealMesh dashboard)

Hackathon judges score a **live demo URL**. This folder documents how to host
the FastAPI dashboard (`app/api/server.py`). AgentCore is separate — see
[`../agentcore/`](../agentcore/).

## What gets hosted

| Surface | Offline without AWS? | Needs Bedrock? |
|---|---|---|
| Dashboard + map + plan + Sentinel replay | Yes | No |
| Extract & Plan (NL) | Falls back to demo mission | Yes for live extract |
| Advisor | Falls back with message | Yes |

Keep `RESQ_NOTIFY_DRY_RUN=true` on the public demo so browsing never pages Slack.

## Option A — Render (fastest free HTTPS URL)

1. Push this repo to GitHub (public for the Devpost submission).
2. Go to [Render Blueprints](https://dashboard.render.com/blueprints) → New Blueprint.
3. Select the repo. It reads `render.yaml` at the root.
4. Deploy. Health check hits `/api/scenario`.
5. Paste the `*.onrender.com` URL into Devpost as the live demo.

Optional: in the Render dashboard, add AWS keys as secret env vars if you want
live Advisor / Extract on the hosted demo.

## Option B — Fly.io

```bash
brew install flyctl
fly auth login
fly apps create mealmesh   # skip if fly.toml app name is free
fly deploy
```

URL will be `https://mealmesh.fly.dev` (or the app name you chose).

## Option C — Docker anywhere (App Runner / ECS / Cloud Run)

From repo root:

```bash
docker build -t mealmesh .
docker run --rm -p 8000:8000 mealmesh
# open http://localhost:8000
```

Push the image to a registry your cloud host can pull, then point the service
at port `8000`. The container honors `$PORT`.

### AWS note

The `resq-mesh-dev` IAM user used for Bedrock typically **cannot** create ECR
repos or App Runner services. Use Render/Fly for the public URL, and keep this
AWS user for Bedrock only — or grant the deploy role separately.

## Smoke test after deploy

```bash
curl -sS "$DEMO_URL/api/scenario" | head -c 200
curl -sS "$DEMO_URL/api/sentinel" | head -c 200
open "$DEMO_URL"
```

You should see the MealMesh dashboard, three Thursday presets, and Silent Deputy
replay (4 autonomous / 2 escalated).

## AgentCore (separate score booster)

```bash
pip install -r deploy/agentcore/requirements-agentcore.txt
agentcore configure --entrypoint deploy/agentcore/agent_entrypoint.py
agentcore launch
agentcore invoke '{"action":"assess","mission":{"destination":"Riverside Community Meals — Eastside","incident_type":"thursday_distribution","requirements":["van driver","packer","site lead"]}}'
```

Show that invoke in the video even if the public URL is Render/Fly.
