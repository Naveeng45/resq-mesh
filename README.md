# resq-mesh

## Lesson 07: Failure and Replan

This lesson makes the plan survive resource loss.

Why this belongs here:

- Lesson 06 gave us a feasible coalition.
- Lesson 07 asks what happens when one of those selected resources fails.
- That’s the right time for counterfactual failure testing and deterministic replanning.

### What we build

- a `replan()` service that reruns the solver after simulated resource loss
- counterfactual tests for every selected resource in the baseline coalition
- recoverable vs mission-breaking classification
- missing-capability reporting when replanning fails
- a simple resilience report

### Files in this lesson

- `app/resilience.py` — failure simulation and resilience reporting
- `app/resilience_agent.py` — demo that prints the baseline coalition and the resilience report
- `app/pipeline.py` — shared full-demo pipeline used by the main agent
- `tests/test_resilience.py` — recoverable and mission-breaking failure tests

### Concept in simple terms

We first find a feasible coalition.
Then we pretend one selected resource disappears.
If the solver can still find a valid replacement plan, the failure is recoverable.
If not, the mission breaks and we report what capability is missing.

### What happens technically

1. The baseline solver finds a feasible coalition.
2. We clone the resource catalog and mark one selected resource unavailable.
3. We run the solver again on the modified catalog.
4. We compare the original coalition to the replacement coalition.
5. We repeat the process for every selected resource.
6. If the replacement is feasible, the failure is recoverable.
7. If the replacement is infeasible, we report the unmet capabilities.

### Assumptions

- The baseline coalition must already be feasible before replanning.
- Recovery means “the mission can still be satisfied,” even if the selected resources change.
- Mission-breaking means no feasible replacement coalition exists after the failure.
- Missing-capability reporting should be deterministic and based on the same capability ontology.

### Run the lesson tests

```bash
cd hack-projects/resq-mesh
python -m unittest tests.test_resilience -v
```

### Run the demo

```bash
cd hack-projects/resq-mesh
.venv/bin/python app/resilience_agent.py
```

### Run the combined main agent

```bash
cd hack-projects/resq-mesh
.venv/bin/python app/agent.py
```

### Start the interactive CLI

```bash
cd hack-projects/resq-mesh
bash scripts/start.sh
```

You can also pass a query directly:

```bash
bash scripts/start.sh "Flood waters have isolated Willow Creek. Send the boat and medical team."
```

### Validate everything with one command

```bash
cd hack-projects/resq-mesh
bash scripts/validate.sh
```

### Expected output

You should see:

- one recoverable failure case
- one mission-breaking failure case
- a resilience report listing the baseline coalition, replacement plans, and unmet capabilities
- the main agent showing both phases with a final end-to-end summary
- the validation script finishing with `Validation completed successfully.`
- the interactive CLI accepting a user query and running the pipeline

### If something breaks

- If the baseline solver is infeasible, check the request and the resource catalog in the demo.
- If every failure is mission-breaking, make sure there is an alternate resource for at least one selected capability.
- If unmet capabilities look wrong, verify the capability ontology codes in `app/capabilities.py`.
- If imports fail, confirm the virtual environment is active and `ortools` is installed in `.venv`.

## Lesson 05: Goal to Capabilities

This lesson turns extracted incident facts into deterministic mission requirements.

Why this belongs here:

- Lesson 03 taught us to extract structure.
- Lesson 04 taught us to keep world-state deterministic.
- Lesson 05 teaches the trust boundary between interpretation and doctrine.

### What we build

- a small capability ontology
- deterministic rules that map incident facts to required capabilities
- an LLM prompt that extracts facts only
- a comparison between LLM-extracted request terms and rule-derived requirements
- a low-confidence or unknown case that requires human review
- tests for known incident patterns

### Files in this lesson

- `app/capabilities.py` — capability ontology, deterministic rules, and comparison helpers
- `app/mission.py` — extracted incident facts model
- `app/mission_agent.py` — demo agent that prints facts, derived capabilities, and the coalition solver output
- `tests/test_capabilities.py` — rule and review tests

### Concept in simple terms

The LLM is a translator, not a commander.
It can turn a natural-language request into clean facts.
The rules engine then decides which capabilities are required.

That separation matters because operational doctrine must stay deterministic.
We do not want the model inventing response policy, choosing resources, or silently expanding the mission.

### What happens technically

1. The LLM extracts incident facts into `Mission`.
2. The extracted request terms stay as user intent, not approved doctrine.
3. `derive_required_capabilities()` in `app/capabilities.py` applies deterministic rules.
4. The rule engine produces `RequiredCapability[]` with reason text and confidence.
5. The assessment compares LLM-requested capability codes with rule-derived capability codes.
6. If the incident is unknown or the rule confidence is low, the assessment asks for human review.
7. When the mission is clear, `mission_agent.py` passes the deterministic capability codes into the CP-SAT solver.

### Trust boundary

- LLM: extract only what the user said.
- Python rules: decide what the mission requires.
- Human review: handle gaps, ambiguity, or low-confidence cases.
- Solver: choose a feasible coalition from the deterministic requirements.

### Assumptions

- `requirements` on `Mission` means explicit user-stated needs, not approved mission doctrine.
- `incident_type` is the main anchor for deterministic capability mapping.
- If the rules cannot confidently map the facts, the result should be reviewed by a human.
- This lesson keeps capability selection outside the LLM so the behavior stays testable.

### Run the lesson tests

```bash
cd hack-projects/resq-mesh
python -m unittest tests.test_capabilities -v
python -m unittest tests.test_mission -v
python -m unittest tests.test_tools -v
```

### Run the combined demo

```bash
cd hack-projects/resq-mesh
.venv/bin/python app/mission_agent.py
```

### Expected output

You should see:

- the known flood case maps to `flood_access` and `field_triage`
- the low-confidence case requires human review
- the unknown case requires human review
- the earlier mission and resource tests still pass
- the combined demo shows the extracted mission, derived capabilities, and the coalition selected by the solver

### If something breaks

- If `Mission` import errors appear, check that `app/mission.py` still exports the model the tests expect.
- If capability comparison fails, confirm the synonym mapping in `app/capabilities.py`.
- If review is not triggered for the low-confidence case, check the threshold and the review reason logic.
- If the demo script crashes, make sure the Bedrock credentials and region are configured before running `app/mission_agent.py`.

## Lesson 04: Resource Catalog

This lesson builds the deterministic world-state that a planner can query without asking the LLM to invent facts.

Why this belongs here:

- Lesson 03 taught us to keep extraction structured.
- Lesson 04 teaches us to keep world-state deterministic.
- The planner should read a resource catalog, not reason its way into fake availability or capacity.

### What we build

- `Resource` and `Capability` models
- a small synthetic resource inventory
- availability, status, reliability, location, and capacity fields
- deterministic query helpers in Python
- a Strands tool that finds resources by required capability
- tests that prove unavailable resources are excluded

### Files in this lesson

- `app/resources.py` — synthetic resource and capability catalog plus deterministic query functions
- `app/tools.py` — Strands tools that expose the catalog
- `tests/test_tools.py` — availability and capability lookup tests

### Concept in simple terms

We separate facts from reasoning.
The catalog says what exists, where it is, and whether it can be used.
The LLM should ask for those facts through tools instead of making them up.

### What happens technically

1. Python keeps the catalog in `app/resources.py`.
2. Each resource has explicit metadata like `status`, `availability`, `location`, `reliability`, and optional `capacity`.
3. A deterministic query function filters the catalog by exact capability match.
4. The Strands tool converts the internal models into JSON-serializable data.
5. Because availability filtering happens in Python, unavailable resources never reach the planner.

### Synthetic-data labeling

Every catalog record includes `synthetic_data=True`.
That label makes it clear this lesson uses mock data for learning, not live operational truth.

### Assumptions

- `availability=False` means the resource should not be used by the planner.
- `status` explains why a resource is unavailable, such as `maintenance` or `offline`.
- `capacity` is optional because not every resource has a useful numeric limit.
- Capability lookups are deterministic exact matches against the curated synthetic capability catalog.

### Setup

```bash
cd hack-projects/resq-mesh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the catalog tests

```bash
source .venv/bin/activate
python -m unittest tests.test_tools -v
```

### Expected output

You should see tests that:

- confirm the available catalog returns only usable resources
- confirm the flood-access lookup returns the available drone
- confirm the maintenance boat is excluded

### If something breaks

- `ModuleNotFoundError: pydantic` or `ModuleNotFoundError: strands` usually means the virtual environment is not active.
- If a test fails on ordering, make sure the catalog and expected output use the same deterministic order.
- If a capability lookup returns nothing, check the capability code or label spelling in `app/resources.py`.
- If a resource appears when it should be excluded, confirm both `availability` and `status` are being checked.
# Lesson 06: CP-SAT Solver

This lesson adds a deterministic optimizer that chooses a feasible coalition of resources.

Why this belongs here:

- Lesson 05 taught us to turn incident facts into deterministic requirements.
- Lesson 06 teaches us how to satisfy those requirements with a solver instead of an LLM.
- The solver must own feasibility and optimization because those are hard rules, not creative text generation.

### What we build

- binary decision variables for resource selection
- hard constraints for capability coverage, capacity, and availability
- a simple objective that minimizes the number of selected resources
- feasible and infeasible test cases
- plain-English explanations of each constraint

### Files in this lesson

- `app/solver.py` — CP-SAT request and result models plus the deterministic solver
- `tests/test_solver.py` — feasible and infeasible solver tests

### Concept in simple terms

Each resource is either selected or not selected.
The solver tries different combinations until it finds one that satisfies every hard constraint.
Only after a solution is feasible do we care about making it smaller or cheaper.

### What happens technically

1. We create one binary decision variable per resource.
2. Availability rules force unavailable resources to 0.
3. Capability coverage rules require at least one selected resource for each requested capability.
4. Capacity rules require the selected coalition to meet the requested minimum capacity.
5. The objective minimizes the number of selected resources.
6. CP-SAT returns either an optimal coalition or an infeasible result.

### Assumptions

- A resource with `availability=False` or a non-`available` status cannot be selected.
- Capability coverage is an all-required-capabilities rule, not a best-effort suggestion.
- Capacity is modeled as total selected capacity in this lesson.
- The solver only works on deterministic structured inputs and never asks the LLM to optimize.

### Setup

```bash
cd hack-projects/resq-mesh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the solver tests

```bash
source .venv/bin/activate
python -m unittest tests.test_solver -v
```

### Run the actual app demo

```bash
source .venv/bin/activate
python app/solver_agent.py
```

### Expected output

You should see:

- one test that finds the minimal feasible coalition
- one test that fails when a required capability is missing
- one test that fails when the only matching resource is unavailable
- the app demo printing the selected resource IDs, coalition size, total capacity, and solver status

### If something breaks

- If `ModuleNotFoundError: ortools` appears, reinstall dependencies with `pip install -r requirements.txt`.
- If the solver returns a different coalition than expected, check the objective and whether multiple coalitions have the same size.
- If an infeasible case unexpectedly passes, check the capability list and the availability constraint.
- If resource selection looks wrong, verify that the test data matches the solver's capacity and capability assumptions.
