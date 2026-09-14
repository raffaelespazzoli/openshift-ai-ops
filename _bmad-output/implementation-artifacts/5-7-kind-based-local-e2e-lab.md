# Story 5.7: Kind-Based Local E2E Lab

Status: ready-for-dev

## Story

As a developer,
I want a single-command local lab that deploys the full stack (kind cluster, Prometheus, AlertManager, and the application Helm chart) on my laptop,
so that I can trigger real alerts and watch the end-to-end pipeline (webhook → correlation → diagnosis → remediation → UI) without needing access to a remote OpenShift cluster.

## Context

The project has five integration test layers (unit, DB, API, pipeline, MCP) that all run with mocked dependencies. E2E testing with real cluster components was deferred at post-Epic 3 because it required "a dedicated test cluster." A local kind cluster eliminates that blocker.

This story builds the **lab infrastructure only** — setup scripts, Helm overlay, alert fixtures, and Makefile targets. Automated test assertions (pytest-based E2E test harness) are a separate follow-up story.

### Dependencies

- Epic 1–5 complete (backend, pipeline, frontend, Helm chart all exist)
- Multi-provider LLM refactor landed (supports `LLM_PROVIDER=openai|anthropic|ollama`)
- `kind` and `helm` CLI tools installed on the developer's machine

## Acceptance Criteria

1. **Given** a developer with `kind` and `helm` installed **When** they run `make lab-up` **Then** a kind cluster is created with the configuration from `lab/kind-cluster.yaml`, kube-prometheus-stack is installed with AlertManager configured to webhook into the backend, and the application Helm chart is deployed using `charts/openshift-ai-ops/` with the `values-kind.yaml` overlay — all within a single automated script.

2. **Given** a running lab cluster **When** the developer runs `make lab-trigger` **Then** a test workload is deployed that causes at least one Prometheus alert to fire (e.g., `KubePodCrashLooping` via a crash-loop pod), and the alert is delivered to the backend via AlertManager webhook within 3 minutes.

3. **Given** a running lab cluster **When** the developer runs `make lab-teardown` **Then** the kind cluster and all associated resources are deleted cleanly.

4. **Given** the `values-kind.yaml` overlay **Then** it disables the OpenShift oauth-proxy sidecar on the frontend, replaces the Route with a NodePort or port-forward instruction, sets `AUTH_DISABLED=true` on the backend, and configures the LLM endpoint for local Ollama (`LLM_PROVIDER=ollama`, `LLM_ENDPOINT=http://host.docker.internal:11434`).

5. **Given** the kube-prometheus-stack deployment **Then** AlertManager is configured with a webhook receiver that sends firing and resolved alerts to `http://<backend-service>:8000/api/v1/webhooks/alertmanager` using the standard v4 payload format.

6. **Given** a running lab cluster **When** the developer runs `make lab-status` **Then** the script displays the health of all components (kind cluster, Prometheus, AlertManager, backend, frontend, PostgreSQL) and provides the URL/port-forward commands to access the frontend and Grafana.

7. **Given** the lab setup **Then** a `lab/prometheusrules-test.yaml` file exists containing at least two custom PrometheusRules with low thresholds that fire on demand (e.g., a rule that fires when a specific ConfigMap exists, and a rule that fires on any pod in a `lab-alerts` namespace), enabling developers to trigger alerts without deploying crash-loop workloads.

8. **Given** the lab documentation **Then** a `lab/README.md` explains prerequisites (kind, helm, ollama), the available Makefile targets, how to trigger alerts, how to switch LLM providers, and troubleshooting tips for common issues (port conflicts, resource limits).

## Technical Notes

### File Structure

```
lab/
  kind-cluster.yaml           # kind cluster config (1 control-plane, port mappings)
  values-kind.yaml             # Helm overlay for kind (no oauth-proxy, NodePort, AUTH_DISABLED)
  prometheus-values.yaml       # kube-prometheus-stack values (AlertManager webhook receiver)
  prometheusrules-test.yaml    # Custom low-threshold PrometheusRules for on-demand alerts
  crashloop-pod.yaml           # Test workload that crash-loops (for KubePodCrashLooping)
  README.md                    # Lab documentation
scripts/
  lab-setup.sh                 # Orchestrates: kind create, helm install prometheus, helm install app
  lab-teardown.sh              # kind delete cluster
  lab-trigger.sh               # Deploy crash-loop pod or apply test PrometheusRules
  lab-status.sh                # Health check and URL display
```

### Makefile Targets

```makefile
lab-up:       scripts/lab-setup.sh
lab-down:     scripts/lab-teardown.sh
lab-trigger:  scripts/lab-trigger.sh
lab-status:   scripts/lab-status.sh
```

### kube-prometheus-stack AlertManager Configuration

The AlertManager webhook receiver should be configured in `lab/prometheus-values.yaml`:

```yaml
alertmanager:
  config:
    route:
      receiver: openshift-ai-ops
      group_by: ['alertname', 'namespace']
      group_wait: 10s
      group_interval: 30s
      repeat_interval: 5m
    receivers:
      - name: openshift-ai-ops
        webhook_configs:
          - url: http://openshift-ai-ops-backend:8000/api/v1/webhooks/alertmanager
            send_resolved: true
```

### Kind Cluster Configuration

- Single control-plane node (sufficient for lab)
- Extra port mappings for NodePort access to frontend and Grafana
- `extraMounts` not needed — all images pulled from registries

### LLM Configuration

The lab defaults to local Ollama (`LLM_PROVIDER=ollama`). Developers can override by setting environment variables before `make lab-up`:

```bash
# Default: local Ollama
make lab-up

# With Anthropic Claude
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-... make lab-up

# With OpenAI-compatible endpoint
LLM_PROVIDER=openai LLM_ENDPOINT=https://api.openai.com/v1 LLM_API_KEY=sk-... make lab-up
```

### What This Story Does NOT Include

- **No automated test assertions** — no `backend/tests/e2e/` directory, no pytest fixtures, no pass/fail gates. That is a follow-up story.
- **No CI integration** — no GitHub Actions workflow. The lab is developer-local only.
- **No multi-node cluster** — single control-plane is sufficient for validating the pipeline.
- **No persistent storage** — lab data is ephemeral. `make lab-down` destroys everything.

### OpenShift-Specific Components to Disable/Replace

| OpenShift Component | Kind Replacement |
|-------------------|-----------------|
| oauth-proxy sidecar | Disabled; `AUTH_DISABLED=true` |
| Route | NodePort + port-forward |
| `registry.redhat.io` images | Not deployed (oauth-proxy skipped) |
| ClusterVersion API | Not present; `_get_cluster_ocp_version()` returns fallback — no impact |

## Out of Scope

- Automated E2E test harness (follow-up story)
- CI pipeline integration (follow-up story)
- Multi-node or HA cluster configurations
- Persistent lab data across teardown/setup cycles
- Eval harness integration (Epic 7)
