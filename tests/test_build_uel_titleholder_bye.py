"""
Tests for build_european_2027_28_predictions.py's "Europa League
Titleholder bye" cascade (_build_uel_titleholder_bye) -- the dynamic
Champions League side only (the 4 fixed Europa League promotions are a
static dict in access_list_permutations_2027_28.py, not computed here).
get_coeff_2027 is monkeypatched so these tests exercise only the
SELECTION logic, with no live API/network dependency.
"""

import pandas as pd
import pytest

import build_european_2027_28_predictions as b


def _entry(country, league, code, label, path):
    return {"country": country, "league": league, "code": code, "path": path,
            "label": label, "route": "League champion" if code == "CH" else f"League {code}"}


def _synthetic_access_list():
    """1 Champions Path country (Norway, PO -- the SAME real-world pool
    ucl_titleholder_bye would also rank, to prove it's excluded via
    claimed_countries) + League Path's own 2 rungs: 2 countries at
    CL-Q3nc (Portugal N3, France N4) and 3 at CL-Q2nc (Czech N2, Denmark
    N2, Norway N2 -- a 3rd left behind to prove top-2-only backfill)."""
    return {
        "Champions League": [
            _entry("Norway", "Norwegian Eliteserien", "CH", "CL-PO", "Champions Path"),
            _entry("Portugal", "Portuguese Primeira Liga", "N3", "CL-Q3nc", "League Path"),
            _entry("France", "French Ligue 1", "N4", "CL-Q3nc", "League Path"),
            _entry("Czech Rep.", "Czech First League", "N2", "CL-Q2nc", "League Path"),
            _entry("Denmark", "Danish Superliga", "N2", "CL-Q2nc", "League Path"),
            _entry("Norway", "Norwegian 2nd", "N2", "CL-Q2nc", "League Path"),
        ],
    }


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "apply_permutations", lambda active=None: _synthetic_access_list())
    coeffs = {
        "Bodo/Glimt": 61.5,  # Champions Path, Norway's CH -- would win if not excluded
        "Sporting CP": 70.0, "Olympique Lyonnais": 20.0,
        "Sparta Praha": 25.0, "FC Copenhagen": 22.0, "Norway Reserves": 5.0,
    }
    monkeypatch.setattr(b, "get_coeff_2027", lambda club, country: coeffs.get(club, 1.0))
    out_path = tmp_path / "uel_titleholder_bye.csv"
    monkeypatch.setattr(b, "UEL_TITLEHOLDER_BYE_OUT", str(out_path))
    return out_path


def _rank(team: str, pos: int) -> dict:
    return {"strTeam": team, "intRank": pos}


def _standings_by_league():
    return {
        "Norwegian Eliteserien": [_rank("Bodo/Glimt", 1)],
        "Portuguese Primeira Liga": [_rank("x", 1), _rank("y", 2), _rank("Sporting CP", 3)],
        "French Ligue 1": [_rank("a", 1), _rank("b", 2), _rank("c", 3), _rank("Olympique Lyonnais", 4)],
        "Czech First League": [_rank("x", 1), _rank("Sparta Praha", 2)],
        "Danish Superliga": [_rank("x", 1), _rank("FC Copenhagen", 2)],
        "Norwegian 2nd": [_rank("x", 1), _rank("Norway Reserves", 2)],
    }


def test_highest_overall_is_league_path_qr3_promotes_to_league_phase(patched):
    movements = b._build_uel_titleholder_bye(_standings_by_league(), claimed_countries=set())
    df = pd.read_csv(patched)
    top_move = df[df["old_label"] == "CL-Q3nc"].iloc[0]
    assert top_move["country"] == "Portugal"
    assert top_move["club"] == "Sporting CP"
    assert top_move["new_label"] == "CL-LS"
    assert "France" not in set(df["country"])
    assert len(movements) == len(df)


def test_top_two_remaining_qr2_clubs_backfill_qr3(patched):
    b._build_uel_titleholder_bye(_standings_by_league(), claimed_countries=set())
    df = pd.read_csv(patched)
    backfill = df[df["old_label"] == "CL-Q2nc"]
    assert set(backfill["country"]) == {"Czech Rep.", "Denmark"}
    assert (backfill["new_label"] == "CL-Q3nc").all()
    # Norway's weaker 2nd-tier club (lowest QR2 coefficient) stays put.
    assert "Norway" not in set(df["country"])


def test_champions_path_club_excluded_even_if_already_claimed_elsewhere(patched):
    # Norway's CH (Bodo/Glimt, coeff 61.5) would outrank everyone here if
    # included -- claimed_countries simulates ucl_titleholder_bye having
    # already promoted it this same run, so it must never appear here.
    movements = b._build_uel_titleholder_bye(_standings_by_league(), claimed_countries={"Norway"})
    assert all(m["country"] != "Norway" or m["old_label"] != "CL-PO" for m in movements)
    df = pd.read_csv(patched)
    assert "CL-PO" not in set(df["old_label"])


def test_champions_path_still_overall_highest_is_skipped_not_misapplied(monkeypatch, patched):
    # Norway's CH is NOT excluded this time and has the highest coefficient
    # of the whole pool -- since it's a Champions Path club, this
    # permutation must do nothing (that cascade belongs to
    # ucl_titleholder_bye only), not invent an untested promotion.
    coeffs = {"Bodo/Glimt": 999.0, "Sporting CP": 70.0}
    monkeypatch.setattr(b, "get_coeff_2027", lambda club, country: coeffs.get(club, 1.0))
    movements = b._build_uel_titleholder_bye(_standings_by_league(), claimed_countries=set())
    assert movements == []


def test_missing_standings_for_a_country_is_skipped_not_fatal(patched):
    standings = _standings_by_league()
    del standings["French Ligue 1"]
    movements = b._build_uel_titleholder_bye(standings, claimed_countries=set())
    assert all(m["country"] != "France" for m in movements)
