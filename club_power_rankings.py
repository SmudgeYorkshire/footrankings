"""
Club Power Rankings — public page.

A new, standalone 0-1000 rating scale covering every club Opta rates
worldwide (not just the 54 tracked top-flight leagues) — built by
build_club_power_rankings.py from opta_power_rankings.csv plus whatever
odds-driven adjustment club_rating_calibration.py fit that day. The single
best club worldwide = 1000; the rest are scaled relative to it.

This is deliberately separate from the Opta Rankings page's 0-100 scale:
that page shows Opta's own rating (and, for tracked leagues, the same
number the simulator uses); this page is the new, odds-aware ranking the
site maintains itself. Clubs outside the 54 tracked leagues (2nd tiers,
other countries) are already present here with no further work, since
build_club_power_rankings.py starts from the complete global Opta list,
not just the tracked-league rosters -- the "Tracked league" tag just notes
which ones also feed live match predictions.
"""

import json
import os
from pathlib import Path

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from config import LEAGUES
from league_display import DROPDOWN_LABELS, DROPDOWN_ORDER, TOP5_LEAGUES

load_dotenv()

_RANKINGS_PATH = "club_power_rankings_1000.csv"
_META_PATH = "opta_power_rankings_meta.json"


def _load_opta_meta() -> dict:
    if not Path(_META_PATH).exists():
        return {}
    try:
        with open(_META_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


st.markdown(
    "<h3 style='margin:0'>🏆 Club Power Rankings</h3>",
    unsafe_allow_html=True,
)
st.caption(
    "A new 0-1000 rating for every club Opta tracks worldwide, not just our 54 tracked "
    "top-flight leagues — the single best club = 1000. Built from Opta's own rating plus, "
    "for clubs in a leading betting market, a daily adjustment fitted against real bookmaker "
    "odds (see the Opta Rankings page for the underlying 0-100 Opta number used in match "
    "predictions)."
)

if not Path(_RANKINGS_PATH).exists():
    st.info(
        f"No club power ranking found yet. Run `build_club_power_rankings.py` "
        f"(scheduled daily via the odds/ratings workflow) to generate {_RANKINGS_PATH}."
    )
    st.stop()

_opta_meta = _load_opta_meta()
if _opta_meta.get("opta_last_updated"):
    st.caption(f"📅 Baseline Opta data from **{_opta_meta['opta_last_updated']}**, odds-adjusted daily.")


@st.cache_data(ttl=3_600, show_spinner=False)
def _load_rankings_df(mtime: float) -> pd.DataFrame:
    df = pd.read_csv(_RANKINGS_PATH)
    df["opta_rating_raw"] = pd.to_numeric(df["opta_rating_raw"], errors="coerce")
    df["adjustment"] = pd.to_numeric(df["adjustment"], errors="coerce").fillna(0.0)
    df["rating_1000"] = pd.to_numeric(df["rating_1000"], errors="coerce")
    df["tracked_league"] = df["tracked_league"].fillna("")
    return df


_df = _load_rankings_df(Path(_RANKINGS_PATH).stat().st_mtime)

col_metric1, col_metric2, col_metric3 = st.columns(3)
col_metric1.metric("Clubs ranked", f"{len(_df):,}")
col_metric2.metric("In a tracked league", f"{(_df['tracked_league'] != '').sum():,}")
col_metric3.metric("With a live odds adjustment", f"{(_df['adjustment'] != 0).sum():,}")

st.divider()

# tracked_league stores "{flag} {league name}" (see build_club_power_rankings.py's
# tracked_league_map) -- match by suffix so the flag emoji doesn't need repeating here.
_TOP5_LABELS = tuple(f" {name}" for name in TOP5_LEAGUES)


def _render_table(df: pd.DataFrame, key_prefix: str, league_options: list[str]) -> None:
    col_search, col_league, col_toggle = st.columns([3, 3, 1])
    with col_search:
        search = st.text_input("Search club", key=f"{key_prefix}_search", placeholder="e.g. Boca Juniors")
    with col_league:
        options = ["All leagues"] + league_options
        league_choice = st.selectbox(
            "League", options=options,
            format_func=lambda n: DROPDOWN_LABELS.get(n, n) if n != "All leagues" else n,
            key=f"{key_prefix}_league_select",
        )
    with col_toggle:
        tracked_only = st.checkbox("Tracked leagues only", key=f"{key_prefix}_tracked_only")

    view = df
    if search:
        view = view[view["team"].str.contains(search, case=False, na=False)]
    if league_choice != "All leagues":
        league_label = f"{LEAGUES[league_choice]['flag']} {league_choice}"
        view = view[view["tracked_league"] == league_label]
    elif tracked_only:
        view = view[view["tracked_league"] != ""]

    view = view.rename(columns={
        "rank": "Rank", "team": "Club", "tracked_league": "Tracked League",
        "opta_rating_raw": "Opta Rating", "adjustment": "Odds Adjustment",
        "rating_1000": "Power Rating", "badge_url": "Badge",
    })[["Rank", "Badge", "Club", "Tracked League", "Opta Rating", "Odds Adjustment", "Power Rating"]]

    st.dataframe(
        view,
        column_config={
            "Rank":            st.column_config.NumberColumn("Rank", width="small"),
            "Badge":           st.column_config.ImageColumn("", width="small"),
            "Club":            st.column_config.TextColumn("Club", width="medium"),
            "Tracked League":  st.column_config.TextColumn("Tracked League", width="medium"),
            "Opta Rating":     st.column_config.NumberColumn("Opta Rating", format="%.1f", width="small"),
            "Odds Adjustment": st.column_config.NumberColumn("Odds Adjustment", format="%+.1f", width="small"),
            "Power Rating":    st.column_config.NumberColumn("Power Rating", format="%.1f", width="small"),
        },
        use_container_width=True,
        hide_index=True,
        height=600,
    )


tab_overall, tab_non_top5 = st.tabs(["🌍 Overall", "🌐 Non-Top 5"])

with tab_overall:
    _render_table(_df, "club_power_overall", DROPDOWN_ORDER)

with tab_non_top5:
    st.caption("Every ranked club except those from the Top 5 leagues (England, Spain, Germany, Italy, France).")
    _non_top5_df = _df[~_df["tracked_league"].str.endswith(_TOP5_LABELS)]
    _non_top5_leagues = [n for n in DROPDOWN_ORDER if n not in TOP5_LEAGUES]
    _render_table(_non_top5_df, "club_power_non_top5", _non_top5_leagues)
