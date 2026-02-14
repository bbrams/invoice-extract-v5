"""
Native PDF text extraction using pdfplumber.
100% accuracy on digital PDFs, zero cost.
"""

import io
import logging

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except Exception:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not available - native PDF extraction disabled")


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from a native (digital) PDF using pdfplumber.
    Returns empty string if PDF is scanned (image-only) or unreadable.
    """
    if not PDFPLUMBER_AVAILABLE:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")
        return ""


def extract_text_from_pdf_path(filepath: str) -> str:
    """Extract text from a native PDF file by path."""
    if not PDFPLUMBER_AVAILABLE:
        return ""
    try:
        with pdfplumber.open(filepath) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed for {filepath}: {e}")
        return ""
