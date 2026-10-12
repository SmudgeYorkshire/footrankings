"""
Tests for the Monte Carlo season simulator (simulator.py). Covers the
regressions found and fixed in this pass: the extra-time goal-rate
constant, the fast-path/slow-path tiebreak-order guard, the
now-consistent NegBin goals model in simulate_final_four, the
clinched/eliminated position-bounds helpers, and the SEASON_STRENGTH_SIGMA
season-level variance fix.
"""

import numpy as np
import pandas as pd
import pytest

from simulator import (
    EXTRA_TIME_FRACTION,
    SEASON_STRENGTH_SIGMA,
    CLINCHED_SENTINEL,
    ELIMINATED_SENTINEL,
    cert_value,
    cert_cell_format,
    position_bounds,
    simulate_season,
    simulate_final_four,
    two_leg_advance_odds,
)


def _standings(teams):
    return [
        {"strTeam": t, "intRank": i + 1, "intPoints": 10 - i, "intGoalDifference": 5 - i,
         "intGoalsFor": 20 - i, "intPlayed": 10}
        for i, t in enumerate(teams)
    ]


def _ratings(teams, values):
    return pd.DataFrame({"team": teams, "alias": [""] * len(teams), "opta_rating": values})


def test_extra_time_fraction_is_a_third():
    """Regression test: this was accidentally 0.767 for a while (traced
    via git blame), contradicting its own "30 min = 1/3 of 90 min" intent."""
    assert EXTRA_TIME_FRACTION == pytest.approx(1 / 3)


def test_simulate_season_fast_path_probabilities_sum_to_one():
    teams = ["A", "B", "C", "D"]
    standings = _standings(teams)
    remaining = [
        {"strHomeTeam": "A", "strAwayTeam": "B"},
        {"strHomeTeam": "C", "strAwayTeam": "D"},
    ]
    ratings = _ratings(teams, [80.0, 75.0, 70.0, 65.0])
    probs = simulate_season(standings, remaining, ratings, n_sim=300, tiebreakers=["gd", "gf"])
    assert probs.shape == (4, 4)
    assert (probs.sum(axis=1).round(6) == 1.0).all()


def test_simulate_season_non_default_gd_gf_order_does_not_crash():
    """Regression test: the fast path used to trigger for ANY tiebreaker
    list without h2h/away_gf rules, including ["gf", "gd"] (wrong order)
    -- fixed to require the exact ["gd", "gf"] order, falling back to the
    general path otherwise. That general path had its own latent bug
    (referencing per-simulation H2H arrays that were never allocated for
    this case) which is what this test guards against."""
    teams = ["A", "B", "C", "D"]
    standings = _standings(teams)
    remaining = [{"strHomeTeam": "A", "strAwayTeam": "B"}]
    ratings = _ratings(teams, [80.0, 75.0, 70.0, 65.0])
    probs = simulate_season(standings, remaining, ratings, n_sim=200, tiebreakers=["gf", "gd"])
    assert probs.shape == (4, 4)
    assert (probs.sum(axis=1).round(6) == 1.0).all()


def test_simulate_season_h2h_path_does_not_crash():
    teams = ["A", "B", "C", "D"]
    standings = _standings(teams)
    remaining = [{"strHomeTeam": "A", "strAwayTeam": "B"}, {"strHomeTeam": "B", "strAwayTeam": "C"}]
    played = [{"strHomeTeam": "A", "strAwayTeam": "C", "intHomeScore": 2, "intAwayScore": 1}]
    ratings = _ratings(teams, [80.0, 75.0, 70.0, 65.0])
    probs = simulate_season(
        standings, remaining, ratings, n_sim=200,
        tiebreakers=["h2h_pts", "h2h_gd", "gd", "gf"], played_fixtures=played,
    )
    assert probs.shape == (4, 4)
    assert (probs.sum(axis=1).round(6) == 1.0).all()


def test_simulate_season_no_remaining_fixtures_is_deterministic():
    teams = ["A", "B"]
    standings = [
        {"strTeam": "A", "intRank": 1, "intPoints": 10, "intGoalDifference": 5, "intGoalsFor": 20, "intPlayed": 10},
        {"strTeam": "B", "intRank": 2, "intPoints": 7, "intGoalDifference": 1, "intGoalsFor": 12, "intPlayed": 10},
    ]
    ratings = _ratings(teams, [80.0, 70.0])
    probs = simulate_season(standings, [], ratings, n_sim=100)
    # A has more points -> 100% chance of finishing 1st
    assert probs.loc["A", "1"] == 1.0
    assert probs.loc["B", "2"] == 1.0


def test_simulate_final_four_returns_all_teams_with_valid_probabilities():
    teams = ["A", "B", "C", "D"]
    ratings = _ratings(teams, [85.0, 80.0, 75.0, 70.0])
    result = simulate_final_four(teams, ratings, n_sim=500)
    assert set(result["Team"]) == set(teams)
    for col in ("SF Win %", "Final %", "Title %"):
        assert (result[col] >= 0).all()
        assert (result[col] <= 100).all()
    # higher-seeded/stronger team should not have a worse title chance
    # than the weakest team (sanity check on the ratings actually mattering)
    a_title = result.loc[result["Team"] == "A", "Title %"].iloc[0]
    d_title = result.loc[result["Team"] == "D", "Title %"].iloc[0]
    assert a_title >= d_title


def test_two_leg_advance_odds_sum_to_one():
    teams = ["A", "B"]
    ratings = _ratings(teams, [80.0, 70.0])
    odds = two_leg_advance_odds("A", "B", ratings)
    assert odds["team1_adv"] + odds["team2_adv"] == pytest.approx(1.0, abs=1e-6)


# ── Mathematically clinched/eliminated position markers (position_bounds /
# cert_value / cert_cell_format, added 2026-10-12 for the ✓/X feature) ─────

def test_cert_value_maps_certain_flag_to_sentinels():
    assert cert_value(42.0, True) == CLINCHED_SENTINEL
    assert cert_value(42.0, False) == ELIMINATED_SENTINEL
    assert cert_value(42.0, None) == 42.0


def test_cert_cell_format_renders_checkmark_cross_or_percentage():
    assert cert_cell_format(CLINCHED_SENTINEL) == "✓"
    assert cert_cell_format(ELIMINATED_SENTINEL) == "X"
    assert cert_cell_format(46.1) == "46.1%"


def test_position_bounds_pins_a_runaway_leader_and_a_dead_last_team():
    # Leader has clinched 1st: its current points alone already beat every
    # rival's ceiling (current + 3*remaining). Bottom can never catch Mid.
    standings = [
        {"strTeam": "Leader", "intPoints": 80},
        {"strTeam": "Mid", "intPoints": 40},
        {"strTeam": "Bottom", "intPoints": 5},
    ]
    remaining = (
        [{"strHomeTeam": "Mid", "strAwayTeam": "Bottom"}] * 3
        + [{"strHomeTeam": "Leader", "strAwayTeam": "Mid"}] * 1
    )
    bounds = position_bounds(standings, remaining)
    assert bounds["Leader"] == (1, 1)
    assert bounds["Bottom"] == (3, 3)


def test_position_bounds_leaves_an_open_race_unpinned():
    standings = [
        {"strTeam": "A", "intPoints": 20},
        {"strTeam": "B", "intPoints": 18},
    ]
    remaining = [{"strHomeTeam": "A", "strAwayTeam": "B"}] * 5
    bounds = position_bounds(standings, remaining)
    # Either could still finish either 1st or 2nd with 5 games apiece left.
    assert bounds["A"] == (1, 2)
    assert bounds["B"] == (1, 2)


def test_position_bounds_pins_everyone_once_no_fixtures_remain():
    standings = [
        {"strTeam": "A", "intPoints": 30},
        {"strTeam": "B", "intPoints": 20},
        {"strTeam": "C", "intPoints": 10},
    ]
    assert position_bounds(standings, []) == {"A": (1, 1), "B": (2, 2), "C": (3, 3)}


# ── Season-level strength variance (SEASON_STRENGTH_SIGMA, added 2026-10-12
# to fix the overconfident title/finish odds flagged against EuroClubIndex/
# Opta/StatsUltra -- see the constant's own comment in simulator.py for the
# full diagnosis) ───────────────────────────────────────────────────────────

def test_season_sigma_widens_title_odds_without_flipping_the_favourite(monkeypatch):
    teams = ["Strong", "Weak"]
    standings = [
        {"strTeam": "Strong", "intRank": 1, "intPoints": 20, "intGoalDifference": 0, "intGoalsFor": 0, "intPlayed": 10},
        {"strTeam": "Weak", "intRank": 2, "intPoints": 17, "intGoalDifference": 0, "intGoalsFor": 0, "intPlayed": 10},
    ]
    ratings = _ratings(teams, [78.0, 72.0])
    # Plenty of head-to-head fixtures left so per-match noise alone would
    # mostly average out -- isolates the season-level effect being tested.
    remaining = [
        {"strHomeTeam": "Strong" if k % 2 == 0 else "Weak",
         "strAwayTeam": "Weak" if k % 2 == 0 else "Strong"}
        for k in range(24)
    ]

    # simulate_season seeds its own rng internally with no way to pass a
    # seed in; force it to a fixed seed so both runs below are reproducible.
    original_default_rng = np.random.default_rng
    monkeypatch.setattr(np.random, "default_rng", lambda *a, **k: original_default_rng(12345))

    no_variance = simulate_season(standings, remaining, ratings, n_sim=4000,
                                   season_sigma=0.0, apply_form=False)
    with_variance = simulate_season(standings, remaining, ratings, n_sim=4000,
                                     season_sigma=SEASON_STRENGTH_SIGMA, apply_form=False)

    p_no_variance = no_variance.loc["Strong", "1"]
    p_with_variance = with_variance.loc["Strong", "1"]

    # Strong stays the favourite either way, but per-match noise alone
    # (season_sigma=0) is the source of the overconfidence this constant
    # fixes -- with it applied, the title race should look meaningfully
    # less like a foregone conclusion.
    assert p_no_variance > 0.97
    assert 0.5 < p_with_variance < 0.97
    assert p_with_variance < p_no_variance
