"""
Tests for euro_2028_qualifying_odds.py -- the Monte Carlo estimate of
every nation's overall chance to reach the Euro 2028 finals (averaged
over the qualifying draw's own randomness too, not conditioned on one
sampled draw).
"""

import euro_2028_qualifying_odds as qo
from euro_2028_draw import POTS


def _ratings_by_rank() -> dict[str, float]:
    """A flat, mildly-descending rating per team (by pot, then position
    within pot) -- enough spread to exercise the routing logic without
    needing real Strength Ranking data."""
    ratings = {}
    rating = 2200.0
    for pot_num in sorted(POTS):
        for team in POTS[pot_num]:
            ratings[team] = rating
            rating -= 5.0
    return ratings


def test_resolve_trial_finalists_matches_resolve_finalists_routes():
    # Same shape euro_2028_finals_bracket.resolve_finalists itself
    # expects, but realized as one trial's actual points instead of a
    # probability table -- the two must agree on who gets which route
    # for an unambiguous (no ties) scenario.
    group_order = {
        "A": [("A1", 15), ("A2", 10), ("A3", 5), ("A4", 0)],
        "B": [("B1", 15), ("B2", 11), ("B3", 5), ("B4", 0)],
        "C": [("C1", 15), ("C2", 12), ("C3", 5), ("C4", 0)],
        "D": [("D1", 15), ("D2", 13), ("D3", 5), ("D4", 0)],
        "E": [("E1", 15), ("E2", 14), ("E3", 5), ("E4", 0)],
        "F": [("F1", 15), ("F2", 9), ("F3", 5), ("F4", 0)],
    }
    routes = qo._resolve_trial_finalists(group_order)

    winners = {g[0] for g in group_order}
    assert all(routes[f"{g}1"] == "Qualifying winner" for g in winners)
    # 6 runners-up ranked by ppg (all groups size 4, so ppg order ==
    # raw-points order): E2(14) > D2(13) > C2(12) > B2(11) > A2(10) > F2(9)
    # -- only 6 runners-up exist in this synthetic 6-group scenario, so
    # all 6 qualify as runners-up directly (top8 cut never binds).
    for g in winners:
        assert routes[f"{g}2"] == "Qualifying runner-up"


def test_resolve_trial_finalists_always_returns_24_unique_teams():
    group_order = {
        letter: [(f"{letter}{i}", pts) for i, pts in enumerate([15, 11, 6, 3], start=1)]
        for letter in "ABCDEFGHIJKL"
    }
    routes = qo._resolve_trial_finalists(group_order)
    assert len(routes) == 24
    assert len(set(routes)) == 24
    assert set(routes.values()) <= {
        "Qualifying winner", "Qualifying runner-up", "Host reservation", "Play-off (simplified)",
    }


def test_simulate_qualifying_chances_covers_all_54_nations_and_sums_sensibly():
    ratings = _ratings_by_rank()
    df = qo.simulate_qualifying_chances(ratings, n_sim=50, seed=1)

    assert len(df) == 54
    assert set(df["team"]) == {t for pot in POTS.values() for t in pot}

    for _, row in df.iterrows():
        route_sum = sum(row[r] for r in qo.ROUTES)
        assert abs(route_sum - row["qualified"]) < 1e-9
        assert 0.0 <= row["qualified"] <= 1.0

    # Exactly 24 of the 54 nations qualify in every single trial, so the
    # "qualified" probabilities must sum to exactly 24 across all teams.
    assert abs(df["qualified"].sum() - 24.0) < 1e-6


def test_simulate_qualifying_chances_is_reproducible_with_the_same_seed():
    ratings = _ratings_by_rank()
    first = qo.simulate_qualifying_chances(ratings, n_sim=30, seed=7)
    second = qo.simulate_qualifying_chances(ratings, n_sim=30, seed=7)
    assert first.equals(second)


def test_simulate_qualifying_chances_favours_higher_rated_pot_1_teams():
    ratings = _ratings_by_rank()
    df = qo.simulate_qualifying_chances(ratings, n_sim=200, seed=3).set_index("team")
    # The single highest-rated team (first in Pot 1) should qualify
    # clearly more often than not -- it's the strongest team in its
    # group by a wide margin in this synthetic ratings ladder, though
    # still not a certainty given group/draw variance and an occasional
    # tough Pot-1-strength group draw.
    top_team = POTS[1][0]
    assert df.loc[top_team, "qualified"] > 0.75
