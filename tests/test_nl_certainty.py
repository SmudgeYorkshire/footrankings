"""
Coverage for nations_league_simulator's mathematical certainty helpers --
group_position_bounds and league_label_certainty -- which back the
Nations League page's "X" (mathematically eliminated) / checkmark
(mathematically clinched) display overrides. These must never assert a
false certainty, so the tests lean on concrete worked examples rather
than just shape checks.
"""

from nations_league_simulator import (
    group_position_bounds, league_label_certainty, _rank_pair_ceiling_at_position,
)


def _group_states(
    pts: dict[str, int], remaining_count: dict[str, int], ranks: dict[str, int] | None = None,
) -> dict[str, dict]:
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
    base_stats = {
        t: ({"pts": p, "rank": ranks[t]} if ranks else {"pts": p})
        for t, p in pts.items()
    }
    return {
        "G1": {
            "teams": teams,
            "base_stats": base_stats,
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


def test_finished_group_uses_real_rank_even_on_an_unresolved_three_way_points_tie():
    # Real bug (2026-11-17, Group A2): Germany/Netherlands/Greece all
    # finish on 11 points with zero fixtures left -- the normal
    # projection logic bails out on a 3-way points tie at the boundary
    # (see _third_team_could_share), which is correct WHILE a fixture
    # remains (a GD guess would be unsound), but wrong once the group has
    # actually finished: real GD has already decided it, nothing left to
    # guess. Each team's own already-fully-tiebroken rank must be used
    # directly instead of re-running the projection.
    states = _group_states(
        {"Germany": 11, "Netherlands": 11, "Greece": 11, "Serbia": 0},
        {"Germany": 0, "Netherlands": 0, "Greece": 0, "Serbia": 0},
        ranks={"Germany": 1, "Netherlands": 2, "Greece": 3, "Serbia": 4},
    )
    bounds = group_position_bounds(states)
    assert bounds["Germany"] == (1, 1)
    assert bounds["Netherlands"] == (2, 2)
    assert bounds["Greece"] == (3, 3)
    assert bounds["Serbia"] == (4, 4)


def test_finished_group_without_rank_data_falls_back_to_the_normal_projection():
    # Same shape as above, but no "rank" supplied in base_stats (older/
    # synthetic state data) -- must not crash, and must fall back to the
    # ordinary (wider, unresolved) bounds rather than silently assuming a
    # rank of 0 or raising a KeyError.
    states = _group_states(
        {"Germany": 11, "Netherlands": 11, "Greece": 11, "Serbia": 0},
        {"Germany": 0, "Netherlands": 0, "Greece": 0, "Serbia": 0},
    )
    bounds = group_position_bounds(states)
    assert bounds["Germany"] == (1, 3)
    assert bounds["Netherlands"] == (1, 3)
    assert bounds["Greece"] == (1, 3)
    assert bounds["Serbia"] == (4, 4)


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


# ---------------------------------------------------------------------------
# Cross-group ranked-position certainty -- league_label_certainty only ever
# ELIMINATED a team from a "ranked" label when the rule's source position
# fell entirely outside group_position_bounds' reachable range (e.g. "can't
# possibly finish 3rd at all"); it never resolved WHICH HALF of a cross-
# group split (e.g. "best two 3rd-place" vs "worst two 3rd-place") a team
# that CAN reach the position would land in, even when every other group's
# own position-3 finisher is mathematically guaranteed to have too few
# points to ever outrank it. Missed live 2026-11-13 (real League A data):
# Italy/France/Belgium (Group A1) all still showed a real percentage for
# "worst two 3rd-place" despite none of League A's other three groups'
# 3rd-place finishers ever being able to out-point them.
# ---------------------------------------------------------------------------

def _multi_group_states(
    group_pts: dict[str, dict[str, int]], group_remaining: dict[str, list[tuple[str, str]]],
    group_played: dict[str, list[tuple[str, str, int, int]]] | None = None,
) -> dict[str, dict]:
    group_played = group_played or {}
    return {
        gname: {
            "teams": list(pts.keys()),
            "base_stats": {t: {"pts": p} for t, p in pts.items()},
            "remaining": [{"strHomeTeam": h, "strAwayTeam": a} for h, a in group_remaining.get(gname, [])],
            "played": [
                {"strHomeTeam": h, "strAwayTeam": a, "intHomeScore": hg, "intAwayScore": ag}
                for h, a, hg, ag in group_played.get(gname, [])
            ],
        }
        for gname, pts in group_pts.items()
    }


# Mirrors real League A data from 2026-11-13 exactly (team names kept the
# same as the live bug report, so this is a faithful regression test, not
# just a structurally-similar synthetic one).
_LEAGUE_A_RULES = [
    ("direct", 1, "Quarterfinals"),
    ("direct", 2, "Quarterfinals"),
    ("ranked", 3, 2, "3rd as Top 2 nations", 2, "Relegation Play-offs"),
    ("ranked", 4, 2, "Relegation Play-offs", 2, "Relegation to League B"),
]
_LEAGUE_A_PTS = {
    "A1": {"Italy": 10, "France": 10, "Belgium": 9, "Turkiye": 0},
    "A2": {"Netherlands": 8, "Greece": 8, "Germany": 5, "Serbia": 0},
    "A3": {"Spain": 15, "England": 12, "Croatia": 3, "Czechia": 0},
    "A4": {"Portugal": 12, "Denmark": 6, "Norway": 3, "Wales": 3},
}
_LEAGUE_A_REMAINING = {
    "A1": [("Belgium", "Italy"), ("France", "Turkiye")],
    "A2": [("Serbia", "Germany"), ("Netherlands", "Greece"), ("Germany", "Netherlands"), ("Greece", "Serbia")],
    "A3": [("Croatia", "Czechia"), ("Spain", "England")],
    "A4": [("Norway", "Wales"), ("Portugal", "Denmark"), ("Denmark", "Norway"), ("Wales", "Portugal")],
}


def test_cross_group_ranked_elimination_from_worst_two_third_place():
    states = _multi_group_states(_LEAGUE_A_PTS, _LEAGUE_A_REMAINING)
    cert = league_label_certainty(states, _LEAGUE_A_RULES)

    # Italy/France (floor 10 pts) can never land in the worst two of the
    # four 3rd-place finishers -- Group A3's 3rd-place finisher can never
    # exceed 6 points (Spain/England are both pinned ahead of Croatia/
    # Czechia), and Group A4's can never exceed 9 (Portugal's pinned
    # 1st/2nd, leaving Denmark/Norway/Wales to fight for 3rd with a shared
    # ceiling that tight) -- only Group A2 (11, Germany's own ceiling once
    # Netherlands/Greece's higher ceilings are capped by needing a 2nd
    # rival to also clear that bar) can ever threaten them, and one
    # potential rival is never enough to push a team out of the top two
    # of four.
    for team in ("Italy", "France"):
        assert cert[team]["Relegation Play-offs"] is False

    # Belgium's own floor (9) EXACTLY ties Group A4's 3rd-place ceiling
    # (9, not strictly below it) -- different groups never play each
    # other, so a cross-group points tie falls straight to overall GD
    # with no bound on the eventual scoreline, and ties must count as
    # "could still beat Belgium" rather than "safe". Confirmed a real bug
    # this way live 2026-11-14 (Wales/Norway wrongly eliminated from an
    # exactly-tied bucket) -- Belgium must stay genuinely open here too.
    assert "Relegation Play-offs" not in cert.get("Belgium", {})


def test_cross_group_ranked_elimination_stays_open_when_genuinely_contested():
    states = _multi_group_states(_LEAGUE_A_PTS, _LEAGUE_A_REMAINING)
    cert = league_label_certainty(states, _LEAGUE_A_RULES)

    # Germany's own floor (5) is low enough that every other group's own
    # 3rd-place ceiling (12 in A1, 6 in A3, 9 in A4) can still clear it --
    # genuinely open, must NOT be asserted either way.
    assert "Relegation Play-offs" not in cert.get("Germany", {})
    assert "3rd as Top 2 nations" not in cert.get("Germany", {})


def test_cross_group_ranked_certainty_stays_silent_with_mismatched_group_count():
    # Only one group present for a rule whose split sizes imply 4 groups
    # (2 + 2) -- the whole "how many OTHER groups could beat it" premise
    # doesn't hold with just one group, so this must stay silent rather
    # than draw a conclusion (a team alone with no real rivals from other
    # groups would otherwise look trivially "safe"). C is pinned to
    # exactly 3rd (reachable, not already eliminated by the plain
    # disjoint-range check), so this specifically exercises the new
    # cross-group refinement's own guard, not the older, unrelated check.
    states = _multi_group_states(
        {"G1": {"A": 10, "B": 9, "C": 3, "D": 0}}, {"G1": [("B", "A")]},
    )
    cert = league_label_certainty(states, _LEAGUE_A_RULES)
    assert "Relegation Play-offs" not in cert.get("C", {})


# ---------------------------------------------------------------------------
# Shared-fixture pairs -- two OTHER rivals who still have to play EACH OTHER
# constrain each other jointly: whichever one of them loses stays low, but
# the other (or both, on a draw) necessarily jumps clear. Plain per-rival
# ceiling/floor bounds can't see this at all, since neither rival's own
# worst case alone need clear the team being tested -- only the fact that
# they can't BOTH be weak simultaneously does. Missed live 2026-11-14
# (real UEFA Nations League Group B3): Israel's own 2nd-place ceiling
# (6, from beating Austria) exactly tied Kosovo's own floor (6, from
# losing to Ireland) -- but Kosovo losing to Ireland means Ireland just
# won that match, so Ireland is ALSO guaranteed clear of Israel in that
# exact scenario (and clear anyway if Kosovo doesn't lose it) -- Israel
# can never actually have two rivals below it, in any outcome.
# ---------------------------------------------------------------------------

def test_shared_remaining_fixture_between_two_rivals_bounds_a_third_team():
    # Mirrors real Group B3 (Austria/Republic of Ireland/Kosovo/Israel,
    # 2026-11-14) exactly: Austria's own floor (8) already clears
    # Israel's ceiling (6) outright, and Kosovo/Ireland's own remaining
    # fixture against EACH OTHER means at least one of them always does
    # too -- so Israel can never reach 2nd, only ever 3rd or 4th.
    pts = {"Austria": 8, "Ireland": 5, "Kosovo": 6, "Israel": 3}
    remaining = [
        ("Austria", "Ireland"), ("Ireland", "Kosovo"), ("Israel", "Austria"),
    ]
    states = _multi_group_states({"G1": pts}, {"G1": remaining})

    bounds = group_position_bounds(states)

    assert bounds["Israel"] == (3, 4)


def test_shared_remaining_fixture_stays_silent_when_the_pair_could_both_stay_low():
    # Same shape, but Ireland's floor is pulled down further (0 instead
    # of 5) so the "Kosovo loses to Ireland" branch no longer forces
    # Ireland above the team being tested (t)'s ceiling -- that branch's
    # max(Kosovo=6, Ireland=0+3=3) = 6, exactly tying rather than
    # clearing t's ceiling, so this specific pair can no longer be
    # asserted to guarantee one of them above. A deliberately adjacent
    # negative case to the real one above, to catch a too-eager version
    # of the fix.
    pts = {"Austria": 8, "Ireland": 0, "Kosovo": 6, "Israel": 3}
    remaining = [
        ("Austria", "Ireland"), ("Ireland", "Kosovo"), ("Israel", "Austria"),
    ]
    states = _multi_group_states({"G1": pts}, {"G1": remaining})

    bounds = group_position_bounds(states)

    assert bounds["Israel"] == (2, 4)


def test_shared_remaining_fixture_mechanism_ignores_two_legs_still_to_play():
    # Both legs between the pair still remain (not just one) -- this
    # mechanism deliberately doesn't attempt the resulting 9-branch
    # combinatorics, so it must stay silent rather than guess.
    pts = {"Leader": 20, "RivalA": 5, "RivalB": 6, "Trailer": 3}
    remaining = [("RivalA", "RivalB"), ("RivalB", "RivalA"), ("Trailer", "Leader")]
    states = _multi_group_states({"G1": pts}, {"G1": remaining})

    bounds = group_position_bounds(states)

    # Leader is pinned 1st outright (current already beats every rival's
    # ceiling); Trailer's own bound must NOT additionally tighten from
    # the two-legs-remaining RivalA/RivalB pair.
    assert bounds["Trailer"][0] == 2


# ---------------------------------------------------------------------------
# Real head-to-head GD/GF can break a boundary tie that h2h_pts alone can't
# -- but ONLY from already-decided results (never a still-unplayed
# fixture's unknown margin). Missed live 2026-11-14 (real UEFA Nations
# League Group A4): Wales' ceiling (6, from beating Portugal) was exactly
# tied by BOTH Denmark's and Norway's own floor (6 each, only by losing
# their shared Denmark-Norway fixture) -- the plain single-rival check
# bails on each individually (the other could share that same value, see
# _third_team_could_share), and even _pair_guarantees_one_above only
# proves "at least one" clears, leaving a false "could still reach 3rd".
# The real UEFA tiebreak order resolves it: Wales already lost both legs
# to Denmark outright (6-0 on real h2h points), and while Wales/Norway
# split 1-1 on real h2h points, Norway's real h2h GD against Wales is +1
# (Wales') own 2-1 win is outweighed by Norway's 3-1 win) -- so whichever
# of Denmark/Norway stays at 6, it's already proven above Wales on real
# results alone, in every possible result of their own shared fixture.
# ---------------------------------------------------------------------------

def test_shared_remaining_fixture_tie_resolved_by_real_h2h_gd_both_sides():
    # Mirrors real Group A4 (Portugal/Denmark/Norway/Wales, 2026-11-14)
    # exactly in shape: Wales' ceiling (6) is tied by both Denmark's and
    # Norway's own floor, but both are already provably above Wales on
    # real head-to-head results (Denmark outright on h2h points, Norway
    # on h2h GD after a 1-1 h2h-points split) -- so Wales is pinned to
    # 4th no matter how the Denmark-Norway fixture itself goes.
    pts = {"Portugal": 12, "Denmark": 6, "Norway": 6, "Wales": 3}
    remaining = [("Portugal", "Denmark"), ("Denmark", "Norway"), ("Wales", "Portugal")]
    played = [
        ("Denmark", "Wales", 2, 0), ("Wales", "Denmark", 0, 1),  # Denmark 6-0 on h2h points
        ("Wales", "Norway", 2, 1), ("Norway", "Wales", 3, 1),  # 1-1 on h2h points, Norway +1 h2h GD
    ]
    states = _multi_group_states({"G1": pts}, {"G1": remaining}, {"G1": played})

    bounds = group_position_bounds(states)

    assert bounds["Wales"] == (4, 4)


def test_shared_remaining_fixture_tie_stays_open_when_real_h2h_also_ties():
    # Same shape, but Norway's two meetings against Wales are now an exact
    # mirror of each other (2-1 and 1-2) -- h2h points AND h2h GD AND h2h
    # GF all tie too, so the real tiebreak chain is exhausted without a
    # winner (would fall through to overall GD/GF, which this module
    # won't guess at). The pair can no longer be proven to BOTH clear
    # Wales, only that at least one of them still does (the weaker,
    # already-existing guarantee) -- a deliberately adjacent negative
    # case to the real one above, to catch a too-eager version of the fix.
    pts = {"Portugal": 12, "Denmark": 6, "Norway": 6, "Wales": 3}
    remaining = [("Portugal", "Denmark"), ("Denmark", "Norway"), ("Wales", "Portugal")]
    played = [
        ("Denmark", "Wales", 2, 0), ("Wales", "Denmark", 0, 1),
        ("Wales", "Norway", 2, 1), ("Norway", "Wales", 1, 2),  # now an exact mirror -- fully tied h2h
    ]
    states = _multi_group_states({"G1": pts}, {"G1": remaining}, {"G1": played})

    bounds = group_position_bounds(states)

    assert bounds["Wales"] == (3, 4)


def test_real_h2h_gd_ignored_when_a_fixture_remains_between_them():
    # Direct test of _fully_decided_h2h_winner's own guard (the simpler,
    # plain 2-team boundary case, not the 3-team shared-fixture one above):
    # T and O still have one leg left between them, so real h2h GD can't
    # be trusted as final while that match's own margin is still unknown.
    # O already leads 3-0 on real h2h points from leg 1, but T reaching
    # its own ceiling (3) requires winning the remaining leg, which would
    # tie h2h points 3-3 with the actual margin genuinely unresolved (a
    # real, not just synthetic, "no certainty" case) -- must stay silent
    # rather than guess at the still-unplayed leg's own GD.
    pts = {"T": 0, "O": 3}
    remaining = [("T", "O")]
    played = [("O", "T", 3, 0)]
    states = _multi_group_states({"G1": pts}, {"G1": remaining}, {"G1": played})

    bounds = group_position_bounds(states)

    assert bounds["T"] == (1, 2)


def test_real_h2h_gd_breaks_a_plain_two_team_boundary_tie():
    # Exercises the simpler, non-shared-fixture upgrade directly: T's
    # ceiling (8, one remaining win) is tied exactly by O's current (8,
    # already done for the season) -- h2h points between them are tied
    # 3-3 (one win each, already fully played, nothing left between
    # them), but O's real h2h GD (+1) beats T's (-1), so O is already
    # provably above T regardless of anything else left to play.
    pts = {"T": 5, "O": 8, "Filler": 0}
    remaining = [("T", "Filler")]
    played = [("T", "O", 1, 0), ("O", "T", 2, 0)]
    states = _multi_group_states({"G1": pts}, {"G1": remaining}, {"G1": played})

    bounds = group_position_bounds(states)

    assert bounds["T"] == (2, 2)


# ---------------------------------------------------------------------------
# A team's plain, unconditional ceiling (group_position_bounds' own best/
# worst) can be strictly higher than what it could ACTUALLY have while
# ranked at one specific worse-than-best position, when reaching that raw
# ceiling requires beating the one rival whose own result decides which of
# them outranks the other -- that same win would rank the team ABOVE that
# rival instead, never at the worse position being asked about. Missed
# live 2026-11-14 (real UEFA Nations League Group A4): Norway's raw
# ceiling (9, from beating Denmark) never actually co-occurs with Norway
# ranked 3rd -- beating Denmark puts Norway above Denmark instead (6-0 on
# real h2h points after that result), so the ceiling conditioned on being
# 3rd is really 7 (a draw, Denmark's other game going well enough to
# still pull clear on raw points) -- tight enough for 2 filler groups'
# fixed 3rd-place floors (9 and 8, neither exceeding the untightened 9) to
# finally prove Norway's elimination from "top two of four 3rd-placers".
# ---------------------------------------------------------------------------

_RANK_PAIR_RULES = [("ranked", 3, 2, "3rd as Top 2 nations", 2, "Relegation Play-offs")]


def test_rank_pair_ceiling_tightens_a_cross_group_elimination():
    # Mirrors real Group A4 exactly for G1; G2/G3 are simple pinned
    # groups (no games left at all) whose 3rd-placed team sits at a
    # fixed 9 and 8 points respectively -- too low to beat Norway's old,
    # untightened ceiling (9) but enough once it's tightened to 7. G4 is
    # just there to satisfy the rule's own "exactly 4 groups" premise.
    group_pts = {
        "G1": {"Portugal": 12, "Denmark": 6, "Norway": 6, "Wales": 3},
        "G2": {"G2Top": 20, "G2Second": 15, "G2Third": 9, "G2Bottom": 0},
        "G3": {"G3Top": 20, "G3Second": 15, "G3Third": 8, "G3Bottom": 0},
        "G4": {"G4Top": 20, "G4Second": 15, "G4Third": 1, "G4Bottom": 0},
    }
    group_remaining = {"G1": [("Portugal", "Denmark"), ("Denmark", "Norway"), ("Wales", "Portugal")]}
    group_played = {"G1": [("Norway", "Denmark", 3, 2)]}
    states = _multi_group_states(group_pts, group_remaining, group_played)

    cert = league_label_certainty(states, _RANK_PAIR_RULES)

    assert cert["Norway"]["3rd as Top 2 nations"] is False


def test_rank_pair_ceiling_direct_unit_check():
    # Same G1 shape, checked directly against the helper rather than
    # through the full cross-group rule -- isolates exactly what's being
    # tightened and from what.
    pts = {"Portugal": 12, "Denmark": 6, "Norway": 6, "Wales": 3}
    remaining = [("Portugal", "Denmark"), ("Denmark", "Norway"), ("Wales", "Portugal")]
    played = [("Norway", "Denmark", 3, 2)]
    states = _multi_group_states({"G1": pts}, {"G1": remaining}, {"G1": played})
    bounds = group_position_bounds(states)
    state = states["G1"]

    ceiling_at_3 = _rank_pair_ceiling_at_position(
        state["teams"],
        {t: p for t, p in pts.items()},
        {"Portugal": 18, "Denmark": 12, "Norway": 9, "Wales": 6},
        state["played"], state["remaining"], bounds, "Norway", 3,
    )

    assert ceiling_at_3 == 7


def test_rank_pair_ceiling_falls_back_when_two_rivals_both_contend():
    # Fully hand-constructed (not derived through group_position_bounds)
    # to isolate the precondition itself: T has TWO separate rivals, O1
    # and O2, each individually sharing exactly one remaining fixture
    # with T and each still a live contender for the slot directly above
    # T's own best position -- the simple two-team framing ("whichever
    # of exactly these two outranks the other decides it") no longer
    # holds with two of them, so this must fall back to the raw,
    # untightened ceiling rather than guess which one (if either)
    # actually ends up deciding T's fate.
    teams = ["T", "O1", "O2"]
    current = {"T": 6, "O1": 6, "O2": 6}
    ceiling = {"T": 9, "O1": 9, "O2": 9}
    bounds = {"T": (1, 2), "O1": (1, 2), "O2": (1, 2)}
    remaining = [{"strHomeTeam": "T", "strAwayTeam": "O1"}, {"strHomeTeam": "T", "strAwayTeam": "O2"}]

    ceiling_at_2 = _rank_pair_ceiling_at_position(teams, current, ceiling, [], remaining, bounds, "T", 2)

    assert ceiling_at_2 == ceiling["T"]
