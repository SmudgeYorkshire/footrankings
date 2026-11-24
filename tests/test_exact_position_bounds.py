"""
Tests for simulator.exact_position_bounds -- the exact (not merely sound)
best/worst final League Phase position used on european.py's Current
Standings and Manual Predictions tables. Covers the specific case
position_bounds leaves loose (two rivals who still play EACH OTHER can't
both simultaneously hit their own independent ceiling), a multi-team
mutual chain verified against brute force, already-decided teams, and
the documented size/budget fallbacks.
"""

import itertools

from simulator import exact_position_bounds, position_bounds


def test_two_rivals_playing_each_other_cant_both_reach_ceiling():
    # T=10 (0 remaining, fixed). X=5, Y=5 each also have a "free" extra
    # game vs a guaranteed-loser W, so each one's INDEPENDENT ceiling is
    # 5+3+3=11 > 10 -- naively both "could" pass T. But their own mutual
    # match hands out at most 3 more points total between the two of
    # them, so AT MOST ONE of X/Y can actually reach 11; the other caps
    # at 9 (losing the mutual match) or 9 (drawing it, 8+1).
    standings = [
        {"strTeam": "T", "intPoints": 10},
        {"strTeam": "X", "intPoints": 5},
        {"strTeam": "Y", "intPoints": 5},
        {"strTeam": "W", "intPoints": 0},
    ]
    remaining = [
        {"strHomeTeam": "X", "strAwayTeam": "Y"},
        {"strHomeTeam": "X", "strAwayTeam": "W"},
        {"strHomeTeam": "Y", "strAwayTeam": "W"},
    ]
    loose = position_bounds(standings, remaining)
    exact = exact_position_bounds(standings, remaining)
    assert loose["T"] == (1, 3)  # naive: both X and Y could pass T at once
    assert exact["T"] == (1, 2)  # exact: only one of them actually can


def test_three_way_mutual_chain_matches_brute_force():
    # T=10 fixed. X, Y, Z each at 8, playing a mini round-robin against
    # each other (3 matches, no other remaining fixtures) -- brute force
    # every one of the 27 possible result combinations to get the true
    # answer, and confirm the solver matches it exactly.
    standings = [
        {"strTeam": "T", "intPoints": 10},
        {"strTeam": "X", "intPoints": 8},
        {"strTeam": "Y", "intPoints": 8},
        {"strTeam": "Z", "intPoints": 8},
    ]
    remaining = [
        {"strHomeTeam": "X", "strAwayTeam": "Y"},
        {"strHomeTeam": "Y", "strAwayTeam": "Z"},
        {"strHomeTeam": "X", "strAwayTeam": "Z"},
    ]
    outcomes = [(3, 0), (1, 1), (0, 3)]
    best_max = 0
    for r1, r2, r3 in itertools.product(outcomes, repeat=3):
        pts = {"X": 8, "Y": 8, "Z": 8}
        pts["X"] += r1[0]; pts["Y"] += r1[1]
        pts["Y"] += r2[0]; pts["Z"] += r2[1]
        pts["X"] += r3[0]; pts["Z"] += r3[1]
        best_max = max(best_max, sum(1 for v in pts.values() if v > 10))

    bounds = exact_position_bounds(standings, remaining)
    assert bounds["T"] == (1, 1 + best_max)


def test_team_already_locked_above_counts_regardless_of_any_result():
    # O's current points alone already exceed T's best-case ceiling --
    # no remaining result can undo that, so it must count unconditionally.
    standings = [
        {"strTeam": "T", "intPoints": 5},
        {"strTeam": "O", "intPoints": 20},
    ]
    remaining = [{"strHomeTeam": "T", "strAwayTeam": "O"}]
    bounds = exact_position_bounds(standings, remaining)
    assert bounds["T"] == (2, 2)


def test_team_that_can_never_reach_cap_is_dropped_as_a_threat():
    # O's own ceiling can never reach T's current points even winning
    # every remaining game -- O should never count as a threat to T's
    # worst case, unlike the loose bound's cruder per-team comparison
    # (which happens to agree here, but for a different reason).
    standings = [
        {"strTeam": "T", "intPoints": 30},
        {"strTeam": "O", "intPoints": 0},
    ]
    remaining = [{"strHomeTeam": "O", "strAwayTeam": "O2"}, {"strHomeTeam": "O2", "strAwayTeam": "T"}]
    # O2 also at 0 by omission -- give it an explicit row.
    standings.append({"strTeam": "O2", "intPoints": 0})
    bounds = exact_position_bounds(standings, remaining)
    assert bounds["T"][1] == 1  # nobody can mathematically catch T


def test_matches_against_t_itself_are_resolved_not_free_variables():
    # T's own remaining fixture against O is fixed by T's own best/worst
    # case (T wins it for T's best case, loses it for T's worst case) --
    # it must not also appear as a free "mutual" variable, and O's points
    # must reflect that fixed result (0 extra for O when T wins it, +3
    # extra for O when T loses it).
    standings = [
        {"strTeam": "T", "intPoints": 5},
        {"strTeam": "O", "intPoints": 5},
    ]
    remaining = [{"strHomeTeam": "T", "strAwayTeam": "O"}]
    bounds = exact_position_bounds(standings, remaining)
    # T's best case: T beats O -> T=8, O stays 5 -> T best = 1.
    # T's worst case: T loses to O -> T=5, O=8 -> O now above T -> T worst = 2.
    assert bounds["T"] == (1, 2)


def test_fallback_when_contender_cluster_exceeds_the_edge_cap():
    # A single oversized mutual cluster shouldn't hang or crash -- it
    # should degrade to the same sound-but-loose treatment position_
    # bounds already uses everywhere, for just that cluster.
    standings = [{"strTeam": "T", "intPoints": 10}]
    teams = [f"R{i}" for i in range(6)]
    for t in teams:
        standings.append({"strTeam": t, "intPoints": 8})
    remaining = [
        {"strHomeTeam": a, "strAwayTeam": b}
        for a, b in itertools.combinations(teams, 2)
    ]  # a fully-connected 6-team cluster -- 15 mutual edges
    bounds = exact_position_bounds(standings, remaining, max_contender_edges=5)
    # Falls back to "every contender simultaneously crosses" for this
    # cluster -- sound (conservative), returns promptly, doesn't crash.
    assert bounds["T"][1] == 1 + len(teams)


def test_node_budget_exhaustion_still_uses_greedy_seed_for_best():
    # Same fully-connected 6-team cluster as the edge-cap fallback test
    # above, but forced to exhaust its SEARCH budget instead (node_budget=1
    # -- the branch-and-bound gets zero real search). Confirmed live
    # 2026-11-24: without a seed, a real ~34-team contender cluster
    # (Champions League, Slovan Bratislava's own Best case) never improved
    # on the trivial "everyone crosses" bound even at 100x the default
    # node_budget, because the search's own fixed match-order DFS never
    # stumbled on a better full assignment in time -- a cheap greedy seed
    # found one (6 crossings instead of 34) in under a millisecond. Here,
    # with node_budget=1, the minimize (Best) direction must still land on
    # the greedy seed's result, not the crude "all 6 cross" fallback.
    standings = [{"strTeam": "T", "intPoints": 10}]
    teams = [f"R{i}" for i in range(6)]
    for t in teams:
        standings.append({"strTeam": t, "intPoints": 8})
    remaining = [
        {"strHomeTeam": a, "strAwayTeam": b}
        for a, b in itertools.combinations(teams, 2)
    ]
    starved = exact_position_bounds(standings, remaining, node_budget=1)
    full = exact_position_bounds(standings, remaining)
    assert starved["T"][0] < 1 + len(teams)  # better than the trivial "everyone crosses"
    assert starved["T"][0] == full["T"][0]  # the seed alone already matches the fully-searched answer here


def test_tiebreaker_reuse_matches_position_bounds_behavior():
    # A and B are tied on points with zero remaining fixtures each (both
    # already "finished"), decided only by their own head-to-head result
    # -- the exact-equality tiebreak case position_bounds already
    # resolves. Confirms exact_position_bounds reuses that same logic
    # (same played_fixtures/tiebreakers plumbing) and agrees with it.
    standings = [
        {"strTeam": "A", "intPoints": 10, "intGoalDifference": 5, "intGoalsFor": 10},
        {"strTeam": "B", "intPoints": 10, "intGoalDifference": 5, "intGoalsFor": 9},
    ]
    remaining = []
    played = [{"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 2, "intAwayScore": 0}]
    tiebreakers = ["h2h_pts"]
    loose = position_bounds(standings, remaining, played, tiebreakers)
    exact = exact_position_bounds(standings, remaining, played, tiebreakers)
    assert exact == loose == {"A": (1, 1), "B": (2, 2)}
