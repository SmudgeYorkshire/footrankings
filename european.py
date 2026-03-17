"""
UEFA European Competitions — Champions League, Europa League, Conference League.

Shows:
  • League Phase standings (computed from round 1-8 results, color-coded by zone)
  • Knockout stage results round-by-round (with H%/D%/A% for upcoming legs)
  • Visual knockout bracket (HTML, scrollable)
  • Qualifying results
"""

import os
import streamlit as st
import pandas as pd
from pathlib import Path

from config import EUROPEAN_COMPETITIONS, LEAGUES
from data_fetcher import SportsDBClient
from simulator import fixture_odds
from entrants_2026_27 import ENTRANTS as ENTRANTS_2026_27, STAGE_ORDER, QUALIFYING_DATES


@st.cache_data(ttl=3_600, show_spinner=False)
def _fetch_albania_top4(api_key: str) -> list[str]:
    """Return Albania 2025-26 top-4 team names ordered by current rank."""
    client = SportsDBClient(api_key)
    standings = client.get_standings(LEAGUES["Albanian Superliga"]["id"], "2025-2026")
    if not standings:
        return []
    return [
        r["strTeam"]
        for r in sorted(standings, key=lambda r: int(r.get("intRank", 99)))[:4]
    ]


def _resolve_dynamic(entries: list[dict], albania_top4: list[str]) -> list[dict]:
    """Replace dynamic placeholder entries with projected club names."""
    out = []
    ff_234_done = False
    for e in entries:
        dyn = e.get("dynamic")
        if dyn == "albania_ff_1":
            club = albania_top4[0] if albania_top4 else None
            out.append({**e, "club": club, "status": "projected" if club else "tbd"})
        elif dyn == "albania_ff_234" and not ff_234_done:
            ff_234_done = True
            for i, slot_route in enumerate(["Final Four 2nd (proj.)", "Final Four 3rd (proj.)", "Final Four 4th (proj.)"], 1):
                club = albania_top4[i] if len(albania_top4) > i else None
                out.append({**e, "club": club, "route": slot_route,
                             "status": "projected" if club else "tbd"})
        else:
            out.append(e)
    return out

_API_KEY = os.getenv("THESPORTSDB_API_KEY", "3")

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_CET = ZoneInfo("Europe/Berlin")

def _utc_to_cet(date_str: str, time_str: str) -> str:
    if not date_str or not time_str or time_str.startswith("00:00"):
        return date_str
    try:
        dt = datetime.strptime(f"{date_str} {time_str[:8]}", "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(_CET)
        return f"{dt.strftime('%d %b')} {dt.strftime('%H:%M')} CET"
    except ValueError:
        return date_str


# Display names for known intRound values (TheSportsDB omits strRound for these)
_ROUND_DISPLAY = {
    400:  "Qualifying",
    1128: "First Qualifying Round",
    128:  "Second Qualifying Round",
    125:  "Third Qualifying Round",
    64:   "Round of 64",
    32:   "Knockout Play-offs",
    16:   "Round of 16",
    8:    "Quarter-finals",
    4:    "Semi-finals",
    150:  "Semi-finals",
    2:    "Final",
    1:    "Final",
}

_ROUND_ORDER = {
    "knockout play-offs": 1, "knockout playoffs": 1,
    "round of 64": 1,
    "round of 32": 2,
    "round of 16": 3,
    "quarter-final": 4, "quarter-finals": 4,
    "semi-final": 5, "semi-finals": 5,
    "final": 6,
}


def _round_sort(label: str) -> int:
    return _ROUND_ORDER.get(label.lower(), 99)


def _round_key(f: dict) -> str:
    sr = (f.get("strRound") or "").strip()
    if sr and not sr.isdigit():
        return sr
    rnd = int(f.get("intRound", 0) or 0)
    return _ROUND_DISPLAY.get(rnd) or (f"Matchday {rnd}" if rnd else "Unknown")


def _intround(f: dict) -> int:
    return int(f.get("intRound", 0) or 0)


def _compute_league_standings(matches: list[dict], badge_lookup: dict) -> list[dict]:
    """Build W/D/L/Pts standings from completed match results."""
    teams: dict[str, dict] = {}
    for m in matches:
        home  = m.get("strHomeTeam", "")
        away  = m.get("strAwayTeam", "")
        hs_r  = m.get("intHomeScore")
        as_r  = m.get("intAwayScore")
        if hs_r in (None, "") or as_r in (None, ""):
            continue
        hs, as_ = int(hs_r), int(as_r)
        for t in (home, away):
            if t not in teams:
                teams[t] = {"strTeam": t, "strBadge": badge_lookup.get(t, ""),
                            "P": 0, "W": 0, "D": 0, "L": 0,
                            "GF": 0, "GA": 0, "GD": 0, "Pts": 0}
        teams[home]["P"]  += 1; teams[home]["GF"] += hs
        teams[home]["GA"] += as_; teams[home]["GD"] += hs - as_
        teams[away]["P"]  += 1; teams[away]["GF"] += as_
        teams[away]["GA"] += hs; teams[away]["GD"] += as_ - hs
        if hs > as_:
            teams[home]["W"] += 1; teams[home]["Pts"] += 3; teams[away]["L"] += 1
        elif as_ > hs:
            teams[away]["W"] += 1; teams[away]["Pts"] += 3; teams[home]["L"] += 1
        else:
            teams[home]["D"] += 1; teams[home]["Pts"] += 1
            teams[away]["D"] += 1; teams[away]["Pts"] += 1
    rows = sorted(teams.values(), key=lambda r: (-r["Pts"], -r["GD"], -r["GF"]))
    for i, r in enumerate(rows):
        r["intRank"] = i + 1
    return rows


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.divider()
    _default_comp = st.session_state.pop("euro_comp", list(EUROPEAN_COMPETITIONS.keys())[0])
    _default_idx  = (list(EUROPEAN_COMPETITIONS.keys()).index(_default_comp)
                     if _default_comp in EUROPEAN_COMPETITIONS else 0)
    comp_name = st.selectbox(
        "Competition",
        options=list(EUROPEAN_COMPETITIONS.keys()),
        format_func=lambda n: f"{EUROPEAN_COMPETITIONS[n]['flag']}  {n}",
        index=_default_idx,
    )
    cfg     = EUROPEAN_COMPETITIONS[comp_name]
    comp_id = cfg["id"]
    season  = st.selectbox("Season", ["2026-2027", "2025-2026"], index=0)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def fetch_all(lid, ssn, key):
    c = SportsDBClient(api_key=key)
    standings         = c.get_standings(lid, ssn)
    played, remaining = c.get_fixtures(lid, ssn)
    info              = c.get_league_info(lid)
    return standings, played, remaining, info


with st.spinner("Loading…"):
    try:
        standings, played_fixtures, remaining_fixtures, league_info = fetch_all(
            comp_id, season, _API_KEY
        )
    except RuntimeError as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

# Badge lookup — from fixture event fields (strHomeTeamBadge / strAwayTeamBadge)
badge_lookup: dict[str, str] = {}
for _f in played_fixtures + remaining_fixtures:
    if _f.get("strHomeTeamBadge"):
        badge_lookup[_f["strHomeTeam"]] = _f["strHomeTeamBadge"]
    if _f.get("strAwayTeamBadge"):
        badge_lookup[_f["strAwayTeam"]] = _f["strAwayTeamBadge"]
# Also pull from standings if available
for row in standings:
    if row.get("strBadge") and row.get("strTeam"):
        badge_lookup.setdefault(row["strTeam"], row["strBadge"])

# ---------------------------------------------------------------------------
# Round classification
# ---------------------------------------------------------------------------
lp_rounds      = cfg.get("league_phase_rounds", 8)
has_lp         = cfg.get("has_league_phase", lp_rounds > 0)
qualifying_ids = cfg.get("qualifying_rounds", set())
n_direct       = cfg.get("n_direct", 8)
n_playoff      = cfg.get("n_playoff", 16)

all_fixtures = played_fixtures + remaining_fixtures

lp_played    = [f for f in played_fixtures    if has_lp and 1 <= _intround(f) <= lp_rounds]
qual_played  = [f for f in played_fixtures    if _intround(f) in qualifying_ids]
qual_all     = [f for f in all_fixtures       if _intround(f) in qualifying_ids]
ko_played    = [f for f in played_fixtures    if _intround(f) not in qualifying_ids
                                              and (not has_lp or _intround(f) > lp_rounds)]
ko_remaining = [f for f in remaining_fixtures if _intround(f) not in qualifying_ids]
all_knockout = ko_played + ko_remaining

# Group by round label
ko_rounds_map: dict[str, list] = {}
for f in all_knockout:
    ko_rounds_map.setdefault(_round_key(f), []).append(f)
sorted_ko_rounds = sorted(ko_rounds_map.keys(), key=_round_sort)

qual_rounds_map: dict[str, list] = {}
for f in qual_all:
    qual_rounds_map.setdefault(_round_key(f), []).append(f)
sorted_qual_rounds = sorted(
    qual_rounds_map.keys(),
    key=lambda r: _intround(qual_rounds_map[r][0]),
    reverse=True,   # largest round number = earliest qualifying round
)

# Combined Opta ratings from all domestic league CSVs
@st.cache_data(ttl=3600, show_spinner=False)
def _load_combined_ratings() -> pd.DataFrame:
    """Merge all domestic league ratings CSVs into one DataFrame."""
    rows = []
    for league_cfg in LEAGUES.values():
        csv_path = Path("ratings") / f"{league_cfg['id']}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, dtype=str)
            if "team" in df.columns and "opta_rating" in df.columns:
                if "alias" not in df.columns:
                    df["alias"] = ""
                df["alias"] = df["alias"].fillna("")
                df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
                rows.append(df[["team", "alias", "opta_rating"]].dropna(subset=["opta_rating"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["team", "alias", "opta_rating"])

ratings_df = _load_combined_ratings()
ko_odds: dict[str, dict] = {}
if ko_remaining and not ratings_df.empty:
    odds_list = fixture_odds(ko_remaining, ratings_df, home_advantage=1.05)
    for f, o in zip(ko_remaining, odds_list):
        ko_odds[f.get("idEvent", f.get("strHomeTeam", "") + f.get("strAwayTeam", ""))] = o


def _fix_id(f: dict) -> str:
    return f.get("idEvent", f.get("strHomeTeam", "") + f.get("strAwayTeam", ""))


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
league_badge    = league_info.get("strBadge") or league_info.get("strLogo")
_season_display = season.replace("-20", "/")
col_logo, col_title = st.columns([1, 9])
with col_logo:
    if league_badge:
        st.image(league_badge, width=70)
with col_title:
    st.markdown(f"## {_season_display} UEFA {comp_name}")
    st.caption(
        f"League phase: **{len(lp_played)}** matches played  |  "
        f"Knockout: **{len(ko_played)}** played · **{len(ko_remaining)}** remaining  |  "
        f"Qualifying: **{len(qual_played)}** matches"
    )

st.divider()

# ---------------------------------------------------------------------------
# Tabs — vary by whether competition has a league phase
# ---------------------------------------------------------------------------
_show_entrants = (season == "2026-2027") and (comp_name in ENTRANTS_2026_27)

if has_lp:
    if _show_entrants:
        tab_league, tab_lp_results, tab_knockout, tab_bracket, tab_qual, tab_entrants = st.tabs(
            ["📊 Standings", "📋 League Stage", "⚔️ Knockout", "🏆 Bracket", "🔍 Qualifying", "📋 Entrants"]
        )
    else:
        tab_league, tab_lp_results, tab_knockout, tab_bracket, tab_qual = st.tabs(
            ["📊 Standings", "📋 League Stage", "⚔️ Knockout", "🏆 Bracket", "🔍 Qualifying"]
        )
        tab_entrants = None
else:
    if _show_entrants:
        tab_knockout, tab_bracket, tab_qual, tab_entrants = st.tabs(
            ["⚔️ Knockout", "🏆 Bracket", "🔍 Qualifying", "📋 Entrants"]
        )
    else:
        tab_knockout, tab_bracket, tab_qual = st.tabs(
            ["⚔️ Knockout", "🏆 Bracket", "🔍 Qualifying"]
        )
        tab_entrants = None
    tab_league = None
    tab_lp_results = None


# ---------------------------------------------------------------------------
# Tab — League Phase standings (computed from match results)
# ---------------------------------------------------------------------------
if tab_league is not None:
    with tab_league:
        if not lp_played:
            st.info("League phase has not started yet.")
        else:
            computed = _compute_league_standings(lp_played, badge_lookup)

            def _lp_zone_bg(pos: int) -> str:
                if pos <= n_direct:
                    return "#d4edda"
                if pos <= n_direct + n_playoff:
                    return "#fff3cd"
                return "#f8d7da"

            lp_rows = [{
                "Pos":   r["intRank"],
                "Badge": r["strBadge"],
                "Team":  r["strTeam"],
                "P":     r["P"], "W": r["W"], "D": r["D"], "L": r["L"],
                "GF":    r["GF"], "GA": r["GA"], "GD": r["GD"], "Pts": r["Pts"],
                "_bg":   _lp_zone_bg(r["intRank"]),
            } for r in computed]

            lp_df     = pd.DataFrame(lp_rows)
            styled_lp = (
                lp_df.drop(columns=["_bg"]).style
                .apply(lambda row: [f"background-color: {lp_rows[row.name]['_bg']}"] * len(row), axis=1)
                .set_properties(subset=["Team", "Pts"], **{"font-weight": "bold"})
            )
            _lp_cfg = {
                "Pos":   st.column_config.NumberColumn("Pos",  width="small"),
                "Badge": st.column_config.ImageColumn("",      width="small"),
                "Team":  st.column_config.TextColumn("Team",   width="medium"),
                "P":     st.column_config.NumberColumn("P",    width="small"),
                "W":     st.column_config.NumberColumn("W",    width="small"),
                "D":     st.column_config.NumberColumn("D",    width="small"),
                "L":     st.column_config.NumberColumn("L",    width="small"),
                "GF":    st.column_config.NumberColumn("GF",   width="small"),
                "GA":    st.column_config.NumberColumn("GA",   width="small"),
                "GD":    st.column_config.NumberColumn("GD",   width="small"),
                "Pts":   st.column_config.NumberColumn("Pts",  width="small"),
            }
            st.caption("🟢 Direct to Round of 16  🟡 Knockout Play-offs  🔴 Eliminated")
            st.dataframe(styled_lp, column_config=_lp_cfg,
                         use_container_width=False, hide_index=True,
                         height=len(lp_rows) * 35 + 42)
            st.caption(
                "Tiebreakers: 1) Head-to-head points; 2) Head-to-head goal difference; "
                "3) Head-to-head goals scored; 4) Head-to-head away goals scored; "
                "5) Goal difference; 6) Goals scored"
            )


# ---------------------------------------------------------------------------
# Tab — League Stage Results (round-by-round)
# ---------------------------------------------------------------------------
if tab_lp_results is not None:
    with tab_lp_results:
        if not lp_played:
            st.info("No league stage results yet.")
        else:
            lp_rounds_map: dict[int, list] = {}
            for f in lp_played:
                rnd = _intround(f)
                lp_rounds_map.setdefault(rnd, []).append(f)
            _lpr_cfg = {
                "Date":  st.column_config.TextColumn("Date",  width=110),
                "HB":    st.column_config.ImageColumn("",     width="small"),
                "Home":  st.column_config.TextColumn("Home",  width="medium"),
                "Score": st.column_config.TextColumn("Score", width="small"),
                "Away":  st.column_config.TextColumn("Away",  width="medium"),
                "AB":    st.column_config.ImageColumn("",     width="small"),
            }
            for rnd in sorted(lp_rounds_map.keys(), reverse=True):
                rows = [{
                    "Date":  _utc_to_cet(f.get("dateEvent", ""), f.get("strTime", "")),
                    "HB":    badge_lookup.get(f.get("strHomeTeam", ""), ""),
                    "Home":  f.get("strHomeTeam", ""),
                    "Score": f"{f.get('intHomeScore', '')}–{f.get('intAwayScore', '')}",
                    "Away":  f.get("strAwayTeam", ""),
                    "AB":    badge_lookup.get(f.get("strAwayTeam", ""), ""),
                } for f in sorted(lp_rounds_map[rnd], key=lambda x: x.get("dateEvent", ""))]
                st.markdown(f"### Matchday {rnd}")
                _lpr_styled = pd.DataFrame(rows).style.set_properties(
                    subset=["Home", "Away"], **{"font-weight": "bold"})
                st.dataframe(_lpr_styled, column_config=_lpr_cfg,
                             use_container_width=False, hide_index=True)


# ---------------------------------------------------------------------------
# Tab — Knockout Results & Predictions
# ---------------------------------------------------------------------------
with tab_knockout:
    if not all_knockout:
        st.info("Knockout stage has not started yet.")
    else:
        _ko_cfg = {
            "Date":  st.column_config.TextColumn("Date",   width=110),
            "HB":    st.column_config.ImageColumn("",      width="small"),
            "Home":  st.column_config.TextColumn("Home",   width="medium"),
            "Score": st.column_config.TextColumn("Score",  width="small"),
            "Away":  st.column_config.TextColumn("Away",   width="medium"),
            "AB":    st.column_config.ImageColumn("",      width="small"),
            "H%":    st.column_config.TextColumn("H%",     width="small"),
            "D%":    st.column_config.TextColumn("D%",     width="small"),
            "A%":    st.column_config.TextColumn("A%",     width="small"),
        }
        for rnd in sorted_ko_rounds:
            st.markdown(f"### {rnd}")
            rows = []
            for f in sorted(ko_rounds_map[rnd], key=lambda x: x.get("dateEvent", "")):
                is_played = f in ko_played
                odds      = ko_odds.get(_fix_id(f), {})
                rows.append({
                    "Date":  _utc_to_cet(f.get("dateEvent", ""), f.get("strTime", "")),
                    "HB":    badge_lookup.get(f.get("strHomeTeam", ""), ""),
                    "Home":  f.get("strHomeTeam", ""),
                    "Score": (f"{f.get('intHomeScore','')}–{f.get('intAwayScore','')}"
                              if is_played else "vs"),
                    "Away":  f.get("strAwayTeam", ""),
                    "AB":    badge_lookup.get(f.get("strAwayTeam", ""), ""),
                    "H%":    f"{odds['home_win']:.0%}" if odds and not is_played else "",
                    "D%":    f"{odds['draw']:.0%}"     if odds and not is_played else "",
                    "A%":    f"{odds['away_win']:.0%}" if odds and not is_played else "",
                })
            _ko_styled = pd.DataFrame(rows).style.set_properties(
                subset=["Home", "Away"], **{"font-weight": "bold"})
            st.dataframe(_ko_styled, column_config=_ko_cfg,
                         use_container_width=False, hide_index=True)


# ---------------------------------------------------------------------------
# Tab — Knockout Bracket (HTML)
# ---------------------------------------------------------------------------
with tab_bracket:
    if not all_knockout:
        st.info("Knockout stage has not started yet.")
    else:
        def _img(url):
            return (f"<img src='{url}' height='14' "
                    f"style='margin-right:4px;vertical-align:middle'>") if url else ""

        def _tie_card(legs: list) -> str:
            """One card per tie (1 or 2 legs). Shows leg scores + aggregate."""
            legs = sorted(legs, key=lambda x: x.get("dateEvent", ""))
            leg1 = legs[0]
            leg2 = legs[1] if len(legs) > 1 else None

            # t1 = home team of leg1, t2 = away team of leg1
            t1 = leg1.get("strHomeTeam", "Unknown")
            t2 = leg1.get("strAwayTeam", "Unknown")
            hb = badge_lookup.get(t1, "")
            ab = badge_lookup.get(t2, "")

            l1_played = leg1 in ko_played
            l1h = int(leg1.get("intHomeScore") or 0) if l1_played else None
            l1a = int(leg1.get("intAwayScore") or 0) if l1_played else None

            l2_played = leg2 is not None and leg2 in ko_played
            # leg2 has t2 as home, t1 as away
            l2h = int(leg2.get("intHomeScore") or 0) if l2_played else None
            l2a = int(leg2.get("intAwayScore") or 0) if l2_played else None

            # Leg score strings
            s1 = f"{l1h}–{l1a}" if l1_played else "vs"
            s2 = (f"{l2h}–{l2a}" if l2_played else ("vs" if leg2 else "")) if leg2 else ""
            mid = f"<span style='color:#555;font-size:12px'>{s1}" + (f" &nbsp;·&nbsp; {s2}" if s2 else "") + "</span>"

            # Aggregate
            winner = ""
            agg_html = ""
            if l1_played and l2_played:
                agg_t1 = l1h + l2a  # t1 total: leg1 home + leg2 away
                agg_t2 = l1a + l2h  # t2 total: leg1 away + leg2 home
                if agg_t1 > agg_t2:   winner = t1
                elif agg_t2 > agg_t1: winner = t2
                col = "#2e7d32" if winner else "#555"
                agg_html = (f"<div style='text-align:center;font-size:11px;color:{col};"
                            f"font-weight:bold;margin-top:3px'>Agg: {agg_t1}–{agg_t2}</div>")
            elif l1_played and not leg2:
                # Single-leg (Final): winner is direct
                if l1h > l1a:   winner = t1
                elif l1a > l1h: winner = t2

            # Probability only for single-leg ties (Final) — two-legged odds are misleading
            prob_html = ""
            if leg2 is None and not l1_played:
                odds = ko_odds.get(_fix_id(leg1), {})
                if odds:
                    hp, ap = odds.get("home_win"), odds.get("away_win")
                    if hp and ap:
                        prob_html = (f"<div style='color:#888;font-size:11px;"
                                     f"text-align:center;margin-top:3px'>"
                                     f"{hp:.0%} – draw – {ap:.0%}</div>")

            t1s = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
                   if winner == t1 else "padding:2px 5px;")
            t2s = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
                   if winner == t2 else "padding:2px 5px;")
            return f"""
<div style="border:1px solid #dee2e6;border-radius:8px;padding:8px 10px;
            margin-bottom:8px;background:#fff;min-width:240px;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
    <div style="{t1s}">{_img(hb)}{t1}</div>{mid}
  </div>
  <div style="display:flex;align-items:center">
    <div style="{t2s}">{_img(ab)}{t2}</div>
  </div>
  {agg_html}{prob_html}
</div>"""

        col_blocks = []
        for rnd in sorted_ko_rounds:
            # Group fixtures into ties by team pair (2 legs each)
            tie_map: dict[str, list] = {}
            for f in ko_rounds_map[rnd]:
                key = "_".join(sorted([f.get("strHomeTeam", ""), f.get("strAwayTeam", "")]))
                tie_map.setdefault(key, []).append(f)
            ties = sorted(tie_map.values(), key=lambda x: x[0].get("dateEvent", ""))
            cards_html = "".join(_tie_card(legs) for legs in ties)
            col_blocks.append(f"""
<div style="min-width:260px">
  <div style="font-weight:700;color:#555;font-size:13px;
              border-bottom:2px solid #dee2e6;padding-bottom:5px;margin-bottom:10px">
    {rnd}
  </div>
  {cards_html}
</div>""")

        st.markdown(f"""
<div style="display:flex;gap:20px;overflow-x:auto;padding:12px 4px 20px 4px;
            align-items:flex-start;font-family:sans-serif;font-size:13px">
  {"".join(col_blocks)}
</div>""", unsafe_allow_html=True)
        st.caption("🟢 Winner of played match")


# ---------------------------------------------------------------------------
# Tab — Qualifying Results
# ---------------------------------------------------------------------------
with tab_qual:
    # ── 2026-27: show static schedule + confirmed entrants ──────────────────
    if season == "2026-2027":
        _comp_entrants = ENTRANTS_2026_27.get(comp_name, {})
        _comp_dates    = QUALIFYING_DATES.get(comp_name, {})
        _QUAL_STAGES   = ["First Qualifying Round", "Second Qualifying Round",
                          "Third Qualifying Round", "Play-off Round"]
        _STATUS_BG = {
            "confirmed":   "#1a3a1a",
            "provisional": "#3a3010",
            "projected":   "#1a2a3a",
            "tbd":         "#2a2a2a",
        }
        _STATUS_LABEL = {
            "confirmed":   "✅ Confirmed",
            "provisional": "⏳ Provisional",
            "projected":   "🔮 Projected",
            "tbd":         "— TBD",
        }
        _albania_top4 = _fetch_albania_top4(_API_KEY)
        st.caption(
            "🟢 Confirmed — domestic season complete  "
            "🟡 Provisional — season still running  "
            "🔮 Projected — based on current standings  "
            "⬜ TBD — club not yet determined  ·  "
            "Draws and individual matchups not yet made"
        )
        for stage in _QUAL_STAGES:
            if stage not in _comp_entrants:
                continue
            dates = _comp_dates.get(stage, {})
            leg1  = dates.get("leg1", "TBD")
            leg2  = dates.get("leg2", "TBD")
            date_str = f"1st leg: **{leg1}** &nbsp;·&nbsp; 2nd leg: **{leg2}**"
            st.markdown(f"### {stage}")
            st.markdown(date_str, unsafe_allow_html=True)
            paths = _comp_entrants[stage]
            for path_label, clubs in paths.items():
                resolved = _resolve_dynamic(clubs, _albania_top4)
                if len(paths) > 1:
                    st.markdown(f"*{path_label}*")
                confirmed_clubs = [e for e in resolved if e["status"] != "tbd"]
                tbd_clubs       = [e for e in resolved if e["status"] == "tbd"]
                # Confirmed / provisional table
                if confirmed_clubs:
                    rows_html = ""
                    for e in confirmed_clubs:
                        bg    = _STATUS_BG[e["status"]]
                        label = _STATUS_LABEL[e["status"]]
                        rows_html += (
                            f"<tr style='background:{bg}'>"
                            f"<td style='padding:4px 8px;font-size:15px'>{e['flag']}</td>"
                            f"<td style='padding:4px 8px;font-weight:bold;color:white'>{e['club']}</td>"
                            f"<td style='padding:4px 8px;color:#aaa'>{e['country']}</td>"
                            f"<td style='padding:4px 8px;color:#888;font-size:12px'>{e['route']}</td>"
                            f"<td style='padding:4px 8px;color:#aaa;font-size:12px'>{label}</td>"
                            f"</tr>"
                        )
                    st.markdown(
                        f"<table style='width:100%;border-collapse:collapse;"
                        f"font-family:sans-serif;margin-bottom:6px'>"
                        f"<thead><tr style='background:#1a1a2e'>"
                        f"<th style='padding:4px 8px;color:#888;text-align:left'></th>"
                        f"<th style='padding:4px 8px;color:#888;text-align:left'>Club</th>"
                        f"<th style='padding:4px 8px;color:#888;text-align:left'>Country</th>"
                        f"<th style='padding:4px 8px;color:#888;text-align:left'>Route</th>"
                        f"<th style='padding:4px 8px;color:#888;text-align:left'>Status</th>"
                        f"</tr></thead><tbody>{rows_html}</tbody></table>",
                        unsafe_allow_html=True,
                    )
                # TBD slots — compact text list
                if tbd_clubs:
                    tbd_items = " · ".join(
                        f"{e['flag']} {e['country']} ({e['route']})" for e in tbd_clubs
                    )
                    st.markdown(
                        f"<div style='background:#1e1e1e;border-left:3px solid #555;"
                        f"padding:8px 12px;border-radius:4px;color:#888;"
                        f"font-size:12px;margin-bottom:10px'>"
                        f"<b style='color:#666'>TBD slots:</b> {tbd_items}</div>",
                        unsafe_allow_html=True,
                    )
            st.divider()

    # ── Live seasons: fetch from API as before ───────────────────────────────
    elif not qual_all:
        st.info("No qualifying data available.")
    else:
        _q_cfg = {
            "Date":  st.column_config.TextColumn("Date",  width=130),
            "HB":    st.column_config.ImageColumn("",     width="small"),
            "Home":  st.column_config.TextColumn("Home",  width="medium"),
            "Score": st.column_config.TextColumn("Score", width="small"),
            "Away":  st.column_config.TextColumn("Away",  width="medium"),
            "AB":    st.column_config.ImageColumn("",     width="small"),
        }
        for rnd in sorted_qual_rounds:
            rnd_fixtures  = sorted(qual_rounds_map[rnd], key=lambda x: x.get("dateEvent", ""))
            n_played      = sum(1 for f in rnd_fixtures if f in qual_played)
            st.markdown(
                f"### {rnd} "
                f"<span style='font-size:14px;color:#888;font-weight:normal'>"
                f"({n_played} matches)</span>",
                unsafe_allow_html=True,
            )
            rows = [{
                "Date":  _utc_to_cet(f.get("dateEvent", ""), f.get("strTime", "")),
                "HB":    badge_lookup.get(f.get("strHomeTeam", ""), ""),
                "Home":  f.get("strHomeTeam", ""),
                "Score": (f"{f.get('intHomeScore','')}–{f.get('intAwayScore','')}"
                          if f in qual_played else "vs"),
                "Away":  f.get("strAwayTeam", ""),
                "AB":    badge_lookup.get(f.get("strAwayTeam", ""), ""),
            } for f in rnd_fixtures]
            _q_styled = pd.DataFrame(rows).style.set_properties(
                subset=["Home", "Away"], **{"font-weight": "bold"})
            st.dataframe(_q_styled, column_config=_q_cfg,
                         use_container_width=False, hide_index=True)


# ---------------------------------------------------------------------------
# Tab — 2026-27 Entrants
# ---------------------------------------------------------------------------
if tab_entrants is not None:
    with tab_entrants:
        comp_entrants = ENTRANTS_2026_27.get(comp_name, {})
        if not comp_entrants:
            st.info("No entrant data available.")
        else:
            st.caption(
                "🟢 Confirmed — domestic season complete  "
                "🟡 Provisional — season still running  "
                "⬜ TBD — club not yet determined"
            )

            _STATUS_BG = {
                "confirmed":   "#1a3a1a",
                "provisional": "#3a3010",
                "tbd":         "#2a2a2a",
            }
            _STATUS_LABEL = {
                "confirmed":   "✅ Confirmed",
                "provisional": "⏳ Provisional",
                "tbd":         "— TBD",
            }

            # Iterate stages in chronological order
            for stage in STAGE_ORDER:
                if stage not in comp_entrants:
                    continue
                paths = comp_entrants[stage]
                with st.expander(f"**{stage}**", expanded=(stage == "League Phase")):
                    for path_label, clubs in paths.items():
                        if len(paths) > 1:
                            st.markdown(f"*{path_label}*")
                        rows_html = ""
                        for e in clubs:
                            bg   = _STATUS_BG.get(e["status"], "#2a2a2a")
                            name = e["club"] if e["club"] else f"<span style='color:#888'>{e['route']}</span>"
                            label = _STATUS_LABEL.get(e["status"], "")
                            rows_html += (
                                f"<tr style='background:{bg}'>"
                                f"<td style='padding:4px 8px;font-size:15px'>{e['flag']}</td>"
                                f"<td style='padding:4px 8px;font-weight:bold;color:white'>{name}</td>"
                                f"<td style='padding:4px 8px;color:#aaa'>{e['country']}</td>"
                                f"<td style='padding:4px 8px;color:#888;font-size:12px'>{e['route']}</td>"
                                f"<td style='padding:4px 8px;color:#aaa;font-size:12px'>{label}</td>"
                                f"</tr>"
                            )
                        st.markdown(
                            f"<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                            f"<thead><tr style='background:#1a1a2e'>"
                            f"<th style='padding:4px 8px;color:#888;text-align:left'></th>"
                            f"<th style='padding:4px 8px;color:#888;text-align:left'>Club</th>"
                            f"<th style='padding:4px 8px;color:#888;text-align:left'>Country</th>"
                            f"<th style='padding:4px 8px;color:#888;text-align:left'>Route</th>"
                            f"<th style='padding:4px 8px;color:#888;text-align:left'>Status</th>"
                            f"</tr></thead><tbody>{rows_html}</tbody></table>",
                            unsafe_allow_html=True,
                        )
                        st.markdown("")
