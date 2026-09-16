"""
2026-27 UEFA Nations League — group stage projections and League A's
predicted knockout bracket.

Groups are the real UEFA draw (see nations_league_data.py); ratings are
eloratings.net's current national-team Elo, scraped by
scrape_elo_ratings.py into ratings/nations_league_elo.csv. The group
stage hasn't kicked off yet (first matchday Sep 2026), so every group
below is a fresh Monte Carlo simulation from a blank table rather than a
mid-season update.
"""

import streamlit as st
import pandas as pd

from flags import flag_url
from nations_league_data import NL_GROUPS, NL_FLAG_ALIASES
from nations_league_simulator import load_nl_ratings, simulate_group, simulate_league_a_knockouts

st.title("🌍 UEFA Nations League 2026/27")
st.caption(
    "Group stage runs September-November 2026. Every group below is simulated from a blank "
    "table using current national-team Elo ratings from "
    "[eloratings.net](https://eloratings.net/) — treat it as a pre-season outlook, not a "
    "live in-season update."
)


def _flag(team: str) -> str:
    return flag_url(NL_FLAG_ALIASES.get(team, team))


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


_PROMOTION_NOTE = {
    "League A": "Bottom side in each group is relegated to League B (subject to the March 2027 relegation play-offs).",
    "League B": "Group winners are promoted to League A; bottom side relegated to League C.",
    "League C": "Group winners are promoted to League B; the two lowest-ranked 4th-place teams across League C are relegated to League D.",
    "League D": "Group winners are promoted to League C.",
}

ratings_df = load_nl_ratings()
if ratings_df.empty:
    st.warning(
        "No Elo ratings found yet — run `scrape_elo_ratings.py` to fetch them from eloratings.net."
    )
    st.stop()

league_names = list(NL_GROUPS.keys())
league_tabs = st.tabs(league_names)

all_group_probs: dict[str, dict[str, pd.DataFrame]] = {}

for league_tab, league_name in zip(league_tabs, league_names):
    with league_tab:
        st.caption(_PROMOTION_NOTE[league_name])
        groups = NL_GROUPS[league_name]
        is_knockout_league = league_name == "League A"
        tab_labels = list(groups.keys()) + (["🏆 Knockout Bracket"] if is_knockout_league else [])
        group_tabs = st.tabs(tab_labels)
        league_group_probs: dict[str, pd.DataFrame] = {}

        for group_tab, (group_name, teams) in zip(group_tabs, groups.items()):
            with group_tab:
                probs, exp_pts = simulate_group(teams, ratings_df, n_sim=10_000)
                league_group_probs[group_name] = probs

                elo_lookup = dict(zip(ratings_df["team"], ratings_df["opta_rating"]))
                n_teams = len(teams)
                rows = []
                for team in probs.index:
                    row = {
                        "Flag": _flag(team),
                        "Team": team,
                        "Elo": int(elo_lookup.get(team, 0)),
                        "Projected Pts": round(exp_pts.get(team, 0.0), 1),
                    }
                    for pos in range(1, n_teams + 1):
                        row[_ordinal(pos)] = round(probs.loc[team, str(pos)] * 100, 1)
                    rows.append(row)
                display_df = pd.DataFrame(rows)

                col_cfg = {
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "Elo": st.column_config.NumberColumn("Elo", width="small"),
                    "Projected Pts": st.column_config.NumberColumn("Proj. Pts", width="small"),
                }
                for pos in range(1, n_teams + 1):
                    col_cfg[_ordinal(pos)] = st.column_config.NumberColumn(_ordinal(pos), format="%.1f%%", width="small")

                st.dataframe(
                    display_df, column_config=col_cfg, use_container_width=True,
                    hide_index=True, height=len(display_df) * 35 + 38,
                )

        all_group_probs[league_name] = league_group_probs

        if is_knockout_league:
            with group_tabs[-1]:
                st.markdown("#### Path to the Nations League Finals")
                st.caption(
                    "Quarter-final pairings (group winners vs. runners-up from a different group) and the "
                    "Finals Four bracket aren't drawn by UEFA until after the group stage — so, like the "
                    "European club competitions' pre-draw qualifying odds elsewhere on this site, each "
                    "simulation run draws its own representative pairing rather than assuming a fixed one. "
                    "**Reach QF** is exact (it's just each team's own chance of finishing top 2 in its "
                    "group); **Reach Finals Four** and **Win it all** are Monte Carlo estimates that also "
                    "sample which specific teams occupy 1st/2nd in each group, so read them as a guide to "
                    "the pecking order rather than precise percentages."
                )
                with st.spinner("Simulating the quarter-finals and Finals Four…"):
                    ko = simulate_league_a_knockouts(league_group_probs, ratings_df, n_sim=8_000)

                ko_rows = []
                for team, r in ko.iterrows():
                    ko_rows.append({
                        "Flag": _flag(team),
                        "Team": team,
                        "Reach QF": round(r["reached_qf"] * 100, 1),
                        "Reach Finals Four": round(r["reached_finals_four"] * 100, 1),
                        "Win it all": round(r["won_competition"] * 100, 1),
                    })
                ko_df = pd.DataFrame(ko_rows)
                ko_col_cfg = {
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "Reach QF": st.column_config.NumberColumn("Reach QF", format="%.1f%%", width="small"),
                    "Reach Finals Four": st.column_config.NumberColumn("Reach Finals Four", format="%.1f%%", width="small"),
                    "Win it all": st.column_config.NumberColumn("Win it all", format="%.1f%%", width="small"),
                }
                st.dataframe(
                    ko_df, column_config=ko_col_cfg, use_container_width=True,
                    hide_index=True, height=len(ko_df) * 35 + 38,
                )
