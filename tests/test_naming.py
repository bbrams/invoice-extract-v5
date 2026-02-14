"""Tests for filename generation."""

import pytest
import sys
import os
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.models import InvoiceData
from core.naming import generate_filename


class TestBasicNaming:
    """Test basic filename generation."""

    def test_full_data(self):
        data = InvoiceData(
            supplier="AWS",
            invoice_number="#2030491957",
            invoice_date=date(2025, 2, 1),
            amount=Decimal("592.37"),
            currency="USD",
        )
        result = generate_filename(data, "original.pdf")
        assert result == "AWS_#2030491957_01-02-2025_592.37USD.pdf"

    def test_missing_fields(self):
        data = InvoiceData(supplier="Unknown")
        result = generate_filename(data, "test.pdf")
        assert result == "Unknown_NoNum_NoDate_0.00XXX.pdf"

    def test_accounting_prefix(self):
        data = InvoiceData(
            supplier="Etisalat",
            invoice_number="#INV123",
            invoice_date=date(2025, 1, 15),
            amount=Decimal("960.34"),
            currency="AED",
        )
        result = generate_filename(
            data, "PUR 25-0024_old.pdf",
            accounting_prefix="PUR 25-0024_",
        )
        assert result.startswith("PUR 25-0024_Etisalat_")
        assert result.endswith(".pdf")

    def test_vat_quarter(self):
        data = InvoiceData(
            supplier="AWS",
            invoice_number="#123",
            invoice_date=date(2025, 3, 15),
            amount=Decimal("100.00"),
            currency="USD",
        )
        result = generate_filename(data, "test.pdf", vat_quarter="Q1-2025")
        assert "Q1-2025" in result

    def test_special_characters_cleaned(self):
        data = InvoiceData(
            supplier="Café & Résumé Ltd.",
            invoice_number="#INV/2025/001",
            invoice_date=date(2025, 1, 1),
            amount=Decimal("50.00"),
            currency="EUR",
        )
        result = generate_filename(data, "test.pdf")
        # Should not contain special chars like &, accented chars, or /
        assert '&' not in result
        assert 'é' not in result
        assert '/' not in result

    def test_preserves_extension(self):
        data = InvoiceData(supplier="Test")
        assert generate_filename(data, "file.jpg").endswith(".jpg")
        assert generate_filename(data, "file.PNG").endswith(".PNG")
        assert generate_filename(data, "file.pdf").endswith(".pdf")


class TestAccountingPrefix:
    """Test accounting prefix handling in filename."""

    def test_pur_prefix(self):
        data = InvoiceData(supplier="Vendor", invoice_number="#123")
        result = generate_filename(data, "test.pdf", accounting_prefix="PUR 25-0024_")
        assert result.startswith("PUR 25-0024_Vendor_")

    def test_pyt_vch_prefix(self):
        data = InvoiceData(supplier="Vendor", invoice_number="#123")
        result = generate_filename(data, "test.pdf", accounting_prefix="Pyt Vch 2023-1386_")
        assert result.startswith("Pyt Vch 2023-1386_Vendor_")

    def test_no_prefix(self):
        data = InvoiceData(supplier="Vendor", invoice_number="#123")
        result = generate_filename(data, "test.pdf")
        assert result.startswith("Vendor_")
