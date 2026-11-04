"""
Sweeps build_club_power_rankings.py's N_FULL_CONFIDENCE (the number of
real odds-implied observations a club needs before the Combined Strength
Ranking trusts the odds signal as much as Opta) against the same held-out
Brier benchmark club_odds_rating_validation.py already uses, to check
whether 12 (the current, explicitly-provisional value -- see that
constant's own comment) is actually a good choice, or whether a lower
value would score as well or better.

Reuses the exact same held-out discipline: football-data.co.uk matches
from BEFORE 2026-10-01 (this site's own daily_odds pipeline didn't exist
yet), so neither the odds-implied rating nor, by extension, the combined
rating could have trained on them.

The combined rating formula mirrors build_club_power_rankings.py's own
(delta-from-the-club's-own-raw-Opta-baseline, confidence-weighted) exactly,
just without that script's GLOBAL cross-league rescale -- not needed here
since club_odds_implied_ratings.csv is already per-league scoped and
odds_validation's Brier scoring works in probability space, not on any
particular rating scale.

Usage:
    py club_combined_rating_validation.py
    py club_combined_rating_validation.py --league "English Premier League"
    py club_combined_rating_validation.py --n-values 2 4 6 8 10 12 16 20
"""

import argparse

import numpy as np
import pandas as pd

from config import LEAGUES
from ratings_manager import load_ratings
from simulator import fixture_odds
from odds_validation import FOOTBALL_DATA_LEAGUES, fetch_matches, match_team_name, brier, DEFAULT_SEASONS
from club_odds_ratings import RATINGS_OUT_PATH

PIPELINE_START_DATE = "2026-10-01"
DEFAULT_N_VALUES = [2, 3, 4, 5, 6, 8, 10, 12, 16, 20]


def _load_odds_implied_with_n(league_id: str) -> pd.DataFrame:
    """This league's (league_id, team)-scoped slice, WITH n_updates --
    same scoping discipline as club_odds_rating_validation.py's own
    _load_odds_implied_ratings (never hand the whole cross-league file to
    anything -- see that function's own docstring for the collision risk
    this avoids)."""
    if not RATINGS_OUT_PATH.exists():
        return pd.DataFrame(columns=["team", "opta_rating", "n_updates"])
    df = pd.read_csv(RATINGS_OUT_PATH, dtype=str)
    df = df[df["league_id"] == str(league_id)]
    df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
    df["n_updates"] = pd.to_numeric(df["n_updates"], errors="coerce").fillna(0).astype(int)
    return df[["team", "opta_rating", "n_updates"]].rename(columns={"opta_rating": "odds_rating"})


def _combined_ratings_for_n(
    live_ratings: pd.DataFrame, odds_with_n: pd.DataFrame, n_full_confidence: int,
) -> pd.DataFrame:
    """Straight linear interpolation between live_ratings (opta + today's
    capped daily nudge) and the odds-implied rating, weighted by
    min(1, n_updates / n_full_confidence): combined = live*(1-conf) +
    odds*conf. A club with no odds row at all keeps its live_rating
    unchanged (confidence implicitly 0) -- the same "Opta covers the gap"
    fallback build_club_power_rankings.py itself implements.

    NOT "live + (odds - raw_opta) * confidence" -- an earlier version of
    this (and, found the same day, build_club_power_rankings.py's own
    shipped Combined Elo) used that delta-from-raw form, which does NOT
    reduce to the pure odds-implied rating at confidence=1: live already
    includes the nudge, so adding (odds - raw) on top leaves the nudge
    double-counted on top of the full odds-implied signal (confirmed:
    live=92.5, odds=95.0 -> old formula gives 97.5 at full confidence,
    not 95.0). Straight interpolation correctly reduces to live_rating at
    confidence=0 and exactly odds_rating at confidence=1, with no
    double-counting in between."""
    odds_lookup = dict(zip(odds_with_n["team"], zip(odds_with_n["odds_rating"], odds_with_n["n_updates"])))

    out = live_ratings.copy()

    def _combined(row):
        team = row["team"]
        if team not in odds_lookup:
            return row["opta_rating"]
        odds_rating, n_updates = odds_lookup[team]
        if pd.isna(odds_rating):
            return row["opta_rating"]
        confidence = min(1.0, n_updates / n_full_confidence)
        return row["opta_rating"] * (1.0 - confidence) + odds_rating * confidence

    out["opta_rating"] = out.apply(_combined, axis=1)
    return out


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


def validate_league(league_name: str, seasons: list[int], n_values: list[int]) -> dict | None:
    cfg = LEAGUES[league_name]
    ratings_id = cfg.get("tsdb_id", cfg["id"])
    home_advantage = cfg.get("home_advantage", 1.20)

    opta_ratings = load_ratings(ratings_id, [], apply_adjustments=False)
    live_ratings = load_ratings(ratings_id, [])
    odds_with_n = _load_odds_implied_with_n(ratings_id)

    matches = fetch_matches(league_name, seasons)
    if matches.empty:
        return None
    matches["date_parsed"] = pd.to_datetime(matches["date"], dayfirst=True, errors="coerce")

    unmatched: set[str] = set()
    matches["home_m"] = matches["home"].apply(lambda n: match_team_name(n, opta_ratings, unmatched))
    matches["away_m"] = matches["away"].apply(lambda n: match_team_name(n, opta_ratings, unmatched))
    scored = matches.dropna(subset=["home_m", "away_m", "date_parsed"])
    held_out = scored[scored["date_parsed"] < pd.Timestamp(PIPELINE_START_DATE)]
    if held_out.empty:
        return {"league": league_name, "n_held_out": 0}

    live_brier = _brier_for(live_ratings, home_advantage, held_out)

    briers_by_n = {}
    for n in n_values:
        combined = _combined_ratings_for_n(live_ratings, odds_with_n, n)
        briers_by_n[n] = _brier_for(combined, home_advantage, held_out)

    return {
        "league": league_name,
        "n_held_out": len(held_out),
        "live_brier": live_brier,
        "briers_by_n": briers_by_n,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default=None)
    ap.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    ap.add_argument("--n-values", nargs="+", type=int, default=DEFAULT_N_VALUES)
    args = ap.parse_args()

    leagues = [args.league] if args.league else list(FOOTBALL_DATA_LEAGUES.keys())

    results = []
    for name in leagues:
        r = validate_league(name, args.seasons, args.n_values)
        if r is None or r["n_held_out"] == 0:
            print(f"{name:32s}  no held-out data")
            continue
        row = f"{name:32s}  n={r['n_held_out']:5d}  live(nudge)={r['live_brier']:.4f}  "
        row += "  ".join(
            f"N={n}:{r['briers_by_n'][n]:.4f}" if r["briers_by_n"][n] is not None else f"N={n}:n/a"
            for n in args.n_values
        )
        print(row)
        results.append(r)

    if results:
        print("-" * 140)
        total_n = sum(r["n_held_out"] for r in results)
        w_live = sum(r["live_brier"] * r["n_held_out"] for r in results) / total_n
        print(f"OVERALL (n-weighted) n={total_n:6d}  live(nudge)={w_live:.4f}")
        for n in args.n_values:
            vals = [(r["briers_by_n"][n], r["n_held_out"]) for r in results if r["briers_by_n"][n] is not None]
            if vals:
                w = sum(v * cnt for v, cnt in vals) / sum(cnt for _, cnt in vals)
                print(f"OVERALL (n-weighted) N_FULL_CONFIDENCE={n:3d}  n={sum(cnt for _, cnt in vals):6d}  brier={w:.4f}")


if __name__ == "__main__":
    main()
