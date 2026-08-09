# Node Not Ready

## Overview

A Kubernetes/OpenShift node has entered the `NotReady` state, meaning the
kubelet is no longer posting healthy status updates to the API server.
Pods on the affected node may be evicted after the pod-eviction timeout.

Related alerts: `KubeNodeNotReady`, `KubeNodeUnreachable`,
`NodeNetworkUnavailable`.

## Symptoms

- `oc get nodes` shows one or more nodes with status `NotReady`.
- The node condition `Ready` is `False` or `Unknown`.
- Pods scheduled on the node transition to `Terminating` or `Unknown`.
- Cluster operators that run DaemonSets may report degraded status.

## Diagnosis Steps

### 1. Identify the Affected Node

```bash
oc get nodes -o wide
oc describe node <node-name>
```

Look at the `Conditions` section for:
- `Ready=False` — kubelet is unhealthy.
- `Ready=Unknown` — API server lost contact with the kubelet.
- `MemoryPressure`, `DiskPressure`, `PIDPressure` — resource exhaustion.

### 2. Check Kubelet Status

SSH into the node (or use `oc debug node/<node-name>`) and inspect:

```bash
chroot /host
systemctl status kubelet
journalctl -u kubelet --since "30 minutes ago" | tail -100
```

Common kubelet failure reasons:
- Certificate expiration (`x509: certificate has expired`).
- Container runtime not responding (`PLEG is not healthy`).
- Disk pressure causing eviction manager to shut down.

### 3. Check Container Runtime

```bash
crictl info
crictl ps -a | head -20
systemctl status crio
```

If CRI-O is unresponsive, pods cannot start or report status.

### 4. Check System Resources

```bash
free -h
df -h /var/lib/containers /var/log
top -b -n1 | head -20
```

- Memory exhaustion can cause OOM kills of kubelet or runtime.
- Disk full on `/var/lib/containers` prevents image pulls.
- High CPU can delay kubelet heartbeats beyond the node-monitor grace period.

### 5. Check Network Connectivity

```bash
curl -k https://<api-server>:6443/healthz
ping <other-node-ip>
```

If the node cannot reach the API server, the node-lifecycle controller
marks it `NotReady` after `node-monitor-grace-period` (default 40s).

## Root Cause Categories

| Category | Indicators |
|----------|-----------|
| Kubelet crash | `systemctl status kubelet` shows `inactive` or `failed` |
| Certificate expiry | `x509: certificate has expired` in kubelet journal |
| CRI-O hang | `crictl info` times out, CRI-O systemd unit not running |
| Resource exhaustion | MemoryPressure/DiskPressure conditions `True` |
| Network partition | Cannot reach API server, other nodes unreachable |
| Kernel panic | Node unreachable on SSH, requires IPMI/BMC console |

## Remediation

### Immediate

1. **Cordon** the node to stop new scheduling: `oc adm cordon <node>`.
2. **Drain** workloads if the node is still partially responsive:
   `oc adm drain <node> --ignore-daemonsets --delete-emptydir-data`.
3. If kubelet is stopped, restart it: `systemctl restart kubelet`.
4. If CRI-O hung, restart: `systemctl restart crio && systemctl restart kubelet`.
5. If disk full, clean container storage:
   `crictl rmi --prune && podman system prune -af`.

### Long-term

- Set up monitoring alerts for disk and memory usage thresholds.
- Enable automatic certificate rotation (`rotateCertificates: true`).
- Configure appropriate resource requests/limits to prevent noisy-neighbor
  exhaustion.
- Use MachineHealthCheck CRDs to auto-remediate unhealthy nodes.
