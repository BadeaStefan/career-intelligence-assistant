"""Turn uploaded bytes into plain text.

The only branch in the ingest pipeline. Everything downstream -- chunking,
extraction, embedding -- operates on the text this module produces, so a
resume and a job posting follow identical paths from here on.
"""

import io

from docx import Document as DocxDocument
from pydantic import BaseModel
from pypdf import PdfReader

PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_TYPES = frozenset({"text/plain", "text/markdown", "application/octet-stream"})

SUPPORTED_TYPES = frozenset({PDF_TYPE, DOCX_TYPE}) | TEXT_TYPES

MIN_USABLE_CHARS = 50
"""Below this, a document is treated as having produced no usable text.

Neither a resume nor a job posting can be meaningfully shorter than this. For
PDFs the cause is almost always a missing text layer -- a scan -- which is the
case worth failing loudly on.
"""

MAX_PDF_PAGES = 50
"""Upper bound on pages in an uploaded PDF.

The byte cap does not bound the work. A 5 MB PDF can hold thousands of mostly
empty pages, and parsing runs inside the request, so page count needs its own
limit or a small upload can still occupy a worker for a long time. Generous
enough that no real resume or job posting comes close. Spec section 8.
"""


class ParsedDocument(BaseModel):
    text: str
    page_count: int | None = None


class UnsupportedDocumentError(Exception):
    """The upload is not a type this system can read."""


class EmptyDocumentError(Exception):
    """Parsing succeeded but produced no usable text."""


def parse_document(data: bytes, filename: str, content_type: str) -> ParsedDocument:
    """Extract plain text from an uploaded document.

    Dispatch is on ``content_type``, never on the filename extension: the
    filename is user-controlled text, so a PDF named ``.txt`` would otherwise
    reach the text decoder and yield mojibake that looks like a successful
    parse rather than an error.
    """
    normalised = content_type.split(";")[0].strip().lower()

    if normalised == PDF_TYPE:
        parsed = _parse_pdf(data)
    elif normalised == DOCX_TYPE:
        parsed = _parse_docx(data)
    elif normalised in TEXT_TYPES:
        parsed = _parse_text(data)
    else:
        raise UnsupportedDocumentError(
            f"{filename!r} has unsupported content type {normalised!r};"
            f" expected one of {sorted(SUPPORTED_TYPES)}"
        )

    if len(parsed.text.strip()) < MIN_USABLE_CHARS:
        raise EmptyDocumentError(
            f"{filename!r} produced no usable text."
            " If this is a scanned document it has no text layer, and OCR is not supported."
        )

    return parsed


def _parse_pdf(data: bytes) -> ParsedDocument:
    reader = PdfReader(io.BytesIO(data))
    page_count = len(reader.pages)

    # Checked before extracting anything: the point of the cap is to avoid
    # doing the work, so discovering the size after paying for it would be
    # pointless.
    if page_count > MAX_PDF_PAGES:
        raise UnsupportedDocumentError(
            f"PDF has {page_count} pages; the maximum accepted is {MAX_PDF_PAGES}."
        )

    pages = [page.extract_text() or "" for page in reader.pages]

    return ParsedDocument(text="\n".join(pages).strip(), page_count=page_count)


def _parse_docx(data: bytes) -> ParsedDocument:
    document = DocxDocument(io.BytesIO(data))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]

    return ParsedDocument(text="\n".join(paragraphs).strip())


def _parse_text(data: bytes) -> ParsedDocument:
    # errors="replace" rather than raising: a stray byte in an otherwise fine
    # document should not fail the upload, and the MIN_USABLE_CHARS check below
    # still catches a file that decodes to nothing meaningful.
    return ParsedDocument(text=data.decode("utf-8", errors="replace").strip())
