"""
Coverage for cross_league_playoff_win_rates / apply_cross_league_playoff_
correction -- fixes simulate_league_outcomes' own internal play-off
resolution only ever seeing one league's roster at a time, which paired
a pool member against its own DOMESTIC rivals instead of its real
cross-league opponent (confirmed on real data: a strong League C team
was shown winning its promotion play-off ~84% of the time against weak
fellow League C sides, instead of the ~50% its genuinely tougher League
B opponents actually give it).
"""

import pandas as pd
import pytest

from nations_league_simulator import cross_league_playoff_win_rates, apply_cross_league_playoff_correction


def _ratings(pairs: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"team": list(pairs.keys()), "alias": "", "opta_rating": list(pairs.values())})


def test_strong_team_in_weak_pool_does_not_dominate_a_stronger_cross_league_pool():
    # Alpha is the clear best of a weak pool; Bravo/Charlie/Delta/Echo are
    # a much stronger pool on the other side.
    higher = pd.Series({"Alpha": 0.5, "Weak2": 0.3, "Weak3": 0.15, "Weak4": 0.05})
    lower = pd.Series({"Bravo": 0.3, "Charlie": 0.3, "Delta": 0.25, "Echo": 0.15})
    ratings = _ratings({
        "Alpha": 1700, "Weak2": 1500, "Weak3": 1450, "Weak4": 1400,
        "Bravo": 1750, "Charlie": 1730, "Delta": 1710, "Echo": 1690,
    })
    rates = cross_league_playoff_win_rates(higher, lower, ratings)
    # Alpha should NOT be a heavy favourite here -- its real opponents
    # (Bravo/Charlie/Delta/Echo) are all comparable or stronger, not the
    # weak domestic pool it was previously (wrongly) tested against.
    assert rates["Alpha"] < 0.6


def test_pool_entry_chance_unchanged_only_split_changes():
    win_label, lose_label = "Won Promotion Play-offs", "Lost Promotion Play-offs"
    win_label2, lose_label2 = "Promoted in Play-offs", "Relegated in Play-offs"
    lower_probs = pd.DataFrame(
        {win_label: [0.6, 0.1], lose_label: [0.1, 0.2]}, index=["Alpha", "Weak2"],
    )
    higher_probs = pd.DataFrame(
        {win_label2: [0.4, 0.1], lose_label2: [0.2, 0.1]}, index=["Bravo", "Charlie"],
    )
    ratings = _ratings({"Alpha": 1700, "Weak2": 1500, "Bravo": 1750, "Charlie": 1600})
    before_pool = lower_probs.loc["Alpha", win_label] + lower_probs.loc["Alpha", lose_label]

    apply_cross_league_playoff_correction(
        higher_probs, "Relegation Play-offs", lower_probs, "Promotion Play-offs", ratings,
    )

    after_pool = lower_probs.loc["Alpha", win_label] + lower_probs.loc["Alpha", lose_label]
    assert after_pool == pytest.approx(before_pool, abs=1e-9)


def test_empty_series_returns_empty_dict():
    assert cross_league_playoff_win_rates(pd.Series(dtype=float), pd.Series({"A": 0.5}), _ratings({"A": 1700})) == {}
