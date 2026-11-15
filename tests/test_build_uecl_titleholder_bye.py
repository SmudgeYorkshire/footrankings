"""
Tests for build_european_2027_28_predictions.py's "Conference League
Titleholder bye" cascade (_build_uecl_titleholder_bye) -- the dynamic
Europa League side only (the fixed, cross-competition Moldova promotion
is a static dict in access_list_permutations_2027_28.py, not computed
here). get_coeff_2027 is monkeypatched so these tests exercise only the
SELECTION logic, with no live API/network dependency.
"""

import pandas as pd
import pytest

import build_european_2027_28_predictions as b


def _entry(country, league, code, label):
    return {"country": country, "league": league, "code": code, "path": "Qualifying",
            "label": label, "route": "League champion" if code == "CH" else f"League {code}"}


def _synthetic_access_list():
    """Turkey has entries at BOTH EL-Q2 (N3) and EL-PO (CW) -- proving
    the comparison spans all 4 rounds, not just "whoever's in PO".
    Slovakia sits at EL-Q1 (CW) alongside a 2nd, weaker EL-Q1 country
    (Bulgaria) to prove the single-club (not pair) backfill excludes the
    weaker one."""
    return {
        "Europa League": [
            _entry("Turkey", "Turkish Super Lig", "N3", "EL-Q2"),
            _entry("Turkey", "Turkish Super Lig", "CW", "EL-PO"),
            _entry("Slovakia", "Slovak First Football League", "CW", "EL-Q1"),
            _entry("Bulgaria", "Bulgarian First League", "CW", "EL-Q1"),
        ],
    }


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "apply_permutations", lambda active=None: _synthetic_access_list())
    monkeypatch.setattr(b, "_UEL_FIXED_PROMOTIONS", {})
    coeffs = {
        "Fenerbahce": 70.0, "Galatasaray": 50.0,
        "Slovan Bratislava": 30.0, "Levski Sofia": 10.0,
    }
    monkeypatch.setattr(b, "get_coeff_2027", lambda club, country: coeffs.get(club, 1.0))
    out_path = tmp_path / "uecl_titleholder_bye.csv"
    monkeypatch.setattr(b, "UECL_TITLEHOLDER_BYE_OUT", str(out_path))
    return out_path


def _rank(team: str, pos: int) -> dict:
    return {"strTeam": team, "intRank": pos}


def _standings_by_league():
    return {
        "Turkish Super Lig": [_rank("x", 1), _rank("y", 2), _rank("Fenerbahce", 3)],
    }


def _cup_winner_by_league():
    # Slovakia/Bulgaria/Turkey's EL-PO entries are all CW-coded (cup
    # winner), resolved from the predicted-cup-winner dict, not a league
    # standings position (confirmed as a real bug while building this --
    # _POSITION_OF_CODE has no rank for "CW").
    return {
        "Turkish Super Lig": "Galatasaray",  # Turkey's OWN EL-PO entry's winner -- weaker than Fenerbahce here
        "Slovak First Football League": "Slovan Bratislava",
        "Bulgarian First League": "Levski Sofia",
    }


def test_highest_overall_promotes_to_league_phase_even_from_lower_round(patched):
    movements = b._build_uecl_titleholder_bye(
        _standings_by_league(), [], [], _cup_winner_by_league(),
    )
    df = pd.read_csv(patched)
    top_move = df[df["old_label"] == "EL-Q2"].iloc[0]
    assert top_move["country"] == "Turkey"
    assert top_move["club"] == "Fenerbahce"
    assert top_move["new_label"] == "EL-LS"
    # Turkey's OWN higher-round EL-PO entry must NOT also be touched.
    assert "EL-PO" not in set(df["old_label"])
    assert len(movements) == len(df)


def test_single_club_backfills_one_round_below_not_a_pair(patched):
    b._build_uecl_titleholder_bye(_standings_by_league(), [], [], _cup_winner_by_league())
    df = pd.read_csv(patched)
    backfill = df[df["old_label"] == "EL-Q1"]
    assert len(backfill) == 1
    assert backfill.iloc[0]["country"] == "Slovakia"
    assert backfill.iloc[0]["club"] == "Slovan Bratislava"
    assert backfill.iloc[0]["new_label"] == "EL-Q2"
    # Bulgaria (weaker EL-Q1 coefficient) stays put.
    assert "Bulgaria" not in set(df["country"])


def test_cw_coded_entries_resolve_via_predicted_cup_winner_not_league_position(patched):
    # Regression for the real bug found while building this: CW-coded
    # entries (the majority of Europa League's own fresh entries) have
    # no _POSITION_OF_CODE rank and used to be silently skipped entirely.
    movements = b._build_uecl_titleholder_bye(
        _standings_by_league(), [], [], _cup_winner_by_league(),
    )
    assert any(m["club"] == "Slovan Bratislava" for m in movements)


def test_ucl_and_uel_bye_movements_applied_before_this_cascade_runs(patched):
    # Simulate uel_titleholder_bye having already promoted Slovakia's own
    # EL-Q1 entry up to EL-Q2 earlier this same run (a DIFFERENT club
    # claiming that slot) -- this cascade's own EL-Q1 comparison must see
    # that, not the stale pre-promotion state.
    uel_movements = [{"country": "Slovakia", "code": "CW", "old_label": "EL-Q1", "new_label": "EL-Q2"}]
    movements = b._build_uecl_titleholder_bye(
        _standings_by_league(), [], uel_movements, _cup_winner_by_league(),
    )
    # Slovakia is no longer in EL-Q1 at all (it's EL-Q2 now), so the
    # backfill pool is just Bulgaria.
    assert any(m["country"] == "Bulgaria" and m["old_label"] == "EL-Q1" for m in movements)


def test_missing_cup_winner_for_a_country_is_skipped_not_fatal(patched):
    cup_winners = _cup_winner_by_league()
    del cup_winners["Bulgarian First League"]
    movements = b._build_uecl_titleholder_bye(_standings_by_league(), [], [], cup_winners)
    assert all(m["country"] != "Bulgaria" for m in movements)


def test_empty_pool_returns_no_movements(patched):
    movements = b._build_uecl_titleholder_bye({}, [], [], {})
    assert movements == []
