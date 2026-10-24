"""Reading numbers and labels exactly as statements print them.

Statements write the same number many ways: "1,234", "$ 1,234", "(1,234)", "-1,234",
"−1,234" (a real minus sign), "1,234 (a)" with a footnote letter. A dash means "nothing to
report". This module turns that text into a Decimal and records how it was shown, and refuses
(returns None with a reason) instead of guessing when the text is not a number it understands.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

DASHES = {"-", "–", "—", "‒", "―", "−", "‐", "‑", "--", "——"}
NOT_AVAILABLE = {"n/a", "na", "nm", "n.m.", "*", "**", "n.a.", "nil"}
MINUS_CHARS = "-−‒–—"

# A number as printed: optional currency, optional sign or parenthesis, digits with
# thousands separators, optional decimals, optional percent, optional closing parenthesis,
# optional footnote marker like (a) or * after it.
_NUMBER = re.compile(
    r"""^
    (?P<cur0>[$€£])?\s*
    (?P<lpar>\()?\s*
    (?P<cur1>[$€£])?\s*
    (?P<sign>[-−‒–—])?\s*
    (?P<cur2>[$€£])?\s*
    (?P<digits>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)
    \s*(?P<pct>%)?
    \s*(?P<rpar>\))?
    \s*(?P<foot>\((?:[a-z]|\d{1,2}|[ivx]{1,4})\)|\*{1,3}|†|‡)?
    \s*$""",
    re.VERBOSE,
)

# European grouping (1.234.567 or 1.234,56): not supported, so it must be refused, not misread.
_EUROPEAN = re.compile(r"^\(?[$€£]?\s*-?\d{1,3}(\.\d{3})+(,\d+)?\)?$")


@dataclass(frozen=True)
class Amount:
    displayed: Decimal  # sign as shown
    negative_display: bool
    dash: bool = False
    percent: bool = False


def clean_text(text: str) -> str:
    """Collapse whitespace (including non-breaking spaces) and normalise unicode forms."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_amount(text: str) -> tuple[Amount | None, str | None]:
    """Parse one printed amount.

    Returns (amount, None) when the text is a number or a dash, (None, None) when the cell is
    blank, and (None, reason) when it has text that is not a number this parser trusts.
    """
    t = clean_text(text)
    if not t:
        return None, None
    if t in DASHES or t.strip("$ ") in DASHES:
        return Amount(Decimal(0), negative_display=False, dash=True), None
    if t.lower() in NOT_AVAILABLE:
        return None, f"'{t}' means not available"
    if _EUROPEAN.match(t) and not re.match(r"^\(?[$]?\s*\d{1,3}\.\d{3}\)?$", t):
        return None, f"'{t}' looks like European number grouping, which is not supported"
    m = _NUMBER.match(t)
    if not m:
        return None, f"'{t}' is not a number"
    lpar, rpar = bool(m.group("lpar")), bool(m.group("rpar"))
    if lpar != rpar:
        # "(1,234" with its ")" in another cell is merged before parsing; a lone one here is odd.
        return None, f"'{t}' has an unmatched parenthesis"
    try:
        value = Decimal(m.group("digits").replace(",", ""))
    except InvalidOperation:  # pragma: no cover - the regex only admits digits
        return None, f"'{t}' is not a number"
    negative = lpar or bool(m.group("sign"))
    if negative:
        value = -value
    return Amount(value, negative_display=negative, percent=bool(m.group("pct"))), None


def is_amount_like(text: str) -> bool:
    """True when the text would parse as a number or a dash (used to tell labels from values)."""
    amount, _ = parse_amount(text)
    return amount is not None


_FOOTNOTE_TAIL = re.compile(r"(\s*(\((?:[a-z]|\d{1,2}|[ivx]{1,4})\)|\*{1,3}|†|‡|\[\d+\]))+\s*$")
_PUNCT = re.compile(r"[^a-z0-9% ]+")


def clean_label(label: str) -> str:
    """The comparable form of a row label: lower case, no footnote markers, no punctuation.

    "Selling, general and administrative (1)" -> "selling general and administrative"
    "Cash and cash equivalents†" -> "cash and cash equivalents"
    """
    t = clean_text(label).lower()
    t = t.replace("’", "'").replace("&", " and ")
    t = _FOOTNOTE_TAIL.sub("", t)
    t = t.replace("'", "")
    t = _PUNCT.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip(":").strip()
