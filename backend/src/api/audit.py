"""Audit log middleware (AD-25).

Intercepts state-changing HTTP requests (POST, PUT, PATCH, DELETE)
and writes audit records to the database. Audit writes are fire-and-forget
async tasks — they never block or fail the HTTP response.
"""

from __future__ import annotations

import asyncio

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.audit import write_audit_log

logger = get_logger(Component.API)

_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_EXCLUDED_PATHS = frozenset({
    "/api/v1/webhooks/alertmanager",
})


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that logs state-changing requests to the audit_log table."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        if request.method not in _STATE_CHANGING_METHODS:
            return response

        if not (200 <= response.status_code < 300):
            return response

        path = request.url.path
        if path in _EXCLUDED_PATHS:
            return response

        actor = "anonymous"
        user_state = request.state
        if hasattr(user_state, "user"):
            actor = user_state.user.username

        action = f"{request.method} {path}"
        asyncio.create_task(
            self._write_audit(actor=actor, action=action, target_resource=path)
        )
        return response

    @staticmethod
    async def _write_audit(*, actor: str, action: str, target_resource: str) -> None:
        """Fire-and-forget audit write. Errors logged but never propagated."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await write_audit_log(
                    conn,
                    actor=actor,
                    action=action,
                    target_resource=target_resource,
                )
        except Exception:
            logger.exception(
                "Audit log background task failed",
                extra={"actor": actor, "action": action},
            )
