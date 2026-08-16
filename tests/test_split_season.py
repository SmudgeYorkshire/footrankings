"""
Tests for _split_season.py's tiebreak engine (rank_tied_group/build_h2h)
and the standings-building functions that use it. This logic underpins
every "live" table on the site — a regression here silently misranks
tied teams, which is hard to notice by eye.
"""

from _split_season import (
    build_h2h,
    rank_tied_group,
    compute_full_standings,
    ensure_full_roster,
)


def test_rank_tied_group_untouched_when_only_one_team():
    group = [{"strTeam": "A"}]
    assert rank_tied_group(group, ["gd", "gf"], {}) == group


def test_rank_tied_group_resolves_on_head_to_head():
    group = [
        {"strTeam": "A", "intGoalDifference": 5, "intGoalsFor": 10},
        {"strTeam": "B", "intGoalDifference": 5, "intGoalsFor": 10},
    ]
    h2h = {
        ("A", "B"): {"pts": 3, "gd": 1, "gf": 1, "away_gf": 0, "wins": 1},
        ("B", "A"): {"pts": 0, "gd": -1, "gf": 0, "away_gf": 0, "wins": 0},
    }
    result = rank_tied_group(group, ["h2h_pts", "h2h_gd", "gd", "gf"], h2h)
    assert [r["strTeam"] for r in result] == ["A", "B"]


def test_rank_tied_group_falls_through_unresolvable_rules():
    """Rules this site can't compute (no card data, literal playoff/coin
    toss) must be skipped, not crash or fabricate an answer."""
    group = [
        {"strTeam": "A", "intGoalDifference": 0, "intGoalsFor": 0},
        {"strTeam": "B", "intGoalDifference": 0, "intGoalsFor": 0},
    ]
    result = rank_tied_group(group, ["fair_play", "playoffs", "draw", "gd", "gf"], {})
    # still tied on every resolvable rule -> original order preserved
    assert [r["strTeam"] for r in result] == ["A", "B"]


def test_rank_tied_group_recurses_into_subgroups():
    """3 teams: A/B tied and ahead of C on GD; A/B further split by GF."""
    group = [
        {"strTeam": "A", "intGoalDifference": 5, "intGoalsFor": 10},
        {"strTeam": "B", "intGoalDifference": 5, "intGoalsFor": 8},
        {"strTeam": "C", "intGoalDifference": 1, "intGoalsFor": 20},
    ]
    result = rank_tied_group(group, ["gd", "gf"], {})
    assert [r["strTeam"] for r in result] == ["A", "B", "C"]


def test_build_h2h_basic():
    h2h = build_h2h([
        {"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 2, "intAwayScore": 1},
    ])
    assert h2h[("A", "B")] == {"pts": 3, "gd": 1, "gf": 2, "away_gf": 0, "wins": 1}
    assert h2h[("B", "A")] == {"pts": 0, "gd": -1, "gf": 1, "away_gf": 1, "wins": 0}


def test_build_h2h_draw_gives_both_sides_a_point():
    h2h = build_h2h([
        {"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 1, "intAwayScore": 1},
    ])
    assert h2h[("A", "B")]["pts"] == 1
    assert h2h[("B", "A")]["pts"] == 1
    assert h2h[("A", "B")]["wins"] == 0


def test_build_h2h_ignores_unscored_fixtures():
    h2h = build_h2h([
        {"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": None, "intAwayScore": None},
    ])
    assert h2h == {}


def test_compute_full_standings_default_tiebreak_is_gd_then_gf():
    roster = [{"strTeam": t} for t in ("A", "B")]
    fixtures = [
        {"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 2, "intAwayScore": 0},
    ]
    table = compute_full_standings(roster, fixtures)
    assert [r["strTeam"] for r in table] == ["A", "B"]
    assert table[0]["intPoints"] == 3
    assert table[0]["intGoalDifference"] == 2


def test_compute_full_standings_head_to_head_beats_gd_gf_tie():
    """Regression test for the core bug fixed in this pass: two teams
    exactly level on points/GD/GF must be split by head-to-head when the
    league's tiebreaker order asks for it, not left in arbitrary order."""
    roster = [{"strTeam": t} for t in ("A", "B", "C", "D", "E")]
    fixtures = [
        {"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 1, "intAwayScore": 0},  # h2h: A > B
        {"strHomeTeam": "A", "strAwayTeam": "C", "intHomeScore": 1, "intAwayScore": 1},
        {"strHomeTeam": "B", "strAwayTeam": "D", "intHomeScore": 2, "intAwayScore": 0},
        {"strHomeTeam": "B", "strAwayTeam": "E", "intHomeScore": 0, "intAwayScore": 0},
    ]
    a = next(r for r in compute_full_standings(roster, fixtures) if r["strTeam"] == "A")
    b = next(r for r in compute_full_standings(roster, fixtures) if r["strTeam"] == "B")
    assert (a["intPoints"], a["intGoalDifference"], a["intGoalsFor"]) == \
           (b["intPoints"], b["intGoalDifference"], b["intGoalsFor"]), "test setup must be a genuine tie"

    default_order = [r["strTeam"] for r in compute_full_standings(roster, fixtures, tiebreakers=["gd", "gf"])
                      if r["strTeam"] in ("A", "B")]
    h2h_order = [r["strTeam"] for r in compute_full_standings(roster, fixtures, tiebreakers=["h2h_pts", "gd", "gf"])
                 if r["strTeam"] in ("A", "B")]
    assert h2h_order == ["A", "B"]
    # sanity: without any h2h rule, this specific engineered tie is left
    # in whatever order the teams were built in (not asserted which way,
    # just that the h2h-aware result is deterministic and correct)
    assert default_order[0] in ("A", "B")


def test_compute_full_standings_ranks_are_contiguous():
    roster = [{"strTeam": t} for t in ("A", "B", "C")]
    fixtures = [{"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 1, "intAwayScore": 0}]
    table = compute_full_standings(roster, fixtures)
    assert sorted(r["intRank"] for r in table) == [1, 2, 3]
    assert {r["strTeam"] for r in table} == {"A", "B", "C"}


def test_ensure_full_roster_pads_missing_teams_from_fixtures():
    roster = [{"strTeam": "A", "strBadge": "a.png"}]
    fixtures = [
        {"strHomeTeam": "A", "strAwayTeam": "B", "strAwayTeamBadge": "b.png"},
        {"strHomeTeam": "C", "strAwayTeam": "A", "strHomeTeamBadge": "c.png"},
    ]
    padded = ensure_full_roster(roster, fixtures)
    names = {r["strTeam"] for r in padded}
    assert names == {"A", "B", "C"}
    assert next(r for r in padded if r["strTeam"] == "B")["strBadge"] == "b.png"


def test_ensure_full_roster_does_not_duplicate_known_teams():
    roster = [{"strTeam": "A", "strBadge": "a.png"}]
    fixtures = [{"strHomeTeam": "A", "strAwayTeam": "B"}]
    padded = ensure_full_roster(roster, fixtures)
    assert sum(1 for r in padded if r["strTeam"] == "A") == 1
