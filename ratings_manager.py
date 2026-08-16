"""
Team ratings I/O.

Ratings are stored as CSV files in the `ratings/` directory,
one file per league: ratings/{league_id}.csv

CSV columns:
    team        – team name as shown on Opta (used for display)
    alias       – alternative name used by the live-data provider (leave blank if identical)
    opta_rating – Opta Power Ranking score (0–100 scale)

When looking up a team from the live-data provider's standings/fixtures,
the code checks `alias` first (if set), then `team`.

Default ratings (when no CSV exists yet) are estimated from season stats:
a composite score based on goal difference and goals scored per game,
scaled to roughly the 68–82 range.
"""

import pandas as pd
from pathlib import Path

RATINGS_DIR = Path("ratings")
DEFAULT_OPTA = 75.0   # fallback for teams with no season data


def load_ratings(league_id: int, standings: list[dict]) -> pd.DataFrame:
    """
    Load Opta ratings for a league from CSV, or generate defaults from standings.
    Returns a DataFrame with columns: ['team', 'alias', 'opta_rating']
    """
    RATINGS_DIR.mkdir(exist_ok=True)
    csv_path = RATINGS_DIR / f"{league_id}.csv"

    if csv_path.exists():
        df = pd.read_csv(csv_path, dtype=str)
        if "team" in df.columns and "opta_rating" in df.columns:
            if "alias" not in df.columns:
                df["alias"] = ""
            df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
            # A malformed cell (typo, stray text) would otherwise reach the
            # simulator as NaN and crash the whole league's page outright
            # (numpy's negative_binomial rejects a NaN n) — fall back to the
            # default rating for just that row instead.
            if df["opta_rating"].isna().any():
                df["opta_rating"] = df["opta_rating"].fillna(DEFAULT_OPTA)
            df["alias"] = df["alias"].fillna("")
            return df[["team", "alias", "opta_rating"]]
        # File exists but doesn't look like a ratings CSV (bad header, a
        # mid-edit save, ...) — return usable estimates for this page load
        # without persisting over whatever's actually on disk; a human
        # should fix or intentionally reset the file (see admin.py).
        return _defaults_from_standings(standings, csv_path, persist=False)

    return _defaults_from_standings(standings, csv_path, persist=True)


def save_ratings(league_id: int, ratings: pd.DataFrame) -> None:
    """Persist ratings DataFrame to CSV."""
    RATINGS_DIR.mkdir(exist_ok=True)
    csv_path = RATINGS_DIR / f"{league_id}.csv"
    out = ratings.copy()
    if "alias" not in out.columns:
        out["alias"] = ""
    out[["team", "alias", "opta_rating"]].to_csv(csv_path, index=False)


def build_lookup(ratings: pd.DataFrame) -> dict[str, float]:
    """
    Build a {name: opta_rating} dict that maps both 'team' and 'alias'
    to the same rating, so the live-data provider's names resolve correctly.
    """
    lookup: dict[str, float] = {}
    for _, row in ratings.iterrows():
        rating = row["opta_rating"]
        lookup[row["team"]] = rating
        alias = str(row.get("alias", "")).strip()
        if alias:
            lookup[alias] = rating
    return lookup


def check_coverage(standings: list[dict], ratings: pd.DataFrame) -> list[str]:
    """
    Return a list of team names from standings that have no matching rating
    entry (neither via 'team' nor 'alias').  These teams will fall back to
    the default attack/defense value during simulation.
    """
    known: set[str] = set()
    for _, row in ratings.iterrows():
        known.add(str(row["team"]).strip())
        alias = str(row.get("alias", "")).strip()
        if alias:
            known.add(alias)
    return [
        s["strTeam"] for s in standings
        if s.get("strTeam") and s["strTeam"] not in known
    ]


def _defaults_from_standings(standings: list[dict], csv_path: Path, persist: bool = True) -> pd.DataFrame:
    """
    Generate default Opta-like ratings from season stats, optionally saving
    to CSV. Uses a composite score (goal diff + goals for per game) scaled
    to roughly 68-82.

    persist=False computes the same estimates without writing csv_path —
    used when an existing file couldn't be read as ratings, so a bad file
    isn't silently clobbered by a page load; only the "no file yet" path
    and an explicit admin reset actually persist.
    """
    rows = []
    for row in standings:
        played = int(row.get("intPlayed") or 0)
        gd     = int(row.get("intGoalDifference") or 0)
        gf     = int(row.get("intGoalsFor") or 0)
        # Use goal difference per game as the primary signal (less circular than pts).
        # Goals for per game added as a secondary signal to break GD ties.
        score  = (gd * 10 + gf) / played if played > 0 else 0
        rows.append({"team": row["strTeam"], "_score": score})

    if not rows:
        return pd.DataFrame(columns=["team", "opta_rating"])

    df = pd.DataFrame(rows)
    min_s, max_s = df["_score"].min(), df["_score"].max()
    if max_s > min_s:
        df["opta_rating"] = 68.0 + 14.0 * (df["_score"] - min_s) / (max_s - min_s)
    else:
        df["opta_rating"] = DEFAULT_OPTA

    df = df[["team", "opta_rating"]].copy()
    df["alias"] = ""
    df["opta_rating"] = df["opta_rating"].round(1)
    if persist:
        df[["team", "alias", "opta_rating"]].to_csv(csv_path, index=False)
    return df[["team", "alias", "opta_rating"]]
