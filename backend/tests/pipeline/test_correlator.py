"""Unit tests for the five-layer correlation engine.

Tests cover:
- Layer 1 (dedup): duplicate fingerprint detection
- Layer 2 (namespace+temporal): same namespace within window
- Layer 3 (label+temporal): shared node/instance/component within window
- Layer 4 (subsystem dependency): cascade-related alerts
- Layer 5 (learning store): graceful None return
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.root_cause_event import CorrelationLayer
from src.pipeline.correlator import (
    correlate_label_temporal,
    correlate_learning_store,
    correlate_namespace_temporal,
    correlate_subsystem_dependency,
)


def _make_group(
    namespace: str | None = None,
    labels: dict | None = None,
    settling_window: int = 300,
    last_alert_ago_seconds: int = 10,
    created_ago_seconds: int = 60,
) -> dict:
    """Create a mock open correlation group for testing."""
    now = datetime.now(timezone.utc)
    group_id = uuid.uuid4()
    member_labels = labels or {}
    if namespace:
        member_labels.setdefault("namespace", namespace)

    return {
        "id": group_id,
        "state": "open",
        "settling_window_seconds": settling_window,
        "created_at": now - timedelta(seconds=created_ago_seconds),
        "last_alert_at": now - timedelta(seconds=last_alert_ago_seconds),
        "max_age_at": now + timedelta(seconds=settling_window * 3 - created_ago_seconds),
        "members": [
            {
                "alert_id": uuid.uuid4(),
                "incident_id": uuid.uuid4(),
                "joined_at": now - timedelta(seconds=last_alert_ago_seconds),
                "fingerprint": "existing-fp",
                "labels": member_labels,
                "status": "firing",
            }
        ],
    }


class TestDedupLayer:
    """Layer 1: Deduplication tests (uses DB mock)."""

    @pytest.mark.unit
    async def test_duplicate_fingerprint_detected(self):
        """Duplicate fingerprint returns True from check_dedup."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=True)

        from src.db.correlation import check_dedup
        result = await check_dedup(mock_conn, "existing-fingerprint")
        assert result is True

    @pytest.mark.unit
    async def test_new_fingerprint_not_duplicate(self):
        """New fingerprint returns False from check_dedup."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=False)

        from src.db.correlation import check_dedup
        result = await check_dedup(mock_conn, "brand-new-fingerprint")
        assert result is False


class TestNamespaceTemporalLayer:
    """Layer 2: Namespace + temporal correlation."""

    @pytest.mark.unit
    async def test_same_namespace_within_window_groups(self):
        """Alert in same namespace within settling window should be grouped."""
        group = _make_group(namespace="openshift-monitoring", settling_window=300, last_alert_ago_seconds=10)
        alert_labels = {"namespace": "openshift-monitoring", "alertname": "HighMemory"}

        result = await correlate_namespace_temporal(alert_labels, [group])
        assert result == group["id"]

    @pytest.mark.unit
    async def test_different_namespace_no_group(self):
        """Alert in different namespace should NOT be grouped."""
        group = _make_group(namespace="openshift-monitoring")
        alert_labels = {"namespace": "openshift-etcd", "alertname": "EtcdSlowDisk"}

        result = await correlate_namespace_temporal(alert_labels, [group])
        assert result is None

    @pytest.mark.unit
    async def test_same_namespace_expired_window_no_group(self):
        """Alert in same namespace but after settling window expiry should NOT be grouped."""
        group = _make_group(
            namespace="openshift-monitoring",
            settling_window=60,
            last_alert_ago_seconds=120,
            created_ago_seconds=200,
        )
        alert_labels = {"namespace": "openshift-monitoring"}

        result = await correlate_namespace_temporal(alert_labels, [group])
        assert result is None

    @pytest.mark.unit
    async def test_no_namespace_label_no_group(self):
        """Alert without namespace label should not match namespace layer."""
        group = _make_group(namespace="openshift-monitoring")
        alert_labels = {"alertname": "SomeAlert"}

        result = await correlate_namespace_temporal(alert_labels, [group])
        assert result is None


class TestLabelTemporalLayer:
    """Layer 3: Label overlap + temporal correlation."""

    @pytest.mark.unit
    async def test_shared_node_within_window_groups(self):
        """Shared 'node' label within settling window should group."""
        group = _make_group(labels={"node": "worker-1", "namespace": "ns1"})
        alert_labels = {"node": "worker-1", "alertname": "DiskPressure"}

        result = await correlate_label_temporal(alert_labels, [group])
        assert result == group["id"]

    @pytest.mark.unit
    async def test_shared_instance_within_window_groups(self):
        """Shared 'instance' label within settling window should group."""
        group = _make_group(labels={"instance": "10.0.1.5:9090"})
        alert_labels = {"instance": "10.0.1.5:9090", "alertname": "HighCPU"}

        result = await correlate_label_temporal(alert_labels, [group])
        assert result == group["id"]

    @pytest.mark.unit
    async def test_shared_component_within_window_groups(self):
        """Shared 'component' label within settling window should group."""
        group = _make_group(labels={"component": "etcd"})
        alert_labels = {"component": "etcd", "alertname": "EtcdHighLatency"}

        result = await correlate_label_temporal(alert_labels, [group])
        assert result == group["id"]

    @pytest.mark.unit
    async def test_no_shared_labels_no_group(self):
        """No shared correlation labels should not group."""
        group = _make_group(labels={"node": "worker-1"})
        alert_labels = {"node": "worker-2", "alertname": "DifferentNode"}

        result = await correlate_label_temporal(alert_labels, [group])
        assert result is None

    @pytest.mark.unit
    async def test_expired_window_no_group(self):
        """Shared label but expired window should not group."""
        group = _make_group(
            labels={"node": "worker-1"},
            settling_window=60,
            last_alert_ago_seconds=120,
            created_ago_seconds=200,
        )
        alert_labels = {"node": "worker-1"}

        result = await correlate_label_temporal(alert_labels, [group])
        assert result is None


class TestSubsystemDependencyLayer:
    """Layer 4: Subsystem dependency correlation."""

    @pytest.mark.unit
    async def test_cascade_related_groups(self):
        """Alerts in cascade-related subsystems should group regardless of settling window expiry."""
        group = _make_group(
            labels={"component": "etcd", "namespace": "openshift-etcd"},
            settling_window=300,
            last_alert_ago_seconds=500,
            created_ago_seconds=600,
        )
        alert_labels = {"component": "kube-apiserver", "alertname": "APIServerErrors"}

        result = await correlate_subsystem_dependency(alert_labels, [group])
        assert result == group["id"]

    @pytest.mark.unit
    async def test_unrelated_subsystems_no_group(self):
        """Unrelated subsystems should NOT group."""
        group = _make_group(labels={"component": "dns"})
        alert_labels = {"component": "storage", "alertname": "StorageFull"}

        result = await correlate_subsystem_dependency(alert_labels, [group])
        assert result is None

    @pytest.mark.unit
    async def test_node_to_pod_cascade(self):
        """Node issues should cascade to pod alerts."""
        group = _make_group(labels={"component": "node"})
        alert_labels = {"component": "pod", "alertname": "PodCrashLoop"}

        result = await correlate_subsystem_dependency(alert_labels, [group])
        assert result == group["id"]

    @pytest.mark.unit
    async def test_no_subsystem_detected_no_group(self):
        """Alert without detectable subsystem should not match."""
        group = _make_group(labels={"component": "etcd"})
        alert_labels = {"alertname": "CustomAlert"}

        result = await correlate_subsystem_dependency(alert_labels, [group])
        assert result is None

    @pytest.mark.unit
    async def test_max_age_exceeded_skips_group(self):
        """Groups past max age should not accept new alerts via subsystem correlation."""
        group = _make_group(
            labels={"component": "etcd", "namespace": "openshift-etcd"},
            settling_window=60,
            last_alert_ago_seconds=50,
            created_ago_seconds=500,
        )
        alert_labels = {"component": "kube-apiserver", "alertname": "APIServerErrors"}

        result = await correlate_subsystem_dependency(alert_labels, [group])
        assert result is None


class TestLearningStoreLayer:
    """Layer 5: Learning Store co-occurrence (stub)."""

    @pytest.mark.unit
    async def test_always_returns_none(self):
        """Learning Store stub should gracefully return None."""
        mock_conn = AsyncMock()
        group = _make_group(labels={"component": "etcd"})
        alert_labels = {"alertname": "SomeAlert", "namespace": "openshift-etcd"}

        result = await correlate_learning_store(alert_labels, [group], mock_conn)
        assert result is None

    @pytest.mark.unit
    async def test_no_error_with_empty_groups(self):
        """Learning Store should not error with empty group list."""
        mock_conn = AsyncMock()
        result = await correlate_learning_store({"alertname": "Test"}, [], mock_conn)
        assert result is None
