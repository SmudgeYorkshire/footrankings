"""
Admin page — full league view (with Opta) + user management.
Access restricted to role: admin via the entrypoint (app.py).
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import LEAGUES, DEFAULT_N_SIMULATIONS, DEFAULT_HOME_ADVANTAGE, get_current_season
from data_fetcher import SportsDBClient
from simulator import simulate_season, fixture_odds
from ratings_manager import load_ratings, save_ratings, build_lookup, _defaults_from_standings
from _split_season import get_split_info, conference_fixtures

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render_heatmap(probs: pd.DataFrame):
    n_teams = len(probs)
    z = probs.values
    text   = [[f"{v:.0%}" if v >= 0.005 else "" for v in row] for row in z]
    hover  = [[f"{v:.1%}" if v >= 0.005 else "<0.5%" for v in row] for row in z]
    cell   = 30          # px — keeps % readable; width = height per cell ≈ square
    l, r, t, b = 160, 90, 50, 50
    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"#{p}" for p in probs.columns],
        y=probs.index.tolist(),
        text=text,
        customdata=hover,
        texttemplate="%{text}",
        textfont={"size": 9},
        hovertemplate="<b>%{y}</b><br>Position %{x}<br>%{customdata}<extra></extra>",
        colorscale="Greens",
        zmin=0, zmax=1,
        showscale=True,
        colorbar=dict(title="Prob.", tickformat=".0%", thickness=12, len=0.8),
    ))
    fig.update_layout(
        title="Season finish probabilities",
        xaxis_title="Final league position",
        yaxis_title="",
        yaxis=dict(autorange="reversed"),
        width=l + n_teams * cell + r,
        height=t + n_teams * cell + b,
        margin=dict(l=l, r=r, t=t, b=b),
    )
    st.plotly_chart(fig, use_container_width=False)


def _zones_from_standings(standings: list[dict]) -> dict:
    """Build {label: [int positions]} from strDescription in standings rows."""
    pos_desc: dict[int, str] = {}
    for row in standings:
        rank = int(row.get("intRank", 0) or 0)
        desc = (row.get("strDescription") or "").strip()
        if rank and desc:
            pos_desc[rank] = desc
    if not pos_desc:
        return {}
    zones: dict[str, list[int]] = {}
    for pos in sorted(pos_desc):
        zones.setdefault(pos_desc[pos], []).append(pos)
    return zones


def render_zone_table(probs: pd.DataFrame, standings: list[dict] = None, zone_override: dict = None):
    """
    Zone probability table.
    Priority: zone_override (from config.py) → strDescription from standings → nothing.

    config.py override format (add to a league's dict):
        "zones": {
            "Champions League": [1, 2, 3, 4],
            "Europa League":    [5, 6],
            "Conference League":[7],
            "Relegation":       [18, 19, 20],
        }
    """
    raw_zones = zone_override or (standings and _zones_from_standings(standings)) or {}
    if not raw_zones:
        return

    # Build display labels with position ranges
    zones: dict[str, list[str]] = {}
    for label, positions in raw_zones.items():
        positions = sorted(positions)
        suffix = f"({positions[0]})" if len(positions) == 1 else f"({positions[0]}-{positions[-1]})"
        zones[f"{label} {suffix}"] = [str(p) for p in positions]

    st.markdown("#### Zone probabilities")
    rows = []
    for team in probs.index:
        row = {"Team": team}
        for zone_name, pos_strs in zones.items():
            cols = [p for p in pos_strs if p in probs.columns]
            row[zone_name] = f"{probs.loc[team, cols].sum():.1%}" if cols else "—"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _green_col(s: pd.Series) -> list[str]:
    """Return CSS background-color styles interpolated white→dark-green per column."""
    vmax = s.max()
    if vmax == 0:
        return [""] * len(s)
    styles = []
    for v in s:
        t = v / vmax
        r = int(255 * (1 - t))
        g = int(255 - t * 155)   # 255 → 100
        b = int(255 * (1 - t))
        text = "white" if t > 0.65 else "black"
        styles.append(f"background-color: rgb({r},{g},{b}); color: {text}")
    return styles


def _compute_expected_pts(standings, remaining_fixtures, ratings_df, home_advantage):
    """Return {team: expected_final_points} from current points + Poisson fixture odds."""
    current = {row["strTeam"]: int(row.get("intPoints", 0)) for row in standings}
    odds_list = fixture_odds(remaining_fixtures, ratings_df, home_advantage)
    exp = dict(current)
    for f, odds in zip(remaining_fixtures, odds_list):
        h, a = f.get("strHomeTeam", ""), f.get("strAwayTeam", "")
        if h in exp:
            exp[h] += 3 * odds["home_win"] + odds["draw"]
        if a in exp:
            exp[a] += 3 * odds["away_win"] + odds["draw"]
    return exp


def render_prob_table(probs: pd.DataFrame, badge_lookup: dict = None, expected_pts: dict = None):
    """Color-coded, sortable finish-probability table. Click any column to sort."""
    df = (probs * 100).round(1)
    df.index.name = "Team"
    badge_lookup = badge_lookup or {}
    df.insert(0, "Badge", [badge_lookup.get(t, "") for t in df.index])
    if expected_pts:
        df["xPts"] = [round(expected_pts.get(t, 0), 1) for t in probs.index]
    pos_cols = [c for c in df.columns if c not in ("Badge", "xPts")]
    styled = (
        df.style
        .apply(_green_col, axis=0, subset=pos_cols)
        .format("{:.1f}%", subset=pos_cols)
    )
    if expected_pts:
        styled = styled.format("{:.1f}", subset=["xPts"])
    col_cfg = {
        "Badge": st.column_config.ImageColumn("", width="small"),
        "xPts":  st.column_config.NumberColumn("xPts", format="%.1f", width="small"),
    }
    st.markdown("#### Season finish probabilities *(click any column header to sort)*")
    st.dataframe(styled, column_config=col_cfg, use_container_width=False,
                 height=len(probs) * 35 + 42)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.divider()
    api_key = st.text_input(
        "TheSportsDB API key",
        value=os.getenv("THESPORTSDB_API_KEY", "3"),
        type="password",
    )
    league_name = st.selectbox(
        "League",
        options=list(LEAGUES.keys()),
        format_func=lambda n: f"{LEAGUES[n]['flag']}  {n}",
    )
    cfg = LEAGUES[league_name]
    league_id = cfg["id"]
    season = get_current_season(cfg["season_type"])
    st.caption(f"Season: **{season}**")
    st.divider()
    n_sim = st.select_slider(
        "Simulations",
        options=[1_000, 5_000, 10_000, 50_000, 100_000],
        value=DEFAULT_N_SIMULATIONS,
    )
    home_advantage = st.slider(
        "Home advantage factor",
        min_value=1.00, max_value=1.50,
        value=DEFAULT_HOME_ADVANTAGE, step=0.01,
    )
    st.divider()
    if st.button("🔄 Refresh data", use_container_width=True):
        SportsDBClient(api_key=api_key).invalidate_cache(league_id, season)
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3_600, show_spinner=False)
def fetch_all(lid, ssn, key):
    c = SportsDBClient(api_key=key)
    standings = c.get_standings(lid, ssn)
    played, remaining = c.get_fixtures(lid, ssn)
    info = c.get_league_info(lid)
    return standings, played, remaining, info


with st.spinner("Loading data…"):
    try:
        standings, played_fixtures, remaining_fixtures, league_info = fetch_all(
            league_id, season, api_key
        )
    except RuntimeError as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

if not standings:
    st.warning(
        f"No standings found for **{league_name}** ({season}). "
        "Try a different season or check your API key."
    )
    st.stop()

ratings_df = load_ratings(league_id, standings)
split_round = cfg.get("split_round")
split_info = get_split_info(standings, split_round) if split_round else None
badge_lookup = {row["strTeam"]: row["strBadge"] for row in standings if row.get("strBadge")}

# ---------------------------------------------------------------------------
# League header
# ---------------------------------------------------------------------------
league_badge = league_info.get("strBadge") or league_info.get("strLogo")
col_logo, col_title = st.columns([1, 9])
with col_logo:
    if league_badge:
        st.image(league_badge, width=70)
with col_title:
    st.markdown(f"## {cfg['flag']}  {league_name}  —  {season}")
    total = len(played_fixtures) + len(remaining_fixtures)
    rounds_with_remaining = {f.get("intRound") for f in remaining_fixtures if f.get("intRound")}
    rounds_with_played = {f.get("intRound") for f in played_fixtures if f.get("intRound")}
    remaining_rounds = len(rounds_with_remaining)
    played_rounds = len(rounds_with_played - rounds_with_remaining)
    total_rounds = played_rounds + remaining_rounds
    st.caption(
        f"Rounds: **{played_rounds}** played · **{remaining_rounds}** remaining · **{total_rounds}** total  |  "
        f"Matches: **{len(played_fixtures)}** played · **{len(remaining_fixtures)}** remaining · **{total}** total"
    )

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_table, tab_proj, tab_results, tab_fixtures, tab_ratings, tab_users = st.tabs(
    ["📊 Current Table", "🎯 Projections", "📋 Results", "📅 Fixtures",
     "⚙️ Team Ratings", "👥 Users"]
)

# ── Current Table ─────────────────────────────────────────────────────────────
with tab_table:
    opta_lookup = build_lookup(ratings_df) if not ratings_df.empty else {}

    def _admin_table_rows(source_rows):
        rows = []
        for row in sorted(source_rows, key=lambda r: int(r.get("intRank", 99))):
            team_name = row.get("strTeam", "")
            rows.append({
                "Pos":    int(row.get("intRank", 0)),
                "Badge":  row.get("strBadge") or "",
                "Team":   team_name,
                "Opta ★": opta_lookup.get(team_name),
                "P":      int(row.get("intPlayed", 0)),
                "W":      int(row.get("intWin", 0)),
                "D":      int(row.get("intDraw", 0)),
                "L":      int(row.get("intLoss", 0)),
                "GF":     int(row.get("intGoalsFor", 0)),
                "GA":     int(row.get("intGoalsAgainst", 0)),
                "GD":     int(row.get("intGoalDifference", 0)),
                "Pts":    int(row.get("intPoints", 0)),
                "Form":   row.get("strForm", ""),
                "Status": row.get("strDescription", ""),
            })
        return rows

    _admin_col_cfg = {
        "Badge":  st.column_config.ImageColumn("",       width="small"),
        "Pos":    st.column_config.NumberColumn("Pos",   width="small"),
        "Team":   st.column_config.TextColumn("Team",    width="medium"),
        "Opta ★": st.column_config.NumberColumn("Opta ★", format="%.1f", width="small"),
        "P":      st.column_config.NumberColumn("P",     width="small"),
        "W":      st.column_config.NumberColumn("W",     width="small"),
        "D":      st.column_config.NumberColumn("D",     width="small"),
        "L":      st.column_config.NumberColumn("L",     width="small"),
        "GF":     st.column_config.NumberColumn("GF",    width="small"),
        "GA":     st.column_config.NumberColumn("GA",    width="small"),
        "GD":     st.column_config.NumberColumn("GD",    width="small"),
        "Pts":    st.column_config.NumberColumn("Pts",   width="small"),
        "Form":   st.column_config.TextColumn("Form",    width="medium"),
        "Status": st.column_config.TextColumn("Status",  width="medium"),
    }

    def _df_height(n):
        return n * 35 + 42

    if split_info:
        st.markdown("### Championship Conference")
        champ_rows = _admin_table_rows(split_info["champ_current"])
        st.dataframe(pd.DataFrame(champ_rows), column_config=_admin_col_cfg,
                     use_container_width=False, hide_index=True,
                     height=_df_height(len(champ_rows)))
        st.markdown("### Relegation Conference")
        relg_rows = _admin_table_rows(split_info["relg_current"])
        st.dataframe(pd.DataFrame(relg_rows), column_config=_admin_col_cfg,
                     use_container_width=False, hide_index=True,
                     height=_df_height(len(relg_rows)))
        with st.expander("Regular Season Final Table"):
            pre_rows = _admin_table_rows(split_info["pre_split"])
            st.dataframe(pd.DataFrame(pre_rows), column_config=_admin_col_cfg,
                         use_container_width=False, hide_index=True,
                         height=_df_height(len(pre_rows)))
    else:
        all_rows = _admin_table_rows(standings)
        st.dataframe(
            pd.DataFrame(all_rows),
            column_config=_admin_col_cfg,
            use_container_width=False,
            hide_index=True,
            height=_df_height(len(all_rows)),
        )

# ── Projections ───────────────────────────────────────────────────────────────
with tab_proj:
    if not remaining_fixtures:
        st.info("The season is complete — no remaining fixtures to simulate.")
    elif split_info:
        champ_fix = conference_fixtures(remaining_fixtures, split_info["champ_teams"])
        relg_fix  = conference_fixtures(remaining_fixtures, split_info["relg_teams"])
        sim_key = (league_id, season, n_sim, home_advantage)
        run_sim = st.button(
            f"▶  Run {n_sim:,} simulations",
            type="primary",
            use_container_width=True,
        )
        if run_sim or st.session_state.get("admin_sim_key") != sim_key:
            with st.spinner(f"Running {n_sim:,} simulations…"):
                probs_champ = simulate_season(
                    standings=split_info["champ_current"],
                    remaining_fixtures=champ_fix,
                    ratings=ratings_df,
                    n_sim=n_sim,
                    home_advantage=home_advantage,
                )
                probs_relg = simulate_season(
                    standings=split_info["relg_current"],
                    remaining_fixtures=relg_fix,
                    ratings=ratings_df,
                    n_sim=n_sim,
                    home_advantage=home_advantage,
                )
            st.session_state["admin_sim_results"] = (probs_champ, probs_relg)
            st.session_state["admin_sim_key"] = sim_key

        if "admin_sim_results" in st.session_state:
            probs_champ, probs_relg = st.session_state["admin_sim_results"]
            champ_exp_pts = _compute_expected_pts(split_info["champ_current"], champ_fix, ratings_df, home_advantage)
            relg_exp_pts  = _compute_expected_pts(split_info["relg_current"],  relg_fix,  ratings_df, home_advantage)
            st.markdown("### Championship Conference")
            if not probs_champ.empty:
                render_prob_table(probs_champ, badge_lookup, champ_exp_pts)
                render_zone_table(probs_champ, split_info["champ_current"], cfg.get("zones"))
            st.markdown("### Relegation Conference")
            if not probs_relg.empty:
                render_prob_table(probs_relg, badge_lookup, relg_exp_pts)
                render_zone_table(probs_relg, split_info["relg_current"], cfg.get("zones"))
        else:
            st.info("Press **▶ Run simulations** to generate projections.")
    else:
        sim_key = (league_id, season, n_sim, home_advantage)
        run_sim = st.button(
            f"▶  Run {n_sim:,} simulations",
            type="primary",
            use_container_width=True,
        )
        if run_sim or st.session_state.get("admin_sim_key") != sim_key:
            with st.spinner(f"Running {n_sim:,} simulations…"):
                probs = simulate_season(
                    standings=standings,
                    remaining_fixtures=remaining_fixtures,
                    ratings=ratings_df,
                    n_sim=n_sim,
                    home_advantage=home_advantage,
                )
            st.session_state["admin_sim_results"] = probs
            st.session_state["admin_sim_key"] = sim_key

        if "admin_sim_results" in st.session_state and not st.session_state["admin_sim_results"].empty:
            exp_pts = _compute_expected_pts(standings, remaining_fixtures, ratings_df, home_advantage)
            render_prob_table(st.session_state["admin_sim_results"], badge_lookup, exp_pts)
            render_zone_table(st.session_state["admin_sim_results"], standings, cfg.get("zones"))
        elif "admin_sim_results" not in st.session_state:
            st.info("Press **▶ Run simulations** to generate projections.")

# ── Results ───────────────────────────────────────────────────────────────────
with tab_results:
    if not played_fixtures:
        st.info("No results available yet.")
    else:
        rounds: dict[int, list] = {}
        for f in sorted(played_fixtures, key=lambda x: (int(x.get("intRound", 0) or 0), x.get("dateEvent", ""), x.get("strTime", "")), reverse=True):
            rnd = int(f.get("intRound", 0) or 0)
            rounds.setdefault(rnd, []).append({
                "Date":  f.get("dateEvent", ""),
                "Time":  f.get("strTime", "")[:5],
                "HB":    badge_lookup.get(f.get("strHomeTeam", ""), ""),
                "Home":  f.get("strHomeTeam", ""),
                "Score": f"{f.get('intHomeScore', '')} – {f.get('intAwayScore', '')}",
                "Away":  f.get("strAwayTeam", ""),
                "AB":    badge_lookup.get(f.get("strAwayTeam", ""), ""),
            })
        _res_col_cfg = {
            "Date":  st.column_config.TextColumn("Date",  width=110),
            "Time":  st.column_config.TextColumn("Time",  width="small"),
            "HB":    st.column_config.ImageColumn("",     width="small"),
            "Home":  st.column_config.TextColumn("Home",  width="medium"),
            "Score": st.column_config.TextColumn("Score", width="small"),
            "Away":  st.column_config.TextColumn("Away",  width="medium"),
            "AB":    st.column_config.ImageColumn("",     width="small"),
        }
        for rnd, rows in rounds.items():
            st.markdown(f"**Round {rnd}**")
            st.dataframe(pd.DataFrame(rows), column_config=_res_col_cfg,
                         use_container_width=False, hide_index=True)

# ── Fixtures ──────────────────────────────────────────────────────────────────
with tab_fixtures:
    if not remaining_fixtures:
        st.info("No upcoming fixtures — the season may be complete.")
    else:
        odds_list = fixture_odds(remaining_fixtures, ratings_df, home_advantage)
        rounds: dict[int, list] = {}
        for f, odds in sorted(
            zip(remaining_fixtures, odds_list),
            key=lambda x: (int(x[0].get("intRound", 0) or 0), x[0].get("dateEvent", ""), x[0].get("strTime", "")),
        ):
            rnd = int(f.get("intRound", 0) or 0)
            rounds.setdefault(rnd, []).append({
                "Date": f.get("dateEvent", ""),
                "Time": f.get("strTime", "")[:5],
                "HB":   badge_lookup.get(f.get("strHomeTeam", ""), ""),
                "Home": f.get("strHomeTeam", ""),
                "H%":   f"{odds['home_win']:.0%}",
                "D%":   f"{odds['draw']:.0%}",
                "A%":   f"{odds['away_win']:.0%}",
                "Away": f.get("strAwayTeam", ""),
                "AB":   badge_lookup.get(f.get("strAwayTeam", ""), ""),
            })
        _fix_col_cfg = {
            "Date": st.column_config.TextColumn("Date",  width=110),
            "Time": st.column_config.TextColumn("Time",  width="small"),
            "HB":   st.column_config.ImageColumn("",     width="small"),
            "Home": st.column_config.TextColumn("Home",  width="medium"),
            "H%":   st.column_config.TextColumn("H%",   width="small"),
            "D%":   st.column_config.TextColumn("D%",   width="small"),
            "A%":   st.column_config.TextColumn("A%",   width="small"),
            "Away": st.column_config.TextColumn("Away",  width="medium"),
            "AB":   st.column_config.ImageColumn("",     width="small"),
        }
        for rnd, rows in rounds.items():
            st.markdown(f"**Round {rnd}**")
            st.dataframe(pd.DataFrame(rows), column_config=_fix_col_cfg,
                         use_container_width=False, hide_index=True)

# ── Team Ratings ──────────────────────────────────────────────────────────────
with tab_ratings:
    st.markdown(
        "Enter the **Opta Power Ranking** (0–100 scale) for each team. "
        "Higher rating = stronger attack and tighter defense."
    )
    edited = st.data_editor(
        ratings_df,
        column_config={
            "team":        st.column_config.TextColumn("Opta Name", disabled=True, width="large"),
            "alias":       st.column_config.TextColumn("TheSportsDB Name (if different)", width="large"),
            "opta_rating": st.column_config.NumberColumn(
                "Opta Rating ★", min_value=0.0, max_value=100.0, step=0.1, format="%.1f"
            ),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
    )
    col_save, col_reset = st.columns(2)
    with col_save:
        if st.button("💾 Save ratings", use_container_width=True):
            save_ratings(league_id, edited)
            ratings_df = edited
            st.session_state.pop("admin_sim_results", None)
            st.success("Ratings saved. Re-run the simulation to update projections.")
    with col_reset:
        if st.button("↺ Reset to estimated ratings", use_container_width=True):
            csv_path = Path("ratings") / f"{league_id}.csv"
            ratings_df = _defaults_from_standings(standings, csv_path)
            st.session_state.pop("admin_sim_results", None)
            st.rerun()

# ── Users ─────────────────────────────────────────────────────────────────────
with tab_users:
    with open("auth.yaml", encoding="utf-8") as f:
        auth_data = yaml.safe_load(f)

    users = auth_data.get("credentials", {}).get("usernames", {})
    user_rows = [
        {
            "Username": uname,
            "Name":     udata.get("name", ""),
            "Email":    udata.get("email", ""),
            "Role":     udata.get("role", "user"),
        }
        for uname, udata in users.items()
    ]
    st.dataframe(pd.DataFrame(user_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown(
        """
        **To add a subscriber**, open `auth.yaml` and add an entry under `credentials.usernames`:
        ```yaml
        newuser:
          email: their@email.com
          name: Their Name
          password: their_password
          role: user
        ```
        The password is auto-hashed by bcrypt on first login.
        """
    )
