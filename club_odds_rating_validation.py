"""
Validates club_odds_ratings.py's persistent odds-implied rating against
real closing bookmaker odds, same discipline as odds_validation.py (which
this reuses directly rather than duplicating): downloads football-data.co.uk's
free historical closing odds, de-vigs them, and Brier-scores predictions
built from this rating against the real market.

Runs a 3-way comparison on the SAME held-out matches:
  (a) pure Opta (today's raw rating, apply_adjustments=False)
  (b) club_rating_calibration.py's current capped 14-day-window nudge
      (today's live ratings_manager.load_ratings() default)
  (c) club_odds_ratings.py's new persistent odds-implied rating

No-leakage discipline: (c) is itself fit FROM odds, unlike (a)/(b)'s Opta
baseline, so testing it on matches it was trained on would be circular.
football-data.co.uk matches from BEFORE 2026-10-01 (this site's own
daily_odds pipeline didn't exist yet) are a clean, non-overlapping test
set -- club_odds_ratings.py could not have seen real closing-odds-informed
evidence for them. Matches from on/after 2026-10-01 are excluded from (c)'s
scoring by default (--include-recent to turn that off for a quick sanity
check, clearly labeled as a leakier number if used).

Usage:
    py club_odds_rating_validation.py
    py club_odds_rating_validation.py --league "English Premier League"
    py club_odds_rating_validation.py --seasons 2023 2024 2025
"""

import argparse

import numpy as np
import pandas as pd

from config import LEAGUES
from ratings_manager import load_ratings
from simulator import fixture_odds
from odds_validation import (
    FOOTBALL_DATA_LEAGUES,
    fetch_matches,
    match_team_name,
    devig,
    brier,
    DEFAULT_SEASONS,
)
from club_odds_ratings import RATINGS_OUT_PATH

PIPELINE_START_DATE = "2026-10-01"


def _load_odds_implied_ratings(league_id: str) -> pd.DataFrame:
    """Just this ONE league's slice of club_odds_ratings.py's (league_id,
    team)-keyed state -- NOT the whole file. That file deliberately scopes
    by league precisely because the same exact team-name string can belong
    to two unrelated clubs in different leagues (e.g. England's vs
    Belarus's "Arsenal", confirmed live 2026-11-04); handing fixture_odds()
    the full cross-league file here would silently resurrect that exact
    collision for this validation."""
    if not RATINGS_OUT_PATH.exists():
        return pd.DataFrame(columns=["team", "alias", "opta_rating"])
    df = pd.read_csv(RATINGS_OUT_PATH, dtype=str)
    df = df[df["league_id"] == str(league_id)]
    df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
    df["alias"] = df["alias"].fillna("")
    return df[["team", "alias", "opta_rating"]]


def _brier_for(ratings_df: pd.DataFrame, home_advantage: float, scored: pd.DataFrame) -> float | None:
    if scored.empty or ratings_df.empty:
        return None
    fixtures = [{"strHomeTeam": r["home_m"], "strAwayTeam": r["away_m"]} for _, r in scored.iterrows()]
    try:
        model_odds = fixture_odds(fixtures, ratings_df, home_advantage=home_advantage)
    except Exception:
        return None
    briers = [
        brier(mo["home_win"], mo["draw"], mo["away_win"], row["ftr"])
        for (_, row), mo in zip(scored.iterrows(), model_odds)
    ]
    return float(np.mean(briers))


def validate_league(league_name: str, seasons: list[int], include_recent: bool) -> dict | None:
    cfg = LEAGUES[league_name]
    ratings_id = cfg.get("tsdb_id", cfg["id"])
    home_advantage = cfg.get("home_advantage", 1.20)

    opta_ratings = load_ratings(ratings_id, [], apply_adjustments=False)
    live_ratings = load_ratings(ratings_id, [])  # today's apply_adjustments=True default
    odds_ratings = _load_odds_implied_ratings(ratings_id)

    matches = fetch_matches(league_name, seasons)
    if matches.empty:
        return None

    # football-data.co.uk's "Date" column is DD/MM/YYYY (confirmed against
    # a real cached file) -- must be parsed with dayfirst=True, a plain
    # string compare against PIPELINE_START_DATE's ISO format below would
    # silently misorder every match.
    matches["date_parsed"] = pd.to_datetime(matches["date"], dayfirst=True, errors="coerce")

    unmatched: set[str] = set()
    matches["home_m"] = matches["home"].apply(lambda n: match_team_name(n, opta_ratings, unmatched))
    matches["away_m"] = matches["away"].apply(lambda n: match_team_name(n, opta_ratings, unmatched))
    scored = matches.dropna(subset=["home_m", "away_m", "date_parsed"])
    if scored.empty:
        return {"league": league_name, "n": 0, "n_held_out": 0, "unmatched": unmatched}

    market_briers = []
    for _, row in scored.iterrows():
        mh, md, ma = devig(row["avg_h"], row["avg_d"], row["avg_a"])
        market_briers.append(brier(mh, md, ma, row["ftr"]))
    market_brier = float(np.mean(market_briers))

    opta_brier = _brier_for(opta_ratings, home_advantage, scored)
    live_brier = _brier_for(live_ratings, home_advantage, scored)

    # Held out: matches strictly before this site's own daily_odds pipeline
    # existed -- club_odds_ratings.py could not have trained on them. See
    # module docstring.
    held_out = scored if include_recent else scored[scored["date_parsed"] < pd.Timestamp(PIPELINE_START_DATE)]
    odds_brier = _brier_for(odds_ratings, home_advantage, held_out) if not held_out.empty else None

    return {
        "league": league_name,
        "n": len(scored),
        "n_held_out": len(held_out),
        "market_brier": market_brier,
        "opta_brier": opta_brier,
        "live_brier": live_brier,
        "odds_brier": odds_brier,
        "unmatched": unmatched,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default=None)
    ap.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    ap.add_argument("--include-recent", action="store_true",
                     help="Also score the new odds rating on matches it may have trained on "
                          "(leakier number -- for a quick sanity check only, not a real result).")
    args = ap.parse_args()

    leagues = [args.league] if args.league else list(FOOTBALL_DATA_LEAGUES.keys())

    results = []
    all_unmatched: dict[str, set[str]] = {}
    for name in leagues:
        r = validate_league(name, args.seasons, args.include_recent)
        if r is None:
            print(f"{name:32s}  no data")
            continue
        if r.get("unmatched"):
            all_unmatched[name] = r["unmatched"]
        if r["n"] == 0:
            print(f"{name:32s}  0 matches scored (all names unmatched)")
            continue
        def _fmt(v):
            return f"{v:.4f}" if v is not None else "   n/a"
        print(
            f"{name:32s}  n={r['n']:5d}  market={_fmt(r['market_brier'])}  "
            f"opta={_fmt(r['opta_brier'])}  live(nudge)={_fmt(r['live_brier'])}  "
            f"odds-implied={_fmt(r['odds_brier'])} (n_held_out={r['n_held_out']})"
        )
        results.append(r)

    scored_results = [r for r in results if r["n"] > 0]
    if scored_results:
        print("-" * 110)
        for key, label in [("market_brier", "market"), ("opta_brier", "opta"), ("live_brier", "live (nudge)")]:
            vals = [(r[key], r["n"]) for r in scored_results if r[key] is not None]
            if vals:
                w = sum(v * n for v, n in vals) / sum(n for _, n in vals)
                print(f"OVERALL (n-weighted) {label:14s} n={sum(n for _, n in vals):5d}  brier={w:.4f}")
        held_vals = [(r["odds_brier"], r["n_held_out"]) for r in scored_results if r["odds_brier"] is not None]
        if held_vals:
            w = sum(v * n for v, n in held_vals) / sum(n for _, n in held_vals)
            print(f"OVERALL (n-weighted) odds-implied   n={sum(n for _, n in held_vals):5d}  brier={w:.4f}  "
                  f"({'INCLUDING recent (leakier)' if args.include_recent else 'held-out only, pre-pipeline matches'})")
        else:
            print("odds-implied rating: no held-out matches scored for it yet "
                  "(ratings/club_odds_implied_ratings.csv may not exist or has no pre-2026-10-01 coverage).")

    if all_unmatched:
        print("\nUnmatched team names (add to odds_validation.TEAM_NAME_OVERRIDES):")
        for league, names in all_unmatched.items():
            print(f"  {league}: {sorted(names)}")


if __name__ == "__main__":
    main()
