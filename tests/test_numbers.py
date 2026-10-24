from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spreader.numbers import clean_label, parse_amount


@pytest.mark.parametrize(
    "text, value, negative, dash",
    [
        ("1,234", Decimal("1234"), False, False),
        ("$ 1,234", Decimal("1234"), False, False),
        ("(1,234)", Decimal("-1234"), True, False),
        ("$ (1,234)", Decimal("-1234"), True, False),
        ("($1,234)", Decimal("-1234"), True, False),
        ("-1,234", Decimal("-1234"), True, False),
        ("−1,234", Decimal("-1234"), True, False),  # a real minus sign
        ("7.49", Decimal("7.49"), False, False),
        ("(0.05)", Decimal("-0.05"), True, False),
        ("—", Decimal("0"), False, True),  # em dash: nothing to report
        ("$ —", Decimal("0"), False, True),
        ("1,234 (a)", Decimal("1234"), False, False),  # footnote letter after the number
        ("12.5%", Decimal("12.5"), False, False),
    ],
)
def test_parse_amount(text: str, value: Decimal, negative: bool, dash: bool) -> None:
    amount, why = parse_amount(text)
    assert why is None
    assert amount is not None
    assert amount.displayed == value
    assert amount.negative_display is negative
    assert amount.dash is dash


@pytest.mark.parametrize("text", ["1.234.567", "(1.234.567)", "1.234,56"])
def test_european_grouping_is_refused_not_misread(text: str) -> None:
    amount, why = parse_amount(text)
    assert amount is None
    assert why and "European" in why


@pytest.mark.parametrize("text", ["(1,234", "Note 5", "n/a", "abc"])
def test_not_a_number(text: str) -> None:
    amount, why = parse_amount(text)
    assert amount is None
    assert why


def test_blank_is_not_an_error() -> None:
    assert parse_amount("   ") == (None, None)


@given(st.integers(min_value=-10**12, max_value=10**12))
def test_round_trip_of_formatted_integers(n: int) -> None:
    text = f"({abs(n):,})" if n < 0 else f"{n:,}"
    amount, _ = parse_amount(text)
    assert amount is not None and amount.displayed == n


def test_clean_label() -> None:
    assert clean_label("Selling, general and administrative (1)") == "selling general and administrative"
    assert clean_label("Proceeds from/(Repayments of) commercial paper, net") == "proceeds from repayments of commercial paper net"
    assert clean_label("Total shareholders’ equity") == "total shareholders equity"
    assert clean_label("Net sales:") == "net sales"
