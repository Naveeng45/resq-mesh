# MealMesh — execution plan

**Hackathon:** [Agents for Humans](https://agentsforhumans.devpost.com/)  
**Track:** Good Neighbor  
**Deadline:** Monday, September 14, 2026, 5:00pm PDT  
**Prize target:** Good Neighbor Golden Agent ($5k). Grand Prize only if the video is unforgettable.  
**Status:** Plan. Do not start a second product.

This is the build plan for pivoting RESQ-Mesh to **MealMesh** without throwing away the coalition engine. Flood/EOC was the right *mechanism* and the wrong *proof*. Judges score whether the demo does real, repetitive work in the background — a Thursday pantry roster is that work; Willow Creek is a costume.

---

## 1. The product we are submitting

**One-liner:** MealMesh is the silent deputy for a community meal program. When a volunteer cancels, it restaffs from the bench. The coordinator is pinged only when a site would go uncovered — and the alert names the exact missing capability to recruit.

**Who it's for:** the one coordinator (often a volunteer themselves) who runs weekly meal sites or a food-pantry distribution: church + food bank + volunteer bench.

**Why it matters:** most texts are routine (“can't make Thursday”). A few mean a site goes dark. Attention is the scarce resource; the agent spends it only on the holes that cannot be filled.

**The clip a judge must remember:**

> Two cancels — phone stays quiet. Third cancel — “Eastside 4pm is missing a van-certified driver. Ask Jordan, or call Second Harvest.”

**Trust boundary (non-negotiable):** the LLM extracts facts (“Maya can't do Thursday Eastside”). Deterministic doctrine maps that to required capabilities. **CP-SAT assigns people.** The model never picks a volunteer.

---

## 2. What we keep vs what we swap

### Keep (do not rewrite)

| Piece | Where it lives | Why |
|---|---|---|
| CP-SAT coalition | `app/solver.py` | Decision authority |
| Resilience (remove-and-re-solve) | `app/resilience.py` | Fragile vs infeasible |
| Sentinel policy | `app/sentinel.py` (`Sentinel`, `observe`, edge-triggered escalate) | Theme fit |
| Notifications (escalations only) | `app/notifications.py` | Slack/webhook, dry-run by default |
| Orchestration + four answers | `app/orchestration.py` | CAN / HOW / WHAT IF / WHAT IS MISSING |
| Strands Advisor + tools | `app/advisor.py`, `app/tools.py` | Technical Implementation score |
| Guardrails, reliability, observability, eval | `app/guardrails.py`, `reliability.py`, `observability.py`, `eval.py` | Productionization |
| AgentCore entrypoint | `deploy/agentcore/` | Technical score boost *once launched* |
| Dashboard shell | `app/api/` | Video replay surface, not the product |

### Swap (domain costume)

| Piece | Today | MealMesh |
|---|---|---|
| Ontology | flood_access, field_triage, road_transport, communications | `van_certified_driver`, `food_handler`, `site_keyholder` |
| Catalog / map scenario | boats, med teams, trucks | volunteers + vans + sites |
| Mission fixture | Willow Creek flood | Thursday Eastside distribution |
| Sentinel timeline | lose boats, airboats arrive | volunteer cancels, bench fills, last driver drops, coordinator recruits |
| README / pitch / architecture copy | disaster EOC | community meal coverage |
| UI copy and icons | boat / medical / comms | driver / packer / lead |

### Add (this is what wins)

1. **Strands-native Sentinel** — `app/sentinel_agent.py`: a Strands agent whose tools wrap `ingest_event` / `assess_coverage` / `notify_coordinator`. CP-SAT stays inside the tool. The headline loop uses the SDK the judges score.
2. **Slack as primary UX** — coordinator channel gets warning/critical only; volunteer DM “you're up” for pre-authorized bench fills. Dashboard is for the video.
3. **Opt-in bench** — backups with `opted_in=True` may be auto-assigned (routine work). Everyone else is a recruit suggestion on escalation, not a silent assign.
4. **Second org on the same bench** — food-bank vans + church volunteers. That is the Good Neighbor proof, not a second product.
5. **Submission pack** — public repo, MIT in About, live URL, AgentCore launched, ≤5 min video, builder.aws.com post titled with “Agents for Humans”.

### Do not build (low judge ROI)

- Multi-agent swarms, routing, fuel, crew rest, full FEMA/food-bank ontology
- Auth/SSO, persistence beyond a JSON roster, HIPAA, real SMS carriers
- Keeping `resq_mesh_learning_plan/` in the submission root (move or `.gitignore` it)
- A second use case (clinic, school pickup, flood) “just in case”

---

## 3. Domain model

### Mission (reuse `app/mission.py` fields)

Map pantry language onto the existing schema so the pipeline stays intact:

| Field | MealMesh meaning | Demo value |
|---|---|---|
| `destination` | Program + flagship site | `Riverside Community Meals — Eastside` |
| `incident_type` | Recurring coverage window | `thursday_distribution` |
| `deadline` | Site open time | `2026-09-10T16:00:00-07:00` |
| `requirements` | Roles the coordinator stated | `["van driver", "packer", "site lead"]` |
| `constraints` | Hard rules | `["van certification required to drive"]` |

Critical facts stay `destination` + `incident_type`. Unknown incident types still route to human review.

### Capabilities (replace `CAPABILITY_ONTOLOGY`)

| Code | Label | Synonyms |
|---|---|---|
| `van_certified_driver` | Van-certified driver | driver, van, CDL-lite, van cert |
| `food_handler` | Food handler | packer, kitchen, food-handler card |
| `site_keyholder` | Site keyholder | site lead, key, opener, host |

**Emergent capability (hypergraph, this is why Mesh still matters):**

`meal_delivery` exists only when a coalition contains **all three**. A van without a certified driver is decoration. A packer without a keyholder cannot open Eastside. Show this in the Advisor and on the hypergraph panel.

Incident defaults: `thursday_distribution` / `meal_service` / `pantry` → all three codes.

### Roster (replace catalogs)

**Sites (demo shows Eastside live; two more exist so a cancel can be site-specific later):**

| Site | Window | Required coalition |
|---|---|---|
| Eastside (flagship) | Thu 4:00pm | 1 driver + 1 packer + 1 keyholder |
| Harbor | Thu 4:30pm | same |
| West End | Thu 5:00pm | same |

**People (synthetic, labeled as such; names are demo volunteers):**

| Id | Name | Org | Capabilities | Role in story |
|---|---|---|---|---|
| `maya` | Maya Chen | Church | driver | On Eastside. First cancel → absorbed. |
| `luis` | Luis Okonkwo | Food bank | driver | Bench, opted in. Silent fill for Maya. |
| `jordan` | Jordan Hale | Food bank | driver | **Not** opted in for Thursday. Recruit-only. |
| `priya` | Priya Shah | Church | food_handler | On Eastside. Second cancel → absorbed. |
| `sam` | Sam Ortiz | Church | food_handler | Bench, opted in. |
| `elena` | Elena Brooks | Church | keyholder | On Eastside. Stays until the end. |
| `noah` | Noah Kim | Food bank | keyholder | Bench, opted in. |

**Assets:** `van-fb-1`, `van-fb-2` (food bank). Vans are resources with `van_certified_driver` only if we treat “van + cert” as one role for v1. **v1 simplification:** a “driver” resource implies they can take a food-bank van (capacity = 1 site). Do not split van vs driver until after the demo timeline is green. Document the simplification in `docs/limitations.md`.

Add a boolean on `Resource` (or a parallel field on a thin `Volunteer` wrapper): `opted_in: bool = False`. Auto-assign only if `opted_in` and available. Jordan stays `opted_in=False` so the infeasible card can name him as someone to *ask*, not someone the agent already scheduled.

### Sentinel timeline (replace `run_sentinel_demo`)

Mirror the flood beat so existing Sentinel tests stay structurally similar:

| Step | Event | Expected action | Judge reads |
|---|---|---|---|
| 0 | Baseline Thursday Eastside staffed, bench full | silent | Watching. |
| 1 | Maya cancels (driver) | auto_recomposed → Luis | Phone quiet. |
| 2 | Priya cancels (packer) | auto_recomposed → Sam | Phone quiet. |
| 3 | Luis cancels (last opted-in driver) | **escalated warning** — plan fragile | First ping: last thread. |
| 4 | Elena cannot open (or last driver path: Luis was the last opted-in driver and no bench remains — **escalated critical**) | infeasible, missing `van_certified_driver` | “Ask Jordan or call Second Harvest.” |
| 5 | Coordinator recruits Jordan (`opted_in` flip or `resource_added`) | improved / resolved | Human did the one job only they can do. |

**Tally target:** 4 handled autonomously, 2 escalated — same ratio as today's flood demo.

Policy copy on the overlay: *Work silently. Alert a human only when a site would go uncovered.*

---

## 4. Architecture deltas

```text
Volunteer cancel / NL message
        │
        ▼
[guardrails]           unchanged
        │
        ▼
[Strands extract]      mission_agent — facts only (“who cancelled, which site”)
        │
        ▼
[Strands Sentinel]     NEW: tools call deterministic core
        │
        ├─ ingest_event          apply WorldEvent (pure)
        ├─ assess_coverage       run_pipeline (CP-SAT + resilience)
        ├─ assign_if_opted_in    only if backup opted_in (routine)
        └─ notify_coordinator    notifications.py (escalations only)
        │
        ▼
Answers + verdict + optional Slack
```

**Trust boundary holds:** Strands orchestrates and explains; tools decide.

**v1 AgentCore actions** (keep `assess` / `ask`, retarget payloads):

```json
{"action": "assess", "mission": {"destination": "Eastside", "incident_type": "thursday_distribution", "requirements": ["van driver", "packer", "site lead"]}}
{"action": "ask", "question": "What single cancel would leave Eastside uncovered?"}
```

**Dashboard:** keep the map, but retitle to sites on a real city (synthetic pins, labeled SIMULATED). Primary video path: Slack-style sentinel overlay first, map second. Rename header from “Disaster-response coalition planner” to “Community meal coverage.”

**Multi-site (stretch, after timeline is green):** one shared catalog, three `Mission`s, one Sentinel that re-runs each site on a volunteer_offline. Skip if it threatens the video. One flagship site is enough for Gold if Slack + AgentCore are real.

---

## 5. File-level work

### Must change

- `app/capabilities.py` — ontology, synonyms, incident defaults
- `app/resources.py` — roster; add `opted_in`, `org` (string is enough)
- `app/api/scenario.py` — sites/coords/icons
- `app/sentinel.py` — `build_demo_mission`, `build_demo_resources`, `run_sentinel_demo`, log header
- `app/mission_agent.py` — system prompt + demo prompt (extract cancellations/facts, never assign)
- `app/advisor.py` — system prompt + demo questions
- `app/tools.py` — tool docstrings (`assess_incident` → keep name *or* alias `assess_coverage`; don't break tests without updating them)
- `app/break_the_plan.py`, `app/cli.py`, `examples/*.json`
- `app/api/static/index.html`, `app.js`, `styles.css` (copy + icons only)
- `app/notifications.py` — escalation wording (“site uncovered”, missing role, people to ask)
- `README.md`, `docs/architecture.md`, `docs/architecture.svg`, `docs/journey.md`, `docs/limitations.md`, `docs/demo_script.md`, `docs/slos.md`
- Tests that hardcode flood/Willow Creek/boat ids (`tests/test_*.py`)

### New files

- `app/sentinel_agent.py` — Strands agent wrapping the existing `Sentinel`
- `tests/test_sentinel_agent.py`
- `docs/mealmesh-plan.md` — this file
- `examples/thursday_eastside.json` — golden coverage window

### Leave alone unless a test forces a touch

- `app/solver.py`, `app/resilience.py`, `app/orchestration.py`, `app/guardrails.py`, `app/reliability.py`, `app/observability.py`, `deploy/agentcore/Dockerfile`

### Submission hygiene

- Commit `LICENSE` (today it is untracked) and `docs/architecture.svg`
- Make GitHub **public**; set MIT in the About panel
- Move `resq_mesh_learning_plan/` out of the default clone story (subfolder `docs/learning/` or omit from the README)
- Never commit `.env` or `*_accessKeys.csv` (already gitignored)

Repo may stay named `resq-mesh` for git history. Product name in README, UI, and Devpost is **MealMesh**.

---

## 6. Nine-day calendar

Today is Saturday 5 Sep. Deadline is Monday 14 Sep 5:00pm PDT. Build in this order. If a day slips, cut stretch, not the video.

| When | Outcome (done when…) |
|---|---|
| **Sat 5 night – Sun 6** | Catalog + ontology + Eastside timeline green. `python -m app.sentinel` prints the new story. `pytest -q` green on updated goldens. No Strands work yet. |
| **Mon 7** | `sentinel_agent.py` lives. Advisor demo questions are pantry. Dashboard copy/icons swapped. Overlay tally still 4/2. |
| **Tue 8** | Slack: dry-run payloads look like coordinator cards; opted-in fill can render a volunteer “you're up” preview (even if still dry-run). |
| **Wed 9** | `agentcore configure && agentcore launch` succeeds. `assess` + `ask` invoked. Live demo URL up (App Runner / Fly / ECS — whatever is fastest). |
| **Thu 10** | Public repo, MIT About, README complete (video placeholder ok). builder.aws.com draft written. |
| **Fri 11** | Record video from `docs/demo_script.md` (rewritten). One take is enough if the Sentinel + Slack + AgentCore beats land. |
| **Sat 12** | Publish video (YouTube/Vimeo public). Publish builder.aws post with **Agents for Humans** in the title. Fill Devpost: description, architecture image, Builder ID, live URL, repo. |
| **Sun 13** | Cold-run: clone from GitHub on a clean machine, follow README, hit live URL, re-watch video. Fix only blockers. |
| **Mon 14 morning** | Freeze. Submit. Do not refactor. |

### Parallel rules

- One person: follow the table strictly.
- Two people: A owns domain + Sentinel + tests; B owns Slack + AgentCore + live URL + video/README.

---

## 7. Demo script (rewrite `docs/demo_script.md` to this)

Target **4:30**. Pitch in the first 40 seconds (required: problem, who, why).

1. **0:00–0:40** — One coordinator, six Thursday sites, a text storm. Most cancels are noise. A few mean no food at Eastside.
2. **0:40–2:00** — Autonomous Sentinel, Play timeline. Maya cancel silent. Priya cancel silent. Luis cancel → warning. Last driver gone → critical, names Jordan. Tally 4 / 2. “The language model never assigned anyone.”
3. **2:00–3:00** — Slack screenshot or live webhook: only the two escalations arrived. Optional: click a volunteer on the map to fail them live.
4. **3:00–4:00** — Advisor: “What single cancel leaves Eastside uncovered?” Show tool call `assess_coverage`. Architecture one-liner (LLM extracts, solver assigns). AgentCore invoke.
5. **4:00–4:30** — Close. All data simulated. Repo + MIT. “MealMesh keeps humans out of the routine and in the loop for the hole only they can fill.”

Fallback: entire Sentinel/eval path is offline; Bedrock only for extract/Advisor.

---

## 8. Submission checklist

Required by the official rules:

- [ ] Text description (problem, who, how)
- [ ] **Public** repo with all source, setup, README
- [ ] MIT or Apache license file, visible in GitHub About
- [ ] Architecture diagram (`docs/architecture.svg`, updated for MealMesh)
- [ ] Demo video ≤ 5 min, public YouTube/Vimeo, pitch covers problem / who / why
- [ ] AWS Builder ID
- [ ] English throughout

Score boosters:

- [ ] Live demo URL
- [ ] AgentCore actually deployed (not just `deploy/agentcore/` docs)
- [ ] builder.aws.com post(s), title contains **Agents for Humans** (up to +0.6)

Devpost track: **Good Neighbor Agents**. One prize max — do not also tick Everyday/Professional.

---

## 9. Definition of done (judge bar)

We ship only if all of these are true:

1. `python -m app.sentinel` tells the Thursday story with 4 autonomous / 2 escalated.
2. A Strands agent is on the path a judge will call “the agent” (Sentinel or Advisor+Sentinel), and CP-SAT is only reached via a tool.
3. Escalations can leave the process (Slack or webhook); silent ticks send nothing.
4. `python -m pytest -q` is green; golden scenarios cover feasible, fragile, infeasible (named missing capability), needs facts, needs review.
5. Live URL and AgentCore invoke are in the video.
6. README does not mention Willow Creek as the product. Limitations still say all operational data is simulated.
7. Learning-plan leftovers are not the first thing a clone sees.

If time dies, **cut Harbor/West End and the volunteer DM.** Do not cut: ontology swap, Sentinel timeline, Strands tool boundary, Slack escalation, AgentCore, video, public repo.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Domain swap breaks 100+ tests | Change fixtures first; keep Sentinel policy tests event-shape-based |
| Strands Sentinel becomes a chatty LLM that assigns people | Tools own assign/escalate; system prompt forbids inventing roster rows; unit-test tools without Bedrock |
| AgentCore launch burns a day | Keep `assess` fully offline; launch Wednesday; video can show local `agent_entrypoint.py` only as last resort (weaker score) |
| Slack workspace not ready | Webhook + payload preview (`python -m app.notifications`) is enough for the video; live Slack is nicer, not required |
| Temptation to keep flood “as a second demo” | One story. Flood remaining in git history is fine; not in README or video |

---

## 11. Next action

Start **§6 Saturday–Sunday**: replace ontology + roster + `run_sentinel_demo`, update goldens, get `pytest -q` green. Do not open AgentCore or the video until the Thursday timeline is the product.
