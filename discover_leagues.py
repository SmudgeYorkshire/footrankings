"""
One-time discovery script — run this ONCE with your API key to find the
correct api-football.com league IDs for every UEFA member nation's top division.

Usage:
    python discover_leagues.py YOUR_API_KEY

Output: prints a ready-to-paste LEAGUES dict block for config.py
"""

import sys
import json
import time
import requests

# ── All 54 UEFA member nations (+ season type) ─────────────────────────────
# season_type "winter" = season spans two years (Aug-May)
# season_type "summer" = season runs within one year  (Apr-Nov)

UEFA_COUNTRIES = [
    # Already confirmed in config – included here so the script validates them too
    ("Albania",            "winter", "🇦🇱"),
    ("Andorra",            "winter", "🇦🇩"),
    ("Armenia",            "winter", "🇦🇲"),
    ("Austria",            "winter", "🇦🇹"),
    ("Azerbaijan",         "winter", "🇦🇿"),
    ("Belarus",            "winter", "🇧🇾"),
    ("Belgium",            "winter", "🇧🇪"),
    ("Bosnia",             "winter", "🇧🇦"),  # api-football uses "Bosnia"
    ("Bulgaria",           "winter", "🇧🇬"),
    ("Croatia",            "winter", "🇭🇷"),
    ("Cyprus",             "winter", "🇨🇾"),
    ("Czech-Republic",     "winter", "🇨🇿"),
    ("Denmark",            "winter", "🇩🇰"),
    ("England",            "winter", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    ("Estonia",            "summer", "🇪🇪"),
    ("Faroe-Islands",      "summer", "🇫🇴"),
    ("Finland",            "summer", "🇫🇮"),
    ("France",             "winter", "🇫🇷"),
    ("Georgia",            "winter", "🇬🇪"),
    ("Germany",            "winter", "🇩🇪"),
    ("Gibraltar",          "winter", "🇬🇮"),
    ("Greece",             "winter", "🇬🇷"),
    ("Hungary",            "winter", "🇭🇺"),
    ("Iceland",            "summer", "🇮🇸"),
    ("Ireland",            "summer", "🇮🇪"),
    ("Israel",             "winter", "🇮🇱"),
    ("Italy",              "winter", "🇮🇹"),
    ("Kazakhstan",         "summer", "🇰🇿"),
    ("Kosovo",             "winter", "🇽🇰"),
    ("Latvia",             "summer", "🇱🇻"),
    ("Liechtenstein",      "winter", "🇱🇮"),  # no domestic league; UEFA Cup only
    ("Lithuania",          "summer", "🇱🇹"),
    ("Luxembourg",         "winter", "🇱🇺"),
    ("Malta",              "winter", "🇲🇹"),
    ("Moldova",            "winter", "🇲🇩"),
    ("Montenegro",         "winter", "🇲🇪"),
    ("Netherlands",        "winter", "🇳🇱"),
    ("North-Macedonia",    "winter", "🇲🇰"),
    ("Northern-Ireland",   "winter", "🇬🇧"),
    ("Norway",             "summer", "🇳🇴"),
    ("Poland",             "winter", "🇵🇱"),
    ("Portugal",           "winter", "🇵🇹"),
    ("Romania",            "winter", "🇷🇴"),
    ("Russia",             "winter", "🇷🇺"),
    ("San-Marino",         "winter", "🇸🇲"),
    ("Scotland",           "winter", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    ("Serbia",             "winter", "🇷🇸"),
    ("Slovakia",           "winter", "🇸🇰"),
    ("Slovenia",           "winter", "🇸🇮"),
    ("Spain",              "winter", "🇪🇸"),
    ("Sweden",             "summer", "🇸🇪"),
    ("Switzerland",        "winter", "🇨🇭"),
    ("Turkey",             "winter", "🇹🇷"),
    ("Ukraine",            "winter", "🇺🇦"),
    ("Wales",              "winter", "🏴󠁧󠁢󠁷󠁬󠁳󠁿"),
]

# Known/expected top-division league name keywords (first match wins)
# Tuples of (country, keyword_hint) — lower-case substring of league name
TOP_DIVISION_HINTS = {
    "Albania":          "superliga",
    "Andorra":          "divisió",
    "Armenia":          "premier",
    "Austria":          "bundesliga",
    "Azerbaijan":       "premyer",
    "Belarus":          "premier",
    "Belgium":          "pro league",
    "Bosnia":           "premijer",
    "Bulgaria":         "first professional",
    "Croatia":          "first football league",
    "Cyprus":           "1. division",
    "Czech-Republic":   "liga",
    "Denmark":          "superliga",
    "England":          "premier league",
    "Estonia":          "meistriliiga",
    "Faroe-Islands":    "meistaradeildin",
    "Finland":          "veikkausliiga",
    "France":           "ligue 1",
    "Georgia":          "erovnuli",
    "Germany":          "bundesliga",
    "Gibraltar":        "premier division",
    "Greece":           "super league",
    "Hungary":          "nb i",
    "Iceland":          "úrvalsdeild",
    "Ireland":          "premier division",
    "Israel":           "premier league",
    "Italy":            "serie a",
    "Kazakhstan":       "premier",
    "Kosovo":           "superliga",
    "Latvia":           "virsliga",
    "Liechtenstein":    "",           # skip – no domestic league
    "Lithuania":        "a lyga",
    "Luxembourg":       "national division",
    "Malta":            "premier league",
    "Moldova":          "super liga",
    "Montenegro":       "first league",
    "Netherlands":      "eredivisie",
    "North-Macedonia":  "super liga",
    "Northern-Ireland": "premiership",
    "Norway":           "eliteserien",
    "Poland":           "ekstraklasa",
    "Portugal":         "primeira liga",
    "Romania":          "liga i",
    "Russia":           "premier league",
    "San-Marino":       "campionato",
    "Scotland":         "premiership",
    "Serbia":           "super liga",
    "Slovakia":         "super liga",
    "Slovenia":         "snl",
    "Spain":            "la liga",
    "Sweden":           "allsvenskan",
    "Switzerland":      "super league",
    "Turkey":           "süper lig",
    "Ukraine":          "premier league",
    "Wales":            "cymru premier",
}

BASE_URL = "https://v3.football.api-sports.io"


def fetch_leagues(country: str, api_key: str) -> list[dict]:
    headers = {"x-apisports-key": api_key}
    url = f"{BASE_URL}/leagues?country={country}&type=League"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    errors = data.get("errors", {})
    if errors:
        raise RuntimeError(str(errors))
    return data.get("response", [])


def pick_top_division(leagues: list[dict], hint: str) -> dict | None:
    """Return the league whose name best matches the hint keyword."""
    if not hint:
        return None
    for entry in leagues:
        name = entry["league"]["name"].lower()
        if hint in name:
            return entry
    # Fallback: return first league alphabetically by division if hint not found
    if leagues:
        return min(leagues, key=lambda e: e["league"]["name"])
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python discover_leagues.py YOUR_API_KEY")
        sys.exit(1)

    api_key = sys.argv[1]
    results = []
    skipped = []

    print(f"Querying api-football.com for {len(UEFA_COUNTRIES)} UEFA nations...\n")

    for country, season_type, flag in UEFA_COUNTRIES:
        hint = TOP_DIVISION_HINTS.get(country, "")

        # Liechtenstein has no domestic league
        if country == "Liechtenstein":
            skipped.append(f"  {flag} Liechtenstein — no domestic league (skip)")
            continue

        try:
            leagues = fetch_leagues(country, api_key)
            chosen = pick_top_division(leagues, hint)
            if chosen:
                league_id = chosen["league"]["id"]
                league_name = chosen["league"]["name"]
                display = country.replace("-", " ")
                results.append((display, flag, league_id, season_type, league_name))
                print(f"  {flag} {display:30s} → [{league_id:4d}] {league_name}")
            else:
                print(f"  {flag} {country:30s} → NOT FOUND (hint: '{hint}')")
        except Exception as e:
            print(f"  ❌ {country}: {e}")

        time.sleep(0.4)   # stay well within 30 req/min free rate limit

    # ── Print ready-to-paste config block ──────────────────────────────────
    print("\n\n# ── Paste this into config.py LEAGUES dict ──────────────────────")
    for display, flag, lid, stype, league_name in results:
        safe_name = display.title().replace("  ", " ")
        print(f'    "{safe_name} {league_name}": {{')
        print(f'        "id": {lid}, "country": "{display}", "flag": "{flag}",')
        print(f'        "season_type": "{stype}",')
        print(f'    }},')

    if skipped:
        print("\n# Skipped:")
        for s in skipped:
            print(s)

    # Also dump to a JSON file for reference
    out = {
        r[0]: {"id": r[2], "season_type": r[3], "league_name": r[4], "flag": r[1]}
        for r in results
    }
    with open("discovered_leagues.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("\nFull results saved to discovered_leagues.json")


if __name__ == "__main__":
    main()
