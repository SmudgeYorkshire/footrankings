"""
Real 2026-27 UEFA League Phase opponent lists.

UEFA's official "Results" page (like the one screenshotted for this
feature) lists each club's 8 (or 6, Conference League) opponents with a
home/away icon per slot, but not grouped into matchday order -- so that's
what gets transcribed here: per club, a list of (opponent, "H"|"A")
tuples. Once every club in a competition has its list filled in,
derive_fixtures() below turns that into a real fixture list (with real
home/away legs, since the icon tells us that much) that
league_phase_simulator can simulate instead of its own synthetic
pot-based schedule, and european.py can use for a real fixture-difficulty
ranking.

Only one side of each pairing needs to be entered -- if Real Madrid's own
list says ("Liverpool", "H"), that already fully determines the match
(Real Madrid home, Liverpool away) without needing Liverpool's list to
also mention it.
"""

LEAGUE_PHASE_OPPONENT_COUNT: dict[str, int] = {
    "Champions League": 8,
    "Europa League": 8,
    "Conference League": 6,
}

# comp -> team -> [(opponent, "H"|"A"), ...]
LEAGUE_PHASE_OPPONENTS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "Champions League": {
        "Paris Saint-Germain": [
            ("Barcelona", "H"), ("Manchester City", "A"),
            ("Roma", "H"), ("Aston Villa", "A"),
            ("Galatasaray", "H"), ("Villarreal", "A"),
            ("Slovan Bratislava", "H"), ("Como", "A"),
        ],
        "Bayern Munich": [
            ("Arsenal", "H"), ("Atlético Madrid", "A"),
            ("Real Betis", "H"), ("Manchester United", "A"),
            ("Bodo/Glimt", "H"), ("Lille", "A"),
            ("Slavia Prague", "H"), ("Viking", "A"),
        ],
        "Real Madrid": [
            ("Inter Milan", "H"), ("Arsenal", "A"),
            ("PSV Eindhoven", "H"), ("Roma", "A"),
            ("RB Leipzig", "H"), ("Shakhtar Donetsk", "A"),
            ("Lask Linz", "H"), ("AEK Athens FC", "A"),
        ],
        "Liverpool": [
            ("Atlético Madrid", "H"), ("Inter Milan", "A"),
            ("Porto", "H"), ("Club Brugge", "A"),
            ("Villarreal", "H"), ("Fenerbahçe", "A"),
            ("Lens", "H"), ("Lask Linz", "A"),
        ],
        "Inter Milan": [
            ("Liverpool", "H"), ("Real Madrid", "A"),
            ("Club Brugge", "H"), ("Borussia Dortmund", "A"),
            ("Shakhtar Donetsk", "H"), ("Feyenoord", "A"),
            ("VfB Stuttgart", "H"), ("Slovan Bratislava", "A"),
        ],
        "Manchester City": [
            ("Paris Saint-Germain", "H"), ("Barcelona", "A"),
            ("Sporting CP", "H"), ("Porto", "A"),
            ("Napoli", "H"), ("RB Leipzig", "A"),
            ("AEK Athens FC", "H"), ("Lens", "A"),
        ],
        "Arsenal": [
            ("Real Madrid", "H"), ("Bayern Munich", "A"),
            ("Borussia Dortmund", "H"), ("Real Betis", "A"),
            ("Lille", "H"), ("Napoli", "A"),
            ("Sabah FA", "H"), ("Slavia Prague", "A"),
        ],
        "Barcelona": [
            ("Manchester City", "H"), ("Paris Saint-Germain", "A"),
            ("Aston Villa", "H"), ("Sporting CP", "A"),
            ("Feyenoord", "H"), ("Galatasaray", "A"),
            ("Como", "H"), ("Sabah FA", "A"),
        ],
        "Atlético Madrid": [
            ("Bayern Munich", "H"), ("Liverpool", "A"),
            ("Manchester United", "H"), ("PSV Eindhoven", "A"),
            ("Fenerbahçe", "H"), ("Bodo/Glimt", "A"),
            ("Viking", "H"), ("VfB Stuttgart", "A"),
        ],
        "Borussia Dortmund": [
            ("Inter Milan", "H"), ("Arsenal", "A"),
            ("Real Betis", "H"), ("Aston Villa", "A"),
            ("Villarreal", "H"), ("Bodo/Glimt", "A"),
            ("AEK Athens FC", "H"), ("Sabah FA", "A"),
        ],
        "Roma": [
            ("Real Madrid", "H"), ("Paris Saint-Germain", "A"),
            ("Sporting CP", "H"), ("Manchester United", "A"),
            ("Lille", "H"), ("Fenerbahçe", "A"),
            ("Slovan Bratislava", "H"), ("AEK Athens FC", "A"),
        ],
        "Sporting CP": [
            ("Barcelona", "H"), ("Manchester City", "A"),
            ("Manchester United", "H"), ("Roma", "A"),
            ("Galatasaray", "H"), ("Shakhtar Donetsk", "A"),
            ("Lask Linz", "H"), ("Lens", "A"),
        ],
        "Aston Villa": [
            ("Paris Saint-Germain", "H"), ("Barcelona", "A"),
            ("Borussia Dortmund", "H"), ("Club Brugge", "A"),
            ("Fenerbahçe", "H"), ("Galatasaray", "A"),
            ("Viking", "H"), ("Slavia Prague", "A"),
        ],
        "Porto": [
            ("Manchester City", "H"), ("Liverpool", "A"),
            ("PSV Eindhoven", "H"), ("Real Betis", "A"),
            ("Napoli", "H"), ("Feyenoord", "A"),
            ("Slavia Prague", "H"), ("Lask Linz", "A"),
        ],
        "Manchester United": [
            ("Bayern Munich", "H"), ("Atlético Madrid", "A"),
            ("Roma", "H"), ("Sporting CP", "A"),
            ("RB Leipzig", "H"), ("Villarreal", "A"),
            ("Sabah FA", "H"), ("Como", "A"),
        ],
        "Club Brugge": [
            ("Liverpool", "H"), ("Inter Milan", "A"),
            ("Aston Villa", "H"), ("PSV Eindhoven", "A"),
            ("Bodo/Glimt", "H"), ("Napoli", "A"),
            ("Lens", "H"), ("VfB Stuttgart", "A"),
        ],
        "Real Betis": [
            ("Arsenal", "H"), ("Bayern Munich", "A"),
            ("Porto", "H"), ("Borussia Dortmund", "A"),
            ("Feyenoord", "H"), ("Lille", "A"),
            ("Como", "H"), ("Slovan Bratislava", "A"),
        ],
        "PSV Eindhoven": [
            ("Atlético Madrid", "H"), ("Real Madrid", "A"),
            ("Club Brugge", "H"), ("Porto", "A"),
            ("Shakhtar Donetsk", "H"), ("RB Leipzig", "A"),
            ("VfB Stuttgart", "H"), ("Viking", "A"),
        ],
        "Feyenoord": [
            ("Inter Milan", "H"), ("Barcelona", "A"),
            ("Porto", "H"), ("Real Betis", "A"),
            ("RB Leipzig", "H"), ("Galatasaray", "A"),
            ("Como", "H"), ("Viking", "A"),
        ],
        "Lille": [
            ("Bayern Munich", "H"), ("Arsenal", "A"),
            ("Real Betis", "H"), ("Roma", "A"),
            ("Galatasaray", "H"), ("Bodo/Glimt", "A"),
            ("Slovan Bratislava", "H"), ("VfB Stuttgart", "A"),
        ],
        "Napoli": [
            ("Arsenal", "H"), ("Manchester City", "A"),
            ("Club Brugge", "H"), ("Porto", "A"),
            ("Bodo/Glimt", "H"), ("Villarreal", "A"),
            ("Viking", "H"), ("Sabah FA", "A"),
        ],
        "Bodo/Glimt": [
            ("Atlético Madrid", "H"), ("Bayern Munich", "A"),
            ("Borussia Dortmund", "H"), ("Club Brugge", "A"),
            ("Lille", "H"), ("Napoli", "A"),
            ("Lask Linz", "H"), ("Lens", "A"),
        ],
        "RB Leipzig": [
            ("Manchester City", "H"), ("Real Madrid", "A"),
            ("PSV Eindhoven", "H"), ("Manchester United", "A"),
            ("Shakhtar Donetsk", "H"), ("Feyenoord", "A"),
            ("Lens", "H"), ("Como", "A"),
        ],
        "Villarreal": [
            ("Paris Saint-Germain", "H"), ("Liverpool", "A"),
            ("Manchester United", "H"), ("Borussia Dortmund", "A"),
            ("Napoli", "H"), ("Fenerbahçe", "A"),
            ("Sabah FA", "H"), ("Slavia Prague", "A"),
        ],
        "Fenerbahçe": [
            ("Liverpool", "H"), ("Atlético Madrid", "A"),
            ("Roma", "H"), ("Aston Villa", "A"),
            ("Villarreal", "H"), ("Shakhtar Donetsk", "A"),
            ("Slavia Prague", "H"), ("Lask Linz", "A"),
        ],
        "Shakhtar Donetsk": [
            ("Real Madrid", "H"), ("Inter Milan", "A"),
            ("Sporting CP", "H"), ("PSV Eindhoven", "A"),
            ("Fenerbahçe", "H"), ("RB Leipzig", "A"),
            ("AEK Athens FC", "H"), ("Slovan Bratislava", "A"),
        ],
        "Viking": [
            ("Bayern Munich", "H"), ("Atlético Madrid", "A"),
            ("PSV Eindhoven", "H"), ("Aston Villa", "A"),
            ("Feyenoord", "H"), ("Napoli", "A"),
            ("Sabah FA", "H"), ("VfB Stuttgart", "A"),
        ],
        "Sabah FA": [
            ("Barcelona", "H"), ("Arsenal", "A"),
            ("Borussia Dortmund", "H"), ("Manchester United", "A"),
            ("Napoli", "H"), ("Villarreal", "A"),
            ("Slavia Prague", "H"), ("Viking", "A"),
        ],
        "Como": [
            ("Paris Saint-Germain", "H"), ("Barcelona", "A"),
            ("Manchester United", "H"), ("Real Betis", "A"),
            ("RB Leipzig", "H"), ("Feyenoord", "A"),
            ("AEK Athens FC", "H"), ("Lens", "A"),
        ],
        "Lens": [
            ("Manchester City", "H"), ("Liverpool", "A"),
            ("Sporting CP", "H"), ("Club Brugge", "A"),
            ("Bodo/Glimt", "H"), ("RB Leipzig", "A"),
            ("Como", "H"), ("Slavia Prague", "A"),
        ],
        "Galatasaray": [
            ("Barcelona", "H"), ("Paris Saint-Germain", "A"),
            ("Aston Villa", "H"), ("Sporting CP", "A"),
            ("Feyenoord", "H"), ("Lille", "A"),
            ("VfB Stuttgart", "H"), ("AEK Athens FC", "A"),
        ],
        "Slavia Prague": [
            ("Arsenal", "H"), ("Bayern Munich", "A"),
            ("Aston Villa", "H"), ("Porto", "A"),
            ("Villarreal", "H"), ("Fenerbahçe", "A"),
            ("Lens", "H"), ("Sabah FA", "A"),
        ],
        "Slovan Bratislava": [
            ("Inter Milan", "H"), ("Paris Saint-Germain", "A"),
            ("Real Betis", "H"), ("Roma", "A"),
            ("Shakhtar Donetsk", "H"), ("Lille", "A"),
            ("VfB Stuttgart", "H"), ("Lask Linz", "A"),
        ],
        "VfB Stuttgart": [
            ("Atlético Madrid", "H"), ("Inter Milan", "A"),
            ("Club Brugge", "H"), ("PSV Eindhoven", "A"),
            ("Lille", "H"), ("Galatasaray", "A"),
            ("Viking", "H"), ("Slovan Bratislava", "A"),
        ],
        "AEK Athens FC": [
            ("Real Madrid", "H"), ("Manchester City", "A"),
            ("Roma", "H"), ("Borussia Dortmund", "A"),
            ("Galatasaray", "H"), ("Shakhtar Donetsk", "A"),
            ("Lask Linz", "H"), ("Como", "A"),
        ],
        "Lask Linz": [
            ("Liverpool", "H"), ("Real Madrid", "A"),
            ("Porto", "H"), ("Sporting CP", "A"),
            ("Fenerbahçe", "H"), ("Bodo/Glimt", "A"),
            ("Slovan Bratislava", "H"), ("AEK Athens FC", "A"),
        ],
    },
    "Europa League": {},
    "Conference League": {},
}


def _resolve_home_by_edge(comp_name: str) -> dict[frozenset, str]:
    """{frozenset({team_a, team_b}): home_team} for every match implied by
    the opponent lists entered so far. First mention of a pairing wins if
    both sides happen to be entered and (incorrectly) disagree."""
    home_by_edge: dict[frozenset, str] = {}
    for team, opponents in LEAGUE_PHASE_OPPONENTS.get(comp_name, {}).items():
        for opp, venue in opponents:
            edge = frozenset({team, opp})
            home = team if venue == "H" else opp
            home_by_edge.setdefault(edge, home)
    return home_by_edge


def is_opponent_list_complete(comp_name: str, field_teams: list[str]) -> bool:
    """True once derive_fixtures() would produce a full, valid schedule:
    every one of the competition's field clubs has exactly the right
    number of distinct opponents, all of them also field clubs."""
    n_needed = LEAGUE_PHASE_OPPONENT_COUNT.get(comp_name, 0)
    edges = _resolve_home_by_edge(comp_name)
    if n_needed <= 0 or not edges:
        return False
    valid = set(field_teams)
    degree = {t: 0 for t in field_teams}
    for edge in edges:
        for t in edge:
            if t not in valid:
                return False
            degree[t] += 1
    return all(d == n_needed for d in degree.values())


def partial_opponents_by_team(comp_name: str) -> dict[str, list[str]]:
    """{team: [opponent, ...]} for every team whose full opponent count is
    already known from the lists entered so far (exactly
    LEAGUE_PHASE_OPPONENT_COUNT distinct opponents) -- lets a
    fixture-difficulty ranking grow incrementally, club by club, rather
    than waiting for the whole competition to be filled in."""
    n_needed = LEAGUE_PHASE_OPPONENT_COUNT.get(comp_name, 0)
    opponents: dict[str, set[str]] = {}
    for edge in _resolve_home_by_edge(comp_name):
        a, b = tuple(edge)
        opponents.setdefault(a, set()).add(b)
        opponents.setdefault(b, set()).add(a)
    return {t: sorted(opps) for t, opps in opponents.items() if len(opps) == n_needed}


def derive_fixtures(comp_name: str) -> list[dict]:
    """The real fixture list as [{"strHomeTeam", "strAwayTeam"}, ...],
    with real home/away legs from the entered opponent lists."""
    fixtures = []
    for edge, home in sorted(_resolve_home_by_edge(comp_name).items(), key=lambda kv: sorted(kv[0])):
        away = next(t for t in edge if t != home)
        fixtures.append({"strHomeTeam": home, "strAwayTeam": away})
    return fixtures
