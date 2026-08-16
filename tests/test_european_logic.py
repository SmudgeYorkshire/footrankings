"""
Tests for the pure-logic pieces of european.py. european.py is a
Streamlit page script (it fetches live data and renders UI at import
time), so it can't be imported directly in a test process — instead we
extract just the target function's source via ast and exec it with a
minimal namespace. This mirrors the manual verification done while
building the fix, formalized so it runs in CI instead of by hand.
"""

import ast
from pathlib import Path

import pytest


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
    return _extract_function("european.py", "_leg_aggregate_winner", {})


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
        "_LEAGUE_PHASE_TIEBREAKERS": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf"],
    }
    return _extract_function("european.py", "_compute_league_standings", ns)


def test_compute_league_standings_applies_head_to_head(compute_league_standings):
    matches = [
        {"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 1, "intAwayScore": 0},
        {"strHomeTeam": "A", "strAwayTeam": "C", "intHomeScore": 1, "intAwayScore": 1},
        {"strHomeTeam": "B", "strAwayTeam": "D", "intHomeScore": 2, "intAwayScore": 0},
        {"strHomeTeam": "B", "strAwayTeam": "E", "intHomeScore": 0, "intAwayScore": 0},
    ]
    rows = compute_league_standings(matches, {})
    a = next(r for r in rows if r["strTeam"] == "A")
    b = next(r for r in rows if r["strTeam"] == "B")
    assert (a["Pts"], a["GD"], a["GF"]) == (b["Pts"], b["GD"], b["GF"]), "test setup must be a genuine tie"

    order = [r["strTeam"] for r in rows if r["strTeam"] in ("A", "B")]
    assert order == ["A", "B"], "A beat B head-to-head and must rank above them"


def test_compute_league_standings_ranks_are_contiguous(compute_league_standings):
    matches = [{"strHomeTeam": "A", "strAwayTeam": "B", "intHomeScore": 1, "intAwayScore": 0}]
    rows = compute_league_standings(matches, {})
    assert sorted(r["intRank"] for r in rows) == [1, 2]
