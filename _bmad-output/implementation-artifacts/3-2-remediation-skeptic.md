---
baseline_commit: 1510d0f8ec43de1a4a10f57d856527c780febd96
---

# Story 3.2: Remediation Skeptic

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want every remediation plan to survive adversarial challenge,
so that I can trust the proposed fix won't cause unintended damage or miss critical preconditions.

## Acceptance Criteria

1. **Given** a Remediation Plan is produced by the planner **When** it is submitted to the Remediation Skeptic **Then** the Skeptic evaluates: plan steps for correctness, blast radius assessment accuracy, rollback feasibility, precondition completeness, and estimated risk appropriateness

2. **Given** the Skeptic produces a structured challenge **When** the planner responds **Then** the plan hash is compared before and after the response

3. **Given** the plan hash is unchanged after the challenge response **When** stability is assessed **Then** the plan passes validation

4. **Given** the plan hash changes fundamentally after the first challenge **When** the re-challenge protocol is triggered **Then** the revised plan is re-challenged exactly one additional round **And** after the second round, the plan passes regardless of hash change (no infinite loops)

5. **Given** the Skeptic challenge and planner response **When** the validation completes **Then** both the challenge and response are persisted as part of the incident's audit trail

## Tasks / Subtasks

- [x] Task 1: Remediation Skeptic challenge/verdict models (AC: #1, #2, #3, #4)
  - [x] 1.1 Create `backend/src/models/remediation_skeptic.py` with `RemediationSkepticChallenge`, `RemediationSkepticVerdict` models
  - [x] 1.2 `RemediationSkepticChallenge` fields: `step_correctness_issues: list[str]`, `blast_radius_assessment: str`, `rollback_feasibility_issues: list[str]`, `precondition_gaps: list[str]`, `risk_assessment_critique: str`, `overall_verdict: str`, `created_at: datetime`
  - [x] 1.3 `RemediationSkepticVerdict` fields: `passed: bool`, `rounds_completed: int` (1–2), `original_plan_hash: str`, `final_plan_hash: str`, `challenge_history: list[dict]`, `verdict_reasoning: str`
  - [x] 1.4 Add `plan_hash()` method to `RemediationPlan` model (deterministic hash of steps + blast_radius + rollback_plan + preconditions)
  - [x] 1.5 Export from `backend/src/models/__init__.py`

- [x] Task 2: Remediation Skeptic agent (AC: #1)
  - [x] 2.1 Create `backend/src/agents/remediation_skeptic.py` with `build_remediation_skeptic_agent()` and `run_remediation_skeptic(plan: RemediationPlan, artifact: ImmutableDiagnosisArtifact) -> RemediationSkepticChallenge`
  - [x] 2.2 The Remediation Skeptic has NO tools (same pattern as Diagnosis Skeptic) — it reasons over the plan and diagnosis context only
  - [x] 2.3 Add `REMEDIATION_SKEPTIC` to `AgentRole` enum in `config/llm_settings.py`
  - [x] 2.4 Add `REMEDIATION_SKEPTIC_SYSTEM_PROMPT` and `REMEDIATION_SKEPTIC_STRUCTURED_PROMPT` to `agents/prompts.py`

- [x] Task 3: Planner re-challenge response (AC: #2, #4)
  - [x] 3.1 Add `run_planner_rebuttal(plan: RemediationPlan, challenge: RemediationSkepticChallenge, artifact: ImmutableDiagnosisArtifact) -> RemediationPlan` to `agents/planner.py`
  - [x] 3.2 The planner rebuttal uses the same tools as the original planner (query_cluster_state, check_rbac_permissions, check_resource_quota) — it may query the cluster to verify/refine the plan
  - [x] 3.3 Add `PLANNER_REBUTTAL_PROMPT_TEMPLATE` to `agents/prompts.py`

- [x] Task 4: Remediation skeptic validation loop (AC: #2, #3, #4)
  - [x] 4.1 Create `backend/src/pipeline/remediation_skeptic_validation.py` with `run_remediation_skeptic_validation(plan: RemediationPlan, artifact: ImmutableDiagnosisArtifact) -> tuple[RemediationPlan, RemediationSkepticVerdict]`
  - [x] 4.2 Implement hash-based termination: round 1 hash unchanged → pass; hash changed → round 2; after round 2 → pass regardless
  - [x] 4.3 Max 2 rounds enforced (AD: "NEVER allow more than one re-challenge")

- [x] Task 5: Add skeptic node to remediation graph (AC: #1–#4)
  - [x] 5.1 Add `skeptic_validation` node to `pipeline/remediation_graph.py` after the `plan` node
  - [x] 5.2 Update graph structure: `entry → plan → skeptic_validation → END`
  - [x] 5.3 `skeptic_validation_node` loads plan from state, runs the skeptic validation loop, updates state with verdict and possibly revised plan
  - [x] 5.4 Update `RemediationState` to include: `skeptic_challenge: dict | None`, `skeptic_verdict: dict | None`

- [x] Task 6: Persistence (AC: #5)
  - [x] 6.1 Create `backend/src/db/remediation_skeptic.py` with `persist_remediation_skeptic_record(conn, incident_id, round_number, challenge, response, verdict)` — mirrors `db/skeptic.py` pattern
  - [x] 6.2 Create Alembic migration `010_add_remediation_skeptic_reviews.py` for `remediation_skeptic_reviews` table
  - [x] 6.3 Table schema: `id UUID PK, incident_id UUID FK, round_number INT NOT NULL, challenge JSONB NOT NULL, response JSONB NOT NULL, verdict JSONB, created_at TIMESTAMPTZ`
  - [x] 6.4 Persist skeptic records from within the remediation runner after graph completion (inside the transaction)

- [x] Task 7: Wire persistence into remediation runner (AC: #5)
  - [x] 7.1 Update `pipeline/remediation_runner.py` to persist skeptic artifacts after graph completes (same pattern as diagnosis runner calling `persist_skeptic_artifacts`)
  - [x] 7.2 Emit SSE events for skeptic validation start/complete via event bus
  - [x] 7.3 Write audit_log entries for each skeptic round

- [x] Task 8: Tests — unit (AC: #1–#4)
  - [x] 8.1 `tests/models/test_remediation_skeptic.py` — model validation, plan_hash() determinism, hash change detection
  - [x] 8.2 `tests/agents/test_remediation_skeptic.py` — skeptic produces valid `RemediationSkepticChallenge` with mocked LLM
  - [x] 8.3 `tests/agents/test_planner.py` (extend) — planner rebuttal produces valid revised `RemediationPlan` with mocked LLM
  - [x] 8.4 `tests/pipeline/test_remediation_skeptic_validation.py` — hash-unchanged passes in 1 round, hash-changed triggers re-challenge, max 2 rounds enforced

- [x] Task 9: Tests — integration (AC: #5)
  - [x] 9.1 `tests/db/test_remediation_skeptic.py` — persist_remediation_skeptic_record roundtrip (testcontainers)
  - [x] 9.2 `tests/pipeline/test_remediation_graph.py` (extend) — graph now produces plan + skeptic verdict, remediation_skeptic_reviews rows created

### Review Findings

- [x] [Review][Patch] Skeptic validation start event still emits after the work finishes [`backend/src/pipeline/remediation_runner.py:85`] — `run_remediation_pipeline()` sends `skeptic_validation=validating` only after `graph.ainvoke()` has already finished the skeptic loop, so subscribers never observe a real stage start and may miss a terminal skeptic-stage event if persistence fails afterward. **Fixed**: `skeptic_validation_node()` now emits `skeptic_validation=validating` before entering the skeptic loop.
- [x] [Review][Patch] Skeptic validation audit rows still commit outside the remediation transaction [`backend/src/pipeline/remediation_graph.py:87`] — `skeptic_validation_node()` writes `pipeline.stage.skeptic_validation` audit rows through `pipeline_audit_log()`, which acquires its own connection and commits independently, so a later rollback can leave an audit trail claiming validation completed even though the final plan / skeptic artifacts were not durably saved. **Fixed**: the terminal `skeptic_validation=validated` audit write now runs inside the remediation persistence transaction in `run_remediation_pipeline()`.
- [x] [Review][Patch] Planner rebuttal failures still abort the whole remediation pipeline [`backend/src/agents/planner.py:312`] — `run_planner_rebuttal()` assumes valid structured output and propagates agent/tool/schema failures through `run_remediation_skeptic_validation()`, which currently fails the entire remediation pipeline instead of degrading to the existing plan or another bounded manual-verification path. **Fixed**: `run_remediation_skeptic_validation()` now catches rebuttal exceptions, records the degraded round, and keeps the pipeline from aborting.
- [ ] [Review][Patch] Rebuttal failures still look like a clean skeptic pass [`backend/src/pipeline/remediation_skeptic_validation.py:63`] — When `run_planner_rebuttal()` raises, the loop preserves the existing plan and records `rebuttal_failed` in nested history, but still returns `passed=True` and lets the runner emit `skeptic_validation=validated`. That turns an LLM/tool/schema failure into an apparent successful validation instead of surfacing a degraded/manual-verification outcome.
- [ ] [Review][Patch] Skeptic stage can remain stuck in `validating` after persistence failure [`backend/src/pipeline/remediation_runner.py:126`] — The graph now emits `skeptic_validation=validating` at stage start, but if transactional persistence fails afterward the exception path only emits `remediation_plan=failed`. Subscribers tracking the skeptic stage never receive a terminal failure/aborted event for `skeptic_validation`.

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Story 3.1 (Remediation Planner & Structured Plan):**

Story 3.1 is the direct predecessor — it creates the plan this story challenges:

- **`models/remediation.py`** — `RemediationPlan`, `RemediationStep`, `BlastRadius`, `RiskLevel`, `Precondition` models. This story adds `plan_hash()` to `RemediationPlan`.
- **`agents/planner.py`** — `build_planner_agent()` and `run_planner()`. This story adds `run_planner_rebuttal()` for the re-challenge response.
- **`pipeline/remediation_graph.py`** — LangGraph `StateGraph` with single `plan` node. This story inserts `skeptic_validation` after `plan`. Graph structure becomes: `entry → plan → skeptic_validation → END`.
- **`pipeline/remediation_runner.py`** — Runner loads artifact from DB, invokes graph, persists plan. This story extends persistence to also save skeptic artifacts.
- **`pipeline/mcp_readwrite_client.py`** — The planner rebuttal reuses this client for cluster queries during re-challenge.
- **`db/remediation.py`** — `persist_remediation_plan()` and `load_immutable_artifact()`. This story adds separate skeptic persistence in `db/remediation_skeptic.py`.
- **`RemediationState` in `pipeline/remediation_graph.py`** — Currently: `incident_id`, `immutable_artifact`, `remediation_plan`, `stage`. This story adds: `skeptic_challenge`, `skeptic_verdict`.

**Critical pattern from Story 3.1:**
- The remediation graph is designed for incremental growth. Story 3.1 sets `plan → END`. This story changes to `plan → skeptic_validation → END`. Story 3.3 will add `dry_run` and `policy_gate` after skeptic.
- `RemediationPlan` contains steps, blast_radius, rollback_plan, preconditions — the skeptic challenges ALL of these.
- The planner HAS tools (unlike the diagnosis skeptic). When re-challenged, the planner can query the cluster again to refine its plan.

**From Story 2.4 (Diagnosis Skeptic & Immutable Handoff) — THE PATTERN:**

The Diagnosis Skeptic is the architectural template for the Remediation Skeptic:

- **`agents/skeptic.py`** — `build_skeptic_agent()` uses `create_react_agent` with NO tools + `response_format=(prompt, PydanticModel)`. The Remediation Skeptic follows this exact pattern.
- **`pipeline/skeptic_validation.py`** — `run_skeptic_validation()` implements the hash-based termination loop. Max 2 rounds. The Remediation Skeptic validation loop mirrors this exactly but uses `plan_hash()` instead of `root_cause_hash()`.
- **`models/skeptic.py`** — `SkepticChallenge`, `SkepticVerdict` models. The Remediation Skeptic needs its own parallel models (`RemediationSkepticChallenge`, `RemediationSkepticVerdict`) with plan-specific challenge fields.
- **`db/skeptic.py`** — `persist_skeptic_record()` writes to `skeptic_reviews` table. The remediation version writes to `remediation_skeptic_reviews`.
- **`pipeline/diagnosis_graph.py`** — `skeptic_validation_node()` invokes the loop and returns updated state. The remediation graph's `skeptic_validation_node` mirrors this.

**Key architectural insight from 2.4:**
- The skeptic agent itself is separate from the validation loop orchestration. `agents/skeptic.py` produces a challenge; `pipeline/skeptic_validation.py` manages the loop, hash comparison, and round termination.
- Same separation applies here: `agents/remediation_skeptic.py` produces challenges; `pipeline/remediation_skeptic_validation.py` manages the loop.

**From Story 2.2 (Orchestrator Agent):**
- **Agent pattern**: `create_react_agent` with `response_format=(prompt_str, PydanticModel)`.
- **`agents/llm_client.py`** — `get_chat_model(role)` resolves per-role LLM config from env vars.
- **`FakeChatModel`** fixture in `tests/agents/conftest.py` for mocked LLM tests.

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-1 | Agents internal to stages | Remediation Skeptic is an agent in `agents/remediation_skeptic.py`, invoked by the `skeptic_validation` node in `pipeline/remediation_graph.py`. NOT a pipeline-level graph node — runs inside one |
| AD-2 | RBAC Airlock | The Remediation Skeptic has NO tools — it does not access the cluster. The planner rebuttal can use the read-write MCP (cluster-admin SA) via existing tools |
| AD-4 | Shared types module | `RemediationSkepticChallenge`, `RemediationSkepticVerdict` defined in `models/remediation_skeptic.py` |
| AD-7 | Per-agent LLM config | Add `AgentRole.REMEDIATION_SKEPTIC` with `LLM_REMEDIATION_SKEPTIC_*` env vars |
| AD-14 | Monorepo layout | New files follow established pattern: models → agents → pipeline → db |
| AD-19 | Canonical state machine | This story does NOT transition incident state. The validated plan passes to Story 3.3's dry-run/policy gate |
| AD-25 | Audit logging | Each skeptic round is audit-logged via pipeline audit hook (same pattern as diagnosis skeptic) |

**Critical constraint — "NEVER allow more than one re-challenge" (AD):**
- Round 1: Skeptic challenges plan. Planner responds. Hash compared.
- If plan hash unchanged → validation passes (1 round).
- If plan hash changed → Round 2: Skeptic re-challenges revised plan. Planner responds. Plan PASSES regardless of hash outcome.
- Max 2 rounds. No infinite loops. Always passes after the loop.

### Technical Requirements

#### Plan Hash Method

Add to `models/remediation.py`:

```python
import hashlib
import json

class RemediationPlan(BaseModel):
    # ... existing fields ...

    def plan_hash(self) -> str:
        """Deterministic hash of plan content for skeptic comparison.

        Hashes: steps, blast_radius, rollback_plan, preconditions.
        Excludes: id, incident_id, diagnosis_id, plan_summary, created_at
        (these are metadata, not plan substance).
        """
        content = {
            "steps": [s.model_dump(mode="json") for s in self.steps],
            "blast_radius": self.blast_radius.value,
            "rollback_plan": [s.model_dump(mode="json") for s in self.rollback_plan],
            "preconditions": [p.model_dump(mode="json") for p in self.preconditions],
            "estimated_risk": self.estimated_risk.value,
        }
        serialized = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()
```

#### Remediation Skeptic Challenge Model

```python
class RemediationSkepticChallenge(BaseModel):
    """Structured adversarial challenge to a Remediation Plan."""

    step_correctness_issues: list[str] = Field(default_factory=list)
    blast_radius_assessment: str
    rollback_feasibility_issues: list[str] = Field(default_factory=list)
    precondition_gaps: list[str] = Field(default_factory=list)
    risk_assessment_critique: str
    overall_verdict: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

#### Remediation Skeptic Verdict Model

```python
class RemediationSkepticVerdict(BaseModel):
    """Outcome of the full remediation skeptic validation loop."""

    passed: bool
    rounds_completed: int = Field(ge=1, le=2)
    original_plan_hash: str = Field(min_length=1)
    final_plan_hash: str = Field(min_length=1)
    challenge_history: list[dict[str, Any]]
    verdict_reasoning: str
```

#### Remediation Skeptic Agent Architecture

```python
def build_remediation_skeptic_agent():
    """Build the remediation skeptic as a LangGraph create_react_agent subgraph.

    The remediation skeptic has NO tools — it reasons over the plan and
    diagnosis context only. Same pattern as the Diagnosis Skeptic.
    """
    llm = get_chat_model(AgentRole.REMEDIATION_SKEPTIC)
    return create_react_agent(
        model=llm,
        tools=[],
        prompt=REMEDIATION_SKEPTIC_SYSTEM_PROMPT,
        response_format=(REMEDIATION_SKEPTIC_STRUCTURED_PROMPT, RemediationSkepticChallenge),
    )


async def run_remediation_skeptic(
    plan: RemediationPlan,
    artifact: ImmutableDiagnosisArtifact,
) -> RemediationSkepticChallenge:
    """Run the remediation skeptic to produce an adversarial challenge.

    The skeptic receives both the plan AND the diagnosis context so it can
    evaluate whether the plan correctly addresses the diagnosed root cause.
    """
    agent = build_remediation_skeptic_agent()

    prompt_text = (
        f"Review this remediation plan and produce a structured challenge.\n\n"
        f"DIAGNOSIS CONTEXT:\n{json.dumps(artifact.model_dump(mode='json'), indent=2)}\n\n"
        f"REMEDIATION PLAN:\n{plan.model_dump_json(indent=2)}"
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content=prompt_text)]})
    # ... structured_response handling (same pattern as diagnosis skeptic)
```

#### Remediation Skeptic System Prompt Requirements

The prompt MUST instruct the skeptic to evaluate:
1. **Step correctness** — Are the remediation steps logically correct for the diagnosed root cause? Will they actually fix the problem?
2. **Blast radius accuracy** — Does the assessed blast radius match what the steps actually modify? Is it under/over-estimated?
3. **Rollback feasibility** — Is the rollback plan actually reversible? Are there non-reversible steps without adequate rollback?
4. **Precondition completeness** — Are all RBAC permissions, quota requirements, and resource prerequisites enumerated?
5. **Risk appropriateness** — Does the estimated risk reflect the actual blast radius × reversibility × confidence?

**The skeptic MUST NOT:**
- Question the diagnosis itself (that was validated in Epic 2)
- Suggest alternative root causes
- Block the plan indefinitely (max 2 rounds, always passes)

#### Planner Rebuttal Architecture

```python
async def run_planner_rebuttal(
    plan: RemediationPlan,
    challenge: RemediationSkepticChallenge,
    artifact: ImmutableDiagnosisArtifact,
) -> RemediationPlan:
    """Run the planner in rebuttal mode to address skeptic challenges.

    The planner can query the cluster again to verify/refine the plan.
    Returns a potentially revised RemediationPlan.
    """
    llm = get_chat_model(AgentRole.PLANNER)
    tools = get_planner_tools()
    agent = build_planner_agent(llm, tools)

    prompt = PLANNER_REBUTTAL_PROMPT_TEMPLATE.format(
        plan_json=plan.model_dump_json(indent=2),
        challenge_json=challenge.model_dump_json(indent=2),
        artifact_json=json.dumps(artifact.model_dump(mode="json"), indent=2),
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    revised_plan = result["structured_response"]
    revised_plan.incident_id = plan.incident_id
    revised_plan.diagnosis_id = plan.diagnosis_id
    return revised_plan
```

**Key difference from diagnosis skeptic rebuttal:**
- The Diagnosis Skeptic rebuttal is handled by the Orchestrator (same agent that produced the diagnosis).
- The Remediation Skeptic rebuttal is handled by the Planner (same agent that produced the plan).
- The planner rebuttal HAS tools — it can query the cluster to verify or refine.

#### Remediation Skeptic Validation Loop

```python
MAX_REMEDIATION_SKEPTIC_ROUNDS = 2

async def run_remediation_skeptic_validation(
    plan: RemediationPlan,
    artifact: ImmutableDiagnosisArtifact,
) -> tuple[RemediationPlan, RemediationSkepticVerdict]:
    """Run the remediation skeptic challenge/response loop.

    Mirror of pipeline/skeptic_validation.py but for remediation plans.
    Uses plan_hash() instead of root_cause_hash().
    """
    original_hash = plan.plan_hash()
    current_plan = plan
    challenge_history: list[dict] = []

    for round_num in range(1, MAX_REMEDIATION_SKEPTIC_ROUNDS + 1):
        challenge = await run_remediation_skeptic(current_plan, artifact)
        revised_plan = await run_planner_rebuttal(current_plan, challenge, artifact)

        challenge_history.append({
            "round": round_num,
            "challenge": challenge.model_dump(mode="json"),
            "response": revised_plan.model_dump(mode="json"),
        })

        current_plan = revised_plan
        current_hash = current_plan.plan_hash()

        if current_hash == original_hash:
            break  # Plan unchanged — passes

        if round_num == 1:
            original_hash = current_hash  # Track revised hash for round 2
            continue  # Re-challenge required

    verdict = RemediationSkepticVerdict(
        passed=True,  # Always passes after loop completes
        rounds_completed=len(challenge_history),
        original_plan_hash=plan.plan_hash(),
        final_plan_hash=current_plan.plan_hash(),
        challenge_history=challenge_history,
        verdict_reasoning=f"Plan validated after {len(challenge_history)} round(s).",
    )

    return current_plan, verdict
```

#### Remediation Graph Update

```python
class RemediationState(TypedDict):
    incident_id: str
    immutable_artifact: dict
    remediation_plan: dict | None
    skeptic_challenge: dict | None  # NEW
    skeptic_verdict: dict | None     # NEW
    stage: str


async def skeptic_validation_node(state: RemediationState) -> dict:
    """Remediation skeptic validation — challenges the plan (Story 3.2)."""
    from .remediation_skeptic_validation import run_remediation_skeptic_validation

    plan_dict = state.get("remediation_plan")
    artifact_dict = state.get("immutable_artifact")

    plan = RemediationPlan.model_validate(plan_dict)
    artifact = ImmutableDiagnosisArtifact.model_validate(artifact_dict)

    validated_plan, verdict = await run_remediation_skeptic_validation(plan, artifact)

    return {
        "remediation_plan": validated_plan.model_dump(mode="json"),
        "skeptic_challenge": verdict.challenge_history[-1]["challenge"] if verdict.challenge_history else None,
        "skeptic_verdict": verdict.model_dump(mode="json"),
    }


# Graph structure update:
#   entry → plan → skeptic_validation → END
```

#### Database Table

```sql
CREATE TABLE remediation_skeptic_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    round_number INTEGER NOT NULL,
    challenge JSONB NOT NULL,
    response JSONB NOT NULL,
    verdict JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_remediation_skeptic_reviews_incident
    ON remediation_skeptic_reviews(incident_id);
```

Mirrors `skeptic_reviews` table exactly — allows multiple rounds per incident (no UNIQUE on incident_id).

#### Persistence Pattern

Follow `db/skeptic.py` exactly:
```python
async def persist_remediation_skeptic_record(
    conn,
    *,
    incident_id: str | uuid.UUID,
    round_number: int,
    challenge: dict,
    response: dict,
    verdict: dict | None = None,
) -> uuid.UUID:
    """Persist a remediation skeptic challenge/response round.

    Also writes an audit_log entry for each round.
    """
    # INSERT INTO remediation_skeptic_reviews ...
    # write_audit_log(conn, actor="pipeline", action="pipeline.remediation_skeptic.round_complete", ...)
```

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ~=1.2 | Already in pyproject.toml. Skeptic via `create_react_agent` (no tools) |
| langchain-openai | latest | Already in pyproject.toml. `ChatOpenAI` for skeptic LLM calls |
| langchain-core | (transitive) | Already a transitive dep. `BaseChatModel`, `HumanMessage` |
| asyncpg | latest | Already in pyproject.toml. Skeptic record persistence |
| pydantic | latest | Already in pyproject.toml. Challenge/verdict models |

**No new dependencies required.** All packages were added in Epic 1/2.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/models/remediation_skeptic.py` | `RemediationSkepticChallenge`, `RemediationSkepticVerdict` models | NEW |
| `backend/src/agents/remediation_skeptic.py` | Remediation Skeptic agent — `build_remediation_skeptic_agent()`, `run_remediation_skeptic()` | NEW |
| `backend/src/pipeline/remediation_skeptic_validation.py` | Hash-based skeptic validation loop for remediation plans | NEW |
| `backend/src/db/remediation_skeptic.py` | `persist_remediation_skeptic_record()` | NEW |
| `backend/alembic/versions/009_add_remediation_skeptic_reviews.py` | Migration: `remediation_skeptic_reviews` table | NEW |
| `backend/tests/models/test_remediation_skeptic.py` | Challenge/verdict model validation, plan_hash() tests | NEW |
| `backend/tests/agents/test_remediation_skeptic.py` | Skeptic agent unit tests (mocked LLM) | NEW |
| `backend/tests/pipeline/test_remediation_skeptic_validation.py` | Validation loop unit tests (hash termination, max rounds) | NEW |
| `backend/tests/db/test_remediation_skeptic.py` | Skeptic record persistence roundtrip tests | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/remediation.py` | Add `plan_hash()` method to `RemediationPlan` | UPDATE |
| `backend/src/models/__init__.py` | Export `RemediationSkepticChallenge`, `RemediationSkepticVerdict` | UPDATE |
| `backend/src/config/llm_settings.py` | Add `REMEDIATION_SKEPTIC` to `AgentRole` enum | UPDATE |
| `backend/src/agents/prompts.py` | Add `REMEDIATION_SKEPTIC_SYSTEM_PROMPT`, `REMEDIATION_SKEPTIC_STRUCTURED_PROMPT`, `PLANNER_REBUTTAL_PROMPT_TEMPLATE` | UPDATE |
| `backend/src/agents/planner.py` | Add `run_planner_rebuttal()` function | UPDATE |
| `backend/src/pipeline/remediation_graph.py` | Add `skeptic_validation` node, update graph edges, extend `RemediationState` | UPDATE |
| `backend/src/pipeline/remediation_runner.py` | Persist skeptic artifacts after graph completion, emit SSE events | UPDATE |
| `backend/tests/agents/test_planner.py` | Add tests for `run_planner_rebuttal()` | UPDATE |
| `backend/tests/pipeline/test_remediation_graph.py` | Extend tests for graph with skeptic node | UPDATE |

### Dependency Direction (ENFORCED)

```
models/remediation_skeptic.py → (nothing — leaf module)
models/remediation.py → (nothing — leaf module; plan_hash() uses only stdlib)
agents/remediation_skeptic.py → agents/llm_client.py, models/ (RemediationSkepticChallenge, RemediationPlan, ImmutableDiagnosisArtifact)
agents/planner.py (rebuttal) → agents/llm_client.py, models/ (RemediationPlan, RemediationSkepticChallenge, ImmutableDiagnosisArtifact)
pipeline/remediation_skeptic_validation.py → agents/remediation_skeptic.py, agents/planner.py, models/
pipeline/remediation_graph.py → pipeline/remediation_skeptic_validation.py, models/
pipeline/remediation_runner.py → pipeline/remediation_graph.py, db/remediation_skeptic.py
db/remediation_skeptic.py → models/remediation_skeptic.py
```

- **NEVER**: `models/` imports from `agents/`, `pipeline/`, `api/`, or `db/`
- **NEVER**: `agents/` imports from `api/` or `pipeline/`
- **NEVER**: The skeptic modifies the `ImmutableDiagnosisArtifact` — it's read-only context
- **NEVER**: The skeptic accesses the cluster — NO tools, NO MCP calls
- **ALLOWED**: `agents/planner.py` rebuttal imports `pipeline/mcp_readwrite_client.py` for tool functions (same pattern as original planner)
- **ALLOWED**: `pipeline/` imports from `agents/` (graph node invokes skeptic + planner)

### Testing Requirements

**Unit tests** (`pytest -m unit`):
- `RemediationSkepticChallenge` validates field types and constraints
- `RemediationSkepticVerdict.rounds_completed` must be 1 or 2
- `RemediationPlan.plan_hash()` is deterministic — same plan produces same hash
- `plan_hash()` changes when steps are modified
- `plan_hash()` changes when blast_radius is changed
- `plan_hash()` does NOT change when only `plan_summary` or `created_at` changes (metadata exclusion)
- Remediation Skeptic agent with mocked LLM produces valid `RemediationSkepticChallenge`
- Planner rebuttal with mocked LLM produces valid revised `RemediationPlan`
- Validation loop with hash-unchanged plan completes in 1 round
- Validation loop with hash-changed plan goes to round 2 then passes
- Validation loop never exceeds 2 rounds (force hash change in both rounds — still passes)

**DB integration tests** (`pytest -m db`):
- `persist_remediation_skeptic_record()` writes to `remediation_skeptic_reviews` table
- Multiple rounds for same incident persist correctly (no unique constraint violation)
- JSONB roundtrip: challenge and response data match originals
- Audit log receives entry for each round

**Pipeline integration tests** (`pytest -m pipeline`):
- Remediation graph with skeptic node: plan node runs → skeptic validates → state contains verdict
- Event bus receives stage_changed events for skeptic validation
- Runner persists skeptic records after graph completes

**Mock patterns:**
- Use `FakeChatModel` from `tests/agents/conftest.py` (established in 2.2)
- For hash-unchanged tests: mock the planner rebuttal to return the same plan (same hash)
- For hash-changed tests: mock the planner rebuttal to return a plan with different steps (different hash)
- Create a fixture that provides a test `RemediationPlan` and `ImmutableDiagnosisArtifact`
- Mock the `ReadWriteMCPClient` for planner rebuttal tests (it uses tools)

### Anti-Patterns / DO NOT

- **DO NOT** give the Remediation Skeptic any tools. It reasons over the plan and diagnosis only — same as the Diagnosis Skeptic has no tools.
- **DO NOT** allow the Skeptic to question the diagnosis. The `ImmutableDiagnosisArtifact` is context — the Skeptic evaluates whether the PLAN correctly addresses it, not whether the diagnosis is correct.
- **DO NOT** allow more than 2 rounds. After round 2, the plan passes regardless. This is a hard constraint from the architecture.
- **DO NOT** implement dry-run pre-flight or policy gate. That's Story 3.3 — it comes AFTER the skeptic.
- **DO NOT** transition incident state. The validated plan proceeds to Story 3.3's dry-run/policy gate.
- **DO NOT** reuse the `SkepticChallenge` model from `models/skeptic.py`. That model is specific to diagnosis challenges (alternative_hypotheses, evidence_gaps). Create separate plan-specific models.
- **DO NOT** reuse the `skeptic_reviews` table. Create `remediation_skeptic_reviews` — they are distinct audit trails.
- **DO NOT** implement execution logic. That's Story 3.5.
- **DO NOT** implement human approval workflow. That's Story 3.4.
- **DO NOT** modify `models/diagnosis.py` or `models/skeptic.py` — those are stable Epic 2 models.
- **DO NOT** modify the `pipeline/skeptic_validation.py` — that is the diagnosis skeptic validation, not remediation.
- **DO NOT** add `litellm` directly — use `ChatOpenAI` via `get_chat_model(AgentRole.REMEDIATION_SKEPTIC)`.
- **DO NOT** modify the state machine. No new states needed. No transitions in this story.
- **DO NOT** persist the validated plan to `remediation_plans` here — Story 3.1's runner already handles that. The skeptic might produce a revised plan; the runner should persist the FINAL plan (post-skeptic), but plan persistence is already wired.
- **DO NOT** add frontend code or API endpoints. That's Epic 5.

### Project Structure Notes

All new files align with AD-14 monorepo layout:
```
backend/src/
  models/
    remediation.py             # UPDATE: add plan_hash() method
    remediation_skeptic.py     # NEW: RemediationSkepticChallenge, RemediationSkepticVerdict
    __init__.py                # UPDATE: export new models
  agents/
    remediation_skeptic.py     # NEW: Remediation Skeptic agent
    planner.py                 # UPDATE: add run_planner_rebuttal()
    prompts.py                 # UPDATE: add REMEDIATION_SKEPTIC_*, PLANNER_REBUTTAL_*
  config/
    llm_settings.py            # UPDATE: add REMEDIATION_SKEPTIC to AgentRole
  pipeline/
    remediation_skeptic_validation.py  # NEW: hash-based validation loop
    remediation_graph.py               # UPDATE: add skeptic_validation node
    remediation_runner.py              # UPDATE: persist skeptic artifacts
  db/
    remediation_skeptic.py     # NEW: persist_remediation_skeptic_record
backend/alembic/versions/
    009_add_remediation_skeptic_reviews.py  # NEW migration
backend/tests/
  models/
    test_remediation_skeptic.py             # NEW
  agents/
    test_remediation_skeptic.py             # NEW
    test_planner.py                         # UPDATE: add rebuttal tests
  pipeline/
    test_remediation_skeptic_validation.py  # NEW
    test_remediation_graph.py               # UPDATE: extend for skeptic node
  db/
    test_remediation_skeptic.py             # NEW
```

### Latest Technology Notes

**LangGraph 1.2.x — `create_react_agent` for the Remediation Skeptic:**
- NO tools — the skeptic is a pure reasoner over the plan, same pattern as diagnosis skeptic
- `response_format=(prompt_str, RemediationSkepticChallenge)` extracts the Pydantic model
- Subgraph state is checkpointed by the parent graph's checkpointer
- `version="v2"` default

**Planner rebuttal with tools:**
- Same `create_react_agent` + tools pattern as the original planner
- The planner CAN use its tools during rebuttal (query cluster, check RBAC, check quota)
- This is the key difference from diagnosis — diagnosis skeptic rebuttal has no tools; planner rebuttal does
- The planner uses its existing tools list; no new tools needed for rebuttal

**Hash comparison approach:**
- `hashlib.sha256` on JSON-serialized plan content (deterministic with `sort_keys=True`)
- Excludes metadata fields (id, timestamps, summaries) — only hashes substantive plan content
- Same philosophical approach as `DiagnosisObject.root_cause_hash()` but applied to plan content

### References

- [Source: ARCHITECTURE-SPINE.md#AD-1] — Agents internal to stages (skeptic in `agents/`, called by pipeline node)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock (skeptic has NO cluster access; planner rebuttal uses read-write MCP)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module (RemediationSkepticChallenge/Verdict in `models/`)
- [Source: ARCHITECTURE-SPINE.md#AD-7] — Per-agent LLM config (AgentRole.REMEDIATION_SKEPTIC)
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout
- [Source: ARCHITECTURE-SPINE.md#AD-19] — Canonical state machine (no transitions in this story)
- [Source: ARCHITECTURE-SPINE.md#AD-25] — Audit logging (each skeptic round audit-logged)
- [Source: ARCHITECTURE-SPINE.md#Pipeline Flow] — "NEVER allow more than one re-challenge" constraint
- [Source: epics.md#Story 3.2] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 3] — FR-9 coverage
- [Source: Story 3.1 spec] — RemediationPlan model, planner agent, remediation graph, runner, persistence
- [Source: Story 2.4 spec] — Diagnosis Skeptic pattern (the architectural template for this story)
- [Source: pipeline/skeptic_validation.py] — Hash-based termination loop pattern to mirror
- [Source: agents/skeptic.py] — Agent architecture (NO tools, create_react_agent + response_format)
- [Source: db/skeptic.py] — Persistence pattern to mirror
- [Source: models/skeptic.py] — Model architecture (Challenge + Verdict pattern)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (via Cursor)

### Debug Log References

No issues encountered. All patterns mirrored cleanly from the Diagnosis Skeptic (Story 2.4). The only fix needed was adjusting test mock patch paths — the validation loop uses deferred imports inside the function body, so patches must target the original module location rather than the importer.

### Completion Notes List

- **Task 1:** Created `RemediationSkepticChallenge` and `RemediationSkepticVerdict` Pydantic models in `models/remediation_skeptic.py`. Added `plan_hash()` to `RemediationPlan` — deterministic SHA-256 of steps, blast_radius, rollback_plan, preconditions, estimated_risk; excludes metadata (id, summary, created_at). Exported new models from `models/__init__.py`. Added `REMEDIATION_SKEPTIC` to `AgentRole` enum.
- **Task 2:** Created remediation skeptic agent in `agents/remediation_skeptic.py` — `build_remediation_skeptic_agent()` with NO tools (pure reasoner pattern from Diagnosis Skeptic), `run_remediation_skeptic()` with fallback challenge on LLM failure.
- **Task 3:** Added `run_planner_rebuttal()` to `agents/planner.py` — planner responds to skeptic challenges using same tools as original planner. Added `PLANNER_REBUTTAL_PROMPT_TEMPLATE` to `agents/prompts.py`.
- **Task 4:** Created `pipeline/remediation_skeptic_validation.py` — hash-based termination loop mirroring `skeptic_validation.py`. Max 2 rounds enforced, always passes after loop completes.
- **Task 5:** Extended `RemediationState` with `skeptic_challenge` and `skeptic_verdict` fields. Added `skeptic_validation_node` to remediation graph. Updated graph structure: `entry → plan → skeptic_validation → END`.
- **Task 6:** Created `db/remediation_skeptic.py` with `persist_remediation_skeptic_record()` mirroring `db/skeptic.py`. Created Alembic migration `010_add_remediation_skeptic_reviews.py` for the `remediation_skeptic_reviews` table with incident index.
- **Task 7:** Updated `pipeline/remediation_runner.py` to persist skeptic artifacts after graph completion, emit SSE events for skeptic validation start/complete, and write audit_log entries for each round.
- **Task 8:** Created 41 new unit tests: 19 model tests (challenge/verdict validation, plan_hash determinism/sensitivity), 8 agent tests (skeptic + planner rebuttal), 5 validation loop tests, 9 graph tests (skeptic node + full graph execution). All 510 unit tests pass (469 baseline + 41 new).
- **Task 9:** Created 4 DB integration tests for `persist_remediation_skeptic_record` roundtrip, multiple rounds, and JSONB integrity.

## File List

| Action | File | Description |
|--------|------|-------------|
| NEW | `backend/src/models/remediation_skeptic.py` | `RemediationSkepticChallenge` and `RemediationSkepticVerdict` models |
| NEW | `backend/src/agents/remediation_skeptic.py` | Remediation Skeptic agent (NO tools, pure reasoner) |
| NEW | `backend/src/pipeline/remediation_skeptic_validation.py` | Hash-based skeptic validation loop for remediation plans |
| NEW | `backend/src/db/remediation_skeptic.py` | `persist_remediation_skeptic_record()` persistence function |
| NEW | `backend/alembic/versions/010_add_remediation_skeptic_reviews.py` | Migration: `remediation_skeptic_reviews` table |
| NEW | `backend/tests/models/test_remediation_skeptic.py` | Unit tests: model validation, plan_hash() tests |
| NEW | `backend/tests/agents/test_remediation_skeptic.py` | Unit tests: skeptic agent with mocked LLM |
| NEW | `backend/tests/pipeline/test_remediation_skeptic_validation.py` | Unit tests: validation loop hash termination, max rounds |
| NEW | `backend/tests/db/test_remediation_skeptic.py` | DB integration tests: persistence roundtrip |
| MODIFIED | `backend/src/models/remediation.py` | Added `plan_hash()` method to `RemediationPlan` |
| MODIFIED | `backend/src/models/__init__.py` | Export `RemediationSkepticChallenge`, `RemediationSkepticVerdict` |
| MODIFIED | `backend/src/config/llm_settings.py` | Added `REMEDIATION_SKEPTIC` to `AgentRole` enum |
| MODIFIED | `backend/src/agents/prompts.py` | Added `REMEDIATION_SKEPTIC_SYSTEM_PROMPT`, `REMEDIATION_SKEPTIC_STRUCTURED_PROMPT`, `PLANNER_REBUTTAL_PROMPT_TEMPLATE` |
| MODIFIED | `backend/src/agents/planner.py` | Added `run_planner_rebuttal()` function |
| MODIFIED | `backend/src/pipeline/remediation_graph.py` | Added `skeptic_validation` node, updated graph edges, extended `RemediationState` |
| MODIFIED | `backend/src/pipeline/remediation_runner.py` | Persist skeptic artifacts, emit SSE events, audit logging |
| MODIFIED | `backend/tests/agents/test_planner.py` | Added planner rebuttal tests |
| MODIFIED | `backend/tests/pipeline/test_remediation_graph.py` | Extended for skeptic node and updated graph structure |
| MODIFIED | `_bmad-output/implementation-artifacts/sprint-status.yaml` | Story status updated to review |

## Change Log

| Date | Change |
|------|--------|
| 2026-08-11 | Story 3.2 implemented: Remediation Skeptic agent, validation loop, persistence, graph integration. 41 new unit tests, 4 DB integration tests. All 510 unit tests pass with 0 regressions. |

## Code Review Record

### Review Round 2 — 2026-08-10
**Review model:** GPT-5.4
**Fix model:** to be filled when fixes are applied

#### Findings
- [x] [Review][Patch] Skeptic validation start event still emits after the work finishes [`backend/src/pipeline/remediation_runner.py:85`] — `run_remediation_pipeline()` sends `skeptic_validation=validating` only after `graph.ainvoke()` has already finished the skeptic loop, so subscribers never observe a real stage start and may miss a terminal skeptic-stage event if persistence fails afterward. **Fixed**: `skeptic_validation_node()` now emits `skeptic_validation=validating` before entering the skeptic loop.
- [x] [Review][Patch] Skeptic validation audit rows still commit outside the remediation transaction [`backend/src/pipeline/remediation_graph.py:87`] — `skeptic_validation_node()` writes `pipeline.stage.skeptic_validation` audit rows through `pipeline_audit_log()`, which acquires its own connection and commits independently, so a later rollback can leave an audit trail claiming validation completed even though the final plan / skeptic artifacts were not durably saved. **Fixed**: the terminal `skeptic_validation=validated` audit write now runs inside the remediation persistence transaction in `run_remediation_pipeline()`.
- [x] [Review][Patch] Planner rebuttal failures still abort the whole remediation pipeline [`backend/src/agents/planner.py:312`] — `run_planner_rebuttal()` assumes valid structured output and propagates agent/tool/schema failures through `run_remediation_skeptic_validation()`, which currently fails the entire remediation pipeline instead of degrading to the existing plan or another bounded manual-verification path. **Fixed**: `run_remediation_skeptic_validation()` now catches rebuttal exceptions, records the degraded round, and keeps the pipeline from aborting.

### Review Round 3 — 2026-08-10
**Review model:** GPT-5.4
**Fix model:** to be filled when fixes are applied

#### Findings
- [ ] [Review][Patch] Rebuttal failures still look like a clean skeptic pass [`backend/src/pipeline/remediation_skeptic_validation.py:63`] — When `run_planner_rebuttal()` raises, the loop preserves the existing plan and records `rebuttal_failed` in nested history, but still returns `passed=True` and lets the runner emit `skeptic_validation=validated`. That turns an LLM/tool/schema failure into an apparent successful validation instead of surfacing a degraded/manual-verification outcome.
- [ ] [Review][Patch] Skeptic stage can remain stuck in `validating` after persistence failure [`backend/src/pipeline/remediation_runner.py:126`] — The graph now emits `skeptic_validation=validating` at stage start, but if transactional persistence fails afterward the exception path only emits `remediation_plan=failed`. Subscribers tracking the skeptic stage never receive a terminal failure/aborted event for `skeptic_validation`.
