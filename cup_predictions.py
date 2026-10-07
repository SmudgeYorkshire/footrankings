"""
Shared domestic-cup status/prediction helpers.

Split out from football_rankings.py (where these were originally built for
its live Cup Details tab) so european_2027_28.py can reuse the exact same
predicted-cup-winner logic for its Cup Winner access-list slots, without
importing football_rankings.py itself (a Streamlit page script whose whole
body runs on import -- see european_2027_28.py's own _current_standings
docstring for why that's avoided elsewhere on this page already).
"""

import pandas as pd
import streamlit as st

from api_football_fetcher import ApiFootballClient


def _cup_campaign_status(team_names: set[str], played: list[dict], remaining: list[dict]) -> dict:
    """One team's progress through a single cup season, derived purely from
    its own fixtures (played + remaining already fetched for the whole
    competition). Returns a dict with a "state" of:
      - "not_entered"  — no fixture at all yet (their round hasn't been
        drawn/published by the provider yet, common for top-flight sides
        that enter a cup many rounds after it starts)
      - "active"       — has an upcoming fixture
      - "awaiting_draw"— won/advanced their last match but the next round
        isn't drawn yet
      - "eliminated"   — lost (normal time, or on penalties) their last match
    "entry_round"/"entry_date" (when available) is their earliest fixture
    this season, i.e. the phase they entered the competition at.
    """
    def _involves(f):
        return f.get("strHomeTeam") in team_names or f.get("strAwayTeam") in team_names

    team_played = sorted((f for f in played if _involves(f)), key=lambda f: f.get("dateEvent", ""))
    team_remaining = sorted((f for f in remaining if _involves(f)), key=lambda f: f.get("dateEvent", ""))
    if not team_played and not team_remaining:
        return {"state": "not_entered"}

    entry_fx = sorted(team_played + team_remaining, key=lambda f: f.get("dateEvent", ""))[0]
    entry_round, entry_date = entry_fx.get("strRound", ""), entry_fx.get("dateEvent", "")

    if team_remaining:
        nxt = team_remaining[0]
        is_home = nxt.get("strHomeTeam") in team_names
        opponent = nxt.get("strAwayTeam") if is_home else nxt.get("strHomeTeam")
        return {
            "state": "active", "entry_round": entry_round, "entry_date": entry_date,
            "next_round": nxt.get("strRound", ""), "next_date": nxt.get("dateEvent", ""),
            "opponent": opponent, "is_home": is_home,
        }

    last = team_played[-1]
    is_home = last.get("strHomeTeam") in team_names
    hs, as_ = last.get("intHomeScore"), last.get("intAwayScore")
    team_score, opp_score = (hs, as_) if is_home else (as_, hs)
    lost = False
    if team_score is not None and opp_score is not None:
        if team_score < opp_score:
            lost = True
        elif team_score == opp_score:
            # Two-legged aggregate ties aren't reconstructed here (that would
            # need pairing up both legs) -- a single-match loss on penalties
            # is treated as elimination, which covers single-match knockout
            # rounds (the common case for the rounds this feature targets).
            ph, pa = last.get("intPenaltyHome"), last.get("intPenaltyAway")
            if ph is not None and pa is not None:
                team_pens, opp_pens = (ph, pa) if is_home else (pa, ph)
                lost = team_pens < opp_pens
    opponent = last.get("strAwayTeam") if is_home else last.get("strHomeTeam")
    if lost:
        return {
            "state": "eliminated", "entry_round": entry_round, "entry_date": entry_date,
            "round": last.get("strRound", ""), "date": last.get("dateEvent", ""),
            "opponent": opponent, "score": f"{hs}–{as_}",
        }
    return {
        "state": "awaiting_draw", "entry_round": entry_round, "entry_date": entry_date,
        "last_round": last.get("strRound", ""), "last_date": last.get("dateEvent", ""),
    }


def _team_name_set(row) -> set[str]:
    return {n for n in (str(row.get("team", "")).strip(), str(row.get("alias", "")).strip()) if n}


def resolve_predicted_cup_winner(ratings_df: pd.DataFrame, played: list[dict], remaining: list[dict]):
    """Highest-Opta-rated team in this league that hasn't already been
    knocked out of this season's cup, plus any higher-rated teams skipped
    over because they're already eliminated. Returns
    (predicted_row, predicted_status, [(skipped_row, skipped_status), ...])."""
    ranked = ratings_df.sort_values("opta_rating", ascending=False)
    skipped = []
    for _, row in ranked.iterrows():
        status = _cup_campaign_status(_team_name_set(row), played, remaining)
        if status["state"] == "eliminated":
            skipped.append((row, status))
            continue
        return row, status, skipped
    # Everyone we track has been eliminated -- fall back to the top-rated
    # team anyway rather than showing nothing.
    row = ranked.iloc[0]
    status = _cup_campaign_status(_team_name_set(row), played, remaining)
    return row, status, skipped[1:]


@st.cache_data(ttl=3_600, show_spinner=False)
def fetch_cup_fixtures(cup_id, season, key):
    """Every fixture (played + remaining) for a cup's current season."""
    return ApiFootballClient(api_key=key).get_fixtures(cup_id, season)
