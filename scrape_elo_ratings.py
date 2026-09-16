"""
Fetches current national-team Elo ratings from eloratings.net for the 54
UEFA Nations League nations, used by nations_league.py.

eloratings.net's own front end is a JS-rendered grid, but it's fed by
small static TSV files the browser fetches directly -- World.tsv (one row
per national team: local rank, global rank, team code, current rating,
...) and en.teams.tsv (team code -> full English name). Reading those
same two files directly is far simpler than driving a headless browser
(as scrape_opta_power_rankings.py has to for theanalyst.com's session-
gated widget) and is exactly the data the page itself displays.

Writes ratings/nations_league_elo.csv with columns [team, alias,
opta_rating] -- reusing the `opta_rating` column name (these are Elo
points, not Opta's 0-100 scale) purely so nations_league_simulator.py can
feed the file straight into simulator.py's existing
_opta_to_attack_defense()/_build_rat_lookup() without any changes there;
the relative (rating / group mean) transform those use is scale-agnostic.
"""

import csv
import sys

import requests

from nations_league_data import ALL_NL_TEAMS

TEAMS_URL = "https://eloratings.net/en.teams.tsv"
WORLD_URL = "https://eloratings.net/World.tsv"
OUT_PATH = "ratings/nations_league_elo.csv"

# eloratings.net's own team names, only where they differ from this site's.
_NAME_ALIASES = {
    "Republic of Ireland": "Ireland",
}


def _load_code_to_name() -> dict[str, str]:
    resp = requests.get(TEAMS_URL, timeout=30)
    resp.raise_for_status()
    code_to_name = {}
    for line in resp.text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and not parts[0].endswith("_loc"):
            code_to_name[parts[0]] = parts[1]
    return code_to_name


def _load_code_to_rating() -> dict[str, float]:
    resp = requests.get(WORLD_URL, timeout=30)
    resp.raise_for_status()
    code_to_rating = {}
    for line in resp.text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            try:
                code_to_rating[parts[2]] = float(parts[3])
            except ValueError:
                continue
    return code_to_rating


def fetch_nl_elo_ratings() -> dict[str, float]:
    """{our team name: current Elo rating} for every team in ALL_NL_TEAMS."""
    code_to_name = _load_code_to_name()
    name_to_code = {v: k for k, v in code_to_name.items()}
    code_to_rating = _load_code_to_rating()

    ratings: dict[str, float] = {}
    missing = []
    for team in ALL_NL_TEAMS:
        lookup_name = _NAME_ALIASES.get(team, team)
        code = name_to_code.get(lookup_name)
        rating = code_to_rating.get(code) if code else None
        if rating is None:
            missing.append(team)
        else:
            ratings[team] = rating
    if missing:
        print(f"WARNING: no Elo rating found for: {', '.join(missing)}", file=sys.stderr)
    return ratings


def main() -> None:
    ratings = fetch_nl_elo_ratings()
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["team", "alias", "opta_rating"])
        for team in ALL_NL_TEAMS:
            if team in ratings:
                writer.writerow([team, "", ratings[team]])
    print(f"Wrote {len(ratings)}/{len(ALL_NL_TEAMS)} team ratings to {OUT_PATH}")


if __name__ == "__main__":
    main()
