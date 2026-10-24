from decimal import Decimal

import pytest

from spreader import formulas

V = {"a": Decimal(10), "b": Decimal(4), "z": Decimal(0)}


def get(n: str) -> Decimal | None:
    return V.get(n)


def test_arithmetic_is_decimal_exact() -> None:
    assert formulas.evaluate("a - b", get)[0] == Decimal(6)
    assert formulas.evaluate("a / b", get)[0] == Decimal("2.5")
    assert formulas.evaluate("0.1 + 0.2", get)[0] == Decimal("0.3")  # not 0.30000000000000004


def test_missing_input_is_reported_not_zeroed() -> None:
    value, missing, _ = formulas.evaluate("a - missing_line", get)
    assert value is None and missing == ["missing_line"]


def test_or_zero_and_sum_present() -> None:
    assert formulas.evaluate("a + missing_or_zero", get)[0] == Decimal(10)
    assert formulas.evaluate("sum_present(a, missing, b)", get)[0] == Decimal(14)
    assert formulas.evaluate("sum_present(missing, other)", get)[0] is None
    assert formulas.evaluate("coalesce(missing, b)", get)[0] == Decimal(4)


def test_division_by_zero_is_not_computable() -> None:
    value, _, why = formulas.evaluate("a / z", get)
    assert value is None and why == "division by zero"


def test_prior_and_days() -> None:
    value, _, _ = formulas.evaluate("a / prior(a) - 1", get, get_prior=lambda n: Decimal(8), days=Decimal(365))
    assert value == Decimal("0.25")
    assert formulas.evaluate("days()", get, days=Decimal("91.25"))[0] == Decimal("91.25")


@pytest.mark.parametrize("bad", ["__import__('os')", "a.b", "a if b else z", "[a]", "open('x')", "a ** b", "lambda: 1"])
def test_unsafe_formulas_are_rejected(bad: str) -> None:
    with pytest.raises(formulas.FormulaError):
        formulas.parse(bad)


def test_names_strip_or_zero() -> None:
    assert formulas.names("a + b_or_zero - prior(c)") == {"a", "b", "c"}
