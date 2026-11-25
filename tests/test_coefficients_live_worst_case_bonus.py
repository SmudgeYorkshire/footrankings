"""
Regression test for the real gap caught live 2026-11-25: the D.5 bonus
functions only ever credited a club TWO values over the whole season --
a flat "just made the League Phase" floor, and the real per-rank value
once the ENTIRE League Phase had concluded for every club. A club that
had mathematically secured a much better bracket mid-season (e.g. locked
into the top half, or into a direct top-8 Round-of-16 spot) got no
credit for that until the season was completely over. The user noticed
this directly: Real Madrid got no bonus-point update despite a result
that should have narrowed their guaranteed range.

Both _compute_secured_league_phase_bonus (D.5b, the sliding per-rank
bonus) and _compute_round_reached_bonus (D.5a, the top-8-reaches-R16
bonus) now consult _live_league_phase_bounds -- the same exact_position_
bounds engine behind european.py's own Best/Worst columns -- so a club's
credited bonus tightens progressively as its range narrows, not just at
those two fixed points.
"""

import coefficients_live as cl


def _fixture(round_name, home, away, home_score, away_score, event_id, date="2026-11-25"):
    return {
        "idEvent": event_id, "strRound": round_name, "dateEvent": date,
        "strHomeTeam": home, "strAwayTeam": away,
        "intHomeScore": home_score, "intAwayScore": away_score,
    }


def _remaining_fixture(round_name, home, away, event_id, date="2026-12-01"):
    return {
        "idEvent": event_id, "strRound": round_name, "dateEvent": date,
        "strHomeTeam": home, "strAwayTeam": away,
        "intHomeScore": None, "intAwayScore": None,
    }


def _clear_caches():
    for fn in (
        cl._fetch_comp_fixtures, cl._final_league_phase_standings,
        cl._live_league_phase_bounds, cl._compute_secured_league_phase_bonus,
        cl._compute_round_reached_bonus, cl._compute_league_phase_bonus_points,
        cl._bonus_added_this_week,
    ):
        fn.clear()


def _patch_fixtures(monkeypatch, comp_fixtures: dict[str, tuple[list, list]]):
    def fake_fetch(comp_name, key):
        return comp_fixtures.get(comp_name, ([], []))
    monkeypatch.setattr(cl, "_fetch_comp_fixtures", fake_fetch)


def test_d5b_bonus_tightens_to_the_live_worst_case_not_the_flat_floor(monkeypatch):
    # T has already clinched a clear lead (9 points, 0 remaining games of
    # its own). O is still mid-table with a game left against a filler
    # club -- a genuine contender for T's worst case, but T's own range
    # is already narrow regardless of how O's last game goes. The point
    # is simply that this must NOT fall back to the flat Champions League
    # floor (6.000) -- it must reflect T's actual live Worst rank.
    played = [
        _fixture("League Stage", "T", "P1", 3, 0, "ev1"),
        _fixture("League Stage", "T", "P2", 2, 0, "ev2"),
        _fixture("League Stage", "T", "P3", 1, 0, "ev3"),
        _fixture("League Stage", "O", "P4", 1, 0, "ev4"),
        _fixture("League Stage", "O", "P5", 1, 1, "ev5"),
    ]
    remaining = [_remaining_fixture("League Stage", "O", "W", "ev6")]
    _clear_caches()
    _patch_fixtures(monkeypatch, {"Champions League": (played, remaining)})

    live_bounds = cl._live_league_phase_bounds("Champions League", "fake-key")
    assert live_bounds is not None, "League Phase is still in progress -- must not be None"
    expected_worst = live_bounds["T"][1]

    bonus = cl._compute_secured_league_phase_bonus("fake-key")
    assert bonus["T"] == cl._league_phase_bonus(expected_worst, "Champions League")
    assert bonus["T"] != 6.0, "must not have silently fallen back to the flat worst-of-36 floor"


def test_d5a_top_8_bonus_credited_early_once_worst_rank_locks_it_in(monkeypatch):
    # Only T and O exist in this toy competition -- T is unambiguously
    # guaranteed to finish above O regardless of anything left to play,
    # so T's Worst rank is at most 2 (trivially <= 8) well before the
    # League Phase as a whole has concluded (O still has a game left).
    played = [
        _fixture("League Stage", "T", "P1", 3, 0, "ev1"),
        _fixture("League Stage", "T", "P2", 3, 0, "ev2"),
        _fixture("League Stage", "O", "P3", 0, 0, "ev3"),
    ]
    remaining = [_remaining_fixture("League Stage", "O", "W", "ev4")]
    _clear_caches()
    _patch_fixtures(monkeypatch, {"Champions League": (played, remaining)})

    live_bounds = cl._live_league_phase_bounds("Champions League", "fake-key")
    assert live_bounds["T"][1] <= 8

    bonus = cl._compute_round_reached_bonus("fake-key")
    assert bonus.get("T") == cl._BONUS_PER_STAGE["Champions League"]


def test_europa_and_conference_league_also_get_live_bonus_not_just_champions_league(monkeypatch):
    # The old flat-floor mechanism only ever credited the Champions
    # League (the other two competitions' floor is 0.000, so the old
    # code skipped them entirely via "if floor <= 0.0: continue"). The
    # live-bounds mechanism has no such excuse -- a genuinely secure
    # Europa League club should still get a real, nonzero D.5b credit.
    played = [
        _fixture("League Stage", "T", "P1", 3, 0, "ev1"),
        _fixture("League Stage", "T", "P2", 3, 0, "ev2"),
    ]
    remaining = [_remaining_fixture("League Stage", "T", "P3", "ev3")]
    _clear_caches()
    _patch_fixtures(monkeypatch, {"Europa League": (played, remaining)})

    bonus = cl._compute_secured_league_phase_bonus("fake-key")
    assert bonus.get("T", 0.0) > 0.0


def test_bonus_added_this_week_reflects_a_result_that_narrows_the_range(monkeypatch):
    # T beat two minnows BEFORE this week (6 points, done playing them).
    # O also picked up points before this week (3) but still has a game
    # left against T -- a genuine threat to T's worst case at that point,
    # since O's ceiling (3+3=6) hadn't yet fallen below T's own points.
    # THIS week, T beats O 3-0: T is now fixed at 9, and O's remaining
    # ceiling (3+3=6, one game left against a filler club) can no longer
    # reach 9 -- O stops being a threat to T entirely. That's a real,
    # meaningful tightening of T's guaranteed range that happened
    # entirely within this week's own results.
    before_week = [
        _fixture("League Stage", "T", "P1", 3, 0, "ev1", date="2026-11-10"),
        _fixture("League Stage", "T", "P2", 3, 0, "ev2", date="2026-11-17"),
        _fixture("League Stage", "O", "P3", 1, 0, "ev3", date="2026-11-10"),
    ]
    this_week = [_fixture("League Stage", "T", "O", 3, 0, "ev4", date="2026-11-24")]
    still_remaining = [_remaining_fixture("League Stage", "O", "W", "ev5", date="2026-12-01")]
    played = before_week + this_week
    _clear_caches()
    _patch_fixtures(monkeypatch, {"Champions League": (played, still_remaining)})

    added = cl._bonus_added_this_week("fake-key", "2026-11-24")
    assert added.get("T", 0.0) > 0.0


def test_falls_back_to_flat_floor_before_the_league_phase_fixture_list_exists(monkeypatch):
    # No League Stage fixtures published yet at all for this competition
    # (e.g. straight after the Play-off round, before the draw) -- must
    # still fall back to the old confirmed-entrant/floor behaviour rather
    # than crediting nothing.
    _clear_caches()
    _patch_fixtures(monkeypatch, {})
    monkeypatch.setattr(
        cl, "CONFIRMED_LEAGUE_PHASE",
        {"Champions League": [("T", "Nation A", "league")], "Europa League": [], "Conference League": []},
    )

    assert cl._live_league_phase_bounds("Champions League", "fake-key") is None
    bonus = cl._compute_secured_league_phase_bonus("fake-key")
    assert bonus.get("T") == cl._SECURED_LP_FLOOR["Champions League"]
