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


# ---------------------------------------------------------------------------
# Head-to-head boundary refinement -- plain points alone can't prove a team
# is eliminated from a position when a rival's current points exactly TIE
# that team's own ceiling (current[o] == ceiling[t] is not current[o] >
# ceiling[t]), even though the real head-to-head record can still make it
# certain. Missed live 2026-11-13 (Group C1): Finland's ceiling (10, one
# remaining win) exactly tied Belarus's current points (10, reachable just
# by losing their own last game) -- Belarus already led 4-1 on real head-to-
# head points, so Finland could never actually finish above them, but the
# old points-only bounds still showed Finland as "possibly 2nd".
# ---------------------------------------------------------------------------

def _h2h_group_state(
    teams: list[str], pts: dict[str, int], played: list[dict], remaining: list[dict],
) -> dict[str, dict]:
    return {"G1": {
        "teams": teams,
        "base_stats": {t: {"pts": p} for t, p in pts.items()},
        "remaining": remaining,
        "played": played,
    }}


def test_real_group_c1_finland_pinned_to_3rd_by_head_to_head():
    teams = ["Albania", "Belarus", "Finland", "San Marino"]
    pts = {"Albania": 12, "Belarus": 10, "Finland": 7, "San Marino": 0}
    played = [
        {"strHomeTeam": "Finland", "strAwayTeam": "Belarus", "intHomeScore": 0, "intAwayScore": 0},
        {"strHomeTeam": "Belarus", "strAwayTeam": "Finland", "intHomeScore": 1, "intAwayScore": 0},
    ]
    remaining = [
        {"strHomeTeam": "Finland", "strAwayTeam": "San Marino"},
        {"strHomeTeam": "Belarus", "strAwayTeam": "Albania"},
    ]
    states = _h2h_group_state(teams, pts, played, remaining)

    bounds = group_position_bounds(states)

    # Finland's ceiling (7 + 3 = 10) exactly ties Belarus's current points
    # (10) -- indistinguishable from "still open" on points alone -- but
    # Belarus already leads the real head-to-head 4-1 (a draw + a win, with
    # no remaining fixture left between them to change that), so Finland
    # can never actually finish above Belarus. Pinned to exactly 3rd.
    assert bounds["Finland"] == (3, 3)


def test_head_to_head_refinement_stays_silent_on_an_exact_tie():
    # Same points-ceiling tie as above, but this time the two teams' real
    # head-to-head record is a dead heat (one win each) -- nothing here can
    # resolve it without guessing at goal difference, so bounds must NOT
    # assert elimination either way. Trailer's one remaining fixture is
    # against a third team, not Leader, so the head-to-head record stays
    # exactly what's already been played (a clean win each).
    teams = ["Leader", "Trailer", "Filler"]
    pts = {"Leader": 10, "Trailer": 7, "Filler": 0}
    played = [
        {"strHomeTeam": "Trailer", "strAwayTeam": "Leader", "intHomeScore": 1, "intAwayScore": 0},
        {"strHomeTeam": "Leader", "strAwayTeam": "Trailer", "intHomeScore": 1, "intAwayScore": 0},
    ]
    remaining = [{"strHomeTeam": "Trailer", "strAwayTeam": "Filler"}]
    states = _h2h_group_state(teams, pts, played, remaining)

    bounds = group_position_bounds(states)

    # Trailer's ceiling (7 + 3 = 10) ties Leader's current points (10), and
    # their head-to-head is a dead heat (3 pts each) -- genuinely
    # unresolved, so Trailer must NOT be shown as provably behind Leader.
    assert bounds["Trailer"] == (1, 2)


def test_head_to_head_bonus_goes_to_the_maximizer_not_whichever_team_is_tested_first():
    # Directional check for the fix itself: when t's ceiling ties o's
    # current points, it's t who must win every remaining fixture
    # (including any one left against o) to reach that ceiling -- so if a
    # fixture between t and o is STILL remaining, t (not o) gets credited
    # with winning it in this exact boundary scenario. Here, Leader's
    # current points (10) tie Trailer's ceiling (7 + one remaining win = 10)
    # -- Trailer must beat Leader in their still-to-play fixture to reach
    # that ceiling, which would flip their head-to-head record from
    # Leader's real 3-0 lead to a 3-3 tie, NOT extend Leader's lead. Trailer
    # must therefore stay open at 2nd, not be wrongly eliminated by
    # crediting that remaining fixture to the wrong side.
    teams = ["Leader", "Trailer"]
    pts = {"Leader": 10, "Trailer": 7}
    played = [{"strHomeTeam": "Leader", "strAwayTeam": "Trailer", "intHomeScore": 1, "intAwayScore": 0}]
    remaining = [{"strHomeTeam": "Trailer", "strAwayTeam": "Leader"}]
    states = _h2h_group_state(teams, pts, played, remaining)

    bounds = group_position_bounds(states)

    assert bounds["Trailer"] == (1, 2)
