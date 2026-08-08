"""Five-layer deterministic correlation engine (AD-5).

Layers execute in strict order; first match wins. Once an alert is grouped,
later layers don't re-evaluate it. Over-grouping is intentional — the
orchestrator refines during diagnosis.

Layer 1: DEDUP — same fingerprint already active → absorb
Layer 2: NAMESPACE + TEMPORAL — same namespace within settling window → group
Layer 3: LABEL + TEMPORAL — shared node/instance/component within settling window → group
Layer 4: SUBSYSTEM DEPENDENCY — known cascade pattern → group (no time constraint)
Layer 5: LEARNING STORE — past co-occurrence (stub, returns None)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg

from ..config.logging import Component, get_logger
from ..db.correlation import (
    add_alert_to_group,
    check_dedup,
    create_correlation_group,
    get_groups_to_seal,
    get_open_groups,
    seal_group,
    update_dedup_timestamp,
)
from ..models.root_cause_event import CorrelationEvidence, CorrelationLayer
from ..models.state_machine import IncidentState, transition
from .settling import check_group_sealing, get_settling_window, recalculate_group_window
from .subsystem_graph import are_cascade_related, extract_subsystem

logger = get_logger(Component.PIPELINE)


async def correlate_namespace_temporal(
    alert_labels: dict,
    open_groups: list[dict],
    settling_check_time: datetime | None = None,
) -> uuid.UUID | None:
    """Layer 2: Correlate by namespace + temporal proximity.

    Match condition: same namespace AND alert arrived within the group's settling window.
    """
    alert_namespace = alert_labels.get("namespace")
    if not alert_namespace:
        return None

    now = settling_check_time or datetime.now(timezone.utc)

    for group in open_groups:
        if check_group_sealing(
            group["last_alert_at"],
            group["created_at"],
            group["settling_window_seconds"],
            now=now,
        ):
            continue

        for member in group.get("members", []):
            member_labels = member.get("labels", {})
            if isinstance(member_labels, str):
                import json
                member_labels = json.loads(member_labels)
            if member_labels.get("namespace") == alert_namespace:
                return group["id"]

    return None


async def correlate_label_temporal(
    alert_labels: dict,
    open_groups: list[dict],
    settling_check_time: datetime | None = None,
) -> uuid.UUID | None:
    """Layer 3: Correlate by shared label (node/instance/component) + temporal proximity.

    Match condition: shared node, instance, or component label AND within settling window.
    """
    correlation_labels = {"node", "instance", "component"}
    alert_corr_labels = {
        k: v for k, v in alert_labels.items() if k in correlation_labels and v
    }

    if not alert_corr_labels:
        return None

    now = settling_check_time or datetime.now(timezone.utc)

    for group in open_groups:
        if check_group_sealing(
            group["last_alert_at"],
            group["created_at"],
            group["settling_window_seconds"],
            now=now,
        ):
            continue

        for member in group.get("members", []):
            member_labels = member.get("labels", {})
            if isinstance(member_labels, str):
                import json
                member_labels = json.loads(member_labels)

            for label_key, label_value in alert_corr_labels.items():
                if member_labels.get(label_key) == label_value:
                    return group["id"]

    return None


async def correlate_subsystem_dependency(
    alert_labels: dict,
    open_groups: list[dict],
    settling_check_time: datetime | None = None,
) -> uuid.UUID | None:
    """Layer 4: Correlate by static subsystem dependency graph.

    Match condition: alert's subsystem matches a known downstream/upstream effect
    of alerts in an existing group. Temporal proximity NOT required, but groups
    that have exceeded max age are skipped (they should be sealed, not extended).
    """
    alert_subsystem = extract_subsystem(alert_labels)
    if not alert_subsystem:
        return None

    now = settling_check_time or datetime.now(timezone.utc)

    for group in open_groups:
        if _group_exceeds_max_age(group, now):
            continue

        for member in group.get("members", []):
            member_labels = member.get("labels", {})
            if isinstance(member_labels, str):
                import json
                member_labels = json.loads(member_labels)

            member_subsystem = extract_subsystem(member_labels)
            if member_subsystem and are_cascade_related(alert_subsystem, member_subsystem):
                return group["id"]

    return None


def _group_exceeds_max_age(group: dict, now: datetime) -> bool:
    """Check if a group has exceeded its max age and should not accept new alerts."""
    from .settling import calculate_max_age

    created_at = group["created_at"]
    settling_window = group["settling_window_seconds"]
    max_age = calculate_max_age(settling_window)
    return (now - created_at) > max_age


async def correlate_learning_store(
    alert_labels: dict,
    open_groups: list[dict],
    conn: asyncpg.Connection | asyncpg.Pool,
) -> uuid.UUID | None:
    """Layer 5: Check historical co-occurrence from Case Records.

    Currently returns None (no Case Records exist yet — Epic 4).
    The interface is defined so Epic 4 can implement without modifying control flow.
    """
    logger.debug(
        "Learning Store co-occurrence: no records available",
        extra={"alert_labels": str(alert_labels)},
    )
    return None


async def process_alert_for_correlation(
    conn: asyncpg.Connection | asyncpg.Pool,
    alert_id: uuid.UUID,
    incident_id: uuid.UUID,
    fingerprint: str,
    labels: dict,
    severity: str,
) -> None:
    """Main correlation entry point — called after alert persistence.

    Runs the five-layer correlator in order. First match wins.
    If no match, creates a new correlation group with this alert as seed.

    Uses FOR UPDATE locking on open groups to prevent concurrent alerts from
    creating duplicate groups when they should be merged into the same one.
    """
    now = datetime.now(timezone.utc)

    open_groups = await get_open_groups(conn, for_update=True)

    matched_group_id: uuid.UUID | None = None
    matched_layer: CorrelationLayer | None = None
    reasoning: str = ""
    dimension_data: dict = {}

    # Layer 2: Namespace + temporal
    matched_group_id = await correlate_namespace_temporal(labels, open_groups, now)
    if matched_group_id:
        matched_layer = CorrelationLayer.NAMESPACE_TEMPORAL
        reasoning = f"Same namespace '{labels.get('namespace')}' within settling window"
        dimension_data = {"namespace": labels.get("namespace")}

    # Layer 3: Label + temporal
    if not matched_group_id:
        matched_group_id = await correlate_label_temporal(labels, open_groups, now)
        if matched_group_id:
            matched_layer = CorrelationLayer.LABEL_TEMPORAL
            shared_labels = {
                k: v for k, v in labels.items()
                if k in ("node", "instance", "component") and v
            }
            reasoning = f"Shared labels {shared_labels} within settling window"
            dimension_data = {"shared_labels": shared_labels}

    # Layer 4: Subsystem dependency
    if not matched_group_id:
        matched_group_id = await correlate_subsystem_dependency(labels, open_groups, now)
        if matched_group_id:
            matched_layer = CorrelationLayer.SUBSYSTEM_DEPENDENCY
            alert_subsystem = extract_subsystem(labels)
            matched_member_subsystem = _find_cascade_match_subsystem(labels, open_groups, matched_group_id)
            reasoning = (
                f"Cascade pattern: '{matched_member_subsystem}' → '{alert_subsystem}' "
                f"(static subsystem dependency graph)"
            )
            dimension_data = {
                "alert_subsystem": alert_subsystem,
                "group_subsystem": matched_member_subsystem,
                "cascade_pattern": f"{matched_member_subsystem} → {alert_subsystem}",
            }

    # Layer 5: Learning Store
    if not matched_group_id:
        matched_group_id = await correlate_learning_store(labels, open_groups, conn)
        if matched_group_id:
            matched_layer = CorrelationLayer.LEARNING_STORE_COOCCURRENCE
            reasoning = "Historical co-occurrence from Case Records"

    settling_window = get_settling_window(severity)

    if matched_group_id and matched_layer:
        evidence = CorrelationEvidence(
            layer=matched_layer,
            alert_ids=[alert_id],
            reasoning=reasoning,
            dimension_data=dimension_data,
        )
        current_window = None
        for g in open_groups:
            if g["id"] == matched_group_id:
                current_window = g["settling_window_seconds"]
                break
        new_window = recalculate_group_window(
            current_window or settling_window, severity
        )
        await add_alert_to_group(conn, matched_group_id, alert_id, incident_id, new_window, evidence)

        logger.info(
            "Alert correlated to existing group",
            extra={
                "alert_id": str(alert_id),
                "group_id": str(matched_group_id),
                "layer": matched_layer.value,
            },
        )
    else:
        await create_correlation_group(conn, alert_id, incident_id, settling_window)
        logger.info(
            "New correlation group created for alert",
            extra={
                "alert_id": str(alert_id),
                "settling_window": settling_window,
            },
        )

    # Transition incident: received → correlating
    await _transition_incident(conn, incident_id, IncidentState.RECEIVED, IncidentState.CORRELATING)

    # Check if any groups should be sealed now
    await seal_expired_groups(conn)


def _find_cascade_match_subsystem(
    alert_labels: dict,
    open_groups: list[dict],
    matched_group_id: uuid.UUID,
) -> str | None:
    """Find the member subsystem that triggered the cascade match for evidence."""
    import json as _json

    alert_subsystem = extract_subsystem(alert_labels)
    for group in open_groups:
        if group["id"] != matched_group_id:
            continue
        for member in group.get("members", []):
            member_labels = member.get("labels", {})
            if isinstance(member_labels, str):
                member_labels = _json.loads(member_labels)
            member_subsystem = extract_subsystem(member_labels)
            if member_subsystem and are_cascade_related(alert_subsystem, member_subsystem):
                return member_subsystem
    return None


async def seal_expired_groups(conn: asyncpg.Connection | asyncpg.Pool) -> int:
    """Check for and seal expired correlation groups.

    Returns the number of groups sealed.
    """
    groups_to_seal = await get_groups_to_seal(conn)
    sealed_count = 0

    for group in groups_to_seal:
        sealed_data = await seal_group(conn, group["id"])

        for inc_id in sealed_data["incident_ids"]:
            try:
                await _transition_incident(
                    conn, inc_id, IncidentState.CORRELATING, IncidentState.QUEUED
                )
            except Exception:
                logger.warning(
                    "Could not transition incident to queued (may already be transitioned)",
                    extra={"incident_id": str(inc_id), "group_id": str(group["id"])},
                )

        sealed_count += 1
        logger.info(
            "Group sealed as RootCauseEvent",
            extra={
                "group_id": str(group["id"]),
                "alert_count": len(sealed_data["alert_ids"]),
            },
        )

    return sealed_count


async def _transition_incident(
    conn: asyncpg.Connection | asyncpg.Pool,
    incident_id: uuid.UUID,
    from_state: IncidentState,
    to_state: IncidentState,
) -> None:
    """Transition an incident's state via the state machine function (AD-19)."""
    current = await conn.fetchval(
        "SELECT state FROM incidents WHERE id = $1", incident_id
    )
    if current is None:
        logger.warning("Incident not found for transition", extra={"incident_id": str(incident_id)})
        return

    current_state = IncidentState(current)
    if current_state != from_state:
        logger.debug(
            "Incident not in expected state for transition",
            extra={
                "incident_id": str(incident_id),
                "expected": from_state.value,
                "actual": current_state.value,
            },
        )
        return

    new_state = transition(current_state, to_state)
    await conn.execute(
        "UPDATE incidents SET state = $2, updated_at = NOW() WHERE id = $1",
        incident_id,
        new_state.value,
    )
