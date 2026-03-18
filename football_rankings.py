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
from simulator import simulate_season, fixture_odds, simulate_final_four
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
    """Normalise strDescription: strip tier/league name prefixes, shorten relegation labels."""
    if desc.startswith("Promotion - "):
        return desc[len("Promotion - "):]
    dl = desc.lower()
    if "relegation play-off" in dl or "relegation playoff" in dl:
        return "Relegation - PO"
    if dl.startswith("relegation"):
        return "Relegation"
    # Strip "League Name (Round Type)" pattern — e.g. "Jupiler Pro League (Relegation round)"
    if " (" in desc and desc.endswith(")"):
        inner = desc[desc.rfind(" (") + 2:-1]
        if "relegation" in inner.lower():
            return "Relegation"
        return ""   # championship/conference round — let euro_spots or zones handle it
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
            row[zone_name] = round(probs.loc[team, cols].sum() * 100, 1) if cols else None
        rows.append(row)
    zone_df = pd.DataFrame(rows)
    # Sort by first zone column descending by default
    first_zone = next(iter(zones), None)
    if first_zone and first_zone in zone_df.columns:
        zone_df = zone_df.sort_values(first_zone, ascending=False).reset_index(drop=True)
    col_cfg = {"Team": st.column_config.TextColumn("Team")}
    for zn in zones:
        col_cfg[zn] = st.column_config.NumberColumn(zn, format="%.1f%%")
    st.dataframe(zone_df, column_config=col_cfg, use_container_width=True, hide_index=True,
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


def _playoff_standings(teams: list, standings_lookup: dict, pts_factor: float) -> list:
    """Mock standings for a play-off group: points adjusted by pts_factor, goals zeroed."""
    rows = []
    for i, team in enumerate(teams, 1):
        orig = standings_lookup.get(team, {})
        pts  = int(orig.get("intPoints", 0) or 0)
        rows.append({
            "strTeam":           team,
            "intPoints":         int(pts * pts_factor),
            "intPlayed":         0,
            "intWin":            0,
            "intDraw":           0,
            "intLoss":           0,
            "intGoalsFor":       0,
            "intGoalsAgainst":   0,
            "intGoalDifference": 0,
            "intRank":           i,
            "strBadge":          orig.get("strBadge", ""),
        })
    return rows


def _roundrobin_fixtures(teams: list) -> list:
    """Generate home+away round-robin fixtures for a list of teams."""
    return [
        {"strHomeTeam": h, "strAwayTeam": a}
        for h in teams for a in teams if h != a
    ]


def _euro_style_cell(val):
    s = str(val).upper()
    if "UCL"  in s: return "color: #1a73e8; font-weight: bold"
    if "UEL"  in s: return "color: #f9ab00; font-weight: bold"
    if "UECL" in s: return "color: #34a853; font-weight: bold"
    return ""


def _status_style_pred(val):
    """Red for relegation labels in the predicted-standings Status column."""
    s = str(val).lower()
    if "relega" in s: return "color: #ea4335; font-weight: bold"
    return ""


def _status_for_pos(pos: int, euro_spots: dict, zones: dict = None) -> str:
    """Return the status label for a predicted finishing position."""
    if euro_spots:
        label = euro_spots.get(pos, "")
        if label:
            return label
    if zones:
        for zone_label, positions in zones.items():
            if pos in positions:
                return zone_label
    return ""


def render_prob_table(probs: pd.DataFrame, badge_lookup: dict = None,
                      expected_pts: dict = None, european_spots: dict = None,
                      title: str = "Season finish probabilities", zones: dict = None):
    """Color-coded finish-probability table, sorted by xPts descending."""
    if expected_pts:
        sorted_teams = sorted(probs.index, key=lambda t: expected_pts.get(t, 0), reverse=True)
        probs = probs.loc[sorted_teams]
    else:
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
    if european_spots or zones:
        df["Status"] = [_status_for_pos(pos, european_spots or {}, zones) for pos in df.index]
    non_pos = {"Badge", "Team", "xPts", "Status"}
    pos_cols = [c for c in df.columns if c not in non_pos]
    styled = (
        df.style
        .apply(_green_col, axis=0, subset=pos_cols)
        .format("{:.1f}%", subset=pos_cols)
        .set_properties(subset=["Team"], **{"font-weight": "bold"})
    )
    if expected_pts:
        styled = styled.format("{:.1f}", subset=["xPts"])
    if "Status" in df.columns:
        styled = (styled
                  .map(_euro_style_cell,  subset=["Status"])
                  .map(_status_style_pred, subset=["Status"]))
    col_cfg = {
        "Badge":  st.column_config.ImageColumn("", width="small"),
        "Team":   st.column_config.TextColumn("Team"),
        "xPts":   st.column_config.NumberColumn("xPts", format="%.1f", width="small"),
        "Status": st.column_config.TextColumn("Status", width=110),
    }
    st.markdown(f"#### {title}")
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
        options=[_UCL_VIEW] + list(LEAGUES.keys()),
        format_func=lambda n: n,
    )
    if league_name in LEAGUES:
        cfg = LEAGUES[league_name]
        league_id = cfg["id"]
        season = get_current_season(cfg["season_type"])
    else:
        cfg = {}
        league_id = None
        season = None
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
_UCL_VIEW = "🏆 2026/27 UEFA Champions League"


# ---------------------------------------------------------------------------
# UCL QR1 qualifier coefficients (UEFA 5-year, 2025/26 cycle)
# ---------------------------------------------------------------------------
_UCL_QR1_COEFFS: dict[str, float] = {
    "Slovenian 1. SNL":             21.000,
    "Moldovan National Division":   20.000,
    "Irish Premier Division":       19.375,
    "Finnish Veikkausliiga":        14.000,
    "Kosovan Superleague":          13.625,
    "Gibraltar National League":    13.500,
    "Bosnian Premier Liga":         13.125,
    "Icelandic Úrvalsdeild":        11.750,
    "Kazakhstan Premier League":    11.000,
    "Latvian Higher League":        10.500,
    "Faroe Islands Premier League": 10.500,
    "Estonian Meistriliiga":        10.000,
    "Northern Irish Premiership":    9.000,
    "Welsh Premier League":          9.000,
    "Maltese Premier League":        8.500,
    "Andorran Primera Divisió":      7.500,
    "Bulgarian First League":        7.000,
    "Armenian Premier League":       7.000,
    "Albanian Superliga":            6.500,
    "Luxembourgish National Div":    6.500,
    "Azerbaijani Premier League":    6.000,
    "Lithuanian A Lyga":             6.000,
    "Montenegrin First League":      6.000,
    "Romanian Liga I":               5.050,
    "Georgian Erovnuli Liga":        5.000,
    "San Marino Campionato":         2.500,
    "Macedonian First League":       1.551,
    "Belarus Vyscha Liga":           1.325,
}


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


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_leader(lid, ssn, key):
    """Return the current league leader row (position 1 in standings)."""
    c = SportsDBClient(api_key=key)
    standings = c.get_standings(lid, ssn)
    if standings:
        return min(standings, key=lambda r: int(r.get("intRank") or 99))
    return None


# ---------------------------------------------------------------------------
# 2026/27 UCL qualifying rounds view
# ---------------------------------------------------------------------------
def _render_ucl_qualifying():
    from datetime import datetime
    st.markdown("## 🏆 2026/27 UEFA Champions League")
    st.markdown("### First Qualifying Round")
    st.caption("1st leg: 7/8 Jul 2026 · 2nd leg: 14/15 Jul 2026")
    rows = []
    with st.spinner("Loading…"):
        for lname, coeff in sorted(_UCL_QR1_COEFFS.items(), key=lambda x: x[1], reverse=True):
            lcfg = LEAGUES.get(lname)
            if not lcfg:
                continue
            is_summer = lcfg["season_type"] == "summer"
            # Summer: fetch confirmed 2025 champion; Winter: fetch current projected leader
            ssn    = "2025" if is_summer else get_current_season("winter")
            leader = fetch_leader(lcfg["id"], ssn, _API_KEY)
            # Determine confirmed vs projected
            if is_summer:
                status = "✅ Confirmed"
            else:
                season_end_str = lcfg.get("season_end", "")
                try:
                    confirmed = datetime.now() > datetime.strptime(season_end_str, "%d %B %Y")
                except (ValueError, TypeError):
                    confirmed = False
                status = "✅ Confirmed" if confirmed else "🔮 Projected"
            route = "Final Four winner" if lcfg.get("final_four") else "League 1st"
            rows.append({
                "Badge":   leader.get("strBadge", "") if leader else "",
                "Club":    leader.get("strTeam", "—") if leader else "—",
                "Country": f"{lcfg.get('flag', '')} {lcfg.get('country', '')}",
                "Route":   route,
                "Coeff.":  coeff,
                "Status":  status,
            })
    df_ucl = pd.DataFrame(rows)
    df_ucl.index = range(1, len(df_ucl) + 1)
    df_ucl.index.name = "#"

    def _status_style_ucl(val):
        s = str(val)
        if "Confirmed" in s: return "color: #34a853; font-weight: bold"
        if "Projected" in s: return "color: #f9ab00; font-weight: bold"
        return ""

    styled = df_ucl.style.map(_status_style_ucl, subset=["Status"])
    st.dataframe(
        styled,
        column_config={
            "Badge":   st.column_config.ImageColumn("",        width="small"),
            "Club":    st.column_config.TextColumn("Club",     width=180),
            "Country": st.column_config.TextColumn("Country",  width=130),
            "Route":   st.column_config.TextColumn("Route",    width=130),
            "Coeff.":  st.column_config.NumberColumn("Coeff.", format="%.3f", width=70),
            "Status":  st.column_config.TextColumn("Status",   width=120),
        },
        use_container_width=False,
        height=len(rows) * 35 + 42,
    )


# ---------------------------------------------------------------------------
# Main content — auto-refreshes every 60 seconds
# ---------------------------------------------------------------------------
@st.fragment(run_every=60)
def main_content():
    if league_name == _UCL_VIEW:
        _render_ucl_qualifying()
        return
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

    # European spots lookup — shared across all tabs
    _euro_spots: dict[int, str] = cfg.get("european_spots", {})

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

        def _euro_label(pos: int) -> str:
            return _euro_spots.get(pos, "")

        def _table_rows(source_rows, show_euro=True):
            rows = []
            for row in sorted(source_rows, key=lambda r: int(r.get("intRank", 99))):
                gd   = int(row.get("intGoalDifference", 0))
                form = row.get("strForm", "") or ""
                pos  = int(row.get("intRank", 0))
                euro = _euro_label(pos) if show_euro else ""
                _zones_cfg = cfg.get("zones", {})
                zone_lbl = next((lbl for lbl, ps in _zones_cfg.items() if pos in ps), "")
                api_status = _clean_desc((row.get("strDescription") or "").strip())
                # Priority: euro label → zones config → API description
                status = euro if euro else zone_lbl if zone_lbl else api_status
                rows.append({
                    "Pos":    pos,
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
                    "Status": status,
                })
            return rows

        def _status_style(val):
            s = str(val).lower()
            if "relega"           in s: return "color: #ea4335; font-weight: bold"
            if "champions league" in s: return "color: #1a73e8; font-weight: bold"
            if "europa league"    in s: return "color: #f9ab00; font-weight: bold"
            if "conference"       in s: return "color: #34a853; font-weight: bold"
            if "final four"       in s: return "color: #2e7d32; font-weight: bold"
            if "championship"     in s: return "color: #2e7d32; font-weight: bold"
            return ""

        def _europe_style(val):
            s = str(val).upper()
            if "UCL"  in s: return "color: #1a73e8; font-weight: bold"
            if "UEL"  in s: return "color: #f9ab00; font-weight: bold"
            if "UECL" in s: return "color: #34a853; font-weight: bold"
            return ""

        def _render_table(rows):
            df = pd.DataFrame(rows)
            # Convert numeric cols to strings so TextColumn respects text-align: center
            for c in ["Pos", "P", "W", "D", "L", "GF", "GA", "Pts"]:
                df[c] = df[c].astype(str)
            num_cols = ["Pos", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"]
            style_obj = (
                df.style
                .hide(axis="index")
                .set_properties(subset=["Team", "Pts"], **{"font-weight": "bold"})
                .set_properties(subset=num_cols, **{"text-align": "center"})
                .map(_status_style, subset=["Status"])
                .map(_europe_style, subset=["Status"])
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
                "Status": st.column_config.TextColumn("Status", width=130),
            }
            tbl_col, _ = st.columns([5, 1])
            with tbl_col:
                st.dataframe(style_obj, column_config=col_cfg, use_container_width=True,
                             hide_index=True, height=len(rows) * 35 + 38)

        _TB_LABELS = {
            "gd":                     "Goal difference",
            "gf":                     "Goals scored",
            "away_gf":                "Away goals scored",
            "away_wins":              "Away matches won",
            "wins":                   "Matches won",
            "less_losses":            "Fewer losses",
            "h2h_pts":                "Head-to-head points",
            "h2h_gd":                 "Head-to-head goal difference",
            "h2h_gf":                 "Head-to-head goals scored",
            "h2h_away_gf":            "Head-to-head away goals scored",
            "h2h_wins":               "Head-to-head matches won",
            "disciplinary":           "Disciplinary points (fewest)",
            "less_red_cards":         "Fewer red cards",
            "less_yellow_cards":      "Fewer yellow cards",
            "playoffs":               "Play-offs",
            "playoffs_champion":      "Play-off (for championship only)",
            "playoffs_title_or_rel3": "Play-off (for championship or third relegation place)",
            "draw":                   "Draw",
            "fair_play":              "Fair-play points",
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
            _render_table(_table_rows(split_info["champ_current"], show_euro=True))
            st.markdown("### ⚠️ Relegation Conference")
            st.caption(_pts_note)
            _render_table(_table_rows(split_info["relg_current"], show_euro=False))
            with st.expander("Regular Season Final Table"):
                _render_table(_table_rows(split_info["pre_split"], show_euro=False))
        else:
            _is_split = bool(cfg.get("n_champ") or cfg.get("final_four"))
            _render_table(_table_rows(standings, show_euro=not _is_split))

            # ── Projected groups (regular season still running) ──────────────
            _nc = cfg.get("n_champ") or (4 if cfg.get("final_four") else None)
            if _nc:
                _nm       = cfg.get("n_mid") or 0
                _pf       = cfg.get("pts_factor", 1.0)
                _sorted_st = sorted(standings, key=lambda r: int(r.get("intRank", 99)))
                _pf_note  = {0.0: "⚠️ Points reset to zero at split",
                             0.5: "⚠️ Points halved (rounded down) at split"}.get(_pf, "")

                st.divider()
                if cfg.get("final_four"):
                    st.markdown("### 📊 Projected Final Four")
                    st.caption("Top 4 by current table position — subject to change")
                    _render_table(_table_rows(_sorted_st[:4], show_euro=True))
                else:
                    st.markdown("### 📊 Projected Groups")
                    st.caption("Based on current standings — regular season still running, groups not yet confirmed")

                    st.markdown("#### 🏆 Championship Group")
                    if _pf_note:
                        st.caption(_pf_note)
                    _render_table(_table_rows(_sorted_st[:_nc], show_euro=False))

                    if _nm:
                        st.markdown("#### 🔵 Middle Group")
                        _render_table(_table_rows(_sorted_st[_nc:_nc + _nm], show_euro=False))

                    st.markdown("#### ⚠️ Relegation Group")
                    _render_table(_table_rows(_sorted_st[_nc + _nm:], show_euro=False))

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
                    render_prob_table(probs_champ, badge_lookup, champ_exp_pts, _euro_spots,
                                      zones=cfg.get("zones"))
                    render_zone_table(probs_champ, split_info["champ_current"], cfg.get("zones"))
                st.markdown("### Relegation Conference")
                if not probs_relg.empty:
                    _relg_zones = cfg.get("zones") or _zones_from_standings(split_info["relg_current"])
                    render_prob_table(probs_relg, badge_lookup, relg_exp_pts, _euro_spots,
                                      zones=_relg_zones)
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
                _main_zones = cfg.get("zones") or _zones_from_standings(standings)
                render_prob_table(st.session_state["sim_results"], badge_lookup, exp_pts, _euro_spots,
                                  zones=_main_zones)
                render_zone_table(st.session_state["sim_results"], standings, cfg.get("zones"))

                # ── Projected groups by probability (pre-split leagues) ───────
                _nc = cfg.get("n_champ") or (4 if cfg.get("final_four") else None)
                if _nc:
                    _nm      = cfg.get("n_mid") or 0
                    probs_df = st.session_state["sim_results"]
                    n_total  = len(standings)

                    def _proj_group_table(teams_list, pos_str_list):
                        """Show the predicted group members with per-position probabilities."""
                        pos_labels = [f"#{p}" for p in pos_str_list]
                        rows = []
                        for team in teams_list:
                            if team not in probs_df.index:
                                continue
                            row = {"Badge": badge_lookup.get(team, ""), "Team": team}
                            for ps, lbl in zip(pos_str_list, pos_labels):
                                row[lbl] = float(probs_df.loc[team, ps]) * 100 if ps in probs_df.columns else 0.0
                            rows.append(row)
                        if not rows:
                            return
                        _df = pd.DataFrame(rows)
                        _styled = (
                            _df.style
                            .hide(axis="index")
                            .apply(_green_col, axis=0, subset=pos_labels)
                            .format("{:.1f}%", subset=pos_labels)
                            .set_properties(subset=["Team"], **{"font-weight": "bold"})
                        )
                        _col_cfg = {
                            "Badge": st.column_config.ImageColumn("", width=32),
                            "Team":  st.column_config.TextColumn("Team", width=170),
                        }
                        for lbl in pos_labels:
                            _col_cfg[lbl] = st.column_config.TextColumn(lbl, width=52)
                        _c, _ = st.columns([5, 1])
                        with _c:
                            st.dataframe(_styled, column_config=_col_cfg,
                                         use_container_width=True, hide_index=True,
                                         height=len(rows) * 35 + 38)

                    # Build group membership by summing P(positions in range)
                    champ_pos = [str(i) for i in range(1, _nc + 1) if str(i) in probs_df.columns]
                    p_champ   = probs_df[champ_pos].sum(axis=1) if champ_pos else None
                    relg_start = _nc + _nm + 1
                    relg_pos   = [str(i) for i in range(relg_start, n_total + 1) if str(i) in probs_df.columns]
                    p_relg     = probs_df[relg_pos].sum(axis=1) if relg_pos else None

                    st.divider()
                    if cfg.get("final_four"):
                        # Show top-4 predicted teams, ranked by P(top 4), with pos 1-4 breakdown
                        st.markdown("### 📊 Projected Final Four")
                        st.caption("4 most likely qualifiers · columns show P(finishing that regular-season position)")
                        if p_champ is not None:
                            top4 = list(p_champ.sort_values(ascending=False).index[:4])
                            _proj_group_table(top4, champ_pos)
                    else:
                        st.markdown("### 📊 Projected Play-offs / Play-outs")
                        _pts_note = {0.0: "points reset to 0", 0.5: "points halved"}.get(_pf, "points carried over")
                        _st_lookup = {r["strTeam"]: r for r in standings}
                        _zone_notes = cfg.get("zone_notes", {})
                        _po_sim_key = ("playoff", league_id, season, n_sim, home_advantage)
                        if st.session_state.get("po_sim_key") != _po_sim_key:
                            st.session_state["po_sims"] = {}
                            st.session_state["po_sim_key"] = _po_sim_key

                        if p_champ is not None:
                            st.markdown("#### 🏆 Championship Play-off")
                            _champ_fmt = _zone_notes.get("championship",
                                f"Top {_nc} teams advance to a round-robin play-off; {_pts_note} at the split.")
                            st.caption(_champ_fmt)
                            top_champ = list(p_champ.sort_values(ascending=False).index[:_nc])
                            _po_c = tuple(top_champ)
                            if _po_c not in st.session_state.get("po_sims", {}):
                                with st.spinner("Simulating championship play-off…"):
                                    _po_probs = simulate_season(
                                        standings=_playoff_standings(top_champ, _st_lookup, _pf),
                                        remaining_fixtures=_roundrobin_fixtures(top_champ),
                                        ratings=ratings_df, n_sim=n_sim,
                                        home_advantage=home_advantage,
                                        tiebreakers=cfg.get("tiebreakers"),
                                    )
                                st.session_state["po_sims"][_po_c] = _po_probs
                            render_prob_table(st.session_state["po_sims"][_po_c], badge_lookup,
                                              european_spots=_euro_spots,
                                              zones=cfg.get("zones"),
                                              title="Championship play-off finish probabilities")

                        if _nm:
                            mid_pos = [str(i) for i in range(_nc + 1, _nc + _nm + 1) if str(i) in probs_df.columns]
                            p_mid   = probs_df[mid_pos].sum(axis=1) if mid_pos else None
                            if p_mid is not None:
                                st.markdown("#### 🔵 Middle Group")
                                _mid_fmt = _zone_notes.get("middle", _zone_notes.get("europa",
                                    f"{_nm} teams advance to a round-robin group; {_pts_note} at the split."))
                                st.caption(_mid_fmt)
                                top_mid = list(p_mid.sort_values(ascending=False).index[:_nm])
                                _po_m = tuple(top_mid)
                                if _po_m not in st.session_state.get("po_sims", {}):
                                    with st.spinner("Simulating middle group…"):
                                        _po_probs = simulate_season(
                                            standings=_playoff_standings(top_mid, _st_lookup, _pf),
                                            remaining_fixtures=_roundrobin_fixtures(top_mid),
                                            ratings=ratings_df, n_sim=n_sim,
                                            home_advantage=home_advantage,
                                            tiebreakers=cfg.get("tiebreakers"),
                                        )
                                    st.session_state["po_sims"][_po_m] = _po_probs
                                render_prob_table(st.session_state["po_sims"][_po_m], badge_lookup,
                                                  title="Middle group finish probabilities")

                        if p_relg is not None:
                            n_relg = n_total - _nc - _nm
                            st.markdown("#### ⚠️ Relegation Play-out")
                            _relg_parts = [v for k, v in _zone_notes.items()
                                           if k in ("relegation", "europa", "middle")]
                            _relg_fmt = "  ".join(_relg_parts) if _relg_parts else \
                                f"Bottom {n_relg} teams advance to a round-robin play-out; {_pts_note} at the split."
                            st.caption(_relg_fmt)
                            top_relg = list(p_relg.sort_values(ascending=False).index[:n_relg])
                            _po_r = tuple(top_relg)
                            if _po_r not in st.session_state.get("po_sims", {}):
                                with st.spinner("Simulating relegation play-out…"):
                                    _po_probs = simulate_season(
                                        standings=_playoff_standings(top_relg, _st_lookup, _pf),
                                        remaining_fixtures=_roundrobin_fixtures(top_relg),
                                        ratings=ratings_df, n_sim=n_sim,
                                        home_advantage=home_advantage,
                                        tiebreakers=cfg.get("tiebreakers"),
                                    )
                                st.session_state["po_sims"][_po_r] = _po_probs
                            _po_relg_zones = cfg.get("zones") or _zones_from_standings(list(_st_lookup.values()))
                            render_prob_table(st.session_state["po_sims"][_po_r], badge_lookup,
                                              zones=_po_relg_zones,
                                              title="Relegation play-out finish probabilities")

                # ── Final Four simulation (e.g. Albanian Superliga) ──────────
                if cfg.get("final_four"):
                    probs_df = st.session_state["sim_results"]
                    # Top-4 probability = sum of P(pos 1..4) for each team
                    top4_cols = [c for c in probs_df.columns if c in [str(i) for i in range(1, 5)]]
                    top4_prob = probs_df[top4_cols].sum(axis=1).sort_values(ascending=False)
                    teams_4   = list(top4_prob.index[:4])

                    ff_key = ("ff", league_id, season, n_sim)
                    if st.session_state.get("ff_key") != ff_key:
                        with st.spinner("Simulating Final Four…"):
                            ff_df = simulate_final_four(teams_4, ratings_df, n_sim)
                        st.session_state["ff_results"] = ff_df
                        st.session_state["ff_key"]     = ff_key

                    if "ff_results" in st.session_state and not st.session_state["ff_results"].empty:
                        ff_df = st.session_state["ff_results"]
                        st.divider()
                        st.markdown("### 🏆 Final Four — Title Probabilities")
                        st.caption(
                            "Draw pairings: Seed 1 & Seed 2 (1st/2nd) cannot meet in the semi-finals. "
                            "Semi-final tie → higher-ranked team advances. Final tie → extra time + penalties."
                        )
                        seed_label = {teams_4[0]: "🥇 Seed 1", teams_4[1]: "🥈 Seed 2",
                                      teams_4[2]: "Unseeded", teams_4[3]: "Unseeded"}
                        rows_html = ""
                        for _, row in ff_df.iterrows():
                            team  = row["Team"]
                            badge = badge_lookup.get(team, "")
                            seed  = seed_label.get(team, "")
                            img   = f"<img src='{badge}' style='height:20px;vertical-align:middle;margin-right:6px'>" if badge else ""
                            rows_html += (
                                f"<tr>"
                                f"<td style='padding:6px 10px'>{img}<b>{team}</b></td>"
                                f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{seed}</td>"
                                f"<td style='padding:6px 10px;text-align:right'>{row['SF Win %']}%</td>"
                                f"<td style='padding:6px 10px;text-align:right'>{row['Final %']}%</td>"
                                f"<td style='padding:6px 10px;text-align:right;font-weight:bold'>{row['Title %']}%</td>"
                                f"</tr>"
                            )
                        st.markdown(
                            "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                            "<thead><tr style='border-bottom:1px solid #444'>"
                            "<th style='padding:6px 10px;text-align:left'>Team</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Seed</th>"
                            "<th style='padding:6px 10px;text-align:right;color:#888'>SF Win %</th>"
                            "<th style='padding:6px 10px;text-align:right;color:#888'>Final %</th>"
                            "<th style='padding:6px 10px;text-align:right;color:#888'>Title %</th>"
                            f"</tr></thead><tbody>{rows_html}</tbody></table>",
                            unsafe_allow_html=True,
                        )

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
                    _manual_zones = cfg.get("zones") or _zones_from_standings(updated_st)
                    render_prob_table(cached["probs"], badge_lookup, manual_exp_pts, _euro_spots,
                                      zones=_manual_zones)
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
            "gd":                     "Goal difference",
            "gf":                     "Goals scored",
            "away_gf":                "Away goals scored",
            "away_wins":              "Away matches won",
            "wins":                   "Matches won",
            "less_losses":            "Fewer losses",
            "h2h_pts":                "Head-to-head points",
            "h2h_gd":                 "Head-to-head goal difference",
            "h2h_gf":                 "Head-to-head goals scored",
            "h2h_away_gf":            "Head-to-head away goals scored",
            "h2h_wins":               "Head-to-head matches won",
            "disciplinary":           "Disciplinary points (fewest)",
            "less_red_cards":         "Fewer red cards",
            "less_yellow_cards":      "Fewer yellow cards",
            "playoffs":               "Play-offs",
            "playoffs_champion":      "Play-off (for championship only)",
            "playoffs_title_or_rel3": "Play-off (for championship or third relegation place)",
            "draw":                   "Draw",
            "fair_play":              "Fair-play points",
        }

        # ── Season overview ──────────────────────────────────────────────────
        st.markdown("### 📅 Season Overview")
        all_dates = sorted([
            f.get("dateEvent") for f in (played_fixtures + remaining_fixtures)
            if f.get("dateEvent")
        ])
        def _fmt_date(d):
            try:
                import datetime
                dt = datetime.datetime.strptime(d, "%Y-%m-%d")
                return f"{dt.day} {dt.strftime('%B')} {dt.year}"
            except Exception:
                return d
        season_start = _fmt_date(all_dates[0])  if all_dates else "—"
        season_end   = cfg.get("season_end") or (_fmt_date(all_dates[-1]) if all_dates else "—")
        _ov_items = [
            ("Teams",        str(len(standings))),
            ("Rounds",       str(total_rounds)),
            ("Season start", season_start),
            ("Season end",   season_end),
        ]
        _ov_cells = "".join(
            f"<div style='margin-right:40px'>"
            f"<div style='font-size:12px;color:#888;margin-bottom:3px'>{lbl}</div>"
            f"<div style='font-size:22px;font-weight:600;color:inherit'>{val}</div>"
            f"</div>"
            for lbl, val in _ov_items
        )
        st.markdown(
            f"<div style='display:inline-flex;align-items:flex-end;"
            f"padding:10px 0 6px'>{_ov_cells}</div>",
            unsafe_allow_html=True,
        )

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
                boxes = [
                    ("#1a472a", "🏆 Championship", f"Top {_nchmp} teams", _pts_label),
                ]
                if _nmid:
                    boxes.append(("#1a3a5c", "🔵 Middle Group", f"{_nmid} teams", _pts_label))
                if n_relg and n_relg > 0:
                    boxes.append(("#4a1a1a", "⚠️ Relegation", f"Bottom {n_relg} teams", _pts_label))
                for bg, title, sub, note in boxes:
                    st.markdown(
                        f"<div class='format-group-box' style='background:{bg};padding:14px 18px;"
                        f"border-radius:8px;color:white;margin-bottom:8px'>"
                        f"<b>{title}</b> &nbsp;·&nbsp; {sub}<br>"
                        f"<small style='opacity:0.85'>{note}</small></div>",
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
