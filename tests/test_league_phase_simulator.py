"""
Tests for the pure-logic pieces of league_phase_simulator.py's knockout-
stage noise (added 2026-11-04 -- see simulate_competition_winner's and
_KNOCKOUT_SIGMA's own docstrings for the full story). Both the probability
helpers and the sigma-resolution helper are plain functions with no I/O,
so they're imported and tested directly rather than needing the AST-
extraction workaround test_european_logic.py uses for Streamlit page
scripts -- this module has none of that.
"""

import math

import pandas as pd

from league_phase_simulator import (
    _KNOCKOUT_SIGMA,
    _noisy_single_match_prob,
    _noisy_two_leg_advance_prob,
    _resolve_knockout_sigma,
    assign_pots,
    generate_league_phase_schedule,
    build_predicted_bracket,
)


def test_noisy_two_leg_equal_teams_is_a_coin_flip():
    p = _noisy_two_leg_advance_prob(
        a_att=1.3, a_def=1.3, b_att=1.3, b_def=1.3,
        ha_a=1.2, ha_b=1.2, league_avg=1.3, phi=0.15, noise_a=1.0, noise_b=1.0,
    )
    assert math.isclose(p, 0.5, abs_tol=1e-9)


def test_noisy_two_leg_stronger_attack_favours_that_side():
    p = _noisy_two_leg_advance_prob(
        a_att=2.0, a_def=1.3, b_att=1.3, b_def=1.3,
        ha_a=1.2, ha_b=1.2, league_avg=1.3, phi=0.15, noise_a=1.0, noise_b=1.0,
    )
    assert p > 0.5


def test_noisy_two_leg_weaker_defense_hurts_that_side():
    p = _noisy_two_leg_advance_prob(
        a_att=1.3, a_def=2.5, b_att=1.3, b_def=1.3,  # a_def is numerically a WORSE (higher) defense value
        ha_a=1.2, ha_b=1.2, league_avg=1.3, phi=0.15, noise_a=1.0, noise_b=1.0,
    )
    assert p < 0.5


def test_noisy_two_leg_own_noise_boosts_own_advance_probability():
    kwargs = dict(
        a_att=1.3, a_def=1.3, b_att=1.3, b_def=1.3,
        ha_a=1.2, ha_b=1.2, league_avg=1.3, phi=0.15,
    )
    p_baseline = _noisy_two_leg_advance_prob(noise_a=1.0, noise_b=1.0, **kwargs)
    p_a_hot = _noisy_two_leg_advance_prob(noise_a=1.5, noise_b=1.0, **kwargs)
    assert p_a_hot > p_baseline > 0.5 - 1e-9


def test_noisy_single_match_equal_teams_is_a_coin_flip():
    p = _noisy_single_match_prob(
        a_att=1.3, a_def=1.3, b_att=1.3, b_def=1.3,
        league_avg=1.3, phi=0.15, noise_a=1.0, noise_b=1.0,
    )
    assert math.isclose(p, 0.5, abs_tol=1e-9)


def test_noisy_single_match_stronger_side_favoured():
    p = _noisy_single_match_prob(
        a_att=2.0, a_def=1.3, b_att=1.3, b_def=1.3,
        league_avg=1.3, phi=0.15, noise_a=1.0, noise_b=1.0,
    )
    assert p > 0.5


def test_knockout_sigma_has_all_three_competitions():
    assert set(_KNOCKOUT_SIGMA) == {"Champions League", "Europa League", "Conference League"}
    assert all(v >= 0 for v in _KNOCKOUT_SIGMA.values())


def test_resolve_knockout_sigma_explicit_override_wins():
    assert _resolve_knockout_sigma("Champions League", season_sigma=0.30, knockout_sigma=0.0) == 0.0
    assert _resolve_knockout_sigma("Champions League", season_sigma=0.30, knockout_sigma=0.9) == 0.9


def test_resolve_knockout_sigma_defaults_to_per_competition_table():
    assert _resolve_knockout_sigma("Champions League", season_sigma=0.30, knockout_sigma=None) == _KNOCKOUT_SIGMA["Champions League"]
    assert _resolve_knockout_sigma("Conference League", season_sigma=0.30, knockout_sigma=None) == _KNOCKOUT_SIGMA["Conference League"]


def test_resolve_knockout_sigma_falls_back_to_season_sigma_for_unknown_competition():
    assert _resolve_knockout_sigma("Nations League", season_sigma=0.30, knockout_sigma=None) == 0.30
    assert _resolve_knockout_sigma(None, season_sigma=0.0, knockout_sigma=None) == 0.0


# ---------------------------------------------------------------------------
# build_predicted_bracket -- the 2026-11-05 live-match-odds override, the
# one gap left over from wiring it into simulate_competition_winner.
# ---------------------------------------------------------------------------

def _36team_setup():
    teams = [f"T{i}" for i in range(36)]
    field = [{"team": t, "country": f"C{i % 12}"} for i, t in enumerate(teams)]
    club_coeff = {t: 50.0 for t in teams}
    ratings_df = pd.DataFrame({"team": teams, "alias": [""] * 36, "opta_rating": [75.0] * 36})
    team_country = {f["team"]: f["country"] for f in field}
    pots = assign_pots(teams, club_coeff, 4)
    schedule = generate_league_phase_schedule(pots, team_country, 2)
    return field, club_coeff, ratings_df, schedule


def test_build_predicted_bracket_without_comp_name_is_unaffected_by_odds(monkeypatch):
    import daily_odds_loader
    # Even if live odds happen to be available, omitting comp_name (the
    # default, same as every pre-2026-11-05 caller) must never look them
    # up at all -- confirms this stays a true no-op for any caller that
    # hasn't been updated to pass it.
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", lambda league_name, **k: (_ for _ in ()).throw(
        AssertionError("load_live_odds_for_league should not be called when comp_name is omitted")
    ))
    field, club_coeff, ratings_df, schedule = _36team_setup()
    bracket = build_predicted_bracket(
        field, club_coeff, ratings_df, n_pots=4, opponents_per_pot=2, n_sim=200, schedule=schedule,
    )
    assert bracket["champion"] in [f["team"] for f in field]


def test_build_predicted_bracket_with_comp_name_uses_live_odds_override(monkeypatch):
    import daily_odds_loader
    field, club_coeff, ratings_df, schedule = _36team_setup()
    fx = next(f for f in schedule if f["strHomeTeam"] == "T0" or f["strAwayTeam"] == "T0")
    key = (fx["strHomeTeam"], fx["strAwayTeam"])
    # Make T0 an overwhelming favourite in whichever slot it's actually in.
    probs = {"home_prob": 0.95, "draw_prob": 0.03, "away_prob": 0.02, "bookmaker_count": 10} \
        if key[0] == "T0" else {"home_prob": 0.02, "draw_prob": 0.03, "away_prob": 0.95, "bookmaker_count": 10}
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", lambda league_name, **k: {key: probs})
    bracket = build_predicted_bracket(
        field, club_coeff, ratings_df, n_pots=4, opponents_per_pot=2, n_sim=200, schedule=schedule,
        comp_name="Champions League",
    )
    assert bracket["champion"] in [f["team"] for f in field]


def test_build_predicted_bracket_excludes_real_results_from_the_override(monkeypatch):
    import daily_odds_loader
    field, club_coeff, ratings_df, schedule = _36team_setup()
    fx = next(f for f in schedule if f["strHomeTeam"] == "T0" or f["strAwayTeam"] == "T0")
    key = (fx["strHomeTeam"], fx["strAwayTeam"])
    calls = []

    def _fake_load(league_name, **k):
        return {key: {"home_prob": 0.95, "draw_prob": 0.03, "away_prob": 0.02, "bookmaker_count": 10}}
    monkeypatch.setattr(daily_odds_loader, "load_live_odds_for_league", _fake_load)

    # Spy on build_live_odds_lambda_overrides itself to confirm the exclude
    # set it receives actually carries the real_results key through.
    import simulator
    original = simulator.build_live_odds_lambda_overrides
    def _spy(fixtures, ratings, home_advantage, league_name, home_advantage_overrides=None, exclude=None):
        calls.append(exclude)
        return original(fixtures, ratings, home_advantage, league_name,
                         home_advantage_overrides=home_advantage_overrides, exclude=exclude)
    monkeypatch.setattr("league_phase_simulator.build_live_odds_lambda_overrides", _spy)

    build_predicted_bracket(
        field, club_coeff, ratings_df, n_pots=4, opponents_per_pot=2, n_sim=200, schedule=schedule,
        real_results={key: (2, 0)}, comp_name="Champions League",
    )
    assert calls == [{key}]
