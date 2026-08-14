"""Fast-path bypass for known patterns (Story 4.3, AD-19).

When a dequeued Root-Cause Event matches a previously successful case record
above the configured similarity threshold, the proven remediation plan is
replayed directly — bypassing the full LLM diagnosis pipeline. The fast-path
still enforces dry-run pre-flight and policy gate controls.

Failures at any stage fall back to the normal diagnosis pipeline.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import asyncpg
from pydantic import BaseModel, Field

from ..config.knowledge_settings import get_knowledge_settings
from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.case_records import search_fast_path_candidates
from ..db.diagnosis import persist_immutable_diagnosis
from ..db.incidents import record_fast_path, transition_incident_state
from ..db.policy_gate import persist_dry_run_result, persist_policy_decision
from ..db.queue import get_rce_incident_ids, mark_pipeline_complete
from ..db.remediation import persist_remediation_plan
from ..knowledge.embeddings import embed_texts
from ..knowledge.learning_store import apply_temporal_decay
from ..models.diagnosis import ImmutableDiagnosisArtifact
from ..models.events import EventNames, SSEEventData
from ..models.remediation import RemediationPlan
from ..models.state_machine import IncidentState, transition
from .audit_hook import pipeline_audit_log
from .case_record_writer import build_alert_signature
from .dry_run import run_dry_run_preflight
from .policy_gate import evaluate_policy_gate

logger = get_logger(Component.PIPELINE)


class FastPathMatch(BaseModel):
    """Result of a fast-path lookup — the matched case record."""

    case_record_id: uuid.UUID
    alert_signature: str
    root_cause_code: str
    similarity: float = Field(ge=0.0, le=1.0)
    effective_confidence: float = Field(ge=0.0)
    ocp_version: str
    diagnosis_object: dict
    remediation_plan: dict


async def check_fast_path(
    item: dict,
    conn: asyncpg.Connection,
) -> FastPathMatch | None:
    """Check whether a dequeued item has a fast-path eligible case record match.

    Builds the alert signature, generates an embedding, queries pgvector,
    and applies temporal decay to rank candidates. Returns the best match
    or None if no match exceeds the threshold.

    Non-fatal: any failure returns None so the caller proceeds with
    the normal diagnosis pipeline.
    """
    try:
        alerts = item.get("alerts", [])
        if not alerts:
            return None

        alert_signature = build_alert_signature(alerts)
        if not alert_signature.strip():
            return None

        embeddings = await embed_texts([alert_signature])
        if not embeddings:
            return None
        query_embedding = embeddings[0]

        settings = get_knowledge_settings()
        threshold = settings.learning_store_fast_path_threshold

        candidates = await search_fast_path_candidates(
            conn, query_embedding, threshold=threshold, top_k=3
        )
        if not candidates:
            return None

        current_ocp_version = os.environ.get("OCP_VERSION", "4")

        best_match: FastPathMatch | None = None
        best_effective_confidence = -1.0

        for candidate in candidates:
            effective_conf = apply_temporal_decay(
                candidate, current_ocp_version=current_ocp_version
            )
            if effective_conf > best_effective_confidence:
                best_effective_confidence = effective_conf
                best_match = FastPathMatch(
                    case_record_id=candidate["id"],
                    alert_signature=candidate["alert_signature"],
                    root_cause_code=candidate["root_cause_code"],
                    similarity=candidate["similarity"],
                    effective_confidence=effective_conf,
                    ocp_version=candidate["ocp_version"],
                    diagnosis_object=candidate["diagnosis_object"],
                    remediation_plan=candidate["remediation_plan"],
                )

        return best_match

    except Exception:
        logger.warning(
            "Fast-path check failed — proceeding with normal pipeline",
            extra={"incident_id": str(item.get("incident_id", ""))},
        )
        return None


async def run_fast_path_pipeline(
    item: dict,
    match: FastPathMatch,
) -> bool:
    """Execute the full fast-path flow for a matched case record.

    Transitions: QUEUED → DIAGNOSED → PLANNING → AWAITING_APPROVAL/EXECUTING
    Creates synthetic diagnosis artifact, replays remediation plan,
    runs dry-run and policy gate, persists all artifacts.

    Returns True on success, False on failure (caller should fall back
    to normal diagnosis pipeline).
    """
    incident_id = item["incident_id"]
    queue_item_id = item["id"]

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # --- Transition QUEUED → DIAGNOSED (all sibling incidents) ---
            transition(IncidentState.QUEUED, IncidentState.DIAGNOSED)
            rce_id = item.get("root_cause_event_id")
            sibling_ids = await get_rce_incident_ids(conn, rce_id) if rce_id else []
            if not sibling_ids:
                sibling_ids = [incident_id]

            for sid in sibling_ids:
                transitioned = await transition_incident_state(
                    conn, sid, "queued", "diagnosed"
                )
                if not transitioned and sid == incident_id:
                    logger.warning(
                        "Fast-path: could not transition primary to diagnosed",
                        extra={"incident_id": str(incident_id)},
                    )
                    return False

            _emit_stage_event(incident_id, "fast_path_match", "diagnosed", {
                "case_record_id": str(match.case_record_id),
                "similarity": match.similarity,
            })

            # --- Create synthetic ImmutableDiagnosisArtifact ---
            artifact = _build_synthetic_artifact(match, incident_id)
            diag_dict = artifact.model_dump(mode="json")
            skeptic_verdict = diag_dict.get("skeptic_verdict", {})

            diagnosis_record_id = await persist_immutable_diagnosis(
                conn,
                incident_id=incident_id,
                diagnosis=diag_dict,
                skeptic_verdict=skeptic_verdict,
                sealed_at=artifact.sealed_at,
            )

            # --- Replay RemediationPlan ---
            plan = _build_replayed_plan(match, incident_id, diagnosis_record_id)
            await persist_remediation_plan(conn, plan)

            # --- Record fast-path metadata ---
            await record_fast_path(conn, incident_id, match.case_record_id, match.similarity)

            # --- Transition DIAGNOSED → PLANNING ---
            transition(IncidentState.DIAGNOSED, IncidentState.PLANNING)
            if not await transition_incident_state(conn, incident_id, "diagnosed", "planning"):
                logger.warning(
                    "Fast-path: could not transition to planning",
                    extra={"incident_id": str(incident_id)},
                )
                return False

            _emit_stage_event(incident_id, "dry_run", "planning", {})

            # --- Dry-run pre-flight ---
            dry_run_result = await run_dry_run_preflight(plan, artifact)
            await persist_dry_run_result(conn, dry_run_result)

            # --- Policy gate ---
            alert_severity = item.get("severity")
            policy_decision = await evaluate_policy_gate(
                plan, artifact, dry_run_result, alert_severity=alert_severity
            )
            await persist_policy_decision(conn, policy_decision)

            _emit_stage_event(incident_id, "policy_gate", "planning", {
                "auto_approved": policy_decision.auto_execution_approved,
            })

            # --- Transition based on policy decision ---
            if policy_decision.auto_execution_approved:
                target_state = IncidentState.EXECUTING
            else:
                target_state = IncidentState.AWAITING_APPROVAL

            transition(IncidentState.PLANNING, target_state)
            if not await transition_incident_state(
                conn, incident_id, "planning", target_state.value
            ):
                logger.warning(
                    "Fast-path: could not transition to %s",
                    target_state.value,
                    extra={"incident_id": str(incident_id)},
                )
                return False

            # --- Audit log ---
            await pipeline_audit_log(
                incident_id=str(incident_id),
                stage_name="fast_path",
                state_before="queued",
                state_after=target_state.value,
                extra_detail={
                    "case_record_id": str(match.case_record_id),
                    "similarity": match.similarity,
                    "effective_confidence": match.effective_confidence,
                    "policy_approved": policy_decision.auto_execution_approved,
                },
                conn=conn,
            )

            # --- Mark queue item complete ---
            await mark_pipeline_complete(conn, queue_item_id)

            _emit_stage_event(incident_id, "fast_path_complete", target_state.value, {
                "policy_decision": "auto_approved" if policy_decision.auto_execution_approved else "awaiting_approval",
            })

        logger.info(
            "Fast-path pipeline completed successfully",
            extra={
                "incident_id": str(incident_id),
                "case_record_id": str(match.case_record_id),
                "final_state": target_state.value,
            },
        )
        return True

    except Exception:
        logger.exception(
            "Fast-path pipeline failed — falling back to normal pipeline",
            extra={"incident_id": str(incident_id)},
        )
        return False


def _build_synthetic_artifact(
    match: FastPathMatch,
    incident_id: uuid.UUID,
) -> ImmutableDiagnosisArtifact:
    """Build a synthetic diagnosis artifact from a case record for fast-path replay.

    The artifact preserves the original diagnosis content but assigns
    a new ID and links to the current incident.
    """
    diag = match.diagnosis_object.copy()
    original_id = diag.get("id")
    new_id = uuid.uuid4()
    diag["id"] = str(new_id)
    diag["diagnosis_object_id"] = original_id or str(new_id)
    diag["incident_id"] = str(incident_id)
    diag["sealed_at"] = datetime.now(timezone.utc).isoformat()

    if "skeptic_verdict" not in diag or diag["skeptic_verdict"] is None:
        diag["skeptic_verdict"] = {
            "outcome": "approved",
            "source": "fast_path_replay",
            "note": "Replayed from proven case record",
        }

    return ImmutableDiagnosisArtifact.model_validate(diag)


def _build_replayed_plan(
    match: FastPathMatch,
    incident_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
) -> RemediationPlan:
    """Build a replayed remediation plan from a case record for fast-path.

    Creates a new plan with the same steps, blast radius, rollback,
    risk, and preconditions as the proven original. Clears stale
    manifest_path fields from forward steps (Story 4.0 compatibility).
    """
    plan_data = match.remediation_plan.copy()
    plan_data["id"] = str(uuid.uuid4())
    plan_data["incident_id"] = str(incident_id)
    plan_data["diagnosis_id"] = str(diagnosis_id)
    plan_data["created_at"] = datetime.now(timezone.utc).isoformat()

    for step in plan_data.get("steps", []):
        step.pop("manifest_path", None)
        step.pop("manifest_generation_failed", None)

    return RemediationPlan.model_validate(plan_data)


def _emit_stage_event(
    incident_id: uuid.UUID,
    stage: str,
    state: str,
    payload: dict,
) -> None:
    """Best-effort SSE event emission for fast-path stage transitions."""
    try:
        import asyncio

        from ..api.event_bus import get_event_bus  # noqa: deferred to avoid circular

        bus = get_event_bus()
        event_data = SSEEventData(
            incident_id=incident_id,
            stage=stage,
            state=state,
            payload=payload,
        )
        asyncio.ensure_future(bus.emit(EventNames.INCIDENT_STAGE_CHANGED, event_data))
    except Exception:
        pass
