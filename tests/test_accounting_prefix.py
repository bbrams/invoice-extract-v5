"""Tests for accounting prefix extraction."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.extractors.accounting_prefix import extract_accounting_prefix


class TestAccountingPrefix:
    """Test accounting prefix extraction from filenames."""

    def test_pur_prefix(self):
        assert extract_accounting_prefix("PUR 25-0024_EUINAE25-107873.pdf") == "PUR 25-0024_"

    def test_pyt_vch_prefix(self):
        assert extract_accounting_prefix("Pyt Vch 2023-1386_invoice2110799769.pdf") == "Pyt Vch 2023-1386_"

    def test_no_prefix(self):
        assert extract_accounting_prefix("regular_invoice.pdf") is None

    def test_partial_match(self):
        assert extract_accounting_prefix("PURCHASE_order.pdf") is None

    def test_pur_different_numbers(self):
        assert extract_accounting_prefix("PUR 24-0001_test.pdf") == "PUR 24-0001_"
