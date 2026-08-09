"""Unit tests for the markdown chunker (AC: #3).

Tests chunking preserves headings, respects size limits, and handles
edge cases.
"""

from __future__ import annotations

import pytest

from src.knowledge.chunker import chunk_markdown, _estimate_tokens, _split_on_headings, _split_oversized


SAMPLE_RUNBOOK = """# Node Memory Pressure

## Symptoms

The node is experiencing memory pressure. Pods may be evicted.

### Common Indicators

- Node condition MemoryPressure is True
- Pods being evicted with reason "The node was low on resource: memory"
- kubelet reporting memory allocation failures

## Diagnosis Steps

1. Check node memory usage: `kubectl top node <node-name>`
2. Check pod memory requests vs limits
3. Look for memory leaks in application pods

## Remediation

### Immediate Actions

- Cordon the node to prevent new pod scheduling
- Identify and delete low-priority pods

### Long-term Fixes

- Increase node memory or add more nodes
- Adjust pod memory requests and limits
- Implement memory quotas per namespace
"""


class TestChunkMarkdown:
    """Tests for the main chunk_markdown function."""

    @pytest.mark.unit
    def test_produces_chunks_from_markdown(self):
        chunks = chunk_markdown(SAMPLE_RUNBOOK, "node-memory-pressure.md")
        assert len(chunks) > 0

    @pytest.mark.unit
    def test_preserves_heading_hierarchy(self):
        chunks = chunk_markdown(SAMPLE_RUNBOOK, "test.md")
        hierarchies = [c.heading_hierarchy for c in chunks]
        has_nested = any(len(h) >= 2 for h in hierarchies)
        assert has_nested, "Should preserve nested heading hierarchy"

    @pytest.mark.unit
    def test_respects_max_token_limit(self):
        chunks = chunk_markdown(SAMPLE_RUNBOOK, "test.md", max_tokens=100)
        for chunk in chunks:
            assert chunk.token_count <= 100 + 20  # Small tolerance for boundary

    @pytest.mark.unit
    def test_chunk_index_is_sequential(self):
        chunks = chunk_markdown(SAMPLE_RUNBOOK, "test.md")
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    @pytest.mark.unit
    def test_source_file_preserved(self):
        chunks = chunk_markdown(SAMPLE_RUNBOOK, "my-runbook.md")
        for chunk in chunks:
            assert chunk.source_file == "my-runbook.md"

    @pytest.mark.unit
    def test_empty_content_returns_empty_list(self):
        chunks = chunk_markdown("", "empty.md")
        assert chunks == []

    @pytest.mark.unit
    def test_whitespace_only_returns_empty_list(self):
        chunks = chunk_markdown("   \n\n  ", "ws.md")
        assert chunks == []

    @pytest.mark.unit
    def test_content_without_headings_produces_single_chunk(self):
        chunks = chunk_markdown("This is plain text without headings.", "plain.md")
        assert len(chunks) == 1
        assert "plain text" in chunks[0].content

    @pytest.mark.unit
    def test_large_section_splits_on_paragraphs(self):
        large_section = "## Big Section\n\n" + "\n\n".join(
            [f"Paragraph {i} with enough text to count as tokens." * 5 for i in range(20)]
        )
        chunks = chunk_markdown(large_section, "large.md", max_tokens=200)
        assert len(chunks) > 1

    @pytest.mark.unit
    def test_token_count_is_positive(self):
        chunks = chunk_markdown(SAMPLE_RUNBOOK, "test.md")
        for chunk in chunks:
            assert chunk.token_count > 0

    @pytest.mark.unit
    def test_oversized_single_paragraph_is_split(self):
        """A single paragraph exceeding max_tokens gets split by sentence."""
        huge_para = "## Oversized\n\n" + (
            "This is a sentence with many words to fill tokens. " * 100
        )
        chunks = chunk_markdown(huge_para, "huge.md", max_tokens=50)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.token_count <= 60  # tolerance for boundary

    @pytest.mark.unit
    def test_oversized_paragraph_without_sentences_splits_by_chars(self):
        """A massive block with no sentence-ending punctuation splits by chars."""
        blob = "## Blob\n\n" + ("x" * 2000)
        chunks = chunk_markdown(blob, "blob.md", max_tokens=50)
        assert len(chunks) > 1


    @pytest.mark.unit
    def test_oversized_sentence_in_multi_sentence_paragraph(self):
        """A single oversized sentence among normal sentences gets char-split."""
        normal = "Short sentence."
        huge = "x" * 2000 + "."
        para = f"## Mixed\n\n{normal} {huge} {normal}"
        chunks = chunk_markdown(para, "mixed.md", max_tokens=50)
        assert len(chunks) > 1
        for chunk in chunks:
            assert _estimate_tokens(chunk.content) <= 60


class TestChunkOverlapOverflow:
    """Tests for Finding R4-4: overlap carry-forward must not create oversized chunks."""

    @pytest.mark.unit
    def test_overlap_plus_paragraph_does_not_exceed_max_tokens(self):
        """When overlap is prepended, final chunk must still respect max_tokens."""
        paras = [
            "A" * 1900,
            "B" * 1900,
            "C" * 1900,
        ]
        content = "## Section\n\n" + "\n\n".join(paras)
        chunks = chunk_markdown(content, "overlap.md", max_tokens=500, overlap_tokens=64)
        for chunk in chunks:
            assert _estimate_tokens(chunk.content) <= 500, (
                f"Chunk exceeded max_tokens: {_estimate_tokens(chunk.content)} tokens"
            )

    @pytest.mark.unit
    def test_near_limit_paragraphs_with_overlap(self):
        """Near-limit paragraphs with carried overlap must not overshoot."""
        para_text = "word " * 495
        content = "## Big\n\n" + "\n\n".join([para_text] * 5)
        chunks = chunk_markdown(content, "near.md", max_tokens=500, overlap_tokens=64)
        for chunk in chunks:
            assert _estimate_tokens(chunk.content) <= 500


class TestSplitOversized:
    """Tests for the oversized paragraph splitting fallback."""

    @pytest.mark.unit
    def test_splits_by_sentence(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        parts = _split_oversized(text, max_tokens=5)
        assert len(parts) >= 2

    @pytest.mark.unit
    def test_splits_by_chars_when_no_sentences(self):
        text = "x" * 1000
        parts = _split_oversized(text, max_tokens=10)
        assert len(parts) > 1
        for part in parts:
            assert len(part) <= 40 + 1  # 10 tokens * 4 chars + tolerance


class TestEstimateTokens:
    """Tests for the token estimation function."""

    @pytest.mark.unit
    def test_empty_string_returns_one(self):
        assert _estimate_tokens("") == 1

    @pytest.mark.unit
    def test_short_text_reasonable_estimate(self):
        tokens = _estimate_tokens("Hello world")
        assert 1 <= tokens <= 5

    @pytest.mark.unit
    def test_longer_text_scales_approximately(self):
        short = _estimate_tokens("word")
        long_text = _estimate_tokens("word " * 100)
        assert long_text > short


class TestSplitOnHeadings:
    """Tests for heading-based splitting."""

    @pytest.mark.unit
    def test_splits_on_h2_boundaries(self):
        md = "## Section 1\nContent 1\n## Section 2\nContent 2"
        sections = _split_on_headings(md)
        assert len(sections) >= 2

    @pytest.mark.unit
    def test_preserves_hierarchy_levels(self):
        md = "# Top\n## Mid\n### Bottom\nContent"
        sections = _split_on_headings(md)
        hierarchies = [h for h, _ in sections]
        has_deep = any(len(h) >= 3 for h in hierarchies)
        assert has_deep

    @pytest.mark.unit
    def test_handles_no_headings(self):
        md = "Just plain text with no headings."
        sections = _split_on_headings(md)
        assert len(sections) == 1
