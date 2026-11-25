"""
Tests for simulator.exact_position_bounds -- the exact (not merely sound)
best/worst final League Phase position used on european.py's Current
Standings and Manual Predictions tables. Covers the specific case
position_bounds leaves loose (two rivals who still play EACH OTHER can't
both simultaneously hit their own independent ceiling), a multi-team
mutual chain verified against brute force, already-decided teams, and a
larger cluster solved exactly via the underlying integer program.
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


def test_fully_connected_cluster_is_solved_exactly_not_approximated():
    # A 6-team fully-connected mutual cluster (15 remaining matches, a
    # mini round robin) against T=10 fixed. Two earlier implementations
    # of this function (a plain branch-and-bound DFS, then a greedy-
    # seeded version of the same thing) could silently fall back to the
    # crude "every contender simultaneously crosses" bound on clusters
    # not much bigger than this one -- this is now solved as a small
    # integer program (see _ilp_crossing_extreme's own docstring) and
    # should land strictly inside the loose bound's range, not just
    # repeat it.
    #
    # Worst case: happens to equal the loose bound here too (7) -- an
    # all-draws result genuinely pushes all 6 teams to 8+5*1=13>10 at
    # once, so position_bounds' independent-ceiling count was already
    # tight for this particular direction.
    #
    # Best case is the one that actually differs: pigeonhole forces at
    # least 3 of the 6 to exceed 10 regardless of how results are
    # arranged (15 matches distribute at least 30 points in total even
    # if every one is a draw, and no 2 teams playing only 5 games each
    # can absorb more than 15 of that between them while the other 4
    # still have 6 matches left to decide among themselves) -- so Best
    # is 4, not the loose bound's naive 1.
    standings = [{"strTeam": "T", "intPoints": 10}]
    teams = [f"R{i}" for i in range(6)]
    for t in teams:
        standings.append({"strTeam": t, "intPoints": 8})
    remaining = [
        {"strHomeTeam": a, "strAwayTeam": b}
        for a, b in itertools.combinations(teams, 2)
    ]
    loose = position_bounds(standings, remaining)
    exact = exact_position_bounds(standings, remaining)
    assert loose["T"] == (1, 7)
    assert exact["T"] == (4, 7)


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
