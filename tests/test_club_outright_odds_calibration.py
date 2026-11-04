"""
Tests for club_outright_odds_calibration.py's shared nudge helper --
same style as tests/test_club_odds_ratings.py's own _fit_persistent tests
(small synthetic inputs, no live API/field data needed).
"""

import pytest

import club_outright_odds_calibration as coc


def test_apply_outright_nudge_seeds_from_raw_when_no_current_entry():
    state = {}
    delta = coc.apply_outright_nudge(
        state, ("4328", "Arsenal"), raw_rating=90.0, alias="",
        model_prob=0.10, market_prob=0.15,
    )
    # error = 0.15 - 0.10 = 0.05 -> delta = 24.0 * 0.05 = 1.2
    assert delta == pytest.approx(1.2)
    assert state[("4328", "Arsenal")]["rating"] == pytest.approx(91.2)
    assert state[("4328", "Arsenal")]["seed"] == 90.0
    assert state[("4328", "Arsenal")]["n_updates"] == 0


def test_apply_outright_nudge_seeds_from_current_persisted_rating():
    state = {("4328", "Arsenal"): {"alias": "", "rating": 95.0, "seed": 90.0, "n_updates": 4, "last_updated": "2026-10-01"}}
    delta = coc.apply_outright_nudge(
        state, ("4328", "Arsenal"), raw_rating=90.0, alias="",
        model_prob=0.20, market_prob=0.20,
    )
    assert delta == pytest.approx(0.0)
    assert state[("4328", "Arsenal")]["rating"] == pytest.approx(95.0)


def test_apply_outright_nudge_does_not_touch_n_updates():
    state = {("4328", "Arsenal"): {"alias": "", "rating": 90.0, "seed": 90.0, "n_updates": 7, "last_updated": "x"}}
    coc.apply_outright_nudge(state, ("4328", "Arsenal"), 90.0, "", model_prob=0.05, market_prob=0.25)
    assert state[("4328", "Arsenal")]["n_updates"] == 7


def test_apply_outright_nudge_clamps_to_sanity_bounds():
    state = {}
    coc.apply_outright_nudge(
        state, ("4328", "LongShot"), raw_rating=5.0, alias="",
        model_prob=0.001, market_prob=0.999,  # huge error, way more than the cap can move it in one nudge
    )
    rating = state[("4328", "LongShot")]["rating"]
    assert coc.RATING_SANITY_MIN <= rating <= coc.RATING_SANITY_MAX


def test_apply_outright_nudge_negative_error_lowers_rating():
    state = {}
    delta = coc.apply_outright_nudge(
        state, ("4328", "Overrated"), raw_rating=90.0, alias="",
        model_prob=0.30, market_prob=0.10,
    )
    assert delta < 0
    assert state[("4328", "Overrated")]["rating"] < 90.0


# ---------------------------------------------------------------------------
# _resolve_field_league_ids -- regression coverage for the real collision
# bug caught live 2026-11-04: a flat, team-column-only dict silently
# resolved England's "Arsenal" to Belarus's league_id (both share the
# literal name), and separately missed any club whose field name is a
# ratings CSV's ALIAS rather than its "team" column (e.g. "Olympiacos").
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_leagues(tmp_path, monkeypatch):
    """Two small, same-country-name-colliding domestic leagues (mirrors
    the real England/Belarus "Arsenal" collision) plus one league with an
    alias-only match case (mirrors "Olympiacos"), all in a temp ratings/
    dir so this test never touches real data on disk."""
    ratings_dir = tmp_path / "ratings"
    ratings_dir.mkdir()

    (ratings_dir / "100.csv").write_text(
        "team,alias,opta_rating\nArsenal,,100.0\nChelsea,,90.0\n", encoding="utf-8",
    )
    (ratings_dir / "200.csv").write_text(
        "team,alias,opta_rating\nArsenal,Arsenal Minsk,60.0\n", encoding="utf-8",
    )
    (ratings_dir / "300.csv").write_text(
        "team,alias,opta_rating\nOlympiakos Piraeus,Olympiacos,85.0\n", encoding="utf-8",
    )

    leagues = {
        "England": {"id": 1, "tsdb_id": 100, "country": "England"},
        "Belarus": {"id": 2, "tsdb_id": 200, "country": "Belarus"},
        "Greece": {"id": 3, "tsdb_id": 300, "country": "Greece"},
    }
    monkeypatch.setattr(coc, "LEAGUES", leagues)
    monkeypatch.setattr(coc, "LEAGUES_TIER2", {})
    monkeypatch.setattr(coc, "COUNTRY_NAME_FIXUP", {})
    monkeypatch.chdir(tmp_path)
    return leagues


def test_resolve_field_league_ids_avoids_cross_country_name_collision(synthetic_leagues):
    field = [
        {"team": "Arsenal", "country": "England"},
        {"team": "Chelsea", "country": "England"},
    ]
    result = coc._resolve_field_league_ids(field)
    assert result["Arsenal"] == "100"
    assert result["Chelsea"] == "100"


def test_resolve_field_league_ids_matches_alias_not_just_team_column(synthetic_leagues):
    field = [{"team": "Olympiacos", "country": "Greece"}]
    result = coc._resolve_field_league_ids(field)
    assert result["Olympiacos"] == "300"


def test_resolve_field_league_ids_belarus_arsenal_resolves_to_its_own_league(synthetic_leagues):
    """The other side of the collision -- Belarus's own "Arsenal" must
    resolve to ITS league, not England's, when IT'S the one being asked
    about (field's own country disambiguates correctly either way)."""
    field = [{"team": "Arsenal", "country": "Belarus"}]
    result = coc._resolve_field_league_ids(field)
    assert result["Arsenal"] == "200"
