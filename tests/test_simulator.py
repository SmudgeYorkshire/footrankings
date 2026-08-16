"""
Tests for the Monte Carlo season simulator (simulator.py). Covers the
regressions found and fixed in this pass: the extra-time goal-rate
constant, the fast-path/slow-path tiebreak-order guard, and the
now-consistent NegBin goals model in simulate_final_four.
"""

import pandas as pd
import pytest

from simulator import (
    EXTRA_TIME_FRACTION,
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
