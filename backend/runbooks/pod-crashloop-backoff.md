# Pod CrashLoopBackOff

## Overview

A pod is repeatedly crashing and being restarted by the kubelet. Kubernetes
applies an exponential back-off delay (10s, 20s, 40s, ... up to 5 minutes)
between restart attempts. The pod status shows `CrashLoopBackOff`.

Related alerts: `KubePodCrashLooping`, `KubeContainerWaiting`,
`KubePodNotReady`.

## Symptoms

- `oc get pods` shows the pod in `CrashLoopBackOff` with a high restart count.
- Container logs show application errors or exit codes.
- Events on the pod show `BackOff` and `Killing` entries.
- Readiness/liveness probes may be failing.

## Diagnosis Steps

### 1. Inspect Pod Status and Events

```bash
oc get pod <pod-name> -n <namespace> -o wide
oc describe pod <pod-name> -n <namespace>
```

Check the `Events` section for:
- `BackOff` — kubelet is delaying the restart.
- `FailedMount` — volume mount failure preventing start.
- `Failed` — container exited with a non-zero exit code.

Key fields in `Status.containerStatuses`:
- `lastState.terminated.exitCode` — the exit code from the last crash.
- `lastState.terminated.reason` — `Error`, `OOMKilled`, `ContainerCannotRun`.
- `restartCount` — total number of restarts.

### 2. Check Container Logs

```bash
oc logs <pod-name> -n <namespace> --previous
oc logs <pod-name> -n <namespace> -c <container> --previous
```

The `--previous` flag retrieves logs from the last terminated instance.

### 3. Check Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success (should not CrashLoop — check restart policy) |
| 1 | Application error |
| 126 | Command not executable |
| 127 | Command not found |
| 137 | SIGKILL (usually OOMKilled) |
| 139 | SIGSEGV (segmentation fault) |
| 143 | SIGTERM (graceful shutdown failed) |

### 4. Check for OOMKilled

```bash
oc get pod <pod-name> -n <namespace> -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'
```

If `OOMKilled`:
- Container exceeded its memory limit.
- Check `resources.limits.memory` vs actual consumption.
- Look for memory leaks in the application.

```bash
oc adm top pod <pod-name> -n <namespace> --containers
```

### 5. Check Image and Configuration

```bash
oc get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].image}'
```

- Verify the image tag exists and is pullable.
- Check environment variables and ConfigMaps for misconfiguration.
- Verify Secrets referenced by the pod exist and contain expected keys.

### 6. Check Liveness/Readiness Probes

Aggressive probe settings can cause premature restarts:

```bash
oc get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].livenessProbe}'
```

- `initialDelaySeconds` too short for slow-starting apps.
- `timeoutSeconds` too short for intermittently loaded apps.
- Probe endpoint returning errors.

## Root Cause Categories

| Category | Indicators |
|----------|-----------|
| OOMKilled | Exit code 137, reason `OOMKilled` in container status |
| Application error | Exit code 1, error messages in `--previous` logs |
| Missing dependency | Connection refused / timeout to database or service in logs |
| Configuration error | Missing env var, invalid config file, Secret not found |
| Image issue | `ImagePullBackOff`, wrong tag, binary not found (exit 127) |
| Probe misconfiguration | Liveness probe killing healthy but slow container |
| Volume mount failure | `FailedMount` event, PVC not bound |

## Remediation

### Immediate

1. **Read previous logs**: `oc logs <pod> -n <ns> --previous` to find the
   crash reason.
2. **OOMKilled**: Increase `resources.limits.memory` in the Deployment.
3. **Missing dependency**: Verify downstream services are running.
4. **Config error**: Check ConfigMaps, Secrets, and environment variables.
5. **Probe failures**: Increase `initialDelaySeconds` and `timeoutSeconds`.

### Long-term

- Set appropriate resource requests and limits based on profiling.
- Implement health-check endpoints that reflect real readiness.
- Add startup probes for slow-starting containers.
- Use PodDisruptionBudgets to maintain availability during disruptions.
- Configure alerts on restart count thresholds to catch issues early.
