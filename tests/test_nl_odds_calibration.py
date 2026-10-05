"""
Regression coverage for nl_odds_calibration.fit_match_adjustments' carry-
forward behavior -- confirmed via real daily commits that shrinking every
team in the carried-forward adjustments dict (not just the ones this
call's observations actually mention) silently wipes out a team's prior
correction if it simply isn't re-observed that day, even though nothing
contradicted it (ratings/nations_league_elo_adjustments.csv lost 8 teams
between the 2026-10-03 and 2026-10-04 automated runs this way).
"""

from nl_odds_calibration import fit_match_adjustments


def test_untouched_team_keeps_its_prior_adjustment():
    base_elo = {"Alpha": 1800.0, "Beta": 1700.0, "Gamma": 1600.0}
    prior = {"Gamma": 25.0}  # some earlier day's fitted correction
    observations = [
        {"type": "match", "home": "Alpha", "away": "Beta", "odds": (1.8, 3.5, 4.2)},
    ]
    fitted = fit_match_adjustments(base_elo, prior, observations=observations)
    # Gamma wasn't in today's observations at all -- its prior correction
    # must survive unchanged, not decay toward 0.
    assert fitted["Gamma"] == 25.0


def test_empty_observations_is_a_no_op():
    base_elo = {"Alpha": 1800.0, "Beta": 1700.0}
    prior = {"Alpha": 10.0, "Beta": -10.0}
    fitted = fit_match_adjustments(base_elo, prior, observations=[])
    assert fitted == prior


def test_observed_team_still_gets_fit_and_shrunk():
    base_elo = {"Alpha": 1800.0, "Beta": 1700.0}
    prior = {"Alpha": 0.0, "Beta": 0.0}
    observations = [
        {"type": "match", "home": "Alpha", "away": "Beta", "odds": (1.2, 6.0, 10.0)},
    ]
    fitted = fit_match_adjustments(base_elo, prior, observations=observations)
    # Alpha is a heavy favourite in the observed odds -- its fitted
    # adjustment should move upward (Beta downward) from the 0.0 prior.
    assert fitted["Alpha"] > 0
    assert fitted["Beta"] < 0
