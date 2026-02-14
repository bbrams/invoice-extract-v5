"""
Supplier learning system.
When the extraction module cannot identify a supplier, this module:
- Prompts the user (CLI) or accepts input (HTTP) for supplier details
- Saves the new supplier template to suppliers.json for future auto-detection
"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'config')


def build_detection_patterns(text: str, supplier_name: str) -> list[str]:
    """
    Auto-generate detection patterns from the invoice text.
    Looks for company-like lines near the top of the document.
    """
    patterns = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    company_suffixes = re.compile(
        r'\b(Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?|Group|'
        r'PJSC|GmbH|S\.?A\.?R\.?L\.?|Pvt\.?|PLC|SAS|SARL|SA|Srl|B\.?V\.?)\b',
        re.IGNORECASE
    )

    skip_words = re.compile(
        r'^\s*(Invoice|Receipt|Bill\b|Statement|Tax\s|Date|Total|'
        r'Amount|Page\s|Tel\b|Phone|Email|Address|Street|'
        r'P\.?O\.?\s*Box|www\.|http|Subtotal|Due\s|Payment)',
        re.IGNORECASE
    )

    for line in lines[:15]:
        if len(line) < 3 or len(line) > 80:
            continue
        if skip_words.search(line):
            # Keep www. lines as they're good detection patterns
            if 'www.' in line.lower():
                url_match = re.search(r'www\.\S+', line, re.IGNORECASE)
                if url_match:
                    patterns.append(url_match.group())
            continue
        if company_suffixes.search(line):
            patterns.append(line)
        elif supplier_name.lower().replace('_', ' ') in line.lower():
            patterns.append(line)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique[:5]  # Keep at most 5 patterns


def create_supplier_template(
    supplier_name: str,
    text: str,
    default_currency: Optional[str] = None,
    detection_patterns: Optional[list[str]] = None,
) -> dict:
    """
    Build a new supplier template dict ready for suppliers.json.
    """
    template_id = re.sub(r'[^a-z0-9]+', '_', supplier_name.lower()).strip('_')
    display_name = re.sub(r'\s+', '_', supplier_name.strip())

    if not detection_patterns:
        detection_patterns = build_detection_patterns(text, supplier_name)
    # Always include the supplier name as a pattern if not already present
    if not any(supplier_name.lower() in p.lower() for p in detection_patterns):
        detection_patterns.insert(0, supplier_name)

    template = {
        "id": template_id,
        "display_name": display_name,
        "detection_patterns": detection_patterns,
    }
    if default_currency:
        template["default_currency"] = default_currency

    return template


def save_supplier_template(template: dict, config_path: Optional[str] = None) -> bool:
    """
    Persist a new supplier template to suppliers.json.
    Returns True on success.
    """
    if config_path is None:
        config_path = os.path.join(_CONFIG_DIR, 'suppliers.json')

    try:
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)

        # Check if supplier already exists
        existing_ids = {s['id'] for s in config.get('suppliers', [])}
        if template['id'] in existing_ids:
            logger.info(f"Supplier '{template['id']}' already exists, skipping.")
            return False

        config['suppliers'].append(template)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write('\n')

        logger.info(f"Saved new supplier template: {template['display_name']}")
        return True

    except Exception as e:
        logger.error(f"Failed to save supplier template: {e}")
        return False


def prompt_supplier_info(text: str) -> Optional[dict]:
    """
    Interactive CLI prompt to collect supplier info from the user.
    Shows the first 10 lines of the invoice for context.
    Returns a supplier template dict, or None if user skips.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    preview = '\n'.join(f"  {l}" for l in lines[:10])

    print("\n--- Supplier not recognized ---")
    print("Invoice preview (first 10 lines):")
    print(preview)
    print()

    supplier_name = input("Supplier name (or Enter to skip): ").strip()
    if not supplier_name:
        return None

    currency = input("Default currency (e.g. USD, EUR, AED) [optional]: ").strip().upper() or None

    # Show auto-detected patterns and let user confirm/edit
    auto_patterns = build_detection_patterns(text, supplier_name)
    if auto_patterns:
        print(f"\nAuto-detected patterns:")
        for i, p in enumerate(auto_patterns, 1):
            print(f"  {i}. {p}")
        use_auto = input("Use these patterns? (Y/n): ").strip().lower()
        if use_auto == 'n':
            custom = input("Enter detection patterns (comma-separated): ").strip()
            auto_patterns = [p.strip() for p in custom.split(',') if p.strip()]

    template = create_supplier_template(
        supplier_name=supplier_name,
        text=text,
        default_currency=currency,
        detection_patterns=auto_patterns if auto_patterns else None,
    )

    save_choice = input("Save this supplier for future invoices? (Y/n): ").strip().lower()
    if save_choice != 'n':
        saved = save_supplier_template(template)
        if saved:
            print(f"  Supplier '{supplier_name}' saved to config.")
        else:
            print(f"  Supplier '{supplier_name}' already exists in config.")

    return template
