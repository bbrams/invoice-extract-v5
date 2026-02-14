"""Tests for invoice number extraction."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.extractors.invoice_number import extract_invoice_number


class TestInvoiceNumberWithTemplate:
    """Test invoice number extraction using supplier templates."""

    def test_etisalat_bill_number(self, etisalat_text):
        template = {"invoice_number_pattern": r"Bill\s*number\s+(INV[0-9]+)"}
        result = extract_invoice_number(etisalat_text, template)
        assert result == "#INV1965257146"

    def test_aws_invoice_number(self, aws_text):
        template = {"invoice_number_pattern": r"Invoice\s*Number:\s*([0-9]+)"}
        result = extract_invoice_number(aws_text, template)
        assert result == "#2030491957"

    def test_zoho_tax_invoice(self, zoho_text):
        template = {"invoice_number_pattern": r"Tax\s*Invoice#\s*([0-9]+)"}
        result = extract_invoice_number(zoho_text, template)
        assert result == "#131898257"

    def test_cursor_invoice_number(self, cursor_text):
        template = {"invoice_number_pattern": r"Invoice\s*number\s+([A-Za-z0-9-]+)"}
        result = extract_invoice_number(cursor_text, template)
        assert result == "#HK7WPHRD-0001"

    def test_du_bill_number(self, du_text):
        template = {"invoice_number_pattern": r"(?:Your\s*)?bill\s*number\s*:?\s*([0-9]+)"}
        result = extract_invoice_number(du_text, template)
        assert result == "#0170948179"


class TestInvoiceNumberGeneric:
    """Test generic invoice number extraction without template."""

    def test_invoice_hash_format(self):
        text = "Invoice # 68263\nDate: 15/01/2025"
        result = extract_invoice_number(text)
        assert result == "#68263"

    def test_invoice_number_colon(self):
        text = "Invoice Number: ABC-12345\nTotal: $100"
        result = extract_invoice_number(text)
        assert result == "#ABC-12345"

    def test_french_invoice_number(self, french_text):
        result = extract_invoice_number(french_text)
        assert result is not None
        assert "FR-2024-78901" in result

    def test_no_invoice_number(self):
        text = "Just some random text without any invoice information"
        result = extract_invoice_number(text)
        assert result is None

    def test_rejects_short_numbers(self):
        text = "# AB\nSomething else"
        result = extract_invoice_number(text)
        assert result is None


class TestInvoiceNumberValidation:
    """Test false positive rejection."""

    def test_rejects_phone_number_only(self):
        """Pure phone numbers should be rejected by the generic pattern,
        but the 'Bill #' pattern may still match. This tests the validator."""
        text = "Contact: +971501234567"
        result = extract_invoice_number(text)
        assert result is None

    def test_accepts_invoice_with_slashes(self):
        text = "Invoice No: INV/23-24/35111"
        result = extract_invoice_number(text)
        assert result is not None
        assert "INV/23-24/35111" in result
