"""
Filename generation engine.
Produces clean, filesystem-safe filenames from extracted invoice data.
"""

import os
import re
import unicodedata
from typing import Optional

from .models import InvoiceData


def generate_filename(
    data: InvoiceData,
    original_filename: str,
    accounting_prefix: Optional[str] = None,
    vat_quarter: Optional[str] = None,
    dirpath: Optional[str] = None,
) -> str:
    """
    Generate invoice filename in format:
    [Prefix_]SupplierName_#InvoiceNumber_DD-MM-YYYY_AmountCurrency[_Q1-2025].ext

    If dirpath is provided, ensures uniqueness by appending counter.
    """
    ext = os.path.splitext(original_filename)[1]

    supplier = _clean_for_filename(data.supplier, "Unknown")
    invoice_num = _clean_for_filename(data.invoice_number or "", "NoNum")
    date_str = data.format_date()
    amount_str = data.format_amount()

    # Build base filename
    parts = []
    if accounting_prefix:
        # Accounting prefix already ends with '_', strip it for joining
        parts.append(accounting_prefix.rstrip('_'))
    parts.extend([supplier, invoice_num, date_str, amount_str])

    if vat_quarter:
        parts.append(vat_quarter)

    base_filename = "_".join(parts) + ext

    # Ensure uniqueness if dirpath provided
    if dirpath:
        base_filename = _ensure_unique(base_filename, dirpath, parts, ext)

    return base_filename


def _clean_for_filename(s: str, default: str) -> str:
    """Clean a string for use in a filename."""
    if not s or not s.strip():
        s = default

    # Normalize unicode (remove accents)
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii')

    # Remove invalid filename characters and special symbols
    s = re.sub(r'[/\\:*?"<>|,.&;\'()@!%^~`{}[\]+=$]', '_', s)

    # Replace spaces with underscores
    s = re.sub(r'\s+', '_', s.strip())

    # Clean up multiple underscores
    s = re.sub(r'_+', '_', s)
    s = s.strip('_')

    return s if s else default


def _ensure_unique(filename: str, dirpath: str, parts: list, ext: str) -> str:
    """Append counter to filename if it already exists in the directory."""
    candidate = os.path.join(dirpath, filename)
    counter = 1
    while os.path.exists(candidate):
        new_parts = parts + [str(counter)]
        filename = "_".join(new_parts) + ext
        candidate = os.path.join(dirpath, filename)
        counter += 1
    return filename
