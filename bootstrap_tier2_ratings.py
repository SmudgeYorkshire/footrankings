"""
Seeds ratings/{tsdb_id}.csv for every LEAGUES_TIER2 league from the global
Opta scrape (opta_power_rankings.csv, ~14,200 clubs worldwide -- already
proven in build_club_power_rankings.py to reach far beyond just the 54
tracked top-flight rosters) instead of leaving it to ratings_manager's
crude goal-difference fallback, which the project plan's research
confirmed would otherwise produce a flat, undifferentiated rating for
every team until several matchdays have been played.

For each league: fetch its real roster via ApiFootballClient.get_standings,
then resolve each team name against the global scrape using EXACT and
normalized (diacritics/club-suffix-stripped) matching only -- deliberately
NOT the fuzzy token-subset tier club_rating_calibration.py also uses.
That tier is only safe when matching INTO a small, scoped pool (one
league's own ~20-team ratings_df); here the match target is the full
~14,200-club GLOBAL list, which is exactly the large/ambiguous pool that
already produced one false positive this project ("Villa" stealing Aston
Villa's rating in build_club_power_rankings.py). Tried here first without
this restriction, it immediately reproduced the same failure mode on a
real run: "Bristol City" fuzzy-matched some unrelated club via the single
generic token "City", and "Sheffield Utd" similarly via "Sheffield",
both landing implausibly low ratings for well-known Championship sides.
Exact/normalized-only trades a little coverage for not being confidently
wrong about a famous club.

Unmatched teams fall back to ratings_manager.DEFAULT_OPTA, the same
constant the existing no-CSV fallback already uses, so a team genuinely
missing from Opta's list isn't rated zero or dropped.

Usage: py bootstrap_tier2_ratings.py [--league "England - Championship"]
(omit --league to bootstrap every LEAGUES_TIER2 entry)
"""

import argparse
import csv
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from config import LEAGUES_TIER2
from api_football_fetcher import ApiFootballClient
from ratings_manager import RATINGS_DIR, DEFAULT_OPTA
from update_ratings_from_opta import _normalize
from _split_season import ensure_full_roster

GLOBAL_RANKINGS_PATH = "opta_power_rankings.csv"


def _build_lookups(global_df: pd.DataFrame) -> tuple[dict[str, tuple[float, str]], dict[str, tuple[float, str]]]:
    """{team: (rating, team)} exact + {normalized: (rating, team)}, built
    once rather than re-scanning/re-normalizing all ~14,200 rows per team
    looked up (50 leagues x ~20 teams would otherwise mean ~14,200 x 1,000
    redundant normalize() calls).

    451 of the ~14,200 names in the global scrape aren't unique -- lots of
    unrelated real clubs worldwide happen to share a short/generic name
    (confirmed: "Wolves" alone has 4 entries, the real Wolverhampton
    Wanderers at 84.9 plus three unrelated clubs down at 37-50). Keeping
    "whichever happens to end up in the dict" picked the WRONG one on a
    real run (37.5 for Wolves, right after they'd been relegated FROM the
    Premier League). For a duplicate, keep the HIGHEST-rated entry: a club
    good enough to play in a European country's top two tiers will almost
    always be the prominent, highly-rated side behind a shared name, not
    an obscure unrelated club elsewhere in the world that coincidentally
    shares it. Not bulletproof, but far better than file-order luck.
    """
    exact: dict[str, tuple[float, str]] = {}
    normalized: dict[str, tuple[float, str]] = {}
    for _, row in global_df.iterrows():
        rating, team = float(row["rating"]), row["team"]
        if team not in exact or rating > exact[team][0]:
            exact[team] = (rating, team)
        key = _normalize(team)
        if key not in normalized or rating > normalized[key][0]:
            normalized[key] = (rating, team)
    return exact, normalized


def _resolve_rating(team_name: str, exact: dict, normalized: dict) -> tuple[float, str]:
    """Returns (rating, matched_name_or_empty). Exact -> normalized only --
    see module docstring for why fuzzy matching against this large a pool
    is deliberately not attempted here."""
    if team_name in exact:
        return exact[team_name]
    hit = normalized.get(_normalize(team_name))
    if hit:
        return hit
    return DEFAULT_OPTA, ""


def bootstrap_league(league_name: str, cfg: dict, key: str, exact: dict, normalized: dict) -> None:
    csv_path = RATINGS_DIR / f"{cfg['tsdb_id']}.csv"
    client = ApiFootballClient(api_key=key)
    season = cfg.get("af_season")
    try:
        roster = client.get_standings(cfg["id"], season)
        played, remaining = client.get_fixtures(cfg["id"], season)
    except RuntimeError as e:
        print(f"  WARNING: couldn't fetch roster for {league_name}: {e}", file=sys.stderr)
        return
    # The standings endpoint has been observed to come back empty even once
    # fixtures exist (same quirk football_rankings.py's fetch_all() already
    # works around) -- pad the roster out from the fixture list before
    # giving up on it.
    roster = ensure_full_roster(roster, played + remaining) if roster or played or remaining else roster
    if not roster:
        print(f"  WARNING: no roster or fixtures for {league_name} yet (season not published)", file=sys.stderr)
        return

    rows, unmatched = [], []
    for team in roster:
        name = team.get("strTeam")
        if not name:
            continue
        rating, matched = _resolve_rating(name, exact, normalized)
        alias = matched if matched and matched != name else ""
        rows.append({"team": name, "alias": alias, "opta_rating": round(rating, 1)})
        if not matched:
            unmatched.append(name)

    RATINGS_DIR.mkdir(exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "alias", "opta_rating"])
        writer.writeheader()
        writer.writerows(rows)

    msg = f"  {league_name}: {len(rows)} teams -> {csv_path}"
    if unmatched:
        msg += f" ({len(unmatched)} unmatched, using default {DEFAULT_OPTA}: {', '.join(unmatched)})"
    print(msg)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default=None, help="Bootstrap just this one LEAGUES_TIER2 key")
    args = parser.parse_args()

    if not Path(GLOBAL_RANKINGS_PATH).exists():
        print(f"{GLOBAL_RANKINGS_PATH} not found -- run scrape_opta_power_rankings.py first.", file=sys.stderr)
        sys.exit(1)
    global_df = pd.read_csv(GLOBAL_RANKINGS_PATH)
    global_df["rating"] = pd.to_numeric(global_df["rating"], errors="coerce")
    global_df = global_df.dropna(subset=["rating"])
    exact, normalized = _build_lookups(global_df)

    import os
    key = os.getenv("API_FOOTBALL_KEY", "")

    targets = {args.league: LEAGUES_TIER2[args.league]} if args.league else LEAGUES_TIER2
    print(f"Bootstrapping {len(targets)} second-tier league(s)...\n")
    for league_name, cfg in targets.items():
        bootstrap_league(league_name, cfg, key, exact, normalized)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
