"""
Tests for the pure-logic pieces of european.py. Play-off bracket
resolution lives in qualifying_projection.py (a plain importable module)
and is imported directly. european.py itself is still a Streamlit page
script (it fetches live data and renders UI at import time), so functions
that remain there (like _compute_league_standings) still need ast
-extraction into a minimal namespace instead.
"""

import ast
from pathlib import Path

import pytest

from qualifying_projection import _leg_aggregate_winner as _leg_aggregate_winner_impl


def _extract_function(file_path: str, func_name: str, namespace: dict) -> callable:
    src = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            exec(ast.get_source_segment(src, node), namespace)
            return namespace[func_name]
    raise AssertionError(f"{func_name} not found in {file_path}")


@pytest.fixture()
def leg_aggregate_winner():
    return _leg_aggregate_winner_impl


def test_leg_aggregate_winner_first_team_wins_on_aggregate(leg_aggregate_winner):
    # leg1: A(home) 2-0 B(away); leg2: B(home) 0-1 A(away) -> A 3, B 0
    assert leg_aggregate_winner("A", "B", 2, 0, 0, 1) == "A"


def test_leg_aggregate_winner_second_team_wins_on_aggregate(leg_aggregate_winner):
    # leg1: A 0-1 B; leg2: B 2-0 A -> A: 0+0=0, B: 1+2=3
    assert leg_aggregate_winner("A", "B", 0, 1, 2, 0) == "B"


def test_leg_aggregate_winner_none_when_level_on_aggregate(leg_aggregate_winner):
    """Level on aggregate means it went to penalties -- this site doesn't
    track a penalty-shootout winner here, so None is the correct answer,
    not a guess."""
    assert leg_aggregate_winner("A", "B", 1, 0, 1, 0) is None


@pytest.fixture()
def compute_league_standings():
    from _split_season import build_h2h, rank_tied_group
    ns = {
        "build_h2h": build_h2h,
        "rank_tied_group": rank_tied_group,
        # Mirrors european.py's own _LEAGUE_PHASE_TIEBREAKERS -- UEFA's
        # real Article 18 order has NO head-to-head criterion at all
        # (confirmed live 2026-11-25 against documents.uefa.com; an
        # earlier version of both this fixture and the real constant
        # wrongly had h2h first, inherited from the old group-stage
        # rules the new Swiss-model league phase deliberately dropped).
        "_LEAGUE_PHASE_TIEBREAKERS": ["gd", "gf", "away_gf", "wins", "away_wins"],
    }
    return _extract_function("european.py", "_compute_league_standings", ns)


def test_compute_league_standings_ignores_head_to_head_uses_gd(compute_league_standings):
    # A and B are tied on points AND head-to-head (they haven't played
    # each other at all here), but A has the better overall goal
    # difference -- the real UEFA League Phase rule (Article 18.01) goes
    # straight from points to GD with no head-to-head step, so A must
    # rank above B on GD alone.
    matches = [
        {"strHomeTeam": "A", "strAwayTeam": "C", "intHomeScore": 3, "intAwayScore": 0},
        {"strHomeTeam": "B", "strAwayTeam": "D", "intHomeScore": 1, "intAwayScore": 0},
    ]
    rows = compute_league_standings(matches, {})
    a = next(r for r in rows if r["strTeam"] == "A")
    b = next(r for r in rows if r["strTeam"] == "B")
    assert a["Pts"] == b["Pts"], "test setup must be a genuine tie on points"
    assert a["GD"] > b["GD"], "test setup must be a genuine GD gap"

    order = [r["strTeam"] for r in rows if r["strTeam"] in ("A", "B")]
    assert order == ["A", "B"], "A has the better goal difference and must rank above B"


def test_compute_league_standings_ranks_are_contiguous(compute_league_standings):
    matches = [{"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 1, "intAwayScore": 0}]
    rows = compute_league_standings(matches, {})
    assert sorted(r["intRank"] for r in rows) == [1, 2]
