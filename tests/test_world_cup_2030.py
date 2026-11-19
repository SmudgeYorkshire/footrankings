"""
Tests for world_cup_2030.py's AFC (Asia) 2030 World Cup qualifying
seeding data -- mainly that every team name resolves to a real flags.py
entry (catching a typo'd/un-aliased name before it reaches the page).
"""

import world_cup_2030 as wc


def _all_teams() -> set[str]:
    pots = [
        wc.ASIA_ROUND2_POT1, wc.ASIA_ROUND2_POT2, wc.ASIA_ROUND2_POT3,
        wc.ASIA_ROUND1_SEEDED, wc.ASIA_ROUND1_UNSEEDED,
    ]
    return {team for pot in pots for team, _rank in pot}


def test_every_team_resolves_to_a_real_flag_entry():
    # flag_url() checks BOTH flags.py dicts (FLAG_CODES, the 54-UEFA-
    # nation set, and _GLOBAL_FLAG_CODES, everyone else) -- most AFC
    # teams live in the latter, so checking FLAG_CODES membership alone
    # would be the wrong (too narrow) check here.
    for team in _all_teams():
        resolved = wc._flag(team)
        assert resolved, team


def test_pot_sizes_match_the_source():
    assert len(wc.ASIA_ROUND2_POT1) == 9
    assert len(wc.ASIA_ROUND2_POT2) == 9
    assert len(wc.ASIA_ROUND2_POT3) == 8
    assert len(wc.ASIA_ROUND1_SEEDED) == 10
    assert len(wc.ASIA_ROUND1_UNSEEDED) == 10


def test_no_team_appears_in_more_than_one_pot():
    teams = _all_teams()
    total = sum(len(pot) for pot in [
        wc.ASIA_ROUND2_POT1, wc.ASIA_ROUND2_POT2, wc.ASIA_ROUND2_POT3,
        wc.ASIA_ROUND1_SEEDED, wc.ASIA_ROUND1_UNSEEDED,
    ])
    assert len(teams) == total
