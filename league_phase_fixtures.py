"""
Real 2026-27 UEFA League Phase schedule, matchday by matchday.

The actual draw (which 8 -- or 6, for the Conference League -- opponents
each team faces, and in which order) hasn't happened yet, so every
matchday below starts empty. Once UEFA holds the draw, fixtures get
transcribed in here matchday-by-matchday as tuples of (home team, away
team); league_phase_simulator can then simulate the real schedule instead
of its own synthetic pot-based one, and european.py can show real
per-matchday win/draw/loss probabilities plus a fixture-difficulty ranking.

Each matchday should end up with exactly 18 fixtures (36 clubs, one match
each) -- is_fixture_list_complete() checks a competition is fully filled
in before anything switches over from the synthetic schedule.
"""

LEAGUE_PHASE_MATCHDAYS: dict[str, int] = {
    "Champions League": 8,
    "Europa League": 8,
    "Conference League": 6,
}

LEAGUE_PHASE_FIXTURES: dict[str, dict[int, list[tuple[str, str]]]] = {
    comp: {md: [] for md in range(1, n_md + 1)}
    for comp, n_md in LEAGUE_PHASE_MATCHDAYS.items()
}


def is_matchday_complete(comp_name: str, matchday: int) -> bool:
    fixtures = LEAGUE_PHASE_FIXTURES.get(comp_name, {}).get(matchday, [])
    if len(fixtures) != 18:
        return False
    teams = [t for pair in fixtures for t in pair]
    return len(teams) == len(set(teams)) == 36


def is_fixture_list_complete(comp_name: str) -> bool:
    n_md = LEAGUE_PHASE_MATCHDAYS.get(comp_name, 0)
    return n_md > 0 and all(is_matchday_complete(comp_name, md) for md in range(1, n_md + 1))


def flatten_schedule(comp_name: str) -> list[dict]:
    """The full competition schedule as
    [{"strHomeTeam", "strAwayTeam", "matchday"}, ...], for
    league_phase_simulator's schedule= parameter."""
    schedule = []
    for md, fixtures in sorted(LEAGUE_PHASE_FIXTURES.get(comp_name, {}).items()):
        for home, away in fixtures:
            schedule.append({"strHomeTeam": home, "strAwayTeam": away, "matchday": md})
    return schedule
