from career_intel.ingest.locate import locate_quote

RAW = "Jane Doe\n\nBuilt a sharded event store\nhandling 40k rps in Python.\n"


def test_exact_match_returns_span():
    span = locate_quote(RAW, "sharded event store")
    assert RAW[span.start : span.end] == "sharded event store"


def test_whitespace_normalised_match_maps_back_to_original_offsets():
    # Extraction routinely collapses the newline into a space.
    span = locate_quote(RAW, "sharded event store handling 40k rps")
    assert span is not None
    assert "sharded event store" in RAW[span.start : span.end]
    assert "40k rps" in RAW[span.start : span.end]


def test_paraphrase_returns_none_rather_than_guessing():
    # A failed location is a grounding signal: the model altered the text.
    assert locate_quote(RAW, "managed a large distributed system") is None


def test_multiple_occurrences_resolve_to_the_first():
    raw = "Python. Later, Python."
    assert locate_quote(raw, "Python").start == 0
