"""
VAT quarter classifier based on configurable company calendars.
Supports UAE TRN calendar and extensible to other calendars.
"""

import json
import logging
import os
from datetime import date
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')


class VATQuarterClassifier:
    """Determines VAT quarter from invoice date using company-specific calendars."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(_CONFIG_DIR, 'companies.json')
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)
        self.companies = {c["id"]: c for c in config.get("companies", [])}
        self.default_company = config.get("default_company", "")

    def classify(self, invoice_date: date, company_id: Optional[str] = None) -> Optional[str]:
        """
        Returns VAT quarter string like "Q1-2025" or None.

        UAE TRN Calendar:
        Q1: Feb-Apr
        Q2: May-Jul
        Q3: Aug-Oct
        Q4: Nov-Jan (January = Q4 of PREVIOUS year)
        """
        if company_id is None:
            company_id = self.default_company

        company = self.companies.get(company_id)
        if not company or not company.get("vat_calendar"):
            return self._default_uae_trn(invoice_date)

        calendar_type = company["vat_calendar"].get("type", "")
        if calendar_type == "uae_trn":
            return self._default_uae_trn(invoice_date)

        return None

    def _default_uae_trn(self, invoice_date: date) -> str:
        """UAE TRN VAT quarter classification."""
        month = invoice_date.month
        year = invoice_date.year

        if 2 <= month <= 4:
            return f"Q1-{year}"
        elif 5 <= month <= 7:
            return f"Q2-{year}"
        elif 8 <= month <= 10:
            return f"Q3-{year}"
        else:
            # Nov, Dec = Q4 of current year; Jan = Q4 of previous year
            if month == 1:
                return f"Q4-{year - 1}"
            else:
                return f"Q4-{year}"
