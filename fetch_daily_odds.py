"""
Single daily pull of pre-match odds from API-Football (already paid for,
used via ApiFootballClient.get_odds_by_date) -- our only odds provider.

The Odds API was removed 2026-10-11: it covered more bookmakers per match
on the leagues it had, but API-Football alone already covers every league
we need, and running two providers was causing real problems --
club_rating_calibration.py's daily fit was silently double-counting any
fixture both providers happened to cover (plain list concatenation, no
cross-source dedup), which let a single real-world match swing a team's
rating adjustment twice as hard as a singly-sourced one. We also don't pay
for The Odds API, so depending on its free tier for a live pipeline was a
standing risk. See club_odds_calibration_pipeline.md (project memory) for
the fuller history.

This is the one place that calls the odds API. Two downstream consumers
read its output instead of hitting the API themselves:
  - odds_comparison_snapshot.py (logs day-by-day API-Football coverage --
    which leagues/fixtures it adds or drops over time)
  - club_rating_calibration.py (fits the daily rating adjustment, for both
    LEAGUES and LEAGUES_TIER2)
  - (indirectly) build_club_power_rankings.py, via the adjustment file

Writes odds_coverage/daily_odds/{date}.json -- a flat list of per-fixture
observations, each already de-vigged to a consensus (home, draw, away)
probability triple (averaging implied probabilities across bookmakers,
then renormalizing to remove the overround), tagged with which of our
tracked top-flight OR tier-2 leagues it belongs to (or "" if it's a fixture
outside both tracked sets -- still logged, since odds_comparison_snapshot.py
wants the full unfiltered picture).

Usage: py fetch_daily_odds.py [--days 3]
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from config import LEAGUES, LEAGUES_TIER2
from api_football_fetcher import ApiFootballClient

OUT_DIR = Path("odds_coverage") / "daily_odds"

# Merged id->name map across both tiers -- API-Football's own league ids
# never collide between the two dicts (they're separate real competitions),
# so a plain merge is safe. A fixture's "tracked" flag (see pull_api_
# football) means "one of our 54 top-flight OR ~49 tier-2 leagues", not
# top-flight only.
_LEAGUE_ID_TO_NAME = {
    **{cfg["id"]: name for name, cfg in LEAGUES.items()},
    **{cfg["id"]: name for name, cfg in LEAGUES_TIER2.items()},
}


def _devig(probs_raw: list[float]) -> list[float] | None:
    total = sum(probs_raw)
    if total <= 0:
        return None
    return [p / total for p in probs_raw]


def _avg_implied(prices: list[float]) -> float:
    """Average IMPLIED PROBABILITY across bookmakers for one outcome
    (averaging probabilities, not raw decimal odds, is the standard way to
    build a consensus price -- raw-odds averaging is skewed by longshots)."""
    return sum(1.0 / p for p in prices if p and p > 0) / len(prices)


def pull_api_football(days: int, key: str) -> list[dict]:
    client = ApiFootballClient(api_key=key)
    today = date.today()
    fixture_cache: dict[tuple, dict] = {}
    observations = []

    for offset in range(days):
        d = (today + timedelta(days=offset)).isoformat()
        try:
            items = client.get_odds_by_date(d)
        except RuntimeError as e:
            print(f"WARNING: API-Football odds fetch failed for {d}: {e}", file=sys.stderr)
            continue

        for item in items:
            league = item.get("league") or {}
            fixture = item.get("fixture") or {}
            lid, season = league.get("id"), league.get("season")
            if lid is None:
                continue
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
            home, away = fixture_cache[cache_key].get(str(fixture.get("id")), (None, None))
            if not home or not away:
                continue  # fixture_id not resolvable to team names this run -- skip rather than guess

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
            probs = _devig([_avg_implied(home_prices), _avg_implied(draw_prices), _avg_implied(away_prices)])
            if not probs:
                continue

            observations.append({
                "source": "api_football",
                "league": _LEAGUE_ID_TO_NAME.get(lid, league.get("name", "")),
                "tracked": lid in _LEAGUE_ID_TO_NAME,
                "home_team": home,
                "away_team": away,
                "commence_time": fixture.get("date", d),
                "bookmaker_count": len(item.get("bookmakers") or []),
                "home_prob": probs[0],
                "draw_prob": probs[1],
                "away_prob": probs[2],
            })
        time.sleep(0.35)  # same pacing as odds_coverage_snapshot.py -- avoids the burst rate-limit
    return observations


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args()

    api_football_key = os.getenv("API_FOOTBALL_KEY", "")

    all_obs = pull_api_football(args.days, api_football_key)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_obs, f, indent=1)

    print(f"Wrote {len(all_obs)} observations (api_football) to {out_path}")
