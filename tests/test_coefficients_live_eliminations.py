"""
Regression test for the real bug caught live 2026-11-05: _compute_ecl_
eliminations() ran EVERY Conference League round (including the League
Phase) through its two-legged-tie elimination logic. Since each League
Phase matchday pairs a club with a different opponent, _group_ties's own
frozenset({home, away}) grouping (built for genuine two-legged knockout
ties) saw each individual League Phase match as its own one-off "tie" and
happily called its loser eliminated -- even though a single League Phase
loss doesn't eliminate anyone (only the final table, or a real knockout
tie, does).
"""

import coefficients_live as cl


def _fixture(round_name, home, away, home_score, away_score, date, event_id):
    return {
        "idEvent": event_id, "strRound": round_name, "dateEvent": date,
        "strHomeTeam": home, "strAwayTeam": away,
        "intHomeScore": home_score, "intAwayScore": away_score,
    }


def test_a_single_league_phase_loss_is_not_reported_as_an_elimination(monkeypatch):
    cl._compute_ecl_eliminations.clear()
    played = [_fixture("League Phase", "Club A", "Club B", 0, 1, "2026-10-30", "ev1")]
    monkeypatch.setattr(cl, "_fetch_comp_fixtures", lambda comp, key: (played, []))
    monkeypatch.setattr(cl, "_load_club_country_map", lambda: {"Club A": "Nation A", "Club B": "Nation B"})

    out = cl._compute_ecl_eliminations("fake-key")
    assert out == []


def test_a_genuine_knockout_tie_loss_is_still_reported(monkeypatch):
    cl._compute_ecl_eliminations.clear()
    played = [_fixture("Quarter-final", "Club A", "Club B", 0, 1, "2026-10-30", "ev1")]
    monkeypatch.setattr(cl, "_fetch_comp_fixtures", lambda comp, key: (played, []))
    monkeypatch.setattr(cl, "_load_club_country_map", lambda: {"Club A": "Nation A", "Club B": "Nation B"})

    out = cl._compute_ecl_eliminations("fake-key")
    assert len(out) == 1
    assert out[0]["club"] == "Club A"
    assert out[0]["country"] == "Nation A"


def test_a_playoff_round_loss_before_the_league_phase_is_still_reported(monkeypatch):
    cl._compute_ecl_eliminations.clear()
    played = [_fixture("Playoff round", "Club A", "Club B", 0, 2, "2026-08-28", "ev1")]
    monkeypatch.setattr(cl, "_fetch_comp_fixtures", lambda comp, key: (played, []))
    monkeypatch.setattr(cl, "_load_club_country_map", lambda: {"Club A": "Nation A", "Club B": "Nation B"})

    out = cl._compute_ecl_eliminations("fake-key")
    assert len(out) == 1
    assert out[0]["club"] == "Club A"
