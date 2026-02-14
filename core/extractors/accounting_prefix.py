"""
Accounting prefix extraction from filenames.
Supports PUR AA-XXXX_ and Pyt Vch AAAA-XXXX_ formats.
"""

import re
from typing import Optional


def extract_accounting_prefix(filename: str) -> Optional[str]:
    """
    Extract accounting prefix from filename if present.

    Supported patterns:
    - PUR AA-XXXX_  (Purchase orders): "PUR 25-0024_something.pdf" -> "PUR 25-0024_"
    - Pyt Vch AAAA-XXXX_ (Payment vouchers): "Pyt Vch 2023-1386_something.pdf" -> "Pyt Vch 2023-1386_"

    Returns None if filename has no accounting prefix.
    """
    # Pattern 1: PUR AA-XXXX_
    match = re.match(r'^(PUR\s+\d{2}-\d{4}_)', filename)
    if match:
        return match.group(1)

    # Pattern 2: Pyt Vch AAAA-XXXX_
    match = re.match(r'^(Pyt\s+Vch\s+\d{4}-\d{4}_)', filename)
    if match:
        return match.group(1)

    return None
