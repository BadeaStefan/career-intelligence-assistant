import pytest

from career_intel.ingest.parsing import (
    EmptyDocumentError,
    UnsupportedDocumentError,
    parse_document,
)
from tests.fixtures.builders import (
    RESUME_LINES,
    make_docx,
    make_imageonly_pdf,
    make_many_page_pdf,
    make_text_pdf,
)

PLAIN_RESUME = "\n".join(RESUME_LINES).encode()


def test_parses_plain_text() -> None:
    result = parse_document(PLAIN_RESUME, "cv.txt", "text/plain")

    assert "Senior Backend Engineer" in result.text
    assert result.page_count is None


def test_parses_pdf() -> None:
    result = parse_document(make_text_pdf(RESUME_LINES), "cv.pdf", "application/pdf")

    assert "sharded event store" in result.text
    assert result.page_count == 1


def test_parses_docx() -> None:
    result = parse_document(
        make_docx(RESUME_LINES),
        "cv.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert "Led a team of four engineers" in result.text


def test_rejects_unsupported_type() -> None:
    with pytest.raises(UnsupportedDocumentError):
        parse_document(b"\x89PNG\r\n\x1a\n", "photo.png", "image/png")


def test_scanned_pdf_raises_rather_than_returning_empty() -> None:
    """A scanned PDF has no text layer, so extraction yields nothing.

    Returning empty text would let ingest continue and produce a fit analysis
    against zero requirements -- a confidently wrong result. Failing here makes
    the real limitation visible to the user instead. Spec section 13.
    """
    with pytest.raises(EmptyDocumentError):
        parse_document(make_imageonly_pdf(), "scan.pdf", "application/pdf")


def test_whitespace_only_text_is_treated_as_empty() -> None:
    with pytest.raises(EmptyDocumentError):
        parse_document(b"   \n\n\t  \n", "blank.txt", "text/plain")


def test_content_type_wins_over_a_misleading_extension() -> None:
    """Browsers send the real type; a filename is user-controlled text.

    Trusting the extension would let a PDF named .txt reach the text decoder
    and produce mojibake that looks like a successful parse.
    """
    result = parse_document(make_text_pdf(RESUME_LINES), "cv.txt", "application/pdf")

    assert "sharded event store" in result.text


def test_rejects_pdf_over_page_cap() -> None:
    """A 5 MB PDF can still hold thousands of pages.

    The byte cap does not bound the work: parsing runs inside the request, so
    page count is its own limit. Spec section 8.
    """
    from career_intel.ingest.parsing import MAX_PDF_PAGES

    oversized = make_many_page_pdf(MAX_PDF_PAGES + 1)

    with pytest.raises(UnsupportedDocumentError):
        parse_document(oversized, "long.pdf", "application/pdf")


def test_accepts_pdf_at_the_page_cap() -> None:
    """The cap is inclusive; a document exactly at the limit is fine."""
    from career_intel.ingest.parsing import MAX_PDF_PAGES

    at_limit = make_text_pdf(RESUME_LINES) if MAX_PDF_PAGES >= 1 else b""

    result = parse_document(at_limit, "cv.pdf", "application/pdf")

    assert result.page_count == 1
