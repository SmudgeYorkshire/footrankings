"""
Regression tests for qualifying_projection.py's raw-API-name resolution --
specifically the 2026-11-04 bug where "Olympiakos Piraeus" (API-Football's
fixtures-endpoint spelling) silently failed to resolve against this site's
canonical League Phase field name "Olympiacos", causing every one of that
club's real League Stage results to be dropped from the simulation (it was
re-simulated from scratch instead of having its actual record locked in --
confirmed live: Top-24 chance read 88.4% instead of the correct ~100%).
"""

import qualifying_projection as qp


def test_resolve_to_team_exact_match():
    assert qp.resolve_to_team("Benfica", {"Benfica", "Porto"}) == "Benfica"


def test_resolve_to_team_no_match_returns_none():
    assert qp.resolve_to_team("Totally Unknown FC", {"Benfica", "Porto"}) is None


def test_olympiacos_raw_name_override_present():
    """The specific, confirmed-live collision this bug was found from --
    see _RAW_NAME_OVERRIDES' own docstring for the full story."""
    assert qp._RAW_NAME_OVERRIDES.get("Olympiakos Piraeus") == "Olympiacos"


def test_resolve_to_team_still_fails_without_the_override():
    """Documents WHY the override is needed rather than relying on
    resolve_to_team's existing fuzzy tiers -- the c/k spelling difference
    isn't a prefix, suffix, or substring relationship, so the plain
    fuzzy-match path alone can't bridge it."""
    assert qp.resolve_to_team("Olympiakos Piraeus", {"Olympiacos"}) is None


def test_olympiacos_override_resolves_correctly():
    raw = "Olympiakos Piraeus"
    field_set = {"Olympiacos", "Benfica"}
    fixed = qp._RAW_NAME_OVERRIDES.get(raw, raw)
    assert qp.resolve_to_team(fixed, field_set) == "Olympiacos"


def test_real_league_phase_results_applies_the_override(monkeypatch):
    """End-to-end: a raw API-Football fixture using the "Olympiakos
    Piraeus" spelling must land in the results dict keyed by this site's
    own canonical "Olympiacos" -- not silently dropped, and with no
    unresolved names reported."""
    played = [
        {
            "strRound": "League Stage - 4", "strStatus": "FT",
            "strHomeTeam": "Rennes", "strAwayTeam": "Olympiakos Piraeus",
            "intHomeScore": "0", "intAwayScore": "0",
        },
    ]
    monkeypatch.setattr(qp, "_fetch_comp_fixtures", lambda comp, key: (played, []))
    results, unresolved = qp.real_league_phase_results("Europa League", "fake-key", ["Rennes", "Olympiacos"])
    assert results == {("Rennes", "Olympiacos"): (0, 0)}
    assert unresolved == []


def test_real_league_phase_results_reports_unresolved_names(monkeypatch):
    """A finished fixture whose raw name genuinely can't be matched to
    anyone in the field must be both dropped from results AND reported in
    unresolved_raw_names -- this is the warning mechanism added after the
    Olympiacos bug went unnoticed for a while; it must never silently
    swallow a real naming gap again."""
    played = [
        {
            "strRound": "League Stage - 1", "strStatus": "FT",
            "strHomeTeam": "Rennes", "strAwayTeam": "Totally Unknown FC",
            "intHomeScore": "2", "intAwayScore": "1",
        },
    ]
    monkeypatch.setattr(qp, "_fetch_comp_fixtures", lambda comp, key: (played, []))
    results, unresolved = qp.real_league_phase_results("Europa League", "fake-key", ["Rennes", "Olympiacos"])
    assert results == {}
    assert unresolved == ["Totally Unknown FC"]
