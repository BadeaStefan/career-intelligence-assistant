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
    paragraphs = _paragraphs(text)

    chunks: list[TextChunk] = []
    chunk_start: int | None = None
    chunk_end = 0
    chunk_tokens = 0

    for para_start, para_end in paragraphs:
        para_tokens = count_tokens(text[para_start:para_end])

        if chunk_start is not None and chunk_tokens + para_tokens > target_tokens:
            chunks.append(
                TextChunk(
                    ordinal=len(chunks),
                    text=text[chunk_start:chunk_end],
                    char_start=chunk_start,
                    char_end=chunk_end,
                )
            )
            chunk_start = _overlap_start(text, chunk_end, overlap_tokens)
            chunk_tokens = count_tokens(text[chunk_start:chunk_end])

        if chunk_start is None:
            chunk_start = para_start

        chunk_end = para_end
        chunk_tokens += para_tokens

    if chunk_start is not None:
        chunks.append(
            TextChunk(
                ordinal=len(chunks),
                text=text[chunk_start:chunk_end],
                char_start=chunk_start,
                char_end=chunk_end,
            )
        )

    return chunks


def _overlap_start(text: str, chunk_end: int, overlap_tokens: int) -> int:
    """Walk backwards from ``chunk_end`` until roughly ``overlap_tokens`` are covered."""
    start = chunk_end
    while start > 0 and count_tokens(text[start:chunk_end]) < overlap_tokens:
        start -= 1
    return start
