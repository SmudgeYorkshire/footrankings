"""
Builds the Nation Power Ranking -- every national team eloratings.net
rates (244, confirmed live), the nation-level analog of
build_club_power_rankings.py.

Much simpler than the club version, for one structural reason: clubs'
odds-implied rating is scoped per-LEAGUE (each league's own "best team =
100" scale), so it has to be converted to a DELTA against that club's own
league baseline before it can be blended onto the global club scale.
Nations have no such per-league scoping -- nation_odds_ratings.py's own
fit already operates directly in eloratings.net's native Elo points, the
exact same units ratings/nation_elo_global.csv already uses -- so the two
numbers are already directly comparable with no delta/rescale step
needed, and (unlike clubs) this page shows eloratings.net's own familiar
native numbers rather than a stylized [1200, 2400] band -- see
nation_power_rankings.py's own module docstring for why.

Three ratings per team, all on eloratings.net's own native scale:
  - elo_rating: today's raw eloratings.net Elo (scrape_nation_elo_
    ratings.py) -- NOT fed by any live daily nudge (eloratings.net's own
    number already updates continuously from real results, unlike
    Opta's, which needed one).
  - odds_rating: nation_odds_ratings.py's persistent, full-history odds-
    implied rating, for teams with any real international-match odds
    coverage (blank otherwise -- deliberately NOT backfilled to the raw
    Elo number when coverage is absent).
  - combined_rating: a confidence-weighted blend of the two (full weight
    on the odds signal once a team has >=N_FULL_CONFIDENCE real odds-
    implied observations, falling back toward pure Elo as that evidence
    thins out or disappears) -- straight linear interpolation, same
    formula and same reasoning as build_club_power_rankings._combined_
    rating (see that function's own docstring for why "interpolate"
    rather than "add the delta" is the correct, non-double-counting
    form -- there's no delta here at all, just two numbers on one scale,
    so this reduces to `elo * (1 - confidence) + odds * confidence`).

Display-only, NOT wired into nations_league_simulator.py or any other
live prediction (see nation_odds_ratings.py's own module docstring).

tracked_nl tags whichever of these 244 teams is also one of the 54
UEFA Nations League teams this site actively simulates (informational
only, same spirit as build_club_power_rankings.py's own "Tracked
league" tag) -- matched by exact name since ALL_NL_TEAMS already shares
this site's own canonical country-name spelling.

Writes nation_power_rankings.csv (rank, team, tracked_nl, elo_rating,
elo_rank, odds_rating, odds_n_updates, combined_rating,
combined_confidence, flag_url).

Usage: py build_nation_power_rankings.py
"""

import sys
from pathlib import Path

import pandas as pd

from flags import flag_url
from nations_league_data import ALL_NL_TEAMS, GLOBAL_ELO_NAME_ALIASES
from nation_odds_ratings import GLOBAL_ELO_PATH, RATINGS_OUT_PATH, N_FULL_CONFIDENCE

OUT_PATH = "nation_power_rankings.csv"

# A handful of ALL_NL_TEAMS' own canonical names ("Republic of Ireland",
# "Türkiye") differ from eloratings.net's own English name for that same
# team ("Ireland", "Turkey") -- nations_league_data.GLOBAL_ELO_NAME_ALIASES
# already tracks exactly this mismatch (reused here, not re-declared, so
# the two can never drift apart) for nations_league_simulator.py's own
# ratings load; this global pull reads eloratings.net's raw name directly
# with no such translation, so the reverse mapping is needed here to tag
# tracked_nl correctly.
_NL_TEAMS_BY_GLOBAL_NAME = {GLOBAL_ELO_NAME_ALIASES.get(t, t) for t in ALL_NL_TEAMS}


def main() -> None:
    if not Path(GLOBAL_ELO_PATH).exists():
        print(f"{GLOBAL_ELO_PATH} not found -- run scrape_nation_elo_ratings.py first.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(GLOBAL_ELO_PATH)
    df["tracked_nl"] = df["team"].isin(_NL_TEAMS_BY_GLOBAL_NAME)

    odds_meta: dict[str, tuple[float, int]] = {}
    if Path(RATINGS_OUT_PATH).exists():
        odf = pd.read_csv(RATINGS_OUT_PATH)
        odds_meta = dict(zip(odf["team"], zip(odf["odds_rating"], odf["n_updates"])))
    df["odds_rating"] = df["team"].map(lambda t: odds_meta.get(t, (None, 0))[0])
    df["odds_n_updates"] = df["team"].map(lambda t: odds_meta.get(t, (None, 0))[1])

    df["combined_confidence"] = (df["odds_n_updates"] / N_FULL_CONFIDENCE).clip(upper=1.0)
    odds_or_elo = df["odds_rating"].fillna(df["elo_rating"])
    df["combined_rating"] = (
        df["elo_rating"] * (1.0 - df["combined_confidence"]) + odds_or_elo * df["combined_confidence"]
    ).round(1)

    df["flag_url"] = df["team"].map(flag_url)

    out = df.sort_values("combined_rating", ascending=False).reset_index(drop=True)
    out = out.drop(columns=["alias", "elo_rank"])
    out.insert(0, "rank", out.index + 1)
    out = out[["rank", "team", "tracked_nl", "elo_rating", "odds_rating",
               "odds_n_updates", "combined_rating", "combined_confidence", "flag_url"]]
    out.to_csv(OUT_PATH, index=False)

    n_odds = out["odds_rating"].notna().sum()
    print(f"Wrote {len(out)} nations to {OUT_PATH} ({n_odds} with an odds-implied rating)")
    summary = out.head(10).to_string(index=False)
    print(summary.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))


if __name__ == "__main__":
    main()
