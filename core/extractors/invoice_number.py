"""
Invoice number extraction with contextual patterns and validation.
Uses supplier template patterns when available, generic patterns as fallback.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# Generic invoice number patterns, ordered by specificity (most specific first)
GENERIC_PATTERNS = [
    # Document/Tax Invoice Number with explicit label
    r'Document\s*Number\s*:\s*([A-Za-z0-9-]+)',
    r'Tax\s*Invoice\s*Number\s*:?\s*([A-Za-z0-9-]+)',
    r'Tax\s*Invoice\s*No\.?\s*:?\s*([A-Za-z0-9-]+)',
    r'Tax\s*Invoice#\s*([A-Za-z0-9-]+)',

    # Standard invoice patterns
    r'Invoice\s*number\s*:?\s*([A-Za-z0-9/-]+)',
    r'Invoice\s*#\s*([A-Za-z0-9/-]+)',
    r'Invoice\s*Number\s*:?\s*([A-Za-z0-9/-]+)',
    r'Invoice\s*No\.?\s*:?\s*([A-Za-z0-9/-]+)',
    r'Invoice\s*ID\s*:?\s*([A-Za-z0-9-]+)',

    # French format
    r'Num[ée]ro\s*(?:de\s*)?(?:la\s*)?facture\s*:?\s*([A-Za-z0-9/-]+)',
    r'Facture\s*(?:n[o°]|#)\s*:?\s*([A-Za-z0-9/-]+)',

    # Bill patterns
    r'Bill\s*number\s*:?\s*([A-Za-z0-9]+)',
    r'Your\s*bill\s*number\s*:?\s*([0-9]+)',

    # Receipt
    r'Receipt\s*#?\s*:?\s*([A-Za-z0-9-]+)',

    # Customer invoice
    r'Customer\s*Invoices?\s*([A-Za-z0-9/]+)',
]


def extract_invoice_number(text: str, supplier_template: Optional[dict] = None) -> Optional[str]:
    """
    Extract invoice number from text.
    Uses supplier-specific pattern first if available, then generic patterns.
    Returns the invoice number with # prefix, or None.
    """
    # Phase 1: Try supplier-specific pattern (lighter validation — context already confirms)
    if supplier_template and supplier_template.get("invoice_number_pattern"):
        pattern = supplier_template["invoice_number_pattern"]
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num = match.group(1).strip()
            if _is_valid_template_match(num):
                return f"#{num}"

    # Phase 2: Generic patterns in order of specificity
    for pattern in GENERIC_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num = match.group(1).strip()
            if _is_valid_invoice_number(num):
                return f"#{num}"

    return None


def _is_valid_template_match(num: str) -> bool:
    """
    Light validation for template-matched invoice numbers.
    Template context already confirms this is an invoice field.
    """
    if not num or len(num) < 3:
        return False
    if len(num) > 30:
        return False
    return True


def _is_valid_invoice_number(num: str) -> bool:
    """
    Strict validation for generically-matched invoice numbers.
    Rejects phone numbers, postal codes, and other false positives.
    """
    if not num or len(num) < 3:
        return False

    if len(num) > 30:
        return False

    # Reject strings that are too long in pure digits (>15 digits)
    digits_only = re.sub(r'[^0-9]', '', num)
    if len(digits_only) > 15:
        return False

    # Reject common false positives
    false_positive_patterns = [
        r'^\+\d{10,}$',       # Phone number with + prefix
        r'^00\d{3}$',         # Country code-like
    ]
    for fp in false_positive_patterns:
        if re.match(fp, num):
            return False

    return True
