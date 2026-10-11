"""
Daily API-Football odds-coverage log.

Supersedes odds_coverage_snapshot.py (deleted) -- that script hit
API-Football directly; this one reads fetch_daily_odds.py's already-pulled,
already-normalized daily_odds/{date}.json instead, so there's exactly one
place that calls the odds API per day. fetch_daily_odds.py's pull is itself
unfiltered (every league/competition that has odds, tagged
"tracked": True/False, not just the 54 we track), so this log covers the
same broad landscape the old script did (national teams, South American
leagues, etc.) as well as our own tracked leagues specifically.

Originally this compared API-Football against The Odds API side by side
(removed 2026-10-11 -- see club_odds_calibration_pipeline.md in project
memory). Now that API-Football is the only source, this instead tracks
ITS OWN coverage day over day -- which leagues it starts/stops carrying
odds for, and how each tracked league's fixture count changes -- so a
real coverage drop (vs. just an ordinary day with fewer matches) is
visible at a glance.

Appends one row per (date, source, league) to odds_coverage/comparison_log.csv:
    date, source, league, tracked, n_fixtures, avg_bookmakers

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


def append_log(odds_date: str, rows: list[dict]) -> list[dict]:
    """Appends, but first drops any existing rows for this same date -- so
    re-running the same day (a manual workflow_dispatch re-trigger, or just
    testing locally) replaces that day's rows instead of duplicating them.
    Returns the pre-existing (earlier-dated) rows, so the caller can diff
    today's coverage against the most recent prior run without a second
    file read."""
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
    return existing


def print_summary(odds_date: str, rows: list[dict], existing_rows: list[dict]) -> None:
    tracked = {r["league"]: r["n_fixtures"] for r in rows if r["tracked"]}
    all_leagues = len({r["league"] for r in rows})
    print(f"\nTracked-league coverage today ({odds_date}): {len(tracked)} leagues, "
          f"{sum(tracked.values())} fixtures")
    print(f"Full landscape (unfiltered): {all_leagues} leagues/competitions today")

    # Day-over-day: what API-Football itself started/stopped covering,
    # compared to the most recent earlier run in the log (same source only
    # -- the log still has old odds_api rows mixed in from before it was
    # removed, and comparing against those wouldn't be apples-to-apples).
    past_dates = sorted({r["date"] for r in existing_rows if r["date"] < odds_date}, reverse=True)
    if not past_dates:
        print("\n(No earlier run in the log yet to compare against.)")
        return
    prev_date = past_dates[0]
    prev_tracked = {
        r["league"]: int(r["n_fixtures"])
        for r in existing_rows
        if r["date"] == prev_date and r.get("source") == "api_football" and r.get("tracked") == "True"
    }
    gained = sorted(set(tracked) - set(prev_tracked))
    lost = sorted(set(prev_tracked) - set(tracked))
    changed = {
        l: (prev_tracked[l], tracked[l])
        for l in set(tracked) & set(prev_tracked)
        if prev_tracked[l] != tracked[l]
    }
    print(f"\nVs. last logged run ({prev_date}):")
    print(f"  newly covered leagues: {gained if gained else 'none'}")
    print(f"  dropped leagues:       {lost if lost else 'none'}")
    if changed:
        print("  fixture-count changes:")
        for l in sorted(changed):
            p, t = changed[l]
            delta = t - p
            print(f"    {l}: {p} -> {t} ({'+' if delta >= 0 else ''}{delta})")


def main(odds_date: str) -> None:
    path = DAILY_ODDS_DIR / f"{odds_date}.json"
    if not path.exists():
        print(f"No daily odds file at {path} -- run fetch_daily_odds.py first.", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        observations = json.load(f)

    rows = summarize(odds_date, observations)
    existing_rows = append_log(odds_date, rows)
    print(f"Appended {len(rows)} rows to {LOG_PATH}")
    print_summary(odds_date, rows, existing_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    main(args.date)
