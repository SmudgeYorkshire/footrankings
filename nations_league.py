"""
2026-27 UEFA Nations League — group stage projections and League A's
predicted knockout bracket.

Groups are the real UEFA draw (see nations_league_data.py); ratings are
eloratings.net's current national-team Elo, scraped by
scrape_elo_ratings.py into ratings/nations_league_elo.csv. Real fixtures/
results come from API-Football (nations_league_fixtures.py) -- once a
match is played it locks in and only what's left to play gets simulated,
the same "real results + simulate the rest" approach used across the
rest of this site (see european.py's League Stage Predictions).
"""

import streamlit as st
import pandas as pd

from flags import flag_url
from nations_league_data import NL_GROUPS, NL_FLAG_ALIASES
from nations_league_simulator import load_nl_ratings, simulate_group, simulate_league_a_knockouts
from nations_league_fixtures import group_fixtures
from _split_season import compute_full_standings

st.title("🌍 UEFA Nations League 2026/27")
st.caption(
    "Group stage runs September-November 2026, using current national-team Elo ratings from "
    "[eloratings.net](https://eloratings.net/). Real results lock in as they're played — only "
    "the remaining fixtures are simulated."
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


def _render_table(standings: list[dict], height: int) -> None:
    rows = []
    for row in sorted(standings, key=lambda r: int(r.get("intRank", 99))):
        gd = int(row.get("intGoalDifference", 0))
        rows.append({
            "Rank": int(row.get("intRank", 0)),
            "Flag": _flag(row["strTeam"]),
            "Team": row["strTeam"],
            "P": int(row.get("intPlayed", 0)),
            "W": int(row.get("intWin", 0)),
            "D": int(row.get("intDraw", 0)),
            "L": int(row.get("intLoss", 0)),
            "GF": int(row.get("intGoalsFor", 0)),
            "GA": int(row.get("intGoalsAgainst", 0)),
            "GD": f"+{gd}" if gd > 0 else str(gd),
            "Pts": int(row.get("intPoints", 0)),
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.set_properties(subset=["Team"], **{"font-weight": "bold"}),
        column_config={
            "Rank": st.column_config.NumberColumn("#", width="small"),
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Team": st.column_config.TextColumn("Team", width="medium"),
        },
        use_container_width=True, hide_index=True, height=height,
    )


def _render_fixtures(played: list[dict], remaining: list[dict], height: int) -> None:
    if not played and not remaining:
        st.info("No fixtures found for this group yet.")
        return
    rows = []
    for f in sorted(played + remaining, key=lambda f: (f.get("dateEvent", ""), f.get("strTime", ""))):
        decided = f in played
        score = f"{f.get('intHomeScore', '')}–{f.get('intAwayScore', '')}" if decided else "—"
        rows.append({
            "Date": f.get("dateEvent", ""),
            "HB": _flag(f.get("strHomeTeam", "")),
            "Home": f.get("strHomeTeam", ""),
            "Score": score,
            "Away": f.get("strAwayTeam", ""),
            "AB": _flag(f.get("strAwayTeam", "")),
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.set_properties(subset=["Home", "Away"], **{"font-weight": "bold"}),
        column_config={
            "HB": st.column_config.ImageColumn("", width="small"),
            "AB": st.column_config.ImageColumn("", width="small"),
        },
        use_container_width=True, hide_index=True, height=height,
    )


def _render_predictions(teams: list[str], probs: pd.DataFrame, exp_pts: dict[str, float]) -> None:
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


def _manual_predictions_tab(group_key: str, teams: list[str], roster: list[dict],
                             played: list[dict], remaining: list[dict]) -> None:
    ver_key = f"nl_manual_ver_{group_key}"
    sim_key = f"nl_manual_sim_{group_key}"
    if ver_key not in st.session_state:
        st.session_state[ver_key] = 0

    if not remaining:
        st.info("All fixtures in this group have been played.")
        return

    fix_rows = []
    for f in remaining:
        fix_rows.append({
            "Date": f.get("dateEvent", ""),
            "HB": _flag(f.get("strHomeTeam", "")),
            "Home": f.get("strHomeTeam", ""),
            "HG": pd.NA, "AG": pd.NA,
            "Away": f.get("strAwayTeam", ""),
            "AB": _flag(f.get("strAwayTeam", "")),
        })
    fix_df = pd.DataFrame(fix_rows)
    fix_df["HG"] = fix_df["HG"].astype(pd.Int64Dtype())
    fix_df["AG"] = fix_df["AG"].astype(pd.Int64Dtype())

    editor_key = f"nl_editor_{group_key}_{st.session_state[ver_key]}"
    height = len(remaining) * 35 + 38

    hdr_col, btn_col, _ = st.columns([2, 1, 3], vertical_alignment="center")
    metric_ph = hdr_col.empty()
    clear_ph = btn_col.empty()
    edited_df = st.data_editor(
        fix_df,
        column_config={
            "HB": st.column_config.ImageColumn("", width="small"),
            "Home": st.column_config.TextColumn("Home", width="medium"),
            "HG": st.column_config.NumberColumn("HG", min_value=0, max_value=20, step=1, width="small"),
            "AG": st.column_config.NumberColumn("AG", min_value=0, max_value=20, step=1, width="small"),
            "Away": st.column_config.TextColumn("Away", width="medium"),
            "AB": st.column_config.ImageColumn("", width="small"),
        },
        disabled=["Date", "HB", "Home", "Away", "AB"],
        use_container_width=True, hide_index=True, height=height, key=editor_key,
    )

    filled_mask = edited_df[["HG", "AG"]].notna().all(axis=1)
    metric_ph.markdown(f"### Predicted: {int(filled_mask.sum())} / {len(remaining)}")
    if clear_ph.button("🗑 Clear", use_container_width=True, key=f"nl_clear_{group_key}"):
        st.session_state[ver_key] += 1
        st.session_state.pop(sim_key, None)
        st.rerun()

    fix_by_pair = {(f["strHomeTeam"], f["strAwayTeam"]): f for f in remaining}
    predicted_as_played = []
    for _, row in edited_df[filled_mask].iterrows():
        pair = (row["Home"], row["Away"])
        if pair in fix_by_pair:
            entry = dict(fix_by_pair[pair])
            entry["intHomeScore"] = int(row["HG"])
            entry["intAwayScore"] = int(row["AG"])
            entry["strStatus"] = "FT"
            predicted_as_played.append(entry)

    predicted_pairs = {(f["strHomeTeam"], f["strAwayTeam"]) for f in predicted_as_played}
    unpredicted = [f for f in remaining
                   if (f["strHomeTeam"], f["strAwayTeam"]) not in predicted_pairs]
    updated_standings = compute_full_standings(roster, played + predicted_as_played, tiebreakers=["gd", "gf"])

    st.divider()
    st.markdown("### Updated standings")
    _render_table(updated_standings, height=len(teams) * 35 + 38)

    fingerprint = (
        tuple(sorted((f["strHomeTeam"], f["strAwayTeam"], f["intHomeScore"], f["intAwayScore"])
                     for f in predicted_as_played)),
    )
    st.divider()
    st.markdown("### Projected final standings")
    cached = st.session_state.get(sim_key)
    if st.button("▶  Run simulations with predictions", type="primary",
                 use_container_width=True, key=f"nl_run_{group_key}"):
        with st.spinner("Simulating…"):
            probs, exp_pts = simulate_group(
                teams, ratings_df, n_sim=10_000,
                standings=updated_standings, remaining_fixtures=unpredicted,
                played_fixtures=played + predicted_as_played,
            )
        st.session_state[sim_key] = {"probs": probs, "exp_pts": exp_pts, "fingerprint": fingerprint}
        cached = st.session_state[sim_key]

    if cached:
        if cached["fingerprint"] != fingerprint:
            st.warning("⚠ Predictions changed since last run — press ▶ to update.")
        _render_predictions(teams, cached["probs"], cached["exp_pts"])
    else:
        st.info("Enter predictions above then press **▶ Run simulations**.")


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
                played, remaining = group_fixtures(teams)
                roster = [{"strTeam": t} for t in teams]
                real_standings = compute_full_standings(roster, played, tiebreakers=["gd", "gf"])

                sub_table, sub_pred, sub_manual = st.tabs(
                    ["📅 Table & Fixtures", "🎯 Predictions", "🔮 Manual Predictions"]
                )

                with sub_table:
                    st.markdown("#### Table")
                    _render_table(real_standings, height=len(teams) * 35 + 38)
                    st.markdown("#### Fixtures")
                    _render_fixtures(played, remaining, height=len(played + remaining) * 35 + 38)

                with sub_pred:
                    probs, exp_pts = simulate_group(
                        teams, ratings_df, n_sim=10_000,
                        standings=real_standings, remaining_fixtures=remaining, played_fixtures=played,
                    )
                    league_group_probs[group_name] = probs
                    _render_predictions(teams, probs, exp_pts)

                with sub_manual:
                    _manual_predictions_tab(f"{league_name}_{group_name}", teams, roster, played, remaining)

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
