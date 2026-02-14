"""Tests for supplier extraction."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.extractors.supplier import SupplierExtractor


@pytest.fixture
def extractor():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'suppliers.json')
    return SupplierExtractor(config_path=config_path)


class TestSupplierTemplateMatching:
    """Test known supplier detection via JSON templates."""

    def test_etisalat_detection(self, extractor, etisalat_text):
        name, template = extractor.extract(etisalat_text)
        assert name == "Etisalat"
        assert template is not None
        assert template["id"] == "etisalat"

    def test_aws_detection(self, extractor, aws_text):
        name, template = extractor.extract(aws_text)
        assert name == "AWS"
        assert template is not None
        assert template["id"] == "aws"

    def test_zoho_detection(self, extractor, zoho_text):
        name, template = extractor.extract(zoho_text)
        assert name == "ZOHO"
        assert template is not None

    def test_cursor_detection(self, extractor, cursor_text):
        name, template = extractor.extract(cursor_text)
        assert name == "Cursor"
        assert template is not None

    def test_hilton_detection(self, extractor, hilton_text):
        name, template = extractor.extract(hilton_text)
        assert name == "Hilton"
        assert template is not None

    def test_du_detection(self, extractor, du_text):
        name, template = extractor.extract(du_text)
        assert name == "DU"
        assert template is not None

    def test_webkul_detection(self, extractor, webkul_text):
        name, template = extractor.extract(webkul_text)
        assert name == "Webkul_Software_Pvt_Ltd"
        assert template is not None


class TestSupplierHeuristic:
    """Test heuristic fallback for unknown suppliers."""

    def test_unknown_supplier_extracts_name(self, extractor):
        text = """Acme Corp International Ltd.
123 Business Street
London, UK

Invoice #12345
Date: 15/01/2025
Total: $500.00
"""
        name, template = extractor.extract(text)
        assert template is None  # Not a known supplier
        assert "Unknown" not in name
        assert "Acme" in name

    def test_skips_own_company(self, extractor):
        text = """BRAMS Technologies LLC
Dubai, UAE

Some Vendor Corp
Invoice #12345
"""
        name, template = extractor.extract(text)
        # Should NOT return BRAMS Technologies LLC
        assert "BRAMS" not in name.upper() or "SA" in name.upper()

    def test_returns_unknown_for_empty(self, extractor):
        name, template = extractor.extract("")
        assert name == "Unknown"
        assert template is None

    def test_skips_invoice_header_words(self, extractor):
        text = """Invoice
Date: 15/01/2025
Total: $100.00
Page 1 of 1
"""
        name, template = extractor.extract(text)
        assert name == "Unknown"


class TestSupplierFrench:
    """Test French invoice supplier detection."""

    def test_amazon_france(self, extractor, french_text):
        name, template = extractor.extract(french_text)
        assert name == "Amazon"
        assert template is not None
