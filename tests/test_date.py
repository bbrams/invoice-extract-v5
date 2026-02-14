"""Tests for date extraction."""

import pytest
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.extractors.date_amount import extract_date


class TestDateContextual:
    """Test date extraction with contextual labels."""

    def test_etisalat_date(self, etisalat_text):
        template = {"date_context": ["Bill issue date", "Bill date"]}
        result = extract_date(etisalat_text, template)
        assert result == date(2025, 1, 15)

    def test_aws_date(self, aws_text):
        template = {"date_context": ["Invoice Date"]}
        result = extract_date(aws_text, template)
        assert result == date(2025, 2, 1)

    def test_zoho_date(self, zoho_text):
        result = extract_date(zoho_text)
        assert result == date(2023, 7, 7)

    def test_cursor_date(self, cursor_text):
        template = {"date_context": ["Date of issue"]}
        result = extract_date(cursor_text, template)
        assert result == date(2025, 4, 10)

    def test_hilton_date(self, hilton_text):
        template = {"date_context": ["INVOICE ISSUED"]}
        result = extract_date(hilton_text, template)
        assert result == date(2025, 1, 3)


class TestDateFormats:
    """Test various date format parsing."""

    def test_dd_mm_yyyy_slash(self):
        text = "Invoice Date: 24/11/2023"
        result = extract_date(text)
        assert result == date(2023, 11, 24)

    def test_ordinal_date(self):
        text = "Invoice Date: 22nd Dec 2024"
        result = extract_date(text)
        assert result == date(2024, 12, 22)

    def test_month_name_full(self):
        text = "Tax Invoice Issue Date 19 February 2025"
        result = extract_date(text)
        assert result == date(2025, 2, 19)

    def test_abbreviated_month(self):
        text = "DATE OF ISSUE: 24-Feb-2025"
        result = extract_date(text)
        assert result == date(2025, 2, 24)

    def test_iso_format(self):
        text = "Date: 2025-03-15"
        result = extract_date(text)
        assert result == date(2025, 3, 15)

    def test_dot_separator(self):
        text = "Date: 15.03.2025"
        result = extract_date(text)
        assert result == date(2025, 3, 15)


class TestDateFrench:
    """Test French date parsing."""

    def test_french_month_name(self, french_text):
        result = extract_date(french_text)
        assert result == date(2024, 3, 15)


class TestDatePriority:
    """Test that invoice date is preferred over due date."""

    def test_prefers_invoice_date(self):
        text = """Due Date: 15/03/2025
Invoice Date: 15/02/2025
Payment Date: 20/03/2025"""
        result = extract_date(text)
        assert result == date(2025, 2, 15)

    def test_no_date_returns_none(self):
        text = "No date information here at all"
        result = extract_date(text)
        assert result is None


class TestDateDU:
    """Test DU telecom date with ordinals."""

    def test_du_ordinal_date(self, du_text):
        template = {"date_context": ["Bill date", "Bill issue date"]}
        result = extract_date(du_text, template)
        assert result == date(2024, 12, 22)
