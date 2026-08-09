# etcd Slow Disk fsync

## Overview

The etcd cluster backing the OpenShift control plane is experiencing slow
WAL (Write-Ahead Log) fsync operations. etcd uses fdatasync to persist
committed entries; when 99th-percentile latency exceeds 10 ms, the cluster
may fail to meet its leader-election and heartbeat deadlines, leading to
leader elections, request timeouts, and potential data-plane disruption.

Related alerts: `etcdHighFsyncDurations`, `etcdHighCommitDurations`,
`etcdMemberCommunicationSlow`, `etcdNoLeader`, `etcdGRPCRequestsSlow`.

## Symptoms

- Prometheus alert `etcdHighFsyncDurations` fires when `histogram_quantile(0.99,
  rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m]))` exceeds 0.01 (10 ms).
- etcd logs contain `slow fdatasync` or `took too long` warnings.
- API server latency increases — `kubectl` / `oc` commands hang or time out.
- Frequent etcd leader elections visible in `etcd_server_leader_changes_seen_total`.
- Cluster operators degrade because the API server cannot write to etcd.

## Diagnosis Steps

### 1. Confirm etcd Health

```bash
oc get etcd -o jsonpath='{.items[0].status.conditions}'
oc get pods -n openshift-etcd -l app=etcd
```

Check for `EtcdMembersAvailable` and `EtcdMembersDegraded` conditions.

### 2. Check fsync Latency Metrics

```bash
oc exec -n openshift-etcd etcd-<node> -c etcd -- \
  etcdctl endpoint status --cluster -w table
```

Or query Prometheus:

```promql
histogram_quantile(0.99,
  rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m])
)
```

Healthy clusters show p99 fsync under 10 ms. Values above 50 ms indicate
serious disk I/O issues.

### 3. Inspect etcd Logs

```bash
oc logs -n openshift-etcd etcd-<node> -c etcd --since=30m | grep -i "slow\|took too long\|overloaded"
```

Common log patterns:
- `slow fdatasync: took 150ms, expected-duration 10ms` — disk latency spike.
- `apply request took too long` — leader cannot commit fast enough.
- `elected leader` / `lost leader` — frequent leader changes.

### 4. Check Disk I/O on etcd Nodes

SSH into the control-plane node or use `oc debug node/<node>`:

```bash
chroot /host
iostat -xz 5 3
```

Look at the device hosting `/var/lib/etcd`:
- `await` > 10 ms — I/O wait is too high.
- `%util` near 100% — disk is saturated.
- `w/s` — high write rate may indicate noisy neighbor or undersized disk.

```bash
fio --name=wal-test --filename=/var/lib/etcd/fio-test \
    --rw=write --bs=2300 --fdatasync=1 --runtime=30 \
    --ioengine=sync --size=22m
```

The fdatasync p99 should be below 10 ms per Red Hat's guidance.

### 5. Check for Noisy Neighbors

On virtualized or cloud infrastructure:
- Other VMs on the same hypervisor may saturate the storage backend.
- Check if the storage tier (e.g., gp2 vs gp3, Standard vs Premium SSD)
  meets etcd IOPS and throughput requirements.
- Network-attached storage (NAS/NFS) is not supported for etcd.

### 6. Check Database Size and Compaction

```bash
oc exec -n openshift-etcd etcd-<node> -c etcd -- \
  etcdctl endpoint status --cluster -w table
```

- `DB SIZE` exceeding 4 GiB indicates missing compaction or defragmentation.
- Large databases increase fsync latency due to larger WAL writes.

```bash
oc exec -n openshift-etcd etcd-<node> -c etcd -- \
  etcdctl compact $(etcdctl endpoint status -w json | jq '.[0].Status.header.revision')
oc exec -n openshift-etcd etcd-<node> -c etcd -- \
  etcdctl defrag --cluster
```

## Root Cause Categories

| Category | Indicators |
|----------|-----------|
| Slow storage | fio fdatasync p99 > 10 ms, `await` high in iostat |
| Disk saturation | `%util` near 100%, high `w/s` from other workloads |
| Wrong storage type | NFS, network-attached, or low-tier cloud disk |
| Database bloat | DB size > 4 GiB, no recent compaction |
| Noisy neighbor | Shared hypervisor, burst-credit exhaustion (e.g., gp2) |
| Network latency | Cross-AZ etcd members, slow inter-member RTT |

## Remediation

### Immediate

1. **Check if compaction is needed**: run `etcdctl compact` + `etcdctl defrag`
   on all members sequentially.
2. **Verify disk type**: ensure etcd volume uses SSD-backed storage with
   sustained IOPS (not burst-only).
3. **Move noisy workloads**: if non-control-plane pods share the disk,
   use node selectors or taints to isolate etcd nodes.

### Long-term

- Use dedicated SSD-backed volumes for `/var/lib/etcd` meeting Red Hat's
  recommended minimum of 50 sequential IOPS at p99 < 10 ms fdatasync.
- On cloud platforms, use provisioned-IOPS storage classes (gp3 with
  baseline IOPS, Premium SSD v2, etc.).
- Enable automatic defragmentation via the etcd operator's
  `defragmentation-schedule` setting.
- Monitor `etcd_disk_wal_fsync_duration_seconds` and set alerting thresholds
  at p99 > 5 ms for early warning.
- Keep etcd members in the same availability zone or ensure low-latency
  networking between members (< 2 ms RTT).
