# Story 4.0: Manifest Generation Pipeline Stage

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want the system to produce validated YAML manifests from the planner's natural-language remediation steps,
so that dry-run pre-flight validates the actual resource content against the cluster, and execution applies deterministic artifacts rather than interpreted commands.

## Acceptance Criteria

1. **Given** a validated RemediationPlan with `apply` or `create` action steps **When** the manifest generation stage runs **Then** for each applicable step it queries the current cluster state for the target resource, produces a patched YAML manifest reflecting the planned change, and stores the manifest as a file artifact

2. **Given** a RemediationStep with action `apply` or `create` **When** the manifest generator queries current state **Then** it reads the existing resource via the read-write MCP Server and applies the planned change to produce a complete YAML manifest

3. **Given** a RemediationStep with an imperative action (restart, scale, patch, etc.) **When** the manifest generator evaluates it **Then** the step is skipped with an honest report (imperative actions have no manifest equivalent)

4. **Given** the manifest generation stage completes **When** it stores artifacts **Then** each manifest is written to a deterministic temp folder path scoped to the incident, and the `RemediationStep` is updated with a reference to the manifest artifact(s)

5. **Given** the downstream dry-run stage receives a step with a manifest artifact **When** it calls `apply_resource` with `--dry-run=server` **Then** it sends the actual YAML manifest body, enabling content-level validation (field values, resource limits, labels) in addition to RBAC and admission checks

6. **Given** the downstream execution stage receives a step with a manifest artifact **When** it executes the remediation **Then** it applies the manifest from the temp folder rather than interpreting a free-form shell command, ensuring deterministic execution

7. **Given** manifest generation fails for a step (e.g., target resource not found, MCP timeout) **When** the failure is recorded **Then** the step is marked with `manifest_generation_failed=True` and the dry-run stage treats it as a failed pre-flight check

8. **Given** a RemediationStep model **When** it is extended for manifest support **Then** it includes a `manifest_path: str | None` field for the artifact reference and a `manifest_generation_failed: bool` field for error tracking

## Tasks / Subtasks

- [ ] Task 1: Extend RemediationStep model (AC: #8)
  - [ ] 1.1 Add `manifest_path: str | None = None` field to `RemediationStep` in `backend/src/models/remediation.py`
  - [ ] 1.2 Add `manifest_generation_failed: bool = False` field to `RemediationStep`
  - [ ] 1.3 Verify `plan_hash()` on `RemediationPlan` excludes `manifest_path` and `manifest_generation_failed` (these are post-skeptic artifacts, not plan substance). These fields should be excluded from the hash because they are populated AFTER the skeptic validation — the skeptic evaluates the plan as natural language; manifests are generated later
  - [ ] 1.4 Update existing model tests to ensure new fields default correctly and don't break existing serialization

- [ ] Task 2: Manifest generation pipeline module (AC: #1, #2, #3, #4, #7)
  - [ ] 2.1 Create `backend/src/pipeline/manifest_generator.py` with `generate_manifests(plan: RemediationPlan, mcp_client: ReadWriteMCPClient) -> RemediationPlan`
  - [ ] 2.2 Define `MANIFEST_ELIGIBLE_ACTIONS: frozenset[str] = frozenset({"apply", "create"})` — same set as dry-run's `DRY_RUNNABLE_ACTIONS`
  - [ ] 2.3 For each eligible step: query current resource state via `mcp_client.query("resources_get", ...)`, parse YAML response, apply the planned change, write the complete YAML to `{temp_dir}/{incident_id}/step-{order}.yaml`
  - [ ] 2.4 Set `step.manifest_path` to the written file path
  - [ ] 2.5 For imperative actions (restart, scale, patch, etc.): skip with log message "Imperative action '{action}' has no manifest equivalent — skipped"
  - [ ] 2.6 For steps without a command: skip (informational steps)
  - [ ] 2.7 On failure (resource not found, MCP timeout, YAML parse error): set `step.manifest_generation_failed = True`, log the error, continue to next step (do NOT fail the whole pipeline)
  - [ ] 2.8 Return a new `RemediationPlan` with the updated steps (Pydantic models are immutable by convention — create a copy with modified steps)
  - [ ] 2.9 Use `tempfile.mkdtemp()` with prefix `aiops-manifests-` for the incident-scoped temp directory. The directory is cleaned up after execution completes (not by this module).

- [ ] Task 3: Add manifest_generation node to remediation graph (AC: #1, #4)
  - [ ] 3.1 Add `manifest_generation_node(state: RemediationState)` to `pipeline/remediation_graph.py`
  - [ ] 3.2 Node reads `remediation_plan` from state, invokes `generate_manifests()`, updates state with the manifest-annotated plan
  - [ ] 3.3 Insert the node between `skeptic_validation` and `dry_run` in the graph: `plan → skeptic_validation → manifest_generation → dry_run → policy_gate → END`
  - [ ] 3.4 Emit SSE events for manifest generation start/complete
  - [ ] 3.5 Add audit log entry for manifest generation with step counts (eligible, generated, skipped, failed)

- [ ] Task 4: Update dry-run to use manifests (AC: #5, #7)
  - [ ] 4.1 Modify `_validate_step()` in `pipeline/dry_run.py` to check `step.manifest_path`
  - [ ] 4.2 If `manifest_path` is set: read the YAML file and send its content as the `manifest` argument to `apply_resource` with `dry_run=server` — this validates the actual resource content, not just the command
  - [ ] 4.3 If `manifest_generation_failed` is True: return a `DryRunStepResult` with `success=False` and message "Manifest generation failed — cannot validate this step"
  - [ ] 4.4 If `manifest_path` is set but the file is missing at runtime: return `DryRunStepResult(success=False, message="Manifest file not found")`
  - [ ] 4.5 Existing behavior preserved for steps without manifests (imperative actions still skipped, informational steps still skipped)

- [ ] Task 5: Update execution engine to use manifests (AC: #6)
  - [ ] 5.1 Modify execution loop in `pipeline/execution_engine.py` to check `step.manifest_path`
  - [ ] 5.2 If `manifest_path` is set: read the YAML manifest and send it as the `manifest` argument to `apply_resource` via `mcp_client.execute()` instead of the raw `command`
  - [ ] 5.3 If `manifest_path` is set but the file is missing: log error and mark step as failed (same as MCP failure)
  - [ ] 5.4 Steps without `manifest_path` execute using the existing `command`-based path (backward compatibility)
  - [ ] 5.5 Log which execution path was used (manifest vs command) for each step

- [ ] Task 6: Tests — unit (AC: #1–#8)
  - [ ] 6.1 `tests/models/test_remediation.py` (extend) — new fields default correctly, `plan_hash()` excludes manifest fields, serialization roundtrip works
  - [ ] 6.2 `tests/pipeline/test_manifest_generator.py` — apply/create steps get manifests, imperative steps skipped, informational steps skipped, MCP failure sets `manifest_generation_failed=True`, YAML written to temp directory
  - [ ] 6.3 `tests/pipeline/test_dry_run.py` (extend) — step with `manifest_path` sends manifest body, step with `manifest_generation_failed` returns failed result, step without manifest uses existing behavior
  - [ ] 6.4 `tests/pipeline/test_execution_engine.py` (extend) — step with `manifest_path` applies manifest, step without manifest uses command, missing manifest file fails step
  - [ ] 6.5 `tests/pipeline/test_remediation_graph.py` (extend) — graph includes manifest_generation node between skeptic and dry_run

- [ ] Task 7: Tests — integration (AC: #4, #5, #6)
  - [ ] 7.1 `tests/pipeline/test_remediation_graph.py` (extend) — full graph with manifest_generation node: plan → skeptic → manifest_generation → dry_run → policy_gate
  - [ ] 7.2 Verify the manifest file is actually written to disk and readable by dry_run and execution_engine

## Dev Notes

### Story Intelligence Chain — Previous Story Context

**From Epic 3 Retrospective (origin of this story):**

This story was created as an action item during the Epic 3 retrospective. The retro identified that the planner produces natural-language remediation steps with `command` strings, but the dry-run stage only validates RBAC and admission — it cannot validate the actual resource content (field values, resource limits, labels). The manifest generation stage fills this gap: it takes the planner's natural-language steps, queries the cluster for current state, produces complete YAML manifests, and updates the execution path to apply deterministic artifacts instead of interpreted commands. The action item in sprint-status.yaml (epic 3, "Add manifest-generation pipeline stage story") is marked `done` — the story was added to the backlog. This story is the implementation.

**From Story 3.5 (Serialized Execution, Outcome Observation & Rollback):**

Story 3.5 is the most recent predecessor — it established:

- **`pipeline/execution_engine.py`** — `execute_remediation()` iterates over `plan.steps` and for each step with a `command`, calls `mcp_client.execute("apply_resource", {"command": step.command})`. This story modifies this loop to prefer `manifest_path` when available.
- **`pipeline/execution_dispatcher.py`** — Background loop that acquires the global lock, runs freshness gate → execute → observe. This story does NOT modify the dispatcher — manifest generation happens during planning (in the remediation graph), not during execution dispatch.
- **`models/execution.py`** — `ExecutionStepLog` records `command` and `output`. The command field should reflect whether a manifest or a raw command was used.
- **`pipeline/remediation_graph.py`** — Graph structure after 3.5 (planning only): `plan → skeptic_validation → dry_run → policy_gate → END`. Execution nodes (`freshness_gate`, `execute`, `observe`) are called by the dispatcher, not wired into the graph. This story inserts `manifest_generation` between `skeptic_validation` and `dry_run`.

**From Story 3.3 (Dry-Run Pre-Flight & Policy Gate):**

- **`pipeline/dry_run.py`** — `run_dry_run_preflight()` iterates steps, checks `_is_dry_runnable()` using `DRY_RUNNABLE_ACTIONS = {"apply", "create"}`. For dry-runnable steps, it calls `client.query("apply_resource", {"command": step.command, "resource": step.resource, "dry_run": "server"})`. This story modifies `_validate_step()` to send the manifest body when `step.manifest_path` is set.
- **`models/policy_gate.py`** — `DryRunStepResult` with `success`, `message`, `error_detail`, `skipped`. No changes needed to this model.
- **`DRY_RUNNABLE_ACTIONS`** — `frozenset({"apply", "create"})` — same set this story uses for manifest eligibility.

**From Story 3.2 (Remediation Skeptic):**

- The skeptic validates the plan BEFORE manifest generation. The skeptic sees the natural-language plan (steps with descriptions, commands, actions). Manifests are a post-skeptic artifact. This is important for `plan_hash()` — manifest fields MUST be excluded from the hash because they don't exist during skeptic validation.

**From Story 3.1 (Remediation Planner & Structured Plan):**

- **`models/remediation.py`** — `RemediationStep` fields: `order`, `description`, `command`, `resource`, `action`, `expected_outcome`. This story adds `manifest_path` and `manifest_generation_failed`. The `resource` field names the Kubernetes resource (e.g., `deployments/my-app`) — the manifest generator uses this to query current state.
- **`RemediationPlan.plan_hash()`** — Hashes `steps`, `blast_radius`, `rollback_plan`, `preconditions`, `estimated_risk`. The manifest fields in steps must be excluded from this hash.
- **`pipeline/mcp_readwrite_client.py`** — `ReadWriteMCPClient` with `query()` and `execute()` methods. The manifest generator uses `query("resources_get", ...)` to fetch current resource state, then `execute("apply_resource", {"manifest": yaml_content})` for execution.

### Architecture Compliance (CRITICAL)

| AD | Requirement | Impact on This Story |
|----|-------------|---------------------|
| AD-1 | Staged pipeline paradigm | Manifest generation is a new pipeline stage node in the remediation graph. It has typed input (RemediationPlan) and typed output (RemediationPlan with manifest annotations). |
| AD-2 | RBAC Airlock | Manifest generation uses the read-WRITE MCP Server (`cluster-admin` SA) to query current resource state — it needs to read the same resources it will later modify. |
| AD-4 | Shared types module | `RemediationStep` extension (manifest_path, manifest_generation_failed) lives in `models/remediation.py`. |
| AD-14 | Monorepo layout | New file `pipeline/manifest_generator.py` follows established pattern. |
| AD-19 | Canonical state machine | No new state transitions. Manifest generation runs within the `planning` state (between skeptic and policy gate). |
| AD-25 | Audit logging | Manifest generation results audit-logged via pipeline audit hook. |

### Technical Requirements

#### Manifest Generator Architecture

The manifest generator sits between the remediation skeptic and the dry-run pre-flight in the remediation graph. It takes the validated (post-skeptic) plan, produces YAML manifests for applicable steps, and passes the manifest-annotated plan to dry-run and execution.

```
plan → skeptic_validation → MANIFEST_GENERATION → dry_run → policy_gate → END
```

For each `apply` or `create` step:
1. Query the current resource state via `mcp_client.query("resources_get", {"resource": step.resource})`
2. Parse the current YAML
3. Apply the planned change (the `command` describes the change; the `description` provides context)
4. Write the complete YAML to `{temp_dir}/{incident_id}/step-{order}.yaml`
5. Set `step.manifest_path` to the file path

For imperative steps (restart, scale, patch, etc.):
- Skip with an honest report. These actions have no declarative YAML equivalent.

On failure:
- Set `manifest_generation_failed = True` on the step
- Log the error
- Continue to next step (do NOT fail the whole pipeline — the dry-run will catch it)

#### RemediationStep Extension

```python
class RemediationStep(BaseModel):
    order: int = Field(ge=1)
    description: str
    command: str | None = None
    resource: str
    action: str
    expected_outcome: str
    manifest_path: str | None = None
    manifest_generation_failed: bool = False
```

`plan_hash()` must exclude `manifest_path` and `manifest_generation_failed` from the hash. Current implementation hashes `steps` by calling `s.model_dump(mode="json")` on each step. The fix: explicitly exclude these fields when dumping for hash purposes.

#### Manifest File Layout

```
/tmp/aiops-manifests-{random}/
  {incident_id}/
    step-1.yaml
    step-3.yaml    # step-2 was imperative, skipped
```

Files are cleaned up after execution completes. The execution dispatcher should delete the temp directory after the observation phase (or on stale skip). This is handled by the execution dispatcher, not the manifest generator.

#### Dry-Run Changes

Current `_validate_step()` sends `{"command": step.command, "resource": step.resource, "dry_run": "server"}`. With manifests:

```python
async def _validate_step(client, step):
    if step.manifest_generation_failed:
        return DryRunStepResult(
            step_order=step.order,
            command=step.command or "",
            success=False,
            message="Manifest generation failed — cannot validate this step",
        )

    if step.manifest_path:
        manifest_content = Path(step.manifest_path).read_text()
        result = await client.query(
            "apply_resource",
            {"manifest": manifest_content, "dry_run": "server"},
        )
    else:
        result = await client.query(
            "apply_resource",
            {"command": step.command, "resource": step.resource, "dry_run": "server"},
        )
```

#### Execution Engine Changes

Current execution sends `{"command": step.command}`. With manifests:

```python
if step.manifest_path:
    manifest_content = Path(step.manifest_path).read_text()
    result = await mcp_client.execute(
        tool_name="apply_resource",
        arguments={"manifest": manifest_content},
    )
else:
    result = await mcp_client.execute(
        tool_name="apply_resource",
        arguments={"command": step.command},
    )
```

#### MCP Server apply_resource Tool

The kubernetes-mcp-server `apply_resource` tool supports both modes:
- `{"command": "kubectl apply -f ..."}` — interprets a command string
- `{"manifest": "apiVersion: v1\nkind: ..."}` — applies raw YAML content

When `manifest` is provided, the MCP server writes it to a temp file and runs `kubectl apply -f <temp_file>` (or equivalent API call). When `dry_run=server` is also set, it adds `--dry-run=server`.

### Library & Framework Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| pyyaml | latest | YAML parsing/serialization for manifest generation. Check if already in pyproject.toml — likely already a dependency via LangGraph or kubernetes tooling. If not, add it. |
| tempfile (stdlib) | N/A | Temp directory for manifest files. No new dependency. |
| pathlib (stdlib) | N/A | File path handling. No new dependency. |

All other packages (langgraph, pydantic, fastapi, asyncpg) are already in pyproject.toml from Epics 1–3.

### File Structure Requirements

#### Files to Create

| File | Purpose | Type |
|------|---------|------|
| `backend/src/pipeline/manifest_generator.py` | Manifest generation logic — query cluster, produce YAML, write to temp dir | NEW |
| `backend/tests/pipeline/test_manifest_generator.py` | Manifest generator unit tests | NEW |

#### Files to Modify

| File | Change | Type |
|------|--------|------|
| `backend/src/models/remediation.py` | Add `manifest_path`, `manifest_generation_failed` fields to `RemediationStep`; update `plan_hash()` to exclude new fields | UPDATE |
| `backend/src/pipeline/remediation_graph.py` | Add `manifest_generation_node`; insert between `skeptic_validation` and `dry_run` | UPDATE |
| `backend/src/pipeline/dry_run.py` | Check `manifest_path` / `manifest_generation_failed`; send manifest body when available | UPDATE |
| `backend/src/pipeline/execution_engine.py` | Check `manifest_path`; apply manifest when available | UPDATE |
| `backend/src/pipeline/remediation_runner.py` | Add SSE event handling for manifest generation stage | UPDATE |
| `backend/tests/models/test_remediation.py` | Test new fields, hash exclusion | UPDATE |
| `backend/tests/pipeline/test_dry_run.py` | Test manifest-based dry-run path | UPDATE |
| `backend/tests/pipeline/test_execution_engine.py` | Test manifest-based execution path | UPDATE |
| `backend/tests/pipeline/test_remediation_graph.py` | Test graph includes manifest_generation node | UPDATE |

### Dependency Direction (ENFORCED)

```
models/remediation.py → (nothing — leaf module)
pipeline/manifest_generator.py → models/remediation.py, pipeline/mcp_readwrite_client.py
pipeline/dry_run.py → models/remediation.py, models/policy_gate.py, pipeline/mcp_readwrite_client.py
pipeline/execution_engine.py → models/remediation.py, models/execution.py, pipeline/mcp_readwrite_client.py
pipeline/remediation_graph.py → pipeline/manifest_generator.py (via lazy import in node function)
```

- **NEVER**: `models/` imports from `pipeline/`, `api/`, or `db/`
- **NEVER**: Manifest generator uses the read-only MCP. It uses read-WRITE because it queries resources that may need `cluster-admin` access to read (e.g., secrets, configmaps in restricted namespaces).
- **ALLOWED**: `pipeline/manifest_generator.py` imports from `pipeline/mcp_readwrite_client.py`
- **ALLOWED**: `pipeline/dry_run.py` reads manifest files from disk
- **ALLOWED**: `pipeline/execution_engine.py` reads manifest files from disk

### Testing Requirements

**Unit tests** (`pytest -m unit`):

Model tests (`tests/models/test_remediation.py` — extend):
- `RemediationStep` defaults: `manifest_path` is None, `manifest_generation_failed` is False
- `RemediationStep` with manifest_path serializes/deserializes correctly
- `RemediationPlan.plan_hash()` excludes `manifest_path` and `manifest_generation_failed` — same plan with/without manifest fields produces identical hash
- Existing RemediationPlan tests still pass (backward compatibility)

Manifest generator tests (`tests/pipeline/test_manifest_generator.py`):
- `apply` step: queries resource, writes manifest, sets `manifest_path`
- `create` step: writes manifest for new resource, sets `manifest_path`
- Imperative step (`restart`): skipped, `manifest_path` stays None
- Informational step (no command): skipped
- MCP timeout: `manifest_generation_failed = True`, pipeline continues
- MCP error (resource not found): `manifest_generation_failed = True`
- YAML parse error: `manifest_generation_failed = True`
- Multiple steps: only eligible steps get manifests
- Temp directory is created scoped to incident ID
- Written YAML is valid and readable

Dry-run tests (`tests/pipeline/test_dry_run.py` — extend):
- Step with `manifest_path`: manifest content sent in `apply_resource` arguments
- Step with `manifest_generation_failed`: returns `DryRunStepResult(success=False)`
- Step without `manifest_path`: existing command-based behavior preserved
- Step with `manifest_path` but missing file: returns `DryRunStepResult(success=False)`

Execution engine tests (`tests/pipeline/test_execution_engine.py` — extend):
- Step with `manifest_path`: manifest content sent via `mcp_client.execute()`
- Step without `manifest_path`: existing command-based behavior preserved
- Step with `manifest_path` but missing file: step marked failed, execution stops

Graph tests (`tests/pipeline/test_remediation_graph.py` — extend):
- Graph includes `manifest_generation` node between `skeptic_validation` and `dry_run`
- State contains updated `remediation_plan` with manifest annotations after manifest_generation node

**Mock patterns:**
- Mock `ReadWriteMCPClient.query()` for resource reads — return canned YAML resource content
- Use `tmp_path` pytest fixture for temp directory (auto-cleanup)
- For dry-run/execution tests with manifests: write test YAML files to `tmp_path`, set `manifest_path` to their location

### Anti-Patterns / DO NOT

- **DO NOT** run manifest generation before the skeptic validates the plan. The skeptic evaluates the natural-language plan; manifests are a post-skeptic artifact. Graph order: `plan → skeptic → manifest_generation → dry_run → policy_gate`.
- **DO NOT** modify the `plan_hash()` to include manifest fields. Manifest path and generation status are post-skeptic metadata, not plan substance. Including them would break the skeptic's hash-stability comparison.
- **DO NOT** fail the entire pipeline if manifest generation fails for one step. Set `manifest_generation_failed = True` on the step and continue. The dry-run stage will report the failure.
- **DO NOT** use the read-only MCP for manifest generation. The manifest generator needs the read-write MCP Server because it queries the same resources it will later modify — these may require `cluster-admin` access.
- **DO NOT** implement manifest generation as an LLM agent. This is a deterministic operation: read current state → apply planned change → write YAML. No LLM involved.
- **DO NOT** clean up manifest temp directories in the manifest generator. Cleanup happens in the execution dispatcher after the full cycle (execution + observation) completes, or when freshness gate skips a stale remediation.
- **DO NOT** modify `models/policy_gate.py`, `models/diagnosis.py`, `models/execution.py`, or any model from a previous story besides `remediation.py`.
- **DO NOT** modify the execution dispatcher (`pipeline/execution_dispatcher.py`) — manifest generation happens during planning (in the remediation graph), not during execution dispatch.
- **DO NOT** modify the rollback API or rollback execution path. Rollback steps do not get manifests in this story.
- **DO NOT** change the skeptic validation in any way. The skeptic sees and evaluates the natural-language plan, unaware of manifests.
- **DO NOT** add manifest generation to the freshness gate, execution, or observation nodes that the dispatcher calls directly. Manifest generation is a graph node only.

### Project Structure Notes

All new/modified files align with AD-14 monorepo layout:
```
backend/src/
  models/
    remediation.py              # UPDATE: add manifest_path, manifest_generation_failed
  pipeline/
    manifest_generator.py       # NEW: manifest generation logic
    remediation_graph.py        # UPDATE: add manifest_generation_node
    dry_run.py                  # UPDATE: use manifest body when available
    execution_engine.py         # UPDATE: apply manifest when available
    remediation_runner.py       # UPDATE: SSE events for manifest generation
backend/tests/
  models/
    test_remediation.py         # UPDATE: test new fields, hash exclusion
  pipeline/
    test_manifest_generator.py  # NEW: manifest generator tests
    test_dry_run.py             # UPDATE: manifest-based dry-run tests
    test_execution_engine.py    # UPDATE: manifest-based execution tests
    test_remediation_graph.py   # UPDATE: graph includes manifest_generation
```

Estimated file count: 2 new + 7 modified = 9 files total (well within the 25-file story size limit).

### Latest Technology Notes

**kubernetes-mcp-server v0.0.66+ — resource operations:**
- `resources_get` — reads a resource (kubectl get equivalent). Returns YAML/JSON representation. Arguments: `{"resource": "deployments/my-app", "namespace": "default"}`. Used by manifest generator to read current state.
- `apply_resource` — applies a manifest. Supports both `{"command": "kubectl apply ..."}` and `{"manifest": "<yaml content>"}` modes. When `manifest` is provided, the MCP server writes it to a temp file and applies it. When `dry_run=server` is also set, adds `--dry-run=server`.

**PyYAML usage:**
- Use `yaml.safe_load()` for parsing cluster resource YAML (never `yaml.load()` without Loader)
- Use `yaml.dump()` with `default_flow_style=False` for readable output
- The `pyyaml` package may already be a transitive dependency. Check `pyproject.toml` — if not present, add it.

**Temp directory lifecycle:**
- `tempfile.mkdtemp(prefix="aiops-manifests-")` creates a unique directory under `/tmp`
- The directory persists across execution stages (manifest_generation → dry_run → execution)
- Cleanup responsibility: the execution dispatcher should delete the temp directory after the observation phase completes or when the freshness gate skips a stale remediation. Add cleanup logic to the dispatcher's existing finally block.

### References

- [Source: epics.md#Story 4.0] — Story requirements and acceptance criteria
- [Source: epics.md#Epic 4] — Learning Store & Fast-Path epic context
- [Source: ARCHITECTURE-SPINE.md#AD-1] — Staged pipeline paradigm (manifest generation is a new stage node)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — RBAC Airlock (manifest generator uses read-write MCP)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — Shared types module (RemediationStep extension)
- [Source: ARCHITECTURE-SPINE.md#AD-14] — Monorepo layout (new file follows pattern)
- [Source: sprint-status.yaml#action_items] — Epic 3 action item: "Add manifest-generation pipeline stage story" (status: done — story added to backlog)
- [Source: models/remediation.py] — Current RemediationStep model (order, description, command, resource, action, expected_outcome)
- [Source: pipeline/remediation_graph.py] — Current graph: plan → skeptic_validation → dry_run → policy_gate → END
- [Source: pipeline/dry_run.py] — `DRY_RUNNABLE_ACTIONS = {"apply", "create"}`, `_validate_step()` sends command to MCP
- [Source: pipeline/execution_engine.py] — `execute_remediation()` iterates steps, calls `mcp_client.execute("apply_resource", {"command": step.command})`
- [Source: pipeline/mcp_readwrite_client.py] — `ReadWriteMCPClient.query()` and `.execute()` methods
- [Source: project-context.md#Pipeline Paradigm Violations] — "NEVER skip the skeptic" — manifest generation is AFTER skeptic, not a replacement
- [Source: project-context.md#Security Anti-Patterns] — "NEVER bypass the policy gate" — manifests still pass through dry-run and policy gate

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Code Review Record

### Review Model Used

### Review Findings

### Decisions Needed / Decisions Taken

### Fixes Applied
