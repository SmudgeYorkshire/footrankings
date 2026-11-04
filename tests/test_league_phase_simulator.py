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

from league_phase_simulator import (
    _KNOCKOUT_SIGMA,
    _noisy_single_match_prob,
    _noisy_two_leg_advance_prob,
    _resolve_knockout_sigma,
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
