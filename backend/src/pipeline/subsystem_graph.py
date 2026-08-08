"""Static OpenShift subsystem dependency graph (AD-5, Layer 4).

Known cascade patterns where failure in one subsystem causes
downstream effects in others. Temporal proximity is NOT required
for subsystem-dependency correlation — these are structural relationships.
"""

from __future__ import annotations

SUBSYSTEM_CASCADES: dict[str, list[str]] = {
    "etcd": ["kube-apiserver", "kube-controller-manager", "kube-scheduler"],
    "kube-apiserver": ["kube-controller-manager", "kube-scheduler", "openshift-apiserver"],
    "node": ["pod", "pvc", "kubelet"],
    "kubelet": ["pod", "container"],
    "storage": ["pvc", "pod"],
    "network/ovn": ["pod", "service", "ingress"],
    "dns": ["pod", "service"],
    "ingress": ["route"],
}

_NAMESPACE_TO_SUBSYSTEM: dict[str, str] = {
    "openshift-etcd": "etcd",
    "openshift-kube-apiserver": "kube-apiserver",
    "openshift-kube-controller-manager": "kube-controller-manager",
    "openshift-kube-scheduler": "kube-scheduler",
    "openshift-apiserver": "openshift-apiserver",
    "openshift-ovn-kubernetes": "network/ovn",
    "openshift-dns": "dns",
    "openshift-ingress": "ingress",
    "openshift-storage": "storage",
}


def get_cascade_descendants(subsystem: str) -> set[str]:
    """Return subsystems that are downstream effects of the given subsystem."""
    return set(SUBSYSTEM_CASCADES.get(subsystem, []))


def get_cascade_ancestors(subsystem: str) -> set[str]:
    """Return subsystems that could CAUSE failures in the given subsystem."""
    ancestors: set[str] = set()
    for parent, children in SUBSYSTEM_CASCADES.items():
        if subsystem in children:
            ancestors.add(parent)
    return ancestors


def are_cascade_related(subsystem_a: str, subsystem_b: str) -> bool:
    """Return True if either subsystem is a known cause/effect of the other."""
    if subsystem_a == subsystem_b:
        return False
    return (
        subsystem_b in get_cascade_descendants(subsystem_a)
        or subsystem_a in get_cascade_descendants(subsystem_b)
    )


def extract_subsystem(labels: dict) -> str | None:
    """Extract subsystem identifier from alert labels.

    Strategy:
    1. Explicit 'component' label
    2. Namespace → subsystem mapping
    3. Alertname prefix heuristic
    """
    if component := labels.get("component"):
        return component.lower()

    if namespace := labels.get("namespace"):
        if subsystem := _NAMESPACE_TO_SUBSYSTEM.get(namespace):
            return subsystem

    alertname = labels.get("alertname", "")
    alertname_lower = alertname.lower()

    for subsystem in SUBSYSTEM_CASCADES:
        normalized = subsystem.replace("/", "").replace("-", "")
        if alertname_lower.startswith(normalized):
            return subsystem

    if "etcd" in alertname_lower:
        return "etcd"
    if "apiserver" in alertname_lower:
        return "kube-apiserver"
    if "kubelet" in alertname_lower:
        return "kubelet"
    if "node" in alertname_lower:
        return "node"

    return None
