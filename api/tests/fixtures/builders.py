"""Builders for binary test fixtures.

Generated rather than committed. A checked-in ``scanned.pdf`` is an opaque
blob that no reviewer can verify; ``make_imageonly_pdf()`` states plainly that
the page carries no text layer.
"""

import io

from docx import Document as DocxDocument
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def make_text_pdf(lines: list[str]) -> bytes:
    """A single-page PDF with a real, extractable text layer."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)

    y = 720
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 18

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_imageonly_pdf() -> bytes:
    """A single-page PDF with no text layer at all.

    Stands in for a scanned resume: the page renders visibly (a filled
    rectangle) but text extraction yields nothing. Without OCR this document
    cannot be analysed, so ingest must reject it loudly rather than proceed
    to a fit analysis with zero requirements.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)

    pdf.rect(72, 600, 400, 120, fill=1)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    buffer = io.BytesIO()
    document = DocxDocument()

    for paragraph in paragraphs:
        document.add_paragraph(paragraph)

    document.save(buffer)
    return buffer.getvalue()


RESUME_LINES = [
    "Jane Doe - Senior Backend Engineer",
    "jane@example.com | London, UK",
    "",
    "EXPERIENCE",
    "Acme Corp, Staff Engineer, 2021-2025",
    "Built a sharded event store handling 40k requests per second.",
    "Migrated core billing services from Python to Go.",
    "Led a team of four engineers across two time zones.",
]
