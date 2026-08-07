"""PDF text extraction — the "digital text layer" half of the pipeline in
PDF_IMPORT.md §3. OCR is explicitly out of scope for v1 (§10); when a PDF
has no text layer at all, `extract_pdf_text` returns "" and the caller
(app/services/pdf_importer.py) routes the whole file to Needs Review
instead of guessing.
"""

from __future__ import annotations

import io

import pdfplumber


class PdfExtractionError(Exception):
    """Base class for PDF errors that should surface a specific,
    human-readable message rather than a generic 500 (PDF_IMPORT.md §6)."""


class PdfPasswordProtectedError(PdfExtractionError):
    pass


class PdfUnreadableError(PdfExtractionError):
    pass


def extract_pdf_text(data: bytes) -> str:
    """Extract the digital text layer from a PDF, page by page, joined
    with newlines. Returns "" (not an error) when the PDF opens fine but
    has no extractable text — that's a scanned/image-only PDF, and routing
    it is a decision for the caller, not this function.
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - pdfminer raises several types
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise PdfPasswordProtectedError(
                "This PDF is password-protected — remove the password and re-upload"
            ) from exc
        raise PdfUnreadableError(
            "This file could not be read as a PDF — it may be corrupt"
        ) from exc

    try:
        with pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:  # noqa: BLE001
        raise PdfUnreadableError(
            "This file could not be read as a PDF — it may be corrupt"
        ) from exc

    return "\n".join(pages_text).strip()
