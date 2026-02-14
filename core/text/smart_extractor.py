"""
Smart text extractor: tries pdfplumber first (free, 100% accurate on native PDFs),
falls back to Google Cloud Vision OCR only for scanned PDFs and images.
"""

import logging
import os
from typing import Tuple, Optional

from .pdfplumber_extractor import extract_text_from_pdf_path, extract_text_from_pdf_bytes
from .vision_ocr import ocr_pdf_path, ocr_pdf_bytes, ocr_image_path

logger = logging.getLogger(__name__)

# Minimum chars for pdfplumber text to be considered usable
MIN_TEXT_LENGTH = 50

SUPPORTED_FORMATS = ('.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.bmp')


class SmartTextExtractor:
    """
    Chooses the best extraction method automatically:
    - pdfplumber for native (digital) PDFs -> 100% accuracy, $0 cost
    - Google Vision OCR for scanned PDFs and images -> ~98% accuracy, ~$0.0015/page
    """

    def __init__(self, vision_client=None):
        self.vision_client = vision_client

    def extract_from_path(self, filepath: str) -> Tuple[str, str]:
        """
        Extract text from a file path.
        Returns (text, method) where method is 'pdfplumber' or 'vision_ocr'.
        """
        ext = os.path.splitext(filepath)[1].lower()

        if ext == '.pdf':
            # Try pdfplumber first (free, instant, perfect for native PDFs)
            text = extract_text_from_pdf_path(filepath)
            if text and len(text.strip()) >= MIN_TEXT_LENGTH:
                logger.info(f"pdfplumber extracted {len(text)} chars from {os.path.basename(filepath)}")
                return text, "pdfplumber"

            # Fallback to Vision OCR (scanned PDF)
            if self.vision_client:
                logger.info(f"Falling back to Vision OCR for {os.path.basename(filepath)}")
                text = ocr_pdf_path(self.vision_client, filepath)
                return text, "vision_ocr"
            else:
                return text or "", "pdfplumber"

        elif ext in ('.jpg', '.jpeg', '.png', '.tiff', '.bmp'):
            # Images always need OCR
            if self.vision_client:
                text = ocr_image_path(self.vision_client, filepath)
                return text, "vision_ocr"
            else:
                raise ValueError(f"Vision client required for image OCR: {filepath}")

        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> Tuple[str, str]:
        """
        Extract text from file bytes (for Cloud Function use).
        Returns (text, method).
        """
        ext = os.path.splitext(filename)[1].lower()

        if ext == '.pdf':
            text = extract_text_from_pdf_bytes(file_bytes)
            if text and len(text.strip()) >= MIN_TEXT_LENGTH:
                return text, "pdfplumber"

            if self.vision_client:
                text = ocr_pdf_bytes(self.vision_client, file_bytes)
                return text, "vision_ocr"
            else:
                return text or "", "pdfplumber"

        elif ext in ('.jpg', '.jpeg', '.png', '.tiff', '.bmp'):
            if self.vision_client:
                from PIL import Image
                import io
                image = Image.open(io.BytesIO(file_bytes))
                from .vision_ocr import ocr_image
                text = ocr_image(self.vision_client, image)
                return text, "vision_ocr"
            else:
                raise ValueError("Vision client required for image OCR")

        else:
            raise ValueError(f"Unsupported file format: {ext}")

    @staticmethod
    def is_supported(filename: str) -> bool:
        return filename.lower().endswith(SUPPORTED_FORMATS)

    @staticmethod
    def validate_file(filepath: str) -> Tuple[bool, Optional[str]]:
        """Validate file before processing. Returns (is_valid, error_message)."""
        if not os.path.exists(filepath):
            return False, "File not found"
        if not os.access(filepath, os.R_OK):
            return False, "File not readable (permission denied)"
        if os.path.getsize(filepath) == 0:
            return False, "File is empty (0 bytes)"
        if filepath.lower().endswith('.pdf'):
            try:
                with open(filepath, 'rb') as f:
                    header = f.read(8)
                    if not header.startswith(b'%PDF-'):
                        return False, "Not a valid PDF file (missing PDF header)"
            except Exception:
                return False, "Cannot read PDF file"
        return True, None
