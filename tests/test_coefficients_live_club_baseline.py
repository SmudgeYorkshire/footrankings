"""
Tests for coefficients_live._canonical_club_name -- the resolution chain
club_coefficients_baseline.py's own module docstring describes (exact
match, then CLUB_BASELINE_ALIASES/CLUB_ALIASES, then case-insensitive,
then a normalized/token-sorted match), plus the dedup-by-canonical-name
merge in predicted_club_coefficients() that fixes a real bug caught live
2026-11-09: "Bayern Munich" and "Bayern München" (two different spellings
of the same real club, pulled from two different underlying data sources)
were silently split across two separate rows, each showing only part of
that club's true points.
"""

import pandas as pd

import coefficients_live as cl


def test_exact_match_resolves_to_itself():
    assert cl._canonical_club_name("Bayern München") == "Bayern München"


def test_club_baseline_alias_resolves():
    # "Bayern Munich" isn't a CLUB_BASELINE key itself -- only reachable
    # via CLUB_BASELINE_ALIASES.
    assert cl._canonical_club_name("Bayern Munich") == "Bayern München"


def test_club_coefficients_alias_resolves():
    # club_coefficients.CLUB_ALIASES also feeds this resolution chain.
    assert cl._canonical_club_name("Inter") == "Internazionale"


def test_case_insensitive_match_resolves():
    assert cl._canonical_club_name("bayern münchen") == "Bayern München"


def test_normalized_match_resolves_diacritics_and_suffix_variants():
    # "Porto" isn't a CLUB_BASELINE key ("FC Porto" is) and isn't covered
    # by either alias dict -- only the normalized/suffix-stripped fallback
    # catches this one.
    assert cl._canonical_club_name("FC Porto") == "FC Porto"


def test_unresolvable_name_falls_back_to_itself():
    # A club genuinely new to Europe this season has no prior baseline
    # entry to resolve against -- must return the input unchanged, not
    # raise or silently pick an unrelated club.
    assert cl._canonical_club_name("Some Brand New FC") == "Some Brand New FC"


def test_predicted_club_coefficients_merges_duplicate_spellings(monkeypatch):
    """Regression test for the real bug caught live 2026-11-09: current_
    points and the Monte Carlo simulation pull team names from different
    underlying sources, so the same real club's points could land under
    two different spellings and silently split across two rows instead of
    summing into one."""
    monkeypatch.setattr(
        cl, "predicted_country_ranking",
        lambda: (
            pd.DataFrame(), [],
            [{"Bayern Munich": _FakeArr(10.0)}],
            {"Bayern Munich": "Germany", "Bayern München": "Germany"},
        ),
    )
    monkeypatch.setattr(
        cl, "_compute_live_club_points",
        lambda key: {"Bayern München": 6.0, "Bayern Munich": 6.0},
    )

    cl.predicted_club_coefficients.clear()
    table, _warnings = cl.predicted_club_coefficients()
    bayern_rows = table[table["club"] == "Bayern München"]
    assert len(bayern_rows) == 1
    row = bayern_rows.iloc[0]
    assert row["current_points"] == 12.0
    assert row["predicted_additional"] == 10.0


class _FakeArr:
    """Stands in for the numpy array predicted_country_ranking's own
    simulated_club_points values normally are -- only .mean() is used."""
    def __init__(self, value: float):
        self._value = value

    def mean(self) -> float:
        return self._value
