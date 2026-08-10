"""Remediation pipeline runner (AD-1, Story 3.1).

Bridges the dispatcher to the remediation LangGraph graph.
Loads the sealed ImmutableDiagnosisArtifact from the database,
invokes the remediation graph, and persists the resulting plan.

Does NOT transition incident state — that is Story 3.3's
policy gate responsibility.
"""

from __future__ import annotations

import uuid

from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.checkpointer import get_checkpointer
from ..db.remediation import load_immutable_artifact, persist_remediation_plan
from ..models.events import EventNames, SSEEventData
from ..models.remediation import RemediationPlan
from .remediation_graph import RemediationState, build_remediation_graph

logger = get_logger(Component.PIPELINE)


async def run_remediation_pipeline(incident_id: uuid.UUID) -> RemediationPlan | None:
    """Run the remediation pipeline for an incident.

    Loads the sealed artifact from immutable_diagnoses, invokes the
    remediation graph, persists the plan, and emits SSE events.

    Args:
        incident_id: The incident UUID to plan remediation for.

    Returns:
        The persisted RemediationPlan, or None on failure.
    """
    logger.info(
        "Starting remediation pipeline",
        extra={"incident_id": str(incident_id)},
    )

    await _emit_remediation_event(incident_id, "remediation_plan", "planning")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            artifact = await load_immutable_artifact(conn, incident_id)

        checkpointer = await get_checkpointer()
        builder = build_remediation_graph()
        graph = builder.compile(checkpointer=checkpointer)

        initial_state: RemediationState = {
            "incident_id": str(incident_id),
            "immutable_artifact": artifact.model_dump(mode="json"),
            "remediation_plan": None,
            "stage": "entered",
        }

        thread_id = f"remediation-{incident_id}"
        config = {"configurable": {"thread_id": thread_id}}
        final_state = await graph.ainvoke(initial_state, config=config)

        plan_dict = final_state.get("remediation_plan")
        if plan_dict is None:
            logger.error(
                "Remediation graph produced no plan",
                extra={"incident_id": str(incident_id)},
            )
            await _emit_remediation_event(incident_id, "remediation_plan", "failed")
            return None

        plan = RemediationPlan.model_validate(plan_dict)

        async with pool.acquire() as conn:
            await persist_remediation_plan(conn, plan)

        await _emit_remediation_event(incident_id, "remediation_plan", "planned")

        logger.info(
            "Remediation pipeline completed successfully",
            extra={
                "incident_id": str(incident_id),
                "plan_id": str(plan.id),
                "step_count": len(plan.steps),
            },
        )

        return plan

    except Exception:
        logger.exception(
            "Remediation pipeline failed",
            extra={"incident_id": str(incident_id)},
        )
        await _emit_remediation_event(incident_id, "remediation_plan", "failed")
        return None


async def _emit_remediation_event(
    incident_id: uuid.UUID,
    stage: str,
    state: str,
) -> None:
    """Emit an SSE event for remediation pipeline stage transitions."""
    try:
        from ..api.event_bus import get_event_bus

        bus = get_event_bus()
        await bus.emit(
            EventNames.INCIDENT_STAGE_CHANGED,
            SSEEventData(
                incident_id=incident_id,
                stage=stage,
                state=state,
                payload={},
            ),
        )
    except Exception:
        logger.warning(
            "Failed to emit remediation stage event",
            extra={"incident_id": str(incident_id), "stage": stage},
        )
