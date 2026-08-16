"""
Static data-integrity checks across config.py, club_coefficients.py,
entrants_2026_27.py and flags.py. These catch the class of bug this
review pass found repeatedly: duplicate dict keys silently overwriting
each other, and country-name spelling mismatches between files that
should agree, which otherwise only surface as a wrong number on a live
page with no exception raised.
"""

import ast
from pathlib import Path

from config import LEAGUES
from coefficients_baseline import COUNTRY_NAME_FIXUP
from flags import FLAG_CODES, flag_url
import club_coefficients as cc


def _literal_dict_keys_from_source(file_path: str, dict_name: str) -> list:
    """Parse a module-level `dict_name = {...}` literal and return every
    key exactly as written, duplicates included -- unlike loading the
    actual dict (which silently keeps only the last value), this lets a
    test assert there were no duplicates in the source at all."""
    src = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == dict_name for t in node.targets
        ):
            return [ast.literal_eval(k) for k in node.value.keys]
        # Annotated module-level dicts (e.g. `FOO: dict[str, float] = {...}`)
        # parse as AnnAssign, not Assign.
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == dict_name:
            return [ast.literal_eval(k) for k in node.value.keys]
    raise AssertionError(f"{dict_name} not found in {file_path}")


def test_club_coefficients_no_duplicate_keys():
    keys = _literal_dict_keys_from_source("club_coefficients.py", "CLUB_COEFFICIENTS")
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate CLUB_COEFFICIENTS keys (last one silently wins): {dupes}"


def test_club_aliases_no_duplicate_keys():
    keys = _literal_dict_keys_from_source("club_coefficients.py", "CLUB_ALIASES")
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate CLUB_ALIASES keys (last one silently wins): {dupes}"


def test_nation_coefficients_no_duplicate_keys():
    keys = _literal_dict_keys_from_source("club_coefficients.py", "NATION_COEFFICIENTS")
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate NATION_COEFFICIENTS keys: {dupes}"


def test_league_ids_are_unique():
    ids = [cfg["id"] for cfg in LEAGUES.values()]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate LEAGUES 'id' values: {dupes}"


def test_league_tsdb_ids_are_unique():
    """tsdb_id doubles as the ratings/{id}.csv filename -- a collision
    means two leagues would silently share one ratings file."""
    tsdb_ids = [cfg.get("tsdb_id", cfg["id"]) for cfg in LEAGUES.values()]
    dupes = {i for i in tsdb_ids if tsdb_ids.count(i) > 1}
    assert not dupes, f"duplicate LEAGUES 'tsdb_id' values: {dupes}"


def test_every_league_country_resolves_to_a_flag():
    """Every domestic league's country (after applying the same fixup
    Coefficients/Live already use) must resolve to a real flagcdn URL --
    regression test for the 6 leagues that silently showed no flag."""
    missing = []
    for name, cfg in LEAGUES.items():
        country = COUNTRY_NAME_FIXUP.get(cfg.get("country", ""), cfg.get("country", ""))
        if not flag_url(country):
            missing.append((name, cfg.get("country")))
    assert not missing, f"leagues with no resolvable flag: {missing}"


def test_turkiye_and_turkey_have_matching_nation_coefficient():
    assert cc.NATION_COEFFICIENTS.get("Türkiye") == cc.NATION_COEFFICIENTS.get("Turkey")
    assert cc.NATION_COEFFICIENTS.get("Türkiye") is not None


def test_entrants_file_does_not_use_stale_country_spellings():
    """entrants_2026_27.py should use this site's canonical spellings
    ("Türkiye", "Czechia") consistently -- a past inconsistency there
    silently zeroed a nation's coefficient lookup."""
    src = Path("entrants_2026_27.py").read_text(encoding="utf-8")
    assert '"country": "Turkey"' not in src
    assert '"country": "Czech Rep."' not in src


def test_flag_codes_have_no_duplicate_keys():
    keys = _literal_dict_keys_from_source("flags.py", "FLAG_CODES")
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate FLAG_CODES keys: {dupes}"


def test_flag_url_returns_empty_for_unknown_country():
    assert flag_url("Not A Real Country") == ""


def test_flag_url_returns_a_flagcdn_url_for_known_country():
    assert flag_url("England").startswith("https://flagcdn.com/")
