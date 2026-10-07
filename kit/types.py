"""Closed value types shared by the gate kit.

Money and fiscal dates are strings outside the code that computes on them (P10). A CUI is the
Romanian fiscal identification code; invented CUIs in this repository must pass its check digit.
"""

from __future__ import annotations

import re

_CUI_KEY = "753217532"
_MONEY = re.compile(r"^-?\d+\.\d{2}$")
_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def normalize_cui(value: str) -> str:
    """The CUI's digits: an optional ``RO`` prefix and surrounding spaces removed."""
    s = value.strip().upper()
    if s.startswith("RO"):
        s = s[2:].strip()
    return s


def cui_is_valid(value: str) -> bool:
    """True when ``value`` is a CUI with a correct check digit.

    The body (all digits but the last, at most nine) is padded on the left to nine digits and
    weighted by ``753217532``; the check digit is ``(sum * 10) % 11``, with 10 read as 0.
    """
    s = normalize_cui(value)
    if not s.isdigit() or not 2 <= len(s) <= 10 or s[0] == "0":
        return False
    body, check = s[:-1].rjust(9, "0"), int(s[-1])
    total = sum(int(d) * int(k) for d, k in zip(body, _CUI_KEY, strict=True))
    return (total * 10) % 11 % 10 == check


def is_money(value: str) -> bool:
    """A money string: optional minus, digits, a dot, exactly two decimals."""
    return bool(_MONEY.match(value))


def is_period(value: str) -> bool:
    """A fiscal period string ``YYYY-MM``."""
    return bool(_PERIOD.match(value))
