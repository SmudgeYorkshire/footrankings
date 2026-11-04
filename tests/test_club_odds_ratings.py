"""
Tests for club_odds_ratings.py's persistent odds-implied rating fit and
its file-level dedup/ledger behaviour. The fit itself (_fit_persistent) is
a pure function, tested directly with small synthetic rosters; the file-
scanning pieces are tested against a temp directory via monkeypatching the
module's path constants, same pattern as any other filesystem-backed unit
under test in this repo.
"""

import json

import pandas as pd
import pytest

import club_odds_ratings as cor


def _ratings_df(ratings: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({
        "team": list(ratings.keys()),
        "alias": [""] * len(ratings),
        "opta_rating": list(ratings.values()),
    })


def test_fit_persistent_neutral_market_barely_moves_ratings():
    df = _ratings_df({"A": 90.0, "B": 90.0})
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.5, "draw_prob": 0.25,
            "away_prob": 0.25, "bookmaker_count": 10}]
    # Equal teams at 90/90 with a roughly-even market (home advantage
    # already explains most of a plain 0.5/0.25/0.25 split) shouldn't need
    # much correction either way.
    out = cor._fit_persistent(df, home_advantage=1.20, resolved=obs, current_ratings={})
    assert set(out) == {"A", "B"}
    assert abs(out["A"] - 90.0) < 3.0
    assert abs(out["B"] - 90.0) < 3.0


def test_fit_persistent_market_favours_away_side_shifts_ratings_that_way():
    df = _ratings_df({"A": 90.0, "B": 90.0})
    # Market thinks the away side is a big favourite despite equal ratings
    # and home advantage -- real signal the fit should move on.
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.15, "draw_prob": 0.15,
            "away_prob": 0.70, "bookmaker_count": 10}]
    out = cor._fit_persistent(df, home_advantage=1.20, resolved=obs, current_ratings={})
    assert out["B"] > out["A"]
    assert out["B"] > 90.0
    assert out["A"] < 90.0


def test_fit_persistent_seeds_from_current_ratings_not_raw_opta():
    df = _ratings_df({"A": 90.0, "B": 90.0})
    # A already has a persisted rating well above its raw Opta row (90) --
    # the fit must start from that persisted value, not silently reset to
    # the raw baseline.
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.5, "draw_prob": 0.25,
            "away_prob": 0.25, "bookmaker_count": 10}]
    out = cor._fit_persistent(df, home_advantage=1.20, resolved=obs, current_ratings={"A": 99.0})
    assert out["A"] > 95.0  # stayed near its persisted 99, not reset to raw-Opta 90


def test_fit_persistent_low_bookmaker_count_moves_rating_less():
    df = _ratings_df({"A": 90.0, "B": 90.0})
    base = {"home_team": "A", "away_team": "B", "home_prob": 0.15, "draw_prob": 0.15, "away_prob": 0.70}
    thin = cor._fit_persistent(df, 1.20, [{**base, "bookmaker_count": 1}], {})
    thick = cor._fit_persistent(df, 1.20, [{**base, "bookmaker_count": 10}], {})
    assert abs(thick["B"] - 90.0) > abs(thin["B"] - 90.0)


def test_fit_persistent_respects_custom_epochs():
    df = _ratings_df({"A": 90.0, "B": 90.0})
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.15, "draw_prob": 0.15,
            "away_prob": 0.70, "bookmaker_count": 10}]
    # bootstrap_historical_odds() passes a smaller epochs count for speed
    # over a large historical replay -- fewer epochs should still move the
    # rating in the right direction, just less far (each epoch shrinks the
    # correction by L2_SHRINKAGE, so more epochs converges further).
    few = cor._fit_persistent(df, 1.20, obs, {}, epochs=2)
    many = cor._fit_persistent(df, 1.20, obs, {}, epochs=cor.EPOCHS)
    assert few["B"] > 90.0
    assert many["B"] > few["B"]


def test_fit_persistent_empty_observations_is_a_noop():
    df = _ratings_df({"A": 90.0, "B": 90.0})
    assert cor._fit_persistent(df, 1.20, [], {}) == {}


def test_fit_persistent_respects_sanity_clamp():
    df = _ratings_df({"A": 90.0, "B": 90.0})
    obs = [{"home_team": "A", "away_team": "B", "home_prob": 0.999, "draw_prob": 0.0005,
            "away_prob": 0.0005, "bookmaker_count": 10}]
    out = cor._fit_persistent(df, 1.20, obs, {})
    assert cor.RATING_SANITY_MIN <= out["A"] <= cor.RATING_SANITY_MAX
    assert cor.RATING_SANITY_MIN <= out["B"] <= cor.RATING_SANITY_MAX


@pytest.fixture()
def daily_odds_dir(tmp_path, monkeypatch):
    d = tmp_path / "daily_odds"
    d.mkdir()
    monkeypatch.setattr(cor, "DAILY_ODDS_DIR", d)
    return d


def _write_day(daily_odds_dir, fname: str, obs: list[dict]) -> None:
    (daily_odds_dir / fname).write_text(json.dumps(obs), encoding="utf-8")


def test_load_all_tracked_observations_freshest_capture_wins(daily_odds_dir):
    fixture = {
        "source": "api_football", "league": "Test League", "tracked": True,
        "home_team": "A", "away_team": "B", "commence_time": "2026-10-10T20:00:00+00:00",
        "bookmaker_count": 3, "home_prob": 0.4, "draw_prob": 0.3, "away_prob": 0.3,
    }
    _write_day(daily_odds_dir, "2026-10-08.json", [{**fixture, "bookmaker_count": 3, "home_prob": 0.4}])
    _write_day(daily_odds_dir, "2026-10-09.json", [{**fixture, "bookmaker_count": 9, "home_prob": 0.55}])

    out = cor._load_all_tracked_observations()
    assert len(out) == 1
    assert out[0]["bookmaker_count"] == 9
    assert out[0]["home_prob"] == 0.55


def test_load_all_tracked_observations_filters_untracked_and_non_api_football(daily_odds_dir):
    _write_day(daily_odds_dir, "2026-10-08.json", [
        {"source": "api_football", "league": "X", "tracked": False, "home_team": "A", "away_team": "B",
         "commence_time": "2026-10-10T20:00:00+00:00", "bookmaker_count": 5,
         "home_prob": 0.4, "draw_prob": 0.3, "away_prob": 0.3},
        {"source": "odds_api", "league": "X", "tracked": True, "home_team": "C", "away_team": "D",
         "commence_time": "2026-10-10T20:00:00+00:00", "bookmaker_count": 5,
         "home_prob": 0.4, "draw_prob": 0.3, "away_prob": 0.3},
    ])
    assert cor._load_all_tracked_observations() == []


@pytest.fixture()
def ledger_path(tmp_path, monkeypatch):
    p = tmp_path / "ledger.csv"
    monkeypatch.setattr(cor, "LEDGER_PATH", p)
    return p


def test_ledger_round_trip(ledger_path):
    assert cor._load_ledger() == set()
    cor._append_ledger([("League", "A", "B", "2026-10-10T20:00:00+00:00")])
    cor._append_ledger([("League", "C", "D", "2026-10-11T20:00:00+00:00")])
    loaded = cor._load_ledger()
    assert loaded == {
        ("League", "A", "B", "2026-10-10T20:00:00+00:00"),
        ("League", "C", "D", "2026-10-11T20:00:00+00:00"),
    }


@pytest.fixture()
def ratings_path(tmp_path, monkeypatch):
    p = tmp_path / "ratings.csv"
    monkeypatch.setattr(cor, "RATINGS_OUT_PATH", p)
    return p


def test_state_round_trip(ratings_path):
    assert cor._load_state() == {}
    state = {
        ("4328", "Arsenal"): {"alias": "A1", "rating": 92.5, "seed": 90.0, "n_updates": 3, "last_updated": "2026-10-10"},
    }
    cor._save_state(state)
    loaded = cor._load_state()
    assert loaded[("4328", "Arsenal")]["rating"] == 92.5
    assert loaded[("4328", "Arsenal")]["seed"] == 90.0
    assert loaded[("4328", "Arsenal")]["n_updates"] == 3
    assert loaded[("4328", "Arsenal")]["last_updated"] == "2026-10-10"


def test_state_keeps_same_team_name_separate_across_leagues(ratings_path):
    """The whole point of the (league_id, team) key -- England's "Arsenal"
    and Belarus's "Arsenal" (a real collision found live 2026-11-04) must
    never merge into one entry."""
    state = {
        ("4328", "Arsenal"): {"alias": "", "rating": 102.0, "seed": 100.0, "n_updates": 5, "last_updated": "2026-10-20"},
        ("4622", "Arsenal"): {"alias": "Arsenal Dzerzhinsk", "rating": 63.9, "seed": 63.9, "n_updates": 1, "last_updated": "2026-10-09"},
    }
    cor._save_state(state)
    loaded = cor._load_state()
    assert loaded[("4328", "Arsenal")]["rating"] == 102.0
    assert loaded[("4622", "Arsenal")]["rating"] == 63.9
    assert len(loaded) == 2
