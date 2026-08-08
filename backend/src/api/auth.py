"""OpenShift OAuth authentication dependency (AD-12).

Validates bearer tokens via the Kubernetes TokenReview API.
Supports dev-mode bypass via AUTH_DISABLED=true for local development.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config.logging import Component, get_logger
from ..models.api import ERROR_UNAUTHORIZED, ApiError

logger = get_logger(Component.API)

KUBE_API = "https://kubernetes.default.svc"
SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

_TOKEN_CACHE_TTL = 60  # seconds
_token_cache: dict[str, tuple[Any, float]] = {}


class AuthenticationError(Exception):
    """Raised when authentication fails. Handled by the app-level exception handler."""

    def __init__(self, message: str = "Authentication required", detail: dict[str, Any] | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class UserInfo(BaseModel):
    """Authenticated user identity from OAuth token."""

    username: str
    groups: list[str] = []


def _is_auth_disabled() -> bool:
    return os.environ.get("AUTH_DISABLED", "").lower() == "true"


def _is_tls_verify_disabled() -> bool:
    """Only allow skipping TLS verification in explicit dev mode."""
    return os.environ.get("K8S_TLS_VERIFY_DISABLED", "").lower() == "true"


def _get_stub_user() -> UserInfo:
    """Return a stub user for local development when auth is disabled."""
    return UserInfo(username="dev-user", groups=["system:authenticated"])


def _get_cached_user(token: str) -> UserInfo | None:
    """Check the in-memory token cache."""
    entry = _token_cache.get(token)
    if entry is None:
        return None
    user_info, cached_at = entry
    if time.time() - cached_at > _TOKEN_CACHE_TTL:
        del _token_cache[token]
        return None
    return user_info


def _cache_user(token: str, user_info: UserInfo) -> None:
    """Store a validated user in the cache with TTL."""
    _token_cache[token] = (user_info, time.time())


def _raise_auth_error(message: str = "Authentication required", detail: dict[str, Any] | None = None):
    """Raise a structured authentication error."""
    raise AuthenticationError(message=message, detail=detail)


async def _validate_token_via_review(bearer_token: str) -> UserInfo:
    """Validate a bearer token via the Kubernetes TokenReview API."""
    sa_token_path = Path(SA_TOKEN_PATH)
    if not sa_token_path.exists():
        logger.error("ServiceAccount token not found — cannot validate tokens")
        _raise_auth_error("Token validation unavailable", {"reason": "service_account_token_missing"})

    sa_token = sa_token_path.read_text().strip()

    ca_path = Path(SA_CA_PATH)
    if ca_path.exists():
        verify: str | bool = SA_CA_PATH
    elif _is_tls_verify_disabled():
        verify = False
    else:
        logger.error(
            "CA bundle missing and K8S_TLS_VERIFY_DISABLED is not set — refusing to skip TLS verification"
        )
        _raise_auth_error("Token validation unavailable", {"reason": "ca_bundle_missing"})

    async with httpx.AsyncClient(verify=verify) as client:
        resp = await client.post(
            f"{KUBE_API}/apis/authentication.k8s.io/v1/tokenreviews",
            headers={"Authorization": f"Bearer {sa_token}"},
            json={
                "apiVersion": "authentication.k8s.io/v1",
                "kind": "TokenReview",
                "spec": {"token": bearer_token},
            },
            timeout=10.0,
        )

    if resp.status_code != 200:
        logger.warning(
            "TokenReview request failed",
            extra={"status_code": resp.status_code},
        )
        _raise_auth_error("Token validation failed")

    review = resp.json()
    status = review.get("status", {})
    if not status.get("authenticated"):
        _raise_auth_error("Invalid or expired token")

    user = status.get("user", {})
    return UserInfo(
        username=user.get("username", "unknown"),
        groups=user.get("groups", []),
    )


async def get_current_user(request: Request) -> UserInfo:
    """FastAPI dependency that extracts and validates the bearer token.

    Returns the authenticated user identity or raises HTTP 401.
    In dev mode (AUTH_DISABLED=true), returns a stub user.
    """
    if _is_auth_disabled():
        return _get_stub_user()

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        _raise_auth_error("Missing or malformed Authorization header")

    token = auth_header[7:]  # Strip "Bearer " prefix

    cached = _get_cached_user(token)
    if cached is not None:
        return cached

    user_info = await _validate_token_via_review(token)
    _cache_user(token, user_info)
    return user_info


def handle_authentication_error(request: Request, exc: AuthenticationError) -> JSONResponse:
    """Exception handler for AuthenticationError — returns structured 401."""
    error = ApiError(
        error=exc.message,
        code=ERROR_UNAUTHORIZED,
        detail=exc.detail or {},
    )
    return JSONResponse(
        status_code=401,
        content=error.model_dump(mode="json"),
        headers={"WWW-Authenticate": "Bearer"},
    )
