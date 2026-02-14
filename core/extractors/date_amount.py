"""
Date and Amount/Currency extraction using dateparser and price-parser.
Replaces 80+ fragile regex patterns from V3 with battle-tested libraries.
"""

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

import dateparser
from price_parser import Price

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# DATE EXTRACTION
# ─────────────────────────────────────────────────────────

# Priority contexts for invoice date (most specific first)
DATE_CONTEXTS = [
    r'Invoice\s*Date\s*:?\s*',
    r'Bill\s*(?:issue\s*)?[Dd]ate\s*:?\s*',
    r'Date\s*of\s*issue\s*:?\s*',
    r'DATE\s*OF\s*ISSUE\s*:?\s*',
    r'Tax\s*Invoice\s*(?:Issue\s*)?Date\s*:?\s*',
    r'INVOICE\s*ISSUED\s*:?\s*',
    r'Facture\s*[Dd]ate\s*:?\s*',
    r'Date\s*(?:de\s*)?(?:la\s*)?facture\s*:?\s*',
    r'Date\s*:?\s*',
]

# Contexts to AVOID (would extract the wrong date)
NEGATIVE_CONTEXTS = [
    r'Due\s*Date',
    r'Payment\s*Date',
    r'Delivery\s*Date',
    r'Expiry\s*Date',
    r'Ship\s*Date',
]

# dateparser settings for consistent DMY parsing
DATEPARSER_SETTINGS = {
    'DATE_ORDER': 'DMY',
    'PREFER_DAY_OF_MONTH': 'first',
    'STRICT_PARSING': False,
    'RETURN_AS_TIMEZONE_AWARE': False,
}

DATEPARSER_LANGUAGES = ['en', 'fr']


def extract_date(text: str, supplier_template: Optional[dict] = None) -> Optional[date]:
    """
    Extract invoice date from text.
    Phase 1: Contextual search near date labels
    Phase 2: dateparser.search on first 2000 chars
    """
    # Build context list (supplier-specific first if available)
    contexts = list(DATE_CONTEXTS)
    if supplier_template and supplier_template.get("date_context"):
        custom = [rf'{c}\s*:?\s*' for c in supplier_template["date_context"]]
        contexts = custom + contexts

    # Phase 1: Search near date labels
    for context_pattern in contexts:
        pattern = context_pattern + r'(.+?)(?:\n|$)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_text = match.group(1).strip()[:50]
            # Clean ordinals before parsing
            date_text = _clean_ordinals(date_text)
            parsed = _parse_date_text(date_text)
            if parsed and _is_reasonable_date(parsed):
                return parsed.date()

    # Phase 2: Search for dates in first 2000 chars
    search_text = text[:2000]
    try:
        results = dateparser.search.search_dates(
            search_text,
            settings=DATEPARSER_SETTINGS,
            languages=DATEPARSER_LANGUAGES,
        )
    except Exception:
        results = None

    if results:
        for label, dt in results:
            if not _is_reasonable_date(dt):
                continue
            # Check this date is NOT in a negative context
            idx = search_text.find(label)
            if idx >= 0:
                preceding = search_text[max(0, idx - 40):idx]
                if any(re.search(neg, preceding, re.IGNORECASE) for neg in NEGATIVE_CONTEXTS):
                    continue
            return dt.date()

    return None


def _parse_date_text(text: str) -> Optional[datetime]:
    """
    Parse a date string, handling ISO format (YYYY-MM-DD) which dateparser
    fails on with DMY settings, and falling back to dateparser for everything else.
    """
    # Try ISO format first (YYYY-MM-DD or YYYY/MM/DD)
    iso_match = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', text.strip())
    if iso_match:
        try:
            return datetime(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            )
        except ValueError:
            pass

    # Try dateparser with DMY settings
    parsed = dateparser.parse(
        text,
        settings=DATEPARSER_SETTINGS,
        languages=DATEPARSER_LANGUAGES,
    )
    if parsed:
        return parsed

    # Try without DATE_ORDER restriction for unusual formats
    return dateparser.parse(text, languages=DATEPARSER_LANGUAGES)


def _clean_ordinals(text: str) -> str:
    """Remove ordinal suffixes: 22nd -> 22, 1st -> 1, etc."""
    return re.sub(r'(\d+)(?:st|nd|rd|th)\b', r'\1', text)


def _is_reasonable_date(dt: datetime) -> bool:
    """Check that date is within a realistic range for invoices."""
    now = datetime.now()
    return datetime(2015, 1, 1) <= dt <= datetime(now.year + 2, 12, 31)


# ─────────────────────────────────────────────────────────
# AMOUNT + CURRENCY EXTRACTION
# ─────────────────────────────────────────────────────────

# Priority contexts for total amount (most specific first)
AMOUNT_CONTEXTS = [
    r'Total\s*Amount\s*Due',
    r'Amount\s*Due',
    r'Grand\s*[Tt]otal',
    r'TOTAL\s*AMOUNT\s*(?:DUE|Payable)',
    r'Total\s*Payable',
    r'BALANCE',
    r'Total\s*(?:incl|inc|with).*?(?:VAT|Tax)',
    r'Total\s*(?:TTC|[àa]\s*payer)',
    r'Total\s*Contribution',
    r'TOTAL\s*PREMIUM',
    r'Montant\s*total',
    r'Total',
    r'Subtotal',
]

# Map currency symbols to ISO codes
SYMBOL_TO_CODE = {
    '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY',
    '₹': 'INR', '﷼': 'SAR', 'US$': 'USD',
}


def extract_amount_and_currency(
    text: str,
    supplier_template: Optional[dict] = None,
) -> Tuple[Optional[Decimal], Optional[str]]:
    """
    Extract the total amount and currency from invoice text.
    Phase 1: Supplier-specific patterns (from template)
    Phase 2: Contextual search near "Total" labels
    Phase 3: Fallback - largest currency-tagged amount
    """
    # Phase 1: Supplier-specific patterns
    if supplier_template and supplier_template.get("amount_patterns"):
        sorted_patterns = sorted(
            supplier_template["amount_patterns"],
            key=lambda p: p.get("priority", 99)
        )
        for pat in sorted_patterns:
            match = re.search(pat["pattern"], text, re.IGNORECASE | re.DOTALL)
            if match:
                raw = _clean_ocr_amount(match.group(1).strip())
                amount = _parse_amount(raw)
                if amount and amount > 0:
                    currency = supplier_template.get("default_currency") or _detect_currency(text)
                    return amount, currency

    # Phase 2: Contextual search near total labels
    for context in AMOUNT_CONTEXTS:
        pattern = context + r'[\s:]*(.+?)(?:\n|$)'
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            raw_line = match.group(1).strip()[:80]
            raw_line = _clean_ocr_amount(raw_line)
            price = Price.fromstring(raw_line)
            if price.amount and price.amount > 0:
                currency = _resolve_currency(price, text)
                return price.amount, currency

    # Phase 3: Fallback - find largest currency-tagged amount
    return _fallback_largest_amount(text)


def _clean_ocr_amount(raw: str) -> str:
    """Fix common OCR artifacts in amounts."""
    # "960 .34" -> "960.34"
    raw = re.sub(r'(\d)\s+\.(\d)', r'\1.\2', raw)
    # "960. 34" -> "960.34"
    raw = re.sub(r'(\d)\.\s+(\d)', r'\1.\2', raw)
    # "1 499.70" -> "1499.70" (space as thousands separator)
    raw = re.sub(r'(\d)\s+(\d{3})(?=[.,\s]|$)', r'\1\2', raw)
    return raw.strip()


def _parse_amount(raw: str) -> Optional[Decimal]:
    """Parse a raw amount string to Decimal using price-parser."""
    price = Price.fromstring(raw)
    if price.amount is not None:
        return price.amount
    # Manual fallback for simple numbers
    try:
        cleaned = re.sub(r'[^\d.,]', '', raw)
        # Handle European format (comma as decimal)
        if ',' in cleaned and '.' not in cleaned:
            parts = cleaned.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                cleaned = cleaned.replace(',', '.')
        elif ',' in cleaned and '.' in cleaned:
            # 1,234.56 format
            cleaned = cleaned.replace(',', '')
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _resolve_currency(price: Price, text: str) -> str:
    """Determine ISO currency code from price-parser result or text context."""
    if price.currency:
        symbol = price.currency.strip()
        if len(symbol) == 3 and symbol.isalpha():
            return symbol.upper()
        if symbol in SYMBOL_TO_CODE:
            return SYMBOL_TO_CODE[symbol]
        for key, code in SYMBOL_TO_CODE.items():
            if key in symbol:
                return code

    return _detect_currency(text)


def _detect_currency(text: str) -> str:
    """Detect currency from text context."""
    # Order matters: check specific patterns first
    patterns = [
        (r'\bAED\b|Dirham(?!.*[Mm]arocain)', 'AED'),
        (r'\bUSD\b|US\s*\$|Dollars?\b', 'USD'),
        (r'\bEUR\b|Euro[s]?\b|€', 'EUR'),
        (r'\bGBP\b|£|Pound\s*Sterling', 'GBP'),
        (r'\bINR\b|₹|Rupee', 'INR'),
        (r'\bMAD\b|Dirham\s*[Mm]arocain', 'MAD'),
        (r'\bSAR\b|﷼|Saudi\s*Riyal', 'SAR'),
        (r'\bCHF\b|Swiss\s*Franc', 'CHF'),
        (r'\$', 'USD'),  # Generic $ last
    ]
    for pattern, code in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return code
    return 'XXX'


def _fallback_largest_amount(text: str) -> Tuple[Optional[Decimal], Optional[str]]:
    """Last resort: find the largest currency-tagged amount in text."""
    amount_re = re.compile(
        r'(?:[\$€£₹]|AED|USD|EUR|INR|US\$)\s*'
        r'(\d{1,3}(?:[,.]?\d{3})*[.,]\d{2})'
        r'|'
        r'(\d{1,3}(?:[,.]?\d{3})*[.,]\d{2})'
        r'\s*(?:[\$€£₹]|AED|USD|EUR|INR)',
        re.IGNORECASE
    )
    amounts = []
    for match in amount_re.finditer(text):
        raw = match.group(0)
        raw = _clean_ocr_amount(raw)
        price = Price.fromstring(raw)
        if price.amount and price.amount > 0:
            currency = _resolve_currency(price, text)
            amounts.append((price.amount, currency))

    if amounts:
        amounts.sort(key=lambda x: x[0], reverse=True)
        return amounts[0]

    return None, None
