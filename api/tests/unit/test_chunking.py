from career_intel.ingest.chunking import chunk_text
from career_intel.llm.tokens import count_tokens

LONG_TEXT = "\n\n".join(f"Paragraph {i}. " + ("word " * 80) for i in range(20))


def test_offsets_round_trip():
    chunks = chunk_text(LONG_TEXT)
    for chunk in chunks:
        assert LONG_TEXT[chunk.char_start : chunk.char_end] == chunk.text


def test_consecutive_chunks_overlap():
    chunks = chunk_text(LONG_TEXT)
    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.char_start < previous.char_end


def test_short_input_yields_exactly_one_chunk():
    chunks = chunk_text("Just a short resume summary.")
    assert len(chunks) == 1
    assert chunks[0].text == "Just a short resume summary."
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len("Just a short resume summary.")


def test_ordinals_are_contiguous_from_zero():
    chunks = chunk_text(LONG_TEXT)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_single_oversized_paragraph_is_split_to_target_tokens():
    text = "word " * 1_000

    chunks = chunk_text(text, target_tokens=400, overlap_tokens=60)

    assert len(chunks) > 1
    assert all(count_tokens(chunk.text) <= 400 for chunk in chunks)
    assert all(text[chunk.char_start : chunk.char_end] == chunk.text for chunk in chunks)
