"""
Opta Rankings — public page.

Shows Opta Power Ranking ratings (0-100 scale) used to project match outcomes:
  • Overall — every club from every league, ranked on one global table
  • Non-Top 5 — every club except those from the Top 5 leagues, ranked on one table
  • By League — per-league ratings table
"""

import streamlit as st
import pandas as pd

from config import LEAGUES
from ratings_manager import load_ratings

_TOP5_LEAGUES = {
    "English Premier League", "Italian Serie A", "Spanish La Liga",
    "German Bundesliga", "French Ligue 1",
}

st.markdown(
    "<h3 style='margin:0'>⭐ Opta Rankings</h3>",
    unsafe_allow_html=True,
)
st.caption("Opta Power Ranking ratings used to project match outcomes across all European leagues.")
st.divider()

tab_overall, tab_non_top5, tab_league = st.tabs(["🌍 Overall", "🌐 Non-Top 5", "🏆 By League"])

_RATING_COL_CFG = {
    "Rank":        st.column_config.NumberColumn("Rank", width="small"),
    "Team":        st.column_config.TextColumn("Team", width="medium"),
    "League":      st.column_config.TextColumn("League", width="medium"),
    "Opta Rating": st.column_config.NumberColumn("Opta Rating", format="%.1f", width="small"),
}

# ---------------------------------------------------------------------------
# Combine every league's ratings into one table (shared by Overall/Non-Top 5)
# Team names are shown as the live-data provider (API-Football) has them,
# matching the rest of the site. The Opta <-> provider name mapping itself
# lives in club_aliases.csv.
# ---------------------------------------------------------------------------
_all_rows = []
for league_name, cfg in LEAGUES.items():
    ratings_df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [])
    for _, row in ratings_df.iterrows():
        if pd.isna(row["opta_rating"]):
            continue
        opta_name = row["team"]
        alias = str(row.get("alias", "")).strip()
        display_name = alias if alias else opta_name
        _all_rows.append({
            "Team":        display_name,
            "League":      f"{cfg['flag']} {league_name}",
            "_league_name": league_name,
            "Opta Rating": row["opta_rating"],
        })
_all_df = pd.DataFrame(_all_rows)


def _ranked(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("Opta Rating", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", out.index + 1)
    return out[["Rank", "Team", "League", "Opta Rating"]]


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

# ---------------------------------------------------------------------------
# By League — pick one league, show its ratings table
# ---------------------------------------------------------------------------
with tab_league:
    league_name = st.selectbox("League", options=list(LEAGUES.keys()), key="opta_league_select")
    cfg = LEAGUES[league_name]

    league_df = _ranked(_all_df[_all_df["_league_name"] == league_name]).drop(columns=["League"])

    st.markdown(f"#### {cfg['flag']} {league_name}")
    st.dataframe(
        league_df,
        column_config=_RATING_COL_CFG,
        use_container_width=True,
        hide_index=True,
    )
