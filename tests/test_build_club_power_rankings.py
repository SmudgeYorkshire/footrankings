"""
Regression test for build_club_power_rankings.py's Combined Elo formula --
found and fixed 2026-11-04 while sweeping N_FULL_CONFIDENCE against
club_combined_rating_validation.py's held-out benchmark: the original
formula ("adjusted_rating + odds_delta * confidence") double-counted the
live odds nudge at high confidence, since adjusted_rating already
includes it and odds_delta is computed against the UNADJUSTED raw rating.
"""

import pandas as pd

from build_club_power_rankings import _combined_rating


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
