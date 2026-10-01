"""
Single daily pull of pre-match odds from both providers -- API-Football
(already paid for, used via ApiFootballClient.get_odds_by_date) and The Odds
API (a separate, dedicated odds provider; confirmed live to cover ~20 of our
54 tracked leagues with far deeper bookmaker coverage than API-Football).

This is the one place that actually calls either odds API. Three downstream
consumers read its output instead of hitting the APIs themselves:
  - odds_comparison_snapshot.py (logs day-by-day coverage from both, to
    decide over the next month whether paying for The Odds API is worth it)
  - club_rating_calibration.py (fits the daily rating adjustment)
  - (indirectly) build_club_power_rankings.py, via the adjustment file

Writes odds_coverage/daily_odds/{date}.json -- a flat list of per-fixture
observations, each already de-vigged to a consensus (home, draw, away)
probability triple (averaging implied probabilities across that source's own
bookmakers, then renormalizing to remove the overround), tagged with which
source it came from and which of our 54 tracked leagues it belongs to (or
"" if it's an API-Football fixture outside our tracked set -- still logged,
since odds_comparison_snapshot.py wants the full unfiltered picture).

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

import requests

from config import LEAGUES
from api_football_fetcher import ApiFootballClient

OUT_DIR = Path("odds_coverage") / "daily_odds"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Every soccer competition The Odds API names that matches one of our 54
# tracked leagues exactly (config.py key -> their sport_key), confirmed live
# against the real API, not their marketing site. The ~34 leagues with no
# entry here simply aren't covered by this provider -- confirmed separately,
# not an oversight.
ODDS_API_SPORT_KEYS: dict[str, str] = {
    "Austrian Bundesliga":               "soccer_austria_bundesliga",
    "Belgian Pro League":                "soccer_belgium_first_div",
    "Danish Superliga":                  "soccer_denmark_superliga",
    "English Premier League":            "soccer_epl",
    "Finnish Veikkausliiga":             "soccer_finland_veikkausliiga",
    "French Ligue 1":                    "soccer_france_ligue_one",
    "German Bundesliga":                 "soccer_germany_bundesliga",
    "Greek Super League 1":              "soccer_greece_super_league",
    "Irish Premier Division":            "soccer_league_of_ireland",
    "Italian Serie A":                   "soccer_italy_serie_a",
    "Dutch Eredivisie":                  "soccer_netherlands_eredivisie",
    "Norwegian Eliteserien":             "soccer_norway_eliteserien",
    "Polish Ekstraklasa":                "soccer_poland_ekstraklasa",
    "Portuguese Primeira Liga":          "soccer_portugal_primeira_liga",
    "Russian Football Premier League":   "soccer_russia_premier_league",
    "Scottish Premiership":              "soccer_spl",
    "Spanish La Liga":                   "soccer_spain_la_liga",
    "Swedish Allsvenskan":               "soccer_sweden_allsvenskan",
    "Swiss Super League":                "soccer_switzerland_superleague",
    "Turkish Super Lig":                 "soccer_turkey_super_league",
}

_LEAGUE_ID_TO_NAME = {cfg["id"]: name for name, cfg in LEAGUES.items()}


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


def pull_odds_api(key: str) -> list[dict]:
    if not key:
        print("WARNING: no ODDS_API_KEY set -- skipping The Odds API pull", file=sys.stderr)
        return []
    observations = []
    for league_name, sport_key in ODDS_API_SPORT_KEYS.items():
        try:
            r = requests.get(
                f"{ODDS_API_BASE}/sports/{sport_key}/odds",
                params={"apiKey": key, "regions": "eu", "markets": "h2h"},
                timeout=15,
            )
            r.raise_for_status()
            matches = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"WARNING: The Odds API fetch failed for {sport_key}: {e}", file=sys.stderr)
            continue
        if not isinstance(matches, list):
            print(f"WARNING: The Odds API returned an error for {sport_key}: {matches}", file=sys.stderr)
            continue

        for m in matches:
            home_team, away_team = m.get("home_team"), m.get("away_team")
            home_prices, draw_prices, away_prices = [], [], []
            for bm in m.get("bookmakers") or []:
                for market in bm.get("markets") or []:
                    if market.get("key") != "h2h":
                        continue
                    for outcome in market.get("outcomes") or []:
                        price = outcome.get("price")
                        if not price:
                            continue
                        if outcome.get("name") == home_team:
                            home_prices.append(price)
                        elif outcome.get("name") == away_team:
                            away_prices.append(price)
                        elif outcome.get("name") == "Draw":
                            draw_prices.append(price)
            if not (home_prices and draw_prices and away_prices):
                continue
            probs = _devig([_avg_implied(home_prices), _avg_implied(draw_prices), _avg_implied(away_prices)])
            if not probs:
                continue

            bookmaker_count = len({bm.get("key") for bm in m.get("bookmakers") or []})
            observations.append({
                "source": "odds_api",
                "league": league_name,
                "tracked": True,
                "home_team": home_team,
                "away_team": away_team,
                "commence_time": m.get("commence_time", ""),
                "bookmaker_count": bookmaker_count,
                "home_prob": probs[0],
                "draw_prob": probs[1],
                "away_prob": probs[2],
            })
        time.sleep(0.2)
    return observations


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args()

    api_football_key = os.getenv("API_FOOTBALL_KEY", "")
    odds_api_key = os.getenv("ODDS_API_KEY", "")

    af_obs = pull_api_football(args.days, api_football_key)
    oa_obs = pull_odds_api(odds_api_key)
    all_obs = af_obs + oa_obs

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_obs, f, indent=1)

    print(f"Wrote {len(all_obs)} observations ({len(af_obs)} api_football, {len(oa_obs)} odds_api) to {out_path}")
