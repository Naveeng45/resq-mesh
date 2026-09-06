# Lesson 03 — Structured Mission

## Objective

Convert vague natural-language incidents into validated structured data.

## Concepts to Learn

- Learn structured output.
- Learn Pydantic models.
- Understand the probabilistic/deterministic boundary.
- Learn validation and missing-field behavior.

## Step-by-Step Implementation

1. Define a `Mission` Pydantic model.
2. Include destination, deadline, incident type, requirements, and constraints.
3. Ask the LLM to convert a natural-language flood request into this structure.
4. Reject or flag missing critical facts instead of inventing them.
5. Add 5 example inputs.
6. Test valid, ambiguous, and incomplete requests.
7. Keep all planning logic out of the LLM.
8. Store example structured missions under `examples/`.
9. Add validation tests.
10. Document which fields are LLM-extracted vs system-derived.

## Expected Result

A natural-language request reliably becomes a validated `Mission` object.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 03 — Structured Mission
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

This is **Lesson 03: Structured Mission**.

### Lesson objective
Convert vague natural-language incidents into validated structured data.

### What I need to learn
- Learn structured output.
- Learn Pydantic models.
- Understand the probabilistic/deterministic boundary.
- Learn validation and missing-field behavior.

### Implementation scope
1. Define a `Mission` Pydantic model.
2. Include destination, deadline, incident type, requirements, and constraints.
3. Ask the LLM to convert a natural-language flood request into this structure.
4. Reject or flag missing critical facts instead of inventing them.
5. Add 5 example inputs.
6. Test valid, ambiguous, and incomplete requests.
7. Keep all planning logic out of the LLM.
8. Store example structured missions under `examples/`.
9. Add validation tests.
10. Document which fields are LLM-extracted vs system-derived.

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
