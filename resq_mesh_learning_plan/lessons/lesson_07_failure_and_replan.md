# Lesson 07 — Failure and Replan

## Objective

Make the plan survive resource loss.

## Concepts to Learn

- Learn counterfactual failure testing.
- Learn re-solving.
- Learn critical-resource detection.
- Learn missing-capability reporting.

## Step-by-Step Implementation

1. Take a feasible coalition.
2. Mark one selected resource unavailable.
3. Re-run the solver.
4. Compare original and replacement plan.
5. Repeat for every selected resource.
6. Classify failures as recoverable or mission-breaking.
7. If infeasible, report unmet capabilities.
8. Add a `replan()` service.
9. Add tests for failure scenarios.
10. Produce a simple resilience report.

## Expected Result

The system can lose a resource and either create a new feasible plan or explain exactly why it cannot.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 07 — Failure and Replan
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

This is **Lesson 07: Failure and Replan**.

### Lesson objective
Make the plan survive resource loss.

### What I need to learn
- Learn counterfactual failure testing.
- Learn re-solving.
- Learn critical-resource detection.
- Learn missing-capability reporting.

### Implementation scope
1. Take a feasible coalition.
2. Mark one selected resource unavailable.
3. Re-run the solver.
4. Compare original and replacement plan.
5. Repeat for every selected resource.
6. Classify failures as recoverable or mission-breaking.
7. If infeasible, report unmet capabilities.
8. Add a `replan()` service.
9. Add tests for failure scenarios.
10. Produce a simple resilience report.

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
