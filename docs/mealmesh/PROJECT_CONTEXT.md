# MealMesh — Project Context

## Repository: resq-mesh

### Architecture

**Backend**: Python 3.11+, FastAPI (`app/api/server.py`), OR-Tools CP-SAT solver, Strands Agents SDK (Amazon Bedrock Nova-lite).

**Frontend**: Vanilla JS SPA (`app/api/static/app.js`, `index.html`, `styles.css`). Leaflet.js for map. Cytoscape.js for hypergraph visualization. No build step.

**Map**: Leaflet with OpenStreetMap tiles (default). Simulated coordinates over Sacramento, CA. Volunteer markers with animated dashed polylines toward destination. No GPS — all positions are static synthetic data.

**Persistence**: None. All data is in-memory synthetic catalogs (`app/resources.py`, `app/api/scenario.py`). No database.

**LLM**: Amazon Bedrock Nova-lite (`us.amazon.nova-lite-v1:0`) via Strands Agents SDK. Used only for natural-language extraction (facts only) and tool-calling Advisor. Falls back to local demo mission when Bedrock is unreachable.

**Deployment targets**: Dockerfile, Render (`render.yaml`), Fly.io (`fly.toml`), AgentCore scaffold (`deploy/agentcore/`).

### Module Map

| Module | Purpose |
|---|---|
| `app/mission.py` | `Mission` model — structured coverage facts extracted from NL |
| `app/capabilities.py` | Capability ontology, deterministic doctrine rules, synonym resolution |
| `app/resources.py` | `Resource`/`Capability` models, synthetic catalog (20 volunteers + 3 vans) |
| `app/solver.py` | CP-SAT coalition optimizer — binary selection, capability coverage, capacity, minimize count |
| `app/resilience.py` | Counterfactual remove-and-re-solve for each selected resource |
| `app/hypergraph.py` | HyperNetX hypergraph, emergent capabilities, projection graph metrics |
| `app/orchestration.py` | Single wiring point: `run_pipeline()` chains all layers deterministically |
| `app/sentinel.py` | Autonomous stateful monitor — edge-triggered escalation policy |
| `app/notifications.py` | Slack/webhook delivery for sentinel escalations |
| `app/advisor.py` | Strands ReAct agent — tool-calling conversational interface |
| `app/tools.py` | Strands `@tool` wrappers: `assess_incident`, `get_available_resources`, `get_resources_by_required_capability` |
| `app/mission_agent.py` | Strands extraction agent — NL to `Mission` structured output |
| `app/guardrails.py` | Prompt-injection screening, input bounding |
| `app/reliability.py` | `retry_call` (exponential backoff), `CircuitBreaker` |
| `app/observability.py` | `trace_id` context var, JSON log events, `traced_stage` |
| `app/agent_observability.py` | Strands callback handlers for audit logging |
| `app/break_the_plan.py` | "Break the plan" narrative demo |
| `app/pipeline.py` | Full end-to-end demo runner |
| `app/cli.py` | Interactive CLI |
| `app/config.py` | Pydantic-settings for tile config |
| `app/api/server.py` | FastAPI app: `/api/scenario`, `/api/plan`, `/api/extract`, `/api/advisor`, `/api/sentinel` |
| `app/api/scenario.py` | Curated scenario: 3 sites, 20 volunteers, site rosters, hyperedges, presets |

### Current Behavior — Thursday Distribution Flow

**Entry point**: User opens dashboard (`GET /`), which loads `GET /api/scenario` for the full world state.

**Preset selection** (`app.js:applyPreset`): Selects one of three Thursday presets (Eastside, Harbor, West End). Each preset is a `Mission` dict with `destination`, `incident_type=thursday_distribution`, `requirements=[van driver, packer, site lead]`.

**Plan request** (`POST /api/plan`):

1. **Roster scoping** (`scenario.py:build_catalog`): Filters resources to the site roster. Volunteers commit to specific sites; floating bench (`*`) volunteers are available everywhere. Non-roster resources are excluded before the solver runs.

2. **Mission review** (`mission.py:review_mission`): Validates `destination` and `incident_type` are non-null.

3. **Capability derivation** (`capabilities.py:derive_required_capabilities`): Looks up `incident_type` in `INCIDENT_CAPABILITY_DEFAULTS`. `thursday_distribution` maps to `[van_certified_driver, food_handler, site_keyholder]`. Synonym matching handles user-facing terms ("van driver" -> `van_certified_driver`).

4. **CP-SAT solve** (`solver.py:solve_resource_coalition`): One binary variable per resource. Hard constraints: availability, capability coverage (at least one resource per required capability), capacity floor. Objective: minimize selected count. Roster order in `_SOLVER_ROSTER_ORDER` ensures deterministic tie-breaking — local site volunteers are selected over floating bench.

5. **Resilience** (`resilience.py:replan`): For each selected resource, clone catalog with that resource offline, re-solve. Classify as `recoverable` or `mission_breaking`. Report unmet capabilities when infeasible.

6. **Hypergraph** (`hypergraph.py:build_hypergraph_report`): Match selected coalition to a predefined `CoalitionHyperedge`. Compute emergent capabilities, projection graph metrics (lambda2).

7. **Response**: `OrchestrationResult` with answers to CAN? HOW? WHAT IF? WHAT IS MISSING? and a verdict.

**Map rendering** (`app.js:renderMarkers`): Selected volunteers get a blue border. Dashed polylines animate from each selected volunteer's static coordinates to the destination. Click any volunteer to toggle availability (adds to `failed` set, re-plans).

**Fallback/replacement**: Toggling a volunteer offline triggers a re-plan. CP-SAT runs again with the reduced catalog. If feasible, a replacement is selected from the bench. If infeasible, the UI shows "BLOCKED" with the missing capability.

**Natural language extraction** (`POST /api/extract`): Bedrock extracts a `Mission` from free text. Falls back to demo mission if Bedrock is unreachable.

**Advisor** (`POST /api/advisor`): Strands ReAct agent calls `assess_incident`, `get_available_resources`, `get_resources_by_required_capability` tools and returns a plain-English answer.

**Sentinel** (`GET /api/sentinel`): Replays a canned 5-event degradation timeline. Edge-triggered escalation: silent when plan holds, escalates only when verdict worsens.

### Volunteer Selection Algorithm (Current)

The solver selects **independently per role**. Given three required capabilities, it picks the minimum set of resources covering all three. Because each volunteer has exactly one capability, the solver always picks exactly 3 people (one per role).

**There is no joint feasibility across sites.** Each preset runs its own independent `POST /api/plan`. Assigning Maya to Eastside does not prevent Maya from being assigned to Harbor. The solver has no multi-site constraint.

**No travel-time modeling.** Volunteer coordinates are static display data. The solver has no distance or time awareness. The map's animated polylines are decorative, not based on routing.

**Consent boundary**: Only `opted_in=True` volunteers can be auto-assigned. `opted_in=False` (recruit-only) are excluded from the solver but shown as suggestions.

### Limitations

1. **No multi-site joint planning** — sites are planned independently; same volunteer could be "assigned" to multiple sites.
2. **No travel time** — coordinates are for display only; solver ignores distance.
3. **No temporal modeling** — no shift overlaps, no arrival time estimation.
4. **No authorization/approval** — plans are proposals with no activation workflow.
5. **No persistent state** — everything resets on page load.
6. **No real notifications** — Slack/webhook delivery is optional and unconfigured by default.
7. **Synthetic data only** — all volunteers, sites, and positions are invented.
8. **Single capability per volunteer** — no multi-skilled volunteers.
9. **Vans are decorative** — listed as assets with no capability; a driver implies a van.

### Test Suite

137 tests across 20 test files. All pass. Coverage includes solver feasibility/infeasibility, resilience recoverable/breaking, capability derivation, mission review, guardrails, notifications, sentinel timeline, orchestration pipeline, golden scenarios, advisor tools, and API endpoints.

### Build / Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api.server:app --reload  # dashboard at http://localhost:8000
python -m pytest tests/ -v           # 137 tests
```
