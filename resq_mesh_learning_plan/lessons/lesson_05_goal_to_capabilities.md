# Lesson 05 — Goal to Capabilities

## Objective

Use the LLM as an interpreter while keeping domain rules deterministic.

## Concepts to Learn

- Understand why LLM should extract facts but not invent operational doctrine.
- Introduce capability ontology/rules.
- Separate user intent from approved mission requirements.

## Step-by-Step Implementation

1. Create a small capability ontology.
2. Map incident facts to required capabilities using deterministic rules.
3. Let the LLM extract incident facts only.
4. Feed facts into the rules engine.
5. Produce `RequiredCapability[]`.
6. Add tests for known incident types.
7. Add a low-confidence or unknown case requiring human review.
8. Compare LLM-generated requirements vs rule-derived requirements.
9. Remove any prompt logic duplicating hard rules.
10. Document the trust boundary.

## Expected Result

The LLM interprets the incident; deterministic rules derive operational capabilities.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 05 — Goal to Capabilities
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

This is **Lesson 05: Goal to Capabilities**.

### Lesson objective
Use the LLM as an interpreter while keeping domain rules deterministic.

### What I need to learn
- Understand why LLM should extract facts but not invent operational doctrine.
- Introduce capability ontology/rules.
- Separate user intent from approved mission requirements.

### Implementation scope
1. Create a small capability ontology.
2. Map incident facts to required capabilities using deterministic rules.
3. Let the LLM extract incident facts only.
4. Feed facts into the rules engine.
5. Produce `RequiredCapability[]`.
6. Add tests for known incident types.
7. Add a low-confidence or unknown case requiring human review.
8. Compare LLM-generated requirements vs rule-derived requirements.
9. Remove any prompt logic duplicating hard rules.
10. Document the trust boundary.

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
