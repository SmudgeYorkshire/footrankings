"""
Automated, daily version of nl_odds_calibration.py's idea -- fit a small
per-team rating adjustment from real bookmaker odds -- but for the 54
tracked club leagues, sourced automatically from fetch_daily_odds.py's
output instead of a hand-typed observation list, and using the site's own
real Poisson match model (simulator.fixture_odds) to compare against the
market instead of a generic Elo-expectancy approximation, since that's
exactly what will actually run once this adjustment is live.

Refits from scratch every run (today's live odds vs. today's raw Opta
baseline) rather than accumulating on top of yesterday's adjustment -- this
is what keeps it from compounding into runaway drift (the "circular
feedback" risk): each day's adjustment is independent, not a moving target
chasing its own previous output.

Writes ratings/club_rating_adjustments.csv (team, adjustment), which
ratings_manager.load_ratings() overlays onto every league's raw ratings the
same way nations_league_simulator.load_nl_ratings() already overlays
nations_league_elo_adjustments.csv.

Usage: py club_rating_calibration.py [--date YYYY-MM-DD]
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from config import LEAGUES
from ratings_manager import load_ratings
from simulator import fixture_odds
from update_ratings_from_opta import _normalize, fuzzy_token_match

DAILY_ODDS_DIR = Path("odds_coverage") / "daily_odds"
OUT_PATH = Path("ratings") / "club_rating_adjustments.csv"

LEARNING_RATE = 1.2     # opta-rating points per unit of probability error (0-100 scale, not Elo)
L2_SHRINKAGE = 0.03     # per-epoch pull toward 0
EPOCHS = 40
ADJUSTMENT_CAP = 10.0   # opta ratings only span ~23-100 -- a 10pt swing is already large


def _resolve_team(name: str, ratings_df: pd.DataFrame) -> str | None:
    """Match an odds provider's team name against a league's own ratings_df
    (its "team" or "alias" column, same convention ratings_manager.
    build_lookup() uses everywhere else). Three tiers, loosest last:
    exact match, normalized (diacritics/club-suffix-stripped) exact match,
    then a normalized token-subset match (e.g. "Inter Milan" ~ alias
    "Inter", "CA Osasuna" ~ "Real Racing Club de Santander" won't -- but
    "Atalanta BC" ~ "Atalanta" will, since {atalanta} is a subset of
    {atalanta, bc}). The subset check is only run within one league's own
    ~18-20 team roster, so the false-positive risk of a loose match is low.
    Returns the ratings_df "team" value (the row's canonical key) or None.
    """
    for _, row in ratings_df.iterrows():
        if name == row["team"] or name == row.get("alias", ""):
            return row["team"]
    norm_name = _normalize(name)
    for _, row in ratings_df.iterrows():
        if norm_name == _normalize(row["team"]) or norm_name == _normalize(str(row.get("alias", ""))):
            return row["team"]
    for _, row in ratings_df.iterrows():
        if fuzzy_token_match(name, (row["team"], str(row.get("alias", "")))):
            return row["team"]
    return None


def fit_league(league_name: str, cfg: dict, observations: list[dict]) -> dict[str, float]:
    # apply_adjustments=False: fit against the true raw Opta baseline, never
    # against an already-adjusted value -- see ratings_manager.load_ratings's
    # own docstring for why (refit-from-scratch, not accumulate).
    ratings_df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [], apply_adjustments=False)
    home_advantage = cfg.get("home_advantage", 1.20)

    resolved = []
    unresolved = set()
    for o in observations:
        home = _resolve_team(o["home_team"], ratings_df)
        away = _resolve_team(o["away_team"], ratings_df)
        if home and away:
            resolved.append({**o, "home_team": home, "away_team": away})
        else:
            unresolved.add((o["home_team"], o["away_team"]))
    for h, a in unresolved:
        print(f"  [{league_name}] WARNING: couldn't resolve '{h}' vs '{a}' to a tracked team", file=sys.stderr)
    if not resolved:
        return {}

    adj: dict[str, float] = {t: 0.0 for t in ratings_df["team"]}
    for _ in range(EPOCHS):
        working = ratings_df.copy()
        working["opta_rating"] = working.apply(lambda r: r["opta_rating"] + adj.get(r["team"], 0.0), axis=1)
        for o in resolved:
            model = fixture_odds(
                [{"strHomeTeam": o["home_team"], "strAwayTeam": o["away_team"]}],
                working, home_advantage=home_advantage,
            )[0]
            err_home = o["home_prob"] - model["home_win"]
            err_away = o["away_prob"] - model["away_win"]
            adj[o["home_team"]] = adj.get(o["home_team"], 0.0) + LEARNING_RATE * err_home
            adj[o["away_team"]] = adj.get(o["away_team"], 0.0) + LEARNING_RATE * err_away
        for t in adj:
            adj[t] *= (1.0 - L2_SHRINKAGE)

    return {
        t: max(-ADJUSTMENT_CAP, min(ADJUSTMENT_CAP, round(v, 2)))
        for t, v in adj.items() if abs(v) >= 0.1
    }


def main(odds_date: str) -> None:
    path = DAILY_ODDS_DIR / f"{odds_date}.json"
    if not path.exists():
        print(f"No daily odds file at {path} -- run fetch_daily_odds.py first.", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        observations = json.load(f)

    by_league: dict[str, list[dict]] = {}
    for o in observations:
        if not o.get("tracked"):
            continue
        by_league.setdefault(o["league"], []).append(o)

    all_adjustments: dict[str, float] = {}
    for league_name, obs in by_league.items():
        cfg = LEAGUES.get(league_name)
        if not cfg:
            continue
        league_adj = fit_league(league_name, cfg, obs)
        if league_adj:
            print(f"{league_name}: {len(obs)} observations -> {len(league_adj)} adjustments")
        all_adjustments.update(league_adj)

    OUT_PATH.parent.mkdir(exist_ok=True)
    rows = sorted(
        ({"team": t, "adjustment": v} for t, v in all_adjustments.items()),
        key=lambda r: -abs(r["adjustment"]),
    )
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "adjustment"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} adjustments to {OUT_PATH}")
    for r in rows[:20]:
        sign = "+" if r["adjustment"] >= 0 else ""
        print(f"  {r['team']:25s} {sign}{r['adjustment']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    main(args.date)
