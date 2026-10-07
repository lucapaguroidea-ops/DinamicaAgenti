"""Value types: CUI check digit (invented CUIs only), money and period strings (P10)."""

import pytest

from kit.types import cui_is_valid, is_money, is_period, normalize_cui


@pytest.mark.parametrize(
    "cui", ["41526372", "908172639", "73645193", "RO41526372", " ro 73645193 "]
)
def test_invented_cuis_pass_the_check_digit(cui):
    assert cui_is_valid(cui)


@pytest.mark.parametrize(
    "cui",
    ["41526371", "908172630", "", "RO", "1", "012345678", "12345678901", "4152637X", "41 526372"],
)
def test_bad_cuis_are_refused(cui):
    assert not cui_is_valid(cui)


def test_normalize_strips_the_ro_prefix():
    assert normalize_cui(" ro41526372 ") == "41526372"


def test_money_is_a_two_decimal_string():
    assert is_money("1234.50") and is_money("-0.01")
    assert not is_money("1234.5") and not is_money("1,234.50") and not is_money("12")


def test_period_is_year_dash_month():
    assert is_period("2026-10")
    assert not is_period("2026-13") and not is_period("2026-1") and not is_period("10-2026")
