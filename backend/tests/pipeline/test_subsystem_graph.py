"""Unit tests for the static subsystem dependency graph.

Tests cover:
- Cascade pattern lookups (ancestors, descendants)
- are_cascade_related bidirectional checks
- Subsystem extraction from alert labels
"""

from __future__ import annotations

import pytest

from src.pipeline.subsystem_graph import (
    are_cascade_related,
    extract_subsystem,
    get_cascade_ancestors,
    get_cascade_descendants,
)


class TestCascadeDescendants:
    @pytest.mark.unit
    def test_etcd_has_apiserver_descendants(self):
        descendants = get_cascade_descendants("etcd")
        assert "kube-apiserver" in descendants
        assert "kube-controller-manager" in descendants
        assert "kube-scheduler" in descendants

    @pytest.mark.unit
    def test_node_has_pod_descendants(self):
        descendants = get_cascade_descendants("node")
        assert "pod" in descendants
        assert "kubelet" in descendants

    @pytest.mark.unit
    def test_unknown_subsystem_empty(self):
        descendants = get_cascade_descendants("nonexistent")
        assert descendants == set()


class TestCascadeAncestors:
    @pytest.mark.unit
    def test_pod_has_node_and_kubelet_ancestors(self):
        ancestors = get_cascade_ancestors("pod")
        assert "node" in ancestors
        assert "kubelet" in ancestors
        assert "storage" in ancestors

    @pytest.mark.unit
    def test_kube_apiserver_has_etcd_ancestor(self):
        ancestors = get_cascade_ancestors("kube-apiserver")
        assert "etcd" in ancestors

    @pytest.mark.unit
    def test_etcd_has_no_ancestors(self):
        ancestors = get_cascade_ancestors("etcd")
        assert ancestors == set()


class TestAreCascadeRelated:
    @pytest.mark.unit
    def test_etcd_and_apiserver_related(self):
        assert are_cascade_related("etcd", "kube-apiserver") is True

    @pytest.mark.unit
    def test_apiserver_and_etcd_related(self):
        """Relationship is bidirectional."""
        assert are_cascade_related("kube-apiserver", "etcd") is True

    @pytest.mark.unit
    def test_node_and_pod_related(self):
        assert are_cascade_related("node", "pod") is True

    @pytest.mark.unit
    def test_dns_and_storage_not_related(self):
        assert are_cascade_related("dns", "storage") is False

    @pytest.mark.unit
    def test_same_subsystem_not_related(self):
        assert are_cascade_related("etcd", "etcd") is False

    @pytest.mark.unit
    def test_network_and_pod_related(self):
        assert are_cascade_related("network/ovn", "pod") is True


class TestExtractSubsystem:
    @pytest.mark.unit
    def test_explicit_component_label(self):
        labels = {"component": "etcd", "namespace": "openshift-etcd"}
        assert extract_subsystem(labels) == "etcd"

    @pytest.mark.unit
    def test_namespace_mapping(self):
        labels = {"namespace": "openshift-etcd", "alertname": "SomethingWrong"}
        assert extract_subsystem(labels) == "etcd"

    @pytest.mark.unit
    def test_namespace_kube_apiserver(self):
        labels = {"namespace": "openshift-kube-apiserver"}
        assert extract_subsystem(labels) == "kube-apiserver"

    @pytest.mark.unit
    def test_alertname_heuristic_etcd(self):
        labels = {"alertname": "etcdHighCommitDurations"}
        assert extract_subsystem(labels) == "etcd"

    @pytest.mark.unit
    def test_alertname_heuristic_kubelet(self):
        labels = {"alertname": "KubeletTooManyPods"}
        assert extract_subsystem(labels) == "kubelet"

    @pytest.mark.unit
    def test_no_subsystem_detected(self):
        labels = {"alertname": "CustomBusinessAlert", "team": "platform"}
        assert extract_subsystem(labels) is None

    @pytest.mark.unit
    def test_component_takes_precedence_over_namespace(self):
        labels = {"component": "storage", "namespace": "openshift-etcd"}
        assert extract_subsystem(labels) == "storage"
