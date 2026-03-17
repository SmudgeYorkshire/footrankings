"""
Football Rankings — public page.

Auto-refreshes data every 60 seconds. API key is read from the
environment only (not user-editable). Opta ratings are hidden.
"""

import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import LEAGUES, DEFAULT_N_SIMULATIONS, DEFAULT_HOME_ADVANTAGE, get_current_season
from data_fetcher import SportsDBClient
from simulator import simulate_season, fixture_odds
from ratings_manager import load_ratings, build_lookup
from _split_season import get_split_info, conference_fixtures

_API_KEY = os.getenv("THESPORTSDB_API_KEY", "3")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_CET = ZoneInfo("Europe/Berlin")

def _utc_to_cet(date_str: str, time_str: str) -> str:
    """Convert UTC date+time from TheSportsDB to CET/CEST. Returns 'HH:MM CET/CEST'."""
    if not date_str or not time_str or time_str.startswith("00:00"):
        return ""
    try:
        dt = datetime.strptime(f"{date_str} {time_str[:8]}", "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(_CET)
        return f"{dt.strftime('%H:%M')} CET"
    except ValueError:
        return time_str[:5]


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


def _clean_desc(desc: str) -> str:
    """Strip 'Promotion - ' prefix; keep 'Relegation - X' intact so the destination shows in red."""
    if desc.startswith("Promotion - "):
        return desc[len("Promotion - "):]
    return desc


def _zones_from_standings(standings: list[dict]) -> dict:
    """Build {label: [int positions]} from strDescription in standings rows."""
    pos_desc: dict[int, str] = {}
    for row in standings:
        rank = int(row.get("intRank", 0) or 0)
        desc = _clean_desc((row.get("strDescription") or "").strip())
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
    zone_df = pd.DataFrame(rows)
    st.dataframe(zone_df, use_container_width=True, hide_index=True,
                 height=len(zone_df) * 35 + 42)


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


def _apply_predictions(standings: list[dict], pred_fixtures: list[dict]) -> list[dict]:
    """Apply predicted results on top of standings. Returns updated standings list."""
    int_fields = ["intPlayed", "intWin", "intDraw", "intLoss",
                  "intGoalsFor", "intGoalsAgainst", "intGoalDifference", "intPoints"]
    updated = {}
    for row in standings:
        t = {k: v for k, v in row.items()}
        for field in int_fields:
            t[field] = int(t.get(field, 0) or 0)
        updated[t["strTeam"]] = t

    for f in pred_fixtures:
        home, away = f["strHomeTeam"], f["strAwayTeam"]
        hg, ag = int(f["pred_hg"]), int(f["pred_ag"])
        for team, gf, ga in [(home, hg, ag), (away, ag, hg)]:
            if team not in updated:
                continue
            t = updated[team]
            t["intPlayed"]         += 1
            t["intGoalsFor"]       += gf
            t["intGoalsAgainst"]   += ga
            t["intGoalDifference"] += gf - ga
            if gf > ga:
                t["intWin"]    += 1; t["intPoints"] += 3
            elif gf == ga:
                t["intDraw"]   += 1; t["intPoints"] += 1
            else:
                t["intLoss"]   += 1

    ranked = sorted(updated.values(),
                    key=lambda r: (-r["intPoints"], -r["intGoalDifference"], -r["intGoalsFor"]))
    for i, t in enumerate(ranked):
        t["intRank"] = i + 1
    return list(updated.values())


def render_prob_table(probs: pd.DataFrame, badge_lookup: dict = None, expected_pts: dict = None):
    """Color-coded finish-probability table, sorted by P(finish 1st) descending."""
    probs = probs.sort_values(probs.columns[0], ascending=False)
    df = (probs * 100).round(1)
    badge_lookup = badge_lookup or {}
    teams = list(probs.index)
    df.insert(0, "Team", teams)
    df.insert(0, "Badge", [badge_lookup.get(t, "") for t in teams])
    if expected_pts:
        df["xPts"] = [round(expected_pts.get(t, 0), 1) for t in teams]
    df.index = range(1, len(df) + 1)
    df.index.name = "Pos"
    pos_cols = [c for c in df.columns if c not in ("Badge", "Team", "xPts")]
    styled = (
        df.style
        .apply(_green_col, axis=0, subset=pos_cols)
        .format("{:.1f}%", subset=pos_cols)
        .set_properties(subset=["Team"], **{"font-weight": "bold"})
    )
    if expected_pts:
        styled = styled.format("{:.1f}", subset=["xPts"])
    col_cfg = {
        "Badge": st.column_config.ImageColumn("", width="small"),
        "Team":  st.column_config.TextColumn("Team"),
        "xPts":  st.column_config.NumberColumn("xPts", format="%.1f", width="small"),
    }
    st.markdown("#### Season finish probabilities")
    st.dataframe(styled, column_config=col_cfg, use_container_width=True,
                 height=len(probs) * 35 + 42)


# ---------------------------------------------------------------------------
# Sidebar — league selector and simulation settings
# ---------------------------------------------------------------------------

with st.sidebar:
    _auth = st.session_state.get("_authenticator")
    if _auth:
        st.caption(f"👤  {st.session_state.get('name', '')}")
        _auth.logout("Logout", location="sidebar")
    st.divider()
    league_name = st.selectbox(
        "European Leagues",
        options=list(LEAGUES.keys()),
        format_func=lambda n: n,
    )
    cfg = LEAGUES[league_name]
    league_id = cfg["id"]
    season = get_current_season(cfg["season_type"])
    st.divider()
    st.markdown(
        """
        <a href="https://x.com/FootRankings" target="_blank" style="
            display: inline-flex; align-items: center; gap: 8px;
            background: #000; color: #fff;
            padding: 8px 16px; border-radius: 20px;
            text-decoration: none; font-size: 14px; font-weight: 600;">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="white" viewBox="0 0 24 24">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747l7.73-8.835L1.254 2.25H8.08l4.253 5.622 5.911-5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            Follow @FootRankings
        </a>
        """,
        unsafe_allow_html=True,
    )

n_sim = DEFAULT_N_SIMULATIONS
home_advantage = DEFAULT_HOME_ADVANTAGE


# ---------------------------------------------------------------------------
# Data fetching — 60-second cache for live feel
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def fetch_all(lid, ssn, key):
    c = SportsDBClient(api_key=key)
    standings = c.get_standings(lid, ssn)
    played, remaining = c.get_fixtures(lid, ssn)
    info = c.get_league_info(lid)
    return standings, played, remaining, info


# ---------------------------------------------------------------------------
# Main content — auto-refreshes every 60 seconds
# ---------------------------------------------------------------------------
@st.fragment(run_every=60)
def main_content():
    with st.spinner("Loading…"):
        try:
            standings, played_fixtures, remaining_fixtures, league_info = fetch_all(
                league_id, season, _API_KEY
            )
        except RuntimeError as e:
            st.error(f"Failed to load data: {e}")
            return

    if not standings:
        st.warning(
            f"No standings found for **{league_name}** ({season}). "
            "Try a different season or check back later."
        )
        return

    ratings_df = load_ratings(league_id, standings)
    split_round = cfg.get("split_round")
    n_champ     = cfg.get("n_champ")
    pts_factor  = cfg.get("pts_factor", 1.0)
    split_info = get_split_info(standings, split_round, n_champ=n_champ, pts_factor=pts_factor) if split_round else None
    badge_lookup = {row["strTeam"]: row["strBadge"] for row in standings if row.get("strBadge")}

    # League header
    league_badge = league_info.get("strBadge") or league_info.get("strLogo")
    col_logo, col_title = st.columns([1, 9])
    with col_logo:
        if league_badge:
            st.image(league_badge, width=70)
    with col_title:
        _season_display = season.replace("-20", "/") if "-" in season else season
        _league_display = league_info.get("strLeague") or league_name
        st.markdown(f"## {_season_display} {_league_display}")
        total = len(played_fixtures) + len(remaining_fixtures)
        rounds_with_remaining = {f.get("intRound") for f in remaining_fixtures if f.get("intRound")}
        rounds_with_played = {f.get("intRound") for f in played_fixtures if f.get("intRound")}
        remaining_rounds = len(rounds_with_remaining)
        played_rounds = len(rounds_with_played - rounds_with_remaining)
        total_rounds = played_rounds + remaining_rounds
        st.caption(
            f"Rounds: **{total_rounds}** total · **{played_rounds}** played · **{remaining_rounds}** remaining  \n"
            f"Matches: **{total}** total · **{len(played_fixtures)}** played · **{len(remaining_fixtures)}** remaining"
        )

    st.divider()

    tab_table, tab_proj, tab_manual, tab_fixtures, tab_results, tab_format = st.tabs(
        ["📊 Current Table", "🎯 Predictions", "🔮 Manual Predictions", "📅 Fixtures", "📋 Results", "🗂️ Format"]
    )

    # ── Current Table ────────────────────────────────────────────────────────
    with tab_table:
        _form_sq = {"W": "🟩", "D": "⬜", "L": "🟥"}

        def _fmt_form(form: str) -> str:
            sq = [_form_sq.get(c, "") for c in (form or "")]
            if len(sq) >= 2:
                return "".join(sq[:-1]) + " │ " + sq[-1]
            return "".join(sq)

        def _table_rows(source_rows):
            rows = []
            for row in sorted(source_rows, key=lambda r: int(r.get("intRank", 99))):
                gd   = int(row.get("intGoalDifference", 0))
                form = row.get("strForm", "") or ""
                rows.append({
                    "Pos":    int(row.get("intRank", 0)),
                    "Badge":  row.get("strBadge") or "",
                    "Team":   row.get("strTeam", ""),
                    "P":      int(row.get("intPlayed", 0)),
                    "W":      int(row.get("intWin", 0)),
                    "D":      int(row.get("intDraw", 0)),
                    "L":      int(row.get("intLoss", 0)),
                    "GF":     int(row.get("intGoalsFor", 0)),
                    "GA":     int(row.get("intGoalsAgainst", 0)),
                    "GD":     f"+{gd}" if gd > 0 else str(gd),
                    "Pts":    int(row.get("intPoints", 0)),
                    "Form":   _fmt_form(form),
                    "Status": _clean_desc((row.get("strDescription") or "").strip()),
                })
            return rows

        def _status_style(val):
            s = str(val).lower()
            if "relega"           in s: return "color: #ea4335; font-weight: bold"
            if "champions league" in s: return "color: #1a73e8; font-weight: bold"
            if "europa league"    in s: return "color: #f9ab00; font-weight: bold"
            if "conference"       in s: return "color: #34a853; font-weight: bold"
            if "championship"     in s: return "color: #2e7d32; font-weight: bold"
            return ""

        def _render_table(rows):
            df = pd.DataFrame(rows)
            # Convert numeric cols to strings so TextColumn respects text-align: center
            for c in ["Pos", "P", "W", "D", "L", "GF", "GA", "Pts"]:
                df[c] = df[c].astype(str)
            num_cols = ["Pos", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"]
            styled = (
                df.style
                .hide(axis="index")
                .set_properties(subset=["Team", "Pts"], **{"font-weight": "bold"})
                .set_properties(subset=num_cols, **{"text-align": "center"})
                .map(_status_style, subset=["Status"])
            )
            col_cfg = {
                "Pos":    st.column_config.TextColumn("Pos",  width=32),
                "Badge":  st.column_config.ImageColumn("",    width=32),
                "Team":   st.column_config.TextColumn("Team", width=170),
                "P":      st.column_config.TextColumn("P",    width=28),
                "W":      st.column_config.TextColumn("W",    width=28),
                "D":      st.column_config.TextColumn("D",    width=28),
                "L":      st.column_config.TextColumn("L",    width=28),
                "GF":     st.column_config.TextColumn("GF",   width=32),
                "GA":     st.column_config.TextColumn("GA",   width=32),
                "GD":     st.column_config.TextColumn("GD",   width=35),
                "Pts":    st.column_config.TextColumn("Pts",  width=32),
                "Form":   st.column_config.TextColumn("Form", width=130),
                "Status": st.column_config.TextColumn("Status", width=220),
            }
            tbl_col, _ = st.columns([5, 1])
            with tbl_col:
                st.dataframe(styled, column_config=col_cfg, use_container_width=True,
                             hide_index=True, height=len(rows) * 35 + 38)

        _TB_LABELS = {
            "gd":           "Goal difference",
            "gf":           "Goals scored",
            "away_gf":      "Away goals scored",
            "h2h_pts":      "Head-to-head points",
            "h2h_gd":       "Head-to-head goal difference",
            "h2h_gf":       "Head-to-head goals scored",
            "h2h_away_gf":  "Head-to-head away goals scored",
        }

        if split_info:
            _pf = split_info.get("pts_factor", 1.0)
            if _pf == 0.0:
                _pts_note = "⚠️ Points reset to zero at split"
            elif _pf == 0.5:
                _pts_note = "⚠️ Points halved (rounded down) at split"
            else:
                _pts_note = "Points carried over in full"
            st.markdown("### 🏆 Championship Conference")
            st.caption(_pts_note)
            _render_table(_table_rows(split_info["champ_current"]))
            st.markdown("### ⚠️ Relegation Conference")
            st.caption(_pts_note)
            _render_table(_table_rows(split_info["relg_current"]))
            with st.expander("Regular Season Final Table"):
                _render_table(_table_rows(split_info["pre_split"]))
        else:
            _render_table(_table_rows(standings))

        tbs = cfg.get("tiebreakers", ["gd", "gf"])[:6]
        tb_text = "; ".join(f"{i+1}) {_TB_LABELS.get(r, r)}" for i, r in enumerate(tbs))
        st.caption(f"Tiebreakers: {tb_text}")

    # ── Projections ──────────────────────────────────────────────────────────
    with tab_proj:
        if not remaining_fixtures:
            st.info("The season is complete — no remaining fixtures to simulate.")
        elif split_info:
            champ_fix = conference_fixtures(remaining_fixtures, split_info["champ_teams"])
            relg_fix  = conference_fixtures(remaining_fixtures, split_info["relg_teams"])
            sim_key = (league_id, season, n_sim, home_advantage)
            if st.session_state.get("sim_key") != sim_key:
                with st.spinner(f"Running {n_sim:,} simulations…"):
                    _tiebreakers = cfg.get("tiebreakers")
                    probs_champ = simulate_season(
                        standings=split_info["champ_current"],
                        remaining_fixtures=champ_fix,
                        ratings=ratings_df,
                        n_sim=n_sim,
                        home_advantage=home_advantage,
                        tiebreakers=_tiebreakers,
                        played_fixtures=played_fixtures,
                    )
                    probs_relg = simulate_season(
                        standings=split_info["relg_current"],
                        remaining_fixtures=relg_fix,
                        ratings=ratings_df,
                        n_sim=n_sim,
                        home_advantage=home_advantage,
                        tiebreakers=_tiebreakers,
                        played_fixtures=played_fixtures,
                    )
                st.session_state["sim_results"] = (probs_champ, probs_relg)
                st.session_state["sim_key"] = sim_key

            if "sim_results" in st.session_state:
                probs_champ, probs_relg = st.session_state["sim_results"]
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
            sim_key = (league_id, season, n_sim, home_advantage)
            if st.session_state.get("sim_key") != sim_key:
                with st.spinner(f"Running {n_sim:,} simulations…"):
                    probs = simulate_season(
                        standings=standings,
                        remaining_fixtures=remaining_fixtures,
                        ratings=ratings_df,
                        n_sim=n_sim,
                        home_advantage=home_advantage,
                        tiebreakers=cfg.get("tiebreakers"),
                        played_fixtures=played_fixtures,
                    )
                st.session_state["sim_results"] = probs
                st.session_state["sim_key"] = sim_key

            if "sim_results" in st.session_state and not st.session_state["sim_results"].empty:
                exp_pts = _compute_expected_pts(standings, remaining_fixtures, ratings_df, home_advantage)
                render_prob_table(st.session_state["sim_results"], badge_lookup, exp_pts)
                render_zone_table(st.session_state["sim_results"], standings, cfg.get("zones"))

    # ── Manual Projections ────────────────────────────────────────────────────
    with tab_manual:
        if split_info:
            st.info(
                "Manual predictions for split-season leagues are not yet supported. "
                "Use the **Projections** tab for automated simulation."
            )
        elif not remaining_fixtures:
            st.info("The season is complete — no remaining fixtures to simulate.")
        else:
            pred_key  = f"manual_pred_{league_id}_{season}"
            ver_key   = f"manual_pred_ver_{league_id}_{season}"
            sim_store = f"manual_sim_{league_id}_{season}"

            if ver_key not in st.session_state:
                st.session_state[ver_key] = 0

            def _build_pred_df():
                rows = []
                for f in sorted(remaining_fixtures,
                                key=lambda x: (int(x.get("intRound", 0) or 0),
                                               x.get("dateEvent", ""),
                                               x.get("strTime", ""))):
                    rows.append({
                        "Rd":   int(f.get("intRound", 0) or 0),
                        "HB":   badge_lookup.get(f.get("strHomeTeam", ""), ""),
                        "Home": f.get("strHomeTeam", ""),
                        "HG":   pd.NA,
                        "AG":   pd.NA,
                        "Away": f.get("strAwayTeam", ""),
                        "AB":   badge_lookup.get(f.get("strAwayTeam", ""), ""),
                    })
                df = pd.DataFrame(rows)
                df["HG"] = df["HG"].astype(pd.Int64Dtype())
                df["AG"] = df["AG"].astype(pd.Int64Dtype())
                return df

            editor_key = f"pred_editor_{league_id}_{season}_{st.session_state[ver_key]}"
            base_df    = _build_pred_df()

            def _style_rounds(df):
                """Alternating row background per distinct round."""
                unique_rds = list(dict.fromkeys(df["Rd"].tolist()))
                rd_idx = {r: i for i, r in enumerate(unique_rds)}
                bg = ["", "background-color: #f0f4ff"]
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for row_i, rd in enumerate(df["Rd"].tolist()):
                    styles.iloc[row_i] = bg[rd_idx[rd] % 2]
                return styles

            # ── Shared height: both tables the same vertical size ─────────
            standings_height = len(standings) * 35 + 38

            # CSS: make the Clear button the same height as an H3 heading
            st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-secondary"] {
    height: 3rem !important;
    line-height: 1 !important;
}
</style>
""", unsafe_allow_html=True)

            # ── Side-by-side: fixture editor (left) + standings (right) ───
            col_editor, col_table = st.columns([5, 4])

            _pred_col_cfg = {
                "Rd":   st.column_config.NumberColumn("Rd",   width="small"),
                "HB":   st.column_config.ImageColumn("",      width="small"),
                "Home": st.column_config.TextColumn("Home",   width="medium"),
                "HG":   st.column_config.NumberColumn("HG",   min_value=0, max_value=20, step=1, width="small"),
                "AG":   st.column_config.NumberColumn("AG",   min_value=0, max_value=20, step=1, width="small"),
                "Away": st.column_config.TextColumn("Away",   width="medium"),
                "AB":   st.column_config.ImageColumn("",      width="small"),
            }
            styled_base = base_df.style.apply(_style_rounds, axis=None).set_properties(
                subset=["Home", "Away"], **{"font-weight": "bold"})

            with col_editor:
                hdr_col, btn_col, _ = st.columns([2, 1, 3], vertical_alignment="center")
                metric_ph = hdr_col.empty()
                clear_ph  = btn_col.empty()
                edited_df = st.data_editor(
                    styled_base,
                    column_config=_pred_col_cfg,
                    disabled=["Rd", "HB", "Home", "Away", "AB"],
                    use_container_width=True,
                    hide_index=True,
                    height=standings_height,
                    key=editor_key,
                )

            # Stats — fill placeholders after editor renders
            filled_mask = edited_df[["HG", "AG"]].notna().all(axis=1)
            n_filled    = int(filled_mask.sum())
            n_total     = len(remaining_fixtures)
            metric_ph.markdown(f"### Predicted: {n_filled} / {n_total}")
            if clear_ph.button("🗑 Clear", use_container_width=True):
                st.session_state[ver_key] += 1
                st.session_state.pop(sim_store, None)
                st.rerun()

            # Build applied predictions list
            fix_by_pair = {(f.get("strHomeTeam"), f.get("strAwayTeam")): f
                           for f in remaining_fixtures}
            pred_applied = []
            for _, row in edited_df[filled_mask].iterrows():
                pair = (row["Home"], row["Away"])
                if pair in fix_by_pair:
                    entry = dict(fix_by_pair[pair])
                    entry["pred_hg"] = int(row["HG"])
                    entry["pred_ag"] = int(row["AG"])
                    pred_applied.append(entry)

            predicted_pairs = {(f["strHomeTeam"], f["strAwayTeam"]) for f in pred_applied}
            unpredicted_fix = [f for f in remaining_fixtures
                               if (f.get("strHomeTeam"), f.get("strAwayTeam")) not in predicted_pairs]

            # Updated standings (live, no simulation)
            updated_st = _apply_predictions(standings, pred_applied)

            # ── Updated standings column ───────────────────────────────────
            with col_table:
                st.markdown("### Updated standings")
                orig_rank = {row["strTeam"]: int(row.get("intRank", 0)) for row in standings}
                upd_rows  = []
                for row in sorted(updated_st, key=lambda r: int(r.get("intRank", 99))):
                    new_rank = int(row.get("intRank", 0))
                    delta    = orig_rank.get(row["strTeam"], new_rank) - new_rank
                    gd       = int(row.get("intGoalDifference", 0))
                    upd_rows.append({
                        "Pos":   new_rank,
                        "Δ":     (f"▲{delta}" if delta > 0 else (f"▼{abs(delta)}" if delta < 0 else "—")),
                        "Badge": row.get("strBadge") or "",
                        "Team":  row.get("strTeam", ""),
                        "P":     int(row.get("intPlayed", 0)),
                        "GD":    f"+{gd}" if gd > 0 else str(gd),
                        "Pts":   int(row.get("intPoints", 0)),
                    })
                _upd_col_cfg = {
                    "Pos":   st.column_config.NumberColumn("Pos",  width="small"),
                    "Δ":     st.column_config.TextColumn("Δ",      width="small"),
                    "Badge": st.column_config.ImageColumn("",       width="small"),
                    "Team":  st.column_config.TextColumn("Team"),
                    "P":     st.column_config.NumberColumn("P",     width="small"),
                    "GD":    st.column_config.TextColumn("GD",      width="small"),
                    "Pts":   st.column_config.NumberColumn("Pts",   width="small"),
                }
                upd_df = pd.DataFrame(upd_rows)
                upd_styled = upd_df.style.set_properties(
                    subset=["Team", "Pts"], **{"font-weight": "bold"}
                ).set_properties(
                    **{"font-size": "12px", "padding": "2px 6px"}
                )

                st.dataframe(upd_styled, column_config=_upd_col_cfg,
                             use_container_width=True, hide_index=True,
                             height=standings_height)

            # Fingerprint for cache invalidation
            pred_fingerprint = (
                tuple(sorted((f["strHomeTeam"], f["strAwayTeam"], f["pred_hg"], f["pred_ag"])
                             for f in pred_applied)),
                n_sim, home_advantage,
            )

            st.divider()

            # ── Projected final standings (simulation) ─────────────────────
            st.markdown("### Projected final standings")
            cached = st.session_state.get(sim_store)

            run_btn = st.button(
                f"▶  Run {n_sim:,} simulations with predictions",
                type="primary",
                use_container_width=True,
            )
            if run_btn:
                with st.spinner(f"Running {n_sim:,} simulations…"):
                    manual_probs = simulate_season(
                        standings=updated_st,
                        remaining_fixtures=unpredicted_fix,
                        ratings=ratings_df,
                        n_sim=n_sim,
                        home_advantage=home_advantage,
                        tiebreakers=cfg.get("tiebreakers"),
                        played_fixtures=played_fixtures,
                    )
                st.session_state[sim_store] = {
                    "probs":       manual_probs,
                    "fingerprint": pred_fingerprint,
                }
                cached = st.session_state[sim_store]

            if cached:
                if cached["fingerprint"] != pred_fingerprint:
                    st.warning("⚠ Predictions changed since last run — press ▶ to update.")
                if not cached["probs"].empty:
                    manual_exp_pts = _compute_expected_pts(
                        updated_st, unpredicted_fix, ratings_df, home_advantage
                    )
                    render_prob_table(cached["probs"], badge_lookup, manual_exp_pts)
                    render_zone_table(cached["probs"], updated_st, cfg.get("zones"))
            else:
                st.info("Enter predictions above then press **▶ Run simulations**.")

    # ── Results ──────────────────────────────────────────────────────────────
    with tab_results:
        if not played_fixtures:
            st.info("No results available yet.")
        else:
            rounds: dict[int, list] = {}
            for f in sorted(played_fixtures, key=lambda x: (int(x.get("intRound", 0) or 0), x.get("dateEvent", ""), x.get("strTime", "")), reverse=True):
                rnd = int(f.get("intRound", 0) or 0)
                rounds.setdefault(rnd, []).append({
                    "Date":  f.get("dateEvent", ""),
                    "Time":  _utc_to_cet(f.get("dateEvent", ""), f.get("strTime", "")),
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
                _res_df = pd.DataFrame(rows).style.set_properties(
                    subset=["Home", "Away"], **{"font-weight": "bold"})
                st.dataframe(_res_df, column_config=_res_col_cfg,
                             use_container_width=False, hide_index=True)

    # ── Fixtures ─────────────────────────────────────────────────────────────
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
                    "Time": _utc_to_cet(f.get("dateEvent", ""), f.get("strTime", "")),
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
                _fix_df = pd.DataFrame(rows).style.set_properties(
                    subset=["Home", "Away"], **{"font-weight": "bold"})
                st.dataframe(_fix_df, column_config=_fix_col_cfg,
                             use_container_width=False, hide_index=True)

    # ── Format ───────────────────────────────────────────────────────────────
    with tab_format:
        _TB_LABELS_FMT = {
            "gd":           "Goal difference",
            "gf":           "Goals scored",
            "away_gf":      "Away goals scored",
            "h2h_pts":      "Head-to-head points",
            "h2h_gd":       "Head-to-head goal difference",
            "h2h_gf":       "Head-to-head goals scored",
            "h2h_away_gf":  "Head-to-head away goals scored",
        }

        # ── Season overview ──────────────────────────────────────────────────
        st.markdown("### 📅 Season Overview")
        all_dates = sorted([
            f.get("dateEvent") for f in (played_fixtures + remaining_fixtures)
            if f.get("dateEvent")
        ])
        season_start = all_dates[0]  if all_dates else "—"
        season_end   = all_dates[-1] if all_dates else "—"
        ov1, ov2, ov3, ov4 = st.columns(4)
        ov1.metric("Teams",        len(standings))
        ov2.metric("Total rounds", total_rounds)
        ov3.metric("Season start", season_start)
        ov4.metric("Season end",   season_end)

        st.divider()

        # ── Competition format ────────────────────────────────────────────────
        if True:
            st.markdown("### 🏟️ Competition Format")
            _sr    = cfg.get("split_round")
            _nchmp = cfg.get("n_champ")
            _nmid  = cfg.get("n_mid")
            _pf    = cfg.get("pts_factor", 1.0)
            _ntms  = len(standings) or _nchmp

            if not _sr:
                st.success("**Standard round-robin**")
                _times = round(total_rounds / (_ntms - 1)) if _ntms and _ntms > 1 and total_rounds else None
                _times_txt = {
                    2: "home and away once each (twice in total)",
                    3: "three times each",
                    4: "home and away twice each (four times in total)",
                    6: "six times each",
                }.get(_times, f"{_times} times each" if _times else "home and away")
                st.markdown(
                    f"All {_ntms} teams play each other {_times_txt} in a single table. "
                    "No post-season split or playoff groups."
                )
            else:
                _pts_label = {
                    1.0: "✅ Points carried over in full",
                    0.5: "⚠️ Points halved (rounded down) at split",
                    0.0: "🔄 Points reset to zero at split",
                }.get(_pf, f"pts × {_pf}")

                if _pf == 0.5:
                    st.warning("**Split-season format** — points halved at split")
                elif _pf == 0.0:
                    st.warning("**Split-season format** — points reset at split")
                else:
                    st.info("**Split-season format** — points carried over")

                _times_reg = round(_sr / (_ntms - 1)) if _ntms and _ntms > 1 and _sr else None
                _times_reg_txt = {
                    2: "home and away once each",
                    3: "three times each",
                    4: "home and away twice each",
                }.get(_times_reg, f"{_times_reg} times each" if _times_reg else "")
                st.markdown(f"**Regular season:** rounds 1 – {_sr}  ({_ntms} teams play each other {_times_reg_txt})")
                st.markdown("After the regular season, teams split into groups:")

                n_relg = (_ntms - (_nchmp or 0) - (_nmid or 0)) if _ntms and _nchmp else None
                group_cols = st.columns(3 if _nmid else 2)
                with group_cols[0]:
                    st.markdown(
                        f"<div style='background:#1a472a;padding:12px;border-radius:8px;"
                        f"text-align:center;color:white'><b>🏆 Championship</b><br>Top {_nchmp} teams<br>"
                        f"<small>{_pts_label}</small></div>",
                        unsafe_allow_html=True
                    )
                if _nmid:
                    with group_cols[1]:
                        st.markdown(
                            f"<div style='background:#1a3a5c;padding:12px;border-radius:8px;"
                            f"text-align:center;color:white'><b>🔵 Middle Group</b><br>{_nmid} teams<br>"
                            f"<small>{_pts_label}</small></div>",
                            unsafe_allow_html=True
                        )
                with group_cols[-1]:
                    if n_relg and n_relg > 0:
                        st.markdown(
                            f"<div style='background:#4a1a1a;padding:12px;border-radius:8px;"
                            f"text-align:center;color:white'><b>⚠️ Relegation</b><br>Bottom {n_relg} teams<br>"
                            f"<small>{_pts_label}</small></div>",
                            unsafe_allow_html=True
                        )

        st.divider()

        # ── League positions ─────────────────────────────────────────────────
        st.markdown("### 🎯 League Positions")
        _ZONE_ICONS = {
            "champions league":  "🏆",
            "champions":         "🏆",
            "europa league":     "🥈",
            "europa":            "🥈",
            "conference league": "🏅",
            "conference":        "🏅",
            "relegation":        "⬇️",
            "promotion":         "⬆️",
            "playoff":           "🔀",
        }
        raw_zones = cfg.get("zones") or _zones_from_standings(standings) or {}
        _zone_notes = cfg.get("zone_notes", {})
        if raw_zones:
            zone_rows = []
            notes_to_show = []
            for label, positions in sorted(raw_zones.items(), key=lambda x: min(x[1])):
                label_lower = label.lower()
                icon = next((v for k, v in _ZONE_ICONS.items() if k in label_lower), "📌")
                pos_sorted = sorted(positions)
                pos_str = (
                    str(pos_sorted[0]) if len(pos_sorted) == 1
                    else f"{pos_sorted[0]}–{pos_sorted[-1]}"
                )
                note = next((v for k, v in _zone_notes.items() if k in label_lower), None)
                has_note = "ℹ️" if note else ""
                zone_rows.append({"Pos.": pos_str, "Zone": f"{icon}  {label}", "": has_note})
                if note:
                    notes_to_show.append((f"{icon}  {label}", note))
            zone_df = pd.DataFrame(zone_rows)
            st.dataframe(zone_df, use_container_width=False, hide_index=True,
                         column_config={
                             "Pos.": st.column_config.TextColumn("Pos.", width=70),
                             "Zone": st.column_config.TextColumn("Zone", width=300),
                             "":     st.column_config.TextColumn("",     width=30),
                         })
            for zone_label, note_text in notes_to_show:
                st.markdown(
                    f"<div style='background:#1e2a3a;border-left:3px solid #4a9eda;"
                    f"padding:10px 14px;border-radius:4px;margin:6px 0;color:white'>"
                    f"<b>{zone_label}</b><br><small>{note_text}</small></div>",
                    unsafe_allow_html=True
                )
        else:
            st.caption("Zone information will appear here once the season begins.")

        st.divider()

        # ── Tiebreakers ───────────────────────────────────────────────────────
        st.markdown("### ⚖️ Tiebreakers")
        st.markdown("*Applied in order when clubs are level on points:*")
        for i, rule in enumerate(cfg.get("tiebreakers", ["gd", "gf"]), 1):
            st.markdown(f"**{i}.** {_TB_LABELS_FMT.get(rule, rule)}")


main_content()
