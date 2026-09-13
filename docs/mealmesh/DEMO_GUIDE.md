# MealMesh — Demo Guide

## ALL DATA IS SIMULATED

No real volunteers, meals, arrivals, or coordinator time savings are claimed.
Travel estimates are Haversine-based placeholders.

## Setup

```bash
# Prerequisites: Python 3.11+
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run tests (proves all demos work)
.venv/bin/python3 -m pytest tests/test_e2e_demo.py -v

# Run full test suite (387 tests)
.venv/bin/python3 -m pytest tests/ -v

# Start the server
uvicorn app.api.server:app --reload
# Dashboard: http://localhost:8000
# Mission Control: http://localhost:8000/mission-control
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MEALMESH_JOINT_PLANNING` | `true` | Enable/disable joint coalition planner |
| `AWS_DEFAULT_REGION` | — | Required for Bedrock LLM features |
| `TILE_URL` | OpenStreetMap default | Map tile server URL |
| `TILE_ATTRIBUTION` | OpenStreetMap default | Map attribution text |

No secrets are stored in the repository. Bedrock access requires AWS credentials.

## Five-Minute Demo Outline

### Minute 1: The Problem (Dashboard)

1. Open `http://localhost:8000`
2. Select "Eastside Thursday" preset
3. Click "Generate Plan" — shows per-site assignment
4. Point out: "This works for one site. But it solves independently."

### Minute 2: Demo A — Joint Planning (Mission Control)

1. Open `http://localhost:8000/mission-control`
2. Show the task panel: Driver, Food Handler, Site Keyholder
3. "The joint solver assigned all three roles simultaneously"
4. "Greedy would pick the nearest driver first — if that driver also holds the site key, the keyholder task blocks"
5. "The CP-SAT solver sees all constraints at once and avoids this"
6. Show alternatives panel — multiple distinct feasible plans

### Minute 3: Demo B — Recomposition

1. In the simulation panel, click Maya (driver)
2. Click "Simulate Removal"
3. Show: recovery proposal appears — Gina replaces Maya
4. "The solver used minimum-change replanning — only 1 assignment changed"
5. Click "Approve" — plan transitions from proposed to approved
6. Show event timeline: event → recovery → approval
7. "Volunteer acceptance is tracked separately — approval is not consent"

### Minute 4: Demo C — Honest Block

1. Reset simulation
2. Click Elena (keyholder)
3. Click "Simulate Removal"
4. Show: BLOCKED status — no recovery possible
5. "Elena is the sole authorized keyholder"
6. Show targeted request: "Need one volunteer with site_keyholder..."
7. "The system did NOT fabricate a replacement or claim it can proceed"

### Minute 5: Demo D — Prevention & Architecture

1. Show counterfactual panel (right side)
2. "Before activation, we stress-tested every assigned volunteer"
3. Point out: Maya/Priya = recoverable, Elena = SPOF (red pulse)
4. "This tells the coordinator: recruit a backup keyholder before going live"
5. Show architecture: "LLM extracts intent, solver decides, validator checks, human approves"

## Demo Scenarios (Automated)

Run all demos programmatically:

```python
from tests.fixtures.thursday_fixture import *
from app.demo_runner import run_full_demo

mission = build_eastside_mission()
volunteers = build_volunteers()
vehicles = [build_church_van()]

result = run_full_demo(mission, volunteers, vehicles)
print(f"Verdict: {result.verdict}")
print(f"Total duration: {result.total_duration_ms:.0f} ms")
for m in result.measurements:
    print(f"  {m.scenario}: {m.solver_status} ({m.planning_duration_ms + m.replanning_duration_ms + m.counterfactual_duration_ms:.0f} ms)")
```

## API Endpoints Summary

### Original (unchanged)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api/scenario` | World state |
| POST | `/api/plan` | Per-site plan (legacy) |
| POST | `/api/extract` | NL → Mission (Bedrock) |
| POST | `/api/advisor` | Advisor agent (Bedrock) |
| GET | `/api/sentinel` | Sentinel timeline |

### Phase 2: Joint Planning

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/joint-plan` | Joint coalition assignment |

### Phase 3: Counterfactual

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/counterfactual` | What-if failure analysis |

### Phase 4: Recovery

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/recovery/event` | Ingest unavailability event |
| POST | `/api/recovery/plan` | Min-change recovery proposal |
| POST | `/api/recovery/approve` | Approve proposal |
| GET | `/api/recovery/risk/{id}` | Mission risk status |

### Phase 5: Semantic Orchestration

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/semantic/context` | Load mission context |
| POST | `/api/semantic` | Natural-language query |
| POST | `/api/semantic/reset` | Reset conversation |
| GET | `/api/proposal/{id}` | Proposal status |

### Phase 6: Mission Control

| Method | Path | Purpose |
|---|---|---|
| GET | `/mission-control` | Mission-control dashboard |
| POST | `/api/mission-control` | Assemble view |
| POST | `/api/mission-control/simulate-removal` | Simulate removal |
| GET | `/api/mission-control/fixture` | Demo fixture data |

## Implemented Architecture

```
User (Coordinator)
  │
  ├── Dashboard (/)              ← Original per-site planning
  └── Mission Control (/mc)      ← New joint planning view
        │
        ├── Leaflet Map           ← Volunteer markers, routes, SPOF halos
        ├── Task Panel            ← Assignments, qualifications, status
        ├── Simulation Panel      ← Click-to-remove failure testing
        ├── Recovery Drawer       ← Proposal diff, approval, gaps
        ├── Counterfactual Panel  ← Per-volunteer recovery status
        └── Event Timeline        ← Event → Recovery → Approval log
              │
FastAPI Server
  │
  ├── Coalition Planner (CP-SAT)  ← Joint assignment, min-change, alternatives
  ├── Validation Engine            ← 10 deterministic rules, independent check
  ├── Counterfactual Engine        ← Remove-and-re-solve per resource
  ├── Recovery Engine              ← Events, proposals, approval, reservations
  ├── Semantic Tools (Strands)     ← 6 typed tools wrapping above services
  ├── Semantic Orchestrator        ← Strands Agent + Bedrock (optional)
  └── Mission Control Assembly     ← View model from domain objects
```

**Trust boundary**: LLM extracts intent and explains results.
Solver owns all assignment decisions. Validator independently checks plans.
Approval requires human coordinator. Volunteer acceptance is explicit.

## Known Limitations

1. **All data SIMULATED** — no real volunteers, sites, or meals
2. **No database** — state resets on server restart
3. **No Bedrock access** — LLM features degrade gracefully
4. **No real notifications** — test adapter captures events in memory
5. **Travel estimates simulated** — Haversine × speed factor, labeled
6. **Map shows straight lines** — not road navigation
7. **In-memory reservations** — no distributed locking
8. **Single-mission scope** — cross-site joint planning is single-mission
9. **No actual pilot data** — cannot claim meals rescued or time saved
10. **Proposal expiration checked at approval** — not proactively

## Integrations Status

| Integration | Status |
|---|---|
| CP-SAT solver | ✅ Working — deterministic, tested |
| Strands Agents SDK | ✅ Working — tools registered, offline demo available |
| Amazon Bedrock | ⚠️ Requires AWS credentials — graceful fallback |
| Slack notifications | ⚠️ Configured but not connected — test adapter |
| AgentCore deployment | ⚠️ Scaffold exists, not deployed |
| Database | ❌ Not present — in-memory only |

## Operator-Validated Policy Requirements Before Real Deployment

1. **Food-safety qualifications** — Verify capability codes map to real certifications
2. **Site access authorization** — Confirm authorized_site_ids reflect actual key/access rights
3. **Vehicle eligibility** — Validate driver certification against fleet records
4. **Consent boundary** — Confirm opted_in status reflects current volunteer agreements
5. **Notification routing** — Configure Slack workspace and channel for escalations
6. **Approval authority** — Define which coordinator roles can approve recovery plans
7. **Data residency** — Determine where volunteer PII may be stored
8. **Backup keyholder policy** — Recruit backup keyholders for all SPOF sites

## Deployment Checklist

- [ ] Run full test suite: `pytest tests/ -v` (387 tests pass)
- [ ] Verify production build: `uvicorn app.api.server:app`
- [ ] Configure Bedrock credentials (or accept offline fallback)
- [ ] Configure notification adapter (Slack/webhook)
- [ ] Review SPOF report for all active sites
- [ ] Confirm operator policy requirements (above)
- [ ] Load real volunteer data (replace fixtures)
- [ ] Run Demo A–D with real data
- [ ] Get coordinator sign-off on approval workflow
- [ ] Document rollback procedure
