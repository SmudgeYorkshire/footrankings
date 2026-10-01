"""
Daily odds-coverage snapshot -- API-Football's /odds endpoint only retains
a short rolling window of pre-match odds (no historical archive at all: a
past-season query comes back empty, confirmed directly against the live
API), so there is no way to retroactively find out which leagues it has
covered over time. This script is the fix: run it once a day (manually
for now; a scheduled job later) and it appends that day's full picture --
every fixture across every competition, club AND national team, that has
at least one bookmaker's odds published -- to odds_coverage/log.csv.
Re-running daily builds the history API-Football itself won't give us,
and over a few weeks shows which of the 54 tracked leagues (plus
international competitions) actually get bookmaker coverage and how far
ahead of kickoff it shows up.

Deliberately unfiltered: this does NOT limit itself to the 54 leagues in
config.py -- the whole point is to see everything API-Football's odds
feed covers (South American leagues, MLS, national teams, youth
qualifiers, ...) so that decision is made from real data, not a guess.

Usage: py odds_coverage_snapshot.py [--days 21]
"""

import argparse
import csv
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from api_football_fetcher import ApiFootballClient

LOG_PATH = Path("odds_coverage") / "log.csv"
FIELDS = [
    "snapshot_date", "fixture_date", "odds_updated_at", "fixture_id", "country", "league_id",
    "league_name", "bookmaker_count", "has_match_winner",
]


def _summarize_bookmakers(item: dict) -> tuple[int, bool]:
    bookmakers = item.get("bookmakers") or []
    has_match_winner = any(
        bet.get("name") == "Match Winner"
        for bm in bookmakers
        for bet in (bm.get("bets") or [])
    )
    return len(bookmakers), has_match_winner


def capture(days: int, key: str) -> list[dict]:
    client = ApiFootballClient(api_key=key)
    today = date.today()
    rows = []
    for offset in range(days):
        d = (today + timedelta(days=offset)).isoformat()
        try:
            items = client.get_odds_by_date(d)
        except RuntimeError as e:
            print(f"WARNING: odds fetch failed for {d}: {e}", file=sys.stderr)
            continue
        for item in items:
            # The /odds payload itself only carries {league, fixture, update,
            # bookmakers} -- no team names (confirmed by inspecting a live
            # response). Resolving fixture_id -> team names happens later,
            # at actual calibration time, via the existing get_fixtures()
            # call for whichever league is being calibrated -- not worth
            # the extra per-fixture API calls just for this coverage count.
            league = item.get("league") or {}
            fixture = item.get("fixture") or {}
            bk_count, has_mw = _summarize_bookmakers(item)
            rows.append({
                "snapshot_date": today.isoformat(),
                "fixture_date": fixture.get("date", d),
                "odds_updated_at": item.get("update", ""),
                "fixture_id": fixture.get("id"),
                "country": league.get("country", ""),
                "league_id": league.get("id"),
                "league_name": league.get("name", ""),
                "bookmaker_count": bk_count,
                "has_match_winner": has_mw,
            })
        time.sleep(0.35)  # pacing -- avoids the burst rate-limit seen under rapid-fire calls
    return rows


def append_log(rows: list[dict]) -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    write_header = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict]) -> None:
    by_league: dict[tuple, int] = {}
    for r in rows:
        k = (r["country"] or "—", r["league_name"])
        by_league[k] = by_league.get(k, 0) + 1

    print(f"\nTotal fixtures with odds across the captured window: {len(rows)}")
    print(f"Distinct leagues/competitions seen: {len(by_league)}\n")

    # API-Football consistently tags international (national-team) fixtures
    # with country "World" -- confirmed by direct inspection of its output.
    national_keys = {k for k in by_league if k[0] in ("World", "")}
    national_team = [(k, v) for k, v in by_league.items() if k in national_keys]
    club = [(k, v) for k, v in by_league.items() if k not in national_keys]

    print("=== National team / international competitions ===")
    for (country, league), count in sorted(national_team, key=lambda x: -x[1]):
        print(f"  {country:10s} {league:45s} {count:3d} fixtures")
    if not national_team:
        print("  (none found in this window)")

    print("\n=== Club leagues (sorted by fixture count) ===")
    for (country, league), count in sorted(club, key=lambda x: -x[1]):
        print(f"  {country:15s} {league:40s} {count:3d} fixtures")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=21)
    args = parser.parse_args()

    api_key = os.getenv("API_FOOTBALL_KEY", "")
    captured = capture(args.days, api_key)
    append_log(captured)
    print(f"Appended {len(captured)} rows to {LOG_PATH}")
    summarize(captured)
