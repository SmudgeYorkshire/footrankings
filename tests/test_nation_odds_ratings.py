"""
Tests for nation_odds_ratings.py's persistent odds-implied rating fit and
its file-level filtering/dedup/ledger behaviour -- same pattern
tests/test_club_odds_ratings.py already uses (the fit is a pure function,
tested directly against small synthetic rosters; filesystem-backed pieces
via tmp_path/monkeypatch on the module's own path constants).
"""

import json

import pandas as pd
import pytest

import nation_odds_ratings as nor


def test_fit_persistent_neutral_market_barely_moves_ratings():
    # Equal teams, home advantage already explains most of a roughly-even
    # split -- shouldn't need much correction either way.
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.55, "away_prob": 0.45, "bookmaker_count": 10}]
    out = nor._fit_persistent(obs, current_ratings={"A": 1800.0, "B": 1800.0})
    assert set(out) == {"A", "B"}
    assert abs(out["A"] - 1800.0) < 10.0
    assert abs(out["B"] - 1800.0) < 10.0


def test_fit_persistent_market_favours_away_side_shifts_ratings_that_way():
    # Market thinks the away side is a big favourite despite equal
    # ratings and home advantage -- real signal the fit should move on.
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.15, "away_prob": 0.85, "bookmaker_count": 10}]
    out = nor._fit_persistent(obs, current_ratings={"A": 1800.0, "B": 1800.0})
    assert out["B"] > out["A"]
    assert out["B"] > 1800.0
    assert out["A"] < 1800.0


def test_fit_persistent_seeds_from_current_ratings_not_zero():
    # A already has a persisted/seeded rating well above B's -- the fit
    # must start from that value, not silently collapse toward 0 (a real
    # bug this module had: a team with no `current_ratings` entry
    # defaulted to 0.0 inside the fit, saturating _elo_expectancy
    # immediately and crashing every rating to the sanity floor).
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.55, "away_prob": 0.45, "bookmaker_count": 10}]
    out = nor._fit_persistent(obs, current_ratings={"A": 2200.0, "B": 1400.0})
    assert out["A"] > 2100.0
    assert out["B"] > 1300.0


def test_fit_persistent_low_bookmaker_count_moves_rating_less():
    base = {"home_team": "A", "away_team": "B", "home_prob": 0.15, "away_prob": 0.85}
    thin = nor._fit_persistent([{**base, "bookmaker_count": 1}], {"A": 1800.0, "B": 1800.0})
    thick = nor._fit_persistent([{**base, "bookmaker_count": 10}], {"A": 1800.0, "B": 1800.0})
    assert abs(thick["B"] - 1800.0) > abs(thin["B"] - 1800.0)


def test_fit_persistent_empty_observations_is_a_noop():
    assert nor._fit_persistent([], {"A": 1800.0}) == {}


def test_fit_persistent_respects_sanity_clamp():
    # An extreme, maximally one-sided market repeated across many epochs
    # must still land within [RATING_SANITY_MIN, RATING_SANITY_MAX], not
    # run away unbounded.
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.01, "away_prob": 0.99, "bookmaker_count": 10}]
    out = nor._fit_persistent(obs, current_ratings={"A": 1800.0, "B": 1800.0}, epochs=200)
    assert nor.RATING_SANITY_MIN <= out["A"] <= nor.RATING_SANITY_MAX
    assert nor.RATING_SANITY_MIN <= out["B"] <= nor.RATING_SANITY_MAX


def test_is_youth_team():
    assert nor._is_youth_team("Scotland U21")
    assert nor._is_youth_team("USA U19")
    assert not nor._is_youth_team("Scotland")
    assert not nor._is_youth_team("Uruguay")  # starts with "U" but isn't an age-group suffix


def _roster() -> pd.DataFrame:
    return pd.DataFrame({
        "team": ["Turkey", "North Macedonia", "Taiwan", "United States"],
        "alias": ["", "", "", ""],
        "elo_rating": [1700.0, 1400.0, 1300.0, 1800.0],
        "elo_rank": [20, 60, 90, 25],
    })


def test_resolve_team_exact_match():
    assert nor._resolve_team("Turkey", _roster()) == "Turkey"


def test_resolve_team_via_odds_name_alias():
    # "Türkiye"/"FYR Macedonia"/"Chinese Taipei"/"USA" are real odds-feed
    # spellings confirmed live 2026-11-15, none of which the normalized/
    # fuzzy tiers alone bridge to eloratings.net's own name.
    assert nor._resolve_team("Türkiye", _roster()) == "Turkey"
    assert nor._resolve_team("FYR Macedonia", _roster()) == "North Macedonia"
    assert nor._resolve_team("Chinese Taipei", _roster()) == "Taiwan"
    assert nor._resolve_team("USA", _roster()) == "United States"


def test_resolve_team_unresolvable_returns_none():
    assert nor._resolve_team("Basque Country", _roster()) is None


@pytest.fixture()
def daily_odds_dir(tmp_path, monkeypatch):
    d = tmp_path / "daily_odds"
    d.mkdir()
    monkeypatch.setattr(nor, "DAILY_ODDS_DIR", d)
    return d


def _write_day(daily_odds_dir, fname: str, obs: list[dict]) -> None:
    (daily_odds_dir / fname).write_text(json.dumps(obs), encoding="utf-8")


def _obs(league: str, home: str, away: str, **overrides) -> dict:
    base = {
        "source": "api_football", "league": league, "home_team": home, "away_team": away,
        "commence_time": "2026-10-10T20:00:00+00:00", "bookmaker_count": 5,
        "home_prob": 0.5, "draw_prob": 0.25, "away_prob": 0.25,
    }
    return {**base, **overrides}


def test_load_all_international_observations_includes_allowlisted_competition(daily_odds_dir):
    _write_day(daily_odds_dir, "2026-10-08.json", [_obs("UEFA Nations League", "A", "B")])
    out = nor._load_all_international_observations()
    assert len(out) == 1
    assert out[0]["home_team"] == "A"


def test_load_all_international_observations_excludes_club_competition_with_similar_name(daily_odds_dir):
    # CAF Champions League / CONMEBOL Libertadores / AFC Champions League
    # etc. are CLUB competitions that happen to share a confederation-
    # style name with a genuine national-team one -- must never leak in.
    _write_day(daily_odds_dir, "2026-10-08.json", [
        _obs("CAF Champions League", "Club A", "Club B"),
        _obs("CONMEBOL Libertadores", "Club C", "Club D"),
        _obs("Friendlies Clubs", "Club E", "Club F"),
        _obs("Friendlies Women", "A Women", "B Women"),
    ])
    assert nor._load_all_international_observations() == []


def test_load_all_international_observations_excludes_youth_friendlies(daily_odds_dir):
    # Confirmed live 2026-11-15: API-Football tags youth internationals
    # under the SAME plain "Friendlies" league name as senior ones, so
    # this can't be filtered by league name alone.
    _write_day(daily_odds_dir, "2026-10-08.json", [_obs("Friendlies", "Scotland U21", "USA U21")])
    assert nor._load_all_international_observations() == []


def test_load_all_international_observations_freshest_capture_wins(daily_odds_dir):
    _write_day(daily_odds_dir, "2026-10-08.json",
               [_obs("UEFA Nations League", "A", "B", bookmaker_count=3, home_prob=0.4)])
    _write_day(daily_odds_dir, "2026-10-09.json",
               [_obs("UEFA Nations League", "A", "B", bookmaker_count=9, home_prob=0.55)])
    out = nor._load_all_international_observations()
    assert len(out) == 1
    assert out[0]["bookmaker_count"] == 9
    assert out[0]["home_prob"] == 0.55


@pytest.fixture()
def ledger_path(tmp_path, monkeypatch):
    p = tmp_path / "ledger.csv"
    monkeypatch.setattr(nor, "LEDGER_PATH", p)
    return p


def test_ledger_round_trip(ledger_path):
    assert nor._load_ledger() == set()
    key = ("UEFA Nations League", "A", "B", "2026-10-10T20:00:00+00:00")
    nor._append_ledger([key])
    assert nor._load_ledger() == {key}


def test_append_ledger_skips_keys_already_on_disk(ledger_path):
    key = ("UEFA Nations League", "A", "B", "2026-10-10T20:00:00+00:00")
    nor._append_ledger([key])
    nor._append_ledger([key])  # re-applying the same key must not duplicate the row
    with open(ledger_path, encoding="utf-8") as f:
        assert len(f.readlines()) == 2  # header + exactly one data row


@pytest.fixture()
def ratings_path(tmp_path, monkeypatch):
    p = tmp_path / "ratings.csv"
    monkeypatch.setattr(nor, "RATINGS_OUT_PATH", p)
    return p


def test_state_round_trip(ratings_path):
    assert nor._load_state() == {}
    state = {"Brazil": {"rating": 1985.5, "seed": 1982.0, "n_updates": 3, "last_updated": "2026-11-14"}}
    nor._save_state(state)
    loaded = nor._load_state()
    assert loaded["Brazil"]["rating"] == 1985.5
    assert loaded["Brazil"]["n_updates"] == 3


def test_blend_nation_rating_no_state_entry_returns_base_unchanged():
    assert nor.blend_nation_rating("Brazil", 1980.0, state={}) == 1980.0


def test_blend_nation_rating_zero_updates_returns_base_unchanged():
    state = {"Brazil": {"rating": 2000.0, "n_updates": 0}}
    assert nor.blend_nation_rating("Brazil", 1980.0, state=state) == 1980.0


def test_blend_nation_rating_full_confidence_returns_pure_odds_implied():
    state = {"Brazil": {"rating": 2000.0, "n_updates": nor.N_FULL_CONFIDENCE}}
    assert nor.blend_nation_rating("Brazil", 1980.0, state=state) == 2000.0


def test_blend_nation_rating_beyond_full_confidence_still_clamps_to_pure_odds_implied():
    state = {"Brazil": {"rating": 2000.0, "n_updates": nor.N_FULL_CONFIDENCE * 10}}
    assert nor.blend_nation_rating("Brazil", 1980.0, state=state) == 2000.0


def test_blend_nation_rating_partial_confidence_interpolates():
    state = {"Brazil": {"rating": 2000.0, "n_updates": nor.N_FULL_CONFIDENCE // 2}}
    out = nor.blend_nation_rating("Brazil", 1980.0, state=state)
    assert 1980.0 < out < 2000.0
