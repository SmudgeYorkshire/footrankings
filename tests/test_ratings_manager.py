"""
Tests for ratings_manager.py's I/O safety: a malformed rating cell must
not crash the simulator with a NaN, and an existing-but-malformed CSV
must not be silently overwritten by a page load.
"""

import pandas as pd
import pytest

import ratings_manager as rm


@pytest.fixture()
def isolated_ratings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RATINGS_DIR", tmp_path)
    return tmp_path


def _standings(teams):
    return [
        {"strTeam": t, "intPlayed": 5, "intGoalDifference": i, "intGoalsFor": 10 + i}
        for i, t in enumerate(teams)
    ]


def test_load_ratings_fills_nan_cell_with_default(isolated_ratings_dir):
    csv_path = isolated_ratings_dir / "1.csv"
    pd.DataFrame({"team": ["A", "B"], "alias": ["", ""],
                  "opta_rating": ["80.0", "not_a_number"]}).to_csv(csv_path, index=False)

    df = rm.load_ratings(1, _standings(["A", "B"]))
    assert not df["opta_rating"].isna().any()
    assert df.loc[df["team"] == "B", "opta_rating"].iloc[0] == rm.DEFAULT_OPTA
    assert df.loc[df["team"] == "A", "opta_rating"].iloc[0] == 80.0


def test_load_ratings_does_not_overwrite_malformed_file(isolated_ratings_dir):
    csv_path = isolated_ratings_dir / "2.csv"
    pd.DataFrame({"foo": ["bar"], "baz": [1]}).to_csv(csv_path, index=False)
    original = csv_path.read_bytes()

    df = rm.load_ratings(2, _standings(["A", "B"]))
    assert csv_path.read_bytes() == original, "malformed file must be left untouched"
    assert len(df) == 2


def test_load_ratings_seeds_a_new_file_when_none_exists(isolated_ratings_dir):
    csv_path = isolated_ratings_dir / "3.csv"
    assert not csv_path.exists()

    rm.load_ratings(3, _standings(["A", "B"]))
    assert csv_path.exists(), "a brand-new league should still get a seeded ratings file"


def test_defaults_from_standings_persist_false_does_not_write(isolated_ratings_dir):
    csv_path = isolated_ratings_dir / "4.csv"
    result = rm._defaults_from_standings(_standings(["A", "B"]), csv_path, persist=False)
    assert not csv_path.exists()
    assert len(result) == 2


def test_defaults_from_standings_persist_true_writes(isolated_ratings_dir):
    csv_path = isolated_ratings_dir / "5.csv"
    rm._defaults_from_standings(_standings(["A", "B"]), csv_path, persist=True)
    assert csv_path.exists()


def test_defaults_from_standings_scales_into_expected_range():
    standings = _standings(["A", "B", "C"])
    df = rm._defaults_from_standings(standings, None, persist=False)
    assert (df["opta_rating"] >= 68.0).all()
    assert (df["opta_rating"] <= 82.0).all()


def test_build_lookup_maps_both_team_and_alias():
    ratings = pd.DataFrame({"team": ["Man City"], "alias": ["Manchester City"], "opta_rating": [95.0]})
    lookup = rm.build_lookup(ratings)
    assert lookup["Man City"] == 95.0
    assert lookup["Manchester City"] == 95.0
