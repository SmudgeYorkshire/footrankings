"""
Helpers for leagues with split seasons (regular season + conference rounds).

Providers cannot reliably keep split-league standings tables up to
date.  The table endpoint is therefore used only to identify which conference
each team belongs to; actual post-split standings are always recomputed in
football_rankings.py from the presplit snapshot + played fixture results.

pts_factor values:
  1.0 – points carried over fully (most leagues)
  0.5 – points halved going into split phase (Belgium, Austria, Romania, Serbia)
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
    as split_rows when the provider stops returning the pre-split rows after the
    split has started.
    """
    split_rows   = [r for r in standings if int(r.get("intPlayed") or 0) == split_round]
    current_rows = [r for r in standings if int(r.get("intPlayed") or 0) >  split_round]

    # Fallback A: provider dropped the pre-split rows — use the saved snapshot
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

    # Try to identify conferences from strDescription
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


_DEFAULT_TIEBREAKERS = ["gd", "gf"]

# Tokens this function knows how to resolve purely from tracked match data.
# Anything else a league's config lists (fair_play, disciplinary,
# less_red_cards, less_yellow_cards, draw, playoffs, playoffs_champion,
# pts_no_round, regular_pts, ...) needs data this site doesn't fetch (card
# counts) or is a literal one-off outcome no formula can resolve (a coin
# toss, an actual playoff match) — those are treated as still-tied and
# skipped, same as if they weren't listed, rather than guessed at.
_KNOWN_TIEBREAK_RULES = {
    "gd", "gf", "away_gf", "wins", "away_wins", "less_losses",
    "h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "h2h_wins",
}


def build_h2h(played_fixtures: list[dict]) -> dict[tuple[str, str], dict]:
    """h2h[(team, opponent)] = accumulated points/GD/GF/away-GF/wins from
    every meeting between exactly that pair, for head-to-head tiebreakers."""
    h2h: dict[tuple[str, str], dict] = {}

    def bump(team, opp, **kw):
        d = h2h.setdefault((team, opp), {"pts": 0, "gd": 0, "gf": 0, "away_gf": 0, "wins": 0})
        for k, v in kw.items():
            d[k] += v

    for f in played_fixtures:
        home, away = f.get("strHomeTeam"), f.get("strAwayTeam")
        if not home or not away:
            continue
        try:
            hg, ag = int(f.get("intHomeScore")), int(f.get("intAwayScore"))
        except (TypeError, ValueError):
            continue
        if hg > ag:
            bump(home, away, pts=3, wins=1)
        elif hg < ag:
            bump(away, home, pts=3, wins=1)
        else:
            bump(home, away, pts=1)
            bump(away, home, pts=1)
        bump(home, away, gd=hg - ag, gf=hg)
        bump(away, home, gd=ag - hg, gf=ag, away_gf=ag)
    return h2h


def rank_tied_group(group: list[dict], rules: list[str], h2h: dict[tuple[str, str], dict]) -> list[dict]:
    """Rank standings rows tied on points using the given tiebreaker rules,
    recursively re-applying the next rule to any still-tied subgroup — same
    recursive-split approach as simulator.py's Monte Carlo `_rank_group`,
    but reading each team's already-known season totals + head-to-head
    instead of a simulated one."""
    if len(group) <= 1:
        return list(group)

    for idx, rule in enumerate(rules):
        if rule not in _KNOWN_TIEBREAK_RULES:
            continue

        def score(row, rule=rule):
            team = row["strTeam"]
            if rule.startswith("h2h_"):
                field = rule[len("h2h_"):]
                if field == "away_gf":
                    field = "away_gf"
                return sum(
                    h2h.get((team, o["strTeam"]), {}).get(field, 0)
                    for o in group if o is not row
                )
            if rule == "gd":
                return row.get("intGoalDifference", 0)
            if rule == "gf":
                return row.get("intGoalsFor", 0)
            if rule == "away_gf":
                return row.get("intAwayGoalsFor", 0)
            if rule == "wins":
                return row.get("intWin", 0)
            if rule == "away_wins":
                return row.get("intAwayWin", 0)
            if rule == "less_losses":
                return -row.get("intLoss", 0)
            return 0

        scores = {id(row): score(row) for row in group}
        if len(set(scores.values())) == 1:
            continue  # still all tied on this rule, try the next one

        remaining_rules = rules[idx + 1:]
        sorted_group = sorted(group, key=lambda r: scores[id(r)], reverse=True)

        result = []
        i = 0
        while i < len(sorted_group):
            j = i + 1
            while j < len(sorted_group) and scores[id(sorted_group[j])] == scores[id(sorted_group[i])]:
                j += 1
            subgroup = sorted_group[i:j]
            result.extend(rank_tied_group(subgroup, remaining_rules, h2h) if len(subgroup) > 1 else subgroup)
            i = j
        return result

    return list(group)  # every known rule exhausted, still tied — keep as-is


def recompute_conference_standings(
    base_rows: list[dict],
    played_fixtures: list[dict],
    pts_factor: float = 1.0,
    pts_round: str = "down",
    tiebreakers: list[str] | None = None,
) -> list[dict]:
    """
    Build conference standings from scratch using the presplit snapshot as
    the base and applying played post-split fixtures on top.

    Applies pts_factor to starting points, then adds W/D/L/GF/GA from each
    played fixture, then re-ranks by points → tiebreakers (the league's own
    configured rule order — see rank_tied_group — defaulting to GD → GF
    when not supplied, matching simulator.py's own default).
    Called for every conference (champ / mid / relg) because the provider
    does not update split-league tables post-split.
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
        row["intPoints"]         = adj_pts
        row["intWin"]            = int(r.get("intWin")            or 0)
        row["intDraw"]           = int(r.get("intDraw")           or 0)
        row["intLoss"]           = int(r.get("intLoss")           or 0)
        row["intGoalsFor"]       = int(r.get("intGoalsFor")       or 0)
        row["intGoalsAgainst"]   = int(r.get("intGoalsAgainst")   or 0)
        row["intPlayed"]         = int(r.get("intPlayed")         or 0)
        row["intAwayGoalsFor"]   = int(r.get("intAwayGoalsFor")   or 0)
        row["intAwayWin"]        = int(r.get("intAwayWin")        or 0)
        # Store rounding bonus: when pts_factor=0.5 and pre-split pts were odd,
        # the team lost 0.5 pts to flooring — credited back as tiebreaker
        row["_half_pts_bonus"] = (
            0.5 if (pts_factor == 0.5 and pts_round == "down" and raw_pts % 2 == 1) else 0.0
        )
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
        rows[away]["intAwayGoalsFor"] += ag
        if hg > ag:
            rows[home]["intWin"]    += 1
            rows[home]["intPoints"] += 3
            rows[away]["intLoss"]   += 1
        elif hg < ag:
            rows[away]["intWin"]     += 1
            rows[away]["intAwayWin"] += 1
            rows[away]["intPoints"]  += 3
            rows[home]["intLoss"]    += 1
        else:
            rows[home]["intDraw"]   += 1
            rows[home]["intPoints"] += 1
            rows[away]["intDraw"]   += 1
            rows[away]["intPoints"] += 1

    row_list = list(rows.values())
    for row in row_list:
        row["intGoalDifference"] = row["intGoalsFor"] - row["intGoalsAgainst"]

    rules = tiebreakers if tiebreakers else _DEFAULT_TIEBREAKERS
    h2h = build_h2h(played_fixtures) if any(r.startswith("h2h") for r in rules) else {}

    row_list.sort(key=lambda r: -(int(r["intPoints"]) + r.get("_half_pts_bonus", 0.0)))
    ranked: list[dict] = []
    i = 0
    while i < len(row_list):
        j = i + 1
        while j < len(row_list) and (
            int(row_list[j]["intPoints"]) + row_list[j].get("_half_pts_bonus", 0.0)
        ) == (
            int(row_list[i]["intPoints"]) + row_list[i].get("_half_pts_bonus", 0.0)
        ):
            j += 1
        group = row_list[i:j]
        ranked.extend(rank_tied_group(group, rules, h2h) if len(group) > 1 else group)
        i = j

    for i, row in enumerate(ranked, start=1):
        row["intRank"] = i
    return ranked


def ensure_full_roster(roster_rows: list[dict], fixtures: list[dict]) -> list[dict]:
    """Fill in any team missing from roster_rows using the fixture list.

    API-Football's /standings endpoint has been observed to return only the
    teams that have already played a match early in a season (e.g. day 1 of
    18, with just one match kicked off) — a whole table would otherwise be
    silently truncated to whichever handful of teams happened to have played
    first. fixtures should be played + remaining so every scheduled team is
    covered regardless of provider quirks.
    """
    known = {r["strTeam"] for r in roster_rows if r.get("strTeam")}
    extra = []
    for f in fixtures:
        for team_key, badge_key in (("strHomeTeam", "strHomeTeamBadge"), ("strAwayTeam", "strAwayTeamBadge")):
            name = f.get(team_key)
            if name and name not in known:
                extra.append({"strTeam": name, "strBadge": f.get(badge_key, "")})
                known.add(name)
    return roster_rows + extra


def compute_full_standings(
    roster_rows: list[dict], played_fixtures: list[dict], tiebreakers: list[str] | None = None,
) -> list[dict]:
    """
    Build a whole league's table from scratch: every team at 0 played, then
    every played fixture applied on top. Used as the site's primary standings
    source for every league (regardless of provider) instead of trusting the
    provider's own aggregated table endpoint, which live-data providers have
    been observed to lag behind actual match results by anywhere from
    minutes to hours.

    roster_rows only needs to supply the team list + badges (typically the
    provider's own get_standings() result) — its stats are zeroed and ignored.

    tiebreakers should be the league's own configured rule order (e.g.
    cfg["tiebreakers"]) so ties resolve the same way here as they do on the
    Predictions tab's simulation — defaults to GD → GF when not supplied.
    """
    zeroed = []
    for r in roster_rows:
        row = dict(r)
        row.update({
            "intPlayed": 0, "intWin": 0, "intDraw": 0, "intLoss": 0,
            "intGoalsFor": 0, "intGoalsAgainst": 0, "intGoalDifference": 0,
            "intPoints": 0,
        })
        zeroed.append(row)
    return recompute_conference_standings(
        zeroed, played_fixtures, pts_factor=1.0, pts_round="down", tiebreakers=tiebreakers,
    )
