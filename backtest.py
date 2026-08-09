"""
Backtest harness for the season simulator's finish-probability model.

Takes a completed past season, rewinds to a mid-season snapshot (using
that season's actual standings/results up to that point), simulates the
rest of the way with today's simulator, and scores the resulting
finish-position probabilities against what actually happened using the
Ranked Probability Score (RPS) — lower is better, 0 is a perfect
prediction.

IMPORTANT CAVEAT: we don't keep historical snapshots of Opta ratings
(only the current CSV), so this necessarily uses TODAY's ratings as the
strength estimate for a PAST season — real hindsight bias. Every model
variant below is scored with the exact same ratings, though, so the
ABSOLUTE RPS numbers are optimistic but the RELATIVE ranking between
variants (does Dixon-Coles/shape-adjustment/form help or hurt) is still
meaningful, because the hindsight bias affects all variants equally.

Usage:
    py backtest.py                          # single run: English Premier League, 2024-25
    py backtest.py --league "German Bundesliga" --season 2024 --snapshot 10
    py backtest.py --multi                  # aggregate across many leagues/seasons/snapshots
"""

import argparse
import os
import sys
import time

import numpy as np
from dotenv import load_dotenv

load_dotenv()

from config import LEAGUES
from api_football_fetcher import ApiFootballClient
from ratings_manager import load_ratings
from _split_season import compute_full_standings
from simulator import simulate_season, apply_shape_adjustment, _opta_to_attack_defense

# Curated spread for --multi: Top 5 + a few split-format / smaller leagues,
# so the aggregate isn't dominated by one competition's quirks.
MULTI_LEAGUES = [
    "English Premier League", "Italian Serie A", "Spanish La Liga",
    "German Bundesliga", "French Ligue 1",
    "Bulgarian First League", "Austrian Bundesliga", "Dutch Eredivisie",
]
MULTI_SEASONS = [2024, 2023]
MULTI_SNAPSHOTS = [10, 20]


def rps(predicted_probs: np.ndarray, actual_position: int) -> float:
    """Ranked Probability Score for one team's predicted finish-position
    distribution vs. its true final position. 0 = perfect, higher = worse."""
    k = len(predicted_probs)
    actual = np.zeros(k)
    actual[actual_position - 1] = 1.0
    cum_pred = np.cumsum(predicted_probs)
    cum_actual = np.cumsum(actual)
    return float(np.sum((cum_pred - cum_actual) ** 2) / (k - 1))


def mean_rps(probs_df, true_positions: dict[str, int]) -> float:
    scores = []
    for team in probs_df.index:
        if team not in true_positions:
            continue
        scores.append(rps(probs_df.loc[team].values, true_positions[team]))
    return float(np.mean(scores)) if scores else float("nan")


def build_variants(ratings_raw, snapshot_played):
    return {
        "baseline (no DC, no shape, form on)": dict(ratings=_opta_to_attack_defense(ratings_raw), use_dixon_coles=False, apply_form=True),
        "baseline, form OFF (isolates form)":  dict(ratings=_opta_to_attack_defense(ratings_raw), use_dixon_coles=False, apply_form=False),
        "+ Dixon-Coles":                       dict(ratings=_opta_to_attack_defense(ratings_raw), use_dixon_coles=True,  apply_form=True),
        "+ Dixon-Coles + shape":               dict(ratings=apply_shape_adjustment(ratings_raw, snapshot_played), use_dixon_coles=True, apply_form=True),
        "+ Dixon-Coles + shape, form OFF":     dict(ratings=apply_shape_adjustment(ratings_raw, snapshot_played), use_dixon_coles=True, apply_form=False),
        "shape only, no DC, form on":          dict(ratings=apply_shape_adjustment(ratings_raw, snapshot_played), use_dixon_coles=False, apply_form=True),
    }


def run_single_backtest(league_name: str, season: int, snapshot: int, n_sim: int,
                         client: ApiFootballClient) -> dict[str, float] | None:
    """Returns {variant_name: mean_rps} for one league/season/snapshot combo,
    or None if that season isn't fully complete / snapshot leaves nothing
    to simulate."""
    cfg = LEAGUES[league_name]
    played_all, remaining_all = client.get_fixtures(cfg["id"], season)
    if remaining_all or not played_all:
        return None

    def _round(f):
        try:
            return int(f.get("intRound") or 0)
        except (TypeError, ValueError):
            return 0

    snapshot_played    = [f for f in played_all if _round(f) <= snapshot]
    snapshot_remaining = [f for f in played_all if _round(f) > snapshot]
    if not snapshot_remaining or not snapshot_played:
        return None

    all_teams = {f["strHomeTeam"] for f in played_all} | {f["strAwayTeam"] for f in played_all}
    true_standings = compute_full_standings([{"strTeam": t} for t in all_teams], played_all)
    true_positions = {r["strTeam"]: int(r["intRank"]) for r in true_standings}

    snapshot_standings = compute_full_standings([{"strTeam": t} for t in all_teams], snapshot_played)
    ratings_raw = load_ratings(cfg.get("tsdb_id", cfg["id"]), snapshot_standings)
    home_adv = cfg.get("home_advantage", 1.20)
    tiebreakers = cfg.get("tiebreakers")

    scores = {}
    for name, kw in build_variants(ratings_raw, snapshot_played).items():
        probs = simulate_season(
            standings=snapshot_standings,
            remaining_fixtures=snapshot_remaining,
            n_sim=n_sim,
            home_advantage=home_adv,
            tiebreakers=tiebreakers,
            played_fixtures=snapshot_played,
            **kw,
        )
        scores[name] = mean_rps(probs, true_positions)
    return scores


def run_multi(n_sim: int):
    key = os.getenv("API_FOOTBALL_KEY", "")
    client = ApiFootballClient(api_key=key)

    print(f"Aggregating across {len(MULTI_LEAGUES)} leagues x {len(MULTI_SEASONS)} seasons x {len(MULTI_SNAPSHOTS)} snapshots")
    print("(hindsight caveat: using TODAY's Opta ratings for past seasons — see module docstring)\n")

    all_runs: list[dict[str, float]] = []
    n_ok, n_skipped = 0, 0
    for league_name in MULTI_LEAGUES:
        for season in MULTI_SEASONS:
            for snapshot in MULTI_SNAPSHOTS:
                result = run_single_backtest(league_name, season, snapshot, n_sim, client)
                if result is None:
                    n_skipped += 1
                    continue
                all_runs.append(result)
                n_ok += 1
                print(f"  [{n_ok}] {league_name} {season}-{season+1} @md{snapshot}  done", flush=True)
                time.sleep(1.2)  # avoid the burst-block seen on rapid sequential calls

    print(f"\nCompleted {n_ok} runs, skipped {n_skipped} (incomplete season data)\n")
    if not all_runs:
        print("No successful runs — nothing to report.", file=sys.stderr)
        sys.exit(1)

    variant_names = all_runs[0].keys()
    print(f"{'Variant':<38} {'Mean RPS':>10} {'Std':>8}  {'N':>4}")
    print("-" * 64)
    for name in variant_names:
        vals = [r[name] for r in all_runs if name in r and not np.isnan(r[name])]
        print(f"{name:<38} {np.mean(vals):>10.5f} {np.std(vals):>8.5f}  {len(vals):>4}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--league", default="English Premier League")
    ap.add_argument("--season", type=int, default=2024, help="API-Football season start year, e.g. 2024 for 2024-25")
    ap.add_argument("--snapshot", type=int, default=10, help="matchday to rewind to before simulating the rest")
    ap.add_argument("--n-sim", type=int, default=10_000)
    ap.add_argument("--multi", action="store_true", help="aggregate across many leagues/seasons/snapshots instead of one run")
    args = ap.parse_args()

    if args.multi:
        run_multi(n_sim=min(args.n_sim, 5_000))  # lighter per-run n_sim — precision comes from aggregation
        return

    if args.league not in LEAGUES:
        print(f"Unknown league: {args.league!r}", file=sys.stderr)
        sys.exit(1)
    key = os.getenv("API_FOOTBALL_KEY", "")
    client = ApiFootballClient(api_key=key)

    print(f"League: {args.league}  |  season {args.season}-{args.season+1}  |  snapshot after matchday {args.snapshot}")
    print("(hindsight caveat: using TODAY's Opta ratings for a past season — see module docstring)\n")

    scores = run_single_backtest(args.league, args.season, args.snapshot, args.n_sim, client)
    if scores is None:
        print("Season not fully complete, or snapshot leaves nothing to simulate — try different args.", file=sys.stderr)
        sys.exit(1)

    print(f"{'Variant':<38} {'Mean RPS':>10}")
    print("-" * 50)
    for name, score in scores.items():
        print(f"{name:<38} {score:>10.5f}")


if __name__ == "__main__":
    main()
