"""
Tests for euro_2028_group_predictions.py's lightweight classic-Elo
win/draw/loss model and round-robin Monte Carlo -- the group-prediction
engine used once a Euro 2028 qualifying draw exists, driven by
nation_power_rankings.csv's combined_rating rather than the site's
Opta-goal Poisson engine.
"""

import euro_2028_group_predictions as gp


def test_evenly_matched_teams_have_near_equal_outcomes_and_peak_draw_rate():
    # e_home == 0.5 exactly (and so the draw probability sits at its
    # maximum, DRAW_PEAK) only when the home side's rating plus its
    # home-advantage boost exactly cancels the away side's rating.
    p_home, p_draw, p_away = gp.match_probabilities(1800.0 - gp.HOME_ADVANTAGE_ELO_PTS, 1800.0)
    assert abs(p_home - p_away) < 1e-9
    assert abs(p_draw - gp.DRAW_PEAK) < 1e-9
    assert abs((p_home + p_draw + p_away) - 1.0) < 1e-9


def test_probabilities_always_sum_to_one():
    for home, away in [(1200, 2300), (2300, 1200), (1800, 1800), (1500, 1500), (2000, 1000)]:
        p_home, p_draw, p_away = gp.match_probabilities(home, away)
        assert abs((p_home + p_draw + p_away) - 1.0) < 1e-9
        assert p_home >= 0 and p_draw >= 0 and p_away >= 0


def test_big_mismatch_favours_the_stronger_team_and_shrinks_draw_rate():
    p_home, p_draw, p_away = gp.match_probabilities(2300.0, 1200.0)
    assert p_home > 0.9
    assert p_draw < 0.05
    assert p_home > p_away


def test_team_rating_uses_name_aliases():
    ratings = {"Turkey": 1700.0, "Ireland": 1650.0, "Czechia": 1600.0}
    assert gp.team_rating("Türkiye", ratings) == 1700.0
    assert gp.team_rating("Republic of Ireland", ratings) == 1650.0
    assert gp.team_rating("Czechia", ratings) == 1600.0


def test_team_rating_falls_back_to_default_when_missing():
    assert gp.team_rating("Nowhereland", {}) == gp.DEFAULT_RATING


def test_round_robin_fixtures_are_home_and_away_for_every_pair():
    teams = ["A", "B", "C", "D"]
    fixtures = gp.round_robin_fixtures(teams)
    assert len(fixtures) == 4 * 3  # every team plays every other team twice
    for a in teams:
        for b in teams:
            if a != b:
                assert (a, b) in fixtures


def test_simulate_group_returns_one_row_per_team_with_points_and_probabilities():
    teams = ["Strongland", "Mediumland", "Weakland", "Tinyland"]
    ratings = {"Strongland": 2200.0, "Mediumland": 1800.0, "Weakland": 1400.0, "Tinyland": 1000.0}
    df = gp.simulate_group(teams, ratings, n_sim=500, seed=42)
    assert set(df["team"]) == set(teams)
    for pos in range(1, 5):
        assert f"pos_{pos}_prob" in df.columns
    for _, row in df.iterrows():
        total_prob = sum(row[f"pos_{pos}_prob"] for pos in range(1, 5))
        assert abs(total_prob - 1.0) < 1e-9


def test_simulate_group_ranks_the_strongest_team_first_on_average():
    teams = ["Strongland", "Mediumland", "Weakland", "Tinyland"]
    ratings = {"Strongland": 2200.0, "Mediumland": 1800.0, "Weakland": 1400.0, "Tinyland": 1000.0}
    df = gp.simulate_group(teams, ratings, n_sim=2000, seed=7)
    assert df.iloc[0]["team"] == "Strongland"
    assert df.iloc[-1]["team"] == "Tinyland"


def test_simulate_group_is_reproducible_with_the_same_seed():
    teams = ["A", "B", "C", "D", "E"]
    ratings = {t: 1500.0 + i * 50 for i, t in enumerate(teams)}
    first = gp.simulate_group(teams, ratings, n_sim=300, seed=99)
    second = gp.simulate_group(teams, ratings, n_sim=300, seed=99)
    assert first.equals(second)
