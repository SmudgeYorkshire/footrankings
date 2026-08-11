"""
UEFA European Competitions — Champions League, Europa League, Conference League.

Shows:
  • League Phase standings (computed from round 1-8 results, color-coded by zone)
  • League Phase results round-by-round
  • Qualifying — every tie from the First Qualifying Round through the Play-off
    round, with live results (from API-Football)
  • Qualifying Predictions — advance-probability predictions for undecided
    Third Qualifying Round ties, plus projected Play-off round pairings
"""

import os
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import EUROPEAN_COMPETITIONS, LEAGUES
from api_football_fetcher import ApiFootballClient
from simulator import two_leg_advance_odds
from qualifying_bracket import PLAYOFF_BRACKET, CONFIRMED_LEAGUE_PHASE

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
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


# Fixed chronological order — qualifying round strRound text from API-Football
_QUAL_ROUND_ORDER = [
    "1st Qualifying Round", "2nd Qualifying Round", "3rd Qualifying Round", "Play-offs",
]


def _round_str(f: dict) -> str:
    return (f.get("strRound") or "").lower()


def _is_league_phase(f: dict) -> bool:
    return "league stage" in _round_str(f) or "league phase" in _round_str(f)


def _is_qual_or_playoff(f: dict) -> bool:
    return (f.get("strRound") or "") in _QUAL_ROUND_ORDER


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


@st.cache_data(ttl=3600, show_spinner=False)
def _load_combined_ratings() -> pd.DataFrame:
    """Merge all domestic league ratings CSVs into one DataFrame."""
    rows = []
    for league_cfg in LEAGUES.values():
        csv_path = Path("ratings") / f"{league_cfg.get('tsdb_id', league_cfg['id'])}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, dtype=str)
            if "team" in df.columns and "opta_rating" in df.columns:
                if "alias" not in df.columns:
                    df["alias"] = ""
                df["alias"] = df["alias"].fillna("")
                df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
                rows.append(df[["team", "alias", "opta_rating"]].dropna(subset=["opta_rating"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["team", "alias", "opta_rating"])


@st.cache_data(ttl=60, show_spinner=False)
def fetch_all(lid, ssn, key):
    c = ApiFootballClient(api_key=key)
    standings         = c.get_standings(lid, ssn)
    played, remaining = c.get_fixtures(lid, ssn)
    info              = c.get_league_info(lid)
    return standings, played, remaining, info


def _badges_from_fixtures(fixtures: list[dict]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for f in fixtures:
        if f.get("strHomeTeamBadge"):
            lookup[f["strHomeTeam"]] = f["strHomeTeamBadge"]
        if f.get("strAwayTeamBadge"):
            lookup[f["strAwayTeam"]] = f["strAwayTeamBadge"]
    return lookup


def _group_ties(fixtures: list[dict]) -> list[list[dict]]:
    """Group a round's fixtures into two-legged ties by team pair, legs date-sorted."""
    tie_map: dict[frozenset, list[dict]] = {}
    for f in fixtures:
        key = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
        tie_map.setdefault(key, []).append(f)
    ties = [sorted(legs, key=lambda x: x.get("dateEvent", "")) for legs in tie_map.values()]
    ties.sort(key=lambda legs: legs[0].get("dateEvent", ""))
    return ties


def _img(url: str, height: int = 14) -> str:
    return (f"<img src='{url}' height='{height}' "
            f"style='margin-right:4px;vertical-align:middle'>") if url else ""


def _tie_card_html(legs: list[dict], badge_lookup: dict, played_set: set) -> str:
    """One card per tie (1 or 2 legs). Shows leg scores + aggregate, winner highlighted."""
    legs = sorted(legs, key=lambda x: x.get("dateEvent", ""))
    leg1 = legs[0]
    leg2 = legs[1] if len(legs) > 1 else None

    t1 = leg1.get("strHomeTeam", "Unknown")
    t2 = leg1.get("strAwayTeam", "Unknown")
    hb = badge_lookup.get(t1, "")
    ab = badge_lookup.get(t2, "")

    def _fid(f):
        return f.get("idEvent", f.get("strHomeTeam", "") + f.get("strAwayTeam", ""))

    l1_played = _fid(leg1) in played_set
    l1h = int(leg1.get("intHomeScore") or 0) if l1_played else None
    l1a = int(leg1.get("intAwayScore") or 0) if l1_played else None

    l2_played = leg2 is not None and _fid(leg2) in played_set
    l2h = int(leg2.get("intHomeScore") or 0) if l2_played else None
    l2a = int(leg2.get("intAwayScore") or 0) if l2_played else None

    d1 = _utc_to_cet(leg1.get("dateEvent", ""), leg1.get("strTime", ""))
    d2 = _utc_to_cet(leg2.get("dateEvent", ""), leg2.get("strTime", "")) if leg2 else ""

    s1 = f"{l1h}–{l1a}" if l1_played else "vs"
    s2 = (f"{l2h}–{l2a}" if l2_played else "vs") if leg2 else ""
    mid = (f"<span style='color:#888;font-size:10px'>{d1}</span><br>"
           f"<span style='color:#555;font-size:12px'>{s1}"
           + (f" &nbsp;·&nbsp; {s2}" if s2 else "") + "</span>"
           + (f"<br><span style='color:#888;font-size:10px'>{d2}</span>" if d2 else ""))

    winner = ""
    agg_html = ""
    if l1_played and l2_played:
        agg_t1 = l1h + l2a
        agg_t2 = l1a + l2h
        if agg_t1 > agg_t2:   winner = t1
        elif agg_t2 > agg_t1: winner = t2
        col = "#2e7d32" if winner else "#555"
        agg_html = (f"<div style='text-align:center;font-size:11px;color:{col};"
                    f"font-weight:bold;margin-top:3px'>Agg: {agg_t1}–{agg_t2}</div>")
    elif l1_played and not leg2:
        if l1h > l1a:   winner = t1
        elif l1a > l1h: winner = t2

    t1s = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
           if winner == t1 else "padding:2px 5px;")
    t2s = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
           if winner == t2 else "padding:2px 5px;")
    return f"""
<div style="border:1px solid #dee2e6;border-radius:8px;padding:8px 10px;
            margin:0 8px 8px 0;background:#fff;width:230px;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
    <div style="{t1s}">{_img(hb)}{t1}</div>
  </div>
  <div style="text-align:center">{mid}</div>
  <div style="display:flex;align-items:center;margin-top:4px">
    <div style="{t2s}">{_img(ab)}{t2}</div>
  </div>
  {agg_html}
</div>"""


# ---------------------------------------------------------------------------
# Play-off bracket resolution
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def _fetch_comp_fixtures(comp_name: str, key: str):
    """played, remaining fixtures for any of the 3 competitions, by name."""
    cid = EUROPEAN_COMPETITIONS[comp_name]["id"]
    client = ApiFootballClient(api_key=key)
    return client.get_fixtures(cid, "2026-2027")


def _resolve_bracket_side(side: tuple, ratings_df: pd.DataFrame) -> dict:
    """Resolve one side of a projected Play-off tie.

    Returns {"label": str|None, "status": "confirmed"|"predicted"|"tbd",
             "pct": float|None}.
    """
    if side[0] == "team":
        return {"label": side[1], "status": "confirmed", "pct": None}

    _, comp, name_set, which = side
    played, remaining = _fetch_comp_fixtures(comp, _API_KEY)
    qr3_played    = [f for f in played    if f.get("strRound") == "3rd Qualifying Round"]
    qr3_remaining = [f for f in remaining if f.get("strRound") == "3rd Qualifying Round"]
    played_ids = {f.get("idEvent") for f in qr3_played}
    all_qr3 = qr3_played + qr3_remaining

    tie_map: dict[frozenset, list[dict]] = {}
    for f in all_qr3:
        pair = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
        tie_map.setdefault(pair, []).append(f)

    match_legs = tie_map.get(frozenset(name_set))
    if match_legs is None:
        for pair, legs in tie_map.items():
            if pair & name_set:
                match_legs = legs
                break
    if match_legs is None:
        return {"label": None, "status": "tbd", "pct": None}

    legs = sorted(match_legs, key=lambda x: x.get("dateEvent", ""))
    leg1 = legs[0]
    leg2 = legs[1] if len(legs) > 1 else None
    t1 = leg1.get("strHomeTeam", "")
    t2 = leg1.get("strAwayTeam", "")
    l1_played = leg1.get("idEvent") in played_ids
    l2_played = leg2 is not None and leg2.get("idEvent") in played_ids

    if l1_played and l2_played:
        agg1 = int(leg1["intHomeScore"] or 0) + int(leg2["intAwayScore"] or 0)
        agg2 = int(leg1["intAwayScore"] or 0) + int(leg2["intHomeScore"] or 0)
        winner = t1 if agg1 > agg2 else (t2 if agg2 > agg1 else None)
        loser  = t2 if winner == t1 else (t1 if winner == t2 else None)
        chosen = winner if which == "winner" else loser
        return {"label": chosen or "TBD (penalties)", "status": "confirmed", "pct": None}

    leg1_score = None
    if l1_played:
        leg1_score = (int(leg1.get("intHomeScore") or 0), int(leg1.get("intAwayScore") or 0))
    odds = two_leg_advance_odds(t1, t2, ratings_df, leg1_score=leg1_score)
    t1_pct, t2_pct = odds["team1_adv"], odds["team2_adv"]
    if which == "winner":
        chosen, pct = (t1, t1_pct) if t1_pct >= t2_pct else (t2, t2_pct)
    else:
        chosen, pct = (t2, t2_pct) if t1_pct >= t2_pct else (t1, t1_pct)
    return {"label": chosen, "status": "predicted", "pct": pct}


def _proj_side_html(resolved: dict, badge_lookup: dict, winner: bool) -> str:
    label = resolved["label"] or "TBD"
    status = resolved["status"]
    badge = badge_lookup.get(label, "") if resolved["label"] else ""
    style = "font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;" if winner else "padding:2px 5px;"
    pct_html = ""
    if status == "predicted" and resolved["pct"] is not None:
        pct_html = f" <span style='color:#856404;font-size:10px'>({resolved['pct']:.0%})</span>"
    elif status == "tbd":
        style = "padding:2px 5px;color:#999;font-style:italic;"
    return f"<div style='{style}'>{_img(badge)}{label}{pct_html}</div>"


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
    season  = "2026-2027"   # only the current season is tracked


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
with st.spinner("Loading…"):
    try:
        standings, played_fixtures, remaining_fixtures, league_info = fetch_all(
            comp_id, season, _API_KEY
        )
    except RuntimeError as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

badge_lookup: dict[str, str] = _badges_from_fixtures(played_fixtures + remaining_fixtures)
for row in standings:
    if row.get("strBadge") and row.get("strTeam"):
        badge_lookup.setdefault(row["strTeam"], row["strBadge"])

lp_rounds = cfg.get("league_phase_rounds", 8)
has_lp    = cfg.get("has_league_phase", lp_rounds > 0)

lp_played = [f for f in played_fixtures if has_lp and 1 <= _intround(f) <= lp_rounds]

qual_all     = [f for f in (played_fixtures + remaining_fixtures) if _is_qual_or_playoff(f)]
qual_played  = [f for f in played_fixtures if _is_qual_or_playoff(f)]
played_ids   = {f.get("idEvent") for f in qual_played}

qual_rounds_map: dict[str, list] = {}
for f in qual_all:
    qual_rounds_map.setdefault(f.get("strRound", ""), []).append(f)

ratings_df = _load_combined_ratings()

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
        f"Qualifying: **{len(qual_played)}** played · **{len(qual_all) - len(qual_played)}** remaining"
    )

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
if has_lp:
    tab_league, tab_lp_results, tab_qual, tab_qual_pred = st.tabs(
        ["📊 Standings", "📋 League Stage", "🔍 Qualifying", "🔮 Qualifying Predictions"]
    )
else:
    tab_qual, tab_qual_pred = st.tabs(["🔍 Qualifying", "🔮 Qualifying Predictions"])
    tab_league = None
    tab_lp_results = None


# ---------------------------------------------------------------------------
# Tab — League Phase standings (computed from match results)
# ---------------------------------------------------------------------------
if tab_league is not None:
    with tab_league:
        if not lp_played:
            st.info("League phase has not started yet.")
            confirmed = CONFIRMED_LEAGUE_PHASE.get(comp_name, [])
            if confirmed:
                st.markdown(f"#### Clubs already confirmed for the League Phase ({len(confirmed)} of 36)")
                st.caption("The remaining spots go to qualifying and Play-off round winners — see the Qualifying tabs.")
                _conf_rows = "".join(
                    f"<div style='display:inline-block;width:220px;padding:4px 8px;font-size:13px'>"
                    f"{flag} {club} <span style='color:#888;font-size:11px'>({country})</span></div>"
                    for club, country, flag in sorted(confirmed, key=lambda x: x[1])
                )
                st.markdown(f"<div>{_conf_rows}</div>", unsafe_allow_html=True)
        else:
            n_direct  = cfg.get("n_direct", 8)
            n_playoff = cfg.get("n_playoff", 16)
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
                         use_container_width=True, hide_index=True,
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
                             use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab — Qualifying (live results, QR1 through Play-offs)
# ---------------------------------------------------------------------------
with tab_qual:
    if not qual_all:
        st.info("Qualifying has not started yet.")
    else:
        present_rounds = [r for r in _QUAL_ROUND_ORDER if r in qual_rounds_map]
        for rnd in present_rounds:
            ties = _group_ties(qual_rounds_map[rnd])
            n_done = sum(
                1 for legs in ties
                if all(_g.get("idEvent") in played_ids for _g in legs)
                and len(legs) >= (1 if rnd == "Play-offs" and len(legs) == 1 else 2)
            )
            with st.expander(f"**{rnd}** — {len(ties)} ties  ({n_done} decided)",
                              expanded=(rnd == present_rounds[-1])):
                cards = "".join(_tie_card_html(legs, badge_lookup, played_ids) for legs in ties)
                st.markdown(
                    f"<div style='display:flex;flex-wrap:wrap'>{cards}</div>",
                    unsafe_allow_html=True,
                )
        st.caption("🟢 Winner of a decided tie/leg")


# ---------------------------------------------------------------------------
# Tab — Qualifying Predictions
# ---------------------------------------------------------------------------
with tab_qual_pred:
    st.caption(
        "**Model:** Opta ratings → attack/defence via power transform → "
        "Negative-Binomial goal distribution → analytical two-leg advance probability.  "
        "Home advantage: 1.05×.  Penalties modelled as 50/50."
    )

    # ── Third Qualifying Round — undecided ties ─────────────────────────────
    st.markdown("### Third Qualifying Round")
    qr3_all = qual_rounds_map.get("3rd Qualifying Round", [])
    qr3_ties = _group_ties(qr3_all)
    qr3_undecided = [
        legs for legs in qr3_ties
        if not (len(legs) >= 2 and all(_g.get("idEvent") in played_ids for _g in legs[:2]))
    ]

    if not qr3_ties:
        st.info("Third Qualifying Round fixtures not yet available.")
    elif not qr3_undecided:
        st.success("Third Qualifying Round is complete — see projected Play-off ties below.")
    else:
        for legs in qr3_undecided:
            leg1 = legs[0]
            leg2 = legs[1] if len(legs) > 1 else None
            team1 = leg1.get("strHomeTeam", "")
            team2 = leg1.get("strAwayTeam", "")
            l1_played = leg1.get("idEvent") in played_ids
            leg1_score = None
            if l1_played:
                leg1_score = (int(leg1.get("intHomeScore") or 0), int(leg1.get("intAwayScore") or 0))

            odds = two_leg_advance_odds(team1, team2, ratings_df, leg1_score=leg1_score)
            t1_adv, t2_adv = odds["team1_adv"], odds["team2_adv"]
            l1o, l2o = odds["leg1"], odds["leg2"]
            b1 = badge_lookup.get(team1, "")
            b2 = badge_lookup.get(team2, "")

            with st.container(border=True):
                hc1, hc2, hc3 = st.columns([2, 1, 2])
                with hc1:
                    if b1: st.image(b1, width=36)
                    st.markdown(f"**{team1}**")
                with hc2:
                    st.markdown("<div style='text-align:center;padding-top:8px'>vs</div>", unsafe_allow_html=True)
                with hc3:
                    if b2: st.image(b2, width=36)
                    st.markdown(f"**{team2}**")

                d1 = leg1.get("dateEvent", "")[:10]
                d2 = leg2.get("dateEvent", "")[:10] if leg2 else "TBD"
                lc1, lc2 = st.columns(2)
                with lc1:
                    st.markdown(f"**Leg 1** · {d1} · *{team1}* at home")
                    if l1_played:
                        st.markdown(f"Result: **{leg1.get('intHomeScore','?')}–{leg1.get('intAwayScore','?')}**")
                    else:
                        st.markdown(
                            f"<span style='color:#1a73e8'>{l1o['home_win']:.0%}</span> · "
                            f"<span style='color:#888'>{l1o['draw']:.0%}</span> · "
                            f"<span style='color:#e53935'>{l1o['away_win']:.0%}</span>  "
                            f"&nbsp;&nbsp;xG: **{l1o['xg_home']:.2f}** – **{l1o['xg_away']:.2f}**",
                            unsafe_allow_html=True,
                        )
                with lc2:
                    st.markdown(f"**Leg 2** · {d2} · *{team2}* at home")
                    st.markdown(
                        f"<span style='color:#1a73e8'>{l2o['home_win']:.0%}</span> · "
                        f"<span style='color:#888'>{l2o['draw']:.0%}</span> · "
                        f"<span style='color:#e53935'>{l2o['away_win']:.0%}</span>  "
                        f"&nbsp;&nbsp;xG: **{l2o['xg_home']:.2f}** – **{l2o['xg_away']:.2f}**",
                        unsafe_allow_html=True,
                    )

                bar_w1 = int(round(t1_adv * 100))
                bar_w2 = 100 - bar_w1
                c1, c2 = ("#1a73e8", "#e53935") if t1_adv >= 0.5 else ("#e53935", "#1a73e8")
                st.markdown(
                    f"<div style='margin:10px 0 4px'>"
                    f"<div style='display:flex;height:22px;border-radius:4px;overflow:hidden'>"
                    f"<div style='width:{bar_w1}%;background:{c1};display:flex;align-items:center;"
                    f"justify-content:center;color:white;font-size:12px;font-weight:600'>"
                    f"{team1} {t1_adv:.0%}</div>"
                    f"<div style='width:{bar_w2}%;background:{c2};display:flex;align-items:center;"
                    f"justify-content:center;color:white;font-size:12px;font-weight:600'>"
                    f"{t2_adv:.0%} {team2}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

    # ── Projected Play-off round ─────────────────────────────────────────────
    st.divider()
    st.markdown("### Projected Play-off Ties")
    st.caption(
        "Where a Third Qualifying Round tie is undecided, the side shown is the "
        "team currently favoured to advance (or be eliminated, for ties that feed "
        "in as a Third Qualifying Round *loser*), with its probability."
    )
    bracket = PLAYOFF_BRACKET.get(comp_name, [])
    if not bracket:
        st.info("No Play-off bracket data available for this competition.")
    else:
        po_cards = []
        for side_a, side_b in bracket:
            ra = _resolve_bracket_side(side_a, ratings_df)
            rb = _resolve_bracket_side(side_b, ratings_df)
            html_a = _proj_side_html(ra, badge_lookup, winner=False)
            html_b = _proj_side_html(rb, badge_lookup, winner=False)
            po_cards.append(f"""
<div style="border:1px solid #dee2e6;border-radius:8px;padding:8px 10px;
            margin:0 8px 8px 0;background:#fff;width:230px;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  {html_a}
  <div style='text-align:center;color:#888;font-size:11px;margin:3px 0'>vs</div>
  {html_b}
</div>""")
        st.markdown(f"<div style='display:flex;flex-wrap:wrap'>{''.join(po_cards)}</div>",
                    unsafe_allow_html=True)
        st.caption("Percentages shown are each side's probability of occupying that Play-off slot.")
