"""Structure-aware chunking with trustworthy offsets.

Splits on paragraph boundaries and accumulates to ``target_tokens``, unlike
LLM-produced spans (``locate.py``) these offsets are computed by us against
text we already hold, so they are correct by construction -- no location
step needed.
"""

import re
from dataclasses import dataclass

from career_intel.llm.tokens import count_tokens

_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    text: str
    char_start: int
    char_end: int


def _paragraphs(text: str) -> list[tuple[int, int]]:
    """Character spans of each paragraph, in source order."""
    spans = []
    pos = 0
    for piece in _PARAGRAPH_SPLIT.split(text):
        start = text.index(piece, pos)
        end = start + len(piece)
        spans.append((start, end))
        pos = end
    return spans


def chunk_text(
    text: str, *, target_tokens: int = 400, overlap_tokens: int = 60
) -> list[TextChunk]:
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be non-negative and smaller than target_tokens")

    paragraphs = _paragraphs(text)
    text_start = paragraphs[0][0]
    text_end = paragraphs[-1][1]
    paragraph_ends = [end for _, end in paragraphs]

    chunks: list[TextChunk] = []
    chunk_start = text_start
    while chunk_start < text_end:
        budget_end = _largest_end_within_tokens(text, chunk_start, text_end, target_tokens)
        paragraph_end = max(
            (end for end in paragraph_ends if chunk_start < end <= budget_end),
            default=budget_end,
        )
        chunk_end = paragraph_end
        chunks.append(
            TextChunk(
                ordinal=len(chunks),
                text=text[chunk_start:chunk_end],
                char_start=chunk_start,
                char_end=chunk_end,
            )
        )

        if chunk_end == text_end:
            break
        chunk_start = _overlap_start(text, chunk_end, overlap_tokens)

    return chunks


def _largest_end_within_tokens(text: str, start: int, end: int, target_tokens: int) -> int:
    """Farthest character boundary whose source slice fits the token budget."""
    low = start + 1
    high = end
    best = start
    while low <= high:
        candidate = (low + high) // 2
        if count_tokens(text[start:candidate]) <= target_tokens:
            best = candidate
            low = candidate + 1
        else:
            high = candidate - 1

    if best == start:
        raise ValueError("target_tokens is too small for the next source character")
    while count_tokens(text[start:best]) > target_tokens:
        best -= 1
    return best


def _overlap_start(text: str, chunk_end: int, overlap_tokens: int) -> int:
    """Walk backwards from ``chunk_end`` until roughly ``overlap_tokens`` are covered."""
    start = chunk_end
    while start > 0 and count_tokens(text[start:chunk_end]) < overlap_tokens:
        start -= 1
    return start
