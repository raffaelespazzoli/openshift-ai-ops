"""AlertManager v4 webhook payload models.

Pydantic models for validating incoming AlertManager webhook payloads.
These are inbound data contracts — they depend on nothing in the project.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WebhookAlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertManagerAlert(BaseModel):
    """A single alert within an AlertManager webhook payload."""

    status: WebhookAlertStatus
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime = Field(alias="endsAt")
    generator_url: str = Field(alias="generatorURL")
    fingerprint: str = Field(min_length=1, max_length=64)

    model_config = {"populate_by_name": True}

    @field_validator("fingerprint")
    @classmethod
    def fingerprint_hex_only(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("fingerprint must not be empty")
        try:
            int(stripped, 16)
        except ValueError:
            raise ValueError("fingerprint must be a hex string")
        return stripped


class AlertManagerWebhook(BaseModel):
    """AlertManager v4 webhook payload (top-level object)."""

    version: Literal["4"]
    group_key: str = Field(alias="groupKey")
    status: WebhookAlertStatus
    receiver: str
    alerts: list[AlertManagerAlert] = Field(min_length=1)
    group_labels: dict[str, str] = Field(alias="groupLabels")
    common_labels: dict[str, str] = Field(alias="commonLabels")
    common_annotations: dict[str, str] = Field(alias="commonAnnotations")
    external_url: str = Field(alias="externalURL")
    truncated_alerts: int = Field(default=0, alias="truncatedAlerts")

    model_config = {"populate_by_name": True}
