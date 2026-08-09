"""Knowledge models — RunbookChunk and CompletenessResult (AD-4).

Leaf models used by the knowledge retrieval and completeness gate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class RunbookChunk(BaseModel):
    """A chunked section of an OpenShift runbook stored in pgvector."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_file: str
    chunk_index: int
    heading_hierarchy: list[str] = Field(default_factory=list)
    content: str
    token_count: int
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompletenessResult(BaseModel):
    """Result of the completeness gate evaluation."""

    complete: bool
    unaddressed_alerts: list[str] = Field(default_factory=list)
    reasoning: str
