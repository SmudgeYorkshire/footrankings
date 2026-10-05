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
# The manual workflow this was built for only ever fed a handful of
# hand-picked marquee observations, so real runs topped out around ±40 and
# shrinkage alone was enough. nl_odds_calibration_auto.py feeds observations
# across the full 54-nation roster (League A through D) instead, and a
# single noisy reading against a minnow's extreme baseline Elo can otherwise
# swing well past ±90 -- this hard cap keeps either path bounded.
ADJUSTMENT_CAP = 60.0

# ---------------------------------------------------------------------------
# Fill in fresh sightings here (dated + sourced) each time this is run, then
# execute the script. Old entries can be pruned once superseded -- this file
# is a scratch input, not a permanent record (the fitted output is what
# matters and is what's committed).
# ---------------------------------------------------------------------------
OBSERVATIONS: list[dict] = [
    # No fresh "match" sightings this round -- nl_odds_calibration_auto.py's
    # daily run already covers match-level odds across the full roster (see
    # its own run log / ratings/nations_league_elo_adjustments.csv), so
    # hand-typing a handful of matches here would just double-apply a
    # correction on top of odds that are already-fitted and current.
    #
    # 2026-10-05 08:00 BST, bettingodds.com's League A outright winner
    # market (fractional -> decimal): Spain still clear favourite after
    # France/England tightened up since the last check; no Serbia line
    # currently posted (dropped the stale 2026-10-01 251.0 guess rather
    # than carry a figure with no current market backing it).
    {"type": "outright", "team": "Spain", "decimal_odds": 3.25},
    {"type": "outright", "team": "France", "decimal_odds": 4.00},
    {"type": "outright", "team": "England", "decimal_odds": 6.00},
    {"type": "outright", "team": "Portugal", "decimal_odds": 7.00},
    {"type": "outright", "team": "Germany", "decimal_odds": 10.00},
    {"type": "outright", "team": "Netherlands", "decimal_odds": 13.00},
    {"type": "outright", "team": "Belgium", "decimal_odds": 17.00},
    {"type": "outright", "team": "Greece", "decimal_odds": 21.00},
    {"type": "outright", "team": "Italy", "decimal_odds": 34.00},
    {"type": "outright", "team": "Norway", "decimal_odds": 34.00},
    {"type": "outright", "team": "Denmark", "decimal_odds": 67.00},
    {"type": "outright", "team": "Croatia", "decimal_odds": 101.00},
    {"type": "outright", "team": "Wales", "decimal_odds": 151.00},
    {"type": "outright", "team": "Türkiye", "decimal_odds": 501.00},
    {"type": "outright", "team": "Czechia", "decimal_odds": 1001.00},
]


def _devig_1x2(odds: tuple[float, float, float]) -> tuple[float, float, float]:
    ph, pd_, pa = 1.0 / odds[0], 1.0 / odds[1], 1.0 / odds[2]
    total = ph + pd_ + pa
    return ph / total, pd_ / total, pa / total


def _elo_expectancy(rating_diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-rating_diff / 400.0))


def fit_match_adjustments(
    base_elo: dict[str, float], adjustments: dict[str, float],
    observations: list[dict] | None = None,
) -> dict[str, float]:
    """observations defaults to the module-level OBSERVATIONS (the manual
    workflow this script was built for); nl_odds_calibration_auto.py passes
    its own automatically-fetched list instead, reusing this exact fit.

    With zero match observations this is a no-op (returns `adjustments`
    unchanged) rather than still running the shrinkage loop -- EPOCHS=400
    passes of L2_SHRINKAGE with nothing to re-anchor against decays
    everything toward 0 (0.98**400 =~ 0.0003x), silently wiping out
    perfectly good adjustments from a separate fitting run (e.g. this
    script's own outright-only manual step, layered on top of
    nl_odds_calibration_auto.py's already-fitted match adjustments file --
    caught for real when a 36-team auto-fit collapsed to 14 after an
    outright-only run with the match OBSERVATIONS pruned)."""
    adj = dict(adjustments)
    match_obs = [o for o in (observations if observations is not None else OBSERVATIONS) if o["type"] == "match"]
    if not match_obs:
        return adj
    # Shrinkage below only ever touches teams THIS call's observations
    # actually mention, not every team in `adj` -- confirmed via real
    # daily commits (ratings/nations_league_elo_adjustments.csv, Oct 3 ->
    # Oct 4) that shrinking the whole carried-forward dict every call
    # wipes out any team not observed again that specific day: 400 epochs
    # of 2% shrinkage is a ~99.97% decay WITHIN ONE RUN (0.98**400), so a
    # team's adjustment from two days ago -- not stale, just not re-
    # observed today -- vanishes by the end of a single day's fit even
    # though nothing contradicted it. The regularization this shrinkage
    # is for ("a team with only one noisy observation doesn't swing far")
    # only makes sense applied to teams actually being fit this call.
    touched = {t for o in match_obs for t in (o["home"], o["away"]) if t in base_elo}
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
        for t in touched:
            adj[t] = max(-ADJUSTMENT_CAP, min(ADJUSTMENT_CAP, adj.get(t, 0.0) * (1.0 - L2_SHRINKAGE)))
    return adj


def apply_outright_adjustments(
    adjustments: dict[str, float], ratings_df: pd.DataFrame,
    observations: list[dict] | None = None,
) -> dict[str, float]:
    outright_obs = [o for o in (observations if observations is not None else OBSERVATIONS) if o["type"] == "outright"]
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
        adj[team] = max(-ADJUSTMENT_CAP, min(ADJUSTMENT_CAP, adj.get(team, 0.0) + OUTRIGHT_LEARNING_RATE * error))
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
