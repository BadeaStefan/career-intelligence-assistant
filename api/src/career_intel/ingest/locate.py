"""Locate a model-quoted span in source text. The model quotes, we locate.

An LLM asked for ``char_start`` returns plausible integers pointing at the
wrong text -- worse than no citation, since it looks authoritative. So
extraction returns a verbatim quote instead, and this module finds it.
Exactly two strategies; no fuzzy matching. A similarity-threshold match can
highlight the *wrong* span, which is the exact failure this function exists
to prevent -- ``None`` is honest, approximately-right is not.
"""

from dataclasses import dataclass

_UNICODE_NORMALIZE = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
}


@dataclass(frozen=True)
class Span:
    start: int
    end: int


def locate_quote(raw_text: str, quote: str) -> Span | None:
    index = raw_text.find(quote)
    if index != -1:
        return Span(start=index, end=index + len(quote))

    normalized_raw, spans = _normalize_with_map(raw_text)
    normalized_quote, _ = _normalize_with_map(quote)
    normalized_quote = normalized_quote.strip()
    if not normalized_quote:
        return None

    match_index = normalized_raw.find(normalized_quote)
    if match_index == -1:
        return None

    start = spans[match_index][0]
    end = spans[match_index + len(normalized_quote) - 1][1]
    return Span(start=start, end=end)


def _normalize_with_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Collapse whitespace runs and normalise unicode punctuation.

    Returns the normalised text alongside, for each normalised character,
    the ``(start, end)`` span of original characters it came from -- so a
    match found in the normalised text maps back to real offsets.
    """
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            chars.append(" ")
            spans.append((i, j))
            i = j
            continue
        chars.append(_UNICODE_NORMALIZE.get(ch, ch))
        spans.append((i, i + 1))
        i += 1
    return "".join(chars), spans
