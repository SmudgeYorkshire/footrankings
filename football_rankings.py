"""
Football Rankings — public page.

Auto-refreshes data every 60 seconds. API key is read from the
environment only (not user-editable). Opta ratings are hidden.
"""

import os
import json
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import LEAGUES, DEFAULT_N_SIMULATIONS, DEFAULT_HOME_ADVANTAGE, get_current_season
from data_fetcher import SportsDBClient
from simulator import simulate_season, fixture_odds, simulate_final_four, simulate_uecl_playoff, simulate_uecl_3team_playoff, simulate_uecl_5team_playoff, simulate_uecl_4team_playoff, simulate_uecl_8team_playoff
from ratings_manager import load_ratings, build_lookup, check_coverage
from _split_season import get_split_info, conference_fixtures, recompute_conference_standings
from league_status import LEAGUE_STATUS

_API_KEY = os.getenv("THESPORTSDB_API_KEY", "3")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from datetime import datetime, timezone
from pathlib import Path
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


def _season_progress_html(played_r: int, total_r: int, n_played_m: int, n_remaining_m: int) -> str:
    """Compact progress bar showing season round progress."""
    pct = (played_r / total_r * 100) if total_r else 0
    bar_color = "#28a745" if pct >= 75 else "#ffc107" if pct >= 40 else "#17a2b8"
    return (
        f"<div style='margin:0 0 10px 0'>"
        f"<div style='display:flex;align-items:baseline;gap:8px;margin-bottom:3px'>"
        f"<span style='font-size:13px;font-weight:600;color:#212529'>Matchweek {played_r} of {total_r}</span>"
        f"<span style='font-size:11px;color:#6c757d'>· {n_played_m} matches played"
        f"{f', {n_remaining_m} remaining' if n_remaining_m else ' · season complete'}</span>"
        f"</div>"
        f"<div style='background:#e9ecef;border-radius:4px;height:5px;max-width:400px'>"
        f"<div style='background:{bar_color};height:100%;width:{pct:.1f}%;border-radius:4px'></div>"
        f"</div></div>"
    )


def _conf_progress_html(conf_played_fix: list, conf_remaining_fix: list) -> str:
    """Progress bar for a conference/play-off phase derived from its fixture lists."""
    _rw_rem = {f.get("intRound") for f in conf_remaining_fix if f.get("intRound")}
    _rw_pl  = {f.get("intRound") for f in conf_played_fix  if f.get("intRound")}
    _pr = len(_rw_pl - _rw_rem)
    _rr = len(_rw_rem)
    _tr = _pr + _rr
    return _season_progress_html(_pr, _tr, len(conf_played_fix), len(conf_remaining_fix))


def _auto_zones(european_spots: dict, status_zones: dict = None) -> dict | None:
    """Derive zone groups from european_spots + league_status zones.

    Zones produced:
      - Champions League  : UCL positions only
      - European places   : all UCL + UEL + UECL positions combined
      - Relegation        : relegation positions (from status_zones or european_spots)
    """
    ucl, all_europe, relega = [], [], []
    for pos, label in (european_spots or {}).items():
        l = str(label).lower()
        if "relega" in l:
            relega.append(pos)
        else:
            if "ucl" in l:
                ucl.append(pos)
            if "ucl" in l or "uel" in l or "uecl" in l:
                all_europe.append(pos)
    # Relegation from league_status if not in european_spots
    for pos, label in (status_zones or {}).items():
        if "relega" in str(label).lower() and pos not in relega:
            relega.append(pos)
    zones = {}
    if ucl:
        zones["Champions League"] = sorted(ucl)
    if all_europe:
        zones["European places"] = sorted(all_europe)
    if relega:
        zones["Relegation"] = sorted(relega)
    return zones or None


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
    raw_zones = zone_override or {}
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
    """Colour + bold for status labels in the predicted-standings Status column."""
    s = str(val).lower().rstrip("*").rstrip()
    if "relega"           in s: return "color: #ea4335; font-weight: bold"
    if "champions league" in s: return "color: #1a73e8; font-weight: bold"
    if "europa league"    in s: return "color: #f9ab00; font-weight: bold"
    if "uecl play-offs"   in s: return "color: #34a853; font-weight: bold"
    if "conference"       in s: return "color: #34a853; font-weight: bold"
    if "final four"       in s: return "color: #2e7d32; font-weight: bold"
    if "championship"     in s: return "color: #2e7d32; font-weight: bold"
    if "play-off"         in s: return "color: #2e7d32; font-weight: bold"
    if "play out"         in s: return "color: #f9ab00; font-weight: bold"
    if "middle"           in s: return "color: #f9ab00; font-weight: bold"
    return ""


def _status_for_pos(pos: int, status_map: dict) -> str:
    """Return the status label for a given position from a {pos: label} dict."""
    return (status_map or {}).get(pos, "")


def render_prob_table(probs: pd.DataFrame, badge_lookup: dict = None,
                      expected_pts: dict = None, european_spots: dict = None,
                      title: str = "Season finish probabilities", zones: dict = None,
                      status_map: dict = None, team_overrides: dict = None):
    """Color-coded finish-probability table, sorted by xPts descending.

    status_map: unified {pos: label} dict from league_status.py (preferred).
    european_spots / zones: legacy params, used only if status_map is not provided.
    team_overrides: {team_name: label} — fixed status for specific teams regardless of position.
    """
    # Resolve unified status map
    _smap = status_map if status_map is not None else (european_spots or {})

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
    if _smap or team_overrides:
        df["Status"] = [
            (team_overrides or {}).get(t) or _status_for_pos(pos, _smap)
            for pos, t in zip(df.index, df["Team"])
        ]
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
        options=list(LEAGUES.keys()),
        format_func=lambda n: n,
    )
    cfg = LEAGUES[league_name]
    league_id = cfg["id"]
    season = get_current_season(cfg["season_type"])
    home_advantage = cfg.get("home_advantage", DEFAULT_HOME_ADVANTAGE)
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

    # ── Apply fixture patches to standings when TheSportsDB lags ────────────
    _patch_file = Path("presplit/fixture_patches.json")
    _patch_key  = f"{league_id}_{season}"
    if _patch_file.exists() and standings:
        try:
            with open(_patch_file) as _pf:
                _patches = json.load(_pf).get(_patch_key, [])
            if _patches:
                _std_by_team = {r["strTeam"]: r for r in standings}
                _modified = False
                for _p in _patches:
                    _home  = _p.get("strHomeTeam", "")
                    _away  = _p.get("strAwayTeam", "")
                    _round = int(_p.get("intRound", 0))
                    _hr    = _std_by_team.get(_home)
                    _ar    = _std_by_team.get(_away)
                    if not _hr or not _ar:
                        continue
                    if int(_hr.get("intPlayed", 0)) >= _round:
                        continue  # standings already up to date for this match
                    _hg = int(_p.get("intHomeScore", 0))
                    _ag = int(_p.get("intAwayScore", 0))
                    for _row, _gf, _ga in [(_hr, _hg, _ag), (_ar, _ag, _hg)]:
                        _row["intPlayed"]       = str(int(_row.get("intPlayed", 0)) + 1)
                        _row["intGoalsFor"]     = str(int(_row.get("intGoalsFor", 0)) + _gf)
                        _row["intGoalsAgainst"] = str(int(_row.get("intGoalsAgainst", 0)) + _ga)
                        _row["intGoalDifference"] = str(
                            int(_row.get("intGoalsFor", 0)) - int(_row.get("intGoalsAgainst", 0))
                        )
                        if _hg > _ag:
                            if _row is _hr:
                                _row["intWin"]    = str(int(_row.get("intWin", 0)) + 1)
                                _row["intPoints"] = str(int(_row.get("intPoints", 0)) + 3)
                            else:
                                _row["intLoss"] = str(int(_row.get("intLoss", 0)) + 1)
                        elif _hg == _ag:
                            _row["intDraw"]   = str(int(_row.get("intDraw", 0)) + 1)
                            _row["intPoints"] = str(int(_row.get("intPoints", 0)) + 1)
                        else:
                            if _row is _ar:
                                _row["intWin"]    = str(int(_row.get("intWin", 0)) + 1)
                                _row["intPoints"] = str(int(_row.get("intPoints", 0)) + 3)
                            else:
                                _row["intLoss"] = str(int(_row.get("intLoss", 0)) + 1)
                    _modified = True
                if _modified:
                    standings = sorted(
                        standings,
                        key=lambda r: (
                            -int(r.get("intPoints", 0)),
                            -int(r.get("intGoalDifference", 0)),
                            -int(r.get("intGoalsFor", 0)),
                        ),
                    )
                    for _i, _r in enumerate(standings, 1):
                        _r["intRank"] = str(_i)
        except Exception:
            pass

    ratings_df = load_ratings(league_id, standings)
    _missing_ratings = check_coverage(standings, ratings_df)
    if _missing_ratings:
        st.warning(
            "⚠️ No rating found for: **" + "**, **".join(_missing_ratings) + "**. "
            "These teams will use the league-average strength. "
            "Add them to the ratings CSV or set an alias to fix this."
        )
    split_round = cfg.get("split_round")
    n_champ     = cfg.get("n_champ")
    pts_factor  = cfg.get("pts_factor", 1.0)

    # ── Pre-split snapshot cache ─────────────────────────────────────────────
    # Saves the exact Round N standings before any team advances or points are
    # halved. Used exclusively for the "Regular Season Final Table" display.
    # presplit/ is committed to git so the live app always has the snapshot.
    # cache/ is local-only and written at runtime.
    _presplit_committed = f"presplit/{league_id}_{season}.json"
    _presplit_cache     = f"cache/presplit_{league_id}_{season}.json"
    _presplit_snapshot = None
    if split_round:
        for _path in (_presplit_cache, _presplit_committed):
            if os.path.exists(_path):
                try:
                    with open(_path) as _f:
                        _presplit_snapshot = json.load(_f)
                    break
                except Exception:
                    pass
        if _presplit_snapshot is None and standings and all(
            int(r.get("intPlayed", 0)) == split_round for r in standings
        ):
            # All teams just completed the split round — save the snapshot now
            try:
                with open(_presplit_cache, "w") as _f:
                    json.dump(standings, _f)
                _presplit_snapshot = list(standings)
            except Exception:
                pass

    split_info = get_split_info(standings, split_round, n_champ=n_champ, n_mid=cfg.get("n_mid", 0), pts_factor=pts_factor, presplit=_presplit_snapshot) if split_round else None

    # TheSportsDB confirmed they cannot update split-league standings tables.
    # Always recompute all conference standings from the presplit snapshot +
    # played post-split fixtures so Current Table and Projections are accurate.
    if split_info and split_round and _presplit_snapshot:
        _pts_round      = cfg.get("pts_round", "down")
        _presplit_by_tm = {r["strTeam"]: r for r in _presplit_snapshot}
        for _conf_key, _teams_key in [
            ("champ_current", "champ_teams"),
            ("mid_current",   "mid_teams"),
            ("relg_current",  "relg_teams"),
        ]:
            _conf_teams = split_info.get(_teams_key, set())
            if not _conf_teams:
                continue
            _base = [_presplit_by_tm[t] for t in _conf_teams if t in _presplit_by_tm]
            if not _base:
                continue
            _post_split_played = [
                f for f in played_fixtures
                if int(f.get("intRound") or 0) > split_round
            ]
            _conf_played = conference_fixtures(_post_split_played, _conf_teams)
            split_info[_conf_key] = recompute_conference_standings(
                _base, _conf_played, pts_factor, _pts_round
            )

    # Override pre_split with the accurate Round N snapshot if available
    if split_info and _presplit_snapshot:
        split_info["pre_split"] = sorted(_presplit_snapshot,
                                         key=lambda r: int(r.get("intRank") or 99))
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
        current_round = min((r for r in rounds_with_remaining if r), default=total_rounds)
        # Last-updated from cache file mtime
        _cache_path = Path("cache") / f"fixtures_{league_id}_{season}.json"
        _updated_str = ""
        if _cache_path.exists():
            _mtime = _cache_path.stat().st_mtime
            _updated_str = "  \nLast updated: **" + datetime.fromtimestamp(_mtime, tz=_CET).strftime("%b %d, %H:%M") + " CET**"
        st.caption(
            f"Rounds: **{total_rounds}** total · **{played_rounds}** played · **{remaining_rounds}** remaining  \n"
            f"Matches: **{total}** total · **{len(played_fixtures)}** played · **{len(remaining_fixtures)}** remaining"
            + _updated_str
        )

    st.divider()

    # Status maps — from league_status.py only; shared across ALL tabs
    # TheSportsDB data is NOT used for status labels
    _ls           = LEAGUE_STATUS.get(league_name, {})
    _main_zones      = _ls.get("regular", {})   # pos → label for regular season
    _team_overrides  = cfg.get("team_status_overrides", {})  # team name → fixed label
    _champ_zones  = _ls.get("champ",   {})   # pos → label within championship conf
    _mid_zones    = _ls.get("mid",     {})   # pos → label within middle conf
    _relg_zones   = _ls.get("relg",    {})   # pos → label within relegation conf
    _mid_label    = cfg.get("mid_label", "Europe Play-off")

    # Spot-only zones: filter _main_zones to actual European/relegation spots
    # (removes group-assignment labels like "Championship Group", "Relegation Group", etc.)
    _SPOT_KW      = ("ucl", "uel", "uecl", "relega", "promot", "play-out", "play out", "championship round")
    _GROUP_SUFFIX = (" group",)
    _spot_zones = {pos: lbl for pos, lbl in (_main_zones or {}).items()
                   if any(kw in lbl.lower() for kw in _SPOT_KW)
                   and not any(lbl.lower().endswith(s) for s in _GROUP_SUFFIX)}

    _UECL_PO_FOOTNOTE = "* These clubs enter additional domestic play-offs to determine the last UECL qualifying spot."


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

        def _table_rows(source_rows, zones=None, show_form=True, relative_zones=False, team_overrides=None):
            rows = []
            for rel_pos, row in enumerate(
                    sorted(source_rows, key=lambda r: int(r.get("intRank", 99))), start=1):
                gd      = int(row.get("intGoalDifference", 0))
                abs_pos = int(row.get("intRank", 0))
                zone_key = rel_pos if relative_zones else abs_pos
                team_name = row.get("strTeam", "")
                status = (team_overrides or {}).get(team_name) or (zones or {}).get(zone_key, "")
                r = {
                    "Pos":    abs_pos,
                    "Badge":  row.get("strBadge") or "",
                    "Team":   team_name,
                    "P":      int(row.get("intPlayed", 0)),
                    "W":      int(row.get("intWin", 0)),
                    "D":      int(row.get("intDraw", 0)),
                    "L":      int(row.get("intLoss", 0)),
                    "GF":     int(row.get("intGoalsFor", 0)),
                    "GA":     int(row.get("intGoalsAgainst", 0)),
                    "GD":     f"+{gd}" if gd > 0 else str(gd),
                    "Pts":    int(row.get("intPoints", 0)),
                    "Status": status,
                }
                if show_form:
                    r["Form"] = _fmt_form(row.get("strForm", "") or "")
                rows.append(r)
            return rows

        def _status_style(val):
            s = str(val).lower().rstrip("*").rstrip()
            if "relega"           in s: return "color: #ea4335; font-weight: bold"
            if "champions league" in s: return "color: #1a73e8; font-weight: bold"
            if "europa league"    in s: return "color: #f9ab00; font-weight: bold"
            if "uecl play-offs"   in s: return "color: #34a853; font-weight: bold"
            if "conference"       in s: return "color: #34a853; font-weight: bold"
            if "final four"       in s: return "color: #2e7d32; font-weight: bold"
            if "championship"     in s: return "color: #2e7d32; font-weight: bold"
            if "play-off"         in s: return "color: #2e7d32; font-weight: bold"
            if "play out"         in s: return "color: #f9ab00; font-weight: bold"
            if "middle"           in s: return "color: #f9ab00; font-weight: bold"
            return ""

        def _europe_style(val):
            s = str(val).upper().rstrip("*").rstrip()
            if "UCL"  in s: return "color: #1a73e8; font-weight: bold"
            if "UEL"  in s: return "color: #f9ab00; font-weight: bold"
            if "UECL" in s: return "color: #34a853; font-weight: bold"
            return ""

        def _render_table(rows):
            if not rows:
                return
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
                "Status": st.column_config.TextColumn("Status", width=130),
            }
            if "Form" in df.columns:
                col_cfg["Form"] = st.column_config.TextColumn("Form", width=130)
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
            "pts_no_round":           "Points (without half-point rounding)",
            "regular_pts":            "Regular season points",
            "regular_position":       "Regular season finishing position",
            "playoffs":               "Play-offs",
            "playoffs_champion":      "Play-off (for championship only)",
            "playoffs_title_or_rel3": "Play-off (for championship or third relegation place)",
            "draw":                   "Draw",
            "fair_play":              "Fair-play points",
        }

        if split_info:
            _pf       = split_info.get("pts_factor", 1.0)
            _pts_dir  = cfg.get("pts_round", "down")  # "up" for Belgium
            _half_note = (
                "⚠️ Points halved (rounded up) at split" if _pts_dir == "up"
                else "⚠️ Points halved (rounded down) at split"
            )
            if _pf == 0.0:
                _pts_note = "⚠️ Points reset to zero at split"
            elif _pf == 0.5:
                _pts_note = _half_note
            else:
                _pts_note = "Points carried over in full"
            _relg_pf = cfg.get("relg_pts_factor", _pf)
            if _relg_pf == 0.0:
                _relg_pts_note = "⚠️ Points reset to zero at split"
            elif _relg_pf == 0.5:
                _relg_pts_note = _half_note
            else:
                _relg_pts_note = "Points carried over in full"
            _champ_pf = conference_fixtures(played_fixtures,    split_info["champ_teams"])
            _champ_rf = conference_fixtures(remaining_fixtures, split_info["champ_teams"])
            _relg_pf  = conference_fixtures(played_fixtures,    split_info["relg_teams"])
            _relg_rf  = conference_fixtures(remaining_fixtures, split_info["relg_teams"])
            _champ_tbs = cfg.get("champ_tiebreakers") or cfg.get("tiebreakers", ["gd", "gf"])
            _mid_tbs   = cfg.get("mid_tiebreakers")   or cfg.get("champ_tiebreakers") or cfg.get("tiebreakers", ["gd", "gf"])
            _relg_tbs  = cfg.get("relg_tiebreakers")  or cfg.get("champ_tiebreakers") or cfg.get("tiebreakers", ["gd", "gf"])
            def _tb_caption(tbs):
                return "Tiebreakers: " + "; ".join(
                    f"{i+1}) {_TB_LABELS.get(r, r)}" for i, r in enumerate(tbs[:8]))

            st.markdown("### 🏆 Championship Round")
            st.markdown(_conf_progress_html(_champ_pf, _champ_rf), unsafe_allow_html=True)
            st.caption(_pts_note)
            _render_table(_table_rows(split_info["champ_current"], zones=_champ_zones))
            st.caption(_tb_caption(_champ_tbs))
            if any(str(v).endswith("*") for v in (_champ_zones or {}).values()):
                st.caption(_UECL_PO_FOOTNOTE)

            # ── Cup Details ──────────────────────────────────────────────────────
            _cup_details = cfg.get("cup_details", "Cup winner will enter European competitions")
            st.markdown("#### 🏆 Cup Details")
            st.markdown(f"<small>{_cup_details}</small>", unsafe_allow_html=True)

            if split_info.get("mid_teams"):
                _mid_pf  = conference_fixtures(played_fixtures,    split_info["mid_teams"])
                _mid_rf  = conference_fixtures(remaining_fixtures, split_info["mid_teams"])
                st.markdown(f"### 🔵 {_mid_label}")
                st.markdown(_conf_progress_html(_mid_pf, _mid_rf), unsafe_allow_html=True)
                st.caption(_pts_note)
                _render_table(_table_rows(split_info["mid_current"], zones=_mid_zones, relative_zones=True))
                st.caption(_tb_caption(_mid_tbs))
            if split_info.get("relg_current") and not cfg.get("champ_only"):
                st.markdown("### ⚠️ Relegation Round")
                st.markdown(_conf_progress_html(_relg_pf, _relg_rf), unsafe_allow_html=True)
                st.caption(_relg_pts_note)
                _render_table(_table_rows(split_info["relg_current"], zones=_relg_zones, relative_zones=True))
                st.caption(_tb_caption(_relg_tbs))
                if any(str(v).endswith("*") for v in (_relg_zones or {}).values()):
                    st.caption(_UECL_PO_FOOTNOTE)

            # ── UECL Play-offs (e.g. Austrian Bundesliga) ────────────────────
            if cfg.get("uecl_playoff"):
                # Deduplicate by team name (keep first/best-ranked entry)
                def _dedup_ranked(rows):
                    seen, out = set(), []
                    for r in sorted(rows, key=lambda r: int(r.get("intRank", 99))):
                        t = r.get("strTeam", "")
                        if t not in seen:
                            seen.add(t)
                            out.append(r)
                    return out
                _champ_ranked = _dedup_ranked(split_info["champ_current"])
                _relg_ranked  = _dedup_ranked(split_info["relg_current"])
                # champ 5th = bye to final; relg 1st (7th) hosts relg 2nd (8th) in semi
                _uecl_entries = []
                if len(_champ_ranked) >= 5:
                    _uecl_entries.append((_champ_ranked[4], "Bye to Final (hosts leg 2)"))
                if len(_relg_ranked) >= 2:
                    _uecl_entries.append((_relg_ranked[0], "SF host (7th)"))
                    _uecl_entries.append((_relg_ranked[1], "SF away (8th)"))
                elif _relg_ranked:
                    _uecl_entries.append((_relg_ranked[0], "SF host (7th)"))
                if _uecl_entries:
                    st.divider()
                    st.markdown("### 🏅 Conference League Play-offs — Projected Entries")
                    st.caption(
                        "7th-placed team (Relegation Group winner) hosts 8th-placed team in a one-legged semi-final. "
                        "The winner meets 5th-placed team (Championship Group) in a two-legged final, "
                        "with 5th hosting the second leg. Winner qualifies for UECL QR2."
                    )
                    # Bye team (first entry) is the projected winner
                    _upo_bye_team = _uecl_entries[0][0].get("strTeam", "") if _uecl_entries else ""
                    _upo_rows = ""
                    for _urow, _urole in _uecl_entries:
                        _ut = _urow.get("strTeam", "")
                        _ub = _urow.get("strBadge", "")
                        _ui = (f"<img src='{_ub}' style='height:20px;vertical-align:middle;"
                               f"margin-right:6px'>" if _ub else "")
                        _upo_status = "UECL – QR2" if _ut == _upo_bye_team else ""
                        _upo_sstyle = "color:#1a73e8;font-weight:bold" if _upo_status else ""
                        _upo_rows += (
                            f"<tr>"
                            f"<td style='padding:6px 10px'>{_ui}<b>{_ut}</b></td>"
                            f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_urole}</td>"
                            f"<td style='padding:6px 10px;{_upo_sstyle}'>{_upo_status}</td>"
                            f"</tr>"
                        )
                    st.markdown(
                        "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                        "<thead><tr style='border-bottom:1px solid #444'>"
                        "<th style='padding:6px 10px;text-align:left'>Team</th>"
                        "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                        "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                        f"</tr></thead><tbody>{_upo_rows}</tbody></table>",
                        unsafe_allow_html=True,
                    )

            # ── UECL 4-team Play-offs (split, e.g. Northern Irish Premiership) ─
            _u4cfg_sp = cfg.get("uecl_4team_playoff")
            if _u4cfg_sp and _u4cfg_sp.get("sf1_away_from_relg") and split_info:
                _u4sp_champ = sorted(split_info["champ_current"], key=lambda r: int(r.get("intRank", 99)))
                _u4sp_relg  = sorted(split_info["relg_current"],  key=lambda r: int(r.get("intRank", 99)))
                _u4sp_pr = [
                    (_u4cfg_sp.get("sf1_home", 4), False, f"SF1 host ({_u4cfg_sp.get('sf1_home_rank', 4)}th)"),
                    (_u4cfg_sp.get("sf1_away", 1), True,  f"SF1 away ({_u4cfg_sp.get('sf1_away_rank', 7)}th)"),
                    (_u4cfg_sp.get("sf2_home", 5), False, f"SF2 host ({_u4cfg_sp.get('sf2_home_rank', 5)}th)"),
                    (_u4cfg_sp.get("sf2_away", 6), False, f"SF2 away ({_u4cfg_sp.get('sf2_away_rank', 6)}th)"),
                ]
                _u4sp_entries = [
                    (_src[_p - 1], _role)
                    for _p, _from_relg, _role in _u4sp_pr
                    for _src in [(_u4sp_relg if _from_relg else _u4sp_champ)]
                    if len(_src) >= _p
                ]
                if _u4sp_entries:
                    st.divider()
                    st.markdown("### 🏅 Conference League Play-offs — Projected Entries")
                    st.caption(_u4cfg_sp.get("caption", ""))
                    _u4sp_html = ""
                    for _u4sp_row, _u4sp_role in _u4sp_entries:
                        _u4sp_t = _u4sp_row.get("strTeam", "")
                        _u4sp_b = _u4sp_row.get("strBadge", "")
                        _u4sp_i = (f"<img src='{_u4sp_b}' style='height:20px;vertical-align:middle;"
                                   f"margin-right:6px'>" if _u4sp_b else "")
                        _u4sp_html += (f"<tr><td style='padding:6px 10px'>{_u4sp_i}<b>{_u4sp_t}</b></td>"
                                       f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u4sp_role}</td></tr>")
                    st.markdown(
                        "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                        "<thead><tr style='border-bottom:1px solid #444'>"
                        "<th style='padding:6px 10px;text-align:left'>Team</th>"
                        "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                        f"</tr></thead><tbody>{_u4sp_html}</tbody></table>",
                        unsafe_allow_html=True,
                    )

            # ── UECL 3-team Play-off (e.g. Romanian Liga I) ──────────────────
            _u3cfg = cfg.get("uecl_3team_playoff")
            if _u3cfg and split_info:
                _u3_champ = sorted(split_info["champ_current"], key=lambda r: int(r.get("intRank", 99)))
                _u3_relg  = sorted(split_info["relg_current"],  key=lambda r: int(r.get("intRank", 99)))
                _u3_bye_pos  = _u3cfg.get("bye_home", 4) - 1
                _u3_sfa_pos  = _u3cfg.get("sf_home", 1) - 1
                _u3_sfb_pos  = _u3cfg.get("sf_away", 2) - 1
                _u3_bye_row  = _u3_champ[_u3_bye_pos]  if len(_u3_champ) > _u3_bye_pos else None
                _u3_sfa_row  = _u3_relg[_u3_sfa_pos]   if len(_u3_relg)  > _u3_sfa_pos else None
                _u3_sfb_row  = _u3_relg[_u3_sfb_pos]   if len(_u3_relg)  > _u3_sfb_pos else None
                if _u3_bye_row and _u3_sfa_row and _u3_sfb_row:
                    _u3_entries = [
                        (_u3_bye_row, f"Final host ({_u3cfg.get('bye_home_rank', 4)}th)"),
                        (_u3_sfa_row, f"SF host ({_u3cfg.get('sf_home_rank', 7)}th)"),
                        (_u3_sfb_row, f"SF away ({_u3cfg.get('sf_away_rank', 8)}th)"),
                    ]
                    st.divider()
                    st.markdown("### 🏅 Conference League Play-offs — Projected Entries")
                    st.caption(_u3cfg.get("caption", ""))
                    _u3_html = ""
                    for _u3_row, _u3_role in _u3_entries:
                        _u3_t = _u3_row.get("strTeam", "")
                        _u3_b = _u3_row.get("strBadge", "")
                        _u3_i = (f"<img src='{_u3_b}' style='height:20px;vertical-align:middle;"
                                 f"margin-right:6px'>" if _u3_b else "")
                        _u3_html += (f"<tr><td style='padding:6px 10px'>{_u3_i}<b>{_u3_t}</b></td>"
                                     f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u3_role}</td></tr>")
                    st.markdown(
                        "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                        "<thead><tr style='border-bottom:1px solid #444'>"
                        "<th style='padding:6px 10px;text-align:left'>Team</th>"
                        "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                        f"</tr></thead><tbody>{_u3_html}</tbody></table>",
                        unsafe_allow_html=True,
                    )

            # ── UECL 5-team Play-off (e.g. Welsh Premier League) ─────────────
            _u5cfg = cfg.get("uecl_5team_playoff")
            if _u5cfg and split_info:
                _u5_champ = sorted(split_info["champ_current"], key=lambda r: int(r.get("intRank", 99)))
                _u5_relg  = sorted(split_info["relg_current"],  key=lambda r: int(r.get("intRank", 99)))
                _u5_fh_p  = _u5cfg.get("final_host", 3) - 1
                _u5_q1h_p = _u5cfg.get("qf1_home",   4) - 1
                _u5_q1a_p = _u5cfg.get("qf1_away",   2) - 1  # index in relg
                _u5_q2h_p = _u5cfg.get("qf2_home",   5) - 1
                _u5_q2a_p = _u5cfg.get("qf2_away",   1) - 1  # index in relg
                _u5_fh_row  = _u5_champ[_u5_fh_p]  if len(_u5_champ) > _u5_fh_p  else None
                _u5_q1h_row = _u5_champ[_u5_q1h_p] if len(_u5_champ) > _u5_q1h_p else None
                _u5_q1a_row = _u5_relg[_u5_q1a_p]  if len(_u5_relg)  > _u5_q1a_p else None
                _u5_q2h_row = _u5_champ[_u5_q2h_p] if len(_u5_champ) > _u5_q2h_p else None
                _u5_q2a_row = _u5_relg[_u5_q2a_p]  if len(_u5_relg)  > _u5_q2a_p else None
                if all([_u5_fh_row, _u5_q1h_row, _u5_q1a_row, _u5_q2h_row, _u5_q2a_row]):
                    _u5_entries = [
                        (_u5_fh_row,  f"Final host ({_u5cfg.get('final_host_rank', 3)}th)"),
                        (_u5_q1h_row, f"QF host ({_u5cfg.get('qf1_home_rank', 4)}th)"),
                        (_u5_q2h_row, f"QF host ({_u5cfg.get('qf2_home_rank', 5)}th)"),
                        (_u5_q2a_row, f"QF away ({_u5cfg.get('qf2_away_rank', 7)}th)"),
                        (_u5_q1a_row, f"QF away ({_u5cfg.get('qf1_away_rank', 8)}th)"),
                    ]
                    st.divider()
                    st.markdown("### 🏅 Conference League Play-offs — Projected Entries")
                    st.caption(_u5cfg.get("caption", ""))
                    _u5_html = ""
                    for _u5_row, _u5_role in _u5_entries:
                        _u5_t = _u5_row.get("strTeam", "")
                        _u5_b = _u5_row.get("strBadge", "")
                        _u5_i = (f"<img src='{_u5_b}' style='height:20px;vertical-align:middle;"
                                 f"margin-right:6px'>" if _u5_b else "")
                        _u5_html += (f"<tr><td style='padding:6px 10px'>{_u5_i}<b>{_u5_t}</b></td>"
                                     f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u5_role}</td></tr>")
                    st.markdown(
                        "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                        "<thead><tr style='border-bottom:1px solid #444'>"
                        "<th style='padding:6px 10px;text-align:left'>Team</th>"
                        "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                        f"</tr></thead><tbody>{_u5_html}</tbody></table>",
                        unsafe_allow_html=True,
                    )

            # ── Champ vs Mid/Relg group European Play-off ──────────────────
            _cmp = cfg.get("champ_mid_playoff")
            if _cmp and split_info:
                _cmp_away_conf = _cmp.get("away_conf", "mid")
                _cmp_away_rows = split_info.get(f"{_cmp_away_conf}_current", [])
                _cmp_has_away  = bool(split_info.get(f"{_cmp_away_conf}_teams"))
                if _cmp_has_away:
                    _cmp_pos_idx  = _cmp.get("champ_pos", 5) - 1
                    _cmp_away_idx = _cmp.get("away_pos", 1) - 1
                    _cmp_champ_sorted = sorted(split_info["champ_current"],
                                               key=lambda r: int(r.get("intRank", 99)))
                    _cmp_away_sorted  = sorted(_cmp_away_rows,
                                               key=lambda r: int(r.get("intRank", 99)))
                    _cmp_home_row = (_cmp_champ_sorted[_cmp_pos_idx]
                                     if len(_cmp_champ_sorted) > _cmp_pos_idx else None)
                    _cmp_away_row = (_cmp_away_sorted[_cmp_away_idx]
                                     if len(_cmp_away_sorted) > _cmp_away_idx else None)
                    _cmp_away_role_label = _cmp.get(
                        "away_label",
                        f"winner of {_mid_label}" if _cmp_away_conf == "mid"
                        else "1st (Relegation Round)",
                    )
                    if _cmp_home_row and _cmp_away_row:
                        st.divider()
                        st.markdown("### 🏅 European Play-off — Projected Entries")
                        st.caption(_cmp.get("caption", ""))
                        _cmp_entries = [
                            (_cmp_home_row, f"Home — {_cmp.get('champ_pos')}th (Championship Round)"),
                            (_cmp_away_row, f"Away — {_cmp_away_role_label}"),
                        ]
                        _cmp_winner_spot = _cmp.get("winner_spot", "UECL - QR2")
                        _cmp_ht = _cmp_home_row.get("strTeam", "")
                        _cmp_rows_html = ""
                        for _ce_row, _ce_role in _cmp_entries:
                            _ct = _ce_row.get("strTeam", "")
                            _cb = _ce_row.get("strBadge", "")
                            _ci = (f"<img src='{_cb}' style='height:20px;vertical-align:middle;"
                                   f"margin-right:6px'>" if _cb else "")
                            _cst = _cmp_winner_spot if _ct == _cmp_ht else ""
                            _css = "color:#1a73e8;font-weight:bold" if _cst else ""
                            _cmp_rows_html += (
                                f"<tr>"
                                f"<td style='padding:6px 10px'>{_ci}<b>{_ct}</b></td>"
                                f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_ce_role}</td>"
                                f"<td style='padding:6px 10px;{_css}'>{_cst}</td>"
                                f"</tr>"
                            )
                        st.markdown(
                            "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                            "<thead><tr style='border-bottom:1px solid #444'>"
                            "<th style='padding:6px 10px;text-align:left'>Team</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                            f"</tr></thead><tbody>{_cmp_rows_html}</tbody></table>",
                            unsafe_allow_html=True,
                        )

            st.divider()
            st.markdown("### 📋 Regular Season Final Table")
            _render_table(_table_rows(split_info["pre_split"], zones=_spot_zones, show_form=False))
        else:
            _is_split = bool(cfg.get("n_champ") or cfg.get("final_four"))
            st.markdown(
                _season_progress_html(played_rounds, total_rounds, len(played_fixtures), len(remaining_fixtures)),
                unsafe_allow_html=True,
            )
            _render_table(_table_rows(standings, zones=_main_zones, team_overrides=_team_overrides))
            _tbs_non_split = cfg.get("tiebreakers", ["gd", "gf"])[:8]
            st.caption("Tiebreakers: " + "; ".join(f"{i+1}) {_TB_LABELS.get(r, r)}" for i, r in enumerate(_tbs_non_split)))
            if cfg.get("team_status_note"):
                st.caption(cfg["team_status_note"])

            # ── Cup Details ──────────────────────────────────────────────────────
            _cup_details = cfg.get("cup_details", "Cup winner will enter European competitions")
            st.markdown("#### 🏆 Cup Details")
            st.markdown(f"<small>{_cup_details}</small>", unsafe_allow_html=True)

            # ── UECL 4-team Play-offs (e.g. Dutch Eredivisie) ────────────────
            _u4cfg = cfg.get("uecl_4team_playoff")
            if _u4cfg:
                _u4_sorted = sorted(standings, key=lambda r: int(r.get("intRank", 99)))
                _u4_pos_roles = [
                    (_u4cfg.get("sf1_home", 5), f"SF1 host ({_u4cfg.get('sf1_home', 5)}th)"),
                    (_u4cfg.get("sf1_away", 9), f"SF1 away ({_u4cfg.get('sf1_away', 9)}th)"),
                    (_u4cfg.get("sf2_home", 7), f"SF2 host ({_u4cfg.get('sf2_home', 7)}th)"),
                    (_u4cfg.get("sf2_away", 8), f"SF2 away ({_u4cfg.get('sf2_away', 8)}th)"),
                ]
                _u4_entries = [
                    (_u4_sorted[_pos - 1], _role)
                    for _pos, _role in _u4_pos_roles
                    if len(_u4_sorted) >= _pos
                ]
                if _u4_entries:
                    st.divider()
                    st.markdown("### 🏅 Conference League Play-offs — Projected Entries")
                    st.caption(_u4cfg.get("caption", ""))
                    _u4_rows_html = ""
                    for _u4row, _u4role in _u4_entries:
                        _u4t = _u4row.get("strTeam", "")
                        _u4b = _u4row.get("strBadge", "")
                        _u4i = (f"<img src='{_u4b}' style='height:20px;vertical-align:middle;"
                                f"margin-right:6px'>" if _u4b else "")
                        _u4_rows_html += (
                            f"<tr>"
                            f"<td style='padding:6px 10px'>{_u4i}<b>{_u4t}</b></td>"
                            f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u4role}</td>"
                            f"</tr>"
                        )
                    st.markdown(
                        "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                        "<thead><tr style='border-bottom:1px solid #444'>"
                        "<th style='padding:6px 10px;text-align:left'>Team</th>"
                        "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                        f"</tr></thead><tbody>{_u4_rows_html}</tbody></table>",
                        unsafe_allow_html=True,
                    )

            # ── UECL 8-team Play-offs (e.g. San Marino) ──────────────────────
            _u8cfg = cfg.get("uecl_8team_playoff")
            if _u8cfg:
                _u8s = sorted(standings, key=lambda r: int(r.get("intRank", 99)))
                _u8_roles = {
                    2: "QF seed (2nd)", 3: "QF seed (3rd)", 5: "QF seed (5th)",
                    6: "QF seed (6th)", 7: "QF seed (7th)", 8: "QF seed (8th)",
                    9: "R1 home (9th)", 10: "R1 home (10th)",
                    11: "R1 away (11th)", 12: "R1 away (12th)",
                }
                _u8_entries = [
                    (_u8s[p - 1], _u8_roles[p])
                    for p in [2, 3, 5, 6, 7, 8, 9, 10, 11, 12]
                    if len(_u8s) >= p
                ]
                if _u8_entries:
                    st.divider()
                    st.markdown("### 🏅 Conference League Play-offs — Projected Entries")
                    st.caption(_u8cfg.get("caption", ""))
                    _u8_html = ""
                    for _u8r, _u8role in _u8_entries:
                        _t = _u8r.get("strTeam", "")
                        _b = _u8r.get("strBadge", "")
                        _i = f"<img src='{_b}' style='height:20px;vertical-align:middle;margin-right:6px'>" if _b else ""
                        _u8_html += (f"<tr><td style='padding:6px 10px'>{_i}<b>{_t}</b></td>"
                                     f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u8role}</td></tr>")
                    st.markdown(
                        "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                        "<thead><tr style='border-bottom:1px solid #444'>"
                        "<th style='padding:6px 10px;text-align:left'>Team</th>"
                        "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                        f"</tr></thead><tbody>{_u8_html}</tbody></table>",
                        unsafe_allow_html=True,
                    )

            # ── Projected groups (regular season still running) ──────────────
            _nc = cfg.get("n_champ") or (4 if cfg.get("final_four") else None)
            if _nc:
                _nm       = cfg.get("n_mid") or 0
                _pf       = cfg.get("pts_factor", 1.0)
                _sorted_st = sorted(standings, key=lambda r: int(r.get("intRank", 99)))
                _pts_dir  = cfg.get("pts_round", "down")
                _pf_note  = {0.0: "⚠️ Points reset to zero at split",
                             0.5: ("⚠️ Points halved (rounded up) at split" if _pts_dir == "up"
                                   else "⚠️ Points halved (rounded down) at split")}.get(_pf, "")

                st.divider()
                if cfg.get("final_four"):
                    st.markdown("### 📊 Projected Final Four")
                    st.caption("Top 4 by current table position — subject to change")
                    _ff_zones = _ls.get("final_four", {})
                    _render_table(_table_rows(_sorted_st[:4], zones=_ff_zones))
                else:
                    st.markdown("### 📊 Projected Groups")
                    st.caption("Based on current standings — regular season still running, groups not yet confirmed")

                    st.markdown("#### 🏆 Championship Group")
                    if _pf_note:
                        st.caption(_pf_note)
                    _render_table(_table_rows(_sorted_st[:_nc], zones=_spot_zones))

                    if _nm:
                        st.markdown(f"#### 🔵 {_mid_label}")
                        _render_table(_table_rows(_sorted_st[_nc:_nc + _nm], zones=_spot_zones))

                    if not cfg.get("champ_only"):
                        st.markdown("#### ⚠️ Relegation Group")
                        _render_table(_table_rows(_sorted_st[_nc + _nm:], zones=_spot_zones))

        if split_info:
            tbs = cfg.get("tiebreakers", ["gd", "gf"])[:8]
            tb_text = "; ".join(f"{i+1}) {_TB_LABELS.get(r, r)}" for i, r in enumerate(tbs))
            st.caption(f"Regular season tiebreakers: {tb_text}")

    # ── Projections ──────────────────────────────────────────────────────────
    with tab_proj:
        if not remaining_fixtures and not split_info:
            st.info("The season is complete — no remaining fixtures to simulate.")
        elif split_info:
            champ_fix = conference_fixtures(remaining_fixtures, split_info["champ_teams"])
            if not champ_fix:
                # API hasn't loaded post-split fixtures yet — generate full round-robin
                champ_fix = _roundrobin_fixtures(sorted(split_info["champ_teams"]))
            mid_fix = conference_fixtures(remaining_fixtures, split_info.get("mid_teams") or set())
            if not mid_fix and split_info.get("mid_teams"):
                mid_fix = _roundrobin_fixtures(sorted(split_info["mid_teams"]))
            relg_fix = conference_fixtures(remaining_fixtures, split_info["relg_teams"])
            if not relg_fix and split_info.get("relg_teams"):
                relg_fix = _roundrobin_fixtures(sorted(split_info["relg_teams"]))
            sim_key = (league_id, season, n_sim, home_advantage, len(champ_fix))
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
                    probs_mid = (
                        simulate_season(
                            standings=split_info["mid_current"],
                            remaining_fixtures=mid_fix,
                            ratings=ratings_df,
                            n_sim=n_sim,
                            home_advantage=home_advantage,
                            tiebreakers=_tiebreakers,
                            played_fixtures=played_fixtures,
                        ) if split_info.get("mid_teams") and split_info["mid_current"]
                        else None
                    )
                    probs_relg = (
                        simulate_season(
                            standings=split_info["relg_current"],
                            remaining_fixtures=relg_fix,
                            ratings=ratings_df,
                            n_sim=n_sim,
                            home_advantage=home_advantage,
                            tiebreakers=_tiebreakers,
                            played_fixtures=played_fixtures,
                        ) if split_info.get("relg_current")
                        else None
                    )
                st.session_state["sim_results"] = (probs_champ, probs_mid, probs_relg)
                st.session_state["sim_key"] = sim_key

            if "sim_results" in st.session_state:
                probs_champ, probs_mid, probs_relg = st.session_state["sim_results"]
                champ_exp_pts = _compute_expected_pts(split_info["champ_current"], champ_fix, ratings_df, home_advantage)
                mid_exp_pts   = (_compute_expected_pts(split_info["mid_current"], mid_fix, ratings_df, home_advantage)
                                 if split_info.get("mid_teams") else None)
                relg_exp_pts  = (_compute_expected_pts(split_info["relg_current"], relg_fix, ratings_df, home_advantage)
                                 if split_info.get("relg_current") else None)
                # Use pre-computed zones (same source as Current Table)
                st.markdown("### 🏆 Championship Round")
                st.markdown(_conf_progress_html(
                    conference_fixtures(played_fixtures,    split_info["champ_teams"]),
                    conference_fixtures(remaining_fixtures, split_info["champ_teams"]),
                ), unsafe_allow_html=True)
                if not probs_champ.empty:
                    render_prob_table(probs_champ, badge_lookup, champ_exp_pts,
                                      status_map=_champ_zones)
                    render_zone_table(probs_champ, split_info["champ_current"], cfg.get("zones"))
                if split_info.get("mid_teams") and probs_mid is not None and not probs_mid.empty:
                    st.markdown(f"### 🔵 {_mid_label}")
                    st.markdown(_conf_progress_html(
                        conference_fixtures(played_fixtures,    split_info["mid_teams"]),
                        conference_fixtures(remaining_fixtures, split_info["mid_teams"]),
                    ), unsafe_allow_html=True)
                    render_prob_table(probs_mid, badge_lookup, mid_exp_pts,
                                      status_map=_mid_zones)
                    render_zone_table(probs_mid, split_info["mid_current"], cfg.get("zones"))
                if split_info.get("relg_current") and probs_relg is not None and not cfg.get("champ_only"):
                    st.markdown("### ⚠️ Relegation Round")
                    st.markdown(_conf_progress_html(
                        conference_fixtures(played_fixtures,    split_info["relg_teams"]),
                        conference_fixtures(remaining_fixtures, split_info["relg_teams"]),
                    ), unsafe_allow_html=True)
                    if not probs_relg.empty:
                        render_prob_table(probs_relg, badge_lookup, relg_exp_pts,
                                          status_map=_relg_zones)
                        render_zone_table(probs_relg, split_info["relg_current"], cfg.get("zones"))

                # ── UECL Play-offs simulation (split leagues) ─────────────
                if cfg.get("uecl_playoff") and not probs_champ.empty and probs_relg is not None and not probs_relg.empty:
                    # Bye = current 5th in championship (avoids picking same team as 1st-4th)
                    _cc = split_info.get("champ_current", [])
                    _cc_sorted = sorted(_cc, key=lambda r: int(r.get("intRank", 99)))
                    _pred_bye  = (_cc_sorted[4]["strTeam"] if len(_cc_sorted) >= 5 else None)
                    _pred_sf_a = (probs_relg["1"].idxmax()
                                  if "1" in probs_relg.columns else None)
                    # Exclude sf_a from pool when picking 2nd to avoid duplicates
                    _pred_sf_b = (probs_relg["2"].drop(index=_pred_sf_a, errors="ignore").idxmax()
                                  if "2" in probs_relg.columns and _pred_sf_a else None)
                    if _pred_bye and _pred_sf_a and _pred_sf_b:
                        st.divider()
                        st.markdown("### 🏅 Conference League Play-offs — Projected Entries")
                        st.caption(
                            "7th-placed team (Relegation Group winner) hosts 8th-placed team in a one-legged semi-final. "
                            "The winner meets 5th-placed team (Championship Group) in a two-legged final, "
                            "with 5th hosting the second leg. Winner qualifies for UECL QR2."
                        )
                        _uecl_sim_key = ("uecl_split", league_id, season, n_sim,
                                         _pred_bye, _pred_sf_a, _pred_sf_b)
                        if st.session_state.get("uecl_split_key") != _uecl_sim_key:
                            with st.spinner("Simulating Conference League play-offs…"):
                                _uecl_df = simulate_uecl_playoff(
                                    _pred_bye, _pred_sf_a, _pred_sf_b, ratings_df, n_sim,
                                    home_advantage=home_advantage)
                            st.session_state["uecl_split_results"] = _uecl_df
                            st.session_state["uecl_split_key"] = _uecl_sim_key
                        if "uecl_split_results" in st.session_state:
                            _uecl_df = st.session_state["uecl_split_results"]
                            _uecl_winner = _uecl_df["Winner %"].idxmax()
                            _uecl_rows = ""
                            for _ui_idx, _ur in _uecl_df.iterrows():
                                _ut = _ur["Team"]
                                _ub = badge_lookup.get(_ut, "")
                                _uimg = (f"<img src='{_ub}' style='height:20px;"
                                         f"vertical-align:middle;margin-right:6px'>"
                                         if _ub else "")
                                _usf = _ur["SF Win %"]
                                _usf_cell = ("-" if str(_usf) == "-"
                                             else f"{_usf:.1f}%")
                                _ustatus = ("UECL – QR2" if _ui_idx == _uecl_winner else "")
                                _ustatus_style = ("color:#1a73e8;font-weight:bold"
                                                  if _ustatus else "")
                                _uecl_rows += (
                                    f"<tr>"
                                    f"<td style='padding:6px 10px'>{_uimg}<b>{_ut}</b></td>"
                                    f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>"
                                    f"{_ur['Role']}</td>"
                                    f"<td style='padding:6px 10px;text-align:right'>"
                                    f"{_usf_cell}</td>"
                                    f"<td style='padding:6px 10px;text-align:right;"
                                    f"font-weight:bold'>{_ur['Winner %']:.1f}%</td>"
                                    f"<td style='padding:6px 10px;{_ustatus_style}'>"
                                    f"{_ustatus}</td>"
                                    f"</tr>"
                                )
                            st.markdown(
                                "<table style='width:100%;border-collapse:collapse;"
                                "font-family:sans-serif'>"
                                "<thead><tr style='border-bottom:1px solid #444'>"
                                "<th style='padding:6px 10px;text-align:left'>Team</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;"
                                "font-size:12px'>Role</th>"
                                "<th style='padding:6px 10px;text-align:right;color:#888'>"
                                "SF Win %</th>"
                                "<th style='padding:6px 10px;text-align:right;color:#888'>"
                                "Winner %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888'>"
                                "Status</th>"
                                f"</tr></thead><tbody>{_uecl_rows}</tbody></table>",
                                unsafe_allow_html=True,
                            )
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
                # Use pre-computed _main_zones (same source as Current Table)
                render_prob_table(st.session_state["sim_results"], badge_lookup, exp_pts,
                                  status_map=_main_zones, team_overrides=_team_overrides)

                # ── Projected groups by probability (pre-split leagues) ───────
                _nc = cfg.get("n_champ") or (4 if cfg.get("final_four") else None)
                # Zone probabilities: show here for simple leagues; moved below play-offs for split leagues
                if not _nc or cfg.get("final_four"):
                    render_zone_table(st.session_state["sim_results"], standings,
                                      cfg.get("zones") or _auto_zones(cfg.get("european_spots"), _main_zones))
                if _nc:
                    _nm      = cfg.get("n_mid") or 0
                    probs_df = st.session_state["sim_results"]
                    n_total  = len(standings)

                    def _proj_group_table(teams_list, pos_str_list, status_map=None):
                        """Show the predicted group members with per-position probabilities."""
                        pos_labels = [f"#{p}" for p in pos_str_list]
                        rows = []
                        for i, team in enumerate(teams_list, start=1):
                            if team not in probs_df.index:
                                continue
                            row = {"Badge": badge_lookup.get(team, ""), "Team": team}
                            for ps, lbl in zip(pos_str_list, pos_labels):
                                row[lbl] = float(probs_df.loc[team, ps]) * 100 if ps in probs_df.columns else 0.0
                            if status_map:
                                row["Status"] = (status_map or {}).get(i, "")
                            rows.append(row)
                        if not rows:
                            return
                        _df = pd.DataFrame(rows)
                        _style_cols = pos_labels
                        _styled = (
                            _df.style
                            .hide(axis="index")
                            .apply(_green_col, axis=0, subset=_style_cols)
                            .format("{:.1f}%", subset=_style_cols)
                            .set_properties(subset=["Team"], **{"font-weight": "bold"})
                        )
                        _col_cfg = {
                            "Badge": st.column_config.ImageColumn("", width=32),
                            "Team":  st.column_config.TextColumn("Team", width=170),
                        }
                        for lbl in pos_labels:
                            _col_cfg[lbl] = st.column_config.TextColumn(lbl, width=52)
                        if status_map:
                            _col_cfg["Status"] = st.column_config.TextColumn("Status", width=130)
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
                    if not cfg.get("final_four"):
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
                                              status_map=_main_zones,
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
                            render_prob_table(st.session_state["po_sims"][_po_r], badge_lookup,
                                              status_map=_relg_zones,
                                              title="Relegation play-out finish probabilities")

                        # ── UECL Play-offs ────────────────────────────────────────────
                        if (cfg.get("uecl_playoff")
                                and p_champ is not None and p_relg is not None
                                and _po_c in st.session_state.get("po_sims", {})
                                and _po_r in st.session_state.get("po_sims", {})):
                            _champ_sim = st.session_state["po_sims"][_po_c]
                            _relg_sim  = st.session_state["po_sims"][_po_r]
                            # Bye = current 5th in championship (avoids duplicate picks)
                            _cc2 = sorted(split_info.get("champ_current", []),
                                          key=lambda r: int(r.get("intRank", 99)))
                            _pred_bye  = (_cc2[4]["strTeam"] if len(_cc2) >= 5 else None)
                            _pred_sf_a = (_relg_sim["1"].idxmax()
                                          if "1" in _relg_sim.columns else None)
                            # Exclude sf_a from pool when picking 2nd to avoid duplicates
                            _pred_sf_b = (_relg_sim["2"].drop(index=_pred_sf_a, errors="ignore").idxmax()
                                          if "2" in _relg_sim.columns and _pred_sf_a else None)
                            if _pred_bye and _pred_sf_a and _pred_sf_b:
                                st.divider()
                                st.markdown("### 🏅 Conference League Play-offs — Predicted Entries")
                                st.caption(
                                    "7th-placed team (Relegation Group winner) hosts 8th-placed team in a one-legged semi-final. "
                                    "The winner meets 5th-placed team (Championship Group) in a two-legged final, "
                                    "with 5th hosting the second leg. Winner qualifies for UECL QR2."
                                )
                                _pred_entries = [
                                    (_pred_bye,  "Bye to Final (hosts leg 2)"),
                                    (_pred_sf_a, "SF host (7th)"),
                                    (_pred_sf_b, "SF away (8th)"),
                                ]
                                _upo_pred_rows = ""
                                for _pt, _pr in _pred_entries:
                                    _pb = badge_lookup.get(_pt, "")
                                    _pi = (f"<img src='{_pb}' style='height:20px;"
                                           f"vertical-align:middle;margin-right:6px'>"
                                           if _pb else "")
                                    _pp_status = "UECL – QR2" if _pt == _pred_bye else ""
                                    _pp_sstyle = "color:#1a73e8;font-weight:bold" if _pp_status else ""
                                    _upo_pred_rows += (
                                        f"<tr>"
                                        f"<td style='padding:6px 10px'>{_pi}<b>{_pt}</b></td>"
                                        f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>"
                                        f"{_pr}</td>"
                                        f"<td style='padding:6px 10px;{_pp_sstyle}'>{_pp_status}</td>"
                                        f"</tr>"
                                    )
                                st.markdown(
                                    "<table style='width:100%;border-collapse:collapse;"
                                    "font-family:sans-serif'>"
                                    "<thead><tr style='border-bottom:1px solid #444'>"
                                    "<th style='padding:6px 10px;text-align:left'>Team</th>"
                                    "<th style='padding:6px 10px;text-align:left;color:#888;"
                                    "font-size:12px'>Role</th>"
                                    "<th style='padding:6px 10px;text-align:left;color:#888'>"
                                    "Status</th>"
                                    f"</tr></thead><tbody>{_upo_pred_rows}</tbody></table>",
                                    unsafe_allow_html=True,
                                )

                # ── Champ vs Mid/Relg group European Play-off (Predictions) ──
                _cmp2 = cfg.get("champ_mid_playoff")
                if _cmp2 and split_info and not probs_champ.empty:
                    _cmp2_away_conf = _cmp2.get("away_conf", "mid")
                    _cmp2_away_probs = (probs_relg if _cmp2_away_conf == "relg" else probs_mid)
                    if _cmp2_away_probs is not None and not _cmp2_away_probs.empty:
                        _cmp2_pos_str = str(_cmp2.get("champ_pos", 5))
                        _cmp2_away_pos_str = str(_cmp2.get("away_pos", 1))
                        _cmp2_home = (probs_champ[_cmp2_pos_str].idxmax()
                                      if _cmp2_pos_str in probs_champ.columns else None)
                        _cmp2_away = (_cmp2_away_probs[_cmp2_away_pos_str].idxmax()
                                      if _cmp2_away_pos_str in _cmp2_away_probs.columns else None)
                        _cmp2_away_role = _cmp2.get(
                            "away_label",
                            f"winner of {_mid_label}" if _cmp2_away_conf == "mid"
                            else "1st (Relegation Round)",
                        )
                    if _cmp2_home and _cmp2_away:
                        _cmp2_fix = [{"strHomeTeam": _cmp2_home, "strAwayTeam": _cmp2_away}]
                        _cmp2_odds = fixture_odds(_cmp2_fix, ratings_df,
                                                  home_advantage=home_advantage)
                        _cmp2_hw = (_cmp2_odds[0]["home_win"] * 100 if _cmp2_odds else 50.0)
                        _cmp2_aw = (_cmp2_odds[0]["away_win"] * 100 if _cmp2_odds else 50.0)
                        _cmp2_draw = (_cmp2_odds[0]["draw"] * 100 if _cmp2_odds else 0.0)
                        _cmp2_winner = _cmp2_home if _cmp2_hw >= _cmp2_aw else _cmp2_away
                        _cmp2_winner_spot = _cmp2.get("winner_spot", "UECL - QR2")
                        st.divider()
                        st.markdown("### 🏅 European Play-off — Predicted Entries")
                        st.caption(_cmp2.get("caption", ""))
                        _cmp2_entries = [
                            (_cmp2_home, f"Home — {_cmp2.get('champ_pos')}th (Championship Round)",
                             _cmp2_hw, _cmp2_draw),
                            (_cmp2_away, f"Away — {_cmp2_away_role}",
                             _cmp2_aw, _cmp2_draw),
                        ]
                        _cmp2_rows_html = ""
                        for _c2t, _c2role, _c2wp, _ in _cmp2_entries:
                            _c2b = badge_lookup.get(_c2t, "")
                            _c2i = (f"<img src='{_c2b}' style='height:20px;"
                                    f"vertical-align:middle;margin-right:6px'>"
                                    if _c2b else "")
                            _c2st = _cmp2_winner_spot if _c2t == _cmp2_winner else ""
                            _c2css = "color:#1a73e8;font-weight:bold" if _c2st else ""
                            _c2wp_str = f"{_c2wp:.1f}%"
                            _cmp2_rows_html += (
                                f"<tr>"
                                f"<td style='padding:6px 10px'>{_c2i}<b>{_c2t}</b></td>"
                                f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_c2role}</td>"
                                f"<td style='padding:6px 10px;color:#555'>{_c2wp_str}</td>"
                                f"<td style='padding:6px 10px;{_c2css}'>{_c2st}</td>"
                                f"</tr>"
                            )
                        st.markdown(
                            "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                            "<thead><tr style='border-bottom:1px solid #444'>"
                            "<th style='padding:6px 10px;text-align:left'>Team</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888'>Win %</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                            f"</tr></thead><tbody>{_cmp2_rows_html}</tbody></table>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"Draw % (→ extra time / penalties): {_cmp2_draw:.1f}%")

                # Zone probabilities for split/playoff leagues (shown after play-offs)
                if _nc and not cfg.get("final_four"):
                    render_zone_table(st.session_state["sim_results"], standings,
                                      cfg.get("zones") or _auto_zones(cfg.get("european_spots"), _main_zones))

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
                        st.markdown("### 📊 Projected Final Four — Title Probabilities")
                        st.caption(
                            "Draw pairings: Seed 1 & Seed 2 (1st/2nd) cannot meet in the semi-finals. "
                            "Semi-final tie → higher-ranked team advances. Final tie → extra time + penalties."
                        )
                        _ff_status = _ls.get("final_four", {})
                        _STATUS_COLORS = {
                            "ucl":          "#1a73e8",
                            "uel":          "#f9ab00",
                            "uecl":         "#34a853",
                            "conference":   "#34a853",
                            "relegation":   "#ea4335",
                            "championship": "#2e7d32",
                            "final four":   "#2e7d32",
                        }
                        def _ff_status_html(status):
                            sl = status.lower()
                            color = next((c for k, c in _STATUS_COLORS.items() if k in sl), "#cccccc")
                            return f"<span style='color:{color};font-weight:bold'>{status}</span>"

                        seed_label = {teams_4[0]: "🥇 Seed 1", teams_4[1]: "🥈 Seed 2",
                                      teams_4[2]: "Unseeded", teams_4[3]: "Unseeded"}
                        rows_html = ""
                        for _ff_rank, (_, row) in enumerate(ff_df.iterrows(), start=1):
                            team   = row["Team"]
                            badge  = badge_lookup.get(team, "")
                            seed   = seed_label.get(team, "")
                            img    = f"<img src='{badge}' style='height:20px;vertical-align:middle;margin-right:6px'>" if badge else ""
                            status = _ff_status.get(_ff_rank, "")
                            rows_html += (
                                f"<tr>"
                                f"<td style='padding:6px 10px'>{img}<b>{team}</b></td>"
                                f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{seed}</td>"
                                f"<td style='padding:6px 10px;text-align:right'>{row['SF Win %']}%</td>"
                                f"<td style='padding:6px 10px;text-align:right;font-weight:bold'>{row['Title %']}%</td>"
                                f"<td style='padding:6px 10px'>{_ff_status_html(status) if status else ''}</td>"
                                f"</tr>"
                            )
                        st.markdown(
                            "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                            "<thead><tr style='border-bottom:1px solid #444'>"
                            "<th style='padding:6px 10px;text-align:left'>Team</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Seed</th>"
                            "<th style='padding:6px 10px;text-align:right;color:#888'>SF Win %</th>"
                            "<th style='padding:6px 10px;text-align:right;color:#888'>Title %</th>"
                            "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                            f"</tr></thead><tbody>{rows_html}</tbody></table>",
                            unsafe_allow_html=True,
                        )

    # ── Manual Projections ────────────────────────────────────────────────────
    with tab_manual:
        # ── Shared helpers ────────────────────────────────────────────────────
        st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-secondary"] {
    height: 3rem !important;
    line-height: 1 !important;
}
</style>
""", unsafe_allow_html=True)

        _pred_col_cfg = {
            "Rd":   st.column_config.NumberColumn("Rd",   width="small"),
            "HB":   st.column_config.ImageColumn("",      width="small"),
            "Home": st.column_config.TextColumn("Home",   width="medium"),
            "HG":   st.column_config.NumberColumn("HG",   min_value=0, max_value=20, step=1, width="small"),
            "AG":   st.column_config.NumberColumn("AG",   min_value=0, max_value=20, step=1, width="small"),
            "Away": st.column_config.TextColumn("Away",   width="medium"),
            "AB":   st.column_config.ImageColumn("",      width="small"),
        }
        _upd_col_cfg = {
            "Pos":   st.column_config.NumberColumn("Pos",  width="small"),
            "Δ":     st.column_config.TextColumn("Δ",      width="small"),
            "Badge": st.column_config.ImageColumn("",       width="small"),
            "Team":  st.column_config.TextColumn("Team"),
            "P":     st.column_config.NumberColumn("P",     width="small"),
            "GD":    st.column_config.TextColumn("GD",      width="small"),
            "Pts":   st.column_config.NumberColumn("Pts",   width="small"),
        }

        def _style_rounds(df):
            unique_rds = list(dict.fromkeys(df["Rd"].tolist()))
            rd_idx = {r: i for i, r in enumerate(unique_rds)}
            bg = ["", "background-color: #f0f4ff"]
            styles = pd.DataFrame("", index=df.index, columns=df.columns)
            for row_i, rd in enumerate(df["Rd"].tolist()):
                styles.iloc[row_i] = bg[rd_idx[rd] % 2]
            return styles

        def _build_fix_df(fixtures):
            rows = []
            for f in sorted(fixtures,
                            key=lambda x: (int(x.get("intRound", 0) or 0),
                                           x.get("dateEvent", ""), x.get("strTime", ""))):
                rows.append({
                    "Rd":   int(f.get("intRound", 0) or 0),
                    "HB":   badge_lookup.get(f.get("strHomeTeam", ""), ""),
                    "Home": f.get("strHomeTeam", ""),
                    "HG":   pd.NA, "AG": pd.NA,
                    "Away": f.get("strAwayTeam", ""),
                    "AB":   badge_lookup.get(f.get("strAwayTeam", ""), ""),
                })
            df = pd.DataFrame(rows)
            df["HG"] = df["HG"].astype(pd.Int64Dtype())
            df["AG"] = df["AG"].astype(pd.Int64Dtype())
            return df

        def _upd_st_rows(base_st, updated):
            orig_rank = {r["strTeam"]: int(r.get("intRank", 0)) for r in base_st}
            rows = []
            for row in sorted(updated, key=lambda r: int(r.get("intRank", 99))):
                new_rank = int(row.get("intRank", 0))
                delta    = orig_rank.get(row["strTeam"], new_rank) - new_rank
                gd       = int(row.get("intGoalDifference", 0))
                rows.append({
                    "Pos":   new_rank,
                    "Δ":     (f"▲{delta}" if delta > 0 else (f"▼{abs(delta)}" if delta < 0 else "—")),
                    "Badge": row.get("strBadge") or "",
                    "Team":  row.get("strTeam", ""),
                    "P":     int(row.get("intPlayed", 0)),
                    "GD":    f"+{gd}" if gd > 0 else str(gd),
                    "Pts":   int(row.get("intPoints", 0)),
                })
            return rows

        def _conf_editor(conf_key, conf_fixtures, conf_standings, conf_zones,
                         tiebreaker_key="tiebreakers", relative_zones=False):
            """Fixture editor + updated standings + simulation for one conference."""
            ver_key_c   = f"manual_pred_ver_{league_id}_{season}_{conf_key}"
            sim_store_c = f"manual_sim_{league_id}_{season}_{conf_key}"
            if ver_key_c not in st.session_state:
                st.session_state[ver_key_c] = 0

            if not conf_fixtures:
                st.info("All fixtures in this round are completed.")
                _render_table(_table_rows(conf_standings, zones=conf_zones,
                                          relative_zones=relative_zones))
                return

            editor_key_c = f"pred_editor_{league_id}_{season}_{conf_key}_{st.session_state[ver_key_c]}"
            base_df_c    = _build_fix_df(conf_fixtures)
            height_c     = len(conf_standings) * 35 + 38
            styled_c     = base_df_c.style.apply(_style_rounds, axis=None).set_properties(
                subset=["Home", "Away"], **{"font-weight": "bold"})

            col_ed, col_tb = st.columns([5, 4])
            with col_ed:
                hdr_col_c, btn_col_c, _ = st.columns([2, 1, 3], vertical_alignment="center")
                metric_ph_c = hdr_col_c.empty()
                clear_ph_c  = btn_col_c.empty()
                edited_df_c = st.data_editor(
                    styled_c, column_config=_pred_col_cfg,
                    disabled=["Rd", "HB", "Home", "Away", "AB"],
                    use_container_width=True, hide_index=True,
                    height=height_c, key=editor_key_c,
                )

            filled_mask_c = edited_df_c[["HG", "AG"]].notna().all(axis=1)
            metric_ph_c.markdown(f"### Predicted: {int(filled_mask_c.sum())} / {len(conf_fixtures)}")
            if clear_ph_c.button("🗑 Clear", use_container_width=True,
                                 key=f"clear_{conf_key}_{league_id}_{season}"):
                st.session_state[ver_key_c] += 1
                st.session_state.pop(sim_store_c, None)
                st.rerun()

            fix_by_pair_c  = {(f.get("strHomeTeam"), f.get("strAwayTeam")): f
                               for f in conf_fixtures}
            pred_applied_c = []
            for _, row in edited_df_c[filled_mask_c].iterrows():
                pair = (row["Home"], row["Away"])
                if pair in fix_by_pair_c:
                    entry = dict(fix_by_pair_c[pair])
                    entry["pred_hg"] = int(row["HG"])
                    entry["pred_ag"] = int(row["AG"])
                    pred_applied_c.append(entry)

            predicted_pairs_c = {(f["strHomeTeam"], f["strAwayTeam"]) for f in pred_applied_c}
            unpredicted_fix_c = [f for f in conf_fixtures
                                  if (f.get("strHomeTeam"), f.get("strAwayTeam"))
                                  not in predicted_pairs_c]
            updated_st_c = _apply_predictions(conf_standings, pred_applied_c)

            with col_tb:
                st.markdown("### Updated standings")
                upd_df_c = pd.DataFrame(_upd_st_rows(conf_standings, updated_st_c))
                upd_styled_c = upd_df_c.style.set_properties(
                    subset=["Team", "Pts"], **{"font-weight": "bold"}
                ).set_properties(**{"font-size": "12px", "padding": "2px 6px"})
                st.dataframe(upd_styled_c, column_config=_upd_col_cfg,
                             use_container_width=True, hide_index=True, height=height_c)

            pred_fp_c = (
                tuple(sorted((f["strHomeTeam"], f["strAwayTeam"], f["pred_hg"], f["pred_ag"])
                             for f in pred_applied_c)),
                n_sim, home_advantage,
            )
            st.divider()
            st.markdown("### Projected final standings")
            cached_c = st.session_state.get(sim_store_c)
            if st.button(f"▶  Run {n_sim:,} simulations with predictions", type="primary",
                         use_container_width=True,
                         key=f"run_btn_{conf_key}_{league_id}_{season}"):
                with st.spinner(f"Running {n_sim:,} simulations…"):
                    manual_probs_c = simulate_season(
                        standings=updated_st_c,
                        remaining_fixtures=unpredicted_fix_c,
                        ratings=ratings_df, n_sim=n_sim,
                        home_advantage=home_advantage,
                        tiebreakers=cfg.get(tiebreaker_key, cfg.get("tiebreakers")),
                        played_fixtures=played_fixtures,
                    )
                st.session_state[sim_store_c] = {"probs": manual_probs_c, "fingerprint": pred_fp_c}
                cached_c = st.session_state[sim_store_c]

            if cached_c:
                if cached_c["fingerprint"] != pred_fp_c:
                    st.warning("⚠ Predictions changed since last run — press ▶ to update.")
                if not cached_c["probs"].empty:
                    manual_exp_c = _compute_expected_pts(
                        updated_st_c, unpredicted_fix_c, ratings_df, home_advantage)
                    render_prob_table(cached_c["probs"], badge_lookup, manual_exp_c,
                                      status_map=conf_zones)
                    render_zone_table(cached_c["probs"], updated_st_c,
                                      cfg.get("zones") or _auto_zones(
                                          cfg.get("european_spots"), _main_zones))
            else:
                st.info("Enter predictions above then press **▶ Run simulations**.")

        def _simple_editor(fix_list, st_list, sim_zones):
            """Full fixture editor + simulation for a non-split or regular-season view."""
            ver_key   = f"manual_pred_ver_{league_id}_{season}"
            sim_store = f"manual_sim_{league_id}_{season}"
            if ver_key not in st.session_state:
                st.session_state[ver_key] = 0

            base_df    = _build_fix_df(fix_list)
            editor_key = f"pred_editor_{league_id}_{season}_{st.session_state[ver_key]}"
            height_reg = len(st_list) * 35 + 38
            styled_base = base_df.style.apply(_style_rounds, axis=None).set_properties(
                subset=["Home", "Away"], **{"font-weight": "bold"})

            col_editor, col_table = st.columns([5, 4])
            with col_editor:
                hdr_col, btn_col, _ = st.columns([2, 1, 3], vertical_alignment="center")
                metric_ph = hdr_col.empty()
                clear_ph  = btn_col.empty()
                edited_df = st.data_editor(
                    styled_base, column_config=_pred_col_cfg,
                    disabled=["Rd", "HB", "Home", "Away", "AB"],
                    use_container_width=True, hide_index=True,
                    height=height_reg, key=editor_key,
                )

            filled_mask = edited_df[["HG", "AG"]].notna().all(axis=1)
            metric_ph.markdown(f"### Predicted: {int(filled_mask.sum())} / {len(fix_list)}")
            if clear_ph.button("🗑 Clear", use_container_width=True):
                st.session_state[ver_key] += 1
                st.session_state.pop(sim_store, None)
                st.rerun()

            fix_by_pair  = {(f.get("strHomeTeam"), f.get("strAwayTeam")): f for f in fix_list}
            pred_applied = []
            for _, row in edited_df[filled_mask].iterrows():
                pair = (row["Home"], row["Away"])
                if pair in fix_by_pair:
                    entry = dict(fix_by_pair[pair])
                    entry["pred_hg"] = int(row["HG"])
                    entry["pred_ag"] = int(row["AG"])
                    pred_applied.append(entry)

            predicted_pairs = {(f["strHomeTeam"], f["strAwayTeam"]) for f in pred_applied}
            unpredicted_fix = [f for f in fix_list
                               if (f.get("strHomeTeam"), f.get("strAwayTeam"))
                               not in predicted_pairs]
            updated_st = _apply_predictions(st_list, pred_applied)

            with col_table:
                st.markdown("### Updated standings")
                upd_df = pd.DataFrame(_upd_st_rows(st_list, updated_st))
                upd_styled = upd_df.style.set_properties(
                    subset=["Team", "Pts"], **{"font-weight": "bold"}
                ).set_properties(**{"font-size": "12px", "padding": "2px 6px"})
                st.dataframe(upd_styled, column_config=_upd_col_cfg,
                             use_container_width=True, hide_index=True, height=height_reg)

            pred_fingerprint = (
                tuple(sorted((f["strHomeTeam"], f["strAwayTeam"], f["pred_hg"], f["pred_ag"])
                             for f in pred_applied)),
                n_sim, home_advantage,
            )
            st.divider()
            st.markdown("### Projected final standings")
            cached = st.session_state.get(sim_store)
            if st.button(f"▶  Run {n_sim:,} simulations with predictions",
                         type="primary", use_container_width=True):
                with st.spinner(f"Running {n_sim:,} simulations…"):
                    manual_probs = simulate_season(
                        standings=updated_st, remaining_fixtures=unpredicted_fix,
                        ratings=ratings_df, n_sim=n_sim, home_advantage=home_advantage,
                        tiebreakers=cfg.get("tiebreakers"), played_fixtures=played_fixtures,
                    )
                st.session_state[sim_store] = {"probs": manual_probs, "fingerprint": pred_fingerprint}
                cached = st.session_state[sim_store]

            if cached:
                if cached["fingerprint"] != pred_fingerprint:
                    st.warning("⚠ Predictions changed since last run — press ▶ to update.")
                if not cached["probs"].empty:
                    manual_exp_pts = _compute_expected_pts(
                        updated_st, unpredicted_fix, ratings_df, home_advantage)
                    render_prob_table(cached["probs"], badge_lookup, manual_exp_pts,
                                      status_map=sim_zones)
                    render_zone_table(cached["probs"], updated_st,
                                      cfg.get("zones") or _auto_zones(
                                          cfg.get("european_spots"), _main_zones))
            else:
                st.info("Enter predictions above then press **▶ Run simulations**.")

        # ── Main tab dispatch ─────────────────────────────────────────────────
        if split_info:
            # Split in progress: championship + relegation editors, no regular standings
            st.markdown("### 🏆 Championship Round")
            _conf_editor(
                "champ",
                conference_fixtures(remaining_fixtures, split_info["champ_teams"]),
                split_info["champ_current"], _champ_zones,
                tiebreaker_key="champ_tiebreakers",
            )
            if split_info.get("relg_current") and not cfg.get("champ_only"):
                st.divider()
                st.markdown("### ⚠️ Relegation Round")
                _conf_editor(
                    "relg",
                    conference_fixtures(remaining_fixtures, split_info["relg_teams"]),
                    split_info["relg_current"], _relg_zones,
                    tiebreaker_key="tiebreakers", relative_zones=True,
                )

            # ── UECL 4-team Play-offs (split, Predictions) ───────────────
            _u4cfg_sp2 = cfg.get("uecl_4team_playoff")
            if _u4cfg_sp2 and _u4cfg_sp2.get("sf1_away_from_relg"):
                _u4_ch_c = st.session_state.get(f"manual_sim_{league_id}_{season}_champ", {})
                _u4_rl_c = st.session_state.get(f"manual_sim_{league_id}_{season}_relg", {})
                _u4_p_ch = _u4_ch_c.get("probs")
                _u4_p_rl = _u4_rl_c.get("probs")
                if (_u4_p_ch is not None and not _u4_p_ch.empty
                        and _u4_p_rl is not None and not _u4_p_rl.empty):
                    _s1h_p = str(_u4cfg_sp2.get("sf1_home", 4))
                    _s1a_p = str(_u4cfg_sp2.get("sf1_away", 1))
                    _s2h_p = str(_u4cfg_sp2.get("sf2_home", 5))
                    _s2a_p = str(_u4cfg_sp2.get("sf2_away", 6))
                    _sp_s1h = _u4_p_ch[_s1h_p].idxmax() if _s1h_p in _u4_p_ch.columns else None
                    _sp_s1a = _u4_p_rl[_s1a_p].idxmax() if _s1a_p in _u4_p_rl.columns else None
                    _sp_s2h = (_u4_p_ch[_s2h_p].drop(index=[t for t in [_sp_s1h] if t], errors="ignore").idxmax()
                               if _s2h_p in _u4_p_ch.columns else None)
                    _sp_s2a = (_u4_p_ch[_s2a_p].drop(index=[t for t in [_sp_s1h, _sp_s2h] if t], errors="ignore").idxmax()
                               if _s2a_p in _u4_p_ch.columns else None)
                    if _sp_s1h and _sp_s1a and _sp_s2h and _sp_s2a:
                        _sp_key = ("uecl_4team_split", league_id, season, n_sim,
                                   _sp_s1h, _sp_s1a, _sp_s2h, _sp_s2a)
                        if st.session_state.get("uecl_4team_key") != _sp_key:
                            with st.spinner("Simulating Conference League play-offs…"):
                                _sp_df = simulate_uecl_4team_playoff(
                                    _sp_s1h, _sp_s1a, _sp_s2h, _sp_s2a,
                                    ratings_df, n_sim, home_advantage=home_advantage,
                                    sf1_home_rank=int(_u4cfg_sp2.get("sf1_home_rank", 4)),
                                    sf1_away_rank=int(_u4cfg_sp2.get("sf1_away_rank", 7)),
                                    sf2_home_rank=int(_u4cfg_sp2.get("sf2_home_rank", 5)),
                                    sf2_away_rank=int(_u4cfg_sp2.get("sf2_away_rank", 6)),
                                )
                            st.session_state["uecl_4team_results"] = _sp_df
                            st.session_state["uecl_4team_key"] = _sp_key
                        _sp_df_d = st.session_state.get("uecl_4team_results")
                        if _sp_df_d is not None and not _sp_df_d.empty:
                            _sp_winner = _sp_df_d.iloc[0]["Team"]
                            _sp_spot   = _u4cfg_sp2.get("winner_spot", "UECL - QR1")
                            st.divider()
                            st.markdown("### 🏅 Conference League Play-offs — Predicted Entries")
                            st.caption(_u4cfg_sp2.get("caption", ""))
                            _sp_rows = ""
                            for _, _sp_r in _sp_df_d.iterrows():
                                _sp_t   = _sp_r["Team"]
                                _sp_b   = badge_lookup.get(_sp_t, "")
                                _sp_i   = (f"<img src='{_sp_b}' style='height:20px;"
                                           f"vertical-align:middle;margin-right:6px'>" if _sp_b else "")
                                _sp_st  = _sp_spot if _sp_t == _sp_winner else ""
                                _sp_css = "color:#1a73e8;font-weight:bold" if _sp_st else ""
                                _sp_rows += (
                                    f"<tr>"
                                    f"<td style='padding:6px 10px'>{_sp_i}<b>{_sp_t}</b></td>"
                                    f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_sp_r['Role']}</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_sp_r['SF Win %']}%</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_sp_r['Winner %']}%</td>"
                                    f"<td style='padding:6px 10px;{_sp_css}'>{_sp_st}</td>"
                                    f"</tr>"
                                )
                            st.markdown(
                                "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                                "<thead><tr style='border-bottom:1px solid #444'>"
                                "<th style='padding:6px 10px;text-align:left'>Team</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>SF Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                                f"</tr></thead><tbody>{_sp_rows}</tbody></table>",
                                unsafe_allow_html=True,
                            )

            # ── UECL 3-team Play-off (split, Predictions) ──────────────
            _u3cfg2 = cfg.get("uecl_3team_playoff")
            if _u3cfg2:
                _u3_ch_c = st.session_state.get(f"manual_sim_{league_id}_{season}_champ", {})
                _u3_rl_c = st.session_state.get(f"manual_sim_{league_id}_{season}_relg", {})
                _u3_p_ch = _u3_ch_c.get("probs")
                _u3_p_rl = _u3_rl_c.get("probs")
                if (_u3_p_ch is not None and not _u3_p_ch.empty
                        and _u3_p_rl is not None and not _u3_p_rl.empty):
                    _b_pos = str(_u3cfg2.get("bye_home", 4))
                    _a_pos = str(_u3cfg2.get("sf_home",  1))
                    _b2_pos = str(_u3cfg2.get("sf_away", 2))
                    _u3_bye = _u3_p_ch[_b_pos].idxmax()  if _b_pos  in _u3_p_ch.columns else None
                    _u3_sfa = _u3_p_rl[_a_pos].idxmax()  if _a_pos  in _u3_p_rl.columns else None
                    _u3_sfb = (_u3_p_rl[_b2_pos].drop(index=[t for t in [_u3_sfa] if t], errors="ignore").idxmax()
                               if _b2_pos in _u3_p_rl.columns else None)
                    if _u3_bye and _u3_sfa and _u3_sfb:
                        _u3_key2 = ("uecl_3team", league_id, season, n_sim, _u3_bye, _u3_sfa, _u3_sfb)
                        if st.session_state.get("uecl_3team_key") != _u3_key2:
                            with st.spinner("Simulating Conference League play-offs…"):
                                _u3_df2 = simulate_uecl_3team_playoff(
                                    _u3_bye, _u3_sfa, _u3_sfb,
                                    ratings_df, n_sim, home_advantage=home_advantage,
                                )
                            st.session_state["uecl_3team_results"] = _u3_df2
                            st.session_state["uecl_3team_key"] = _u3_key2
                        _u3_df_d = st.session_state.get("uecl_3team_results")
                        if _u3_df_d is not None and not _u3_df_d.empty:
                            _u3_winner2 = _u3_df_d.iloc[0]["Team"]
                            _u3_spot2   = _u3cfg2.get("winner_spot", "UECL - QR2")
                            st.divider()
                            st.markdown("### 🏅 Conference League Play-offs — Predicted Entries")
                            st.caption(_u3cfg2.get("caption", ""))
                            _u3_rows2 = ""
                            for _, _u3_r in _u3_df_d.iterrows():
                                _u3_t2   = _u3_r["Team"]
                                _u3_b2   = badge_lookup.get(_u3_t2, "")
                                _u3_i2   = (f"<img src='{_u3_b2}' style='height:20px;"
                                            f"vertical-align:middle;margin-right:6px'>" if _u3_b2 else "")
                                _u3_st2  = _u3_spot2 if _u3_t2 == _u3_winner2 else ""
                                _u3_css2 = "color:#1a73e8;font-weight:bold" if _u3_st2 else ""
                                _u3_rows2 += (
                                    f"<tr>"
                                    f"<td style='padding:6px 10px'>{_u3_i2}<b>{_u3_t2}</b></td>"
                                    f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u3_r['Role']}</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u3_r['SF Win %']}%</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u3_r['Final %']}%</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u3_r['Winner %']}%</td>"
                                    f"<td style='padding:6px 10px;{_u3_css2}'>{_u3_st2}</td>"
                                    f"</tr>"
                                )
                            st.markdown(
                                "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                                "<thead><tr style='border-bottom:1px solid #444'>"
                                "<th style='padding:6px 10px;text-align:left'>Team</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>SF Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Final %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                                f"</tr></thead><tbody>{_u3_rows2}</tbody></table>",
                                unsafe_allow_html=True,
                            )

            # ── UECL 5-team Play-off (split, Predictions) ────────────────────
            _u5cfg2 = cfg.get("uecl_5team_playoff")
            if _u5cfg2:
                _u5_ch_c = st.session_state.get(f"manual_sim_{league_id}_{season}_champ", {})
                _u5_rl_c = st.session_state.get(f"manual_sim_{league_id}_{season}_relg", {})
                _u5_p_ch = _u5_ch_c.get("probs")
                _u5_p_rl = _u5_rl_c.get("probs")
                if (_u5_p_ch is not None and not _u5_p_ch.empty
                        and _u5_p_rl is not None and not _u5_p_rl.empty):
                    _fh_p  = str(_u5cfg2.get("final_host", 3))
                    _q1h_p = str(_u5cfg2.get("qf1_home",   4))
                    _q1a_p = str(_u5cfg2.get("qf1_away",   2))
                    _q2h_p = str(_u5cfg2.get("qf2_home",   5))
                    _q2a_p = str(_u5cfg2.get("qf2_away",   1))
                    _u5_fh  = _u5_p_ch[_fh_p].idxmax()  if _fh_p  in _u5_p_ch.columns else None
                    _u5_q1h = (_u5_p_ch[_q1h_p].drop(index=[t for t in [_u5_fh] if t], errors="ignore").idxmax()
                               if _q1h_p in _u5_p_ch.columns else None)
                    _u5_q2h = (_u5_p_ch[_q2h_p].drop(index=[t for t in [_u5_fh, _u5_q1h] if t], errors="ignore").idxmax()
                               if _q2h_p in _u5_p_ch.columns else None)
                    _u5_q2a = _u5_p_rl[_q2a_p].idxmax()  if _q2a_p in _u5_p_rl.columns else None
                    _u5_q1a = (_u5_p_rl[_q1a_p].drop(index=[t for t in [_u5_q2a] if t], errors="ignore").idxmax()
                               if _q1a_p in _u5_p_rl.columns else None)
                    if all([_u5_fh, _u5_q1h, _u5_q2h, _u5_q2a, _u5_q1a]):
                        _u5_key2 = ("uecl_5team", league_id, season, n_sim,
                                    _u5_fh, _u5_q1h, _u5_q2h, _u5_q2a, _u5_q1a)
                        if st.session_state.get("uecl_5team_key") != _u5_key2:
                            with st.spinner("Simulating Conference League play-offs…"):
                                _u5_df2 = simulate_uecl_5team_playoff(
                                    _u5_fh, _u5_q1h, _u5_q2h, _u5_q2a, _u5_q1a,
                                    ratings_df, n_sim, home_advantage=home_advantage,
                                    qf1_home_rank=int(_u5cfg2.get("qf1_home_rank", 4)),
                                    qf1_away_rank=int(_u5cfg2.get("qf1_away_rank", 8)),
                                    qf2_home_rank=int(_u5cfg2.get("qf2_home_rank", 5)),
                                    qf2_away_rank=int(_u5cfg2.get("qf2_away_rank", 7)),
                                    final_host_rank=int(_u5cfg2.get("final_host_rank", 3)),
                                )
                            st.session_state["uecl_5team_results"] = _u5_df2
                            st.session_state["uecl_5team_key"] = _u5_key2
                        _u5_df_d = st.session_state.get("uecl_5team_results")
                        if _u5_df_d is not None and not _u5_df_d.empty:
                            _u5_winner = _u5_df_d.iloc[0]["Team"]
                            _u5_spot   = _u5cfg2.get("winner_spot", "UECL - QR1")
                            st.divider()
                            st.markdown("### 🏅 Conference League Play-offs — Predicted Entries")
                            st.caption(_u5cfg2.get("caption", ""))
                            _u5_rows2 = ""
                            for _, _u5_r in _u5_df_d.iterrows():
                                _u5_t2   = _u5_r["Team"]
                                _u5_b2   = badge_lookup.get(_u5_t2, "")
                                _u5_i2   = (f"<img src='{_u5_b2}' style='height:20px;"
                                            f"vertical-align:middle;margin-right:6px'>" if _u5_b2 else "")
                                _u5_st2  = _u5_spot if _u5_t2 == _u5_winner else ""
                                _u5_css2 = "color:#1a73e8;font-weight:bold" if _u5_st2 else ""
                                _qf_val  = _u5_r["QF Win %"]
                                _u5_rows2 += (
                                    f"<tr>"
                                    f"<td style='padding:6px 10px'>{_u5_i2}<b>{_u5_t2}</b></td>"
                                    f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u5_r['Role']}</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{'–' if _qf_val == '-' else f'{_qf_val}%'}</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u5_r['SF Win %']}{'%' if _u5_r['SF Win %'] != '-' else ''}</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u5_r['Winner %']}%</td>"
                                    f"<td style='padding:6px 10px;{_u5_css2}'>{_u5_st2}</td>"
                                    f"</tr>"
                                )
                            st.markdown(
                                "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                                "<thead><tr style='border-bottom:1px solid #444'>"
                                "<th style='padding:6px 10px;text-align:left'>Team</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>QF Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>SF Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                                f"</tr></thead><tbody>{_u5_rows2}</tbody></table>",
                                unsafe_allow_html=True,
                            )

        elif cfg.get("n_champ") and remaining_fixtures:
            # Regular season still running for a split league
            _simple_editor(remaining_fixtures, standings, _main_zones)

            # Show projected championship/relegation groups based on current standings
            n_champ_p = cfg["n_champ"]
            n_mid_p   = cfg.get("n_mid") or 0
            sorted_st = sorted(standings, key=lambda r: int(r.get("intRank", 99)))
            proj_champ = sorted_st[:n_champ_p]
            proj_mid   = sorted_st[n_champ_p:n_champ_p + n_mid_p] if n_mid_p else []
            proj_relg  = sorted_st[n_champ_p + n_mid_p:]

            st.divider()
            st.markdown("### 🏆 Projected Championship Round")
            st.caption(f"Projected top {n_champ_p} after round {cfg['split_round']} based on current standings")
            _render_table(_table_rows(proj_champ, zones=_champ_zones))
            if proj_mid:
                st.markdown(f"### 🔵 Projected {cfg.get('mid_label', 'Europa Play-off')}")
                _render_table(_table_rows(proj_mid, zones=_mid_zones))
            if proj_relg:
                st.markdown("### ⚠️ Projected Relegation Round")
                _render_table(_table_rows(proj_relg, zones=_relg_zones, relative_zones=True))

        elif not remaining_fixtures:
            st.info("The season is complete — no remaining fixtures to simulate.")

        else:
            # Simple non-split league
            _simple_editor(remaining_fixtures, standings, _main_zones)

            # ── UECL 4-team Play-offs (Predictions, non-split) ───────────────
            _u4cfg2 = cfg.get("uecl_4team_playoff")
            if _u4cfg2:
                _u4_sim_cache2 = st.session_state.get(f"manual_sim_{league_id}_{season}", {})
                _u4_probs2 = _u4_sim_cache2.get("probs")
                if _u4_probs2 is not None and not _u4_probs2.empty:
                    _u4_sf1h_pos = str(_u4cfg2.get("sf1_home", 5))
                    _u4_sf1a_pos = str(_u4cfg2.get("sf1_away", 9))
                    _u4_sf2h_pos = str(_u4cfg2.get("sf2_home", 7))
                    _u4_sf2a_pos = str(_u4cfg2.get("sf2_away", 8))
                    _u4_sf1h = (_u4_probs2[_u4_sf1h_pos].idxmax()
                                if _u4_sf1h_pos in _u4_probs2.columns else None)
                    _u4_sf1a = (_u4_probs2[_u4_sf1a_pos].drop(
                                    index=[t for t in [_u4_sf1h] if t], errors="ignore").idxmax()
                                if _u4_sf1a_pos in _u4_probs2.columns and _u4_sf1h else None)
                    _u4_sf2h = (_u4_probs2[_u4_sf2h_pos].drop(
                                    index=[t for t in [_u4_sf1h, _u4_sf1a] if t], errors="ignore").idxmax()
                                if _u4_sf2h_pos in _u4_probs2.columns else None)
                    _u4_sf2a = (_u4_probs2[_u4_sf2a_pos].drop(
                                    index=[t for t in [_u4_sf1h, _u4_sf1a, _u4_sf2h] if t], errors="ignore").idxmax()
                                if _u4_sf2a_pos in _u4_probs2.columns else None)
                    if _u4_sf1h and _u4_sf1a and _u4_sf2h and _u4_sf2a:
                        _u4_key2 = ("uecl_4team", league_id, season, n_sim,
                                    _u4_sf1h, _u4_sf1a, _u4_sf2h, _u4_sf2a)
                        if st.session_state.get("uecl_4team_key") != _u4_key2:
                            with st.spinner("Simulating Conference League play-offs…"):
                                _u4_df2 = simulate_uecl_4team_playoff(
                                    _u4_sf1h, _u4_sf1a, _u4_sf2h, _u4_sf2a,
                                    ratings_df, n_sim, home_advantage=home_advantage,
                                    sf1_home_rank=int(_u4_sf1h_pos),
                                    sf1_away_rank=int(_u4_sf1a_pos),
                                    sf2_home_rank=int(_u4_sf2h_pos),
                                    sf2_away_rank=int(_u4_sf2a_pos),
                                )
                            st.session_state["uecl_4team_results"] = _u4_df2
                            st.session_state["uecl_4team_key"] = _u4_key2
                        _u4_df_disp = st.session_state.get("uecl_4team_results")
                        if _u4_df_disp is not None and not _u4_df_disp.empty:
                            _u4_winner2 = _u4_df_disp.iloc[0]["Team"]
                            _u4_spot2   = _u4cfg2.get("winner_spot", "UECL - LS")
                            st.divider()
                            st.markdown("### 🏅 Conference League Play-offs — Predicted Entries")
                            st.caption(_u4cfg2.get("caption", ""))
                            _u4_rows2 = ""
                            for _, _u4r in _u4_df_disp.iterrows():
                                _u4t2   = _u4r["Team"]
                                _u4role2 = _u4r["Role"]
                                _u4sf2   = _u4r["SF Win %"]
                                _u4w2    = _u4r["Winner %"]
                                _u4b2 = badge_lookup.get(_u4t2, "")
                                _u4i2 = (f"<img src='{_u4b2}' style='height:20px;"
                                         f"vertical-align:middle;margin-right:6px'>"
                                         if _u4b2 else "")
                                _u4st2  = _u4_spot2 if _u4t2 == _u4_winner2 else ""
                                _u4css2 = "color:#1a73e8;font-weight:bold" if _u4st2 else ""
                                _u4_rows2 += (
                                    f"<tr>"
                                    f"<td style='padding:6px 10px'>{_u4i2}<b>{_u4t2}</b></td>"
                                    f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>"
                                    f"{_u4role2}</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u4sf2}%</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u4w2}%</td>"
                                    f"<td style='padding:6px 10px;{_u4css2}'>{_u4st2}</td>"
                                    f"</tr>"
                                )
                            st.markdown(
                                "<table style='width:100%;border-collapse:collapse;"
                                "font-family:sans-serif'>"
                                "<thead><tr style='border-bottom:1px solid #444'>"
                                "<th style='padding:6px 10px;text-align:left'>Team</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;"
                                "font-size:12px'>Role</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;"
                                "font-size:12px'>SF Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;"
                                "font-size:12px'>Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888'>"
                                "Status</th>"
                                f"</tr></thead><tbody>{_u4_rows2}</tbody></table>",
                                unsafe_allow_html=True,
                            )

            # ── UECL 8-team Play-offs (Predictions, non-split) ──────────────
            _u8cfg2 = cfg.get("uecl_8team_playoff")
            if _u8cfg2 and not cfg.get("uecl_4team_playoff"):
                _u8_probs2 = st.session_state.get(f"manual_sim_{league_id}_{season}", {}).get("probs")
                if _u8_probs2 is not None and not _u8_probs2.empty:
                    _u8_pos_order = [2, 3, 5, 6, 7, 8, 9, 10, 11, 12]
                    _u8_picks2 = {}
                    _u8_used2  = []
                    for _p in _u8_pos_order:
                        _col = str(_p)
                        if _col in _u8_probs2.columns:
                            _t = _u8_probs2[_col].drop(index=_u8_used2, errors="ignore").idxmax()
                            _u8_picks2[_p] = _t
                            _u8_used2.append(_t)
                    if len(_u8_picks2) == 10:
                        _u8_key2 = ("uecl_8team", league_id, season, n_sim,
                                    *[_u8_picks2[p] for p in _u8_pos_order])
                        if st.session_state.get("uecl_8team_key") != _u8_key2:
                            with st.spinner("Simulating Conference League play-offs…"):
                                _u8_df2 = simulate_uecl_8team_playoff(
                                    _u8_picks2[2], _u8_picks2[3], _u8_picks2[5],
                                    _u8_picks2[6], _u8_picks2[7], _u8_picks2[8],
                                    _u8_picks2[9], _u8_picks2[10], _u8_picks2[11], _u8_picks2[12],
                                    ratings_df, n_sim, home_advantage=home_advantage,
                                )
                            st.session_state["uecl_8team_results"] = _u8_df2
                            st.session_state["uecl_8team_key"] = _u8_key2
                        _u8_df_d = st.session_state.get("uecl_8team_results")
                        if _u8_df_d is not None and not _u8_df_d.empty:
                            _u8_winner2 = _u8_df_d.iloc[0]["Team"]
                            _u8_spot2   = _u8cfg2.get("winner_spot", "UECL - QR1")
                            st.divider()
                            st.markdown("### 🏅 Conference League Play-offs — Predicted Entries")
                            st.caption(_u8cfg2.get("caption", ""))
                            _u8_rows2 = ""
                            for _, _u8r2 in _u8_df_d.iterrows():
                                _u8t  = _u8r2["Team"]
                                _u8b  = badge_lookup.get(_u8t, "")
                                _u8i  = (f"<img src='{_u8b}' style='height:20px;"
                                         f"vertical-align:middle;margin-right:6px'>" if _u8b else "")
                                _u8st = _u8_spot2 if _u8t == _u8_winner2 else ""
                                _u8cs = "color:#1a73e8;font-weight:bold" if _u8st else ""
                                _u8_rows2 += (
                                    f"<tr>"
                                    f"<td style='padding:6px 10px'>{_u8i}<b>{_u8t}</b></td>"
                                    f"<td style='padding:6px 10px;color:#aaa;font-size:12px'>{_u8r2['Role']}</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u8r2['R1 Win %']}%</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u8r2['QF Win %']}%</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u8r2['SF Win %']}%</td>"
                                    f"<td style='padding:6px 10px;color:#555'>{_u8r2['Win %']}%</td>"
                                    f"<td style='padding:6px 10px;{_u8cs}'>{_u8st}</td>"
                                    f"</tr>"
                                )
                            st.markdown(
                                "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                                "<thead><tr style='border-bottom:1px solid #444'>"
                                "<th style='padding:6px 10px;text-align:left'>Team</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Role</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>R1 Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>QF Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>SF Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888;font-size:12px'>Win %</th>"
                                "<th style='padding:6px 10px;text-align:left;color:#888'>Status</th>"
                                f"</tr></thead><tbody>{_u8_rows2}</tbody></table>",
                                unsafe_allow_html=True,
                            )

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
        _zone_notes = cfg.get("zone_notes", {})
        # Invert {pos: label} → {label: [positions]} for display grouping
        _inv: dict[str, list] = {}
        for _p, _lbl in (_main_zones or {}).items():
            _inv.setdefault(_lbl, []).append(_p)
        raw_zones = _inv
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
