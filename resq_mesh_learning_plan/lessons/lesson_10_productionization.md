# Lesson 10 — Productionization

## Objective

Prepare the prototype for hackathon judging and credible production discussion.

## Concepts to Learn

- Learn AgentCore basics.
- Add observability.
- Add regression evaluation.
- Add security and cost controls.
- Prepare demo and architecture story.

## Step-by-Step Implementation

1. Evaluate whether to deploy the Strands agent to AgentCore Runtime.
2. Add distributed tracing / structured logs.
3. Define basic SLOs.
4. Add golden test scenarios.
5. Measure tool-call accuracy and mission-feasibility correctness.
6. Add prompt-injection defenses and strict tool schemas.
7. Add circuit-breaker/retry boundaries around external services.
8. Add model-routing only if it materially helps.
9. Build the `BREAK THE PLAN` demo.
10. Finalize README, architecture diagram, demo script, limitations, and submission assets.

## Expected Result

A demo-ready, testable, observable hackathon prototype with a clear production architecture story.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 10 — Productionization
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

This is **Lesson 10: Productionization**.

### Lesson objective
Prepare the prototype for hackathon judging and credible production discussion.

### What I need to learn
- Learn AgentCore basics.
- Add observability.
- Add regression evaluation.
- Add security and cost controls.
- Prepare demo and architecture story.

### Implementation scope
1. Evaluate whether to deploy the Strands agent to AgentCore Runtime.
2. Add distributed tracing / structured logs.
3. Define basic SLOs.
4. Add golden test scenarios.
5. Measure tool-call accuracy and mission-feasibility correctness.
6. Add prompt-injection defenses and strict tool schemas.
7. Add circuit-breaker/retry boundaries around external services.
8. Add model-routing only if it materially helps.
9. Build the `BREAK THE PLAN` demo.
10. Finalize README, architecture diagram, demo script, limitations, and submission assets.

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
