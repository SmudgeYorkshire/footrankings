"""
Daily finish-position-probability snapshot for every league.

Meant to run once a day (e.g. via a scheduled job) and append one row per
team to history/{tsdb_id}.csv with that day's simulated probability of
finishing in each position. Stores the FULL position matrix (not just
title) so relegation/European-spot charts can be added later with zero
backfill gap — the data will already be there from whenever this started
running.

Mirrors football_rankings.py's own "Season finish probabilities" logic
exactly, so the history matches what the live site would have shown that
day: pre-split (or non-split) leagues simulate the whole table; once a
split-format league has actually split, position probabilities come from
the Championship conference simulation instead (that's where the title
race happens post-split).
"""

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from config import LEAGUES, DEFAULT_N_SIMULATIONS, DEFAULT_HOME_ADVANTAGE, get_current_season
from api_football_fetcher import ApiFootballClient
from ratings_manager import load_ratings
from _split_season import get_split_info, compute_full_standings, conference_fixtures
from simulator import simulate_season

HISTORY_DIR = "history"


def _load_presplit_snapshot(league_id, season):
    for path in (f"cache/presplit_{league_id}_{season}.json", f"presplit/{league_id}_{season}.json"):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None


def snapshot_league(cfg: dict, key: str, client: ApiFootballClient):
    """Return a position-probability DataFrame for one league, or None if
    there's not enough data yet (season hasn't started, etc.)."""
    league_id = cfg["id"]
    ratings_id = cfg.get("tsdb_id", cfg["id"])
    season = cfg.get("af_season") or get_current_season(cfg["season_type"])

    roster = client.get_standings(league_id, season)
    if not roster:
        return None
    played, remaining = client.get_fixtures(league_id, season)
    standings = compute_full_standings(roster, played)
    if not standings:
        return None

    ratings_df = load_ratings(ratings_id, standings)
    home_advantage = cfg.get("home_advantage", DEFAULT_HOME_ADVANTAGE)
    tiebreakers = cfg.get("tiebreakers")

    split_round = cfg.get("split_round")
    split_info = None
    if split_round:
        presplit = _load_presplit_snapshot(league_id, season)
        split_info = get_split_info(
            standings, split_round,
            n_champ=cfg.get("n_champ"), n_mid=cfg.get("n_mid", 0),
            pts_factor=cfg.get("pts_factor", 1.0), presplit=presplit,
        )

    if split_info:
        target_standings = split_info["champ_current"]
        target_fixtures = conference_fixtures(remaining, split_info["champ_teams"])
    else:
        target_standings = standings
        target_fixtures = remaining

    if not target_standings:
        return None

    return simulate_season(
        standings=target_standings,
        remaining_fixtures=target_fixtures,
        ratings=ratings_df,
        n_sim=DEFAULT_N_SIMULATIONS,
        home_advantage=home_advantage,
        tiebreakers=tiebreakers,
        played_fixtures=played,
    )


def append_snapshot(tsdb_id, probs, date_str) -> dict[str, float] | None:
    """Append today's row per team; returns {team: title_prob} for the
    swing-detection summary."""
    if probs is None or probs.empty:
        return None
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, f"{tsdb_id}.csv")
    n_positions = len(probs.columns)
    fieldnames = ["date", "team"] + [f"pos_{i}" for i in range(1, n_positions + 1)]

    # Idempotent per day: drop any existing rows for date_str before writing
    # fresh ones, so re-running the same day (manual trigger, retry, etc.)
    # replaces that day's numbers instead of duplicating them — duplicate
    # (date, team) pairs would break the history chart's pivot() later.
    existing_rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing_rows = [r for r in csv.DictReader(f) if r["date"] != date_str]

    title_probs = {}
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)
        for team in probs.index:
            row = {"date": date_str, "team": team}
            for i, col in enumerate(probs.columns, 1):
                row[f"pos_{i}"] = round(float(probs.loc[team, col]), 4)
            writer.writerow(row)
            title_probs[team] = row["pos_1"]
    return title_probs


def _yesterdays_title_probs(tsdb_id, date_str) -> dict[str, float]:
    """Read the most recent prior date's pos_1 values, for swing detection."""
    path = os.path.join(HISTORY_DIR, f"{tsdb_id}.csv")
    if not os.path.exists(path):
        return {}
    rows_by_date: dict[str, dict[str, float]] = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["date"] == date_str:
                continue  # today's own row (if re-run) shouldn't count as "yesterday"
            rows_by_date.setdefault(row["date"], {})[row["team"]] = float(row["pos_1"])
    if not rows_by_date:
        return {}
    latest_prior = max(rows_by_date)
    return rows_by_date[latest_prior]


def main():
    key = os.getenv("API_FOOTBALL_KEY", "")
    client = ApiFootballClient(api_key=key)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ok, skipped, failed = 0, 0, []
    swings = []  # (league_name, team, delta, from_pct, to_pct)

    for league_name, cfg in LEAGUES.items():
        try:
            before = _yesterdays_title_probs(cfg.get("tsdb_id", cfg["id"]), date_str)
            probs = snapshot_league(cfg, key, client)
            title_probs = append_snapshot(cfg.get("tsdb_id", cfg["id"]), probs, date_str)
            if title_probs is None:
                skipped += 1
                print(f"  SKIP {league_name} (no data yet)")
                continue
            ok += 1
            print(f"  OK   {league_name}")
            for team, new_p in title_probs.items():
                old_p = before.get(team)
                if old_p is not None and abs(new_p - old_p) >= 0.10:  # >=10pp swing
                    swings.append((league_name, team, new_p - old_p, old_p, new_p))
        except Exception as e:
            failed.append((league_name, str(e)))
            print(f"  FAIL {league_name}: {e}")
        time.sleep(1.2)  # avoid the burst-block seen on rapid sequential API calls

    print(f"\n{ok}/{len(LEAGUES)} leagues snapshotted, {skipped} skipped, {len(failed)} failed")
    if failed:
        print("Failures:")
        for name, err in failed:
            print(f"  - {name}: {err}")

    if swings:
        swings.sort(key=lambda s: abs(s[2]), reverse=True)
        print(f"\nBig title-probability swings today (>=10pp):")
        for league_name, team, delta, old_p, new_p in swings:
            arrow = "▲" if delta > 0 else "▼"
            print(f"  {arrow} {league_name}: {team}  {old_p:.0%} -> {new_p:.0%}")
    else:
        print("\nNo big title-probability swings today (>=10pp).")


if __name__ == "__main__":
    main()
