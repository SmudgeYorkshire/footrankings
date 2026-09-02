"""
Trivia stats for the European Competitions "Trivia" tab: how many clubs
and nations reached each competition's League Phase vs. got eliminated
in qualifying (Q1 through the Play-off round), plus grand totals across
all three competitions combined.

Split out from european.py (a page script that runs top-level rendering
code on import) so this reusable logic can be imported cleanly, same
pattern as qualifying_projection.py.
"""

import streamlit as st

from qualifying_projection import (
    _fetch_comp_fixtures, _project_league_phase_field, _load_combined_ratings,
)
from qualifying_bracket import CONFIRMED_LEAGUE_PHASE
from coefficients_live import _load_club_country_map

_QUAL_ROUNDS = frozenset({
    "1st Qualifying Round", "2nd Qualifying Round", "3rd Qualifying Round",
    "Play-offs", "Playoff round",
})

# The live qualifying-round data sometimes names a club differently than
# this site's own League Phase entrant lists do (usually the club's
# native-language name vs. the English exonym we use elsewhere, e.g.
# UEFA/API-Football's "Sparta Praha" vs. our "Sparta Prague") -- without
# this, the same physical club would be double-counted as both a League
# Phase entrant AND a separate "eliminated in qualifying" club. Each
# entry here was found and verified by cross-checking every "eliminated"
# name against the League Phase list; extend it if a new one surfaces.
_ELIMINATION_NAME_ALIASES: dict[str, str] = {
    "Sparta Praha": "Sparta Prague",
    "Union St. Gilloise": "Union Saint-Gilloise",
}

COMPETITIONS = ("Champions League", "Europa League", "Conference League")


def _by_country(rows: list[tuple[str, str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for team, country in rows:
        out.setdefault(country, []).append(team)
    for country in out:
        out[country].sort()
    return out


def _country_lookup(comp_name: str) -> callable:
    confirmed_country = {t: c for t, c, _flag in CONFIRMED_LEAGUE_PHASE.get(comp_name, [])}
    club_country = _load_club_country_map()

    def country_for(team: str) -> str:
        if team in confirmed_country:
            return confirmed_country[team]
        return club_country.get(team, "Unknown")

    return country_for


def _qualifying_and_direct_entrants(comp_name: str, api_key: str) -> set[str]:
    played, remaining = _fetch_comp_fixtures(comp_name, api_key)
    qual_teams: set[str] = set()
    for fx in played + remaining:
        if fx.get("strRound") in _QUAL_ROUNDS:
            qual_teams.add(fx.get("strHomeTeam", ""))
            qual_teams.add(fx.get("strAwayTeam", ""))
    qual_teams.discard("")
    qual_teams = {_ELIMINATION_NAME_ALIASES.get(t, t) for t in qual_teams}
    direct_teams = {t for t, _c, _f in CONFIRMED_LEAGUE_PHASE.get(comp_name, [])}
    return qual_teams | direct_teams


@st.cache_data(ttl=3600, show_spinner=False)
def competition_trivia(comp_name: str, api_key: str) -> dict:
    """{"league_phase": {country: [clubs]}, "eliminated": {country: [clubs]}}
    for one competition -- every club that reached its 36-club League
    Phase field, and every club knocked out of *this competition's own*
    qualifying bracket (Q1 through Play-offs) before reaching it. A
    Play-off loser that cascades into a lower competition's League Phase
    (Champions League -> Europa League, Europa League -> Conference
    League) still counts as "eliminated" here, since it's specifically
    about this competition's own bracket -- see overall_trivia() for the
    season-wide count that excludes cascade survivors."""
    ratings_df = _load_combined_ratings()
    field = _project_league_phase_field(comp_name, ratings_df)
    league_phase_clubs = {f["team"] for f in field}
    league_phase = _by_country([(f["team"], f["country"]) for f in field])

    country_for = _country_lookup(comp_name)
    eliminated_teams = _qualifying_and_direct_entrants(comp_name, api_key) - league_phase_clubs
    eliminated = _by_country([(t, country_for(t)) for t in eliminated_teams])

    return {"league_phase": league_phase, "eliminated": eliminated}


@st.cache_data(ttl=3600, show_spinner=False)
def overall_trivia(api_key: str) -> dict:
    """Season-wide totals across all three competitions combined: every
    club/nation that reached *some* League Phase, and every club/nation
    that's genuinely out of Europe entirely this season -- unlike
    competition_trivia()'s per-competition "eliminated" (which counts a
    Play-off cascade survivor as eliminated from its original
    competition), a club is only counted here if it didn't reach ANY of
    the three League Phases."""
    league_phase_clubs: set[str] = set()
    league_phase_nations: set[str] = set()
    all_entrants: dict[str, str] = {}  # team -> country

    for comp in COMPETITIONS:
        ratings_df = _load_combined_ratings()
        field = _project_league_phase_field(comp, ratings_df)
        for f in field:
            league_phase_clubs.add(f["team"])
            league_phase_nations.add(f["country"])
        country_for = _country_lookup(comp)
        for t in _qualifying_and_direct_entrants(comp, api_key):
            all_entrants[t] = country_for(t)

    eliminated_clubs = set(all_entrants) - league_phase_clubs
    eliminated_nations = {all_entrants[t] for t in eliminated_clubs}
    all_nations = league_phase_nations | eliminated_nations

    return {
        "league_phase_clubs": len(league_phase_clubs),
        "league_phase_nations": len(league_phase_nations),
        "eliminated_clubs": len(eliminated_clubs),
        "eliminated_nations": len(eliminated_nations),
        "total_clubs": len(league_phase_clubs) + len(eliminated_clubs),
        "total_nations": len(all_nations),
    }
