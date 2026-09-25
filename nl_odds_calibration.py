"""
Periodic, MANUALLY-run calibration: compares nations_league_simulator's
model against real bookmaker odds (gathered via web search -- there's no
ToS-safe, script-callable odds feed for international matches, so this
can't be part of the daily GitHub Action the way scrape_elo_ratings.py
is) and fits small per-team Elo adjustments on top of eloratings.net's
own daily-updated numbers, so simulations track the market better without
discarding or overwriting the raw Elo baseline.

Workflow: whenever asked to refresh the odds comparison, Claude web-
searches current odds for a handful of upcoming fixtures (and the League
A outright winner market if available), fills in OBSERVATIONS below with
the new data (dated, sourced), and runs this script. It reads the current
ratings/nations_league_elo.csv + ratings/nations_league_elo_adjustments.csv,
fits new adjustments, and overwrites the adjustments file --
nations_league_simulator.load_nl_ratings() then applies it automatically
everywhere.

Method (deliberately simple -- this is a periodic nudge, not a full
market-making model):
  - "match" observations: real de-vigged 1X2 odds for one fixture, with
    the draw stripped out (p_home/(p_home+p_away)) to get a pairwise
    "decisive win" signal. Compared against the standard Elo win-
    expectancy formula (base 400, +100 pts for the home side -- the
    classic national-team convention, independent of this site's own
    group-scoped Poisson/K-power transform, since what's being corrected
    here is the raw rating itself, not any one simulation's use of it).
    Small gradient-descent steps nudge both teams' adjustments in
    opposite directions, with L2 shrinkage toward 0 so a team with only
    one noisy observation doesn't swing far.
  - "outright" observations: a League A team's real de-vigged chance of
    winning the whole tournament, compared against our own
    simulate_league_a_knockouts output for that team under the ratings
    as fit so far. Applied as a single direct nudge (not iterated jointly
    with the pairwise fit -- re-running the Monte Carlo knockout sim
    inside a fitting loop is expensive, and this is meant to stay a quick
    manual step).

Usage: py nl_odds_calibration.py
"""

import sys

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from nations_league_data import NL_GROUPS, NL_TIEBREAKERS
from nations_league_simulator import (
    RATINGS_ADJUSTMENTS_PATH, load_raw_nl_ratings, load_nl_rating_adjustments,
    simulate_group, simulate_league_a_knockouts,
)
from nations_league_fixtures import group_fixtures
from _split_season import compute_full_standings

HOME_ADVANTAGE_ELO_PTS = 100.0  # classic national-team convention
LEARNING_RATE = 15.0            # Elo points per unit of match-level error
OUTRIGHT_LEARNING_RATE = 300.0  # Elo points per unit of outright-market error
L2_SHRINKAGE = 0.02             # per-epoch pull toward 0, keeps sparse teams tame
EPOCHS = 400

# ---------------------------------------------------------------------------
# Fill in fresh sightings here (dated + sourced) each time this is run, then
# execute the script. Old entries can be pruned once superseded -- this file
# is a scratch input, not a permanent record (the fitted output is what
# matters and is what's committed).
# ---------------------------------------------------------------------------
OBSERVATIONS: list[dict] = [
    # 2026-09-25, matchday-1 kickoff-day line via sofascore.com (sharper
    # than the 09-24 pre-match line this replaces -- same fixture)
    {"type": "match", "home": "Türkiye", "away": "France", "odds": (8.00, 5.50, 1.33)},
    # 2026-09-25, sofascore.com aggregate (replaces the 09-24 line)
    {"type": "match", "home": "Italy", "away": "Belgium", "odds": (2.20, 3.60, 3.10)},
    # 2026-09-24, sportskeeda.com aggregate (American odds converted: +140/+260/+170)
    {"type": "match", "home": "Netherlands", "away": "Germany", "odds": (2.4286, 3.6, 2.5882)},
    # 2026-09-24, wincomparator.com
    {"type": "match", "home": "England", "away": "Spain", "odds": (2.62, 3.3, 2.55)},
    # 2026-09-25, sportsgambler.com
    {"type": "match", "home": "Hungary", "away": "Ukraine", "odds": (2.25, 3.30, 3.15)},
    # 2026-09-25, sportytrader.com model odds
    {"type": "match", "home": "Montenegro", "away": "Cyprus", "odds": (1.78, 4.05, 6.30)},
    # 2026-09-25, bettingodds.com aggregate -- rechecked, unchanged from
    # 09-21 after matchday 1's results so far
    {"type": "outright", "team": "Spain", "decimal_odds": 4.5},
    {"type": "outright", "team": "France", "decimal_odds": 5.0},
    {"type": "outright", "team": "England", "decimal_odds": 5.5},
    {"type": "outright", "team": "Germany", "decimal_odds": 5.5},
    {"type": "outright", "team": "Portugal", "decimal_odds": 9.0},
    {"type": "outright", "team": "Netherlands", "decimal_odds": 13.0},
    {"type": "outright", "team": "Norway", "decimal_odds": 17.0},
    {"type": "outright", "team": "Italy", "decimal_odds": 13.0},
    {"type": "outright", "team": "Belgium", "decimal_odds": 17.0},
    {"type": "outright", "team": "Denmark", "decimal_odds": 26.0},
    {"type": "outright", "team": "Croatia", "decimal_odds": 51.0},
]


def _devig_1x2(odds: tuple[float, float, float]) -> tuple[float, float, float]:
    ph, pd_, pa = 1.0 / odds[0], 1.0 / odds[1], 1.0 / odds[2]
    total = ph + pd_ + pa
    return ph / total, pd_ / total, pa / total


def _elo_expectancy(rating_diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-rating_diff / 400.0))


def fit_match_adjustments(base_elo: dict[str, float], adjustments: dict[str, float]) -> dict[str, float]:
    adj = dict(adjustments)
    match_obs = [o for o in OBSERVATIONS if o["type"] == "match"]
    for _ in range(EPOCHS):
        for o in match_obs:
            home, away = o["home"], o["away"]
            if home not in base_elo or away not in base_elo:
                print(f"WARNING: unknown team in observation {o}", file=sys.stderr)
                continue
            p_h, _, p_a = _devig_1x2(o["odds"])
            target = p_h / (p_h + p_a)
            diff = (base_elo[home] + adj.get(home, 0.0)) - (base_elo[away] + adj.get(away, 0.0)) + HOME_ADVANTAGE_ELO_PTS
            model = _elo_expectancy(diff)
            error = target - model
            adj[home] = adj.get(home, 0.0) + LEARNING_RATE * error
            adj[away] = adj.get(away, 0.0) - LEARNING_RATE * error
        for t in list(adj):
            adj[t] *= (1.0 - L2_SHRINKAGE)
    return adj


def apply_outright_adjustments(adjustments: dict[str, float], ratings_df: pd.DataFrame) -> dict[str, float]:
    outright_obs = [o for o in OBSERVATIONS if o["type"] == "outright"]
    if not outright_obs:
        return adjustments

    adj = dict(adjustments)
    adjusted_ratings = ratings_df.copy()
    adjusted_ratings["opta_rating"] = adjusted_ratings.apply(
        lambda r: r["opta_rating"] + adj.get(r["team"], 0.0), axis=1,
    )

    groups = NL_GROUPS["League A"]
    group_probs = {}
    for gname, teams in groups.items():
        played, remaining = group_fixtures(teams)
        roster = [{"strTeam": t} for t in teams]
        standings = compute_full_standings(roster, played, tiebreakers=NL_TIEBREAKERS)
        probs, _ = simulate_group(
            teams, adjusted_ratings, n_sim=10_000,
            standings=standings, remaining_fixtures=remaining, played_fixtures=played,
        )
        group_probs[gname] = probs

    ko = simulate_league_a_knockouts(group_probs, adjusted_ratings, n_sim=15_000)

    total_implied = sum(1.0 / o["decimal_odds"] for o in outright_obs)
    for o in outright_obs:
        team = o["team"]
        if team not in ko.index:
            print(f"WARNING: unknown team in outright observation {o}", file=sys.stderr)
            continue
        target = (1.0 / o["decimal_odds"]) / total_implied
        model = float(ko.loc[team, "won_competition"])
        error = target - model
        adj[team] = adj.get(team, 0.0) + OUTRIGHT_LEARNING_RATE * error
    return adj


def main() -> None:
    ratings_df = load_raw_nl_ratings()
    base_elo = dict(zip(ratings_df["team"], ratings_df["opta_rating"]))
    current_adj = load_nl_rating_adjustments()

    fitted = fit_match_adjustments(base_elo, current_adj)
    fitted = apply_outright_adjustments(fitted, ratings_df)

    rows = sorted(
        ({"team": t, "adjustment": round(v, 1)} for t, v in fitted.items() if abs(v) >= 0.1),
        key=lambda r: -abs(r["adjustment"]),
    )
    pd.DataFrame(rows, columns=["team", "adjustment"]).to_csv(RATINGS_ADJUSTMENTS_PATH, index=False)
    print(f"Wrote {len(rows)} adjustments to {RATINGS_ADJUSTMENTS_PATH}")
    for r in rows:
        sign = "+" if r["adjustment"] >= 0 else ""
        print(f"  {r['team']:20s} {sign}{r['adjustment']}")


if __name__ == "__main__":
    main()
