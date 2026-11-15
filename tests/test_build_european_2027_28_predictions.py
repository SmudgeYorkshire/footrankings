"""
Tests for build_european_2027_28_predictions.py's "UCL Titleholder bye"
cascade -- the dynamically-resolved permutation that promotes whichever
Champions-Path club has the highest coefficient in each of CL-PO, CL-Q2
and CL-Q1 up one level (PO -> League Phase direct, QR2 -> PO, two QR1
clubs -> QR2). get_coeff_2027 is monkeypatched (a thin, pure lookup in
the real code) so these tests exercise only the SELECTION logic, with no
live API/network dependency.
"""

import pandas as pd
import pytest

import build_european_2027_28_predictions as b


def _synthetic_access_list():
    """A small, self-contained Champions League Champions-Path pool: 2
    countries in CL-PO, 2 in CL-Q2, 3 in CL-Q1 (so the QR1 top-2 pick has
    a real 3rd-place club left behind to prove it's excluded) -- enough to
    exercise every branch of the cascade without the full ~40-country
    real access list."""
    def entry(country, league, label):
        return {"country": country, "league": league, "code": "CH", "path": "Champions Path",
                "label": label, "route": "League champion"}

    return {
        "Champions League": [
            entry("Norway", "Norwegian Eliteserien", "CL-PO"),
            entry("Greece", "Greek Super League 1", "CL-PO"),
            entry("Hungary", "Hungarian NB I", "CL-Q2"),
            entry("Ukraine", "Ukrainian Premier League", "CL-Q2"),
            entry("Serbia", "Serbian Super Liga", "CL-Q1"),
            entry("Ireland", "Irish Premier Division", "CL-Q1"),
            entry("Romania", "Romanian Liga I", "CL-Q1"),
        ],
    }


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "apply_permutations", lambda active=None: _synthetic_access_list())
    coeffs = {
        "Bodo/Glimt": 61.5, "Panathinaikos": 39.75,
        "Ferencvarosi TC": 63.25, "Shakhtar Donetsk": 59.25,
        "FK Crvena Zvezda": 37.5, "Shamrock Rovers": 20.38, "Universitatea Craiova": 18.5,
    }
    monkeypatch.setattr(b, "get_coeff_2027", lambda club, country: coeffs.get(club, 1.0))
    out_path = tmp_path / "titleholder_bye.csv"
    monkeypatch.setattr(b, "TITLEHOLDER_BYE_OUT", str(out_path))
    return out_path


def _standings(team: str) -> list[dict]:
    return [{"strTeam": team, "intRank": 1}]


def test_highest_po_club_promotes_to_league_phase(patched):
    standings_by_league = {
        "Norwegian Eliteserien": _standings("Bodo/Glimt"),
        "Greek Super League 1": _standings("Panathinaikos"),
        "Hungarian NB I": _standings("Ferencvarosi TC"),
        "Ukrainian Premier League": _standings("Shakhtar Donetsk"),
        "Serbian Super Liga": _standings("FK Crvena Zvezda"),
        "Irish Premier Division": _standings("Shamrock Rovers"),
        "Romanian Liga I": _standings("Universitatea Craiova"),
    }
    b._build_titleholder_bye(standings_by_league)
    df = pd.read_csv(patched)
    po_move = df[df["old_label"] == "CL-PO"].iloc[0]
    assert po_move["country"] == "Norway"
    assert po_move["club"] == "Bodo/Glimt"
    assert po_move["new_label"] == "CL-LS"
    # Greece (lower PO coefficient) must NOT also move.
    assert "Greece" not in set(df["country"])


def test_highest_qr2_club_promotes_to_po(patched):
    standings_by_league = {
        "Norwegian Eliteserien": _standings("Bodo/Glimt"),
        "Greek Super League 1": _standings("Panathinaikos"),
        "Hungarian NB I": _standings("Ferencvarosi TC"),
        "Ukrainian Premier League": _standings("Shakhtar Donetsk"),
        "Serbian Super Liga": _standings("FK Crvena Zvezda"),
        "Irish Premier Division": _standings("Shamrock Rovers"),
        "Romanian Liga I": _standings("Universitatea Craiova"),
    }
    b._build_titleholder_bye(standings_by_league)
    df = pd.read_csv(patched)
    qr2_move = df[df["old_label"] == "CL-Q2"].iloc[0]
    assert qr2_move["country"] == "Hungary"
    assert qr2_move["club"] == "Ferencvarosi TC"
    assert qr2_move["new_label"] == "CL-PO"
    assert "Ukraine" not in set(df["country"])


def test_top_two_qr1_clubs_promote_to_qr2_as_a_pair(patched):
    standings_by_league = {
        "Norwegian Eliteserien": _standings("Bodo/Glimt"),
        "Greek Super League 1": _standings("Panathinaikos"),
        "Hungarian NB I": _standings("Ferencvarosi TC"),
        "Ukrainian Premier League": _standings("Shakhtar Donetsk"),
        "Serbian Super Liga": _standings("FK Crvena Zvezda"),
        "Irish Premier Division": _standings("Shamrock Rovers"),
        "Romanian Liga I": _standings("Universitatea Craiova"),
    }
    b._build_titleholder_bye(standings_by_league)
    df = pd.read_csv(patched)
    qr1_moves = df[df["old_label"] == "CL-Q1"]
    assert set(qr1_moves["country"]) == {"Serbia", "Ireland"}
    assert (qr1_moves["new_label"] == "CL-Q2").all()
    # Romania has the lowest QR1 coefficient of the three -- stays put.
    assert "Romania" not in set(df["country"])


def test_russia_excluded_even_if_present_in_pool(patched, monkeypatch):
    access_list = _synthetic_access_list()
    access_list["Champions League"].append(
        {"country": "Russia", "league": "Russian Football Premier League", "code": "CH",
         "path": "Champions Path", "label": "CL-PO", "route": "League champion"}
    )
    monkeypatch.setattr(b, "apply_permutations", lambda active=None: access_list)
    monkeypatch.setattr(b, "get_coeff_2027", lambda club, country: 9999.0 if country == "Russia" else 1.0)
    standings_by_league = {
        "Norwegian Eliteserien": _standings("Bodo/Glimt"),
        "Greek Super League 1": _standings("Panathinaikos"),
        "Hungarian NB I": _standings("Ferencvarosi TC"),
        "Ukrainian Premier League": _standings("Shakhtar Donetsk"),
        "Serbian Super Liga": _standings("FK Crvena Zvezda"),
        "Irish Premier Division": _standings("Shamrock Rovers"),
        "Romanian Liga I": _standings("Universitatea Craiova"),
        "Russian Football Premier League": _standings("CSKA Moscow"),
    }
    b._build_titleholder_bye(standings_by_league)
    df = pd.read_csv(patched)
    assert "Russia" not in set(df["country"])


def test_missing_standings_for_a_country_is_skipped_not_fatal(patched):
    # Serbia's own league standings never resolved (live fetch failed) --
    # must not crash, and Serbia must not appear as a mover.
    standings_by_league = {
        "Norwegian Eliteserien": _standings("Bodo/Glimt"),
        "Greek Super League 1": _standings("Panathinaikos"),
        "Hungarian NB I": _standings("Ferencvarosi TC"),
        "Ukrainian Premier League": _standings("Shakhtar Donetsk"),
        "Irish Premier Division": _standings("Shamrock Rovers"),
        "Romanian Liga I": _standings("Universitatea Craiova"),
    }
    b._build_titleholder_bye(standings_by_league)
    df = pd.read_csv(patched)
    assert "Serbia" not in set(df["country"])
