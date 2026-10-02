"""
One-time discovery script -- finds the correct api-football.com league IDs
for European countries' SECOND division, adapted from discover_leagues.py
(which does the same thing for first divisions). Hints below were derived
by directly sampling API-Football for ~50 countries, not guessed from
memory -- see the "European Leagues - 2nd Tiers" project plan.

Known exceptions (no hint given, expect "NOT FOUND" and that's correct,
not a bug): Liechtenstein (no domestic league at all, same as the
top-flight LEAGUES dict), San Marino (only one division exists --
"Campionato" -- nothing below it), Gibraltar (single-tier country, only
"Premier Division"), Luxembourg (API-Football tracks only "National
Division" + "Cup" for it, no second tier despite one existing in real
life), Bosnia (pyramid is split into two entity-based regional leagues,
"1st League - RS" and "1st League - FBiH", not one unified national 2nd
tier -- deliberately skipped rather than picking one arbitrarily).

Usage:
    python discover_second_tier_leagues.py
(reads API_FOOTBALL_KEY from .env, same as every other script here)
"""

import json
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

import requests

# (api-football country-query string, season_type, flag) -- country strings
# match discover_leagues.py's UEFA_COUNTRIES exactly, except Macedonia
# (API-Football wants plain "Macedonia", not "North Macedonia" -- confirmed
# by direct query; "North Macedonia"/"North-Macedonia"/"FYR Macedonia" all
# return empty).
COUNTRIES = [
    ("Albania", "winter", "🇦🇱"), ("Armenia", "winter", "🇦🇲"),
    ("Austria", "winter", "🇦🇹"), ("Azerbaijan", "winter", "🇦🇿"),
    ("Belarus", "winter", "🇧🇾"), ("Belgium", "winter", "🇧🇪"),
    ("Bulgaria", "winter", "🇧🇬"), ("Croatia", "winter", "🇭🇷"),
    ("Cyprus", "winter", "🇨🇾"), ("Czech-Republic", "winter", "🇨🇿"),
    ("Denmark", "winter", "🇩🇰"), ("England", "winter", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    ("Estonia", "summer", "🇪🇪"), ("Faroe-Islands", "summer", "🇫🇴"),
    ("Finland", "summer", "🇫🇮"), ("France", "winter", "🇫🇷"),
    ("Georgia", "summer", "🇬🇪"), ("Germany", "winter", "🇩🇪"),
    ("Greece", "winter", "🇬🇷"), ("Hungary", "winter", "🇭🇺"),
    ("Iceland", "summer", "🇮🇸"), ("Ireland", "summer", "🇮🇪"),
    ("Israel", "winter", "🇮🇱"), ("Italy", "winter", "🇮🇹"),
    ("Kazakhstan", "summer", "🇰🇿"), ("Kosovo", "winter", "🇽🇰"),
    ("Latvia", "summer", "🇱🇻"), ("Lithuania", "summer", "🇱🇹"),
    ("Macedonia", "winter", "🇲🇰"), ("Malta", "winter", "🇲🇹"),
    ("Moldova", "winter", "🇲🇩"), ("Montenegro", "winter", "🇲🇪"),
    ("Netherlands", "winter", "🇳🇱"), ("Northern-Ireland", "winter", "🇬🇧"),
    ("Norway", "summer", "🇳🇴"), ("Poland", "winter", "🇵🇱"),
    ("Portugal", "winter", "🇵🇹"), ("Romania", "winter", "🇷🇴"),
    ("Russia", "winter", "🇷🇺"), ("Scotland", "winter", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    ("Serbia", "winter", "🇷🇸"), ("Slovakia", "winter", "🇸🇰"),
    ("Slovenia", "winter", "🇸🇮"), ("Spain", "winter", "🇪🇸"),
    ("Sweden", "summer", "🇸🇪"), ("Switzerland", "winter", "🇨🇭"),
    ("Turkey", "winter", "🇹🇷"), ("Ukraine", "winter", "🇺🇦"),
    ("Wales", "winter", "🏴󠁧󠁢󠁷󠁬󠁳󠁿"),
    # Deliberately no hint -- expect NOT FOUND, see module docstring.
    ("Andorra", "winter", "🇦🇩"), ("Liechtenstein", "winter", "🇱🇮"),
    ("San-Marino", "winter", "🇸🇲"), ("Gibraltar", "winter", "🇬🇮"),
    ("Luxembourg", "winter", "🇱🇺"), ("Bosnia", "winter", "🇧🇦"),
]

SECOND_DIVISION_HINTS: dict[str, str] = {
    "Albania": "1st division", "Armenia": "first league",
    "Austria": "2. liga", "Azerbaijan": "birinci dasta",
    "Belarus": "1. division", "Belgium": "challenger pro league",
    "Bulgaria": "second league", "Croatia": "first nl",
    "Cyprus": "2. division", "Czech-Republic": "fnl",
    "Denmark": "1. division", "England": "championship",
    "Estonia": "esiliiga a", "Faroe-Islands": "1. deild",
    "Finland": "ykk",  # "Ykkönen" -- the ö sits inside the word, so a short prefix avoids it
    "France": "ligue 2",
    "Georgia": "erovnuli liga 2", "Germany": "2. bundesliga",
    "Greece": "football league", "Hungary": "nb ii",
    "Iceland": "1. deild", "Ireland": "first division",
    "Israel": "liga leumit", "Italy": "serie b",
    "Kazakhstan": "1. division", "Kosovo": "liga e pare",
    "Latvia": "1. liga", "Lithuania": "1 lyga",
    "Macedonia": "second league", "Malta": "challenge league",
    "Moldova": "liga 1", "Montenegro": "second league",
    "Netherlands": "eerste divisie", "Northern-Ireland": "championship",
    "Norway": "1. division", "Poland": "i liga",
    "Portugal": "segunda liga", "Romania": "liga ii",
    "Russia": "first league", "Scotland": "championship",
    "Serbia": "prva liga", "Slovakia": "2. liga",
    "Slovenia": "2. snl", "Spain": "segunda divisi",
    "Sweden": "superettan", "Switzerland": "challenge league",
    "Turkey": "1. lig", "Ukraine": "persha liga",
    "Wales": "faw championship",
    # Andorra's actual 2nd tier has an accented char ("2a Divisió") right
    # after where this hint ends -- a prefix substring match avoids needing
    # to get the accent encoding right.
    "Andorra": "2a divisi",
}

BASE_URL = "https://v3.football.api-sports.io"


def fetch_leagues(country: str, api_key: str) -> list[dict]:
    headers = {"x-apisports-key": api_key}
    resp = requests.get(f"{BASE_URL}/leagues", headers=headers,
                         params={"country": country, "type": "League"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    return data.get("response", [])


def pick_division(leagues: list[dict], hint: str) -> dict | None:
    if not hint:
        return None
    for entry in leagues:
        if hint in entry["league"]["name"].lower():
            return entry
    return None


def main() -> None:
    api_key = os.getenv("API_FOOTBALL_KEY", "")
    if not api_key:
        print("No API_FOOTBALL_KEY in .env", file=sys.stderr)
        sys.exit(1)

    results = []
    not_found = []
    print(f"Querying api-football.com for {len(COUNTRIES)} countries' 2nd divisions...\n")

    for country, season_type, flag in COUNTRIES:
        hint = SECOND_DIVISION_HINTS.get(country, "")
        try:
            leagues = fetch_leagues(country, api_key)
            chosen = pick_division(leagues, hint)
            if chosen:
                lid = chosen["league"]["id"]
                lname = chosen["league"]["name"]
                display = country.replace("-", " ")
                results.append((display, flag, lid, season_type, lname))
                print(f"  {flag} {display:20s} -> [{lid:4d}] {lname}")
            else:
                display = country.replace("-", " ")
                not_found.append(display)
                print(f"  {flag} {display:20s} -> NOT FOUND (hint: '{hint}', "
                      f"{len(leagues)} leagues available)")
        except Exception as e:
            print(f"  ERROR {country}: {e}", file=sys.stderr)
        time.sleep(0.4)

    print("\n\n# -- Paste into config.py as LEAGUES_TIER2 (after review) --------------")
    for i, (display, flag, lid, stype, lname) in enumerate(results):
        tsdb_id = 20000 + i
        print(f'    "{display}": {{"id": {lid}, "tsdb_id": {tsdb_id}, "country": "{display}", '
              f'"flag": "{flag}", "season_type": "{stype}"}},  # {lname}')

    print(f"\n# Not found / skipped ({len(not_found)}): {', '.join(not_found)}")

    with open("discovered_second_tier_leagues.json", "w", encoding="utf-8") as f:
        json.dump(
            {r[0]: {"id": r[2], "season_type": r[3], "league_name": r[4], "flag": r[1]} for r in results},
            f, indent=2, ensure_ascii=False,
        )
    print(f"\nFull results saved to discovered_second_tier_leagues.json ({len(results)} found)")


if __name__ == "__main__":
    main()
