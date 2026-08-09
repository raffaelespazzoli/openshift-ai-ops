"""Markdown runbook chunker — heading-aware, token-bounded (AD-13).

Splits markdown files into chunks that preserve heading hierarchy,
respect token limits, and maintain cross-boundary overlap for continuity.
"""

from __future__ import annotations

import re

from ..models.knowledge import RunbookChunk


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token for English text."""
    return max(1, len(text) // 4)


def _split_on_headings(content: str) -> list[tuple[list[str], str]]:
    """Split markdown content on heading boundaries, tracking hierarchy.

    Returns list of (heading_hierarchy, section_content) tuples.
    """
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    sections: list[tuple[list[str], str]] = []
    current_hierarchy: list[str] = []
    last_pos = 0

    for match in heading_pattern.finditer(content):
        if last_pos < match.start():
            section_text = content[last_pos:match.start()].strip()
            if section_text:
                sections.append((list(current_hierarchy), section_text))

        level = len(match.group(1))
        heading_text = match.group(2).strip()

        current_hierarchy = current_hierarchy[:level - 1]
        while len(current_hierarchy) < level - 1:
            current_hierarchy.append("")
        current_hierarchy.append(heading_text)

        last_pos = match.end()

    trailing = content[last_pos:].strip()
    if trailing:
        sections.append((list(current_hierarchy), trailing))

    return sections


def _split_oversized(text: str, max_tokens: int) -> list[str]:
    """Split a single oversized block by sentence, then by character."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 1:
        char_budget = max_tokens * 4
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for sentence in sentences:
            s_tokens = _estimate_tokens(sentence)
            if s_tokens > max_tokens:
                if current:
                    chunks.append(" ".join(current))
                    current = []
                    current_tokens = 0
                chunks.extend(
                    sentence[i:i + char_budget]
                    for i in range(0, len(sentence), char_budget)
                )
                continue
            if current_tokens + s_tokens > max_tokens and current:
                chunks.append(" ".join(current))
                current = []
                current_tokens = 0
            current.append(sentence)
            current_tokens += s_tokens
        if current:
            chunks.append(" ".join(current))
        return chunks

    char_budget = max_tokens * 4
    return [text[i:i + char_budget] for i in range(0, len(text), char_budget)]


def _split_paragraph(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split text on paragraph boundaries when it exceeds max_tokens."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)

        if para_tokens > max_tokens:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_tokens = 0
            sub_parts = _split_oversized(para, max_tokens)
            chunks.extend(sub_parts)
            continue

        if current_tokens + para_tokens > max_tokens and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            overlap_text = ""
            overlap_count = 0
            for prev_para in reversed(current_chunk):
                prev_tokens = _estimate_tokens(prev_para)
                if overlap_count + prev_tokens > overlap_tokens:
                    break
                overlap_text = prev_para + ("\n\n" + overlap_text if overlap_text else "")
                overlap_count += prev_tokens

            if overlap_text and overlap_count + para_tokens > max_tokens:
                overlap_text = ""
                overlap_count = 0

            current_chunk = [overlap_text] if overlap_text else []
            current_tokens = overlap_count

        current_chunk.append(para)
        current_tokens += para_tokens

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def chunk_markdown(
    content: str,
    source_file: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[RunbookChunk]:
    """Split a markdown document into token-bounded chunks.

    Strategy:
    1. Split on heading boundaries (##, ###) first
    2. If a section exceeds max_tokens, split on paragraph boundaries
    3. Preserve heading hierarchy in chunk metadata
    4. Overlap ensures cross-boundary continuity

    Args:
        content: The full markdown content.
        source_file: The source file path for provenance.
        max_tokens: Maximum tokens per chunk.
        overlap_tokens: Token overlap between consecutive chunks.

    Returns:
        List of RunbookChunk objects ready for embedding.
    """
    if not content.strip():
        return []

    sections = _split_on_headings(content)
    if not sections:
        sections = [([], content.strip())]

    chunks: list[RunbookChunk] = []
    chunk_index = 0

    for hierarchy, section_text in sections:
        section_tokens = _estimate_tokens(section_text)

        if section_tokens <= max_tokens:
            chunks.append(RunbookChunk(
                source_file=source_file,
                chunk_index=chunk_index,
                heading_hierarchy=[h for h in hierarchy if h],
                content=section_text,
                token_count=section_tokens,
            ))
            chunk_index += 1
        else:
            sub_chunks = _split_paragraph(section_text, max_tokens, overlap_tokens)
            for sub in sub_chunks:
                sub_tokens = _estimate_tokens(sub)
                chunks.append(RunbookChunk(
                    source_file=source_file,
                    chunk_index=chunk_index,
                    heading_hierarchy=[h for h in hierarchy if h],
                    content=sub,
                    token_count=sub_tokens,
                ))
                chunk_index += 1

    return chunks
