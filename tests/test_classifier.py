"""Tests for VAT quarter classification."""

import pytest
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.classifier import VATQuarterClassifier


@pytest.fixture
def classifier():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'companies.json')
    return VATQuarterClassifier(config_path=config_path)


class TestUAEVATQuarters:
    """Test UAE TRN VAT quarter classification."""

    def test_q1_february(self, classifier):
        assert classifier.classify(date(2025, 2, 15)) == "Q1-2025"

    def test_q1_april(self, classifier):
        assert classifier.classify(date(2025, 4, 30)) == "Q1-2025"

    def test_q2_may(self, classifier):
        assert classifier.classify(date(2025, 5, 1)) == "Q2-2025"

    def test_q2_july(self, classifier):
        assert classifier.classify(date(2025, 7, 31)) == "Q2-2025"

    def test_q3_august(self, classifier):
        assert classifier.classify(date(2025, 8, 1)) == "Q3-2025"

    def test_q3_october(self, classifier):
        assert classifier.classify(date(2025, 10, 31)) == "Q3-2025"

    def test_q4_november(self, classifier):
        assert classifier.classify(date(2025, 11, 1)) == "Q4-2025"

    def test_q4_december(self, classifier):
        assert classifier.classify(date(2025, 12, 31)) == "Q4-2025"

    def test_q4_january_previous_year(self, classifier):
        """January belongs to Q4 of the PREVIOUS year."""
        assert classifier.classify(date(2025, 1, 15)) == "Q4-2024"
