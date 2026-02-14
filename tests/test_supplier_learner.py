"""Tests for supplier learning system."""

import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.extractors.supplier_learner import (
    build_detection_patterns,
    create_supplier_template,
    save_supplier_template,
)
from core.extractors.supplier import SupplierExtractor


SAMPLE_TEXT = """Acme Corp International Ltd.
123 Business Street, Suite 400
London, UK EC1A 1BB
www.acmecorp.com

Tax Invoice
Invoice Number: INV-2025-001
Date: 15/01/2025
Amount Due: $1,500.00
"""

SAMPLE_TEXT_MINIMAL = """SomeVendor
Invoice #999
Total: $50.00
"""


class TestBuildDetectionPatterns:
    """Test auto-detection of patterns from invoice text."""

    def test_finds_company_suffix_lines(self):
        patterns = build_detection_patterns(SAMPLE_TEXT, "Acme Corp")
        assert any("Acme Corp" in p for p in patterns)

    def test_finds_url_patterns(self):
        patterns = build_detection_patterns(SAMPLE_TEXT, "Acme")
        assert any("www.acmecorp.com" in p for p in patterns)

    def test_returns_empty_for_blank_text(self):
        patterns = build_detection_patterns("", "Test")
        assert patterns == []

    def test_limits_to_5_patterns(self):
        # Text with many company-like lines
        text = "\n".join([f"Company{i} Ltd." for i in range(20)])
        patterns = build_detection_patterns(text, "Company")
        assert len(patterns) <= 5


class TestCreateSupplierTemplate:
    """Test template creation."""

    def test_basic_template(self):
        template = create_supplier_template("Acme Corp", SAMPLE_TEXT)
        assert template["id"] == "acme_corp"
        assert template["display_name"] == "Acme_Corp"
        assert len(template["detection_patterns"]) > 0

    def test_with_currency(self):
        template = create_supplier_template("Test Vendor", SAMPLE_TEXT, default_currency="EUR")
        assert template["default_currency"] == "EUR"

    def test_with_custom_patterns(self):
        template = create_supplier_template(
            "My Vendor",
            SAMPLE_TEXT,
            detection_patterns=["custom-pattern-1", "custom-pattern-2"],
        )
        assert "custom-pattern-1" in template["detection_patterns"]

    def test_supplier_name_added_to_patterns_if_missing(self):
        template = create_supplier_template(
            "Xyz Unique",
            "No matching text here\nJust some random lines\n",
        )
        assert any("Xyz Unique" in p for p in template["detection_patterns"])

    def test_id_normalized(self):
        template = create_supplier_template("My Fancy Corp! #1", "text")
        assert template["id"] == "my_fancy_corp_1"


class TestSaveSupplierTemplate:
    """Test persisting templates to suppliers.json."""

    def setup_method(self):
        """Create a temporary config file for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "suppliers.json")
        config = {
            "suppliers": [
                {"id": "existing", "display_name": "Existing", "detection_patterns": ["existing"]}
            ],
            "own_companies": []
        }
        with open(self.config_path, 'w') as f:
            json.dump(config, f)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_saves_new_supplier(self):
        template = {
            "id": "new_vendor",
            "display_name": "New_Vendor",
            "detection_patterns": ["New Vendor Corp"],
        }
        result = save_supplier_template(template, config_path=self.config_path)
        assert result is True

        with open(self.config_path) as f:
            config = json.load(f)
        ids = [s['id'] for s in config['suppliers']]
        assert "new_vendor" in ids

    def test_rejects_duplicate(self):
        template = {
            "id": "existing",
            "display_name": "Existing",
            "detection_patterns": ["existing"],
        }
        result = save_supplier_template(template, config_path=self.config_path)
        assert result is False

    def test_saved_supplier_is_detected(self):
        """End-to-end: save a template, then verify SupplierExtractor finds it."""
        template = create_supplier_template("Acme Corp", SAMPLE_TEXT, default_currency="USD")
        save_supplier_template(template, config_path=self.config_path)

        extractor = SupplierExtractor(config_path=self.config_path)
        name, tmpl = extractor.extract(SAMPLE_TEXT)
        assert "Acme" in name
        assert tmpl is not None
