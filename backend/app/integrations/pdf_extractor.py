"""PDF text extraction — the "digital text layer" half of the pipeline in
PDF_IMPORT.md §3. OCR is explicitly out of scope for v1 (§10); when a PDF
has no text layer at all, `extract_pdf_text` returns "" and the caller
(app/services/pdf_importer.py) routes the whole file to Needs Review
instead of guessing.
"""

from __future__ import annotations

import io

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError

from app.core.config import settings


class PdfExtractionError(Exception):
    """Base class for PDF errors that should surface a specific,
    human-readable message rather than a generic 500 (PDF_IMPORT.md §6)."""


class PdfPasswordProtectedError(PdfExtractionError):
    pass


class PdfUnreadableError(PdfExtractionError):
    pass


class PdfTooManyPagesError(PdfExtractionError):
    pass


def extract_pdf_text(data: bytes) -> str:
    """Extract the digital text layer from a PDF, page by page, joined
    with newlines. Returns "" (not an error) when the PDF opens fine but
    has no extractable text — that's a scanned/image-only PDF, and routing
    it is a decision for the caller, not this function.
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except PDFEncryptionError as exc:
        # pdfminer raises this (often with an *empty* exception message —
        # confirmed against a real encrypted PDF, not just read off the
        # library's docs) for both "wrong/missing password" and "we don't
        # support this encryption scheme". Either way it's the same user
        # story: remove the password and re-upload. Caught by type, not
        # by sniffing the message text, precisely because that message
        # can't be relied on to say "password" at all.
        raise PdfPasswordProtectedError(
            "This PDF is password-protected — remove the password and re-upload"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - pdfminer raises several types
        raise PdfUnreadableError(
            "This file could not be read as a PDF — it may be corrupt"
        ) from exc

    try:
        with pdf:
            if len(pdf.pages) > settings.pdf_max_pages:
                raise PdfTooManyPagesError(
                    f"PDF has more than {settings.pdf_max_pages} pages — "
                    "booking confirmations are expected to be short; split "
                    "or trim the document and re-upload"
                )
            pages_text = [page.extract_text() or "" for page in pdf.pages]
    except PdfTooManyPagesError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PdfUnreadableError(
            "This file could not be read as a PDF — it may be corrupt"
        ) from exc

    return "\n".join(pages_text).strip()
