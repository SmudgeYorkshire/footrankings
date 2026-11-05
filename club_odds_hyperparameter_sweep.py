"""
Sweeps club_odds_ratings.py's four match-level fitting hyperparameters
(LEARNING_RATE, L2_SHRINKAGE, EPOCHS, MIN_BOOKMAKERS_FOR_FULL_WEIGHT --
all copied from club_rating_calibration.py's own values as a starting
point when club_odds_ratings.py was built, never independently
validated) against the same held-out Brier benchmark club_odds_rating_
validation.py and club_combined_rating_validation.py already use, the
same way N_FULL_CONFIDENCE was swept and found to do better at 6 than
its original guess of 12.

Unlike N_FULL_CONFIDENCE (a downstream blend weight applied to an
already-fitted rating), these four control the FITTING process itself --
there's no shortcut through the already-committed ratings/club_odds_
implied_ratings.csv. This script REPLAYS club_odds_ratings.py's own real
fixture history (club_odds_ratings._load_all_tracked_observations(),
same freshest-capture-wins dedup) chronologically, grouped into daily
batches exactly the way main() itself processes new evidence day to day,
starting every team from its raw Opta rating (no persisted state exists
for a fresh replay) -- one full replay per candidate hyperparameter
value, scored on the SAME held-out pre-2026-10-01 football-data.co.uk
matches club_odds_rating_validation.py uses (club_odds_ratings.py could
not have trained on them either way).

Scoped to the 21 leagues odds_validation.FOOTBALL_DATA_LEAGUES actually
has held-out data for -- the only leagues this sweep can meaningfully
score, and also the only leagues club_odds_rating_validation.py /
club_combined_rating_validation.py themselves cover, so results stay
directly comparable to those. European competitions are out of scope
here for the same reason football-data.co.uk doesn't cover them.

Sweeps one parameter at a time (holding the other three at their current
shipped values), not a full joint grid search -- a 4-way grid at 5
candidates each would mean 625 full replays; this is standard practice
for this kind of hyperparameter check (the same one-dimension-at-a-time
approach club_combined_rating_validation.py's own N_FULL_CONFIDENCE
sweep used) and is clearly labeled as such in the output, not presented
as a joint optimum.

Usage:
    py club_odds_hyperparameter_sweep.py
    py club_odds_hyperparameter_sweep.py --param learning_rate
    py club_odds_hyperparameter_sweep.py --league "English Premier League"
"""

import argparse
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

from config import LEAGUES
import club_odds_ratings as cor
from odds_validation import FOOTBALL_DATA_LEAGUES, fetch_matches, match_team_name, brier, DEFAULT_SEASONS
from simulator import fixture_odds

PIPELINE_START_DATE = "2026-10-01"

# Current shipped values -- the baseline every sweep holds the OTHER
# three parameters at while varying one.
BASELINE = {
    "learning_rate": cor.LEARNING_RATE,
    "l2_shrinkage": cor.L2_SHRINKAGE,
    "epochs": cor.EPOCHS,
    "min_bookmakers": cor.MIN_BOOKMAKERS_FOR_FULL_WEIGHT,
}

CANDIDATES = {
    "learning_rate": [0.6, 0.9, 1.2, 1.6, 2.0],
    "l2_shrinkage": [0.0, 0.01, 0.03, 0.06, 0.10],
    "epochs": [10, 20, 40, 60, 80],
    "min_bookmakers": [3, 4, 5, 7, 9],
}


def _load_league_observations(league_name: str) -> list[dict]:
    all_obs = cor._load_all_tracked_observations()
    return [o for o in all_obs if o.get("league") == league_name]


def _replay_fit(
    league_name: str, cfg: dict, learning_rate: float, l2_shrinkage: float,
    epochs: int, min_bookmakers: float,
) -> dict[str, float]:
    """Chronologically replay one league's full real fixture history
    through _fit_persistent, grouped into daily batches (same
    granularity main() itself uses), starting every team from its raw
    Opta rating. Returns the final {team: rating} dict.

    LEARNING_RATE/L2_SHRINKAGE/MIN_BOOKMAKERS_FOR_FULL_WEIGHT are read as
    module globals inside _fit_persistent/its own _weight() closure, not
    function parameters -- monkeypatched on the module for the duration
    of this one replay (restored in a finally block) rather than
    reimplementing the fit's own internals here."""
    ratings_id = cfg.get("tsdb_id", cfg["id"])
    home_advantage = cfg.get("home_advantage", 1.20)
    raw_ratings_df = cor.load_ratings(ratings_id, [], apply_adjustments=False)

    obs = _load_league_observations(league_name)
    resolved = cor._resolve_observations(league_name, raw_ratings_df, obs)
    if not resolved:
        return {}

    by_day: dict[str, list[dict]] = defaultdict(list)
    for o in resolved:
        day = o["commence_time"][:10]
        by_day[day].append(o)

    original = (cor.LEARNING_RATE, cor.L2_SHRINKAGE, cor.MIN_BOOKMAKERS_FOR_FULL_WEIGHT)
    cor.LEARNING_RATE = learning_rate
    cor.L2_SHRINKAGE = l2_shrinkage
    cor.MIN_BOOKMAKERS_FOR_FULL_WEIGHT = min_bookmakers
    try:
        current_ratings: dict[str, float] = {}
        for day in sorted(by_day):
            day_resolved = by_day[day]
            updates = cor._fit_persistent(raw_ratings_df, home_advantage, day_resolved, current_ratings, epochs=epochs)
            current_ratings.update(updates)
    finally:
        cor.LEARNING_RATE, cor.L2_SHRINKAGE, cor.MIN_BOOKMAKERS_FOR_FULL_WEIGHT = original

    return current_ratings


def _ratings_df_from_dict(raw_ratings_df: pd.DataFrame, ratings: dict[str, float]) -> pd.DataFrame:
    out = raw_ratings_df.copy()
    out["opta_rating"] = out.apply(lambda r: ratings.get(r["team"], r["opta_rating"]), axis=1)
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


def _held_out_matches(league_name: str, seasons: list[int], raw_ratings_df: pd.DataFrame) -> pd.DataFrame:
    matches = fetch_matches(league_name, seasons)
    if matches.empty:
        return matches
    matches["date_parsed"] = pd.to_datetime(matches["date"], dayfirst=True, errors="coerce")
    unmatched: set[str] = set()
    matches["home_m"] = matches["home"].apply(lambda n: match_team_name(n, raw_ratings_df, unmatched))
    matches["away_m"] = matches["away"].apply(lambda n: match_team_name(n, raw_ratings_df, unmatched))
    scored = matches.dropna(subset=["home_m", "away_m", "date_parsed"])
    return scored[scored["date_parsed"] < pd.Timestamp(PIPELINE_START_DATE)]


def sweep_param(param: str, league_names: list[str], seasons: list[int]) -> None:
    candidates = CANDIDATES[param]
    print(f"\n=== Sweeping {param} (baseline={BASELINE[param]}), others held at {BASELINE} ===")

    per_league_held_out: dict[str, pd.DataFrame] = {}
    per_league_raw: dict[str, pd.DataFrame] = {}
    for name in league_names:
        cfg = LEAGUES[name]
        raw = cor.load_ratings(cfg.get("tsdb_id", cfg["id"]), [], apply_adjustments=False)
        per_league_raw[name] = raw
        per_league_held_out[name] = _held_out_matches(name, seasons, raw)

    results: dict = {c: [] for c in candidates}  # candidate -> [(brier, n), ...]
    for name in league_names:
        held_out = per_league_held_out[name]
        if held_out.empty:
            continue
        cfg = LEAGUES[name]
        home_advantage = cfg.get("home_advantage", 1.20)
        row = f"{name:32s} n={len(held_out):5d}  "
        for c in candidates:
            kwargs = dict(BASELINE)
            kwargs[param] = c
            ratings = _replay_fit(name, cfg, **kwargs)
            ratings_df = _ratings_df_from_dict(per_league_raw[name], ratings)
            b = _brier_for(ratings_df, home_advantage, held_out)
            if b is not None:
                results[c].append((b, len(held_out)))
            row += f"{param}={c}:{b:.4f}  " if b is not None else f"{param}={c}:n/a  "
        print(row)

    print("-" * 100)
    for c in candidates:
        vals = results[c]
        if not vals:
            print(f"OVERALL (n-weighted) {param}={c!s:8s}  no data")
            continue
        total_n = sum(n for _, n in vals)
        w = sum(b * n for b, n in vals) / total_n
        marker = "  <- current" if c == BASELINE[param] else ""
        print(f"OVERALL (n-weighted) {param}={c!s:8s}  n={total_n:6d}  brier={w:.4f}{marker}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default=None)
    ap.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    ap.add_argument("--param", choices=list(CANDIDATES.keys()), default=None,
                     help="sweep just this one parameter instead of all four")
    args = ap.parse_args()

    leagues = [args.league] if args.league else list(FOOTBALL_DATA_LEAGUES.keys())
    params = [args.param] if args.param else list(CANDIDATES.keys())

    print(f"Started {datetime.now().isoformat(timespec='seconds')}")
    for param in params:
        sweep_param(param, leagues, args.seasons)
    print(f"\nFinished {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
