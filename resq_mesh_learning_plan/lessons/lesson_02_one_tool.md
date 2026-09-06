# Lesson 02 — One Tool

## Objective

Teach the agent to invoke one deterministic Python tool.

## Concepts to Learn

- Understand what makes an LLM application agentic.
- Learn tool registration.
- Learn how the model decides to call a tool.
- Understand tool input/output contracts.

## Step-by-Step Implementation

1. Create a tiny in-memory resource catalog.
2. Add 3 resources: truck, boat, medical team.
3. Implement exactly one tool: `get_available_resources`.
4. Expose it to the Strands agent.
5. Ask a question that requires resource data.
6. Observe whether the agent invokes the tool.
7. Add logging around the tool.
8. Add a unit test for the deterministic tool itself.
9. Do not let the tool perform planning.
10. Document the agent/tool execution sequence.

## Expected Result

The agent calls one deterministic resource tool and uses the returned data in its answer.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 02 — One Tool
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

This is **Lesson 02: One Tool**.

### Lesson objective
Teach the agent to invoke one deterministic Python tool.

### What I need to learn
- Understand what makes an LLM application agentic.
- Learn tool registration.
- Learn how the model decides to call a tool.
- Understand tool input/output contracts.

### Implementation scope
1. Create a tiny in-memory resource catalog.
2. Add 3 resources: truck, boat, medical team.
3. Implement exactly one tool: `get_available_resources`.
4. Expose it to the Strands agent.
5. Ask a question that requires resource data.
6. Observe whether the agent invokes the tool.
7. Add logging around the tool.
8. Add a unit test for the deterministic tool itself.
9. Do not let the tool perform planning.
10. Document the agent/tool execution sequence.

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
