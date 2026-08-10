"""
Opta Rankings — public page.

Shows Opta Power Ranking ratings (0-100 scale) used to project match outcomes:
  • Overall — every club from every league, ranked on one global table
  • By League — per-league ratings table
  • Non-Top 5 — every club except those from the Top 5 leagues, ranked on one table
"""

import os
import time

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from config import LEAGUES, get_current_season
from ratings_manager import load_ratings
from api_football_fetcher import ApiFootballClient
from league_display import TOP5_LEAGUES as _TOP5_LEAGUES, DROPDOWN_LABELS, DROPDOWN_ORDER

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")

st.markdown(
    "<h3 style='margin:0'>⭐ Opta Rankings</h3>",
    unsafe_allow_html=True,
)
st.caption("Opta Power Ranking ratings used to project match outcomes across all European leagues.")
st.divider()

tab_overall, tab_league, tab_non_top5 = st.tabs(["🌍 Overall", "🏆 By League", "🌐 Non-Top 5"])

_RATING_COL_CFG = {
    "Rank":          st.column_config.NumberColumn("Rank", width="small"),
    "Badge":         st.column_config.ImageColumn("", width="small"),
    "Team":          st.column_config.TextColumn("Team", width="medium"),
    "League Badge":  st.column_config.ImageColumn("", width="small"),
    "League":        st.column_config.TextColumn("League", width="medium"),
    "Opta Rating":   st.column_config.NumberColumn("Opta Rating", format="%.1f", width="small"),
}


def _league_badge_url(league_id: int) -> str:
    """API-Football's league logo CDN URL — deterministic, no API call needed."""
    return f"https://media.api-sports.io/football/leagues/{league_id}.png"


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_team_badges(league_id: int, season, key: str) -> dict[str, str]:
    """{team_name: badge_url} for one league's current roster."""
    try:
        client = ApiFootballClient(api_key=key)
        roster = client.get_standings(league_id, season)
    except Exception:
        return {}
    return {r["strTeam"]: r["strBadge"] for r in roster if r.get("strTeam") and r.get("strBadge")}


# ---------------------------------------------------------------------------
# Combine every league's ratings into one table (shared by Overall/Non-Top 5)
# Team names are shown as the live-data provider (API-Football) has them,
# matching the rest of the site. The Opta <-> provider name mapping itself
# lives in club_aliases.csv.
# ---------------------------------------------------------------------------
_all_rows = []
for league_name, cfg in LEAGUES.items():
    ratings_df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [])
    season = cfg.get("af_season") or get_current_season(cfg["season_type"])
    team_badges = _fetch_team_badges(cfg["id"], season, _API_KEY)
    league_badge = _league_badge_url(cfg["id"])
    time.sleep(0.3)  # pacing on a cold cache — avoids API-Football's burst rate-limit

    for _, row in ratings_df.iterrows():
        if pd.isna(row["opta_rating"]):
            continue
        opta_name = row["team"]
        alias = str(row.get("alias", "")).strip()
        display_name = alias if alias else opta_name
        # Badge lookup checks both fields — alias isn't always the one that
        # actually matches the live provider's current name (sometimes the
        # primary team name already matches and alias is a stale leftover).
        badge = team_badges.get(display_name) or team_badges.get(opta_name) or team_badges.get(alias, "")
        _all_rows.append({
            "Team":         display_name,
            "Badge":        badge,
            "League":       f"{cfg['flag']} {league_name}",
            "League Badge": league_badge,
            "_league_name": league_name,
            "Opta Rating":  row["opta_rating"],
        })
_all_df = pd.DataFrame(_all_rows)


def _ranked(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("Opta Rating", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", out.index + 1)
    return out[["Rank", "Badge", "Team", "League Badge", "League", "Opta Rating"]]


# ---------------------------------------------------------------------------
# Overall — every club from every league
# ---------------------------------------------------------------------------
with tab_overall:
    st.dataframe(
        _ranked(_all_df),
        column_config=_RATING_COL_CFG,
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# By League — pick one league, show its ratings table
# ---------------------------------------------------------------------------
with tab_league:
    league_name = st.selectbox(
        "League", options=DROPDOWN_ORDER,
        format_func=lambda n: DROPDOWN_LABELS.get(n, n),
        key="opta_league_select",
    )
    cfg = LEAGUES[league_name]

    league_df = _ranked(_all_df[_all_df["_league_name"] == league_name]).drop(columns=["League", "League Badge"])

    col_logo, col_title = st.columns([1, 9])
    with col_logo:
        st.image(_league_badge_url(cfg["id"]), width=60)
    with col_title:
        st.markdown(f"#### {cfg['flag']} {league_name}")
    st.dataframe(
        league_df,
        column_config=_RATING_COL_CFG,
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# Non-Top 5 — every club except England/France/Germany/Italy/Spain
# ---------------------------------------------------------------------------
with tab_non_top5:
    non_top5_df = _all_df[~_all_df["_league_name"].isin(_TOP5_LEAGUES)]
    st.dataframe(
        _ranked(non_top5_df),
        column_config=_RATING_COL_CFG,
        use_container_width=True,
        hide_index=True,
    )
