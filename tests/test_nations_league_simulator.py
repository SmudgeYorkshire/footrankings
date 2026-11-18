"""
Regression test for the real bug caught live 2026-11-12 (Nations League
Group C2): simulate_league_outcomes ranked each replicate's points-tied
teams by raw GD/GF alone, ignoring NL_TIEBREAKERS' h2h-first rule. Real
numbers: Cyprus (8 pts, 1 game left vs Montenegro) can only be caught on
points by Armenia (5 pts, 1 game left vs Latvia) if Cyprus loses its last
game (falling to 8) AND Armenia wins its last game (rising to 8) -- and
Cyprus already has the better head-to-head record against Armenia (4 h2h
pts to 1: a win and a draw vs just a draw), so even in that exact tie
Cyprus must finish above Armenia. Before the fix, Armenia still showed a
real (non-zero, ~13%) chance of finishing 2nd.
"""

import itertools

import pandas as pd

import nations_league_simulator as nls
from nations_league_simulator import (
    simulate_league_outcomes, league_interim_rankings, league_interim_order, group_expected_points,
    project_playoff_entries, project_qf_entries,
)


def _ratings(teams: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"team": teams, "alias": "", "opta_rating": [1700.0] * len(teams)})


def _c2_group_states() -> dict[str, dict]:
    teams = ["Montenegro", "Cyprus", "Latvia", "Armenia"]
    return {
        "C2": {
            "teams": teams,
            "base_stats": {
                "Montenegro": {"pts": 10, "gd": 3, "gf": 7},
                "Cyprus": {"pts": 8, "gd": 2, "gf": 6},
                "Armenia": {"pts": 5, "gd": -1, "gf": 5},
                "Latvia": {"pts": 1, "gd": -4, "gf": 2},
            },
            "remaining": [
                {"strHomeTeam": "Montenegro", "strAwayTeam": "Latvia"},
                {"strHomeTeam": "Latvia", "strAwayTeam": "Armenia"},
                {"strHomeTeam": "Cyprus", "strAwayTeam": "Montenegro"},
            ],
            "played": [
                {"strHomeTeam": "Armenia", "strAwayTeam": "Latvia", "intHomeScore": 2, "intAwayScore": 0},
                {"strHomeTeam": "Montenegro", "strAwayTeam": "Cyprus", "intHomeScore": 2, "intAwayScore": 1},
                {"strHomeTeam": "Latvia", "strAwayTeam": "Cyprus", "intHomeScore": 0, "intAwayScore": 0},
                {"strHomeTeam": "Armenia", "strAwayTeam": "Montenegro", "intHomeScore": 2, "intAwayScore": 3},
                {"strHomeTeam": "Latvia", "strAwayTeam": "Montenegro", "intHomeScore": 1, "intAwayScore": 2},
                {"strHomeTeam": "Cyprus", "strAwayTeam": "Armenia", "intHomeScore": 2, "intAwayScore": 0},
                {"strHomeTeam": "Cyprus", "strAwayTeam": "Latvia", "intHomeScore": 2, "intAwayScore": 1},
                {"strHomeTeam": "Montenegro", "strAwayTeam": "Armenia", "intHomeScore": 0, "intAwayScore": 0},
                {"strHomeTeam": "Armenia", "strAwayTeam": "Cyprus", "intHomeScore": 1, "intAwayScore": 1},
            ],
        },
    }


def test_team_mathematically_behind_on_h2h_never_shown_finishing_above_rival():
    teams = ["Montenegro", "Cyprus", "Latvia", "Armenia"]
    rules = [("direct", pos, f"P{pos}") for pos in (1, 2, 3, 4)]

    probs, _ = simulate_league_outcomes(
        _c2_group_states(), rules, _ratings(teams), n_sim=5000, seed=7,
    )

    assert probs.loc["Armenia", "P2"] == 0.0


def test_without_played_fixtures_still_runs_but_is_not_the_point_of_this_test():
    # "played" is optional (a group with no real played fixtures yet, e.g.
    # before a season starts, has nothing to build h2h matrices from) --
    # confirms that case doesn't crash, independent of the tiebreak fix.
    teams = ["A", "B", "C", "D"]
    group_states = {
        "G1": {
            "teams": teams,
            "base_stats": {t: {"pts": 0, "gd": 0, "gf": 0} for t in teams},
            "remaining": [
                {"strHomeTeam": "A", "strAwayTeam": "B"},
                {"strHomeTeam": "C", "strAwayTeam": "D"},
            ],
        },
    }
    rules = [("direct", pos, f"P{pos}") for pos in (1, 2, 3, 4)]
    probs, _ = simulate_league_outcomes(group_states, rules, _ratings(teams), n_sim=500, seed=1)
    assert set(probs.index) == set(teams)


def _one_hot_probs(order: list[str]) -> pd.DataFrame:
    """A group position-probability matrix pinned to exactly `order`
    (position i certain for order[i-1]) -- for league_interim_rankings
    tests, where the ranking logic under test should be exercised
    independent of any actual group simulation."""
    n = len(order)
    return pd.DataFrame(
        {str(i): [1.0 if order[i - 1] == t else 0.0 for t in order] for i in range(1, n + 1)},
        index=order,
    )


def test_league_interim_rankings_orders_by_group_position_before_points():
    # X1/X2 are pinned 1st/2nd in G1; Y1/Y2 are pinned 1st/2nd in G2 -- but
    # Y2 (2nd in G2) has far more real points than X1 (1st in G1). UEFA's
    # interim ranking still orders by GROUP POSITION first: every group's
    # 1st-place team outranks every group's 2nd-place team regardless of
    # points. Within each position tier, points break the tie (descending)
    # -- so the expected order is X1, Y1 (both 1st, X1 ahead on points),
    # then Y2, X2 (both 2nd, Y2 ahead on points despite being 2nd overall).
    group_probs = {
        "G1": _one_hot_probs(["X1", "X2"]),
        "G2": _one_hot_probs(["Y1", "Y2"]),
    }
    standings = {
        "G1": [{"strTeam": "X1", "intPoints": 10}, {"strTeam": "X2", "intPoints": 5}],
        "G2": [{"strTeam": "Y1", "intPoints": 3}, {"strTeam": "Y2", "intPoints": 20}],
    }
    remaining = {"G1": [], "G2": []}
    ratings_df = _ratings(["X1", "X2", "Y1", "Y2"])

    rows = league_interim_rankings(group_probs, standings, remaining, ratings_df)

    assert [r["team"] for r in rows] == ["X1", "Y1", "Y2", "X2"]
    assert [r["position"] for r in rows] == [1, 1, 2, 2]
    # No remaining fixtures -- projected points are exactly the real points
    # (also a regression check for _expected_points' own "teams with zero
    # remaining fixtures must not be dropped" fix, in this same change).
    assert [r["exp_pts"] for r in rows] == [10.0, 3.0, 20.0, 5.0]
    # league_interim_order is a thin wrapper -- must agree exactly.
    assert league_interim_order(group_probs, standings, remaining, ratings_df) == ["X1", "Y1", "Y2", "X2"]


def test_league_interim_rankings_breaks_points_ties_with_goal_difference_then_goals_scored():
    # Real bug (2026-11-17): Serbia and Türkiye both finished last in their
    # own (finished) League A group on 0 points, but Serbia's goal
    # difference (-8) is clearly better than Türkiye's (-11) -- Serbia
    # should rank above Türkiye, not fall to whatever arbitrary order the
    # old points-only tiebreak left them in.
    group_probs = {
        "A1": _one_hot_probs(["France", "Türkiye"]),
        "A2": _one_hot_probs(["Germany", "Serbia"]),
    }
    standings = {
        "A1": [
            {"strTeam": "France", "intPoints": 13, "intGoalDifference": 4, "intGoalsFor": 10},
            {"strTeam": "Türkiye", "intPoints": 0, "intGoalDifference": -11, "intGoalsFor": 4},
        ],
        "A2": [
            {"strTeam": "Germany", "intPoints": 11, "intGoalDifference": 8, "intGoalsFor": 11},
            {"strTeam": "Serbia", "intPoints": 0, "intGoalDifference": -8, "intGoalsFor": 4},
        ],
    }
    remaining = {"A1": [], "A2": []}
    ratings_df = _ratings(["France", "Türkiye", "Germany", "Serbia"])

    rows = league_interim_rankings(group_probs, standings, remaining, ratings_df)
    last_place = [r for r in rows if r["position"] == 2]

    assert [r["team"] for r in last_place] == ["Serbia", "Türkiye"]
    assert league_interim_order(group_probs, standings, remaining, ratings_df)[-2:] == ["Serbia", "Türkiye"]


def test_league_interim_rankings_breaks_gd_ties_with_goals_scored():
    group_probs = {"A1": _one_hot_probs(["X1"]), "A2": _one_hot_probs(["Y1"])}
    standings = {
        "A1": [{"strTeam": "X1", "intPoints": 5, "intGoalDifference": 0, "intGoalsFor": 3}],
        "A2": [{"strTeam": "Y1", "intPoints": 5, "intGoalDifference": 0, "intGoalsFor": 7}],
    }
    remaining = {"A1": [], "A2": []}
    ratings_df = _ratings(["X1", "Y1"])

    rows = league_interim_rankings(group_probs, standings, remaining, ratings_df)

    assert [r["team"] for r in rows] == ["Y1", "X1"]


def test_group_expected_points_keeps_a_team_with_zero_remaining_fixtures():
    # A real bug this change caught: deriving the team roster purely from
    # `remaining_fixtures` drops any team that's already finished its
    # group schedule, so it silently gets treated as 0.0 projected points
    # by every caller instead of its real final points. Not yet live on
    # this site (no NL group has finished every team's games today), but
    # guaranteed to misfire the moment one does.
    teams = ["Finished", "StillPlaying1", "StillPlaying2"]
    standings = [
        {"strTeam": "Finished", "intPoints": 12},
        {"strTeam": "StillPlaying1", "intPoints": 4},
        {"strTeam": "StillPlaying2", "intPoints": 1},
    ]
    # "Finished" appears in no remaining fixture -- the other two still
    # have one match left between themselves.
    remaining_fixtures = [{"strHomeTeam": "StillPlaying1", "strAwayTeam": "StillPlaying2"}]

    exp_pts = group_expected_points(
        teams, _ratings(teams), standings=standings, remaining_fixtures=remaining_fixtures,
    )

    assert exp_pts["Finished"] == 12.0


def test_playoff_entries_only_ever_pair_across_the_two_pools(monkeypatch):
    # Answers a real user question (2026-11-17): does the League A-vs-B
    # (and B-vs-C) "Chance to prevail" projection respect UEFA's own
    # rule that a League A third/fourth-place side can only be drawn
    # against a League B runner-up, never against another League A side
    # (same for League B fourth place vs League C runner-up)? Confirmed
    # by spying on every two_leg_advance_odds call _average_pairing_
    # prevail makes across all 24 permutations: every single tie must
    # have its home side in higher_teams and its away side in
    # lower_teams -- never two teams from the same side facing each other.
    higher_teams = ["Norway", "Croatia", "Wales", "Serbia"]
    lower_teams = ["Slovenia", "Northern Ireland", "Kosovo", "Bosnia and Herzegovina"]
    seen_pairs = []
    real_two_leg_advance_odds = nls.two_leg_advance_odds

    def _spy(home, away, *args, **kwargs):
        seen_pairs.append((home, away))
        return real_two_leg_advance_odds(home, away, *args, **kwargs)

    monkeypatch.setattr(nls, "two_leg_advance_odds", _spy)
    ratings = _ratings(higher_teams + lower_teams)

    entries = project_playoff_entries(
        higher_teams, "League A third place/fourth place",
        lower_teams, "League B runner-up", ratings,
    )

    assert len(seen_pairs) == len(list(itertools.permutations(lower_teams))) * len(higher_teams)
    for home, away in seen_pairs:
        assert home in higher_teams
        assert away in lower_teams

    # Every team from both pools gets a row, and nobody from one pool is
    # mislabeled as belonging to the other.
    assert set(entries[entries["pool"] == "League A third place/fourth place"]["team"]) == set(higher_teams)
    assert set(entries[entries["pool"] == "League B runner-up"]["team"]) == set(lower_teams)


def test_qf_entries_never_pair_a_group_winner_against_its_own_runner_up(monkeypatch):
    # Answers a real user question (2026-11-17): does "Projected
    # Quarterfinals Entries" respect UEFA's own rule that a group's
    # winner can never be drawn against ITS OWN group's runner-up (only
    # a different group's)? Confirmed by spying on every
    # two_leg_advance_odds call project_qf_entries' derangement loop
    # makes, across all 9 valid 4-group derangements, and asserting none
    # of them ever pairs a group's winner with its own runner-up.
    group_probs = {
        "A1": _one_hot_probs(["France", "Belgium"]),
        "A2": _one_hot_probs(["Germany", "Netherlands"]),
        "A3": _one_hot_probs(["England", "Spain"]),
        "A4": _one_hot_probs(["Portugal", "Denmark"]),
    }
    own_runner_up = {"France": "Belgium", "Germany": "Netherlands", "England": "Spain", "Portugal": "Denmark"}
    seen_pairs = []
    real_two_leg_advance_odds = nls.two_leg_advance_odds

    def _spy(home, away, *args, **kwargs):
        seen_pairs.append((home, away))
        return real_two_leg_advance_odds(home, away, *args, **kwargs)

    monkeypatch.setattr(nls, "two_leg_advance_odds", _spy)
    ratings = _ratings(["France", "Belgium", "Germany", "Netherlands", "England", "Spain", "Portugal", "Denmark"])

    entries = project_qf_entries(group_probs, ratings)

    assert len(seen_pairs) == 9 * 4  # 9 valid derangements of 4 groups, 4 ties each
    for home, away in seen_pairs:
        assert own_runner_up[home] != away

    assert set(entries["team"]) == set(own_runner_up.keys()) | set(own_runner_up.values())


def test_load_nl_ratings_uses_strength_ranking_with_name_aliases(monkeypatch, tmp_path):
    # Nations League ratings switched (2026-11-18) from a bespoke
    # eloratings.net scrape + manual odds adjustments (now fully retired)
    # to nation_power_rankings.csv's own combined_rating. This confirms
    # that file's eloratings.net-style names ("Turkey", "Ireland") resolve
    # to this site's own Nations League spelling ("Türkiye", "Republic of
    # Ireland") via the same nations_league_data.GLOBAL_ELO_NAME_ALIASES
    # bridge build_nation_power_rankings.py and euro_2028_group_predictions.py
    # already use, and that an unaliased name (e.g. "Spain") passes
    # through unchanged.
    npr_path = tmp_path / "nation_power_rankings.csv"
    pd.DataFrame({
        "team": ["Spain", "Turkey", "Ireland", "SomeIrrelevantCountry"],
        "combined_rating": [2284.0, 1752.0, 1694.0, 1500.0],
    }).to_csv(npr_path, index=False)
    monkeypatch.setattr(nls, "NATION_POWER_RANKINGS_PATH", str(npr_path))

    ratings = nls._load_nl_ratings_uncached()
    by_team = dict(zip(ratings["team"], ratings["opta_rating"]))

    assert by_team["Spain"] == 2284.0
    assert by_team["Türkiye"] == 1752.0
    assert by_team["Republic of Ireland"] == 1694.0
    assert "SomeIrrelevantCountry" not in by_team
    assert set(ratings.columns) == {"team", "alias", "opta_rating"}


def test_load_nl_ratings_missing_file_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(nls, "NATION_POWER_RANKINGS_PATH", "this_file_does_not_exist.csv")
    ratings = nls._load_nl_ratings_uncached()
    assert list(ratings.columns) == ["team", "alias", "opta_rating"]
    assert len(ratings) == 0
