"""
Automated, daily version of nl_odds_calibration.py's idea -- fit a small
per-team rating adjustment from real bookmaker odds -- but for the 54
tracked top-flight leagues AND LEAGUES_TIER2's ~52 second tiers, sourced
automatically from fetch_daily_odds.py's output instead of a hand-typed
observation list, and using the site's own real Poisson match model
(simulator.fixture_odds) to compare against the market instead of a
generic Elo-expectancy approximation, since that's exactly what will
actually run once this adjustment is live.

PERSISTENT per team: this is meant to be the site's own permanent club
strength rating, not a daily snapshot that happens to use Opta as a
fallback. A team's adjustment is only ever RECOMPUTED on a run where it
actually has odds evidence in the window (see below) -- every other team
keeps whatever adjustment its own last refit produced, indefinitely, even
across runs with zero fresh odds for it. On top of a team's own persisted
adjustment, every run still overlays that team's CURRENT raw Opta rating
(ratings_manager.load_ratings() does this, not this file), so the final
strength number still moves with Opta's own day-to-day changes even for a
team whose own adjustment hasn't been touched in a while -- "adjusted
further on with Opta and odds changes" without ever reverting to a bare,
odds-blind Opta number just because this team itself has no fresh line
right now.

Each individual refit is still computed from scratch (this run's pool of
live-odds observations vs. that league's raw Opta baseline, apply_
adjustments=False in fit_league) rather than nudging the team's own
previous adjustment -- that's what keeps it from compounding into runaway
drift (the "circular feedback" risk): a team's adjustment is always
anchored back to real market evidence every time it changes, never a
moving target chasing its own previous output. Persistence only changes
what happens between refits, not how a refit itself is computed.

Pulls its observations from a trailing WINDOW of fetch_daily_odds.py's
output (WINDOW_DAYS calendar days ending at --date), not just that one
day's file -- fetch_daily_odds.py only looks --days (default 3) ahead each
run, so a single day's file alone only ever covers whichever teams happen
to kick off in the next couple of days. Confirmed as a real issue
2026-10-12: a Club Power Rankings screenshot showed Arsenal/Man City/
Bayern/Real Madrid/Barcelona (and everyone else without a next-3-days
fixture) all flat at +0.0, even though every one of them had been priced by
a bookmaker within the trailing fortnight. The window makes each
individual refit better-corroborated (more of a team's matches to average
over); persistence (above) is the separate piece that stops an
up-to-date adjustment from vanishing the moment that window passes.

Where the same real-world fixture was captured on more than one day within
the window (e.g. seen as a "2 days out" lookahead, then again "1 day out"),
only the freshest (latest-dated) capture of it is kept -- the odds closest
to kickoff reflect the most information (team news, latest market
movement). Also hard-filters to source == "api_football": window days from
before the 2026-10-11 Odds API removal still have old "odds_api"-sourced
rows mixed in on disk, and including both would resurrect the exact
same-fixture double-counting bug fetch_daily_odds.py's own docstring
describes being fixed.

Writes ratings/club_rating_adjustments.csv (team, adjustment), which
ratings_manager.load_ratings() overlays onto every league's raw ratings the
same way nations_league_simulator.load_nl_ratings() already overlays
nations_league_elo_adjustments.csv.

Usage: py club_rating_calibration.py [--date YYYY-MM-DD] [--window-days 14]
"""

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from config import LEAGUES, LEAGUES_TIER2
from ratings_manager import load_ratings
from simulator import fixture_odds
from update_ratings_from_opta import _normalize, fuzzy_token_match

DAILY_ODDS_DIR = Path("odds_coverage") / "daily_odds"
OUT_PATH = Path("ratings") / "club_rating_adjustments.csv"

# How many trailing calendar days of fetch_daily_odds.py output to pool
# observations from -- see the module docstring for why a single day's
# file leaves most clubs with no observation at all most days. 14 days
# comfortably covers one full fixture cycle even for a team that plays
# only every other week; a team with no captured fixture in that whole
# window legitimately has no fresh market signal to adjust from.
WINDOW_DAYS = 14

LEARNING_RATE = 1.2     # opta-rating points per unit of probability error (0-100 scale, not Elo)
L2_SHRINKAGE = 0.03     # per-epoch pull toward 0
EPOCHS = 40
ADJUSTMENT_CAP = 10.0   # opta ratings only span ~23-100 -- a 10pt swing is already large

# A team with only ONE observed fixture that day has no corroborating match
# to average against -- a single lopsided line (strong favourite at home
# against a weak side, say) can otherwise swing that team's whole daily
# adjustment on its own. Confirmed as a real issue 2026-10-11: Besiktas'
# adjustment was being driven entirely by one home fixture vs a bottom-half
# side, further inflated (now fixed separately) by The Odds API and
# API-Football both reporting that same real match as two "independent"
# observations. Scaling a team's effective learning rate by how many
# distinct fixtures it has that day -- full strength at 2+, half strength
# at exactly 1 -- softens that single-match whiplash without muting the
# normal case (most teams only ever have 1-2 fixtures in a few days).
MIN_OBS_FOR_FULL_WEIGHT = 2


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
    """Fit (and return) an adjustment for every team that has at least one
    resolved odds observation in `observations` -- NOT every team in the
    league. A team with zero observations this run is deliberately left out
    of the return value entirely (rather than returned as 0.0) so the
    caller's persistent merge (see main()) leaves that team's own last
    fitted value untouched instead of overwriting it with a fresh "no
    evidence" zero."""
    # apply_adjustments=False: fit against the true raw Opta baseline, never
    # against an already-adjusted value -- each refit is independent of a
    # team's own previous adjustment (see module docstring: this is what
    # keeps persistence, added separately in main(), from compounding).
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

    obs_count: dict[str, int] = {}
    for o in resolved:
        obs_count[o["home_team"]] = obs_count.get(o["home_team"], 0) + 1
        obs_count[o["away_team"]] = obs_count.get(o["away_team"], 0) + 1

    def _weight(team: str) -> float:
        return min(1.0, obs_count.get(team, 0) / MIN_OBS_FOR_FULL_WEIGHT)

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
            adj[o["home_team"]] = adj.get(o["home_team"], 0.0) + LEARNING_RATE * _weight(o["home_team"]) * err_home
            adj[o["away_team"]] = adj.get(o["away_team"], 0.0) + LEARNING_RATE * _weight(o["away_team"]) * err_away
        for t in adj:
            adj[t] *= (1.0 - L2_SHRINKAGE)

    # Every team in obs_count had >=1 real observation this run, so it's
    # included even when the fitted value itself rounds near 0.0 -- that's
    # a genuine "checked, Opta already matches the market" result, distinct
    # from "not checked this run", and main()'s merge needs to see it to
    # correctly overwrite a stale nonzero persisted value for this team.
    return {
        t: max(-ADJUSTMENT_CAP, min(ADJUSTMENT_CAP, round(adj[t], 2)))
        for t in obs_count
    }


def _load_windowed_observations(end_date: str, window_days: int) -> list[dict]:
    """Pool api_football observations from the window_days calendar days
    ending at end_date (inclusive), keeping only the freshest capture of
    each real-world fixture -- see this module's own docstring for why
    both of those matter."""
    end = date.fromisoformat(end_date)
    # Oldest day first, so a later day's capture of the same fixture
    # overwrites an earlier one -- "freshest capture wins".
    by_fixture: dict[tuple, dict] = {}
    found_any_file = False
    for offset in range(window_days - 1, -1, -1):
        d = (end - timedelta(days=offset)).isoformat()
        path = DAILY_ODDS_DIR / f"{d}.json"
        if not path.exists():
            continue
        found_any_file = True
        with open(path, encoding="utf-8") as f:
            day_obs = json.load(f)
        for o in day_obs:
            if o.get("source") != "api_football":
                continue  # excludes the removed Odds API's rows still on disk in older files
            key = (o.get("league"), o.get("home_team"), o.get("away_team"))
            by_fixture[key] = o
    if not found_any_file:
        print(f"No daily odds files found in the {window_days}-day window ending {end_date} "
              f"-- run fetch_daily_odds.py first.", file=sys.stderr)
        sys.exit(1)
    return list(by_fixture.values())


def _load_persisted_adjustments() -> dict[str, float]:
    if not OUT_PATH.exists():
        return {}
    with open(OUT_PATH, encoding="utf-8") as f:
        return {row["team"]: float(row["adjustment"]) for row in csv.DictReader(f)}


def main(odds_date: str, window_days: int = WINDOW_DAYS) -> None:
    observations = _load_windowed_observations(odds_date, window_days)

    by_league: dict[str, list[dict]] = {}
    for o in observations:
        if not o.get("tracked"):
            continue
        by_league.setdefault(o["league"], []).append(o)

    # Start from what's already on disk -- this is the persistence: a team
    # keeps its last fitted adjustment unless this run actually refits it
    # (has >=1 observation for it below), never because it's simply absent
    # from this run's window. See module docstring.
    all_adjustments = _load_persisted_adjustments()
    touched = 0
    for league_name, obs in by_league.items():
        cfg = LEAGUES.get(league_name) or LEAGUES_TIER2.get(league_name)
        if not cfg:
            continue
        league_adj = fit_league(league_name, cfg, obs)
        if league_adj:
            changed = sum(1 for t, v in league_adj.items() if round(all_adjustments.get(t, 0.0), 2) != v)
            print(f"{league_name}: {len(obs)} observations -> {len(league_adj)} teams refit ({changed} changed)")
        touched += len(league_adj)
        all_adjustments.update(league_adj)

    # Prune only here, at the final merged set -- a team refit down to
    # ~0.0 this run correctly drops out (the fresh evidence says it no
    # longer needs one), while an untouched team's old value, whatever its
    # size, was already deemed significant on the run that set it and
    # stays regardless.
    all_adjustments = {t: v for t, v in all_adjustments.items() if abs(v) >= 0.1}

    OUT_PATH.parent.mkdir(exist_ok=True)
    rows = sorted(
        ({"team": t, "adjustment": v} for t, v in all_adjustments.items()),
        key=lambda r: -abs(r["adjustment"]),
    )
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "adjustment"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{touched} teams refit this run. Wrote {len(rows)} total persisted adjustments to {OUT_PATH}")
    for r in rows[:20]:
        sign = "+" if r["adjustment"] >= 0 else ""
        print(f"  {r['team']:25s} {sign}{r['adjustment']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    args = parser.parse_args()
    main(args.date, args.window_days)
