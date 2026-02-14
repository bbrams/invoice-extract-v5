"""
Supplier name extraction using JSON templates + heuristic fallback.
No hardcoded supplier patterns in code.
"""

import json
import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Resolve config path relative to this file
_CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'config')


class SupplierExtractor:
    """
    Two-phase supplier extraction:
    1. Template matching from suppliers.json (known suppliers)
    2. Heuristic fallback (unknown suppliers)
    """

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(_CONFIG_DIR, 'suppliers.json')
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)
        self.templates = config.get("suppliers", [])
        self.own_companies = [c.upper() for c in config.get("own_companies", [])]

    def extract(self, text: str) -> Tuple[str, Optional[dict]]:
        """
        Returns (display_name, template_dict) if known supplier,
        or (heuristic_name, None) if unknown.
        """
        template = self._match_template(text)
        if template:
            return template["display_name"], template

        name = self._heuristic_extract(text)
        return name, None

    def _match_template(self, text: str) -> Optional[dict]:
        """Match text against detection patterns from all templates."""
        text_upper = text.upper()
        for template in self.templates:
            for pattern in template.get("detection_patterns", []):
                if pattern.upper() in text_upper:
                    return template
        return None

    def _heuristic_extract(self, text: str) -> str:
        """
        Fallback for unknown suppliers.
        Looks at first 20 lines for company-like names.
        Excludes own company names (Bill To sections).
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        company_suffixes = re.compile(
            r'\b(Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?|Group|'
            r'PJSC|GmbH|S\.?A\.?R\.?L\.?|Pvt\.?|PLC|SAS|SARL|SA|Srl|B\.?V\.?)\b',
            re.IGNORECASE
        )

        skip_words = re.compile(
            r'^\s*(Invoice|Receipt|Bill\b|Statement|Tax\s|Date|Total|'
            r'Amount|Page\s|Tel\b|Phone|Email|Address|Street|'
            r'P\.?O\.?\s*Box|www\.|http|Subtotal|Due\s|Payment|'
            r'Description|Quantity|Unit|Price|Item|Service|'
            r'IBAN|SWIFT|Account|Bank|Reference)',
            re.IGNORECASE
        )

        candidates = []
        for i, line in enumerate(lines[:20]):
            # Length filters
            if len(line) < 3 or len(line) > 80:
                continue

            # Skip known non-supplier lines
            if skip_words.search(line):
                continue

            # Skip own company names (Bill To section)
            if any(own in line.upper() for own in self.own_companies):
                continue

            # Skip lines that are mostly numbers/symbols
            alpha_count = sum(c.isalpha() or c == ' ' for c in line)
            if alpha_count < len(line) * 0.5:
                continue

            # Score candidates
            score = 0
            if company_suffixes.search(line):
                score += 15
            if i < 5:
                score += (5 - i)
            if 5 <= len(line) <= 50:
                score += 5
            if line[0].isupper():
                score += 3

            candidates.append((score, line))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0][1]
            # Clean for filename: replace spaces with underscores
            return re.sub(r'\s+', '_', best.strip())

        return "Unknown"
