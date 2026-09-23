"""
Real UEFA Nations League 2026-27 fixtures/results (API-Football league id
5, season 2026) for nations_league.py's Table & Fixtures and Manual
Predictions tabs.

nations_league_simulator.py's own pre-season group simulation doesn't
need this -- it draws a synthetic (but structurally correct) double
round-robin schedule since only the probability math matters there, not
real dates. Showing the actual calendar and locking in real results as
they're played needs the genuine fixture list, though, which this module
fetches and resolves to this site's own team-name spelling (see
_NAME_ALIASES for the handful that differ from API-Football's).
"""

import os

import streamlit as st

from api_football_fetcher import ApiFootballClient
from qualifying_projection import resolve_to_team
from nations_league_data import ALL_NL_TEAMS

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_LEAGUE_ID = 5
_SEASON = 2026

# API-Football's own spelling, where it differs from this site's (see
# NL_GROUPS in nations_league_data.py) -- resolve_to_team's fuzzy match
# already handles everything else.
_NAME_ALIASES = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "FYR Macedonia": "North Macedonia",
    "Rep. Of Ireland": "Republic of Ireland",
    "Türkiye": "Turkey",
}


def _resolve_name(raw: str) -> str:
    return _NAME_ALIASES.get(raw) or resolve_to_team(raw, ALL_NL_TEAMS) or raw


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_all_fixtures() -> tuple[list[dict], list[dict]]:
    """(played, remaining) for the entire 2026-27 Nations League -- all 54
    nations, 156 fixtures -- fetched once and filtered per group by the
    caller, rather than one API call per group."""
    if not _API_KEY:
        return [], []
    client = ApiFootballClient(_API_KEY)
    played, remaining = client.get_fixtures(_LEAGUE_ID, _SEASON)
    return played, remaining


def group_fixtures(teams: list[str]) -> tuple[list[dict], list[dict]]:
    """(played, remaining) real fixtures among exactly `teams` (one
    group), resolved to this site's own team names and sorted by date.
    Each fixture dict is API-Football's normalized shape (strHomeTeam,
    strAwayTeam, intHomeScore, intAwayScore, dateEvent, strTime, ...)."""
    played, remaining = _fetch_all_fixtures()
    team_set = set(teams)

    def _resolve_and_filter(fixtures: list[dict]) -> list[dict]:
        out = []
        for f in fixtures:
            h = _resolve_name(f.get("strHomeTeam", ""))
            a = _resolve_name(f.get("strAwayTeam", ""))
            if h in team_set and a in team_set:
                out.append({**f, "strHomeTeam": h, "strAwayTeam": a})
        return sorted(out, key=lambda f: (f.get("dateEvent", ""), f.get("strTime", "")))

    return _resolve_and_filter(played), _resolve_and_filter(remaining)
