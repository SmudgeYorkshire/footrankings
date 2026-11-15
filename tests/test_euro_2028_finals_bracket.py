"""
Tests for euro_2028_finals_bracket.py -- resolving the 24 Euro 2028
finals teams from this page's qualifying-group predictions, drawing
the 6 Finals groups, and simulating the knockout bracket through to a
champion (see that module's own docstring for the real-rule gaps it
stands in for).
"""

import pandas as pd
import pytest

import euro_2028_finals_bracket as fb
import euro_2028_qualifying_draw as d


def _qual_df(ordered_teams: list[str], points: list[float]) -> pd.DataFrame:
    """A synthetic qualifying-group prediction table, already sorted by
    predicted_points descending (as gp.simulate_group's own output is)."""
    n = len(ordered_teams)
    rows = []
    for pos, (team, pts) in enumerate(zip(ordered_teams, points)):
        row = {"team": team, "predicted_points": pts}
        for p in range(n):
            row[f"pos_{p + 1}_prob"] = 1.0 if p == pos else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def _synthetic_qual_predictions() -> dict[str, pd.DataFrame]:
    """12 qualifying groups (6 of 4 teams, 6 of 5), winners/runners-up
    all distinct synthetic team names so ranking order is unambiguous."""
    preds = {}
    letters_4 = list("ABCDEF")
    letters_5 = list("GHIJKL")
    for i, letter in enumerate(letters_4):
        teams = [f"{letter}Win", f"{letter}Runner", f"{letter}Third", f"{letter}Fourth"]
        # Runner-up points-per-game descend A->F so ranking is unambiguous.
        points = [15.0, 12.0 - i * 0.1, 6.0, 3.0]
        preds[letter] = _qual_df(teams, points)
    for i, letter in enumerate(letters_5):
        teams = [f"{letter}Win", f"{letter}Runner", f"{letter}Third", f"{letter}Fourth", f"{letter}Fifth"]
        points = [18.0, 10.0 - i * 0.1, 8.0, 5.0, 2.0]
        preds[letter] = _qual_df(teams, points)
    return preds


def _host_qual_predictions() -> dict[str, pd.DataFrame]:
    """Same shape, but with the 4 real hosts + Northern Ireland seeded
    as some groups' winners, to test host-reservation / NIR handling."""
    preds = _synthetic_qual_predictions()
    # Make England the Group A winner, and have Wales/Republic of
    # Ireland/Scotland/Northern Ireland all miss out entirely (4th/5th),
    # so they need host reservation (or are simply absent, for NIR).
    preds["A"] = _qual_df(["England", "ARunner", "AThird", "AFourth"], [15.0, 12.0, 6.0, 3.0])
    preds["G"] = _qual_df(
        ["GWin", "GRunner", "Wales", "Scotland", "Republic of Ireland"],
        [18.0, 10.0, 8.0, 5.0, 2.0],
    )
    return preds


def test_resolve_finalists_returns_24_unique_teams():
    finalists = fb.resolve_finalists(_synthetic_qual_predictions())
    teams = [f["team"] for f in finalists]
    assert len(teams) == 24
    assert len(set(teams)) == 24


def test_group_winners_always_qualify_directly():
    preds = _synthetic_qual_predictions()
    finalists = fb.resolve_finalists(preds)
    routes = {f["team"]: f["route"] for f in finalists}
    for letter, df in preds.items():
        winner = df.iloc[0]["team"]
        assert routes[winner] == "Qualifying winner"


def test_runner_up_ranking_uses_points_per_game_not_raw_points():
    """A five-team group's runner-up plays 8 games vs a four-team
    group's runner-up's 6 -- raw points would unfairly favour the
    larger group; points-per-game should not."""
    preds = {
        "A": _qual_df(["AWin", "ARunner", "AThird", "AFourth"], [15.0, 11.0, 6.0, 3.0]),  # 11/6 = 1.83 ppg
        "G": _qual_df(
            ["GWin", "GRunner", "GThird", "GFourth", "GFifth"], [18.0, 12.0, 8.0, 5.0, 2.0],
        ),  # 12/8 = 1.5 ppg -- fewer points per game despite more raw points
    }
    for letter in "BCDEF":
        preds[letter] = _qual_df([f"{letter}Win", f"{letter}Runner", f"{letter}Third", f"{letter}Fourth"], [15.0, 1.0, 0.5, 0.0])
    for letter in "HIJKL":
        preds[letter] = _qual_df(
            [f"{letter}Win", f"{letter}Runner", f"{letter}Third", f"{letter}Fourth", f"{letter}Fifth"],
            [18.0, 0.5, 0.3, 0.2, 0.1],
        )
    finalists = fb.resolve_finalists(preds)
    routes = {f["team"]: f["route"] for f in finalists}
    # ARunner (1.83 ppg) should rank above GRunner (1.5 ppg) for the top-8 cut.
    assert routes["ARunner"] == "Qualifying runner-up"


def test_missing_hosts_get_reserved_slots():
    finalists = fb.resolve_finalists(_host_qual_predictions())
    routes = {f["team"]: f["route"] for f in finalists}
    # Wales and Scotland are 3rd/4th in Group G (not winners, not the
    # single runner-up) -- the 2 reserved host slots should pick them
    # up (Republic of Ireland misses out, since only 2 slots exist and
    # 3 hosts need one here).
    reserved = {t for t, r in routes.items() if r == "Host reservation"}
    assert reserved == {"Wales", "Scotland"}


def test_at_most_two_host_reservation_slots_exist():
    finalists = fb.resolve_finalists(_host_qual_predictions())
    reserved = [f for f in finalists if f["route"] == "Host reservation"]
    assert len(reserved) <= 2


def _hosts_qualify_as_winners_predictions() -> dict[str, pd.DataFrame]:
    """Seeds Wales/England/Republic of Ireland/Scotland as qualifying
    winners of 4 different groups, guaranteeing they're all finalists
    -- the ordinary case build_finals_pots' fixed-head assignment
    should produce for."""
    preds = _synthetic_qual_predictions()
    preds["A"] = _qual_df(["Wales", "ARunner", "AThird", "AFourth"], [15.0, 12.0, 6.0, 3.0])
    preds["B"] = _qual_df(["England", "BRunner", "BThird", "BFourth"], [15.0, 11.9, 6.0, 3.0])
    preds["C"] = _qual_df(["CWin", "CRunner", "CThird", "CFourth"], [15.0, 11.8, 6.0, 3.0])
    preds["D"] = _qual_df(["Republic of Ireland", "DRunner", "DThird", "DFourth"], [15.0, 11.7, 6.0, 3.0])
    preds["E"] = _qual_df(["EWin", "ERunner", "EThird", "EFourth"], [15.0, 11.6, 6.0, 3.0])
    preds["F"] = _qual_df(["Scotland", "FRunner", "FThird", "FFourth"], [15.0, 11.5, 6.0, 3.0])
    return preds


def test_build_finals_pots_head_assignment_fixes_the_four_hosts():
    finalists = fb.resolve_finalists(_hosts_qualify_as_winners_predictions())
    ratings = {f["team"]: 1500.0 + i for i, f in enumerate(finalists)}
    _, head_assignment = fb.build_finals_pots(finalists, ratings)
    assert head_assignment["A"] == "Wales"
    assert head_assignment["B"] == "England"
    assert head_assignment["E"] == "Republic of Ireland"
    assert head_assignment["F"] == "Scotland"


def _two_hosts_miss_out_entirely_predictions() -> dict[str, pd.DataFrame]:
    """All 4 hosts finish last in their own (4-team) qualifying group --
    none win or finish runner-up, so none qualify directly, and only
    England/Wales (ranked ahead on points-per-game, both tied on
    finishing position) claim the 2 reserved host spots. Scotland and
    Republic of Ireland are the realistic edge case: a host that misses
    out on all 24 slots entirely, only possible when 3+ hosts fail at
    once (only 2 reservations exist)."""
    preds = _synthetic_qual_predictions()
    preds["A"] = _qual_df(["AWin", "ARunner", "AThird", "Wales"], [15.0, 12.0, 6.0, 4.0])
    preds["B"] = _qual_df(["BWin", "BRunner", "BThird", "England"], [15.0, 11.9, 6.0, 5.0])
    preds["E"] = _qual_df(["EWin", "ERunner", "EThird", "Republic of Ireland"], [15.0, 11.6, 6.0, 1.0])
    preds["F"] = _qual_df(["FWin", "FRunner", "FThird", "Scotland"], [15.0, 11.5, 6.0, 2.0])
    return preds


def test_resolve_finalists_excludes_a_host_when_more_than_two_miss_out():
    finalists = fb.resolve_finalists(_two_hosts_miss_out_entirely_predictions())
    teams = {f["team"] for f in finalists}
    assert {"England", "Wales"} <= teams
    assert not ({"Scotland", "Republic of Ireland"} & teams)
    assert len(teams) == 24


def test_build_finals_pots_leaves_a_missing_hosts_group_head_random():
    """Scotland and Republic of Ireland aren't finalists at all here --
    their groups' heads should fall back to None rather than
    build_finals_pots inventing a fixed head for a non-finalist."""
    finalists = fb.resolve_finalists(_two_hosts_miss_out_entirely_predictions())
    ratings = {f["team"]: 1500.0 + i for i, f in enumerate(finalists)}
    _, head_assignment = fb.build_finals_pots(finalists, ratings)
    assert head_assignment["A"] == "Wales"
    assert head_assignment["B"] == "England"
    assert head_assignment["E"] is None
    assert head_assignment["F"] is None


def test_build_finals_pots_sizes_are_six_each():
    finalists = fb.resolve_finalists(_synthetic_qual_predictions())
    ratings = {f["team"]: 1500.0 + i for i, f in enumerate(finalists)}
    pots, _ = fb.build_finals_pots(finalists, ratings)
    assert len(pots) == 4
    for p in pots.values():
        assert len(p) == 6


def test_draw_finals_groups_every_team_placed_once_in_six_groups_of_four():
    finalists = fb.resolve_finalists(_synthetic_qual_predictions())
    ratings = {f["team"]: 1500.0 + i for i, f in enumerate(finalists)}
    pots, head_assignment = fb.build_finals_pots(finalists, ratings)
    groups = fb.draw_finals_groups(pots, head_assignment, seed=1)
    assert set(groups.keys()) == set(fb.FINALS_GROUPS)
    all_teams = [t for teams in groups.values() for t in teams]
    assert len(all_teams) == 24
    assert len(set(all_teams)) == 24
    for teams in groups.values():
        assert len(teams) == 4


def test_draw_finals_groups_fixed_heads_land_in_their_own_group():
    finalists = fb.resolve_finalists(_synthetic_qual_predictions())
    ratings = {f["team"]: 1500.0 + i for i, f in enumerate(finalists)}
    pots, head_assignment = fb.build_finals_pots(finalists, ratings)
    groups = fb.draw_finals_groups(pots, head_assignment, seed=2)
    for letter, head in head_assignment.items():
        if head:
            assert head in groups[letter]


def test_draw_finals_groups_never_places_a_political_pair_together():
    # Force Kosovo and Serbia to both be finalists by seeding them as
    # group winners, independent of the synthetic qualifying data.
    preds = _synthetic_qual_predictions()
    preds["A"] = _qual_df(["Kosovo", "ARunner", "AThird", "AFourth"], [15.0, 12.0, 6.0, 3.0])
    preds["B"] = _qual_df(["Serbia", "BRunner", "BThird", "BFourth"], [15.0, 11.9, 6.0, 3.0])
    finalists = fb.resolve_finalists(preds)
    ratings = {f["team"]: 1500.0 + i for i, f in enumerate(finalists)}
    for seed in range(15):
        pots, head_assignment = fb.build_finals_pots(finalists, ratings)
        groups = fb.draw_finals_groups(pots, head_assignment, seed=seed)
        for teams in groups.values():
            team_set = set(teams)
            assert not (d.POLITICAL_PAIRS and any(pair <= team_set for pair in d.POLITICAL_PAIRS))


def test_third_place_permutation_table_matches_the_wikipedia_quote():
    assert fb.THIRD_PLACE_PERMUTATION[frozenset("ABCD")] == ("A", "D", "B", "C")
    assert fb.THIRD_PLACE_PERMUTATION[frozenset("CDEF")] == ("F", "E", "D", "C")
    assert fb.THIRD_PLACE_PERMUTATION[frozenset("ABEF")] == ("E", "F", "B", "A")


def test_third_place_permutation_table_has_all_fifteen_combinations():
    import itertools
    expected = {frozenset(c) for c in itertools.combinations("ABCDEF", 4)}
    assert set(fb.THIRD_PLACE_PERMUTATION.keys()) == expected


@pytest.fixture()
def _drawn_finals(monkeypatch):
    finalists = fb.resolve_finalists(_synthetic_qual_predictions())
    ratings = {f["team"]: 1500.0 + 10 * i for i, f in enumerate(finalists)}
    pots, head_assignment = fb.build_finals_pots(finalists, ratings)
    groups = fb.draw_finals_groups(pots, head_assignment, seed=3)
    return finalists, groups, ratings


def test_simulate_finals_probabilities_sum_sensibly(_drawn_finals):
    finalists, groups, ratings = _drawn_finals
    df = fb.simulate_finals(finalists, groups, ratings, n_sim=500, seed=42)
    assert len(df) == 24
    for letter in fb.FINALS_GROUPS:
        group_teams = df[df["group"] == letter]
        assert abs(group_teams["p_win_group"].sum() - 1.0) < 1e-9
    assert abs(df["p_champion"].sum() - 1.0) < 1e-9
    # Monotonic funnel: can't reach the final without reaching R16 first.
    for _, row in df.iterrows():
        assert row["p_r16"] >= row["p_qf"] >= row["p_sf"] >= row["p_final"] >= row["p_champion"]


def test_simulate_finals_is_reproducible_with_the_same_seed(_drawn_finals):
    finalists, groups, ratings = _drawn_finals
    first = fb.simulate_finals(finalists, groups, ratings, n_sim=200, seed=7)
    second = fb.simulate_finals(finalists, groups, ratings, n_sim=200, seed=7)
    assert first.equals(second)


def test_most_likely_bracket_returns_a_single_champion(_drawn_finals):
    finalists, groups, ratings = _drawn_finals
    path = fb.most_likely_bracket(groups, ratings)
    all_teams = {t for teams in groups.values() for t in teams}
    assert path["champion"] in all_teams
    for m in ("M37", "M38", "M39", "M40", "M41", "M42", "M43", "M44"):
        assert path["r16"][m] in all_teams
