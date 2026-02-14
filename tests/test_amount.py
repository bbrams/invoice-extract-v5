"""Tests for amount and currency extraction."""

import pytest
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.extractors.date_amount import extract_amount_and_currency


class TestAmountWithTemplate:
    """Test amount extraction using supplier templates."""

    def test_etisalat_amount(self, etisalat_text):
        template = {
            "default_currency": "AED",
            "amount_patterns": [
                {"pattern": r"Total\s*Amount\s*Due\s*([\d.,\s]+)", "priority": 1},
                {"pattern": r"Grand\s*total[^\n]*?([\d][\d.,\s]*\d)", "priority": 2},
            ]
        }
        amount, currency = extract_amount_and_currency(etisalat_text, template)
        assert amount is not None
        assert float(amount) == pytest.approx(960.34, abs=0.01)
        assert currency == "AED"

    def test_aws_amount(self, aws_text):
        template = {
            "default_currency": "USD",
            "amount_patterns": [
                {"pattern": r"TOTAL AMOUNT DUE.*?\$([0-9.,]+)", "priority": 1},
            ]
        }
        amount, currency = extract_amount_and_currency(aws_text, template)
        assert amount is not None
        assert float(amount) == pytest.approx(592.37, abs=0.01)
        assert currency == "USD"

    def test_zoho_amount(self, zoho_text):
        template = {
            "default_currency": "USD",
            "amount_patterns": [
                {"pattern": r"Total\s*US\$([0-9.,]+)", "priority": 1},
            ]
        }
        amount, currency = extract_amount_and_currency(zoho_text, template)
        assert amount is not None
        assert float(amount) == pytest.approx(2100.00, abs=0.01)
        assert currency == "USD"

    def test_du_amount(self, du_text):
        template = {
            "default_currency": "AED",
            "amount_patterns": [
                {"pattern": r"Total\s*amount\s*due.*?AED\s*([0-9.,]+)", "priority": 1},
            ]
        }
        amount, currency = extract_amount_and_currency(du_text, template)
        assert amount is not None
        assert float(amount) == pytest.approx(167.16, abs=0.01)
        assert currency == "AED"


class TestAmountGeneric:
    """Test generic amount extraction without template."""

    def test_usd_total(self):
        text = "Subtotal $300.00\nTax $15.00\nTotal $315.00"
        amount, currency = extract_amount_and_currency(text)
        assert amount is not None
        # Should find one of the amounts
        assert float(amount) > 0

    def test_eur_total(self):
        text = "Total à payer 263,97 €"
        amount, currency = extract_amount_and_currency(text)
        assert amount is not None
        assert float(amount) == pytest.approx(263.97, abs=0.01)
        assert currency == "EUR"

    def test_aed_total(self):
        text = "Total Payable AED 694.08"
        amount, currency = extract_amount_and_currency(text)
        assert amount is not None
        assert float(amount) == pytest.approx(694.08, abs=0.01)
        assert currency == "AED"

    def test_no_amount(self):
        text = "No monetary amounts here"
        amount, currency = extract_amount_and_currency(text)
        assert amount is None


class TestAmountOCRArtifacts:
    """Test handling of OCR-broken amounts."""

    def test_space_before_decimal(self):
        text = "Grand total (Incl 5% VAT)960 .34"
        amount, currency = extract_amount_and_currency(text)
        assert amount is not None
        assert float(amount) == pytest.approx(960.34, abs=0.01)

    def test_space_as_thousands(self):
        text = "Total Amount Due 1 499.70"
        amount, currency = extract_amount_and_currency(text)
        assert amount is not None
        assert float(amount) == pytest.approx(1499.70, abs=0.01)


class TestCurrencyDetection:
    """Test currency detection from context."""

    def test_usd_from_dollar_sign(self):
        text = "Total: $500.00"
        amount, currency = extract_amount_and_currency(text)
        assert currency == "USD"

    def test_eur_from_euro_sign(self):
        text = "Total: 500.00 €"
        amount, currency = extract_amount_and_currency(text)
        assert currency == "EUR"

    def test_aed_from_text(self):
        text = "Total Payable AED 500.00"
        amount, currency = extract_amount_and_currency(text)
        assert currency == "AED"

    def test_hilton_amount(self, hilton_text):
        template = {
            "default_currency": "AED",
            "amount_patterns": [
                {"pattern": r"BALANCE\s*([0-9.,]+)", "priority": 1},
            ]
        }
        amount, currency = extract_amount_and_currency(hilton_text, template)
        assert amount is not None
        assert float(amount) == pytest.approx(830.00, abs=0.01)
        assert currency == "AED"


class TestFrenchAmount:
    """Test French invoice amount extraction."""

    def test_french_total(self, french_text):
        amount, currency = extract_amount_and_currency(french_text)
        assert amount is not None
        assert float(amount) == pytest.approx(263.97, abs=0.01)
        assert currency == "EUR"
