"""
Google Cloud Vision OCR for scanned PDFs and images.
Fallback when pdfplumber cannot extract text.
"""

import io
import logging
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def ocr_image(vision_client, image: Image.Image) -> str:
    """OCR a single PIL Image using Google Cloud Vision API."""
    from google.cloud import vision

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    vision_image = vision.Image(content=buf.getvalue())
    response = vision_client.text_detection(image=vision_image)
    if response.error.message:
        raise Exception(f"Vision API error: {response.error.message}")
    if response.full_text_annotation:
        return response.full_text_annotation.text
    return ""


def ocr_pdf_bytes(vision_client, pdf_bytes: bytes) -> str:
    """OCR a PDF by converting pages to images and running Vision API."""
    import pdf2image

    images = pdf2image.convert_from_bytes(pdf_bytes)
    texts = []
    for image in images:
        text = ocr_image(vision_client, image)
        if text:
            texts.append(text)
    return "\n".join(texts)


def ocr_pdf_path(vision_client, filepath: str) -> str:
    """OCR a PDF file by path."""
    import pdf2image

    images = pdf2image.convert_from_path(filepath)
    texts = []
    for image in images:
        text = ocr_image(vision_client, image)
        if text:
            texts.append(text)
    return "\n".join(texts)


def ocr_image_path(vision_client, filepath: str) -> str:
    """OCR an image file by path."""
    image = Image.open(filepath)
    return ocr_image(vision_client, image)
