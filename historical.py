"""
Historical (completed) season data — fetch + shape for both the site's
History tab and backtest.py's calibration work.

Unlike the live season, a completed past season never changes, so this
leans on the provider's OWN standings table directly (get_standings_groups)
rather than self-computing from fixtures — there's no live-lag risk once
a season is finished, and the provider's per-conference groups are already
correctly split/ranked for split-format leagues without needing to
reconstruct their point-carryover rules.
"""

from api_football_fetcher import ApiFootballClient
from config import CACHE_TTL_HISTORICAL


def fetch_historical_season(cfg: dict, season_year: int, api_key: str) -> dict:
    """
    Fetch one completed past season for a league.

    Returns:
        {
            "season_year": int,
            "played_fixtures": list[dict],
            "groups": list[{"label": str, "rows": list[dict]}],
        }
    "groups" has one entry for a normal league, or multiple for a
    split-format league (largest-average-points group first).
    """
    client = ApiFootballClient(api_key=api_key)
    league_id = cfg["id"]

    played, _remaining = client.get_fixtures(league_id, season_year, ttl=CACHE_TTL_HISTORICAL)
    raw_groups = client.get_standings_groups(league_id, season_year, ttl=CACHE_TTL_HISTORICAL)

    total_teams = len({r["strTeam"] for g in raw_groups for r in g if r.get("strTeam")})
    # Drop the provider's "all teams combined" pseudo-group, if present —
    # it's not a real conference, just every team's own final row again.
    real_groups = [g for g in raw_groups if g and len(g) < total_teams] or raw_groups

    def _avg_pts(g: list[dict]) -> float:
        pts = [int(r.get("intPoints") or 0) for r in g]
        return sum(pts) / len(pts) if pts else 0.0

    real_groups.sort(key=_avg_pts, reverse=True)

    if len(real_groups) <= 1:
        labels = ["Final Table"]
    elif len(real_groups) == 2:
        labels = ["Top Group", "Bottom Group"]
    else:
        labels = ["Top Group"] + [f"Middle Group {i}" for i in range(1, len(real_groups) - 1)] + ["Bottom Group"]

    groups = [{"label": lbl, "rows": g} for lbl, g in zip(labels, real_groups)]

    return {
        "season_year": season_year,
        "played_fixtures": played,
        "groups": groups,
    }
