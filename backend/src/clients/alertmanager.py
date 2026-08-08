"""AlertManager API client for alert verification (AC5).

Provides an abstract interface, an HTTP implementation that calls the
AlertManager v2 API, and a stub for test/dev environments.
"""

from __future__ import annotations

import abc
import os

import httpx

from ..config.logging import Component, get_logger

logger = get_logger(Component.API, module=__name__)


class AlertManagerUnreachableError(Exception):
    """Raised when the AlertManager API cannot be reached."""


class AlertManagerClient(abc.ABC):
    """Abstract interface for verifying alert status against AlertManager."""

    @abc.abstractmethod
    async def check_alerts_firing(self, fingerprints: list[str]) -> bool:
        """Check whether any of the given alert fingerprints are currently firing.

        Returns True if at least one alert is still firing.

        Raises:
            AlertManagerUnreachableError: If the AlertManager API is unreachable.
        """
        ...


class AlertManagerHTTPClient(AlertManagerClient):
    """Production client that queries AlertManager's v2 API."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self._base_url = (
            base_url
            or os.environ.get("ALERTMANAGER_URL", "")
        ).rstrip("/")
        self._timeout = timeout

    async def check_alerts_firing(self, fingerprints: list[str]) -> bool:
        if not self._base_url:
            raise AlertManagerUnreachableError("ALERTMANAGER_URL not configured")

        url = f"{self._base_url}/api/v2/alerts"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params={"active": "true"})
                resp.raise_for_status()

            active_fingerprints: set[str] = set()
            for alert in resp.json():
                fp = alert.get("fingerprint", "")
                if fp:
                    active_fingerprints.add(fp)

            return bool(active_fingerprints & set(fingerprints))
        except (httpx.HTTPError, httpx.TimeoutException, Exception) as exc:
            logger.warning(
                "AlertManager API unreachable",
                extra={"error": str(exc), "url": url},
            )
            raise AlertManagerUnreachableError(str(exc)) from exc


class AlertManagerStubClient(AlertManagerClient):
    """Stub that always signals unreachable (fail-safe default for dev/test)."""

    async def check_alerts_firing(self, fingerprints: list[str]) -> bool:
        raise AlertManagerUnreachableError(
            "AlertManager API client not configured (stub)"
        )


def create_alertmanager_client() -> AlertManagerClient:
    """Factory that returns the appropriate client based on configuration."""
    url = os.environ.get("ALERTMANAGER_URL", "")
    if url:
        return AlertManagerHTTPClient(url)
    return AlertManagerStubClient()
