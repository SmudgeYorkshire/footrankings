"""
Tests for european_2027_28.py's 3 CSV-loader functions
(_load_predicted_standings_csv / _load_position_probs_csv /
_load_predicted_cup_winners_csv) -- the fast, file-backed replacement for
what used to be a live simulate_season() run per country on every page
load (see european_predictions_core.py's own docstring). european_2027_28.py
is still a Streamlit PAGE script (it fetches live data and renders UI at
import time), so these are ast-extracted into a minimal namespace instead
of imported directly -- same technique tests/test_european_logic.py
already uses for this exact reason.
"""

import ast
import os
from pathlib import Path

import pandas as pd
import pytest

FILE_PATH = str(Path(__file__).parent.parent / "european_2027_28.py")


def _extract_function(file_path: str, func_name: str, namespace: dict) -> callable:
    src = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            exec(ast.get_source_segment(src, node), namespace)
            return namespace[func_name]
    raise AssertionError(f"{func_name} not found in {file_path}")


@pytest.fixture()
def standings_loader(monkeypatch, tmp_path):
    csv_path = tmp_path / "standings.csv"
    namespace = {"os": os, "pd": pd, "_PREDICTED_STANDINGS_CSV": str(csv_path)}
    fn = _extract_function(FILE_PATH, "_load_predicted_standings_csv", namespace)
    return fn, csv_path


@pytest.fixture()
def probs_loader(tmp_path):
    csv_path = tmp_path / "probs.csv"
    namespace = {"os": os, "pd": pd, "_POSITION_PROBS_CSV": str(csv_path)}
    fn = _extract_function(FILE_PATH, "_load_position_probs_csv", namespace)
    return fn, csv_path


@pytest.fixture()
def cup_winners_loader(tmp_path):
    csv_path = tmp_path / "cup_winners.csv"
    namespace = {"os": os, "pd": pd, "_PREDICTED_CUP_WINNERS_CSV": str(csv_path)}
    fn = _extract_function(FILE_PATH, "_load_predicted_cup_winners_csv", namespace)
    return fn, csv_path


def test_standings_loader_missing_file_returns_empty_dict(standings_loader):
    fn, _path = standings_loader
    assert fn() == {}


def test_standings_loader_groups_by_league_sorted_by_rank(standings_loader):
    fn, path = standings_loader
    pd.DataFrame([
        {"league_name": "Greek Super League 1", "intRank": 2, "strTeam": "Panathinaikos", "strBadge": "b2"},
        {"league_name": "Greek Super League 1", "intRank": 1, "strTeam": "Olympiakos Piraeus", "strBadge": "b1"},
        {"league_name": "Danish Superliga", "intRank": 1, "strTeam": "FC Copenhagen", "strBadge": "b3"},
    ]).to_csv(path, index=False)
    out = fn()
    assert [r["strTeam"] for r in out["Greek Super League 1"]] == ["Olympiakos Piraeus", "Panathinaikos"]
    assert out["Danish Superliga"][0]["strTeam"] == "FC Copenhagen"


def test_probs_loader_missing_file_returns_empty_dict(probs_loader):
    fn, _path = probs_loader
    assert fn() == {}


def test_probs_loader_pivots_into_team_by_position_matrix(probs_loader):
    fn, path = probs_loader
    pd.DataFrame([
        {"league_name": "Greek Super League 1", "strTeam": "Olympiakos Piraeus", "position": "1", "probability": 0.402},
        {"league_name": "Greek Super League 1", "strTeam": "Panathinaikos", "position": "1", "probability": 0.310},
    ]).to_csv(path, index=False)
    out = fn()
    df = out["Greek Super League 1"]
    assert df.loc["Olympiakos Piraeus", "1"] == pytest.approx(0.402)
    # Position column must stay a string (matching simulate_season()'s
    # own convention) so downstream lookups like _position_chance work
    # the same way whether this came from a live run or this CSV.
    assert list(df.columns) == ["1"]


def test_cup_winners_loader_missing_file_returns_empty_dict(cup_winners_loader):
    fn, _path = cup_winners_loader
    assert fn() == {}


def test_cup_winners_loader_keys_by_league_name(cup_winners_loader):
    fn, path = cup_winners_loader
    pd.DataFrame([
        {"league_name": "Albanian Superliga", "team": "Egnatia", "note": "predicted cup winner — domestic cup still in progress"},
    ]).to_csv(path, index=False)
    out = fn()
    assert out["Albanian Superliga"] == ("Egnatia", "predicted cup winner — domestic cup still in progress")
