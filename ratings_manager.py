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
CLUB_ADJUSTMENTS_PATH = RATINGS_DIR / "club_rating_adjustments.csv"


def load_club_rating_adjustments() -> dict[str, float]:
    """{team: adjustment} fit daily by club_rating_calibration.py from real
    odds, refit from scratch each run (never accumulated) -- mirrors
    nations_league_simulator.load_nl_rating_adjustments()'s exact pattern."""
    try:
        df = pd.read_csv(CLUB_ADJUSTMENTS_PATH)
    except FileNotFoundError:
        return {}
    return dict(zip(df["team"], df["adjustment"]))


def load_ratings(league_id: int, standings: list[dict], apply_adjustments: bool = True) -> pd.DataFrame:
    """
    Load Opta ratings for a league from CSV, or generate defaults from standings.
    Returns a DataFrame with columns: ['team', 'alias', 'opta_rating']

    apply_adjustments=True (the default, used by every live page) overlays
    club_rating_calibration.py's odds-fitted adjustment on top of the raw
    CSV value, THEN (2026-11-05) blends in club_odds_ratings.py's
    persistent Odds-Implied rating wherever a club has enough real
    evidence (club_odds_ratings.blend_with_live_rating -- confidence-
    weighted, degrades to the adjusted Opta value unchanged for a club
    with no/thin odds history). club_rating_calibration.py itself calls
    with apply_adjustments=False to fit against the true raw baseline
    each run -- fitting against an already-adjusted value would compound
    indefinitely instead of refitting from scratch. club_odds_ratings.py's
    OWN internal fitting (main()/_load_tracked_ratings_with_source())
    ALSO always calls with apply_adjustments=False for the identical
    reason -- the blend below must never be visible to either fitting
    path, only to the live-page default.
    """
    raw = _load_raw_ratings(league_id, standings)
    if not apply_adjustments:
        return raw

    # Local import -- club_odds_ratings.py itself imports load_ratings
    # FROM this module (for its own cross-league field resolution), so a
    # top-level import here would be circular. Cheap after the first call
    # (Python caches the module), so no real cost to doing it per call.
    from club_odds_ratings import blend_with_live_rating, _load_state

    adjustments = load_club_rating_adjustments()
    out = raw.copy()
    if adjustments:
        out["opta_rating"] = out.apply(
            lambda r: r["opta_rating"] + adjustments.get(r["team"], adjustments.get(str(r.get("alias", "")), 0.0)),
            axis=1,
        )
    odds_state = _load_state()
    out["opta_rating"] = out.apply(
        lambda r: blend_with_live_rating(str(league_id), r["team"], r["opta_rating"], odds_state), axis=1,
    )
    return out


def _load_raw_ratings(league_id: int, standings: list[dict]) -> pd.DataFrame:
    RATINGS_DIR.mkdir(exist_ok=True)
    csv_path = RATINGS_DIR / f"{league_id}.csv"

    if csv_path.exists():
        df = pd.read_csv(csv_path, dtype=str)
        if "team" in df.columns and "opta_rating" in df.columns:
            if "alias" not in df.columns:
                df["alias"] = ""
            if "opta_scrape_alias" not in df.columns:
                df["opta_scrape_alias"] = ""
            df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
            # A malformed cell (typo, stray text) would otherwise reach the
            # simulator as NaN and crash the whole league's page outright
            # (numpy's negative_binomial rejects a NaN n) — fall back to the
            # default rating for just that row instead.
            if df["opta_rating"].isna().any():
                df["opta_rating"] = df["opta_rating"].fillna(DEFAULT_OPTA)
            df["alias"] = df["alias"].fillna("")
            df["opta_scrape_alias"] = df["opta_scrape_alias"].fillna("")
            return df[["team", "alias", "opta_rating", "opta_scrape_alias"]]
        # File exists but doesn't look like a ratings CSV (bad header, a
        # mid-edit save, ...) — return usable estimates for this page load
        # without persisting over whatever's actually on disk; a human
        # should fix or intentionally reset the file (see admin.py).
        return _defaults_from_standings(standings, csv_path, persist=False)

    return _defaults_from_standings(standings, csv_path, persist=True)


def save_ratings(league_id: int, ratings: pd.DataFrame) -> None:
    """Persist ratings DataFrame to CSV. Preserves opta_scrape_alias if the
    incoming DataFrame has it (e.g. admin.py's ratings editor round-tripping
    load_ratings' own output) -- dropping it here would silently erase every
    club's Club Power Ranking scrape-name match on the next save, even
    though the editor never exposes that column for hand-editing."""
    RATINGS_DIR.mkdir(exist_ok=True)
    csv_path = RATINGS_DIR / f"{league_id}.csv"
    out = ratings.copy()
    if "alias" not in out.columns:
        out["alias"] = ""
    if "opta_scrape_alias" not in out.columns:
        out["opta_scrape_alias"] = ""
    out[["team", "alias", "opta_rating", "opta_scrape_alias"]].to_csv(csv_path, index=False)


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
    df["opta_scrape_alias"] = ""
    return df[["team", "alias", "opta_rating", "opta_scrape_alias"]]
