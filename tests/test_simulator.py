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

import simulator
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
    _outcome_probs_from_lambdas,
    _solve_lambdas_for_market_probs,
    build_live_odds_lambda_overrides,
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


# ---------------------------------------------------------------------------
# Live match odds -- feeding a near-term fixture's real bookmaker odds
# directly into its own (home_lambda, away_lambda) pair (2026-11-05).
# ---------------------------------------------------------------------------

def test_outcome_probs_from_lambdas_sums_to_one():
    p_home, p_draw, p_away = _outcome_probs_from_lambdas(1.5, 1.1)
    assert p_home + p_draw + p_away == pytest.approx(1.0)


def test_outcome_probs_from_lambdas_higher_home_lambda_favours_home():
    low = _outcome_probs_from_lambdas(1.0, 1.0)
    high = _outcome_probs_from_lambdas(2.0, 1.0)
    assert high[0] > low[0]


def test_solve_lambdas_self_consistent_target_barely_moves():
    # Feeding a pair's own actual probabilities back in as the target
    # should recover (almost) exactly the same pair -- zero error the
    # whole time, so the iterative nudge should barely move it.
    lam_h0, lam_a0 = 1.6, 1.1
    target = _outcome_probs_from_lambdas(lam_h0, lam_a0)
    lam_h, lam_a = _solve_lambdas_for_market_probs(lam_h0, lam_a0, *target)
    assert lam_h == pytest.approx(lam_h0, abs=1e-6)
    assert lam_a == pytest.approx(lam_a0, abs=1e-6)


def test_solve_lambdas_converges_toward_a_realistic_market_shift():
    # Model starts out roughly even; market says the home side is a
    # heavy favourite -- solved probabilities should land close to it.
    lam_h, lam_a = _solve_lambdas_for_market_probs(1.3, 1.2, 0.70, 0.18, 0.12)
    p_home, p_draw, p_away = _outcome_probs_from_lambdas(lam_h, lam_a)
    assert p_home == pytest.approx(0.70, abs=0.02)
    assert p_away == pytest.approx(0.12, abs=0.02)


def test_solve_lambdas_respects_sanity_clamp_on_extreme_target():
    lam_h, lam_a = _solve_lambdas_for_market_probs(1.3, 1.2, 0.999, 0.0005, 0.0005)
    assert simulator._LIVE_ODDS_LAMBDA_MIN <= lam_h <= simulator._LIVE_ODDS_LAMBDA_MAX
    assert simulator._LIVE_ODDS_LAMBDA_MIN <= lam_a <= simulator._LIVE_ODDS_LAMBDA_MAX


def _two_team_ratings():
    return pd.DataFrame({"team": ["A", "B"], "alias": ["", ""], "opta_rating": [75.0, 75.0]})


def test_build_live_odds_lambda_overrides_empty_when_toggle_off(monkeypatch):
    monkeypatch.setattr(simulator, "USE_LIVE_MATCH_ODDS", False)
    result = build_live_odds_lambda_overrides(
        [{"strHomeTeam": "A", "strAwayTeam": "B"}], _two_team_ratings(), 1.2, "Test League",
    )
    assert result == {}


def test_build_live_odds_lambda_overrides_empty_when_no_coverage(monkeypatch):
    import daily_odds_loader
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", lambda league_name, **k: {})
    result = build_live_odds_lambda_overrides(
        [{"strHomeTeam": "A", "strAwayTeam": "B"}], _two_team_ratings(), 1.2, "Test League",
    )
    assert result == {}


def test_build_live_odds_lambda_overrides_skips_excluded_fixtures(monkeypatch):
    import daily_odds_loader
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", lambda league_name, **k: {
        ("A", "B"): {"home_prob": 0.70, "draw_prob": 0.18, "away_prob": 0.12, "bookmaker_count": 10},
    })
    result = build_live_odds_lambda_overrides(
        [{"strHomeTeam": "A", "strAwayTeam": "B"}], _two_team_ratings(), 1.2, "Test League",
        exclude={("A", "B")},
    )
    assert result == {}


def test_build_live_odds_lambda_overrides_skips_fixtures_with_no_odds_entry(monkeypatch):
    import daily_odds_loader
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", lambda league_name, **k: {
        ("C", "D"): {"home_prob": 0.5, "draw_prob": 0.25, "away_prob": 0.25, "bookmaker_count": 10},
    })
    result = build_live_odds_lambda_overrides(
        [{"strHomeTeam": "A", "strAwayTeam": "B"}], _two_team_ratings(), 1.2, "Test League",
    )
    assert result == {}


def test_build_live_odds_lambda_overrides_full_confidence_matches_solved_pair(monkeypatch):
    import daily_odds_loader
    from club_odds_ratings import MIN_BOOKMAKERS_FOR_FULL_WEIGHT
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", lambda league_name, **k: {
        ("A", "B"): {
            "home_prob": 0.70, "draw_prob": 0.18, "away_prob": 0.12,
            "bookmaker_count": MIN_BOOKMAKERS_FOR_FULL_WEIGHT,
        },
    })
    result = build_live_odds_lambda_overrides(
        [{"strHomeTeam": "A", "strAwayTeam": "B"}], _two_team_ratings(), 1.2, "Test League",
    )
    lam_h, lam_a = result[("A", "B")]
    p_home, _p_draw, p_away = _outcome_probs_from_lambdas(lam_h, lam_a)
    assert p_home == pytest.approx(0.70, abs=0.02)
    assert p_away == pytest.approx(0.12, abs=0.02)


def test_build_live_odds_lambda_overrides_zero_bookmakers_is_a_full_model_fallback(monkeypatch):
    import daily_odds_loader
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", lambda league_name, **k: {
        ("A", "B"): {"home_prob": 0.95, "draw_prob": 0.03, "away_prob": 0.02, "bookmaker_count": 0},
    })
    ratings = _two_team_ratings()
    result = build_live_odds_lambda_overrides(
        [{"strHomeTeam": "A", "strAwayTeam": "B"}], ratings, 1.2, "Test League",
    )
    # Equal ratings, home_advantage=1.2 -> the model's own lambda pair is
    # fully recoverable without reaching into simulator internals: both
    # attack/defense values are equal, so lam_h0/lam_a0 are just
    # DEFAULT_BASE_GOALS scaled by home_advantage and 1.0 respectively.
    from config import DEFAULT_BASE_GOALS
    lam_h, lam_a = result[("A", "B")]
    assert lam_h == pytest.approx(DEFAULT_BASE_GOALS * 1.2, rel=1e-6)
    assert lam_a == pytest.approx(DEFAULT_BASE_GOALS, rel=1e-6)
