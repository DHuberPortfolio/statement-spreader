"""Money as Decimal, read the way finance files print it, compared under an explicit tolerance.

The statement engine's number reader (spreader.numbers) is reused: it already refuses text it
does not understand instead of guessing. This module adds what transaction files need on top:
currency codes, trailing minus and CR/DR markers, and a tolerance object that says exactly how
far apart two amounts may be.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pydantic import BaseModel, model_validator

from spreader.numbers import clean_text, parse_amount

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("1e13")  # larger than any invoice or bank line; beyond it the text is not an amount
_CODES = re.compile(r"^(?:[A-Z]{3}\s+)?(.*?)(?:\s+[A-Z]{3})?$")
_TRAILING_MINUS = re.compile(r"^(.*\d)\s*-$")


def parse_money(text: object) -> tuple[Decimal | None, str | None]:
    """Read one amount. Returns (value, None), (None, None) for a blank, or (None, reason).

    Accepts what parse_amount accepts plus "USD 1,234.50", "1,234.50 EUR", "1,234.50-" and a
    trailing "CR"/"DR" (CR negative, DR positive: a source whose convention is the opposite
    says so in its configuration with amount_sign: negate).
    """
    if text is None:
        return None, None
    if isinstance(text, (int, Decimal, float)):
        v = Decimal(str(text)) if isinstance(text, float) else Decimal(text)
        return (v, None) if v.is_finite() and abs(v) < MAX_AMOUNT else (None, f"'{text}' is not a plausible amount")
    t = clean_text(str(text))
    if not t:
        return None, None
    sign = 1
    upper = t.upper()
    if upper.endswith(" CR") or upper.endswith("CR") and upper[:-2].strip()[-1:].isdigit():
        t, sign = t[:-2].strip(), -1
    elif upper.endswith(" DR") or upper.endswith("DR") and upper[:-2].strip()[-1:].isdigit():
        t = t[:-2].strip()
    m = _TRAILING_MINUS.match(t)
    if m:
        t, sign = m.group(1), -sign
    m = _CODES.match(t)
    if m:
        t = m.group(1).strip()
    amount, reason = parse_amount(t)
    if amount is None:
        return None, reason or f"'{text}' is not an amount"
    if amount.percent:
        return None, f"'{text}' is a percentage, not an amount"
    value = amount.displayed * sign
    if not value.is_finite() or abs(value) >= MAX_AMOUNT:
        return None, f"'{text}' is not a plausible amount"
    return value, None


_ISO = re.compile(r"(?:^|\s)([A-Z]{3})(?:\s|$)")
_SIGNS = {"€": "EUR", "£": "GBP", "¥": "JPY"}


def currency_in(text: object) -> str | None:
    """A currency printed inside an amount cell ("EUR 1,234.50", "1.234,50 €"), else None. "$" is ambiguous: None."""
    t = clean_text(str(text or ""))
    for sign, code in _SIGNS.items():
        if sign in t:
            return code
    m = _ISO.search(t.upper())
    return m.group(1) if m and m.group(1) not in {"CR", "DR"} else None


def to_decimal(value: object) -> Decimal:
    """Strict conversion for values that must be numbers (configuration, test fixtures)."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{value!r} is not a number") from exc


def round_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class Tolerance(BaseModel):
    """How far apart two amounts may be and still count as agreeing.

    abs   an amount in currency units (e.g. 0.01)
    pct   a share of the larger amount (e.g. 0.02 for 2%)
    combine  when both are set: "min" (the stricter one applies) or "max" (the looser one)

    Zero tolerance (the default) means exact equality to the cent.
    """

    abs: Decimal | None = None
    pct: Decimal | None = None
    combine: str = "min"

    @model_validator(mode="after")
    def _check(self) -> Tolerance:
        if self.combine not in ("min", "max"):
            raise ValueError("combine must be 'min' or 'max'")
        for name in ("abs", "pct"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise ValueError(f"{name} tolerance cannot be negative")
        if self.pct is not None and self.pct >= 1:
            raise ValueError("pct is a share (0.02 = 2%), so it must be below 1")
        return self

    def allowed(self, a: Decimal, b: Decimal, base: Decimal | None = None) -> Decimal:
        """`base` is what a percentage is a share of: by default the larger amount; a price check passes the PO price."""
        base = max(abs(a), abs(b)) if base is None else abs(base)
        parts = []
        if self.abs is not None:
            parts.append(self.abs)
        if self.pct is not None:
            parts.append(self.pct * base)
        if not parts:
            return Decimal(0)
        return min(parts) if self.combine == "min" else max(parts)

    def within(self, a: Decimal, b: Decimal, base: Decimal | None = None) -> bool:
        return abs(a - b) <= self.allowed(a, b, base)

    def describe(self) -> str:
        parts = []
        if self.abs is not None:
            parts.append(f"{self.abs}")
        if self.pct is not None:
            parts.append(f"{self.pct * 100:g}%")
        if not parts:
            return "exact to the cent"
        if len(parts) == 1:
            return f"within {parts[0]}"
        return f"within {' or '.join(parts)}, whichever is {'smaller' if self.combine == 'min' else 'larger'}"
