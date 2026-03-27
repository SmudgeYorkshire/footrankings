"""
Helpers for leagues with split seasons (regular season + conference rounds).

After the regular season ends at `split_round`, TheSportsDB returns TWO sets
of standings rows for the same league:
  - Pre-split rows  (intPlayed == split_round): final regular-season table,
    with strDescription = "Championship round" or "Relegation Round"
  - Current rows    (intPlayed >  split_round): live conference standings

This module detects that phase, identifies which conference each team belongs
to, and provides helpers to filter fixtures by conference.

pts_factor values:
  1.0 – points carried over fully (most leagues)
  0.5 – points halved going into playoff (Belgium, Austria, Romania, Serbia)
  0.0 – points reset to zero (Malta Apertura/Clausura)
"""


def get_split_info(standings: list[dict], split_round: int,
                   n_champ: int = None, n_mid: int = 0,
                   pts_factor: float = 1.0,
                   presplit: list[dict] = None) -> dict | None:
    """
    Returns None if still in regular season (no conference data yet).

    Returns a dict with:
        champ_teams   – set of team names in the Championship conference
        mid_teams     – set of team names in the Middle conference (may be empty)
        relg_teams    – set of team names in the Relegation conference
        pre_split     – list of end-of-regular-season rows (sorted by rank)
        champ_current – current Championship conference rows (sorted by rank)
        mid_current   – current Middle conference rows (may be empty)
        relg_current  – current Relegation conference rows (sorted by rank)
        pts_factor    – float: 1.0 full / 0.5 halved / 0.0 reset

    presplit: optional saved snapshot of standings at exactly split_round; used
    as split_rows when TheSportsDB stops returning the pre-split rows after the
    split has started.
    """
    split_rows   = [r for r in standings if int(r.get("intPlayed") or 0) == split_round]
    current_rows = [r for r in standings if int(r.get("intPlayed") or 0) >  split_round]

    # Fallback A: TheSportsDB dropped the pre-split rows — use the saved snapshot
    if not split_rows and presplit:
        split_rows = list(presplit)

    # Fallback B: no snapshot either, but we know n_champ and have current rows
    # Derive group membership purely from current league rankings
    if not split_rows and current_rows and n_champ:
        split_rows = sorted(current_rows, key=lambda r: int(r.get("intRank") or 99))

    # Fallback C: regular season finished, split rounds not yet started
    # All teams sit at exactly split_round; use split_rows as a proxy for current_rows
    # so the split groups are shown (with 0 games played in split phase)
    if split_rows and not current_rows:
        current_rows = list(split_rows)

    if not split_rows or not current_rows:
        return None  # Regular season still running

    # Try to identify conferences from TheSportsDB strDescription
    champ_teams = {
        r["strTeam"] for r in split_rows
        if "championship" in (r.get("strDescription") or "").lower()
    }
    relg_teams = {
        r["strTeam"] for r in split_rows
        if "relegation" in (r.get("strDescription") or "").lower()
    }
    # Middle group: anything described as europa/play-off/conference/middle
    # that isn't championship or relegation
    _mid_keywords = ("europa", "play-off", "playoff", "conference", "middle")
    mid_teams = {
        r["strTeam"] for r in split_rows
        if any(kw in (r.get("strDescription") or "").lower() for kw in _mid_keywords)
        and r["strTeam"] not in champ_teams
        and r["strTeam"] not in relg_teams
    }

    # Fallback 1: use n_champ (+ n_mid) rank split when strDescription not available
    # Only reliable when split_rows contains ALL teams (no team has advanced yet)
    _split_team_set   = {r["strTeam"] for r in split_rows}
    _current_team_set = {r["strTeam"] for r in current_rows}
    _all_teams_in_split = not (_current_team_set - _split_team_set)
    if (not champ_teams or not relg_teams) and n_champ and _all_teams_in_split:
        sorted_split = sorted(split_rows, key=lambda r: int(r.get("intRank") or 99))
        champ_teams = {r["strTeam"] for r in sorted_split[:n_champ]}
        if n_mid:
            mid_teams  = {r["strTeam"] for r in sorted_split[n_champ:n_champ + n_mid]}
            relg_teams = {r["strTeam"] for r in sorted_split[n_champ + n_mid:]}
        else:
            relg_teams = {r["strTeam"] for r in sorted_split[n_champ:]}

    # Fallback 2: champ teams have already advanced past split_round;
    # split_rows contains only the relg/mid teams, current_rows only the champ teams
    if (not champ_teams or not relg_teams) and _current_team_set and _split_team_set:
        if not (_current_team_set & _split_team_set):   # disjoint → safe to assign
            champ_teams = _current_team_set
            relg_teams  = _split_team_set - mid_teams

    # Allow empty relg_teams when all remaining teams are in champ
    # (e.g. Moldova: 2 relg-playoff teams leave the main standings entirely)
    _only_champ_remaining = bool(
        champ_teams and not relg_teams
        and _current_team_set and _current_team_set <= champ_teams
    )
    if not champ_teams or (not relg_teams and not _only_champ_remaining):
        return None  # Cannot identify conferences

    def _sort(rows):
        return sorted(rows, key=lambda r: int(r.get("intRank") or 99))

    champ_current = _sort([r for r in current_rows if r["strTeam"] in champ_teams])
    mid_current   = _sort([r for r in current_rows if r["strTeam"] in mid_teams])
    relg_current  = _sort([r for r in current_rows if r["strTeam"] in relg_teams])
    # If relegation conference hasn't started yet, fall back to their split-round rows
    if not relg_current:
        relg_current = _sort([r for r in split_rows if r["strTeam"] in relg_teams])
    if not mid_current and mid_teams:
        mid_current = _sort([r for r in split_rows if r["strTeam"] in mid_teams])

    # pre_split: all teams at the split round; if champ teams have already advanced
    # (their split-round rows are gone), use their current rows as a proxy
    pre_split_rows = _sort(split_rows)
    if not any(r["strTeam"] in champ_teams for r in pre_split_rows):
        # Supplement with champ current rows so the table shows all teams
        pre_split_rows = _sort(split_rows + [r for r in current_rows if r["strTeam"] in champ_teams])

    return {
        "champ_teams":   champ_teams,
        "mid_teams":     mid_teams,
        "relg_teams":    relg_teams,
        "pre_split":     pre_split_rows,
        "champ_current": champ_current,
        "mid_current":   mid_current,
        "relg_current":  relg_current,
        "pts_factor":    pts_factor,
    }


def conference_fixtures(fixtures: list[dict], teams: set[str]) -> list[dict]:
    """Return only fixtures where BOTH teams are in the given set."""
    return [
        f for f in fixtures
        if f.get("strHomeTeam") in teams and f.get("strAwayTeam") in teams
    ]


def recompute_conference_standings(
    base_rows: list[dict],
    played_fixtures: list[dict],
    pts_factor: float = 1.0,
    pts_round: str = "down",
) -> list[dict]:
    """
    Recompute conference standings when the TheSportsDB API stops updating
    them post-split (e.g., Austrian Relegation Round).

    Applies pts_factor to starting points, then adds W/D/L/GF/GA from
    each played fixture, then re-ranks by points → GD → GF.
    """
    import copy
    import math

    rows: dict[str, dict] = {}
    for r in base_rows:
        row = copy.deepcopy(r)
        raw_pts = int(r.get("intPoints") or 0)
        if pts_factor == 1.0:
            adj_pts = raw_pts
        elif pts_round == "up":
            adj_pts = math.ceil(raw_pts * pts_factor)
        else:
            adj_pts = math.floor(raw_pts * pts_factor)
        row["intPoints"]       = adj_pts
        row["intWin"]          = int(r.get("intWin")          or 0)
        row["intDraw"]         = int(r.get("intDraw")         or 0)
        row["intLoss"]         = int(r.get("intLoss")         or 0)
        row["intGoalsFor"]     = int(r.get("intGoalsFor")     or 0)
        row["intGoalsAgainst"] = int(r.get("intGoalsAgainst") or 0)
        row["intPlayed"]       = int(r.get("intPlayed")       or 0)
        rows[r["strTeam"]] = row

    for fix in played_fixtures:
        home = fix.get("strHomeTeam")
        away = fix.get("strAwayTeam")
        try:
            hg = int(fix.get("intHomeScore"))
            ag = int(fix.get("intAwayScore"))
        except (TypeError, ValueError):
            continue
        if home not in rows or away not in rows:
            continue
        rows[home]["intPlayed"] += 1
        rows[away]["intPlayed"] += 1
        rows[home]["intGoalsFor"]     += hg
        rows[home]["intGoalsAgainst"] += ag
        rows[away]["intGoalsFor"]     += ag
        rows[away]["intGoalsAgainst"] += hg
        if hg > ag:
            rows[home]["intWin"]    += 1
            rows[home]["intPoints"] += 3
            rows[away]["intLoss"]   += 1
        elif hg < ag:
            rows[away]["intWin"]    += 1
            rows[away]["intPoints"] += 3
            rows[home]["intLoss"]   += 1
        else:
            rows[home]["intDraw"]   += 1
            rows[home]["intPoints"] += 1
            rows[away]["intDraw"]   += 1
            rows[away]["intPoints"] += 1

    row_list = list(rows.values())
    for row in row_list:
        row["intGoalDifference"] = row["intGoalsFor"] - row["intGoalsAgainst"]
    row_list.sort(key=lambda r: (
        -int(r["intPoints"]),
        -int(r["intGoalDifference"]),
        -int(r["intGoalsFor"]),
    ))
    for i, row in enumerate(row_list, start=1):
        row["intRank"] = i
    return row_list
