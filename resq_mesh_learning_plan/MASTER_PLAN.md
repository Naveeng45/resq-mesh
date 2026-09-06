# RESQ-Mesh Hackathon Learning & Implementation Plan

## Purpose

This document is the **main-chat orchestration file** for building the RESQ-Mesh hackathon project incrementally.

Use this chat as the **main project chat** for:
- architecture decisions
- progress tracking
- integration decisions
- design reviews
- hackathon strategy
- final demo and submission planning

Use a **new sub-chat for each lesson** so implementation details do not make the main chat context unnecessarily large.

Each lesson file contains:
1. learning objective
2. concepts to understand
3. step-by-step implementation
4. expected output
5. validation checklist
6. copy/paste prompt for a fresh sub-chat

---

# Core Project Idea

RESQ-Mesh is a disaster-response planning and coordination agent.

The core engineering principle is:

**LLM understands.  
Domain rules validate.  
Hypergraph represents.  
Math solver decides.  
Resilience engine stress-tests.  
Human approves.  
Agent orchestrates.**

The LLM must not directly allocate scarce or safety-critical resources.

---

# Simple Mental Model

The system answers four questions:

1. **CAN?**  
   Can the available resources accomplish the mission?

2. **HOW?**  
   Which combination of resources should be used?

3. **WHAT IF?**  
   What happens if a resource, route, or team becomes unavailable?

4. **WHAT IS MISSING?**  
   If the mission is infeasible, which missing capability would make it feasible?

---

# Initial Demo Scenario

Start with a deliberately simple synthetic scenario:

> Three villages are affected by flooding. Given available rescue resources, determine how to deliver essential supplies.

Initial resources may include:
- rescue boat
- army truck
- medical team
- satellite communication unit
- local guide
- supply packages

All operational data used in the hackathon demo should be clearly labeled as simulated unless independently verified.

---

# Technology Stack

## AWS / Agentic Layer
- Python 3.10+
- Strands Agents SDK
- Amazon Bedrock
- AgentCore later, after local functionality works

## Deterministic Planning Layer
- Pydantic
- OR-Tools CP-SAT
- NetworkX
- HyperNetX
- NumPy / SciPy

## Optional Later
- FastAPI
- lightweight web UI
- observability/tracing
- persistence

---

# Repository Direction

```text
resq-mesh/
├── app/
│   ├── agents/
│   ├── tools/
│   ├── domain/
│   ├── solver/
│   ├── resilience/
│   ├── orchestration/
│   └── api/
├── tests/
├── docs/
├── examples/
├── requirements.txt
├── README.md
└── .gitignore
```

Do not create the full folder structure on Day 1. Grow it as lessons require.

---

# Main-Chat / Sub-Chat Working Model

## Main Chat Responsibilities

Use the main chat for:
- deciding the next lesson
- reviewing completed lesson results
- changing architecture
- tracking risks
- keeping hackathon scope under control
- integrating completed components
- preparing final architecture and demo

After completing a lesson in a sub-chat, return to the main chat with:

```text
Lesson completed:
Files created/changed:
What works:
What I learned:
Current errors:
Questions:
```

The main chat should then decide whether to:
- fix the lesson
- integrate it
- proceed to the next lesson
- change scope

---

## Sub-Chat Responsibilities

One lesson = one fresh chat.

At the beginning of the sub-chat:
1. Upload this plan or the relevant lesson file.
2. Paste the lesson prompt.
3. Keep that chat focused only on the lesson.
4. Do not redesign the entire project unless the lesson reveals a genuine architecture problem.

---

# Lesson Roadmap

| Lesson | Goal | Main Concept |
|---|---|---|
| 01 | Hello Strands | Agent + Bedrock |
| 02 | One Tool | Tool calling |
| 03 | Structured Mission | Structured output |
| 04 | Resource Catalog | Deterministic external data |
| 05 | Goal → Capabilities | LLM as interpreter |
| 06 | CP-SAT Solver | Math decides |
| 07 | Failure + Replan | Resilience |
| 08 | Hypergraph Model | Emergent capability composition |
| 09 | Orchestration + HITL | Agent coordinates |
| 10 | Productionization | AgentCore, tracing, demo |

---

# Architecture Evolution

## Stage 1

```text
User
  ↓
Strands Agent
  ↓
Amazon Bedrock
  ↓
Response
```

## Stage 2

```text
User
  ↓
Strands Agent
  ↓
Tool
  ↓
Resource Data
  ↓
Agent Response
```

## Stage 3

```text
Natural Language
  ↓
LLM
  ↓
Structured Mission
```

## Stage 4

```text
Structured Mission
  ↓
Domain Rules
  ↓
Resource Catalog
  ↓
CP-SAT Solver
  ↓
Feasible Coalition
```

## Stage 5

```text
Coalition
  ↓
Remove Resource / Route
  ↓
Re-solve
  ↓
New Coalition or Missing Capability
```

## Final

```text
User
  ↓
Strands Agent
  ↓
Incident Interpreter
  ↓
Structured Mission
  ↓
Domain Rules / Capability Ontology
  ↓
Resource Catalog
  ↓
Capability Hypergraph
  ↓
OR-Tools CP-SAT
  ↓
Candidate Coalitions
  ↓
Resilience Engine
  ↓
Human Approval
  ↓
Agent Execution / Simulation
```

---

# Non-Negotiable Engineering Rules

1. Do not let the LLM become the optimizer.
2. Do not use multi-agent architecture unless it adds clear value.
3. Keep deterministic business/safety constraints outside prompts.
4. Use structured models between probabilistic and deterministic components.
5. Every tool should have a narrow, explicit contract.
6. Add observability before calling the system production-ready.
7. Use synthetic data for high-stakes rescue scenarios.
8. Human approval remains mandatory before simulated execution.
9. Build the smallest working version before adding research complexity.
10. Every lesson must end with a testable artifact.

---

# Completion Protocol

After each lesson, record:

```text
LESSON:
STATUS: PASS / PARTIAL / BLOCKED

WORKING:
-

NOT WORKING:
-

FILES:
-

KEY LEARNING:
-

NEXT:
-
```

---

# Final Hackathon Demonstration Goal

The final demo should be understandable without explaining advanced mathematics first.

Example:

```text
Mission:
Deliver medical supplies to Village A within 3 hours.

Initial Plan:
Truck A + Medical Team + Satellite Unit
Coverage: 100%
ETA: 132 minutes

BREAK THE PLAN:
Truck A unavailable due to landslide.

System:
Original plan infeasible.
Recomposing...

New Plan:
Boat B + Truck C + Medical Team + Satellite Unit
Coverage: 100%
ETA: 164 minutes

Second Failure:
Boat B unavailable.

System:
No feasible coalition.
Missing capability:
Water transport capacity >= 500 kg
```

Only after the audience understands this should we explain:
- coalition formation
- hypergraph representation
- CP-SAT
- counterfactual node removal
- resilience metrics

---

# How to Use the Lesson Files

Open the corresponding file under `/lessons`.

Example:

```text
lessons/lesson_01_hello_strands.md
```

Copy the prompt at the bottom into a fresh ChatGPT conversation and work through only that lesson.

When completed, return to the main chat.
