# MealMesh — Contracts

## Existing Contracts (unchanged)

### Mission (app/mission.py)
```python
class Mission(CompatBaseModel):
    destination: str | None
    deadline: datetime | None
    incident_type: str | None
    requirements: list[str]
    constraints: list[str]
```

### Resource (app/resources.py)
```python
class Resource(CompatBaseModel):
    id: str
    name: str
    category: str
    location: str
    status: Literal["available", "maintenance", "offline", "busy"]
    availability: bool
    reliability: float  # [0.0, 1.0]
    capacity: int | None
    capacity_unit: str | None
    capability_codes: list[str]
    opted_in: bool
    org: str
    synthetic_data: bool = True
```

### CoalitionRequest / CoalitionSolution (app/solver.py)
```python
class CoalitionRequest(CompatBaseModel):
    required_capabilities: list[str]
    minimum_total_capacity: int = 0

class CoalitionSolution(CompatBaseModel):
    feasible: bool
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
    selected_resources: list[Resource]
    selected_resource_ids: list[str]
    selected_count: int
    total_capacity: int
    objective_value: int | None
    constraint_explanations: list[str]
    infeasible_reason: str | None
```

### OrchestrationResult (app/orchestration.py)
```python
class OrchestrationResult(CompatBaseModel):
    mission: Mission
    review: MissionReview
    capability_assessment: CapabilityAssessment
    coalition: CoalitionSolution | None
    resilience: ResilienceReport | None
    hypergraph: HypergraphReport | None
    missing_capabilities: list[str]
    verdict: str
    answers: dict[str, str]  # CAN, HOW, WHAT IF, WHAT IS MISSING
    trace_id: str | None
```

### API Endpoints (unchanged)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/scenario` | — | World state: resources, destinations, hyperedges, presets, map config |
| POST | `/api/plan` | `{mission, failed_resource_ids, min_capacity}` | `{result: OrchestrationResult, failed_resource_ids, destination}` |
| POST | `/api/extract` | `{query: str}` | `{mission, used_llm, message}` |
| POST | `/api/advisor` | `{question: str}` | `{answer, used_llm, tools, audit_summary}` |
| GET | `/api/sentinel` | `?notify=bool` | `{mission, observations, summary}` |

### Strands Tools (app/tools.py — unchanged)

```python
@tool assess_incident(destination, incident_type, requirements?, constraints?, deadline?) -> dict
@tool get_available_resources() -> dict
@tool get_resources_by_required_capability(required_capability) -> dict
```

---

## Phase 1 Contracts (NEW — app/contracts.py)

### Enumerations
```python
class PlanStatus(str, Enum): PROPOSED | APPROVED | ACTIVE | SUPERSEDED | REJECTED | COMPLETED
class ConfirmationStatus(str, Enum): PENDING | ACCEPTED | DECLINED | TIMED_OUT
class EventKind(str, Enum): RESOURCE_UNAVAILABLE | PLAN_PROPOSED | PLAN_APPROVED | ...
class DataProvenance(str, Enum): SIMULATED | OPERATOR_PROVIDED | LIVE_SYSTEM
```

### TimeWindow
```python
class TimeWindow(CompatBaseModel):
    start: datetime  # tz-aware required
    end: datetime    # tz-aware required, must be after start
```

### TravelEstimate
```python
class TravelEstimate(CompatBaseModel):
    origin_id: str
    destination_id: str
    estimated_minutes: float | None  # None iff unknown=True
    distance_km: float | None
    unknown: bool = False            # unknown + minutes → error
    provenance: DataProvenance
```

### TaskDefinition
```python
class TaskDefinition(CompatBaseModel):
    id: str
    label: str
    required_capability: str
    duration_minutes: float  # > 0
    time_window: TimeWindow | None
    depends_on: list[str]   # task IDs
```

### MissionSpec
```python
class MissionSpec(CompatBaseModel):
    id: str; version: int
    destination: str; destination_id: str
    location_coords: list[float] | None  # [lat, lng]
    mission_timezone: str                # IANA name
    service_window: TimeWindow
    deadline: datetime                   # tz-aware
    incident_type: str
    required_roles: list[str]            # capability codes
    tasks: list[TaskDefinition]
    requested_quantity: int | None
    constraints: list[str]
    permitted_start_adjustment_minutes: float
    provenance: DataProvenance
```

### VolunteerSpec
```python
class VolunteerSpec(CompatBaseModel):
    id: str; name: str
    capability_codes: list[str]
    availability_intervals: list[AvailabilityInterval]
    commitments: list[Commitment]
    authorized_site_ids: list[str]     # "*" = all
    eligible_vehicle_ids: list[str]
    opted_in: bool
    org: str
    location_label: str
    location_coords: list[float] | None
    location_updated_at: datetime | None
    travel_estimates: list[TravelEstimate]
    provenance: DataProvenance
    # Methods: is_available_during(), has_capability(), has_site_access()
```

### VehicleSpec
```python
class VehicleSpec(CompatBaseModel):
    id: str; name: str
    capacity: int          # explicit unit below
    capacity_unit: str     # e.g. "meals"
    availability_intervals: list[AvailabilityInterval]
    eligible_driver_ids: list[str]
    equipment_capabilities: list[str]
    org: str
    provenance: DataProvenance
    # Methods: is_available_during(), has_eligible_driver()
```

### PlanSpec
```python
class PlanSpec(CompatBaseModel):
    id: str; mission_id: str; version: int; input_snapshot_version: int
    assignments: list[TaskAssignment]
    violations: list[ConstraintViolation]
    is_feasible: bool
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "NOT_SOLVED"]
    objective_value: float | None
    status: PlanStatus
    proposed_at: datetime; approved_at: datetime | None; approved_by: str | None
    outstanding_confirmations: list[str]
    provenance: DataProvenance
```

### ConstraintViolation
```python
class ConstraintViolation(CompatBaseModel):
    constraint_type: str  # capability_gap, time_overlap, no_eligible_driver, site_access, ...
    description: str
    affected_resource_ids: list[str]
    affected_task_ids: list[str]
    severity: Literal["blocking", "warning"]
```

### ResourceUnavailableEvent, RecoveryProposal, ApprovalRecord, MissionEvent
See `app/contracts.py` for full definitions.

---

## Validation Rules (app/validation.py)

`validate_plan(plan, mission, volunteers, vehicles) -> list[ConstraintViolation]`

Checks:
1. ID references (tasks, volunteers, vehicles exist)
2. Capability coverage (volunteer has task's required capability)
3. Site access (volunteer authorized for mission site)
4. Volunteer availability (interval covers scheduled window)
5. Overlapping assignments (same person, overlapping times)
6. Driving/handling separation (concurrent driving + handling blocked)
7. Vehicle availability (interval covers scheduled window)
8. Vehicle driver eligibility (assigned driver is in eligible list)
9. Task dependency ordering (dependent task starts after prerequisite ends)
10. Travel time feasibility (missing/unknown travel estimates flagged)

---

## Phase 2 Contracts (NEW — app/coalition_planner.py)

### CoalitionPlannerRequest
```python
class CoalitionPlannerRequest(CompatBaseModel):
    mission: MissionSpec
    volunteers: list[VolunteerSpec]
    vehicles: list[VehicleSpec] = []
    incumbent_plan: PlanSpec | None = None     # for future min-disruption replanning
    max_alternatives: int = 3                  # 1–10
    time_limit_seconds: float = 10.0
```

### CoalitionPlannerResult
```python
class CoalitionPlannerResult(CompatBaseModel):
    feasible: bool
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
    alternatives: list[AlternativePlan] = []
    violations: list[ConstraintViolation] = []
    infeasible_reasons: list[str] = []
    solve_duration_seconds: float = 0.0
    input_snapshot: InputSnapshot | None = None
```

### AlternativePlan
```python
class AlternativePlan(CompatBaseModel):
    plan: PlanSpec
    label: str                  # "lowest_travel", "earliest_completion", "alternative_N"
    objective_value: float | None = None
    objective_description: str = ""
```

### InputSnapshot
```python
class InputSnapshot(CompatBaseModel):
    mission_id: str
    mission_version: int
    volunteer_count: int
    vehicle_count: int
    task_count: int
    opted_in_count: int
    timestamp: str
```

### API Endpoint
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/joint-plan` | `JointPlanRequest{mission, volunteers, vehicles, max_alternatives, time_limit_seconds}` | `{result: CoalitionPlannerResult, simulated: true}` |

---

## Phase 3 Contracts (NEW — app/counterfactual.py)

### BottleneckExplanation
```python
class BottleneckExplanation(CompatBaseModel):
    resource_id: str
    resource_type: Literal["volunteer", "vehicle"]
    resource_name: str
    capability_at_risk: list[str]       # capabilities uncoverable after removal
    uncovered_task_ids: list[str]       # tasks that cannot be assigned
    is_single_point_of_failure: bool
    explanation: str                     # human-readable
```

### ObjectiveDelta
```python
class ObjectiveDelta(CompatBaseModel):
    baseline_objective: float | None
    recovery_objective: float | None
    additional_travel_minutes: float | None   # simulated
    completion_delay_minutes: float | None    # simulated
    changed_assignment_count: int
```

### CounterfactualScenario
```python
class CounterfactualScenario(CompatBaseModel):
    scenario_id: str
    removed_resource_id: str
    removed_resource_type: Literal["volunteer", "vehicle"]
    removed_resource_name: str
    recovery_status: Literal["robust", "recoverable", "infeasible", "unknown"]
    mission_impact: str
    recovery_plan: PlanSpec | None
    required_replacements: list[str]    # volunteer IDs needing confirmation
    uncovered_tasks: list[str]
    infeasible_reasons: list[str]
    objective_delta: ObjectiveDelta | None
    bottleneck: BottleneckExplanation | None
    snapshot_version: int
    evaluation_timestamp: str
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
```

### CounterfactualReport
```python
class CounterfactualReport(CompatBaseModel):
    report_id: str
    mission_id: str
    baseline_plan_id: str
    snapshot_version: int
    scenarios: list[CounterfactualScenario]
    total_scenarios: int
    robust_count: int
    recoverable_count: int
    infeasible_count: int
    unknown_count: int
    single_points_of_failure: list[str]
    summary: str                        # interpretable, e.g. "Recoverable in 4 of 5..."
    evaluation_duration_seconds: float
    evaluation_timestamp: str
    provenance: DataProvenance
```

### API Endpoint
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/counterfactual` | `{mission, baseline_plan, volunteers, vehicles, resource_ids_to_test?, time_limit_seconds?}` | `{report: CounterfactualReport, simulated: true}` |

### Staleness Check
```python
is_report_stale(report: CounterfactualReport, current_mission_version: int) -> bool
```

---

## Phase 4 Contracts (NEW — app/recovery.py)

### ResourceEvent
```python
class ResourceEvent(CompatBaseModel):
    id: str                             # unique event ID
    resource_id: str
    resource_type: Literal["volunteer", "vehicle"]
    effective_time: datetime             # when resource became unavailable (tz-aware)
    observed_time: datetime              # when system learned about it (tz-aware)
    mission_id: str | None               # affected mission, if known
    source: str                          # "coordinator_report", "system_detection", etc.
    is_simulated: bool                   # simulated vs live marker
    reason: str
```

### EventIngestionResult
```python
class EventIngestionResult(CompatBaseModel):
    status: Literal["accepted", "duplicate", "stale"]
    event_id: str
    reason: str
```

### RecoveryProposalSpec
```python
class RecoveryProposalSpec(CompatBaseModel):
    id: str
    triggering_event_ids: list[str]
    original_plan_id: str
    original_plan_version: int
    mission_id: str
    expected_mission_version: int
    proposed_plan: PlanSpec
    changes: list[AssignmentChange]
    changes_count: int
    is_feasible: bool
    infeasible_reasons: list[str]
    capability_gaps: list[str]
    safe_actions: list[str]
    targeted_request: str | None
    expires_at: datetime                 # proposal TTL
    created_at: datetime
    status: Literal["pending", "approved", "expired", "rejected", "superseded"]
    provenance: DataProvenance
```

### AssignmentChange
```python
class AssignmentChange(CompatBaseModel):
    task_id: str
    task_label: str
    before_volunteer_id: str | None
    before_volunteer_name: str | None
    after_volunteer_id: str | None
    after_volunteer_name: str | None
    change_type: Literal["replaced", "removed", "added", "unchanged"]
```

### ApprovalRequest / ApprovalResult
```python
class ApprovalRequest(CompatBaseModel):
    proposal_id: str
    coordinator_id: str
    expected_plan_version: int
    expected_mission_version: int

class ApprovalResult(CompatBaseModel):
    success: bool
    status: Literal["approved", "stale", "expired", "already_approved",
                     "not_found", "reservation_conflict"]
    activated_plan: PlanSpec | None
    reason: str
```

### MissionRiskStatus
```python
class MissionRiskStatus(CompatBaseModel):
    mission_id: str
    status: Literal["nominal", "at_risk", "blocked"]
    reason: str
    pending_proposals: list[str]
    unavailable_resources: list[str]
```

### RecoveryEngine
```python
class RecoveryEngine:
    def ingest_event(event: ResourceEvent) -> EventIngestionResult
    def plan_recovery(mission, current_plan, volunteers, vehicles,
                      unavailable_resource_ids, task_statuses?,
                      triggering_event_ids?) -> RecoveryProposalSpec
    def approve_proposal(request: ApprovalRequest) -> ApprovalResult
    def record_volunteer_response(proposal_id, volunteer_id, response) -> dict
    def get_mission_risk_status(mission_id) -> MissionRiskStatus
```

### Phase 4 API Endpoints
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/recovery/event` | `{event: ResourceEvent}` | `{result: EventIngestionResult}` |
| POST | `/api/recovery/plan` | `{mission, current_plan, volunteers, vehicles, unavailable_resource_ids, ...}` | `{proposal: RecoveryProposalSpec}` |
| POST | `/api/recovery/approve` | `{proposal_id, coordinator_id, expected_plan_version, expected_mission_version}` | `{result: ApprovalResult}` |
| GET | `/api/recovery/risk/{mission_id}` | — | `{status: MissionRiskStatus}` |

### Modified: CoalitionPlannerRequest
```python
class CoalitionPlannerRequest(CompatBaseModel):
    ...
    fixed_task_ids: list[str] = []       # NEW: tasks that must keep their assignments
```

---

## Phase 5 Contracts (NEW — app/semantic_tools.py, app/semantic_orchestrator.py)

### Semantic Tools (Strands @tool decorated)

| Tool | Input | Output | Backend Service |
|---|---|---|---|
| `get_mission_context` | (none) | mission, plan, volunteer summaries, vehicle count | In-memory state |
| `validate_mission_draft` | mission_json? | valid, violations, missing_info | `validate_plan()` |
| `generate_coalition_plans` | max_alternatives?, time_limit_seconds? | feasible, alternatives, violations | `solve_coalition()` |
| `evaluate_plan_failures` | resource_ids_to_test?, time_limit_seconds? | scenarios, SPOFs, summary | `run_counterfactual_analysis()` |
| `prepare_recovery_proposal` | unavailable_resource_ids, is_simulation? | proposal_id, changes, gaps | `plan_recovery()` |
| `get_proposal_status` | proposal_id? | proposals list | In-memory state |

### Conversation State Management

```python
set_mission_context(mission, volunteers, vehicles, plan?) -> None
reset_conversation_state() -> None
get_mission_context_state() -> dict
```

### Phase 5 API Endpoints

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/semantic/context` | `{mission, volunteers, vehicles, plan?}` | `{status, mission_id, volunteer_count, ...}` |
| POST | `/api/semantic` | `{question, mission?, volunteers?, vehicles?}` | `{answer, used_llm, tools, audit_summary}` |
| POST | `/api/semantic/reset` | (none) | `{status: "reset"}` |
| GET | `/api/proposal/{proposal_id}` | — | `{proposal: RecoveryProposalSpec}` |

### System Prompt Safety Contract

The semantic orchestrator system prompt enforces:
1. Never invent resources, capabilities, ETAs, feasibility, or solver results
2. Never override infeasibility
3. Never bypass qualification, capacity, or site-access requirements
4. Never claim a plan is active unless tool returns status=APPROVED
5. A recovery proposal is NOT an active plan until approved
6. "What if X cancels?" is a SIMULATION
7. All data is SIMULATED unless stated otherwise

Tool-level enforcement is independent of prompt compliance (D-022).

---

## Phase 6 Contracts (NEW — app/mission_control.py)

### TaskView
```python
class TaskView(CompatBaseModel):
    task_id: str
    label: str
    required_capability: str
    volunteer_id: str | None
    volunteer_name: str | None
    qualification_status: Literal["qualified", "unqualified", "unassigned"]
    site_access: bool
    time_window_label: str | None
    depends_on: list[str]
    confirmation_status: str  # "pending" | "confirmed"
    is_proposed: bool         # True for recovery proposals not yet approved
```

### VolunteerView
```python
class VolunteerView(CompatBaseModel):
    id: str
    name: str
    capability_codes: list[str]
    location_label: str
    location_coords: list[float] | None
    location_stale: bool
    travel_minutes: float | None
    travel_label: str | None
    is_assigned: bool
    assigned_task_id: str | None
    is_spof: bool
    opted_in: bool
    is_proposed: bool
```

### RecoveryView
```python
class RecoveryView(CompatBaseModel):
    proposal_id: str | None
    is_feasible: bool
    what_changed: str
    unchanged_assignments: list[str]
    changes: list[dict]
    capability_gaps: list[str]
    safe_actions: list[str]
    targeted_request: str | None
    pending_confirmations: list[str]
    requirements_satisfied: bool
    expires_label: str | None
```

### MissionControlPayload
```python
class MissionControlPayload(CompatBaseModel):
    mission_id: str
    mission_label: str
    deadline_label: str
    plan_status: str
    roles_covered: int
    roles_required: int
    tasks_at_risk: int
    recovery_summary: str
    tasks: list[TaskView]
    volunteers: list[VolunteerView]
    destination_coords: list[float] | None
    destination_label: str
    single_points_of_failure: list[str]
    counterfactual_scenarios: list[dict]
    recovery: RecoveryView | None
    risk_status: str          # nominal | at_risk | blocked
    risk_reason: str
    simulated: bool
    provenance: str
```

### Phase 6 API Endpoints

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/mission-control` | `{mission, volunteers, vehicles, plan?}` | `MissionControlPayload` |
| POST | `/api/mission-control/simulate-removal` | `{mission, volunteers, vehicles, plan, removed_resource_ids}` | `MissionControlPayload` with recovery |
| GET | `/api/mission-control/fixture` | — | `MissionControlPayload` + `_raw_*` for round-trips |
| GET | `/mission-control` | — | HTML page |

---

## Proposed Extension Points (Phase 7+)

### New Strands Tools (proposed)

| Tool | Phase | Purpose |
|---|---|---|
| `assess_joint_coverage` | 7 | Run joint solver across all sites |
| `simulate_cancellation` | 7 | Remove a volunteer, return min-change replan |
