"""
Tests for update_ratings_from_opta.py's name normalization and the
ambiguous-name disambiguation logic -- the part most at risk of silently
assigning one club's Opta rating to a different, same-named club.
"""

from update_ratings_from_opta import _normalize, _pick_rating


def test_normalize_strips_diacritics():
    assert _normalize("Bayern München") == _normalize("Bayern Munchen")


def test_normalize_strips_club_suffix():
    assert _normalize("Ajax FC") == _normalize("Ajax")


def test_normalize_is_case_insensitive():
    assert _normalize("REAL MADRID") == _normalize("real madrid")


def test_pick_rating_single_candidate_is_unambiguous():
    rating, disambiguated = _pick_rating([100.0], old_rating=90.0)
    assert rating == 100.0
    assert disambiguated is False


def test_pick_rating_picks_closest_to_prior_rating():
    """Regression case: 'Arsenal' exists 4x globally (100.0, 64.6, 62.3,
    51.8) -- our tracked English Arsenal's prior rating (~95) must
    resolve to the 100.0 entry, not one of the unrelated homonym clubs."""
    rating, disambiguated = _pick_rating([100.0, 64.6, 62.3, 51.8], old_rating=95.0)
    assert rating == 100.0
    assert disambiguated is True


def test_pick_rating_refuses_when_no_prior_rating():
    rating, disambiguated = _pick_rating([100.0, 64.6], old_rating=None)
    assert rating is None
    assert disambiguated is False


def test_pick_rating_refuses_when_candidates_are_too_close():
    """Two candidates within 5 points of the prior rating and each other
    is genuinely ambiguous -- must not guess."""
    rating, disambiguated = _pick_rating([81.0, 79.0], old_rating=80.0)
    assert rating is None
