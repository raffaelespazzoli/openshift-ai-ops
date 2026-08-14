"""Unit tests for fast-path DB operations (Story 4.3).

Tests search_fast_path_candidates() and record_fast_path() with mocked connections.
Integration tests (testcontainers) are in the integration marker.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.db.case_records import search_fast_path_candidates
from src.db.incidents import record_fast_path

pytestmark = pytest.mark.unit


class TestSearchFastPathCandidates:
    """Tests for search_fast_path_candidates()."""

    async def test_returns_matching_records(self):
        """Returns records when matches exist above threshold."""
        row_id = uuid.uuid4()
        mock_row = {
            "id": row_id,
            "alert_signature": "HighMemory default warning",
            "root_cause_code": "node/memory-pressure",
            "outcome": "success",
            "outcome_confidence": 0.9,
            "ocp_version": "4.16",
            "created_at": datetime.now(timezone.utc),
            "diagnosis_object": {"root_cause_component": "node"},
            "remediation_plan": {"steps": []},
            "similarity": 0.95,
        }
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[mock_row])

        results = await search_fast_path_candidates(
            conn, [0.1] * 1536, threshold=0.90, top_k=3
        )

        assert len(results) == 1
        assert results[0]["id"] == row_id
        assert results[0]["similarity"] == 0.95
        assert results[0]["diagnosis_object"] == {"root_cause_component": "node"}
        assert results[0]["remediation_plan"] == {"steps": []}
        conn.fetch.assert_called_once()

    async def test_returns_empty_when_no_matches(self):
        """Returns empty list when no records match."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        results = await search_fast_path_candidates(
            conn, [0.1] * 1536, threshold=0.90
        )

        assert results == []

    async def test_uses_correct_threshold(self):
        """Passes threshold parameter to query."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await search_fast_path_candidates(
            conn, [0.5] * 1536, threshold=0.85, top_k=5
        )

        call_args = conn.fetch.call_args
        assert call_args[0][1] == str([0.5] * 1536)
        assert call_args[0][2] == 0.85
        assert call_args[0][3] == 5


class TestRecordFastPath:
    """Tests for record_fast_path()."""

    async def test_updates_incident_with_fast_path_fields(self):
        """Sets fast_path=TRUE, similarity, and case_record_id."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")

        incident_id = uuid.uuid4()
        case_record_id = uuid.uuid4()

        await record_fast_path(conn, incident_id, case_record_id, 0.95)

        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        assert incident_id in call_args
        assert 0.95 in call_args
        assert case_record_id in call_args
