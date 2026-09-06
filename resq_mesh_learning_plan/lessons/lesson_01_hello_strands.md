# Lesson 01 — Hello Strands

## Objective

Create the smallest working Strands agent using Amazon Bedrock.

## Concepts to Learn

- Understand the difference between Bedrock, Strands, and AgentCore.
- Create a Python virtual environment.
- Install Strands.
- Configure AWS credentials/model access.
- Run one local Agent() invocation.
- Capture any errors and understand the request path.

## Step-by-Step Implementation

1. Create a new repository/folder named `resq-mesh`.
2. Create and activate `.venv`.
3. Install `strands-agents`.
4. Create `app/agent.py`.
5. Instantiate the smallest possible `Agent()`.
6. Send a one-sentence flood scenario.
7. Print the result.
8. Do not add tools, MCP, RAG, LangGraph, solver, or multi-agent logic.
9. Add a tiny README section explaining the flow.
10. Verify you can explain: Python → Strands → Bedrock → model → response.

## Expected Result

A local script successfully returns an LLM response through Strands and Bedrock.

## Definition of Done

- I can run the lesson artifact locally.
- I can explain the main concept without reading code.
- Deterministic behavior has tests where appropriate.
- I have not added future-lesson complexity.
- I can report changed files and current errors back to the main chat.

## Return-to-Main-Chat Report

```text
Lesson completed: 01 — Hello Strands
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

This is **Lesson 01: Hello Strands**.

### Lesson objective
Create the smallest working Strands agent using Amazon Bedrock.

### What I need to learn
- Understand the difference between Bedrock, Strands, and AgentCore.
- Create a Python virtual environment.
- Install Strands.
- Configure AWS credentials/model access.
- Run one local Agent() invocation.
- Capture any errors and understand the request path.

### Implementation scope
1. Create a new repository/folder named `resq-mesh`.
2. Create and activate `.venv`.
3. Install `strands-agents`.
4. Create `app/agent.py`.
5. Instantiate the smallest possible `Agent()`.
6. Send a one-sentence flood scenario.
7. Print the result.
8. Do not add tools, MCP, RAG, LangGraph, solver, or multi-agent logic.
9. Add a tiny README section explaining the flow.
10. Verify you can explain: Python → Strands → Bedrock → model → response.

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
