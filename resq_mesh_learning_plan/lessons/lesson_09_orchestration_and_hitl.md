# Lesson 09 — Orchestration and HITL

## Objective

Use Strands to coordinate interpretation, tools, solver, stress test, and human approval.

## Concepts to Learn

- Learn orchestration.
- Learn when one agent is enough.
- Learn HITL.
- Learn deterministic tool boundaries.

## Step-by-Step Implementation

1. Expose solver operations as narrow tools/services.
2. Build one orchestrator agent.
3. Flow: parse → validate → fetch → solve → stress-test → summarize.
4. Add explicit human approval before any execution simulation.
5. Add tool error handling.
6. Add retries only where safe.
7. Add trace/correlation IDs.
8. Avoid creating specialist agents unless needed.
9. Add an approval/rejection branch.
10. Test a complete end-to-end mission.

## Expected Result

One Strands orchestrator coordinates the full planning workflow while deterministic components retain decision authority.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 09 — Orchestration and HITL
Status: PASS / PARTIAL / BLOCKED

Files created/changed:
-

What works:
-

What I learned:
-

Current errors:
-

Questions:
-
```

## Fresh Sub-Chat Prompt

Copy everything below into a new ChatGPT chat:

---

I am building **RESQ-Mesh**, a hackathon learning project using Amazon Strands Agents SDK and Amazon Bedrock.

This is **Lesson 09: Orchestration and HITL**.

### Lesson objective
Use Strands to coordinate interpretation, tools, solver, stress test, and human approval.

### What I need to learn
- Learn orchestration.
- Learn when one agent is enough.
- Learn HITL.
- Learn deterministic tool boundaries.

### Implementation scope
1. Expose solver operations as narrow tools/services.
2. Build one orchestrator agent.
3. Flow: parse → validate → fetch → solve → stress-test → summarize.
4. Add explicit human approval before any execution simulation.
5. Add tool error handling.
6. Add retries only where safe.
7. Add trace/correlation IDs.
8. Avoid creating specialist agents unless needed.
9. Add an approval/rejection branch.
10. Test a complete end-to-end mission.

Act as a **senior agentic-AI engineer and hands-on tutor**.

Guide me incrementally. For every step:
1. explain the concept in simple terms,
2. explain what happens technically,
3. show only the code needed for this step,
4. tell me exactly which file to create/change,
5. tell me how to run it,
6. tell me what output I should expect,
7. help me debug errors before moving forward.

Important constraints:
- Do not build future lessons early.
- Do not generate the entire RESQ-Mesh application.
- Do not introduce LangGraph unless this lesson explicitly needs it.
- Do not introduce multi-agent architecture unless necessary.
- Keep deterministic rules outside the LLM.
- Never use the LLM as the optimization solver.
- Prefer small, testable code.
- Explain AWS concepts instead of assuming I already know them.
- At the end, give me a concise summary I can paste into my main project chat.

Before writing implementation code, briefly tell me what we are going to build in this lesson and why it belongs at this stage.

---
