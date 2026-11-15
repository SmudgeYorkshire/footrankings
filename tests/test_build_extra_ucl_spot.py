"""
Tests for build_european_2027_28_predictions.py's "Extra Champions
League spot" permutation (_build_extra_ucl_spot) -- the European
Performance Spot rule's position cascade. coefficients_live.
eps_bonus_recipients is monkeypatched (it's imported locally inside the
function, so patched via monkeypatch.setattr on that module directly) so
these tests exercise only the CASCADE logic, with no live Monte Carlo
simulation dependency.
"""

import pandas as pd
import pytest

import build_european_2027_28_predictions as b
import coefficients_live


def _entry(country, league, code, label, path="Direct"):
    return {"country": country, "league": league, "code": code, "path": path,
            "label": label, "route": "League champion" if code == "CH" else f"League {code[1:]}th"}


def _synthetic_access_list():
    """England-shaped: CH/N2/N3/N4 already CL-LS, CW+N5 at EL-LS, N6 at
    CO-PO, no N7 at all -- the exact real shape confirmed against
    entrants_2027_28.py. France included unchanged, to prove it's left
    alone when it isn't a winner."""
    return {
        "Champions League": [
            _entry("England", "English Premier League", "CH", "CL-LS"),
            _entry("England", "English Premier League", "N2", "CL-LS"),
            _entry("England", "English Premier League", "N3", "CL-LS"),
            _entry("England", "English Premier League", "N4", "CL-LS"),
            _entry("France", "French Ligue 1", "CH", "CL-LS"),
        ],
        "Europa League": [
            _entry("England", "English Premier League", "CW", "EL-LS"),
            _entry("England", "English Premier League", "N5", "EL-LS"),
        ],
        "Conference League": [
            _entry("England", "English Premier League", "N6", "CO-PO", path="Qualifying"),
        ],
    }


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "apply_permutations", lambda active=None: _synthetic_access_list())
    monkeypatch.setattr(b, "_UEL_FIXED_PROMOTIONS", {})
    monkeypatch.setattr(b, "_UECL_FIXED_PROMOTIONS", {})
    monkeypatch.setattr(coefficients_live, "eps_bonus_recipients", lambda n=2: ["England"])
    out_path = tmp_path / "extra_ucl_spot.csv"
    monkeypatch.setattr(b, "EXTRA_UCL_SPOT_OUT", str(out_path))
    return out_path


def test_fifth_placed_club_promotes_to_champions_league(patched):
    movements = b._build_extra_ucl_spot([], [], [])
    df = pd.read_csv(patched)
    n5 = df[df["code"] == "N5"].iloc[0]
    assert n5["old_label"] == "EL-LS"
    assert n5["new_label"] == "CL-LS"


def test_cup_winner_slot_is_untouched_separate_route(patched):
    movements = b._build_extra_ucl_spot([], [], [])
    assert all(m["code"] != "CW" for m in movements)


def test_sixth_placed_club_shifts_up_into_vacated_europa_slot(patched):
    b._build_extra_ucl_spot([], [], [])
    df = pd.read_csv(patched)
    n6 = df[df["code"] == "N6"].iloc[0]
    assert n6["old_label"] == "CO-PO"
    assert n6["new_label"] == "EL-LS"


def test_seventh_entry_created_brand_new_at_conference_league_playoff(patched):
    b._build_extra_ucl_spot([], [], [])
    df = pd.read_csv(patched)
    n7 = df[df["code"] == "N7"].iloc[0]
    assert pd.isna(n7["old_label"]) or n7["old_label"] == ""
    assert n7["new_label"] == "CO-PO"
    assert n7["league"] == "English Premier League"


def test_non_winning_country_untouched(patched):
    movements = b._build_extra_ucl_spot([], [], [])
    assert all(m["country"] != "France" for m in movements)


def test_country_already_all_champions_league_is_skipped(monkeypatch, patched):
    monkeypatch.setattr(coefficients_live, "eps_bonus_recipients", lambda n=2: ["France"])
    movements = b._build_extra_ucl_spot([], [], [])
    assert movements == []


def test_two_winners_both_get_their_own_cascade(monkeypatch, patched):
    access_list = _synthetic_access_list()
    access_list["Champions League"].extend([
        _entry("Germany", "German Bundesliga", "CH", "CL-LS"),
        _entry("Germany", "German Bundesliga", "N2", "CL-LS"),
        _entry("Germany", "German Bundesliga", "N3", "CL-LS"),
        _entry("Germany", "German Bundesliga", "N4", "CL-LS"),
    ])
    access_list["Europa League"].extend([
        _entry("Germany", "German Bundesliga", "CW", "EL-LS"),
        _entry("Germany", "German Bundesliga", "N5", "EL-LS"),
    ])
    access_list["Conference League"].append(
        _entry("Germany", "German Bundesliga", "N6", "CO-PO", path="Qualifying")
    )
    monkeypatch.setattr(b, "apply_permutations", lambda active=None: access_list)
    monkeypatch.setattr(coefficients_live, "eps_bonus_recipients", lambda n=2: ["England", "Germany"])
    movements = b._build_extra_ucl_spot([], [], [])
    assert {m["country"] for m in movements} == {"England", "Germany"}
    assert len([m for m in movements if m["country"] == "Germany"]) == 3
