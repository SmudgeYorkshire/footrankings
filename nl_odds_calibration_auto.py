"""
Automated, daily version of nl_odds_calibration.py's manual workflow --
pulls Nations League match odds from API-Football instead of a human
web-searching and hand-typing OBSERVATIONS, then reuses that script's exact
fitting functions (fit_match_adjustments / apply_outright_adjustments)
unchanged, so the math stays identical to the manual process that's already
been running safely for weeks.

The Odds API (removed 2026-10-11, see club_odds_calibration_pipeline.md in
project memory for the fuller history) used to be the primary source here
-- its soccer_uefa_nations_league sport_key covered every fixture across
all four leagues (A/B/C/D) in one call, including tiny nations like
Liechtenstein and Malta, with deep bookmaker counts. API-Football was only
ever a secondary source alongside it, and confirmed to return ZERO Nations
League odds as of 2026-10-11 -- so right now this pipeline has no live
observations most days and main() just leaves the adjustments file
untouched until API-Football starts carrying this market (or someone goes
back to nl_odds_calibration.py's manual workflow). No outright (tournament
winner) market is available from API-Football at all -- its whole bet-type
catalog has no tournament-outright market -- so this only ever builds
"match" observations; apply_outright_adjustments is still called for
consistency with the manual script but is a no-op without "outright" rows.

Like nl_odds_calibration.py's own manual process, this carries the
adjustment forward run-to-run (not a from-scratch refit) -- the per-epoch
L2 shrinkage already prevents runaway drift, and that's the exact,
already-proven behavior this is meant to automate, not change.

Usage: py nl_odds_calibration_auto.py
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from api_football_fetcher import ApiFootballClient
from nations_league_simulator import RATINGS_ADJUSTMENTS_PATH, load_raw_nl_ratings, load_nl_rating_adjustments
from nl_odds_calibration import fit_match_adjustments, apply_outright_adjustments
from update_ratings_from_opta import _normalize, fuzzy_token_match

import pandas as pd

API_FOOTBALL_DAYS = 10  # NL matchdays are spaced ~weeks apart -- a wider window than club leagues


def _resolve_team(name: str, ratings_df: pd.DataFrame) -> str | None:
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


def pull_api_football(key: str, ratings_df: pd.DataFrame) -> list[dict]:
    from datetime import date, timedelta
    client = ApiFootballClient(api_key=key)
    today = date.today()
    observations = []
    fixture_cache: dict[tuple, dict] = {}

    for offset in range(API_FOOTBALL_DAYS):
        d = (today + timedelta(days=offset)).isoformat()
        try:
            items = client.get_odds_by_date(d)
        except RuntimeError as e:
            print(f"WARNING: API-Football odds fetch failed for {d}: {e}", file=sys.stderr)
            continue
        for item in items:
            league = item.get("league") or {}
            if league.get("name") != "UEFA Nations League":
                continue
            fixture = item.get("fixture") or {}
            lid, season = league.get("id"), league.get("season")
            cache_key = (lid, season)
            if cache_key not in fixture_cache:
                try:
                    played, remaining = client.get_fixtures(lid, season)
                except RuntimeError:
                    fixture_cache[cache_key] = {}
                else:
                    fixture_cache[cache_key] = {
                        f["idEvent"]: (f["strHomeTeam"], f["strAwayTeam"]) for f in played + remaining
                    }
            home_raw, away_raw = fixture_cache[cache_key].get(str(fixture.get("id")), (None, None))
            if not home_raw or not away_raw:
                continue
            home, away = _resolve_team(home_raw, ratings_df), _resolve_team(away_raw, ratings_df)
            if not home or not away:
                continue

            home_prices, draw_prices, away_prices = [], [], []
            for bm in item.get("bookmakers") or []:
                for bet in bm.get("bets") or []:
                    if bet.get("name") != "Match Winner":
                        continue
                    for val in bet.get("values") or []:
                        try:
                            price = float(val.get("odd"))
                        except (TypeError, ValueError):
                            continue
                        if val.get("value") == "Home":
                            home_prices.append(price)
                        elif val.get("value") == "Draw":
                            draw_prices.append(price)
                        elif val.get("value") == "Away":
                            away_prices.append(price)
            if not (home_prices and draw_prices and away_prices):
                continue
            avg = lambda prices: sum(prices) / len(prices)
            observations.append({"type": "match", "home": home, "away": away,
                                  "odds": (avg(home_prices), avg(draw_prices), avg(away_prices))})
    return observations


def main() -> None:
    ratings_df = load_raw_nl_ratings()
    base_elo = dict(zip(ratings_df["team"], ratings_df["opta_rating"]))
    current_adj = load_nl_rating_adjustments()

    observations = pull_api_football(os.getenv("API_FOOTBALL_KEY", ""), ratings_df)

    print(f"Collected {len(observations)} match observations (api_football)")
    if not observations:
        print("No observations today -- leaving the existing adjustments file untouched.")
        return

    fitted = fit_match_adjustments(base_elo, current_adj, observations=observations)
    fitted = apply_outright_adjustments(fitted, ratings_df, observations=observations)

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
