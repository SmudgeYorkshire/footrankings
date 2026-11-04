"""
Tests for manual_outright_odds.devig_outright() -- the N-way (not fixed
3-way) de-vig used to compare this site's own won_competition probability
against manually-entered real bookmaker outright odds.
"""

import pytest

from manual_outright_odds import devig_outright


def test_devig_outright_removes_the_overround():
    # Two-runner market, both at even-ish money but with a clear overround
    # (1/2.0 + 1/2.0 = 1.0 exactly here, so use a book with real juice):
    out = devig_outright({"A": 1.8, "B": 1.8})
    assert out["A"] == pytest.approx(0.5)
    assert out["B"] == pytest.approx(0.5)
    assert sum(out.values()) == pytest.approx(1.0)


def test_devig_outright_sums_to_one_with_many_runners():
    odds = {"A": 3.0, "B": 5.0, "C": 10.0, "D": 15.0, "E": 50.0}
    out = devig_outright(odds)
    assert sum(out.values()) == pytest.approx(1.0)
    # Favourite (lowest odds) must have the highest fair probability.
    assert out["A"] > out["B"] > out["C"] > out["D"] > out["E"]


def test_devig_outright_skips_non_positive_or_missing_prices():
    out = devig_outright({"A": 2.0, "B": 0.0, "C": -1.0, "D": 4.0})
    assert set(out.keys()) == {"A", "D"}
    assert sum(out.values()) == pytest.approx(1.0)


def test_devig_outright_empty_input_returns_empty():
    assert devig_outright({}) == {}


def test_devig_outright_all_invalid_prices_returns_empty():
    assert devig_outright({"A": 0.0, "B": -5.0}) == {}
