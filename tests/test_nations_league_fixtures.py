"""
Regression test for the real bug caught live 2026-11-12: API-Football
calls Czechia "Czech Republic", which doesn't fuzzy-match this site's own
canonical "Czechia" at all (a genuinely different word, not a diacritic/
suffix variant resolve_to_team's fuzzy match could catch). Every one of
Czechia's real Group A3 fixtures was silently filtered out of
group_fixtures() as a result -- neither side of the match ever matched
the group's own team_set -- showing them at 0 played despite having
actually played their full schedule.
"""

from nations_league_data import ALL_NL_TEAMS
from nations_league_fixtures import _resolve_name


def test_czech_republic_resolves_to_czechia():
    assert _resolve_name("Czech Republic") == "Czechia"


def test_every_name_alias_target_is_a_known_nl_team():
    from nations_league_fixtures import _NAME_ALIASES
    for raw, target in _NAME_ALIASES.items():
        assert target in ALL_NL_TEAMS, f"{raw!r} -> {target!r}, not a known NL team"
