# Lesson 06 — CP-SAT Solver

## Objective

Create a deterministic optimizer that selects a feasible resource coalition.

## Concepts to Learn

- Learn binary decision variables.
- Learn hard constraints vs objective function.
- Understand feasibility before optimization.
- Learn why the LLM must not be the solver.

## Step-by-Step Implementation

1. Install OR-Tools.
2. Create a minimal solver module.
3. Define binary resource-selection variables.
4. Add capability coverage constraints.
5. Add capacity constraints.
6. Add availability constraints.
7. Add a simple cost or resource-count objective.
8. Return selected resources and feasibility.
9. Add infeasible test cases.
10. Explain every constraint in plain English.

## Expected Result

Given requirements and resources, CP-SAT returns a mathematically feasible coalition or `INFEASIBLE`.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 06 — CP-SAT Solver
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

This is **Lesson 06: CP-SAT Solver**.

### Lesson objective
Create a deterministic optimizer that selects a feasible resource coalition.

### What I need to learn
- Learn binary decision variables.
- Learn hard constraints vs objective function.
- Understand feasibility before optimization.
- Learn why the LLM must not be the solver.

### Implementation scope
1. Install OR-Tools.
2. Create a minimal solver module.
3. Define binary resource-selection variables.
4. Add capability coverage constraints.
5. Add capacity constraints.
6. Add availability constraints.
7. Add a simple cost or resource-count objective.
8. Return selected resources and feasibility.
9. Add infeasible test cases.
10. Explain every constraint in plain English.

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
