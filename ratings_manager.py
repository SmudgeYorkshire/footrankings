"""
Team ratings I/O.

Ratings are stored as CSV files in the `ratings/` directory,
one file per league: ratings/{league_id}.csv

CSV columns:
    team        – team name as shown on Opta (used for display)
    alias       – alternative name used by TheSportsDB (leave blank if identical)
    opta_rating – Opta Power Ranking score (0–100 scale)

When looking up a team from TheSportsDB standings/fixtures, the code
checks `alias` first (if set), then `team`.

Default ratings (when no CSV exists yet) are estimated from season stats:
a composite score based on points, goal difference, and goals scored,
scaled to roughly the 70–100 range.
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
            df["alias"] = df["alias"].fillna("")
            return df[["team", "alias", "opta_rating"]]

    return _defaults_from_standings(standings, csv_path)


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
    to the same rating, so TheSportsDB names resolve correctly.
    """
    lookup: dict[str, float] = {}
    for _, row in ratings.iterrows():
        rating = row["opta_rating"]
        lookup[row["team"]] = rating
        alias = str(row.get("alias", "")).strip()
        if alias:
            lookup[alias] = rating
    return lookup


def _defaults_from_standings(standings: list[dict], csv_path: Path) -> pd.DataFrame:
    """
    Generate default Opta-like ratings from season stats and save to CSV.
    Uses a composite score (points + goal diff + goals for) scaled to 70-100.
    """
    rows = []
    for row in standings:
        played = int(row.get("intPlayed") or 0)
        pts    = int(row.get("intPoints") or 0)
        gd     = int(row.get("intGoalDifference") or 0)
        gf     = int(row.get("intGoalsFor") or 0)
        # Composite performance score (arbitrary but rank-preserving)
        score  = pts * 3 + gd * 2 + gf if played > 0 else 0
        rows.append({"team": row["strTeam"], "_score": score})

    if not rows:
        return pd.DataFrame(columns=["team", "opta_rating"])

    df = pd.DataFrame(rows)
    min_s, max_s = df["_score"].min(), df["_score"].max()
    if max_s > min_s:
        df["opta_rating"] = 70.0 + 30.0 * (df["_score"] - min_s) / (max_s - min_s)
    else:
        df["opta_rating"] = DEFAULT_OPTA

    df = df[["team", "opta_rating"]].copy()
    df["alias"] = ""
    df["opta_rating"] = df["opta_rating"].round(1)
    df[["team", "alias", "opta_rating"]].to_csv(csv_path, index=False)
    return df[["team", "alias", "opta_rating"]]
