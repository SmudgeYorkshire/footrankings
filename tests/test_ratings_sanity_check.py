"""
Tests for ratings_sanity_check.py -- each check exercised against small
synthetic fixtures in a temp directory (same monkeypatching pattern
tests/test_club_odds_ratings.py and tests/test_club_outright_odds_
calibration.py already use), never touching real repo data.
"""

import csv

import pandas as pd
import pytest

import club_odds_ratings as cor
import ratings_sanity_check as rsc


@pytest.fixture()
def isolated_pipeline(tmp_path, monkeypatch):
    """A temp ledger + state file, and a synthetic single domestic league
    (no European competitions -- keeps _true_n_updates_by_key's domestic
    branch exercised without needing to also fake club_odds_ratings.
    _load_tracked_ratings_with_source's own cross-league scan)."""
    ratings_dir = tmp_path / "ratings"
    ratings_dir.mkdir()
    (ratings_dir / "100.csv").write_text(
        "team,alias,opta_rating\nAlpha FC,,90.0\nBeta United,,85.0\n", encoding="utf-8",
    )
    leagues = {"Test League": {"id": 1, "tsdb_id": 100, "country": "Testland", "flag": "\U0001F3F3"}}
    monkeypatch.setattr(rsc, "LEAGUES", leagues)
    monkeypatch.setattr(rsc, "LEAGUES_TIER2", {})
    monkeypatch.setattr(rsc, "EUROPEAN_COMPETITIONS", {})
    monkeypatch.setattr(cor, "LEDGER_PATH", tmp_path / "ledger.csv")
    monkeypatch.setattr(cor, "RATINGS_OUT_PATH", tmp_path / "state.csv")
    monkeypatch.chdir(tmp_path)
    return leagues


def _write_ledger(rows: list[tuple]) -> None:
    with open(cor.LEDGER_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["league", "home_team", "away_team", "commence_time"])
        w.writerows(rows)


def _write_state(entries: dict) -> None:
    cor._save_state(entries)


# ---------------------------------------------------------------------------
# _check_ledger_duplicates
# ---------------------------------------------------------------------------

def test_ledger_duplicates_clean_ledger_no_issues(isolated_pipeline):
    _write_ledger([
        ("Test League", "Alpha FC", "Beta United", "2026-10-10T15:00:00+00:00"),
        ("Test League", "Beta United", "Alpha FC", "2026-10-17T15:00:00+00:00"),
    ])
    assert rsc._check_ledger_duplicates() == []


def test_ledger_duplicates_catches_a_planted_duplicate(isolated_pipeline):
    key = ("Test League", "Alpha FC", "Beta United", "2026-10-10T15:00:00+00:00")
    _write_ledger([key, key, key])
    issues = rsc._check_ledger_duplicates()
    assert len(issues) == 1
    assert "Alpha FC vs Beta United" in issues[0]
    assert "3x" in issues[0]


# ---------------------------------------------------------------------------
# _check_n_updates_accuracy
# ---------------------------------------------------------------------------

def test_n_updates_accuracy_clean_state_no_issues(isolated_pipeline):
    _write_ledger([
        ("Test League", "Alpha FC", "Beta United", "2026-10-10T15:00:00+00:00"),
        ("Test League", "Beta United", "Alpha FC", "2026-10-17T15:00:00+00:00"),
    ])
    _write_state({
        ("100", "Alpha FC"): {"alias": "", "rating": 92.0, "seed": 90.0, "n_updates": 2, "last_updated": "x"},
        ("100", "Beta United"): {"alias": "", "rating": 84.0, "seed": 85.0, "n_updates": 2, "last_updated": "x"},
    })
    assert rsc._check_n_updates_accuracy() == []


def test_n_updates_accuracy_catches_confidence_tier_flip(isolated_pipeline):
    # Ledger only truly supports 1 match for Alpha FC, but its state
    # claims 9 (>= N_FULL_CONFIDENCE=6) -- exactly the real bug's
    # most damaging symptom: treated as fully confident on thin evidence.
    _write_ledger([("Test League", "Alpha FC", "Beta United", "2026-10-10T15:00:00+00:00")])
    _write_state({
        ("100", "Alpha FC"): {"alias": "", "rating": 99.0, "seed": 90.0, "n_updates": 9, "last_updated": "x"},
    })
    issues = rsc._check_n_updates_accuracy()
    assert len(issues) == 1
    assert "CONFIDENCE-TIER FLIP" in issues[0]
    assert "Alpha FC" in issues[0]
    assert "n_updates=9" in issues[0]
    assert "supports 1" in issues[0]


def test_n_updates_accuracy_non_tier_flip_mismatch_reported_separately(isolated_pipeline):
    # Both the stored and true counts are below N_FULL_CONFIDENCE=6 --
    # still a real mismatch worth knowing about, but doesn't change the
    # live blend's confidence weighting, so it's reported as a count,
    # not called out individually the way a tier flip is.
    _write_ledger([("Test League", "Alpha FC", "Beta United", "2026-10-10T15:00:00+00:00")])
    _write_state({
        ("100", "Alpha FC"): {"alias": "", "rating": 91.0, "seed": 90.0, "n_updates": 3, "last_updated": "x"},
    })
    issues = rsc._check_n_updates_accuracy()
    assert len(issues) == 1
    assert "CONFIDENCE-TIER FLIP" not in issues[0]
    assert "1 other club" in issues[0]


# ---------------------------------------------------------------------------
# _check_orphaned_keys
# ---------------------------------------------------------------------------

def test_orphaned_keys_clean_state_no_issues(isolated_pipeline):
    _write_state({
        ("100", "Alpha FC"): {"alias": "", "rating": 90.0, "seed": 90.0, "n_updates": 1, "last_updated": "x"},
    })
    assert rsc._check_orphaned_keys() == []


def test_orphaned_keys_catches_a_name_that_matches_nothing(isolated_pipeline):
    # Mirrors the real bug: a nudge keyed by a competition field's own
    # display name ("Alpha Football Club") instead of the ratings CSV's
    # canonical "team" column ("Alpha FC").
    _write_state({
        ("100", "Alpha Football Club"): {"alias": "", "rating": 90.0, "seed": 90.0, "n_updates": 1, "last_updated": "x"},
    })
    issues = rsc._check_orphaned_keys()
    assert len(issues) == 1
    assert "ORPHANED STATE KEY" in issues[0]
    assert "Alpha Football Club" in issues[0]


def test_orphaned_keys_skips_euro_fallback_bucket(isolated_pipeline):
    _write_state({
        ("EURO:Champions League", "Some Club"): {"alias": "", "rating": 90.0, "seed": 90.0, "n_updates": 1, "last_updated": "x"},
    })
    assert rsc._check_orphaned_keys() == []


# ---------------------------------------------------------------------------
# _check_display_freshness
# ---------------------------------------------------------------------------

def _write_power_rankings(rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(rsc.POWER_RANKINGS_PATH, index=False)


def test_display_freshness_missing_file_is_its_own_issue(isolated_pipeline, monkeypatch):
    monkeypatch.setattr(rsc, "POWER_RANKINGS_PATH", "does_not_exist_1000.csv")
    issues = rsc._check_display_freshness()
    assert len(issues) == 1
    assert "does not exist" in issues[0]


def test_display_freshness_clean_state_no_issues(isolated_pipeline, monkeypatch):
    monkeypatch.setattr(rsc, "POWER_RANKINGS_PATH", "power_rankings.csv")
    _write_state({
        ("100", "Alpha FC"): {"alias": "", "rating": 92.5, "seed": 90.0, "n_updates": 3, "last_updated": "x"},
    })
    _write_power_rankings([
        {"team": "Alpha FC", "tracked_league": "\U0001F3F3 Test League", "odds_implied_rating": 92.5, "odds_n_updates": 3},
    ])
    assert rsc._check_display_freshness() == []


def test_display_freshness_catches_a_stale_row(isolated_pipeline, monkeypatch):
    monkeypatch.setattr(rsc, "POWER_RANKINGS_PATH", "power_rankings.csv")
    _write_state({
        ("100", "Alpha FC"): {"alias": "", "rating": 97.0, "seed": 90.0, "n_updates": 5, "last_updated": "x"},
    })
    _write_power_rankings([
        {"team": "Alpha FC", "tracked_league": "\U0001F3F3 Test League", "odds_implied_rating": 92.5, "odds_n_updates": 3},
    ])
    issues = rsc._check_display_freshness()
    assert len(issues) == 1
    assert "STALE DISPLAY" in issues[0]
    assert "Alpha FC" in issues[0]
