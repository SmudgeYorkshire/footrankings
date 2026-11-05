"""
Regression test for build_club_power_rankings.py's Combined Elo formula --
found and fixed 2026-11-04 while sweeping N_FULL_CONFIDENCE against
club_combined_rating_validation.py's held-out benchmark: the original
formula ("adjusted_rating + odds_delta * confidence") double-counted the
live odds nudge at high confidence, since adjusted_rating already
includes it and odds_delta is computed against the UNADJUSTED raw rating.
"""

import pandas as pd
import pytest

from build_club_power_rankings import _combined_rating, N_FULL_CONFIDENCE
from club_odds_ratings import blend_with_live_rating


def test_combined_rating_zero_confidence_equals_adjusted_rating():
    out = _combined_rating(
        adjusted_rating=pd.Series([92.5]), league_raw_rating=pd.Series([90.0]),
        odds_delta=pd.Series([5.0]), confidence=pd.Series([0.0]),
    )
    assert out.iloc[0] == 92.5


def test_combined_rating_full_confidence_equals_pure_odds_rating():
    """The specific case this bug was found from: live=92.5 (raw 90 +
    nudge 2.5), odds=95.0 (raw 90 + delta 5.0) -- at full confidence the
    combined rating must equal 95.0 exactly, not 97.5 (nudge + odds)."""
    out = _combined_rating(
        adjusted_rating=pd.Series([92.5]), league_raw_rating=pd.Series([90.0]),
        odds_delta=pd.Series([5.0]), confidence=pd.Series([1.0]),
    )
    assert out.iloc[0] == 95.0


def test_combined_rating_interpolates_between_the_two():
    out = _combined_rating(
        adjusted_rating=pd.Series([100.0]), league_raw_rating=pd.Series([90.0]),
        odds_delta=pd.Series([10.0]), confidence=pd.Series([0.5]),
    )
    # adjusted=100, odds_equivalent=90+10=100 -- same here, so use a case
    # where they differ:
    out2 = _combined_rating(
        adjusted_rating=pd.Series([100.0]), league_raw_rating=pd.Series([90.0]),
        odds_delta=pd.Series([20.0]), confidence=pd.Series([0.5]),
    )
    assert out2.iloc[0] == 105.0  # 100*0.5 + 110*0.5
    assert out.iloc[0] == 100.0


def test_combined_rating_handles_no_odds_coverage_without_nan():
    """A club with no odds row at all has odds_delta=NaN; confidence must
    already be 0 for it (guaranteed by the caller), and the result must
    stay the plain adjusted_rating, not NaN."""
    out = _combined_rating(
        adjusted_rating=pd.Series([88.0]), league_raw_rating=pd.Series([85.0]),
        odds_delta=pd.Series([float("nan")]), confidence=pd.Series([0.0]),
    )
    assert out.iloc[0] == 88.0


# ---------------------------------------------------------------------------
# The Club Power Rankings page's "Combined Strength Ranking" column must be
# a live mirror of what blend_with_live_rating() actually feeds every real
# prediction (wired in 2026-11-05) -- not a separate number that merely
# happens to agree. Checked at a PARTIAL confidence level specifically,
# since full/zero confidence collapse both formulas to the same trivial
# endpoint regardless of whether they're truly the same formula.
# ---------------------------------------------------------------------------

def test_combined_rating_matches_blend_with_live_rating_at_partial_confidence():
    adjusted_rating = 92.5     # Opta + today's small daily nudge
    league_raw_rating = 90.0   # this club's raw, pre-nudge Opta rating
    odds_implied_rating = 101.0
    n_updates = N_FULL_CONFIDENCE // 2  # partial confidence, not 0 or full
    confidence = n_updates / N_FULL_CONFIDENCE

    display_value = _combined_rating(
        adjusted_rating=pd.Series([adjusted_rating]),
        league_raw_rating=pd.Series([league_raw_rating]),
        odds_delta=pd.Series([odds_implied_rating - league_raw_rating]),
        confidence=pd.Series([confidence]),
    ).iloc[0]

    state = {("4328", "Test FC"): {
        "rating": odds_implied_rating, "seed": league_raw_rating,
        "n_updates": n_updates, "last_updated": "x",
    }}
    live_value = blend_with_live_rating("4328", "Test FC", adjusted_rating, state)

    assert display_value == pytest.approx(live_value)
