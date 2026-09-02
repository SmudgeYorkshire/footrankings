"""
Validates the site's match-outcome model against real closing bookmaker
odds, using football-data.co.uk's free historical CSV downloads (no
scraping/ToS concerns -- these are meant to be downloaded in bulk).

For every mapped league/season, this:
  1. Downloads (and caches) football-data.co.uk's match results + closing
     odds.
  2. De-vigs the closing odds (market average across many bookmakers)
     into fair probabilities.
  3. Computes our own model's home/draw/away probability for the same
     fixture using simulator.fixture_odds() with TODAY's Opta ratings
     (same hindsight-bias caveat as backtest.py -- meaningful for
     relative comparison, optimistic in absolute terms).
  4. Scores both against the real result with the (3-outcome) Brier
     score and reports the gap, per league and overall.

This does NOT change any live prediction code -- it's a standalone
diagnostic, like backtest.py.

Coverage: football-data.co.uk only covers ~21 of our 54 tracked leagues
(the "big" Western European leagues plus a handful of others) -- the
long tail (Baltics, Balkans, Caucasus, micro-states, etc.) has no
closing-odds source and stays unvalidated by this script.

Usage:
    py odds_validation.py                          # all mapped leagues, default seasons
    py odds_validation.py --league "English Premier League"
    py odds_validation.py --seasons 2023 2024 2025
"""

import argparse
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from config import LEAGUES
from ratings_manager import load_ratings
from simulator import fixture_odds

CACHE_DIR = Path("cache")
BASE_URL = "https://www.football-data.co.uk"
DEFAULT_SEASONS = [2023, 2024, 2025]

# Our LEAGUES key -> ("big", code) for a per-season file at
# mmz4281/{YYYY}/{code}.csv, or ("extra", code) for one combined
# multi-season file at new/{code}.csv. Every code below was verified live
# (HTTP 200, real rows) before being added -- see the conversation this
# was built in for the verification transcript.
FOOTBALL_DATA_LEAGUES: dict[str, tuple[str, str]] = {
    "English Premier League": ("big", "E0"),
    "Italian Serie A": ("big", "I1"),
    "Spanish La Liga": ("big", "SP1"),
    "German Bundesliga": ("big", "D1"),
    "French Ligue 1": ("big", "F1"),
    "Belgian Pro League": ("big", "B1"),
    "Dutch Eredivisie": ("big", "N1"),
    "Greek Super League 1": ("big", "G1"),
    "Portuguese Primeira Liga": ("big", "P1"),
    "Scottish Premiership": ("big", "SC0"),
    "Turkish Super Lig": ("big", "T1"),
    "Austrian Bundesliga": ("extra", "AUT"),
    "Danish Superliga": ("extra", "DNK"),
    "Finnish Veikkausliiga": ("extra", "FIN"),
    "Irish Premier Division": ("extra", "IRL"),
    "Norwegian Eliteserien": ("extra", "NOR"),
    "Polish Ekstraklasa": ("extra", "POL"),
    "Romanian Liga I": ("extra", "ROU"),
    "Russian Football Premier League": ("extra", "RUS"),
    "Swedish Allsvenskan": ("extra", "SWE"),
    "Swiss Super League": ("extra", "SWZ"),
}

# football-data.co.uk's own team-name spelling -> our ratings CSV's
# spelling, for every mismatch found while validating this script against
# the mapped leagues. Extend this as more leagues/seasons surface new
# stragglers -- unmatched names are printed (not silently dropped) so
# they're easy to spot.
TEAM_NAME_OVERRIDES: dict[str, str] = {
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Nott'm Forest": "Nottingham Forest",
}


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


def _big_season_code(year: int) -> str:
    """2025 -> '2526' (the 2025-26 season, football-data.co.uk's own
    two-digit-two-digit file-naming convention)."""
    return f"{str(year)[2:]}{str(year + 1)[2:]}"


def _cached_download(url: str, cache_name: str, ttl: float | None) -> str | None:
    """Plain-text file cache (these are CSVs, not JSON) -- ttl=None means
    cache forever once fetched (a completed past season's file never
    changes)."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists():
        if ttl is None:
            return path.read_text(encoding="utf-8-sig")
        import time
        if time.time() - path.stat().st_mtime < ttl:
            return path.read_text(encoding="utf-8-sig")
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[odds_validation] WARNING: download failed for {url}: {e}", file=sys.stderr)
        return path.read_text(encoding="utf-8-sig") if path.exists() else None
    text = resp.text
    path.write_text(text, encoding="utf-8")
    return text


def fetch_matches(league_name: str, seasons: list[int]) -> pd.DataFrame:
    """[{date, home, away, fthg, ftag, ftr, avg_h, avg_d, avg_a}, ...] for
    every match football-data.co.uk has for this league in the requested
    seasons. Prefers CLOSING market-average odds (AvgCH/D/A) over
    pre-match (AvgH/D/A) when both are present -- closing is the market's
    final, most-informed price."""
    if league_name not in FOOTBALL_DATA_LEAGUES:
        return pd.DataFrame()
    source, code = FOOTBALL_DATA_LEAGUES[league_name]

    if source == "big":
        frames = []
        for year in seasons:
            season_code = _big_season_code(year)
            is_current = year == max(seasons)
            text = _cached_download(
                f"{BASE_URL}/mmz4281/{season_code}/{code}.csv",
                f"football_data_{code}_{season_code}.csv",
                ttl=(6 * 3600 if is_current else None),
            )
            if not text:
                continue
            from io import StringIO
            df = pd.read_csv(StringIO(text), low_memory=False)
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        raw = pd.concat(frames, ignore_index=True)
    else:
        text = _cached_download(
            f"{BASE_URL}/new/{code}.csv", f"football_data_{code}_all.csv", ttl=6 * 3600,
        )
        if not text:
            return pd.DataFrame()
        from io import StringIO
        raw = pd.read_csv(StringIO(text), low_memory=False)
        # "Winter" leagues (season spans two calendar years) are recorded
        # as e.g. "2025/2026"; "summer" leagues (season fits in one) are
        # recorded as a plain "2025" -- matches config.py's own
        # season_type distinction for the same reason.
        if LEAGUES[league_name].get("season_type") == "summer":
            season_strs = {str(y) for y in seasons}
        else:
            season_strs = {f"{y}/{y + 1}" for y in seasons}
        raw = raw[raw["Season"].astype(str).isin(season_strs)]
        raw = raw.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG", "Res": "FTR"})

    def _col(df: pd.DataFrame, closing: str, opening: str) -> pd.Series:
        if closing in df.columns and df[closing].notna().any():
            return pd.to_numeric(df[closing], errors="coerce")
        if opening in df.columns:
            return pd.to_numeric(df[opening], errors="coerce")
        return pd.Series(np.nan, index=df.index)

    out = pd.DataFrame({
        "date": raw.get("Date"),
        "home": raw["HomeTeam"],
        "away": raw["AwayTeam"],
        "fthg": pd.to_numeric(raw["FTHG"], errors="coerce"),
        "ftag": pd.to_numeric(raw["FTAG"], errors="coerce"),
        "ftr": raw["FTR"],
        "avg_h": _col(raw, "AvgCH", "AvgH"),
        "avg_d": _col(raw, "AvgCD", "AvgD"),
        "avg_a": _col(raw, "AvgCA", "AvgA"),
    })
    out = out.dropna(subset=["home", "away", "fthg", "ftag", "avg_h", "avg_d", "avg_a"])
    return out.reset_index(drop=True)


def match_team_name(name: str, ratings_df: pd.DataFrame, unmatched: set[str]) -> str | None:
    """football-data.co.uk name -> our ratings CSV's team name, or None
    (and records `name` into `unmatched`) if nothing lines up."""
    if name in TEAM_NAME_OVERRIDES:
        name = TEAM_NAME_OVERRIDES[name]
    norm_target = _normalize(name)
    for _, row in ratings_df.iterrows():
        if _normalize(row["team"]) == norm_target or (row["alias"] and _normalize(row["alias"]) == norm_target):
            return row["team"]
    # fuzzy: one side a whole-word prefix/substring of the other
    for _, row in ratings_df.iterrows():
        cand = _normalize(row["team"])
        if cand.startswith(norm_target) or norm_target.startswith(cand):
            return row["team"]
    unmatched.add(name)
    return None


def devig(oh: float, od: float, oa: float) -> tuple[float, float, float]:
    """Decimal odds -> de-vigged (fair) probabilities via proportional
    normalization (divide out the bookmaker's overround)."""
    ph, pd_, pa = 1.0 / oh, 1.0 / od, 1.0 / oa
    total = ph + pd_ + pa
    return ph / total, pd_ / total, pa / total


def brier(p_home: float, p_draw: float, p_away: float, ftr: str) -> float:
    actual = {"H": (1.0, 0.0, 0.0), "D": (0.0, 1.0, 0.0), "A": (0.0, 0.0, 1.0)}[ftr]
    return (p_home - actual[0]) ** 2 + (p_draw - actual[1]) ** 2 + (p_away - actual[2]) ** 2


def validate_league(league_name: str, seasons: list[int]) -> dict | None:
    cfg = LEAGUES[league_name]
    ratings_id = cfg.get("tsdb_id", cfg["id"])
    ratings_df = load_ratings(ratings_id, [])
    matches = fetch_matches(league_name, seasons)
    if matches.empty:
        return None

    unmatched: set[str] = set()
    matches["home_m"] = matches["home"].apply(lambda n: match_team_name(n, ratings_df, unmatched))
    matches["away_m"] = matches["away"].apply(lambda n: match_team_name(n, ratings_df, unmatched))
    scored = matches.dropna(subset=["home_m", "away_m"])

    if scored.empty:
        return {"league": league_name, "n": 0, "unmatched": unmatched}

    fixtures = [{"strHomeTeam": r["home_m"], "strAwayTeam": r["away_m"]} for _, r in scored.iterrows()]
    home_advantage = cfg.get("home_advantage", 1.20)
    model_odds = fixture_odds(fixtures, ratings_df, home_advantage=home_advantage)

    model_briers, market_briers = [], []
    for (_, row), mo in zip(scored.iterrows(), model_odds):
        model_briers.append(brier(mo["home_win"], mo["draw"], mo["away_win"], row["ftr"]))
        mh, md, ma = devig(row["avg_h"], row["avg_d"], row["avg_a"])
        market_briers.append(brier(mh, md, ma, row["ftr"]))

    return {
        "league": league_name,
        "n": len(scored),
        "model_brier": float(np.mean(model_briers)),
        "market_brier": float(np.mean(market_briers)),
        "unmatched": unmatched,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default=None, help="Validate a single league by name")
    ap.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    args = ap.parse_args()

    leagues = [args.league] if args.league else list(FOOTBALL_DATA_LEAGUES.keys())

    results = []
    all_unmatched: dict[str, set[str]] = {}
    for name in leagues:
        r = validate_league(name, args.seasons)
        if r is None:
            print(f"{name:35s}  no data")
            continue
        if r.get("unmatched"):
            all_unmatched[name] = r["unmatched"]
        if r["n"] == 0:
            print(f"{name:35s}  0 matches scored (all names unmatched)")
            continue
        gap = r["model_brier"] - r["market_brier"]
        print(f"{name:35s}  n={r['n']:5d}  our={r['model_brier']:.4f}  market={r['market_brier']:.4f}  gap={gap:+.4f}")
        results.append(r)

    if results:
        total_n = sum(r["n"] for r in results)
        weighted_our = sum(r["model_brier"] * r["n"] for r in results) / total_n
        weighted_mkt = sum(r["market_brier"] * r["n"] for r in results) / total_n
        print("-" * 90)
        print(f"{'OVERALL (n-weighted)':35s}  n={total_n:5d}  our={weighted_our:.4f}  market={weighted_mkt:.4f}  gap={weighted_our - weighted_mkt:+.4f}")

    if all_unmatched:
        print("\nUnmatched team names (add to TEAM_NAME_OVERRIDES):")
        for league, names in all_unmatched.items():
            print(f"  {league}: {sorted(names)}")


if __name__ == "__main__":
    main()
