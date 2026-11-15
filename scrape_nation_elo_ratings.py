"""
Fetches current national-team Elo ratings from eloratings.net for EVERY
national team it rates (244 teams, confirmed live) -- the global analog of
scrape_elo_ratings.py, which only pulls the 54 UEFA Nations League nations
for nations_league.py's own simulations.

Same two static TSV files scrape_elo_ratings.py already reads (see that
module's own docstring for why reading them directly beats driving a
headless browser): en.teams.tsv (team code -> full English name) and
World.tsv (one row per national team: local rank, global rank, team code,
current rating, ...). This script just doesn't filter World.tsv down to
any one subset -- every team eloratings.net lists comes through.

Writes ratings/nation_elo_global.csv with columns [team, alias,
elo_rating, elo_rank] -- the nation-level analog of
opta_power_rankings.csv (the global CLUB scrape build_club_power_
rankings.py starts from). Does NOT touch ratings/nations_league_elo.csv
at all -- that file stays exactly as scrape_elo_ratings.py maintains it,
fully separate from this one.

Feeds build_nation_power_rankings.py / nation_power_rankings.py (Nation
Strength Rankings) -- a new, display-only page, not yet wired into any
simulation. See nation_odds_ratings.py for the odds-implied side.
"""

import csv
import sys

import requests

TEAMS_URL = "https://eloratings.net/en.teams.tsv"
WORLD_URL = "https://eloratings.net/World.tsv"
OUT_PATH = "ratings/nation_elo_global.csv"

# Same sanity-floor principle as scrape_elo_ratings.py's own
# MIN_EXPECTED_RATINGS -- refuse to overwrite a good file with a near-
# empty one if eloratings.net ever returns a malformed/empty body without
# raising an HTTPError.
MIN_EXPECTED_RATINGS = 150


def _load_code_to_name() -> dict[str, str]:
    resp = requests.get(TEAMS_URL, timeout=30)
    resp.raise_for_status()
    # eloratings.net's response has no charset in its Content-Type header
    # (confirmed live: "text/tab-separated-values", no "; charset=..."),
    # so requests falls back to the HTTP-spec default of ISO-8859-1 for
    # resp.encoding even though the real body is UTF-8 (confirmed via
    # resp.apparent_encoding) -- decoding a multi-byte UTF-8 name (e.g.
    # "Curaçao") as ISO-8859-1 produces mojibake that then round-trips
    # through csv.writer's own correct UTF-8 encoding as DOUBLE-encoded
    # garbage. Forcing utf-8 here reads the real bytes correctly instead
    # of relying on requests' guess.
    resp.encoding = "utf-8"
    code_to_name = {}
    for line in resp.text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and not parts[0].endswith("_loc"):
            code_to_name[parts[0]] = parts[1]
    return code_to_name


def _load_world_rows() -> list[tuple[str, float, int]]:
    """[(team code, rating, global rank), ...] straight from World.tsv,
    column order per that file's own layout (local rank, global rank,
    code, rating, ...)."""
    resp = requests.get(WORLD_URL, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # see _load_code_to_name's own comment on why
    rows = []
    for line in resp.text.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        try:
            global_rank = int(parts[1])
            rating = float(parts[3])
        except ValueError:
            continue
        rows.append((parts[2], rating, global_rank))
    return rows


def fetch_global_elo_ratings() -> list[dict]:
    """[{team, elo_rating, elo_rank}, ...] for every team eloratings.net
    rates, sorted by elo_rank ascending (best team first)."""
    code_to_name = _load_code_to_name()
    rows = _load_world_rows()

    out = []
    missing_codes = []
    for code, rating, rank in rows:
        name = code_to_name.get(code)
        if name is None:
            missing_codes.append(code)
            continue
        out.append({"team": name, "elo_rating": rating, "elo_rank": rank})
    if missing_codes:
        print(f"WARNING: no team name found for eloratings.net codes: {', '.join(missing_codes)}", file=sys.stderr)
    out.sort(key=lambda r: r["elo_rank"])
    return out


def main() -> None:
    ratings = fetch_global_elo_ratings()
    if len(ratings) < MIN_EXPECTED_RATINGS:
        print(
            f"ERROR: only matched {len(ratings)} teams (need at least {MIN_EXPECTED_RATINGS}) -- "
            "eloratings.net likely returned an empty/malformed response. Leaving "
            f"{OUT_PATH} untouched rather than overwriting it with a near-empty file.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["team", "alias", "elo_rating", "elo_rank"])
        for r in ratings:
            writer.writerow([r["team"], "", r["elo_rating"], r["elo_rank"]])
    print(f"Wrote {len(ratings)} team ratings to {OUT_PATH}")


if __name__ == "__main__":
    main()
