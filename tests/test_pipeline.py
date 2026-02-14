"""Integration tests for the full pipeline."""

import pytest
import sys
import os
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.pipeline import InvoicePipeline


@pytest.fixture
def pipeline():
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    return InvoicePipeline(
        vision_client=None,
        suppliers_config=os.path.join(config_dir, 'suppliers.json'),
        companies_config=os.path.join(config_dir, 'companies.json'),
    )


class TestPipelineEndToEnd:
    """End-to-end pipeline tests using process_text."""

    def test_etisalat_full(self, pipeline, etisalat_text):
        result = pipeline.process_text(etisalat_text, "PUR 25-0024_old.pdf")
        assert result.invoice_data.supplier == "Etisalat"
        assert result.invoice_data.invoice_number == "#INV1965257146"
        assert result.invoice_data.invoice_date == date(2025, 1, 15)
        assert result.invoice_data.currency == "AED"
        assert result.invoice_data.amount is not None
        assert float(result.invoice_data.amount) == pytest.approx(960.34, abs=0.01)
        assert result.accounting_prefix == "PUR 25-0024_"
        assert result.vat_quarter == "Q4-2024"  # January = Q4 of previous year
        assert result.new_filename.startswith("PUR 25-0024_")
        assert "Etisalat" in result.new_filename
        assert result.invoice_data.confidence > 0.8

    def test_aws_full(self, pipeline, aws_text):
        result = pipeline.process_text(aws_text, "invoice.pdf")
        assert result.invoice_data.supplier == "AWS"
        assert result.invoice_data.invoice_number == "#2030491957"
        assert result.invoice_data.invoice_date == date(2025, 2, 1)
        assert result.invoice_data.currency == "USD"
        assert float(result.invoice_data.amount) == pytest.approx(592.37, abs=0.01)
        assert result.vat_quarter == "Q1-2025"
        assert "AWS" in result.new_filename
        assert result.invoice_data.confidence >= 0.9

    def test_zoho_full(self, pipeline, zoho_text):
        result = pipeline.process_text(zoho_text, "zoho_inv.pdf")
        assert result.invoice_data.supplier == "ZOHO"
        assert result.invoice_data.invoice_number == "#131898257"
        assert result.invoice_data.invoice_date == date(2023, 7, 7)
        assert result.invoice_data.currency == "USD"
        assert float(result.invoice_data.amount) == pytest.approx(2100.00, abs=0.01)

    def test_cursor_full(self, pipeline, cursor_text):
        result = pipeline.process_text(cursor_text, "cursor_invoice.pdf")
        assert result.invoice_data.supplier == "Cursor"
        assert result.invoice_data.invoice_number == "#HK7WPHRD-0001"
        assert result.invoice_data.invoice_date == date(2025, 4, 10)
        assert result.invoice_data.currency == "USD"

    def test_hilton_full(self, pipeline, hilton_text):
        result = pipeline.process_text(hilton_text, "hilton.pdf")
        assert result.invoice_data.supplier == "Hilton"
        assert result.invoice_data.invoice_date == date(2025, 1, 3)
        assert result.invoice_data.currency == "AED"

    def test_du_full(self, pipeline, du_text):
        result = pipeline.process_text(du_text, "du_bill.pdf")
        assert result.invoice_data.supplier == "DU"
        assert result.invoice_data.invoice_date == date(2024, 12, 22)
        assert result.invoice_data.currency == "AED"

    def test_french_invoice_full(self, pipeline, french_text):
        result = pipeline.process_text(french_text, "amazon_fr.pdf")
        assert result.invoice_data.supplier == "Amazon"
        assert result.invoice_data.invoice_date == date(2024, 3, 15)
        assert result.invoice_data.currency == "EUR"
        assert float(result.invoice_data.amount) == pytest.approx(263.97, abs=0.01)

    def test_webkul_full(self, pipeline, webkul_text):
        result = pipeline.process_text(webkul_text, "webkul.pdf")
        assert result.invoice_data.supplier == "Webkul_Software_Pvt_Ltd"
        assert result.invoice_data.currency == "USD"


class TestPipelineConfidence:
    """Test confidence scoring."""

    def test_full_extraction_high_confidence(self, pipeline, aws_text):
        result = pipeline.process_text(aws_text)
        assert result.invoice_data.confidence >= 0.9

    def test_empty_text_low_confidence(self, pipeline):
        result = pipeline.process_text("Nothing useful here", "test.pdf")
        assert result.invoice_data.confidence < 0.5

    def test_partial_extraction(self, pipeline):
        text = "Invoice Date: 15/02/2025\nTotal: $100.00"
        result = pipeline.process_text(text)
        # Has date and amount but no supplier or invoice number
        assert 0.3 <= result.invoice_data.confidence <= 0.7


class TestPipelineFilenameFormat:
    """Test generated filename format."""

    def test_standard_format(self, pipeline, aws_text):
        result = pipeline.process_text(aws_text, "original.pdf")
        # Format: Supplier_#InvoiceNum_DD-MM-YYYY_AmountCurrency_Q-YYYY.pdf
        parts = result.new_filename.replace('.pdf', '').split('_')
        assert len(parts) >= 4
        assert parts[0] == "AWS"

    def test_accounting_prefix_preserved(self, pipeline, etisalat_text):
        result = pipeline.process_text(etisalat_text, "PUR 25-0024_old.pdf")
        assert result.new_filename.startswith("PUR 25-0024_")

    def test_no_vat_quarter(self, pipeline, aws_text):
        result = pipeline.process_text(aws_text, "test.pdf", include_vat_quarter=False)
        assert "Q1" not in result.new_filename
        assert "Q2" not in result.new_filename
        assert "Q3" not in result.new_filename
        assert "Q4" not in result.new_filename
