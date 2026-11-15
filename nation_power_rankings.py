"""
Nation Strength Rankings — public page.

The nation-level analog of club_power_rankings.py ("Club Strength
Rankings") -- every national team eloratings.net rates (244, confirmed
live), not just the 54 UEFA Nations League nations tracked elsewhere on
this site, built by build_nation_power_rankings.py from
ratings/nation_elo_global.csv plus whatever odds-driven signal
nation_odds_ratings.py has accumulated.

Three ratings per team, all on eloratings.net's own native scale:
  - Elo Rating: today's raw eloratings.net Elo -- unlike the club version,
    there's no separate "today's small live nudge" layer here, since
    eloratings.net's own number already updates continuously from real
    results (Opta's rating needed that extra layer; this doesn't).
  - Odds Rating: a separate, persistent rating built entirely from this
    team's own real international-match odds history (blank where that
    history is too thin or absent -- see Elo Rating for those teams
    instead).
  - Combined Rating: a confidence-weighted blend of the two -- full
    weight on the odds signal once a team has enough real odds-implied
    history, falling back toward Elo Rating where that history is thin
    or missing. This is the headline "Strength Ranking" below and is NOT
    wired into nations_league_simulator.py or any other live prediction.

Deliberately NOT rescaled onto a stylized band the way Club Strength
Rankings is (that page's Opta/Odds/Combined Elo all land on [1200, 2400]
purely for display, since Opta's native 0-100 scale doesn't look like
Elo at all) -- eloratings.net's own numbers already ARE a widely
recognized real Elo scale (e.g. "Spain ~2290" is a number a football fan
might already know), so remapping them here would only obscure something
already familiar.
"""

from pathlib import Path

import streamlit as st
import pandas as pd

OUT_PATH = "nation_power_rankings.csv"


st.markdown(
    "<h3 style='margin:0'>🌍 Nation Strength Rankings</h3>",
    unsafe_allow_html=True,
)
st.caption(
    "An Elo rating for every national team eloratings.net tracks worldwide, not just our "
    "54 tracked UEFA Nations League nations. Elo Rating, Odds Rating and Combined Rating are "
    "three views of the same team on eloratings.net's own familiar number line: its raw Elo "
    "rating, a separate rating built entirely from real international-match odds history, "
    "and a confidence-weighted blend of the two."
)

if not Path(OUT_PATH).exists():
    st.info(
        f"No nation strength ranking found yet. Run `build_nation_power_rankings.py` "
        f"(scheduled daily via the odds/ratings workflow) to generate {OUT_PATH}."
    )
    st.stop()


@st.cache_data(ttl=3_600, show_spinner=False)
def _load_rankings_df(mtime: float) -> pd.DataFrame:
    df = pd.read_csv(OUT_PATH)
    df["odds_rating"] = pd.to_numeric(df["odds_rating"], errors="coerce")
    for col in ("odds_n_updates", "combined_rating", "combined_confidence"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["tracked_nl"] = df["tracked_nl"].astype(bool)
    return df


_df = _load_rankings_df(Path(OUT_PATH).stat().st_mtime)

col_metric1, col_metric2, col_metric3 = st.columns(3)
col_metric1.metric("Nations ranked", f"{len(_df):,}")
col_metric2.metric("UEFA Nations League teams", f"{_df['tracked_nl'].sum():,}")
col_metric3.metric("With an odds-implied rating", f"{_df['odds_rating'].notna().sum():,}")

st.divider()

col_search, col_toggle = st.columns([3, 1])
with col_search:
    search = st.text_input("Search nation", placeholder="e.g. Brazil")
with col_toggle:
    nl_only = st.checkbox("Nations League teams only")

view = _df
if search:
    view = view[view["team"].str.contains(search, case=False, na=False)]
if nl_only:
    view = view[view["tracked_nl"]]

view = view.rename(columns={
    "rank": "Rank", "team": "Nation", "tracked_nl": "Nations League",
    "elo_rating": "Elo Rating", "odds_rating": "Odds Rating",
    "odds_n_updates": "Odds Evidence (n)", "combined_rating": "Combined Rating",
    "combined_confidence": "Odds Weight", "flag_url": "Flag",
})[["Rank", "Flag", "Nation", "Nations League", "Elo Rating", "Odds Rating",
    "Odds Evidence (n)", "Combined Rating", "Odds Weight"]]

st.dataframe(
    view,
    column_config={
        "Rank":           st.column_config.NumberColumn("Rank", width="small"),
        "Flag":           st.column_config.ImageColumn("", width="small"),
        "Nation":         st.column_config.TextColumn("Nation", width="medium"),
        "Nations League": st.column_config.CheckboxColumn("Nations League", width="small"),
        "Elo Rating":     st.column_config.NumberColumn(
            "Elo Rating", format="%.0f", width="small",
            help="Today's raw eloratings.net Elo rating.",
        ),
        "Odds Rating": st.column_config.NumberColumn(
            "Odds Rating", format="%.0f", width="small",
            help="A separate, persistent rating built entirely from this team's real "
                 "international-match odds history (not capped, not reset each day). Blank "
                 "where there's no odds-market coverage for this team yet.",
        ),
        "Odds Evidence (n)": st.column_config.NumberColumn(
            "Odds Evidence (n)", width="small",
            help="How many real odds-implied observations back this team's Odds Rating -- "
                 "also what Combined Rating's blend weight is based on.",
        ),
        "Combined Rating": st.column_config.NumberColumn(
            "Combined Rating", format="%.0f", width="small",
            help="A confidence-weighted blend of Elo Rating and Odds Rating -- full weight on "
                 "the odds signal once a team has enough real evidence, falling back toward "
                 "Elo Rating where that evidence is thin or missing. This page's headline "
                 "ranking. Not yet wired into any live match prediction.",
        ),
        "Odds Weight": st.column_config.ProgressColumn(
            "Odds Weight", width="small", min_value=0.0, max_value=1.0,
            help="How much of Combined Rating comes from the odds signal vs. Elo Rating "
                 "(0 = pure Elo, 1 = pure odds-implied).",
        ),
    },
    width="content",
    hide_index=True,
    height=600,
)
