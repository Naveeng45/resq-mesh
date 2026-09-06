# RESQ-Mesh — Demo Video Script (≤ 5 minutes)

Target: **4:30**. The submission requires the pitch to cover **(1) the problem,
(2) who it's for, (3) why it matters** — those land in the first 40 seconds.
The **Sentinel** is the centerpiece, because it is what makes this an *Agent for
Humans*. Everything runs offline; the only network call is optional LLM
extraction, which falls back gracefully — so the demo never hard-fails on stage.

**Before recording:** `uvicorn app.api.server:app --reload`, open
`http://localhost:8000`, and have a terminal ready.

---

## 0:00–0:40 · The problem, who, why  *(pitch requirement)*

> "When a flood or wildfire hits, one coordinator is tracking dozens of moving
> parts — boats, medical teams, comms, roads. Most updates are routine noise. A
> few of them quietly break the rescue plan, and by the time a human notices,
> the window to act has closed.
>
> RESQ-Mesh is for those coordinators — in emergency operations centers and
> community relief groups. It's an agent that handles the routine churn silently
> and only interrupts a human when there's a real decision to make. Because in a
> disaster, attention is the scarcest resource."

On screen: the dashboard, map with resources and the Willow Creek incident.

## 0:40–2:00 · The Sentinel (the centerpiece)

Click **🛰 Autonomous Sentinel** → **▶ Play timeline**. Narrate as rows appear:

1. **Baseline** — mission feasible, redundant. *"It's watching. Silent."*
2. **First boat lost** to a landslide → `auto-recomposed`. *"A resource just
   went down. It re-planned onto a backup and stayed silent — no human needed."*
3. **Second boat lost** → **ESCALATED (warning)**. *"Now the plan is fragile —
   losing the last boat breaks it. That's a real decision, so — and only now —
   it surfaces to a human."* Point at the decision card.
4. **Last boat lost** → **ESCALATED (critical)**. *"Mission infeasible. It names
   exactly what's missing: Water Access — what you'd need to airlift or truck
   in."*
5. **Reserves arrive** → `improved` → `resolved`. *"A human sourced airboats; it
   confirmed recovery on its own."*

Point at the tally: **4 handled autonomously · 2 escalated to a human.**

> "The language model was never in this loop. A constraint solver decided every
> step."

## 2:00–3:15 · Break the plan, live on the map

Close the overlay. On the map:
- Click a **boat** → it fails; the coalition recomputes, routes redraw. *"Absorbed."*
- Click the **second boat** → verdict flips to **no feasible coalition**, and
  *WHAT IS MISSING* reads **Water Access**. *"Proven impossible — not guessed."*
- Click **Reset failures** to restore.

Optionally drag the **min-capacity** slider to show the solver reacting.

## 3:15–4:00 · The trust boundary

Show `docs/architecture.svg` (or the diagram in the README).

> "The LLM only turns natural language into facts. Everything after that —
> required capabilities, allocation, resilience — is deterministic and
> unit-tested. That's why you can trust it with a safety-critical decision."

Show the **Advisor** proving that boundary live — a Strands agent that answers in
English by *calling a deterministic tool*:

```bash
python -m app.advisor "What single failure would break a flood response in Willow Creek?"
#   🔧 tool call #1: assess_incident
#   The single resource failure ... is either `drone-02` or `med-team-alpha`.
```

> "The agent didn't decide that — it called the CP-SAT tool and reported the
> result. Built on the Strands Agents SDK, deployable to Bedrock AgentCore
> (`deploy/agentcore/`)."

Optional terminal beat:

```bash
python -m app.eval    # golden regression eval — all verdict branches pass
```

## 4:00–4:30 · Close

> "RESQ-Mesh: an agent that keeps humans out of the routine and in the loop for
> the decisions that matter. Built on the Strands Agents SDK and Amazon Bedrock,
> with a constraint solver holding the authority. All data shown is simulated."

On screen: the repo URL and the MIT license.

---

## Fallback if offline / no AWS

Everything above runs without Bedrock. Natural-language extraction falls back to
a local demo mission automatically. The Sentinel, break-the-plan, map, and eval
are all fully deterministic and offline.
