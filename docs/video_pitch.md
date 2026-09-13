# RESQ-Mesh — Video Pitch Script (5 minutes)

> **Format:** Screen recording with voiceover. No need to appear on camera.
> **Tools:** Slides (sections 1–3), then live terminal/dashboard demo (sections 4–5), then slides (section 6).

---

## SLIDE 1 — The Hook (0:00–0:30)

**[Show: A phone buzzing with messages — "Maria cancelled", "Van 3 won't start", "Who's covering Eastside?"]**

> Every week, 60,000 community meal programs across the US face the same problem.
>
> A volunteer cancels. A van breaks down. A site lead calls in sick.
>
> The coordinator drops everything, texts ten people, reshuffles the schedule — for a problem that had an obvious answer.
>
> Meanwhile, the *real* emergencies — the ones that actually need a human decision — get buried in the noise.

---

## SLIDE 2 — The Problem (0:30–1:00)

**[Show: Split screen — Left: coordinator on phone juggling texts. Right: a list of 20 "routine" disruptions vs. 1 "real decision"]**

> Community meal coordinators spend 5 to 10 hours a week on coverage logistics.
>
> 90% of disruptions are routine — someone cancels, but there's a qualified backup available. The answer is obvious. It just takes time to find it.
>
> The other 10% are genuine crises — no backup exists, a site might go uncovered, real people might not eat.
>
> But coordinators can't tell which is which until they've worked through the whole list.
>
> What if an agent handled the routine 90% silently, and only surfaced the 10% that actually needs a human?

---

## SLIDE 3 — The Solution: RESQ-Mesh (1:00–1:45)

**[Show: Architecture diagram (docs/architecture.svg)]**

> RESQ-Mesh is an autonomous agent built with the Strands Agents SDK that does exactly that.
>
> Here's how it works:
>
> **Step 1 — Understand.** A coordinator types a natural-language request: "We need Thursday coverage at Riverside — a van driver, a packer, and a site lead." The Strands agent, powered by Amazon Bedrock, extracts structured facts. Just the facts — never a decision.
>
> **Step 2 — Decide deterministically.** Those facts flow through a rules engine that maps them to required capabilities, then into a CP-SAT constraint solver from Google OR-Tools. The solver *proves* whether coverage is feasible and picks the optimal volunteer assignment. The LLM never touches this step.
>
> **Step 3 — Stress-test.** The resilience engine removes each assigned volunteer one at a time and re-solves. Now we know exactly which single cancellation would break the plan — before it happens.
>
> **Step 4 — Monitor autonomously.** The Silent Deputy — our sentinel agent — watches for changes in the background. Volunteer cancels? It re-runs the full pipeline. If it can absorb the loss, it stays silent. If the plan breaks, it escalates to Slack — immediately, with context.

---

## SLIDE 4 — How We Use Strands Agents SDK (1:45–2:45)

**[Show: Code snippets as you narrate each one]**

> RESQ-Mesh uses Strands in three distinct agent patterns:
>
> **Pattern 1 — Structured Extraction Agent**

**[Show: `app/mission_agent.py` — the `build_agent()` function]**

```python
from strands import Agent
from strands.models.bedrock import BedrockModel

Agent(
    model=BedrockModel(model_id="us.amazon.nova-lite-v1:0", ...),
    system_prompt=SYSTEM_PROMPT,        # "extract facts only, never decide"
    structured_output_model=Mission,    # Pydantic model = guaranteed schema
)
```

> The extraction agent uses Strands' `structured_output_model` to guarantee the LLM returns a valid `Mission` object — destination, deadline, requirements, constraints. If a fact is missing, it's `null`, not hallucinated.

> **Pattern 2 — Tool-Calling ReAct Agent (The Advisor)**

**[Show: `app/advisor.py` — the `build_advisor()` function]**

```python
Agent(
    model=BedrockModel(...),
    system_prompt=ADVISOR_SYSTEM_PROMPT,  # "never decide, only call tools"
    tools=[assess_incident, get_available_resources, get_resources_by_required_capability],
)
```

> The Advisor is a Strands multi-tool agent. A coordinator asks "Can Eastside open Thursday?" — the agent calls `assess_incident`, which runs the full CP-SAT pipeline, and reports the verdict. The LLM orchestrates and explains. The deterministic tools decide.

> **Pattern 3 — Strands @tool Decorator**

**[Show: `app/tools.py` — the `@tool` decorated functions]**

```python
from strands import tool

@tool
def assess_incident(destination: str, incident_type: str, ...) -> dict:
    """Decide whether a meal site can be covered, and by whom."""
    mission = Mission(...)
    result = run_pipeline(mission, resources=list_available_resources(), ...)
    return {"verdict": result.verdict, "feasible": ..., "missing_capabilities": ...}
```

> Every `@tool` is a bridge between the LLM and a deterministic backend. The Strands SDK handles schema generation, argument parsing, and result routing. We wrote 9 tools total — from coalition planning to counterfactual failure analysis to recovery proposals.

> **The key design:** the LLM is the *interface*. The math is the *authority*. Strands makes that separation clean.

---

## SECTION 5 — Live Demo (2:45–4:15)

**[Switch to: terminal + dashboard screen recording]**

### Demo A — CLI (30 seconds)

> Let me show you RESQ-Mesh in action. First, the CLI.

```bash
python -m app.cli --demo
```

**[Show the output: extracted facts → capabilities → solver coalition → resilience report → verdict]**

> In one command: natural language in, structured facts out, deterministic solver picks the team, resilience engine identifies the single points of failure, and the verdict is "ready to deploy" or "ready but fragile."

### Demo B — The Advisor Agent (30 seconds)

```bash
python -m app.advisor "Can Riverside Eastside open Thursday?"
```

**[Show: the Strands agent calling assess_incident, then returning a plain-English answer with the verdict]**

> The coordinator doesn't need to know about solvers or hypergraphs. They ask a question in English, the Strands agent calls the right tools, and they get an operational answer.

### Demo C — The Sentinel / Silent Deputy (30 seconds)

```bash
python -m app.sentinel
```

**[Show: the sentinel processing 6 world events — 4 silent, 2 escalated]**

> Here's the sentinel running through a simulated Thursday. Six things happen — volunteers cancel, return, change capacity. Four times, the sentinel absorbs the change silently. Twice, it escalates to the coordinator because the plan actually broke. That's the hackathon theme: handle the routine, surface the real decisions.

### Demo D — Dashboard (30 seconds)

```bash
uvicorn app.api.server:app --reload
```

**[Show: browser at localhost:8000 — the MealMesh dashboard with map, presets, Sentinel replay]**

> And here's the web dashboard — pick a scenario preset, see the coverage plan, replay the sentinel's autonomous decisions. Everything runs without AWS if needed; Bedrock is used only for the NL extraction step.

---

## SLIDE 5 — Why It Matters (4:15–4:45)

**[Show: Impact slide with key numbers]**

> **Who it's for:** The 60,000+ community meal programs in the US that run on volunteer coordination.
>
> **What it saves:** 5–10 hours per week of phone-tag logistics per coordinator.
>
> **Why it's different:**
> - The LLM never makes the decision. A mathematical solver does.
> - Every plan is stress-tested *before* it's deployed.
> - The agent runs in the background — no app to open, no dashboard to check.
> - Humans only get paged when it actually matters.
>
> This isn't a chatbot that suggests volunteers. It's an autonomous agent that *proves* coverage is feasible, *proves* which failure would break it, and *only* calls a human when the math says it has to.

---

## SLIDE 6 — Closing (4:45–5:00)

**[Show: Tech stack logos — Strands, Bedrock, OR-Tools, HyperNetX, FastAPI]**

> RESQ-Mesh. Built with Strands Agents SDK. Powered by Amazon Bedrock. Decisions by math, not by language model.
>
> Because the best agent is the one you never notice — until you need it.
>
> Thank you.

---

## Recording Checklist

- [ ] Slides for sections 1–3 and 5–6 (Google Slides / Keynote / Canva)
- [ ] Terminal recordings for Demo A–C (use `asciinema` or screen record)
- [ ] Browser recording for Demo D (dashboard at localhost:8000)
- [ ] Voiceover (record in one pass or segment by segment)
- [ ] Final edit: keep under 5:00, add background music if desired
- [ ] Export as MP4, upload to YouTube/Loom/Vimeo, paste URL in Devpost

## Slide Design Notes

- Use dark theme (matches terminal demos)
- Architecture diagram: use `docs/architecture.svg` directly
- Code snippets: use a monospace font, syntax-highlighted, large enough to read
- Keep text minimal on slides — the voiceover carries the story
- End slide: include GitHub repo URL and live demo URL
