# Epic 2: AI Diagnosis Pipeline — User Acceptance Test

## UAT Metadata

| Field | Value |
|-------|-------|
| Epic | 2 — AI Diagnosis Pipeline |
| Date | 2026-08-09 |
| Environment | etl6 (kube context: `etl6`) |
| Deployment Method | Helm chart (`charts/openshift-ai-ops/`) |
| Tester | rspazzol |

## Scope

This UAT validates the end-to-end behavior of the AI Diagnosis Pipeline (Epic 2) deployed to a live OpenShift cluster. The test involves:

1. Deploying the application to the `etl6` cluster using the Helm chart
2. Generating an artificial alert to trigger the pipeline
3. Observing system behavior through the diagnosis stages

## Pre-Requisites

- [ ] `kubectl` / `oc` context set to `etl6`
- [ ] Helm 3 installed
- [ ] LLM endpoint configured and accessible from the cluster
- [ ] MCP Server (read-only) accessible with `cluster-reader` ServiceAccount
- [ ] PostgreSQL with pgvector available (deployed via chart)

---

## Step 1: Deploy to etl6

### Actions

```bash
# Verify context
kubectl config use-context etl6
kubectl config current-context

# Deploy via Helm
helm upgrade --install openshift-ai-ops charts/openshift-ai-ops/ \
  --namespace openshift-ai-ops \
  --create-namespace \
  -f <values-override-if-needed>
```

### Expected Result

- All pods in `openshift-ai-ops` namespace reach `Running` state
- Health check (`GET /healthz`) returns 200
- Database migrations applied successfully

### Actual Result

Deployment required several iterations to resolve:

1. **No Containerfile existed** — Created `backend/Containerfile` and `skills/Containerfile`
2. **No Makefile existed** — Created root `Makefile` with build/test/image targets
3. **Images pushed to** `quay.io/raffaelespazzoli/openshift-ai-ops-{backend,skills}:0.1.0`
4. **pgvector extension** — Had to manually `CREATE EXTENSION vector` before migrations
5. **Alembic migrations** — Ran successfully (7 migrations) via `kubectl exec`
6. **RHOKP access key secret** — Created placeholder; Solr pod still in Error state (non-blocking for Epic 2 UAT)
7. **Runbook ingestion failed** — Expected; requires real LLM API key for embeddings
8. **Health check** — Returns `200 {"status":"healthy","database":"connected"}`

**Issues found during deployment (to fix):**
- Helm chart needs an init container or Job to run `CREATE EXTENSION vector` + Alembic migrations
- `alembic.ini` hardcodes localhost; env.py uses `DATABASE_URL` but the Helm chart doesn't set it
- MCP readonly readiness probe fails (Streamable HTTP requires `Mcp-Session-Id` header on GET)
- Backend deployment needs `LLM_ENDPOINT`, `LLM_MODEL`, `LLM_API_KEY` env vars from Secret

### Pod Status

```
NAME                                             READY   STATUS    RESTARTS
openshift-ai-ops-backend-68d68f8bb-7f8r5         1/1     Running   0
openshift-ai-ops-mcp-readonly-6d8fb478dd-mksgl   0/1     Running   0  (readiness probe issue)
openshift-ai-ops-okp-mcp-cf8b7c574-psr44         1/1     Running   0
openshift-ai-ops-postgresql-0                    1/1     Running   0
openshift-ai-ops-solr-0                          0/1     Error     4  (missing real access key)
```

---

## Step 2: Generate Artificial Alert

### Actions

Send a simulated AlertManager webhook payload to the backend webhook endpoint.

```bash
curl -X POST http://<backend-route>/api/v1/webhooks/alertmanager \
  -H "Content-Type: application/json" \
  -d '{
    "version": "4",
    "groupKey": "test-uat-epic2",
    "status": "firing",
    "receiver": "openshift-ai-ops",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "KubePodCrashLooping",
          "namespace": "test-app",
          "pod": "test-app-deployment-abc123",
          "severity": "warning",
          "container": "app"
        },
        "annotations": {
          "summary": "Pod test-app/test-app-deployment-abc123 is crash looping",
          "description": "Pod test-app/test-app-deployment-abc123 (app) is restarting 5.2 times / 10 minutes."
        },
        "startsAt": "2026-08-09T21:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "fingerprint": "uat-epic2-crashloop-001"
      }
    ]
  }'
```

### Expected Result

- HTTP 200 returned within 500ms
- Incident created in `received` state
- Alert fingerprint, labels, annotations persisted

### Actual Result

- **HTTP 200 in 163ms** (well under 500ms SLA)
- Incident created: `2c52184e-a360-4c6f-b3ae-8e6474a90556`, state=`received`
- Alert persisted: `5aa2e37d-b703-41f9-acc7-66157821cdb1`, fingerprint=`abc123def456`
- Correlation group created with 300s settling window (correct for warning severity)

---

## Step 3: Observe Correlation & Queueing

### Expected Behavior

1. Incident transitions: `received` → `correlating` → `queued`
2. Settling window for warning severity: 5 minutes
3. After settling, Root-Cause Event sealed and enqueued in priority queue

### Observations

Pipeline completed end-to-end. Timeline:

| Time | Event |
|------|-------|
| 23:07:59 | Alert received, incident created (state: `received`) |
| 23:07:59 | Correlation group created, settling window: 300s |
| 23:13:07 | Group sealed (5 min elapsed), RCE enqueued (priority: 49.99) |
| 23:13:12 | Dequeued, dispatched to diagnosis pipeline |
| 23:13:13 | Orchestrator starts diagnosis (attempt 1) |
| 23:13:19 | MCP queries fail (readiness probe issue), evidence gaps recorded |
| 23:13:28 | Runbook search fails (API key restricted to gpt-oss-120b only, no embedding model) |
| 23:14:06 | Attempt 1 fails validation (root-cause code not slash-delimited) |
| 23:14:15 | Attempt 2 fails (LLM returns non-JSON channel tokens) |
| 23:14:42 | Attempt 3 fails (structured output no parsed field) |
| 23:14:42 | Completeness gate exhausted retries — passes with evidence gap |
| 23:14:42 | Skeptic validation starts (original hash: `248d836bb2299a98`) |
| 23:15:03 | Skeptic LLM call succeeds |
| 23:15:27 | Skeptic round 1 complete: **hash unchanged → PASSED** |
| 23:15:27 | **Immutable Diagnosis Artifact sealed** |
| 23:15:27 | Incident state: `diagnosed` |

**Final state verified via PostgreSQL:**
- Incident state: `diagnosed`
- Immutable Diagnosis: root_cause=`unknown`, failure_mode=`unclassified`, confidence=`0.0`
- Skeptic verdict: `passed=true`, 1 round, hash stable

**Issues encountered:**
1. MCP Server not responding (readiness probe fails due to Streamable HTTP requiring session header)
2. LLM model (`gpt-oss-120b`) doesn't support structured output reliably — returns channel tokens/empty content
3. Embedding model access denied (API key restricted to `gpt-oss-120b` only)
4. Orchestrator fallback diagnosis produced `unknown/unclassified` with confidence 0.0

### Expected Behavior (Story 2.1 — LangGraph Pipeline & MCP Integration)

- [ ] Incident transitions from `queued` to `diagnosing`
- [ ] LangGraph checkpoint persisted to PostgreSQL
- [ ] MCP Server queried via Streamable HTTP (read-only)
- [ ] Structured Diagnosis Object produced with required fields

### Expected Behavior (Story 2.2 — Orchestrator & Runbook Enrichment)

- [ ] Orchestrator forms hypothesis from alert metadata
- [ ] Cluster queried via read-only MCP Server for evidence
- [ ] Runbook similarity search performed against pgvector
- [ ] Confidence score assigned (0–1)
- [ ] Completeness gate evaluates all correlated alerts addressed

### Expected Behavior (Story 2.3 — RHOKP & Learning Store)

- [ ] RHOKP queried via okp-mcp (Solr + Streamable HTTP)
- [ ] Learning Store queried (empty results on fresh deployment is OK)
- [ ] Evidence array distinguishes source of each artifact

### Expected Behavior (Story 2.4 — Skeptic & Immutable Handoff)

- [ ] Skeptic receives Structured Diagnosis Object
- [ ] Structured challenge produced (alternative hypotheses, evidence gaps, weaknesses)
- [ ] Orchestrator responds to challenge
- [ ] Root-cause hash compared before/after
- [ ] If hash unchanged → diagnosis passes
- [ ] If hash changed → one re-challenge round, then pass regardless
- [ ] Challenge and response persisted in audit trail
- [ ] Immutable Diagnosis Artifact created (read-only)
- [ ] Incident transitions from `diagnosing` to `diagnosed`

### Observations

> _To be filled during UAT execution_

---

## Step 5: Verify Final State

### Checks

- [ ] Incident in `diagnosed` state (pipeline stops here — Epic 3 not implemented)
- [ ] Immutable Diagnosis Artifact persisted and readable via API
- [ ] Structured Diagnosis Object contains:
  - `root_cause_component` (slash-delimited taxonomy code)
  - `failure_mode`
  - `causal_chain` (array)
  - `affected_resources` (array)
  - `evidence` (array with source attribution)
  - `evidence_gaps` (array, may be empty)
  - `confidence` (float 0–1)
- [ ] Skeptic challenge/response in audit trail
- [ ] SSE events emitted for each stage transition
- [ ] Prometheus metrics updated (diagnosis latency, LLM call latency)
- [ ] Structured JSON logs produced for all pipeline stages

### API Verification

```bash
# Get incident detail
curl -H "Authorization: Bearer <token>" \
  http://<backend-route>/api/v1/incidents/<incident-id>

# Get SSE events (observe in separate terminal during pipeline execution)
curl -N -H "Authorization: Bearer <token>" \
  http://<backend-route>/api/v1/events
```

### Observations

> _To be filled during UAT execution_

---

## Results Summary

| Criterion | Pass/Fail | Notes |
|-----------|-----------|-------|
| Helm deployment successful | | |
| Webhook acknowledged <500ms | | |
| Incident state machine transitions correct | | |
| MCP Server queried (read-only) | | |
| Runbook RAG retrieval functional | | |
| RHOKP knowledge retrieval functional | | |
| Structured Diagnosis Object valid schema | | |
| Skeptic challenge/response completed | | |
| Immutable Diagnosis Artifact created | | |
| LangGraph checkpoints persisted | | |
| SSE events delivered | | |
| Prometheus metrics exposed | | |
| Structured JSON logging | | |

## Issues Found

> _To be filled during UAT execution_

## UAT Verdict

- [ ] **PASS** — Epic 2 acceptance criteria met in live environment
- [ ] **FAIL** — Issues require resolution before acceptance

---

## Notes

> _Free-form observations, screenshots, log snippets, etc._
