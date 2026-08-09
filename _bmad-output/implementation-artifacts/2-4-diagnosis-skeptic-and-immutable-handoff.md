# Story 2.4: Diagnosis Skeptic & Immutable Handoff

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want every diagnosis to survive adversarial challenge before I act on it,
so that I can trust the system's conclusions are robust, not hallucinated or incomplete.

## Acceptance Criteria

1. **Given** the Orchestrator produces a Structured Diagnosis Object that passes the completeness gate **When** it is submitted to the Diagnosis Skeptic **Then** the Skeptic produces a structured challenge containing: alternative hypotheses, evidence gaps, and logical weaknesses in the diagnosis

2. **Given** the Skeptic has issued a challenge **When** the Orchestrator responds to the challenge **Then** the response addresses each point in the challenge with evidence or reasoning

3. **Given** the Orchestrator's response to the Skeptic challenge **When** the root-cause hash is compared before and after the challenge response **Then** if the hash is unchanged, the diagnosis passes validation

4. **Given** the root-cause hash changes after the first challenge **When** the diagnosis is fundamentally altered **Then** the new diagnosis is re-challenged exactly one additional round **And** after the second round, the diagnosis passes regardless of hash change (no infinite loops)

5. **Given** the Skeptic challenge and response **When** the validation completes **Then** both the challenge and response are persisted as part of the incident's audit trail

6. **Given** a diagnosis that passes Skeptic validation **When** it is finalized **Then** it becomes an Immutable Diagnosis Artifact — a read-only object that is persisted for audit and cannot be modified

7. **Given** an Immutable Diagnosis Artifact **When** it crosses the RBAC Airlock to the remediation side **Then** the remediation planner receives it as read-only input and cannot re-diagnose, re-interpret, or modify any field

8. **Given** the Skeptic must evaluate a diagnosis with non-empty `evidence_gaps` **When** it reviews the diagnosis **Then** it explicitly challenges the evidence gaps as a required part of its structured challenge

9. **Given** the diagnosis passes Skeptic validation **When** the incident state is updated **Then** it transitions from `diagnosing` to `diagnosed` via the state machine function

## Tasks / Subtasks

- [ ] Task 1: Skeptic-related Pydantic models (AC: #1, #2, #5)
  - [ ] 1.1 Create `backend/src/models/skeptic.py` with `SkepticChallenge`, `SkepticResponse`, `SkepticVerdict` Pydantic models
  - [ ] 1.2 `SkepticChallenge` fields: `alternative_hypotheses: list[str]`, `evidence_gap_challenges: list[str]`, `logical_weaknesses: list[str]`, `overall_assessment: str`, `created_at: datetime`
  - [ ] 1.3 `SkepticResponse` fields: `rebuttals: list[SkepticRebuttal]`, `revised_diagnosis: DiagnosisObject | None`, `summary: str`, `created_at: datetime`
  - [ ] 1.4 `SkepticVerdict` fields: `passed: bool`, `rounds_completed: int`, `original_hash: str`, `final_hash: str`, `challenge_history: list[dict]`, `verdict_reasoning: str`
  - [ ] 1.5 Export from `backend/src/models/__init__.py`

- [ ] Task 2: Skeptic agent implementation (AC: #1, #2, #8)
  - [ ] 2.1 Create `backend/src/agents/skeptic.py` with `run_skeptic(diagnosis: DiagnosisObject, state: DiagnosisState) -> SkepticChallenge`
  - [ ] 2.2 Build skeptic as a LangGraph `create_react_agent` subgraph with `response_format=SkepticChallenge`
  - [ ] 2.3 System prompt: require mandatory challenge of every `evidence_gaps` entry, identify alternative root causes, find logical gaps in the causal chain
  - [ ] 2.4 Create `backend/src/agents/prompts.py` — add `SKEPTIC_SYSTEM_PROMPT` (extend existing prompts file from 2.2)

- [ ] Task 3: Orchestrator rebuttal function (AC: #2)
  - [ ] 3.1 Add `run_orchestrator_rebuttal(diagnosis: DiagnosisObject, challenge: SkepticChallenge, state: DiagnosisState) -> SkepticResponse` to `backend/src/agents/orchestrator.py`
  - [ ] 3.2 Rebuttal uses same tools as orchestrator (MCP cluster query, runbook RAG) to gather additional evidence
  - [ ] 3.3 If the orchestrator agrees with a challenge point, it may revise the diagnosis — return revised `DiagnosisObject` in the response

- [ ] Task 4: Skeptic validation loop with hash comparison (AC: #3, #4)
  - [ ] 4.1 Create `backend/src/pipeline/skeptic_validation.py` with `run_skeptic_validation(diagnosis: DiagnosisObject, state: DiagnosisState) -> tuple[DiagnosisObject, SkepticVerdict]`
  - [ ] 4.2 Implement hash-based loop: compare `root_cause_hash()` before and after each round
  - [ ] 4.3 If hash unchanged after round 1 → pass immediately
  - [ ] 4.4 If hash changed after round 1 → run exactly one more round, then pass regardless
  - [ ] 4.5 Return final (possibly revised) `DiagnosisObject` and `SkepticVerdict`

- [ ] Task 5: Immutable Diagnosis Artifact sealing (AC: #6, #7)
  - [ ] 5.1 The `ImmutableDiagnosisArtifact` model already exists in `models/diagnosis.py` (created by 2.1) — verify it is frozen (Pydantic `model_config = ConfigDict(frozen=True)`)
  - [ ] 5.2 Create `seal_diagnosis(diagnosis: DiagnosisObject, verdict: SkepticVerdict) -> ImmutableDiagnosisArtifact` in `backend/src/pipeline/skeptic_validation.py` — copies diagnosis fields into the frozen model with the skeptic verdict attached
  - [ ] 5.3 Ensure sealed artifact includes `sealed_at: datetime`, `skeptic_verdict: SkepticVerdict`, and all original DiagnosisObject fields

- [ ] Task 6: Integrate skeptic into diagnosis graph (AC: #3, #4, #9)
  - [ ] 6.1 Update `backend/src/pipeline/diagnosis_graph.py` — add `skeptic_validation` node between completeness gate and `finalize`
  - [ ] 6.2 Add `DiagnosisState` fields: `skeptic_challenge: dict | None`, `skeptic_verdict: dict | None`, `immutable_artifact: dict | None`
  - [ ] 6.3 Wire edges: completeness gate pass → `skeptic_validation` → `finalize`
  - [ ] 6.4 `finalize` node: seal the diagnosis into `ImmutableDiagnosisArtifact`, transition incident state `diagnosing→diagnosed`, persist artifact, emit SSE event

- [ ] Task 7: Audit trail persistence (AC: #5)
  - [ ] 7.1 Create `backend/src/db/skeptic.py` with `persist_skeptic_record(conn, incident_id, challenge, response, verdict)`
  - [ ] 7.2 Persist full challenge/response/verdict JSON to a `skeptic_reviews` table
  - [ ] 7.3 Create Alembic migration for `skeptic_reviews` table: `id UUID PK, incident_id UUID FK, round_number INT, challenge JSONB, response JSONB, verdict JSONB, created_at TIMESTAMPTZ`
  - [ ] 7.4 Write audit_log entry via `write_audit_log()` from `db/audit.py` for each skeptic round completion

- [ ] Task 8: Immutable artifact persistence (AC: #6, #7)
  - [ ] 8.1 Create `backend/src/db/diagnosis.py` with `persist_immutable_diagnosis(conn, artifact: ImmutableDiagnosisArtifact)`
  - [ ] 8.2 Create Alembic migration for `immutable_diagnoses` table: `id UUID PK, incident_id UUID FK UNIQUE, diagnosis JSONB NOT NULL, skeptic_verdict JSONB NOT NULL, sealed_at TIMESTAMPTZ, created_at TIMESTAMPTZ`
  - [ ] 8.3 The serialized artifact is the handoff object for Epic 3 (remediation planner reads from this table)

- [ ] Task 9: Tests — unit (AC: #1, #2, #3, #4, #5, #6, #8)
  - [ ] 9.1 `tests/models/test_skeptic.py` — SkepticChallenge, SkepticResponse, SkepticVerdict validation, serialization
  - [ ] 9.2 `tests/agents/test_skeptic.py` — skeptic produces valid structured challenge with mocked LLM, evidence gaps are always challenged
  - [ ] 9.3 `tests/pipeline/test_skeptic_validation.py` — hash unchanged → pass in 1 round; hash changed → max 2 rounds then pass; evidence_gaps mandate challenge
  - [ ] 9.4 `tests/models/test_diagnosis.py` — extend: ImmutableDiagnosisArtifact is truly frozen (raises on mutation), seal_diagnosis copies all fields correctly

- [ ] Task 10: Tests — pipeline integration (AC: #3, #4, #9)
  - [ ] 10.1 `tests/pipeline/test_diagnosis_graph.py` — update graph tests: full path `diagnose→completeness→skeptic→finalize` with mocked LLM, state transitions `queued→diagnosing→diagnosed`
  - [ ] 10.2 `tests/pipeline/test_diagnosis_graph.py` — re-challenge path: skeptic changes hash → second round → diagnosed
  - [ ] 10.3 `tests/pipeline/test_diagnosis_graph.py` — verify ImmutableDiagnosisArtifact is in final state, verify skeptic_reviews persisted
  - [ ] 10.4 `tests/db/test_skeptic.py` — persist_skeptic_record and persist_immutable_diagnosis roundtrip (testcontainers)

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 2.1 (LangGraph Diagnosis Pipeline & MCP Integration):**

Story 2.1 established the pipeline infrastructure this story extends:

- **`pipeline/diagnosis_graph.py`** — LangGraph `StateGraph` with `DiagnosisState` TypedDict. The graph defines nodes and edges for the diagnosis flow. The `finalize` node handles state transitions and SSE event emission. This story adds the `skeptic_validation` node between the completeness gate and `finalize`.
- **`models/diagnosis.py`** — `DiagnosisObject`, `EvidenceArtifact`, `EvidenceGap`, `ImmutableDiagnosisArtifact`, `EvidenceSource` enum, root-cause taxonomy. The `root_cause_hash()` method on `DiagnosisObject` is the deterministic comparison used by the skeptic loop.
- **`pipeline/mcp_client.py`** — `ReadOnlyMCPClient` for cluster queries. The orchestrator rebuttal uses this to gather additional evidence.
- **`pipeline/runner.py`** — Pipeline runner invoking the graph. No changes needed for this story.
- **`pipeline/audit_hook.py`** — LangGraph callback writing state transitions to `audit_log`. Skeptic rounds will be captured by this hook.
- **`db/checkpointer.py`** — `AsyncPostgresSaver` for LangGraph checkpoints. Skeptic state is automatically checkpointed.

**Critical patterns from 2.1 this story MUST follow:**
- `DiagnosisState` TypedDict is the graph state — extend with new fields (defaults required)
- `root_cause_hash()` is deterministic: same `root_cause_component + failure_mode + sorted causal_chain` → same hash
- MCP timeout → `EvidenceGap`, never an exception (AD-15)
- Two separate DB pools: asyncpg (application) and psycopg (LangGraph checkpoints)
- State transitions via `transition()` from `models/state_machine.py`

**From Story 2.2 (Orchestrator Agent & Runbook-Enriched Diagnosis):**

Story 2.2 built the orchestrator and completeness gate that this story's skeptic challenges:

- **`agents/orchestrator.py`** — `build_orchestrator_agent()` using `create_react_agent` with tools and `response_format=DiagnosisObject`. `run_orchestrator(state)` produces the diagnosis. This story adds `run_orchestrator_rebuttal()` — same agent/tools but with challenge context injected.
- **`agents/tools.py`** — LangChain `@tool` functions: `query_cluster_resources`, `get_resource_logs`, `search_runbooks`. The rebuttal function reuses these tools to gather additional evidence.
- **`agents/completeness_gate.py`** — `evaluate_completeness(diagnosis, rce_alerts)` returns `CompletenessResult`. The skeptic fires AFTER the completeness gate passes.
- **`agents/llm_client.py`** — `get_chat_model(role: AgentRole)` factory. The skeptic uses `AgentRole.SKEPTIC` for a separate LLM config.
- **`agents/prompts.py`** — System prompts for the orchestrator. This story adds `SKEPTIC_SYSTEM_PROMPT`.
- **`config/llm_settings.py`** — `AgentLLMConfig`, `AgentRole` enum. `AgentRole.SKEPTIC` already defined.
- **`knowledge/runbook_rag.py`** — RAG retrieval. Available for rebuttal tool use.

**Critical patterns from 2.2 this story MUST follow:**
- Agents are LangGraph `create_react_agent` subgraphs invoked INSIDE pipeline nodes (AD-1)
- `AgentRole.SKEPTIC` config loaded from env vars: `LLM_SKEPTIC_ENDPOINT`, `LLM_SKEPTIC_MODEL`, `LLM_SKEPTIC_TEMPERATURE`
- `FakeChatModel` fixture in `tests/agents/conftest.py` for mocked LLM tests
- Orchestrator already handles multiple tool calls in a ReAct loop — rebuttal follows the same pattern

**From Epic 1 (all stories complete — code reviewed and merged):**
- State machine in `models/state_machine.py` — `transition(current, target)`, `diagnosing→diagnosed` is a valid transition
- Event bus: `event_bus.emit(EventNames.INCIDENT_STAGE_CHANGED, SSEEventData(...))`
- Audit log: `write_audit_log(conn, actor=..., action=..., target_resource=..., detail=...)`
- Structured logging: `logger = get_logger(Component.AGENT)` or `Component.PIPELINE`
- DB operations in `db/` module — never inline SQL
- Test markers: `unit`, `db`, `api`, `pipeline`
- Testcontainers PostgreSQL + pgvector fixture in `conftest.py`

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-1 | Agents internal to stages | Skeptic is an agent in `agents/skeptic.py`, invoked by the `skeptic_validation` node in `pipeline/`. It is NOT a pipeline-level graph node — it runs inside one |
| AD-2 | RBAC Airlock | The `ImmutableDiagnosisArtifact` is THE object that crosses the RBAC boundary. Remediation (Epic 3) receives it read-only. The skeptic operates on the diagnosis side — `cluster-reader` SA only |
| AD-4 | Shared types module | `SkepticChallenge`, `SkepticResponse`, `SkepticVerdict` defined in `models/skeptic.py`. `ImmutableDiagnosisArtifact` already in `models/diagnosis.py` |
| AD-15 | MCP timeout → evidence_gaps | Skeptic MUST explicitly challenge every entry in `evidence_gaps`. This is a hard requirement in the system prompt, not optional |
| AD-19 | Canonical state machine | `diagnosing→diagnosed` transition after skeptic passes. No new states added |
| AD-24 | In-process event bus | Skeptic completion emits `incident.stage_changed` event with skeptic verdict payload |
| AD-25 | Audit log | Skeptic challenge/response persisted via `write_audit_log()` (write point #2 from pipeline audit hook) AND to dedicated `skeptic_reviews` table for structured querying |

### Technical Requirements

#### Skeptic Agent Architecture

The skeptic is a LangGraph `create_react_agent` subgraph — same pattern as the orchestrator in 2.2. It receives the `DiagnosisObject` and produces a structured `SkepticChallenge`:

```python
from langgraph.prebuilt import create_react_agent

def build_skeptic_agent(llm: BaseChatModel) -> CompiledStateGraph:
    return create_react_agent(
        model=llm,
        tools=[],  # Skeptic has NO tools — it reasons over the diagnosis only
        prompt=SKEPTIC_SYSTEM_PROMPT,
        response_format=(SKEPTIC_STRUCTURED_PROMPT, SkepticChallenge),
    )
```

The skeptic has NO tools — it does not query the cluster or search runbooks. Its role is adversarial review of the diagnosis artifact only. This is a deliberate design: the skeptic challenges based on the evidence presented, not by gathering new evidence.

#### Skeptic System Prompt

```python
SKEPTIC_SYSTEM_PROMPT = """You are an adversarial reviewer of OpenShift cluster diagnoses.
Your purpose is to find weaknesses, gaps, and errors in the diagnosis before it is acted upon.

You receive a Structured Diagnosis Object and MUST produce a structured challenge.

MANDATORY REQUIREMENTS:
1. For EVERY entry in evidence_gaps, produce a specific challenge about what the missing evidence could change about the conclusion
2. Identify at least one alternative root cause that the evidence could also support
3. Evaluate the causal chain for logical gaps — are there unexplained jumps?
4. Assess whether confidence score is justified by the evidence strength
5. Challenge any evidence that is circumstantial rather than definitive

RULES:
- Be adversarial but constructive — your goal is to strengthen the diagnosis, not block it
- Cite specific evidence artifacts when challenging claims
- Every challenge must be actionable — the orchestrator must be able to address it
- Focus on the STRONGEST objection, not every possible nitpick
"""
```

#### Orchestrator Rebuttal

The rebuttal is a separate invocation of the orchestrator agent with the challenge injected into context:

```python
async def run_orchestrator_rebuttal(
    diagnosis: DiagnosisObject,
    challenge: SkepticChallenge,
    state: DiagnosisState,
) -> SkepticResponse:
    """Orchestrator responds to skeptic challenge, possibly revising the diagnosis."""
    llm = get_chat_model(AgentRole.ORCHESTRATOR)
    tools = build_orchestrator_tools(state)
    agent = build_orchestrator_agent(llm, tools)

    prompt = build_rebuttal_prompt(diagnosis, challenge, state)
    result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})

    revised_diagnosis = result.get("structured_response")
    return SkepticResponse(
        rebuttals=[...],
        revised_diagnosis=revised_diagnosis if hash_changed else None,
        summary=result["messages"][-1].content,
    )
```

The orchestrator rebuttal CAN use tools (MCP cluster queries, runbook search) to gather additional evidence to refute the challenge. If it agrees with the challenge, it produces a revised `DiagnosisObject` — this is what triggers the hash comparison.

#### Skeptic Validation Loop

```python
async def run_skeptic_validation(
    diagnosis: DiagnosisObject,
    state: DiagnosisState,
) -> tuple[DiagnosisObject, SkepticVerdict]:
    """Run the skeptic challenge/response loop with hash-based termination."""
    original_hash = diagnosis.root_cause_hash()
    current_diagnosis = diagnosis
    challenge_history = []
    max_rounds = 2

    for round_num in range(1, max_rounds + 1):
        challenge = await run_skeptic(current_diagnosis, state)

        response = await run_orchestrator_rebuttal(
            current_diagnosis, challenge, state
        )

        challenge_history.append({
            "round": round_num,
            "challenge": challenge.model_dump(),
            "response": response.model_dump(),
        })

        if response.revised_diagnosis is not None:
            current_diagnosis = response.revised_diagnosis

        current_hash = current_diagnosis.root_cause_hash()

        if current_hash == original_hash:
            break  # Hash unchanged — diagnosis stable

        if round_num == 1:
            original_hash = current_hash  # Reset for round 2 comparison
            continue  # One more round

    verdict = SkepticVerdict(
        passed=True,  # Always passes after max rounds
        rounds_completed=len(challenge_history),
        original_hash=diagnosis.root_cause_hash(),
        final_hash=current_diagnosis.root_cause_hash(),
        challenge_history=challenge_history,
        verdict_reasoning="...",
    )

    return current_diagnosis, verdict
```

Key constraints:
- **Max 2 rounds** — no infinite loops (AD: "NEVER allow more than one re-challenge")
- **Round 1**: if hash unchanged → pass. If hash changed → go to round 2.
- **Round 2**: pass regardless of hash change.
- The `SkepticVerdict.passed` is always `True` after the loop completes — the verdict records what happened, not whether to proceed.

#### ImmutableDiagnosisArtifact Sealing

```python
def seal_diagnosis(
    diagnosis: DiagnosisObject,
    verdict: SkepticVerdict,
) -> ImmutableDiagnosisArtifact:
    """Freeze the diagnosis into an immutable artifact for handoff."""
    return ImmutableDiagnosisArtifact(
        **diagnosis.model_dump(),
        skeptic_verdict=verdict,
        sealed_at=datetime.now(timezone.utc),
    )
```

The `ImmutableDiagnosisArtifact` model (from 2.1) uses `model_config = ConfigDict(frozen=True)`. After sealing:
- No field can be modified (`FrozenInstanceError` on attribute assignment)
- The object is persisted to `immutable_diagnoses` table as JSONB
- Epic 3's remediation planner reads from this table — it receives the artifact read-only

#### DiagnosisState Extension

```python
class DiagnosisState(TypedDict):
    incident_id: str
    root_cause_event: dict
    alerts: list[dict]
    mcp_evidence: list[dict]
    evidence_gaps: list[dict]
    diagnosis: dict | None
    stage: str
    # From 2.2:
    runbook_context: list[dict]
    completeness_attempts: int
    coverage_gaps: list[str]
    rejected_hypotheses: list[dict]
    # New fields for 2.4:
    skeptic_challenge: dict | None
    skeptic_verdict: dict | None
    immutable_artifact: dict | None
```

Add new fields with `None` defaults so existing graph invocations don't break.

#### Graph Update — Adding the Skeptic Node

The diagnosis graph after this story:

```
entry → diagnose (orchestrator) → completeness_gate
                                     ↓ pass
                               skeptic_validation
                                     ↓
                                  finalize → END
                                     
completeness_gate ↓ fail → re-diagnose (max 2) → completeness_gate
```

```python
builder.add_node("diagnose", diagnose_node)
builder.add_node("skeptic_validation", skeptic_validation_node)
builder.add_node("finalize", finalize_node)

builder.set_entry_point("diagnose")
builder.add_conditional_edges("diagnose", completeness_check, {
    "pass": "skeptic_validation",
    "retry": "diagnose",
})
builder.add_edge("skeptic_validation", "finalize")
builder.add_edge("finalize", END)
```

The `skeptic_validation_node` calls `run_skeptic_validation()` and stores the result in state:

```python
async def skeptic_validation_node(state: DiagnosisState) -> dict:
    diagnosis = DiagnosisObject(**state["diagnosis"])
    final_diagnosis, verdict = await run_skeptic_validation(diagnosis, state)
    
    sealed = seal_diagnosis(final_diagnosis, verdict)
    
    return {
        "diagnosis": final_diagnosis.model_dump(),
        "skeptic_verdict": verdict.model_dump(),
        "immutable_artifact": sealed.model_dump(),
    }
```

#### Database Tables

**`skeptic_reviews` table:**
```sql
CREATE TABLE skeptic_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    round_number INTEGER NOT NULL,
    challenge JSONB NOT NULL,
    response JSONB NOT NULL,
    verdict JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(incident_id, round_number)
);

CREATE INDEX idx_skeptic_reviews_incident ON skeptic_reviews(incident_id);
```

**`immutable_diagnoses` table:**
```sql
CREATE TABLE immutable_diagnoses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
    diagnosis JSONB NOT NULL,
    skeptic_verdict JSONB NOT NULL,
    sealed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_immutable_diagnoses_incident ON immutable_diagnoses(incident_id);
```

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ~=1.2 | Already in pyproject.toml. Skeptic subgraph via `create_react_agent`, graph node addition |
| langchain-openai | latest | Already in pyproject.toml (added in 2.2). `ChatOpenAI` for Skeptic LLM calls |
| langchain-core | (transitive) | Already a transitive dep. `BaseChatModel`, `HumanMessage` |
| asyncpg | latest | Already in pyproject.toml. Skeptic review and immutable diagnosis persistence |
| pydantic | latest | Already in pyproject.toml. `SkepticChallenge`, `SkepticResponse`, `SkepticVerdict` models |

**No new dependencies required.** All needed packages were added in Stories 2.1 and 2.2.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/models/skeptic.py` | `SkepticChallenge`, `SkepticResponse`, `SkepticRebuttal`, `SkepticVerdict` Pydantic models | NEW |
| `backend/src/agents/skeptic.py` | Skeptic agent — `build_skeptic_agent()`, `run_skeptic()` | NEW |
| `backend/src/pipeline/skeptic_validation.py` | Validation loop with hash comparison, `seal_diagnosis()` | NEW |
| `backend/src/db/skeptic.py` | `persist_skeptic_record()` — writes to `skeptic_reviews` table | NEW |
| `backend/src/db/diagnosis.py` | `persist_immutable_diagnosis()` — writes to `immutable_diagnoses` table | NEW |
| `backend/alembic/versions/xxx_add_skeptic_reviews.py` | Migration: `skeptic_reviews` table | NEW |
| `backend/alembic/versions/xxx_add_immutable_diagnoses.py` | Migration: `immutable_diagnoses` table | NEW |
| `backend/tests/models/test_skeptic.py` | Skeptic model validation/serialization tests | NEW |
| `backend/tests/agents/test_skeptic.py` | Skeptic agent unit tests (mocked LLM) | NEW |
| `backend/tests/pipeline/test_skeptic_validation.py` | Validation loop unit tests (mocked agents) | NEW |
| `backend/tests/db/test_skeptic.py` | DB persistence roundtrip tests (testcontainers) | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/pipeline/diagnosis_graph.py` | Add `skeptic_validation` node, wire edges after completeness gate | UPDATE |
| `backend/src/agents/orchestrator.py` | Add `run_orchestrator_rebuttal()` function | UPDATE |
| `backend/src/agents/prompts.py` | Add `SKEPTIC_SYSTEM_PROMPT`, `SKEPTIC_STRUCTURED_PROMPT`, `REBUTTAL_PROMPT_TEMPLATE` | UPDATE |
| `backend/src/models/__init__.py` | Export `SkepticChallenge`, `SkepticResponse`, `SkepticVerdict` | UPDATE |
| `backend/tests/pipeline/test_diagnosis_graph.py` | Update graph tests: full path including skeptic, re-challenge path | UPDATE |

### Dependency Direction (ENFORCED)

```
models/skeptic.py → models/diagnosis.py (DiagnosisObject for type refs)
agents/skeptic.py → agents/llm_client.py (get_chat_model), models/ (SkepticChallenge, DiagnosisObject)
agents/orchestrator.py → agents/tools.py, agents/llm_client.py, models/ (rebuttal function)
pipeline/skeptic_validation.py → agents/skeptic.py, agents/orchestrator.py, models/ (DiagnosisObject, ImmutableDiagnosisArtifact, SkepticVerdict)
pipeline/diagnosis_graph.py → pipeline/skeptic_validation.py (new node)
db/skeptic.py → models/skeptic.py (for types), db/audit.py (write_audit_log)
db/diagnosis.py → models/diagnosis.py (ImmutableDiagnosisArtifact)
```

- **NEVER**: `models/` imports from `agents/`, `pipeline/`, `api/`, or `db/`
- **NEVER**: `agents/` imports from `api/` or `pipeline/` (except `pipeline/mcp_client.py` for tools)
- **NEVER**: `pipeline/skeptic_validation.py` imports from `api/`
- **ALLOWED**: `pipeline/` imports from `agents/` (skeptic and orchestrator invocation)
- **ALLOWED**: `agents/skeptic.py` imports from `models/` (leaf dependency)

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- `SkepticChallenge` validates required fields: non-empty `alternative_hypotheses`, `logical_weaknesses`
- `SkepticResponse` validates `rebuttals` list, optional `revised_diagnosis`
- `SkepticVerdict` validates `rounds_completed` is 1 or 2, hashes are non-empty strings
- Skeptic agent with mocked LLM produces valid `SkepticChallenge` — evidence_gaps entries are always present in challenge when `evidence_gaps` is non-empty
- Orchestrator rebuttal with mocked LLM produces valid `SkepticResponse` with rebuttals addressing each challenge point
- `seal_diagnosis()` copies all DiagnosisObject fields into ImmutableDiagnosisArtifact correctly
- `ImmutableDiagnosisArtifact` is frozen — raises `ValidationError` on field assignment attempt

**Validation loop tests** (`pytest -m unit`):
- Hash unchanged after round 1 → verdict has `rounds_completed=1`, `passed=True`
- Hash changed after round 1 → verdict has `rounds_completed=2`, `passed=True`
- Hash changed after both rounds → still `passed=True` (no infinite loops)
- Evidence gaps present → skeptic challenge includes gap-specific challenges
- Challenge history contains full challenge/response pairs

**DB integration tests** (`pytest -m db`):
- `persist_skeptic_record()` writes round data to `skeptic_reviews` table
- `persist_immutable_diagnosis()` writes sealed artifact to `immutable_diagnoses` table
- Unique constraint on `(incident_id, round_number)` in `skeptic_reviews`
- Unique constraint on `incident_id` in `immutable_diagnoses`
- JSONB roundtrip: persisted and retrieved data matches original Pydantic model

**Pipeline integration tests** (`pytest -m pipeline`):
- Full graph path: `diagnose→completeness→skeptic→finalize` produces `ImmutableDiagnosisArtifact` in state
- State transitions: `queued→diagnosing→diagnosed` for success path
- Re-challenge path: skeptic changes hash → second round → still reaches `diagnosed`
- Event bus receives `incident.stage_changed` events for skeptic completion
- Audit log receives skeptic round entries
- Checkpointed state includes skeptic verdict (verify by resuming from checkpoint)

**Mock LLM patterns:**
- Use `FakeChatModel` from `tests/agents/conftest.py` (established in 2.2)
- Skeptic mock returns deterministic `SkepticChallenge` with known fields
- Orchestrator rebuttal mock returns `SkepticResponse` with optionally changed diagnosis hash
- For hash-change tests: mock two different `DiagnosisObject` outputs (different `root_cause_component` values → different hashes)

### Anti-Patterns / DO NOT

- **DO NOT** give the skeptic agent any tools. The skeptic reasons over the presented evidence only — it does NOT query the cluster or search runbooks. Tool use is the orchestrator's domain.
- **DO NOT** allow more than 2 skeptic rounds. After round 2, the diagnosis passes regardless of hash change. No configurable max rounds. No exceptions. This is a hard architectural rule (AD: "NEVER allow more than one re-challenge").
- **DO NOT** implement the Remediation Skeptic. Story 3.2 implements `FR-9`. This story implements `FR-8` (Diagnosis Skeptic) only.
- **DO NOT** modify the `DiagnosisObject` model. It was created in 2.1 and extended in 2.2. The skeptic works WITH it, not ON it. If the orchestrator revises the diagnosis, it produces a NEW `DiagnosisObject` instance.
- **DO NOT** implement RBAC-crossing logic for remediation. This story creates the `ImmutableDiagnosisArtifact` and persists it. Epic 3 reads it. The handoff is simply a database read by the remediation planner.
- **DO NOT** implement the remediation planner or anything beyond persisting the immutable artifact. Epic 3 scope.
- **DO NOT** modify the state machine transitions. `diagnosing→diagnosed` is already a valid transition. No new states needed.
- **DO NOT** add RHOKP or Learning Store integration to the skeptic. The skeptic has no external data sources. Story 2.3 adds RHOKP/Learning Store to the orchestrator, not the skeptic.
- **DO NOT** modify `pipeline/runner.py` or `pipeline/dispatcher.py`. The graph modification in `diagnosis_graph.py` is sufficient — the runner invokes the graph, and the graph now includes the skeptic node.
- **DO NOT** add frontend code or API endpoints. The skeptic data is persisted for future API exposure (Epic 5 detail view, Skeptic panel).
- **DO NOT** use `litellm` directly — use `ChatOpenAI` via `get_chat_model(AgentRole.SKEPTIC)` per the pattern established in 2.2.
- **DO NOT** create custom LangGraph graph nodes for the skeptic's internal challenge/response loop. The loop logic is in `pipeline/skeptic_validation.py` — the graph sees a single `skeptic_validation` node.

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  models/
    skeptic.py             # NEW: SkepticChallenge, SkepticResponse, SkepticVerdict
    __init__.py            # UPDATE: export new models
  agents/
    skeptic.py             # NEW: Skeptic agent (create_react_agent subgraph)
    orchestrator.py        # UPDATE: add run_orchestrator_rebuttal()
    prompts.py             # UPDATE: add SKEPTIC_SYSTEM_PROMPT
  pipeline/
    skeptic_validation.py  # NEW: Validation loop + seal_diagnosis()
    diagnosis_graph.py     # UPDATE: add skeptic_validation node + edges
  db/
    skeptic.py             # NEW: skeptic_reviews persistence
    diagnosis.py           # NEW: immutable_diagnoses persistence
backend/alembic/versions/
    xxx_add_skeptic_reviews.py       # NEW migration
    xxx_add_immutable_diagnoses.py   # NEW migration
backend/tests/
  models/
    test_skeptic.py        # NEW
  agents/
    test_skeptic.py        # NEW
  pipeline/
    test_skeptic_validation.py  # NEW
    test_diagnosis_graph.py     # UPDATE: full graph path tests
  db/
    test_skeptic.py        # NEW
```

### Latest Technology Notes

**LangGraph 1.2.x — `create_react_agent` with `response_format`:**
- `response_format=(prompt_str, PydanticModel)` triggers a final structured output call after any tool loop
- When the agent has no tools (like the skeptic), `create_react_agent` effectively becomes: one LLM call → structured output extraction
- The subgraph returns `state["structured_response"]` containing the Pydantic model instance
- Subgraph checkpointing: the skeptic subgraph state is automatically checkpointed by the parent graph's checkpointer
- `version="v2"` is the default and recommended version

**Adversarial agent pattern in LangGraph:**
- The challenge/response loop is implemented as plain Python in `skeptic_validation.py`, NOT as graph edges
- This is the correct pattern: the pipeline graph sees a single node (`skeptic_validation`), inside which the skeptic and orchestrator interact across multiple invocations
- Keeping the loop in Python (not graph edges) avoids checkpoint complexity for internal debate rounds while still allowing the overall node to be checkpointed
- The LangGraph graph structure is: `diagnose → completeness_gate → skeptic_validation → finalize`

**`ImmutableDiagnosisArtifact` with Pydantic `frozen=True`:**
- `model_config = ConfigDict(frozen=True)` makes all fields immutable after construction
- Attempting to set any attribute raises `pydantic.ValidationError`
- `model_dump()` and `model_dump_json()` still work for serialization
- Construction via `ImmutableDiagnosisArtifact(**diagnosis.model_dump(), skeptic_verdict=..., sealed_at=...)` — keyword arguments at creation time

### References

- [Source: ARCHITECTURE-SPINE.md#AD-1] — Agents internal to stages (skeptic in `agents/`, called by pipeline node)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock (ImmutableDiagnosisArtifact is what crosses)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module (SkepticChallenge, SkepticVerdict in `models/`)
- [Source: ARCHITECTURE-SPINE.md#AD-15] — MCP timeout → evidence_gaps, Skeptic MUST challenge gaps
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (diagnosing→diagnosed)
- [Source: ARCHITECTURE-SPINE.md#AD-24] — In-process event bus for SSE
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit log write points
- [Source: ARCHITECTURE-SPINE.md#Pipeline Flow] — Skeptic after diagnosis, before remediation
- [Source: project-context.md#Critical Don't-Miss Rules] — NEVER skip the skeptic, NEVER allow more than one re-challenge
- [Source: project-context.md#LangGraph] — Agents internal to stages, checkpoints
- [Source: project-context.md#Testing Rules] — Mock LLM, mock MCP, test layers
- [Source: epics.md#Story 2.4] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 2] — FR-8, FR-10 coverage
- [Source: Story 2.1 spec] — DiagnosisObject, root_cause_hash(), ImmutableDiagnosisArtifact, DiagnosisState, pipeline graph
- [Source: Story 2.2 spec] — Orchestrator agent, tools, completeness gate, AgentRole.SKEPTIC, FakeChatModel fixture
- [Source: epics.md#Story 3.1] — Remediation planner reads ImmutableDiagnosisArtifact (downstream consumer)

## Code Review Record

### Review Model Used

(to be filled during review — must differ from dev model)

### Review Findings

(to be filled during review)

### Decisions Needed / Decisions Taken

(to be filled during review)

### Fixes Applied

(to be filled during review)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### Change Log

### File List
