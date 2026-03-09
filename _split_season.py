"""
Helpers for leagues with split seasons (regular season + conference rounds).

After the regular season ends at `split_round`, TheSportsDB returns TWO sets
of standings rows for the same league:
  - Pre-split rows  (intPlayed == split_round): final regular-season table,
    with strDescription = "Championship round" or "Relegation Round"
  - Current rows    (intPlayed >  split_round): live conference standings

This module detects that phase, identifies which conference each team belongs
to, and provides helpers to filter fixtures by conference.
"""


def get_split_info(standings: list[dict], split_round: int) -> dict | None:
    """
    Returns None if still in regular season (no conference data yet).

    Returns a dict with:
        champ_teams   – set of team names in the Championship conference
        relg_teams    – set of team names in the Relegation conference
        pre_split     – list of end-of-regular-season rows (sorted by rank)
        champ_current – current Championship conference rows (sorted by rank)
        relg_current  – current Relegation conference rows (sorted by rank)
    """
    split_rows   = [r for r in standings if int(r.get("intPlayed") or 0) == split_round]
    current_rows = [r for r in standings if int(r.get("intPlayed") or 0) >  split_round]

    if not split_rows or not current_rows:
        return None  # Regular season still running

    champ_teams = {
        r["strTeam"] for r in split_rows
        if "championship" in (r.get("strDescription") or "").lower()
    }
    relg_teams = {
        r["strTeam"] for r in split_rows
        if "relegation" in (r.get("strDescription") or "").lower()
    }

    if not champ_teams or not relg_teams:
        return None  # Cannot identify conferences

    def _sort(rows):
        return sorted(rows, key=lambda r: int(r.get("intRank") or 99))

    return {
        "champ_teams":   champ_teams,
        "relg_teams":    relg_teams,
        "pre_split":     _sort(split_rows),
        "champ_current": _sort([r for r in current_rows if r["strTeam"] in champ_teams]),
        "relg_current":  _sort([r for r in current_rows if r["strTeam"] in relg_teams]),
    }


def conference_fixtures(fixtures: list[dict], teams: set[str]) -> list[dict]:
    """Return only fixtures where BOTH teams are in the given set."""
    return [
        f for f in fixtures
        if f.get("strHomeTeam") in teams and f.get("strAwayTeam") in teams
    ]
