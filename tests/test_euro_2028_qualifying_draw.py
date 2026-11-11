"""
Tests for euro_2028_qualifying_draw.generate_draw -- the randomized
retry-until-valid draw (same approach as league_phase_simulator.py's own
pot draws), run repeatedly with different seed keys to make sure every
hard constraint holds on every draw, not just typically.
"""

import euro_2028_qualifying_draw as d


def _all_draws(n=25):
    return [d.generate_draw(("test", i)) for i in range(n)]


def test_group_sizes_are_correct():
    for groups in _all_draws():
        for g in d.GROUPS_4:
            assert len(groups[g]) == 4
        for g in d.GROUPS_5:
            assert len(groups[g]) == 5


def test_every_team_placed_exactly_once():
    all_teams_expected = {t for teams in d.POTS.values() for t, _tags in teams}
    assert len(all_teams_expected) == 54
    for groups in _all_draws():
        placed = [t for teams in groups.values() for t, _tags in teams]
        assert len(placed) == 54
        assert set(placed) == all_teams_expected


def test_one_team_per_pot_per_group():
    team_to_pot = {t: p for p, teams in d.POTS.items() for t, _tags in teams}
    for groups in _all_draws():
        for letter, teams in groups.items():
            pots_here = [team_to_pot[t] for t, _tags in teams]
            assert len(pots_here) == len(set(pots_here)), (letter, pots_here)


def test_hosts_always_in_separate_groups():
    for groups in _all_draws():
        host_group = {
            team: letter
            for letter, teams in groups.items()
            for team, _tags in teams
            if team in d.HOSTS
        }
        assert len(host_group) == len(d.HOSTS)
        assert len(set(host_group.values())) == len(d.HOSTS)


def test_northern_ireland_never_shares_a_group_with_a_host():
    for groups in _all_draws():
        host_groups = {
            letter for letter, teams in groups.items()
            for team, _tags in teams if team in d.HOSTS
        }
        nir_group = next(
            letter for letter, teams in groups.items()
            for team, _tags in teams if team == d.NIR
        )
        assert nir_group not in host_groups


def test_qf_tagged_pot1_teams_fill_all_six_four_team_group_slots():
    """8 QF-tagged teams exist (all Pot 1), but only 6 four-team-group
    Pot-1 slots do -- the draw should always manage to fill all 6 of
    them from the QF pool (see generate_draw's own docstring)."""
    pot1_tags = dict(d.POTS[1])
    qf_teams = {t for t, tags in pot1_tags.items() if "QF" in tags}
    assert len(qf_teams) == 8
    team_to_pot = {t: p for p, teams in d.POTS.items() for t, _tags in teams}
    for groups in _all_draws():
        pot1_in_af = [
            team for letter in d.GROUPS_4 for team, _tags in groups[letter]
            if team_to_pot[team] == 1
        ]
        assert len(pot1_in_af) == 6
        assert all(team in qf_teams for team in pot1_in_af)


def test_same_seed_key_is_reproducible():
    first = d.generate_draw(("reproducibility-check", 42))
    second = d.generate_draw(("reproducibility-check", 42))
    assert first == second


def test_different_seed_keys_can_differ():
    draws = [d.generate_draw(("variety-check", i)) for i in range(10)]
    group_a_rosters = {tuple(sorted(t for t, _tags in g["A"])) for g in draws}
    assert len(group_a_rosters) > 1
