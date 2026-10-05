"""
Coverage for nations_league_simulator's mathematical certainty helpers --
group_position_bounds and league_label_certainty -- which back the
Nations League page's "X" (mathematically eliminated) / checkmark
(mathematically clinched) display overrides. These must never assert a
false certainty, so the tests lean on concrete worked examples rather
than just shape checks.
"""

from nations_league_simulator import group_position_bounds, league_label_certainty


def _group_states(pts: dict[str, int], remaining_count: dict[str, int]) -> dict[str, dict]:
    teams = list(pts.keys())
    # Build `remaining_count[t]` fixtures each team appears in (paired up
    # arbitrarily -- group_position_bounds only counts appearances).
    fixtures = []
    pool = []
    for t, n in remaining_count.items():
        pool.extend([t] * n)
    # Pair consecutive entries as home/away fixtures (fine for a count-only test).
    while len(pool) >= 2:
        fixtures.append({"strHomeTeam": pool.pop(), "strAwayTeam": pool.pop()})
    return {
        "G1": {
            "teams": teams,
            "base_stats": {t: {"pts": p} for t, p in pts.items()},
            "remaining": fixtures,
        }
    }


def test_clinched_top_spot_when_ceiling_of_all_rivals_is_below_current_points():
    # A: 20 pts, 0 games left. B: 10 pts, 2 games left (ceiling 16, still < 20).
    # C: 5 pts, 2 games left (ceiling 11). D: 5 pts, 2 games left (ceiling 11).
    states = _group_states({"A": 20, "B": 10, "C": 5, "D": 5}, {"A": 0, "B": 2, "C": 2, "D": 2})
    bounds = group_position_bounds(states)
    assert bounds["A"] == (1, 1)  # pinned to 1st: nobody can catch up


def test_eliminated_from_top_two_when_two_rivals_already_guarantee_more():
    # E has 5 pts with 0 games left (ceiling 5). Two rivals already sit on
    # 15 pts each (guaranteed above E's ceiling) -- E can be at best 3rd.
    states = _group_states({"E": 5, "F": 15, "G": 15, "H": 0}, {"E": 0, "F": 2, "G": 2, "H": 2})
    bounds = group_position_bounds(states)
    best, worst = bounds["E"]
    assert best == 3


def test_fully_open_group_has_no_pinned_positions():
    states = _group_states({"A": 3, "B": 3, "C": 3, "D": 3}, {"A": 6, "B": 6, "C": 6, "D": 6})
    bounds = group_position_bounds(states)
    for t in ("A", "B", "C", "D"):
        best, worst = bounds[t]
        assert best == 1 and worst == 4


def test_league_a_style_rules_eliminate_cross_group_labels_once_top_two_clinched():
    # League-A-shaped rules: direct QF for 1st/2nd, ranked 3rd/4th splits.
    rules = [
        ("direct", 1, "Quarterfinals"),
        ("direct", 2, "Quarterfinals"),
        ("ranked", 3, 2, "3rd as Top 2 nations", 2, "Relegation Play-offs"),
        ("ranked", 4, 2, "Relegation Play-offs", 2, "Relegation to League B"),
    ]
    # A: pinned to 1st (clinched QF). Nobody else pinned.
    states = _group_states({"A": 20, "B": 10, "C": 5, "D": 5}, {"A": 0, "B": 2, "C": 2, "D": 2})
    cert = league_label_certainty(states, rules)
    assert cert["A"]["Quarterfinals"] is True
    # A can't possibly finish 3rd or 4th -> eliminated from every
    # cross-group bucket sourced from those positions. "Relegation
    # Play-offs" is itself a _PLAYOFF_POOLS label (shared by BOTH the
    # position-3 bottom split and the position-4 top split), so its
    # elimination surfaces on its post-split win/lose columns, the same
    # columns simulate_league_outcomes' own probs_df actually carries.
    assert cert["A"]["3rd as Top 2 nations"] is False
    assert cert["A"]["Promoted in Play-offs"] is False
    assert cert["A"]["Relegated in Play-offs"] is False
    assert cert["A"]["Relegation to League B"] is False


def test_playoff_pool_label_elimination_propagates_to_split_columns():
    # League-B-shaped rules: direct position-4 rule feeds a play-off pool
    # that simulate_league_outcomes later splits into win/lose columns.
    rules = [
        ("direct", 1, "Promotion"),
        ("direct", 2, "Promotion Play-offs"),
        ("direct", 4, "Relegation Play-offs"),
    ]
    # Team pinned to 1st can never reach position 4 -> eliminated from
    # BOTH of "Relegation Play-offs"' split outcomes.
    states = _group_states({"A": 20, "B": 10, "C": 5, "D": 5}, {"A": 0, "B": 2, "C": 2, "D": 2})
    cert = league_label_certainty(states, rules)
    assert cert["A"]["Promoted in Play-offs"] is False
    assert cert["A"]["Relegated in Play-offs"] is False
    # And "Promotion Play-offs" (pos 2) is also unreachable for A (pinned 1st).
    assert cert["A"]["Won Promotion Play-offs"] is False
    assert cert["A"]["Lost Promotion Play-offs"] is False


def test_ranked_label_with_two_source_positions_needs_both_routes_closed():
    # "Relegation Play-offs" is fed by BOTH the position-3 bottom cut AND
    # the position-4 top cut. A team that can still reach position 3 (but
    # not 4) must stay OPEN on that label, not get wrongly eliminated
    # just because one of its two routes in happens to be closed.
    rules = [
        ("direct", 1, "Quarterfinals"),
        ("direct", 2, "Quarterfinals"),
        ("ranked", 3, 2, "3rd as Top 2 nations", 2, "Relegation Play-offs"),
        ("ranked", 4, 2, "Relegation Play-offs", 2, "Relegation to League B"),
    ]
    # B/C/D are tied on points with games left (fully open 1st-3rd among
    # them); E is already mathematically last (0 pts, 0 games left, can
    # never catch any of the other three's current points). So B can
    # still finish anywhere 1st-3rd, but never 4th.
    states = _group_states({"B": 10, "C": 10, "D": 10, "E": 0}, {"B": 2, "C": 2, "D": 2, "E": 0})
    bounds = group_position_bounds(states)
    best, worst = bounds["B"]
    assert (best, worst) == (1, 3)
    cert = league_label_certainty(states, rules)
    # Position 4 is unreachable for B, but position 3 still is -- so
    # "Relegation Play-offs" (fed by position 3 too) must stay OPEN.
    assert "Promoted in Play-offs" not in cert.get("B", {})
    assert "Relegated in Play-offs" not in cert.get("B", {})
    # "Relegation to League B" is ONLY fed by position 4 -- correctly
    # eliminated outright since B can never reach position 4 at all.
    assert cert["B"]["Relegation to League B"] is False


def test_clinched_pool_entry_surfaces_on_raw_label_not_split_columns():
    # League-B-shaped rules: direct position-4 rule feeds a play-off pool.
    rules = [
        ("direct", 1, "Promotion"),
        ("direct", 2, "Promotion Play-offs"),
        ("direct", 4, "Relegation Play-offs"),
    ]
    # Team pinned to exactly 4th is guaranteed to reach the relegation
    # play-off pool -- but which way that tie goes is still open.
    states = _group_states({"A": 20, "B": 10, "C": 5, "D": 0}, {"A": 0, "B": 2, "C": 2, "D": 0})
    cert = league_label_certainty(states, rules)
    assert cert["D"]["Relegation Play-offs"] is True
    assert "Promoted in Play-offs" not in cert.get("D", {})
    assert "Relegated in Play-offs" not in cert.get("D", {})


def test_never_asserts_certainty_in_a_fully_open_scenario():
    rules = [
        ("direct", 1, "Promotion"),
        ("direct", 2, "Promotion Play-offs"),
        ("direct", 4, "Relegation Play-offs"),
    ]
    states = _group_states({"A": 3, "B": 3, "C": 3, "D": 3}, {"A": 6, "B": 6, "C": 6, "D": 6})
    cert = league_label_certainty(states, rules)
    assert cert == {}
