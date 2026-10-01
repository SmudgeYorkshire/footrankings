"""
Daily API-Football vs. The Odds API comparison log.

Supersedes odds_coverage_snapshot.py (deleted) -- that script hit
API-Football directly; this one reads fetch_daily_odds.py's already-pulled,
already-normalized daily_odds/{date}.json instead, so there's exactly one
place that calls either odds API per day. Since fetch_daily_odds.py's
API-Football pull is itself unfiltered (every league/competition that has
odds, tagged "tracked": True/False, not just the 54 we track), this log
still covers the same broad landscape the old script did (national teams,
South American leagues, etc.) as well as the specific tracked-league,
both-providers comparison the user asked to run daily for the next month.

Appends one row per (date, source, league) to odds_coverage/comparison_log.csv:
    date, source, league, tracked, n_fixtures, avg_bookmakers

Meant to run daily for about a month; after that, group by (source,
tracked) and compare n_fixtures/avg_bookmakers to decide whether The Odds
API's extra coverage/depth over free API-Football justifies its cost.

Usage: py odds_comparison_snapshot.py [--date YYYY-MM-DD]
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

DAILY_ODDS_DIR = Path("odds_coverage") / "daily_odds"
LOG_PATH = Path("odds_coverage") / "comparison_log.csv"
FIELDS = ["date", "source", "league", "tracked", "n_fixtures", "avg_bookmakers"]


def summarize(odds_date: str, observations: list[dict]) -> list[dict]:
    groups: dict[tuple, list[int]] = defaultdict(list)
    for o in observations:
        key = (o["source"], o["league"], o.get("tracked", False))
        groups[key].append(o.get("bookmaker_count", 0))

    rows = []
    for (source, league, tracked), bookmaker_counts in groups.items():
        rows.append({
            "date": odds_date,
            "source": source,
            "league": league,
            "tracked": tracked,
            "n_fixtures": len(bookmaker_counts),
            "avg_bookmakers": round(sum(bookmaker_counts) / len(bookmaker_counts), 1),
        })
    return rows


def append_log(odds_date: str, rows: list[dict]) -> None:
    """Appends, but first drops any existing rows for this same date -- so
    re-running the same day (a manual workflow_dispatch re-trigger, or just
    testing locally) replaces that day's rows instead of duplicating them."""
    LOG_PATH.parent.mkdir(exist_ok=True)
    existing = []
    if LOG_PATH.exists():
        with open(LOG_PATH, newline="", encoding="utf-8") as f:
            existing = [r for r in csv.DictReader(f) if r["date"] != odds_date]
    with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(existing)
        writer.writerows(rows)


def print_summary(rows: list[dict]) -> None:
    tracked_rows = [r for r in rows if r["tracked"]]
    by_source: dict[str, set] = defaultdict(set)
    for r in tracked_rows:
        by_source[r["source"]].add(r["league"])

    print(f"\nTracked-league coverage today: "
          f"api_football={len(by_source.get('api_football', set()))} leagues, "
          f"odds_api={len(by_source.get('odds_api', set()))} leagues")
    only_af = by_source.get("api_football", set()) - by_source.get("odds_api", set())
    only_oa = by_source.get("odds_api", set()) - by_source.get("api_football", set())
    both = by_source.get("api_football", set()) & by_source.get("odds_api", set())
    print(f"  both providers:      {sorted(both)}")
    print(f"  api_football only:   {sorted(only_af)}")
    print(f"  odds_api only:       {sorted(only_oa)}")

    all_leagues = len({r["league"] for r in rows})
    print(f"\nFull landscape (unfiltered, API-Football side): {all_leagues} leagues/competitions total today")


def main(odds_date: str) -> None:
    path = DAILY_ODDS_DIR / f"{odds_date}.json"
    if not path.exists():
        print(f"No daily odds file at {path} -- run fetch_daily_odds.py first.", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        observations = json.load(f)

    rows = summarize(odds_date, observations)
    append_log(odds_date, rows)
    print(f"Appended {len(rows)} rows to {LOG_PATH}")
    print_summary(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    main(args.date)
