"""
UEFA European Competitions — Champions League, Europa League, Conference League.

Shows:
  • League Phase standings (computed from round 1-8 results, color-coded by zone)
  • League Phase results round-by-round
  • Qualifying — every tie from the First Qualifying Round through the Play-off
    round, with live results (from API-Football). No Qualifying Predictions tab
    this season -- qualifying for 2026/27 is already complete.
"""

import os
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import EUROPEAN_COMPETITIONS, LEAGUES
from api_football_fetcher import ApiFootballClient
from _split_season import build_h2h, rank_tied_group
from simulator import position_bounds
from qualifying_bracket import CONFIRMED_LEAGUE_PHASE
from club_coefficients import get_coeff
from league_phase_simulator import (
    build_predicted_bracket, single_match_outcome_probs,
    cached_league_phase_simulation, league_phase_sim_cache_key,
    simulate_competition_winner,
)
from prob_table import render_prob_table, _green_col
from league_phase_fixtures import (
    is_opponent_list_complete, derive_fixtures, partial_opponents_by_team, dated_schedule,
)
from competition_trivia import competition_trivia, overall_trivia
from qualifying_projection import (
    _load_combined_ratings, _resolve_field_ratings,
    _leg_aggregate_winner, _project_league_phase_field,
    _fuzzy_key, real_league_phase_results,
)

# Real pot sizing per competition (see league_phase_simulator's docstring):
# Champions/Europa League: 4 pots of 9, 2 opponents each = 8 League Phase
# games. Conference League: 6 pots of 6, 1 opponent each = 6 games.
_LEAGUE_PHASE_POTS = {
    "Champions League": (4, 2), "Europa League": (4, 2), "Conference League": (6, 1),
}

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_CET = ZoneInfo("Europe/Berlin")
_CURRENT_EURO_SEASON = "2026-2027"  # only the current season is tracked


def _utc_to_cet(date_str: str, time_str: str) -> str:
    if not date_str or not time_str or time_str.startswith("00:00"):
        return date_str
    try:
        dt = datetime.strptime(f"{date_str} {time_str[:8]}", "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(_CET)
        return f"{dt.strftime('%d %b')} {dt.strftime('%H:%M')} CET"
    except ValueError:
        return date_str


# Fixed chronological order — qualifying round strRound text from API-Football.
# The Play-off round's own name isn't consistent across competitions --
# Champions/Europa League use "Play-offs", Conference League uses "Playoff
# round" -- so anything identifying that round checks _PLAYOFF_ROUND_NAMES
# rather than a single literal.
_QUAL_ROUND_ORDER = [
    "1st Qualifying Round", "2nd Qualifying Round", "3rd Qualifying Round",
    "Play-offs", "Playoff round",
]
_PLAYOFF_ROUND_NAMES = frozenset({"Play-offs", "Playoff round"})


def _round_str(f: dict) -> str:
    return (f.get("strRound") or "").lower()


def _is_league_phase(f: dict) -> bool:
    return "league stage" in _round_str(f) or "league phase" in _round_str(f)


def _is_qual_or_playoff(f: dict) -> bool:
    return (f.get("strRound") or "") in _QUAL_ROUND_ORDER


def _intround(f: dict) -> int:
    return int(f.get("intRound", 0) or 0)


# UEFA's own official League Phase tiebreak order (ahead of the Article
# governing the Champions/Europa/Conference League format): head-to-head
# points, then head-to-head GD, then head-to-head GF, then head-to-head
# away GF, then overall GD, then overall GF.
_LEAGUE_PHASE_TIEBREAKERS = ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf"]


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

    # rank_tied_group (shared with _split_season.py) reads intGoalDifference/
    # intGoalsFor — alias them onto these Pts/GD/GF-keyed rows rather than
    # keeping a second, independently-maintained tiebreak implementation.
    for row in teams.values():
        row["intGoalDifference"] = row["GD"]
        row["intGoalsFor"] = row["GF"]

    h2h = build_h2h(matches)
    row_list = sorted(teams.values(), key=lambda r: -r["Pts"])
    ranked: list[dict] = []
    i = 0
    while i < len(row_list):
        j = i + 1
        while j < len(row_list) and row_list[j]["Pts"] == row_list[i]["Pts"]:
            j += 1
        group = row_list[i:j]
        ranked.extend(
            rank_tied_group(group, _LEAGUE_PHASE_TIEBREAKERS, h2h) if len(group) > 1 else group
        )
        i = j

    for i, r in enumerate(ranked):
        r["intRank"] = i + 1
    return ranked


@st.cache_data(ttl=60, show_spinner=False)
def fetch_all(lid, ssn, key):
    c = ApiFootballClient(api_key=key)
    standings         = c.get_standings(lid, ssn)
    played, remaining = c.get_fixtures(lid, ssn)
    info              = c.get_league_info(lid)
    teams             = c.get_teams(lid, ssn)
    return standings, played, remaining, info, teams


def _badges_from_fixtures(fixtures: list[dict]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for f in fixtures:
        if f.get("strHomeTeamBadge"):
            lookup[f["strHomeTeam"]] = f["strHomeTeamBadge"]
        if f.get("strAwayTeamBadge"):
            lookup[f["strAwayTeam"]] = f["strAwayTeamBadge"]
    return lookup


# Confirmed League Phase direct entrants (the big domestic-league winners)
# often have zero fixtures in the European competition itself before the
# League Phase draw happens, so the European competition's own fixtures/
# standings can't supply their badge -- fall back to their domestic league,
# where they've already played plenty of matches this season.
_COUNTRY_TO_DOMESTIC_LEAGUE: dict[str, tuple[int, int]] = {
    cfg["country"]: (cfg["id"], cfg["af_season"])
    for cfg in LEAGUES.values() if cfg.get("country") and cfg.get("provider") == "api_football"
}


@st.cache_data(ttl=3600, show_spinner=False)
def _domestic_league_badges(league_id: int, af_season: int, key: str) -> dict[str, str]:
    c = ApiFootballClient(api_key=key)
    lookup: dict[str, str] = {}
    for row in c.get_standings(league_id, af_season):
        if row.get("strBadge") and row.get("strTeam"):
            lookup[row["strTeam"]] = row["strBadge"]
    return lookup


def _fill_missing_badges(teams_and_countries: list[tuple[str, str]], badge_lookup: dict, key: str) -> None:
    """Mutates badge_lookup in place, filling gaps via each missing team's
    domestic league standings -- these clubs have often played zero
    fixtures in the European competition itself (e.g. League Phase direct
    entrants before the draw), so their domestic league is the only source
    with a badge on file. Falls back to fuzzy (accent/filler-word
    insensitive) name matching since API-Football's own domestic-league
    naming doesn't always match our static confirmed-entrant lists
    (e.g. "Bayern Munich" vs "Bayern München", "Inter Milan" vs "Inter")."""
    missing = [(team, country) for team, country in teams_and_countries
               if team not in badge_lookup and country in _COUNTRY_TO_DOMESTIC_LEAGUE]
    if not missing:
        return
    needed_leagues = {_COUNTRY_TO_DOMESTIC_LEAGUE[country] for _team, country in missing}
    badges_by_league: dict[tuple, dict[str, str]] = {
        league: _domestic_league_badges(*league, key) for league in needed_leagues
    }
    for badges in badges_by_league.values():
        for name, logo in badges.items():
            badge_lookup.setdefault(name, logo)

    for team, country in missing:
        if team in badge_lookup:
            continue
        badges = badges_by_league[_COUNTRY_TO_DOMESTIC_LEAGUE[country]]
        fuzzy_index = {_fuzzy_key(name): logo for name, logo in badges.items()}
        key_fz = _fuzzy_key(team)
        if key_fz in fuzzy_index:
            badge_lookup[team] = fuzzy_index[key_fz]
            continue
        # Scoped to this one country's clubs, so a loose "one name contains
        # the other" match (e.g. "hoffenheim" in "1899 hoffenheim") is safe.
        for other_key, logo in fuzzy_index.items():
            if len(other_key) >= 4 and (other_key in key_fz or key_fz in other_key):
                badge_lookup[team] = logo
                break


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
        winner = _leg_aggregate_winner(t1, t2, l1h, l1a, l2h, l2a) or ""
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


def _bracket_tie_html(tie: dict, badge_lookup: dict) -> str:
    """Renders one tie of a predicted knockout bracket (build_predicted_
    bracket's output): the favoured side highlighted, each side's own
    advance % for this specific matchup."""
    a, b = tie["team_a"], tie["team_b"]
    pa, pb = tie["pct_a"], tie["pct_b"]
    ba, bb = badge_lookup.get(a, ""), badge_lookup.get(b, "")
    winner = tie["winner"]
    as_ = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
           if winner == a else "padding:2px 5px;")
    bs_ = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
           if winner == b else "padding:2px 5px;")
    return (
        f"<div style='{as_}'>{_img(ba)}{a} "
        f"<span style='color:#856404;font-size:10px'>({pa:.0%})</span></div>"
        f"<div style='text-align:center;color:#888;font-size:11px;margin:3px 0'>vs</div>"
        f"<div style='{bs_}'>{_img(bb)}{b} "
        f"<span style='color:#856404;font-size:10px'>({pb:.0%})</span></div>"
    )


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
    season  = _CURRENT_EURO_SEASON


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
with st.spinner("Loading…"):
    try:
        standings, played_fixtures, remaining_fixtures, league_info, team_badges = fetch_all(
            comp_id, season, _API_KEY
        )
    except RuntimeError as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

badge_lookup: dict[str, str] = _badges_from_fixtures(played_fixtures + remaining_fixtures)
for row in standings:
    if row.get("strBadge") and row.get("strTeam"):
        badge_lookup.setdefault(row["strTeam"], row["strBadge"])
for name, logo in team_badges.items():
    badge_lookup.setdefault(name, logo)

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
    tab_league, tab_lp_results, tab_lp_pred, tab_ko_pred, tab_manual, tab_points_needed, tab_qual, tab_trivia = st.tabs(
        ["📊 Current Standings", "📅 Fixtures", "📈 League Stage Predictions", "🥊 Knockout Predictions",
         "🔮 Manual Predictions", "📐 Points Needed", "🔍 Qualifying", "🎲 Trivia"]
    )
else:
    tab_qual, tab_trivia = st.tabs(["🔍 Qualifying", "🎲 Trivia"])
    tab_league = None
    tab_lp_results = None
    tab_lp_pred = None
    tab_ko_pred = None
    tab_manual = None
    tab_points_needed = None


# ---------------------------------------------------------------------------
# Shared League Phase field/schedule/simulation -- computed once here (pure
# data, no UI calls: a `with st.spinner()`/`st.info()` placed here would
# render outside any tab's own panel, since this runs after st.tabs() but
# before any `with tab_x:` block) so League Stage Predictions, Knockout
# Predictions, and Manual Predictions can all reference the exact same
# _field/_real_schedule_ready/_real_results/_ls_result instead of each
# re-deriving (or worse, redundantly re-simulating) it. Each of those tabs
# still shows its own "not ready yet" message / readiness caption using
# _field_ready/_real_schedule_ready below -- only the DATA is shared, not
# any UI.
# ---------------------------------------------------------------------------
if has_lp:
    _field = _project_league_phase_field(comp_name, ratings_df)
    _fill_missing_badges([(f["team"], f["country"]) for f in _field], badge_lookup, _API_KEY)
    _field_cascade_note = {
        "Europa League": " + Champions League Play-off losers (parachuted down)",
        "Conference League": " + Europa League Play-off losers (parachuted down)",
    }.get(comp_name, "")
    _field_ready = len(_field) >= 36
    # Resolved unconditionally (not gated on _field_ready) -- Fixture
    # Difficulty (in the Trivia tab) uses this for whichever clubs ARE
    # already confirmed, even with a partial field.
    _field_ratings_df = _resolve_field_ratings(_field)
    if _field_ready:
        _real_schedule_ready = is_opponent_list_complete(comp_name, [f["team"] for f in _field])
        _real_schedule = derive_fixtures(comp_name) if _real_schedule_ready else None
        _real_results = (
            real_league_phase_results(comp_name, _API_KEY, tuple(f["team"] for f in _field))
            if _real_schedule_ready else {}
        )
        _n_pots, _opp_per_pot = _LEAGUE_PHASE_POTS[comp_name]
        _club_coeff = {f["team"]: get_coeff(f["team"], f["country"]) for f in _field}
        _n_sim = 30_000
        _home_advantage = EUROPEAN_COMPETITIONS[comp_name]["home_advantage"]
        _ls_cache_key = league_phase_sim_cache_key(
            comp_name, _n_sim, _home_advantage, _field, _field_ratings_df, _real_results,
        )
        _ls_result, _ls_points_by_club, _ls_rank_points = cached_league_phase_simulation(
            _ls_cache_key, _field, _club_coeff, _field_ratings_df,
            _n_pots, _opp_per_pot, _n_sim, _home_advantage, comp_name,
            _real_schedule, _real_results,
        )
        _lp_pos_cols = [str(i) for i in range(1, len(_field) + 1)]
        # 9th-24th (Knockout Play-off band) and 25th-36th (Elimination) --
        # summed directly from the per-position columns already computed
        # above, same basis reached_top8/top16/top24 are built from, not a
        # subtraction of those cumulative fields (mathematically identical,
        # but this reuses data already in hand with one less assumption
        # about those fields staying cumulative).
        _ko_band_cols = [c for c in _lp_pos_cols if 9 <= int(c) <= 24]
        _elim_band_cols = [c for c in _lp_pos_cols if int(c) >= 25]
        _ls_result["pct_knockout_band"] = _ls_result[_ko_band_cols].sum(axis=1) if _ko_band_cols else 0.0
        _ls_result["pct_elimination_band"] = _ls_result[_elim_band_cols].sum(axis=1) if _elim_band_cols else 0.0


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
                         width="content", hide_index=True,
                         height=len(lp_rows) * 35 + 42)
            st.caption(
                "Tiebreakers: 1) Head-to-head points; 2) Head-to-head goal difference; "
                "3) Head-to-head goals scored; 4) Head-to-head away goals scored; "
                "5) Goal difference; 6) Goals scored"
            )


# ---------------------------------------------------------------------------
# Tab — Fixtures (full League Phase calendar, past results + future fixtures,
# grouped by matchday -- a completed matchday starts collapsed, any matchday
# with at least one match still to play starts open). Replaces the old
# results-only "League Stage" tab; the dated/undated/not-yet-known fallback
# below is the same one "League Phase Fixtures" used inside League Stage
# Predictions, just moved here (that's a fixture/result listing, not a
# prediction, so this is where it belongs) and now wrapped per-matchday in
# an expander.
# ---------------------------------------------------------------------------
if tab_lp_results is not None:
    with tab_lp_results:
        if not _field_ready:
            st.info(
                f"Only {len(_field)} of 36 League Phase clubs are known for the {comp_name} so far "
                f"(confirmed direct entrants + each Play-off tie's favoured side{_field_cascade_note}) — "
                "the full fixture list will appear once the rest are confirmed."
            )
        else:
            def _gray_decided_pct(row):
                """Gray out just the ONE pre-match outcome % cell that
                matches what actually happened (e.g. the Draw column for a
                1-1) once a match is decided -- not all three, since the
                other two didn't happen and graying them too would lose
                the "this is what occurred" signal. style.apply(axis=1)
                hands the WHOLE row (not just a subset) -- a subset= on
                the apply call would only pass those columns, losing the
                "Score" lookup below."""
                score = row["Score"]
                if score == "—":
                    return ["" for _ in row.index]
                try:
                    hg, ag = (int(x) for x in score.split("–"))
                except (ValueError, AttributeError):
                    return ["" for _ in row.index]
                outcome_col = "Home Win" if hg > ag else ("Away Win" if ag > hg else "Draw")
                style = "background-color: #e0e0e0; color: #888"
                return [style if col == outcome_col else "" for col in row.index]

            _cl_dated = dated_schedule(comp_name)
            if _cl_dated:
                st.caption(
                    "UEFA's real, dated League Phase calendar, with each match's outcome probability."
                )
                _probs_by_pair = {
                    (_fx["strHomeTeam"], _fx["strAwayTeam"]): _fx
                    for _fx in single_match_outcome_probs(
                        _real_schedule, _field_ratings_df,
                        home_advantage=EUROPEAN_COMPETITIONS[comp_name]["home_advantage"],
                    )
                }
                _by_md: dict[int, list[dict]] = {}
                for _fx in _cl_dated:
                    _by_md.setdefault(_fx["matchday"], []).append(_fx)
                for _md in sorted(_by_md):
                    _md_fixtures = _by_md[_md]
                    _md_done = all((_fx["home"], _fx["away"]) in _real_results for _fx in _md_fixtures)
                    with st.expander(f"Matchday {_md}", expanded=not _md_done):
                        _md_rows = []
                        for _fx in sorted(_md_fixtures, key=lambda f: (f["date"], f["time"])):
                            _p = _probs_by_pair.get((_fx["home"], _fx["away"]), {})
                            _real = _real_results.get((_fx["home"], _fx["away"]))
                            _dt = datetime.strptime(_fx["date"], "%Y-%m-%d")
                            _md_rows.append({
                                "Date": f"{_dt.strftime('%a %d %b')} {_fx['time']}",
                                "HB": badge_lookup.get(_fx["home"], ""),
                                "Home": _fx["home"],
                                "Score": f"{_real[0]}–{_real[1]}" if _real else "—",
                                "Home Win": round(_p.get("pct_home", 0.0) * 100, 1),
                                "Draw": round(_p.get("pct_draw", 0.0) * 100, 1),
                                "Away Win": round(_p.get("pct_away", 0.0) * 100, 1),
                                "Away": _fx["away"],
                                "AB": badge_lookup.get(_fx["away"], ""),
                            })
                        _md_styled = pd.DataFrame(_md_rows).style.apply(_gray_decided_pct, axis=1)
                        st.dataframe(
                            _md_styled,
                            column_config={
                                "HB": st.column_config.ImageColumn("", width="small"),
                                "AB": st.column_config.ImageColumn("", width="small"),
                                "Home Win": st.column_config.NumberColumn("Home Win (pre-match)", format="%.1f%%"),
                                "Draw": st.column_config.NumberColumn("Draw (pre-match)", format="%.1f%%"),
                                "Away Win": st.column_config.NumberColumn("Away Win (pre-match)", format="%.1f%%"),
                            },
                            width="content", hide_index=True, height=len(_md_rows) * 35 + 38,
                        )
                        # Goals scored so far this matchday -- recomputed
                        # from _real_results on every page load, so it
                        # updates live as more of the matchday's games get
                        # decided, not just once the whole matchday is done.
                        _md_played_results = [
                            _real_results[(_fx["home"], _fx["away"])]
                            for _fx in _md_fixtures if (_fx["home"], _fx["away"]) in _real_results
                        ]
                        if _md_played_results:
                            _md_goals = sum(_hg + _ag for _hg, _ag in _md_played_results)
                            _md_avg = _md_goals / len(_md_played_results)
                            _md_complete = len(_md_played_results) == len(_md_fixtures)
                            _md_so_far = "" if _md_complete else " so far"
                            st.caption(
                                f"⚽ {_md_goals} goals scored{_md_so_far} in Matchday {_md} "
                                f"({_md_avg:.2f} per match, {len(_md_played_results)} of {len(_md_fixtures)} played)"
                            )
            elif _real_schedule_ready:
                st.caption(
                    "The real League Phase opponent list, with each match's outcome probability. "
                    "UEFA doesn't publish matchday-by-matchday order/dates alongside the opponent "
                    "list itself, so these aren't grouped or dated — home/away legs are real, though."
                )
                _fx_probs = single_match_outcome_probs(
                    _real_schedule, _field_ratings_df,
                    home_advantage=EUROPEAN_COMPETITIONS[comp_name]["home_advantage"],
                )
                _fx_rows = [{
                    "HB": badge_lookup.get(_fx["strHomeTeam"], ""),
                    "Home": _fx["strHomeTeam"],
                    "Score": (lambda _r: f"{_r[0]}–{_r[1]}" if _r else "—")(
                        _real_results.get((_fx["strHomeTeam"], _fx["strAwayTeam"]))),
                    "Home Win": round(_fx["pct_home"] * 100, 1),
                    "Draw": round(_fx["pct_draw"] * 100, 1),
                    "Away Win": round(_fx["pct_away"] * 100, 1),
                    "Away": _fx["strAwayTeam"],
                    "AB": badge_lookup.get(_fx["strAwayTeam"], ""),
                } for _fx in sorted(_fx_probs, key=lambda f: f["strHomeTeam"])]
                _fx_styled = pd.DataFrame(_fx_rows).style.apply(_gray_decided_pct, axis=1)
                st.dataframe(
                    _fx_styled,
                    column_config={
                        "HB": st.column_config.ImageColumn("", width="small"),
                        "AB": st.column_config.ImageColumn("", width="small"),
                        "Home Win": st.column_config.NumberColumn("Home Win (pre-match)", format="%.1f%%"),
                        "Draw": st.column_config.NumberColumn("Draw (pre-match)", format="%.1f%%"),
                        "Away Win": st.column_config.NumberColumn("Away Win (pre-match)", format="%.1f%%"),
                    },
                    width="content", hide_index=True, height=len(_fx_rows) * 35 + 38,
                )
            else:
                st.caption(
                    "UEFA's real League Phase draw hasn't been made yet. Once each club's opponent "
                    "list is entered, the real fixture list (with outcome probabilities) goes here."
                )


# ---------------------------------------------------------------------------
# Tab — League Stage Predictions (headline % for the 5 league-stage bands,
# then the full position-by-position table). Uses the shared _field/
# _real_schedule_ready/_ls_result computed once above this tab split.
# ---------------------------------------------------------------------------
if tab_lp_pred is not None:
    with tab_lp_pred:
        if not _field_ready:
            st.info(
                f"Only {len(_field)} of 36 League Phase clubs are known for the {comp_name} so far "
                f"(confirmed direct entrants + each Play-off tie's favoured side{_field_cascade_note}) — "
                "predictions need the full field and will appear once the rest are confirmed."
            )
        else:
            if _real_schedule_ready:
                _decided_note = (
                    f" **{len(_real_results)} of {len(_real_schedule)} matches are already decided** and "
                    "locked in at their real scoreline — only the rest are simulated."
                    if _real_results else " No League Phase matches have been played yet, so all of them are simulated."
                )
                st.caption(
                    "Simulates the full 36-club League Phase, using the **real, confirmed opponent "
                    f"list and home/away legs**.{_decided_note} Recomputes when the page cache refreshes."
                )
            else:
                st.caption(
                    "Simulates the full 36-club League Phase, using each Play-off tie's currently "
                    f"favoured side{_field_cascade_note} — no waiting for legs to actually be played. "
                    "UEFA's real League Phase draw hasn't been made yet, so each run draws its own "
                    "representative schedule following the *real* pot-based draw rules "
                    "(coefficient-ranked pots, no same-country pairings). Once the real opponent list "
                    "is known, this switches over to it automatically. Recomputes when the page cache refreshes."
                )
            # Avg Pos -- the same "expected finishing position" metric
            # render_prob_table itself sorts by (Σ position × probability
            # across the "1".."36" columns) -- recomputed here rather than
            # imported, since this headline table needs it as a plain
            # displayed/sorted column, not just an internal sort key.
            _pos_nums = pd.Series({c: int(c) for c in _lp_pos_cols})
            _avg_pos_series = _ls_result[_lp_pos_cols].mul(_pos_nums, axis=1).sum(axis=1)

            _ls_rows = []
            for _team, _r in _ls_result.iterrows():
                _ls_rows.append({
                    "Badge": badge_lookup.get(_team, ""),
                    "Team": _team,
                    "Pts": round(_r["expected_pts"], 2),
                    "GD": round(_r["expected_gd"], 2),
                    "Top 8": round(_r["reached_top8"] * 100, 1),
                    "Top 16": round(_r["reached_top16"] * 100, 1),
                    "Top 24": round(_r["reached_top24"] * 100, 1),
                    "Knockout Play-offs (9th-24th)": round(_r["pct_knockout_band"] * 100, 1),
                    "Elimination (25th-36th)": round(_r["pct_elimination_band"] * 100, 1),
                    "Avg Pos": round(_avg_pos_series[_team], 2),
                })
            _ls_df = pd.DataFrame(_ls_rows).sort_values("Avg Pos").reset_index(drop=True)
            _ls_df.insert(0, "Rank", _ls_df.index + 1)

            def _ls_zone_bg(rank: int) -> str:
                if rank <= 8:
                    return "background-color: #d4edda"
                if rank <= 24:
                    return "background-color: #fff3cd"
                return "background-color: #f8d7da"

            _ls_styled = _ls_df.style.apply(
                lambda row: [_ls_zone_bg(row["Rank"])] * len(row), axis=1)
            _pct_cols = ["Top 8", "Top 16", "Top 24", "Knockout Play-offs (9th-24th)", "Elimination (25th-36th)"]
            _ls_col_cfg = {
                "Rank": st.column_config.NumberColumn("Rank", width="small"),
                "Badge": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Pts": st.column_config.NumberColumn("Pts", format="%.2f", width="small"),
                "GD": st.column_config.NumberColumn("GD", format="%.2f", width="small"),
                "Avg Pos": st.column_config.NumberColumn("Avg Pos", format="%.2f", width="small"),
            }
            for _c in _pct_cols:
                _ls_col_cfg[_c] = st.column_config.NumberColumn(_c, format="%.1f%%", width="small")
            st.caption("🟢 Top 8 (direct to Round of 16)  🟡 Knockout Play-offs (9th-24th)  🔴 Eliminated (25th-36th)")
            st.dataframe(
                _ls_styled, column_config=_ls_col_cfg, width="content",
                hide_index=True, height=len(_ls_df) * 35 + 38,
            )

            # ── Full League Phase position-probability table ─────────────────
            # Bounds only make sense once the real draw exists -- before that,
            # every team is at 0 points and nothing is meaningfully "clinched"
            # or "impossible" yet (asserting either would claim certainty about
            # a schedule that isn't real). Replays _real_results alone (NOT
            # _ls_result's own pts_matrix, which mixes real locked-in points
            # with each simulation's own randomly-simulated remaining
            # fixtures) to get real current points + remaining-fixture-count
            # per team -- the same "current points" basis simulator.
            # position_bounds expects everywhere else it's used.
            if _real_schedule_ready:
                _lp_points = {f["team"]: 0 for f in _field}
                for (_h, _a), (_hg, _ag) in _real_results.items():
                    if _hg > _ag:
                        _lp_points[_h] = _lp_points.get(_h, 0) + 3
                    elif _hg == _ag:
                        _lp_points[_h] = _lp_points.get(_h, 0) + 1
                        _lp_points[_a] = _lp_points.get(_a, 0) + 1
                    else:
                        _lp_points[_a] = _lp_points.get(_a, 0) + 3
                _lp_standings = [{"strTeam": t, "intPoints": p} for t, p in _lp_points.items()]
                _lp_remaining = [
                    f for f in _real_schedule
                    if (f["strHomeTeam"], f["strAwayTeam"]) not in _real_results
                ]
                _lp_bounds = position_bounds(_lp_standings, _lp_remaining)
            else:
                _lp_bounds = None
            render_prob_table(
                _ls_result[_lp_pos_cols], badge_lookup=badge_lookup, bounds=_lp_bounds,
                title=f"{comp_name} League Phase — full position probabilities",
            )


# ---------------------------------------------------------------------------
# Tab — Knockout Predictions (knockout-stage reach probabilities + one
# concrete predicted bracket path). Same shared _ls_result/_field as League
# Stage Predictions -- Top 8/16/24 relabeled "(LS)" here since they sit
# alongside genuinely knockout-stage columns, plus "Knockouts" (9th-24th,
# the same band League Stage Predictions calls "Knockout Play-offs").
# ---------------------------------------------------------------------------
if tab_ko_pred is not None:
    with tab_ko_pred:
        if not _field_ready:
            st.info(
                f"Only {len(_field)} of 36 League Phase clubs are known for the {comp_name} so far "
                f"(confirmed direct entrants + each Play-off tie's favoured side{_field_cascade_note}) — "
                "knockout predictions need the full field and will appear once the rest are confirmed."
            )
        else:
            _ko_rows = []
            for _team, _r in _ls_result.iterrows():
                _ko_rows.append({
                    "Badge": badge_lookup.get(_team, ""),
                    "Team": _team,
                    "Top 8 (LS)": round(_r["reached_top8"] * 100, 1),
                    "Top 16 (LS)": round(_r["reached_top16"] * 100, 1),
                    "Top 24 (LS)": round(_r["reached_top24"] * 100, 1),
                    "Knockouts": round(_r["pct_knockout_band"] * 100, 1),
                    "Reach R16": round(_r["reached_r16"] * 100, 1),
                    "Reach QF": round(_r["reached_qf"] * 100, 1),
                    "Reach SF": round(_r["reached_sf"] * 100, 1),
                    "Reach Final": round(_r["reached_final"] * 100, 1),
                    "Win it all": round(_r["won_competition"] * 100, 1),
                })
            _ko_df = pd.DataFrame(_ko_rows)
            _ko_pct_cols = ["Top 8 (LS)", "Top 16 (LS)", "Top 24 (LS)", "Knockouts",
                            "Reach R16", "Reach QF", "Reach SF", "Reach Final", "Win it all"]
            _ko_col_cfg = {
                "Badge": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
            }
            for _c in _ko_pct_cols:
                _ko_col_cfg[_c] = st.column_config.NumberColumn(_c, format="%.1f%%", width="small")
            st.caption(
                "\"(LS)\" columns are the same League Stage finish bands as the League Stage "
                "Predictions tab -- shown here alongside the knockout-stage reach probabilities "
                "they feed into. \"Knockouts\" = chance of actually PLAYING in the Knockout "
                "Play-off round (finishing 9th-24th), as opposed to going straight to the Round "
                "of 16 (top 8) or being eliminated (25th-36th)."
            )
            st.dataframe(
                _ko_df, column_config=_ko_col_cfg, width="content",
                hide_index=True, height=len(_ko_df) * 35 + 38,
            )

            # ── Predicted Knockout Bracket ───────────────────────────────────
            st.markdown("#### Predicted Knockout Bracket")
            st.caption(
                "One concrete predicted path through the knockout stage, picking the favoured "
                "side at every tie from the Knockout Play-off round through the Final — not the "
                "same thing as the reach-probability table above, which shows each club's *own* "
                "chances across every possible bracket outcome, not just this one favourites-only path."
            )
            with st.spinner("Building the predicted bracket…"):
                _bracket = build_predicted_bracket(
                    field=_field, club_coeff=_club_coeff, ratings_df=_field_ratings_df,
                    n_pots=_n_pots, opponents_per_pot=_opp_per_pot, n_sim=_n_sim,
                    home_advantage=_home_advantage,
                    schedule=_real_schedule, real_results=_real_results,
                )
            _round_labels = [
                ("ko_playoff", "Knockout Play-off (9th–24th)"),
                ("r16", "Round of 16"),
                ("qf", "Quarter-finals"),
                ("sf", "Semi-finals"),
                ("final", "Final"),
            ]
            for _key, _label in _round_labels:
                st.markdown(f"**{_label}**")
                _cards = []
                for _tie in _bracket[_key]:
                    _cards.append(f"""
<div style="border:1px solid #dee2e6;border-radius:8px;padding:8px 10px;
            margin:0 8px 8px 0;background:#fff;width:230px;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  {_bracket_tie_html(_tie, badge_lookup)}
</div>""")
                st.markdown(f"<div style='display:flex;flex-wrap:wrap'>{''.join(_cards)}</div>",
                            unsafe_allow_html=True)
            st.markdown(f"🏆 **Predicted champion: {_bracket['champion']}**")


# ---------------------------------------------------------------------------
# Tab — Manual Predictions (enter your own League Phase scorelines, see
# updated standings via the real UEFA tiebreak chain, then run a one-off
# what-if simulation scoped to just the 5 league-stage finish bands --
# deliberately NOT the full 1-36 position table, per explicit instruction to
# cap this tab's predictions at Top 8/16/24/Knockout Play-offs/Elimination
# only. Uses its own session_state-fingerprint cache, not the shared
# cached_league_phase_simulation -- this is a one-off hypothetical scenario,
# same reasoning football_rankings.py's domestic Manual Predictions tab
# already uses its own separate cache rather than sharing the main
# Predictions tab's cache.
# ---------------------------------------------------------------------------
if tab_manual is not None:
    with tab_manual:
        if not _field_ready:
            st.info(
                f"Only {len(_field)} of 36 League Phase clubs are known for the {comp_name} so far "
                f"(confirmed direct entrants + each Play-off tie's favoured side{_field_cascade_note}) — "
                "manual predictions need the full field and will appear once the rest are confirmed."
            )
        elif not _real_schedule_ready:
            st.info(
                "UEFA's real League Phase draw hasn't been made yet — manual predictions need the "
                "real fixture list, not a freshly-redrawn synthetic one, so they'll appear here once "
                "the draw is known."
            )
        else:
            # Keyed by (home, away) -> the full dated-schedule fixture dict
            # (matchday/date/time), not just the matchday number, so the
            # editor can be sorted the same way the Fixtures tab is --
            # chronologically, not alphabetically by home team.
            _dated_by_pair = {(_fx["home"], _fx["away"]): _fx for _fx in dated_schedule(comp_name)}
            _unplayed_schedule = [
                f for f in _real_schedule
                if (f["strHomeTeam"], f["strAwayTeam"]) not in _real_results
            ]

            if not _unplayed_schedule:
                st.info("All League Phase matches are already decided.")
            else:
                _ver_key = f"euro_manual_pred_ver_{comp_name}"
                _sim_store_key = f"euro_manual_sim_{comp_name}"
                if _ver_key not in st.session_state:
                    st.session_state[_ver_key] = 0

                def _build_manual_fix_df(fixtures):
                    def _sort_key(x):
                        _fx = _dated_by_pair.get((x["strHomeTeam"], x["strAwayTeam"])) or {}
                        return (_fx.get("matchday", 99), _fx.get("date", ""), _fx.get("time", ""), x["strHomeTeam"])

                    rows = []
                    for f in sorted(fixtures, key=_sort_key):
                        _fx = _dated_by_pair.get((f["strHomeTeam"], f["strAwayTeam"])) or {}
                        rows.append({
                            "MD":   _fx.get("matchday", pd.NA),
                            "HB":   badge_lookup.get(f["strHomeTeam"], ""),
                            "Home": f["strHomeTeam"],
                            "HG":   pd.NA, "AG": pd.NA,
                            "Away": f["strAwayTeam"],
                            "AB":   badge_lookup.get(f["strAwayTeam"], ""),
                        })
                    df = pd.DataFrame(rows)
                    df["HG"] = df["HG"].astype(pd.Int64Dtype())
                    df["AG"] = df["AG"].astype(pd.Int64Dtype())
                    return df

                _manual_col_cfg = {
                    "MD":   st.column_config.NumberColumn("MD",   width="small"),
                    "HB":   st.column_config.ImageColumn("",      width="small"),
                    "Home": st.column_config.TextColumn("Home",   width="medium"),
                    "HG":   st.column_config.NumberColumn("HG",   min_value=0, max_value=20, step=1, width="small"),
                    "AG":   st.column_config.NumberColumn("AG",   min_value=0, max_value=20, step=1, width="small"),
                    "Away": st.column_config.TextColumn("Away",   width="medium"),
                    "AB":   st.column_config.ImageColumn("",      width="small"),
                }

                _editor_key    = f"euro_manual_editor_{comp_name}_{st.session_state[_ver_key]}"
                _base_df       = _build_manual_fix_df(_unplayed_schedule)
                _editor_height = min(len(_base_df), 15) * 35 + 38

                _hdr_col, _btn_col, _ = st.columns([2, 1, 3], vertical_alignment="center")
                _metric_ph = _hdr_col.empty()
                _clear_ph  = _btn_col.empty()
                _edited_df = st.data_editor(
                    _base_df, column_config=_manual_col_cfg,
                    disabled=["MD", "HB", "Home", "Away", "AB"],
                    width="content", hide_index=True,
                    height=_editor_height, key=_editor_key,
                )

                _filled_mask = _edited_df[["HG", "AG"]].notna().all(axis=1)
                _metric_ph.markdown(f"### Predicted: {int(_filled_mask.sum())} / {len(_unplayed_schedule)}")
                if _clear_ph.button("🗑 Clear", use_container_width=True, key=f"euro_manual_clear_{comp_name}"):
                    st.session_state[_ver_key] += 1
                    st.session_state.pop(_sim_store_key, None)
                    st.rerun()

                _predicted_results = dict(_real_results)
                _user_scorelines = []
                for _, _row in _edited_df[_filled_mask].iterrows():
                    _hg, _ag = int(_row["HG"]), int(_row["AG"])
                    _predicted_results[(_row["Home"], _row["Away"])] = (_hg, _ag)
                    _user_scorelines.append((_row["Home"], _row["Away"], _hg, _ag))

                _user_matches = [
                    {"strHomeTeam": h, "strAwayTeam": a, "intHomeScore": hg, "intAwayScore": ag}
                    for h, a, hg, ag in _user_scorelines
                ]

                st.divider()
                st.markdown("### Updated standings")
                _computed = _compute_league_standings(lp_played + _user_matches, badge_lookup)

                def _manual_zone_bg(pos: int) -> str:
                    if pos <= cfg.get("n_direct", 8):
                        return "#d4edda"
                    if pos <= cfg.get("n_direct", 8) + cfg.get("n_playoff", 16):
                        return "#fff3cd"
                    return "#f8d7da"

                _upd_rows = [{
                    "Pos":   r["intRank"],
                    "Badge": r["strBadge"],
                    "Team":  r["strTeam"],
                    "P":     r["P"], "W": r["W"], "D": r["D"], "L": r["L"],
                    "GF":    r["GF"], "GA": r["GA"], "GD": r["GD"], "Pts": r["Pts"],
                    "_bg":   _manual_zone_bg(r["intRank"]),
                } for r in _computed]
                if not _upd_rows:
                    # No League Phase matches played yet and no predictions
                    # entered either -- _compute_league_standings has
                    # nothing to rank, and an all-empty DataFrame has no
                    # columns at all (not even "_bg") to drop.
                    st.info("Enter a few predictions above to see updated standings.")
                else:
                    _upd_df     = pd.DataFrame(_upd_rows)
                    _styled_upd = (
                        _upd_df.drop(columns=["_bg"]).style
                        .apply(lambda row: [f"background-color: {_upd_rows[row.name]['_bg']}"] * len(row), axis=1)
                        .set_properties(subset=["Team", "Pts"], **{"font-weight": "bold"})
                    )
                    _upd_col_cfg = {
                        "Pos":   st.column_config.NumberColumn("Pos",  width="small"),
                        "Badge": st.column_config.ImageColumn("",      width="small"),
                        "Team":  st.column_config.TextColumn("Team",  width="medium"),
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
                    st.dataframe(_styled_upd, column_config=_upd_col_cfg,
                                 width="content", hide_index=True,
                                 height=len(_upd_rows) * 35 + 42)

                st.divider()
                st.markdown("### Projected League Stage finish (with your predictions)")
                _pred_fp = (tuple(sorted(_user_scorelines)), _n_sim)
                _cached  = st.session_state.get(_sim_store_key)
                if st.button(f"▶  Run {_n_sim:,} simulations with predictions", type="primary",
                             use_container_width=True, key=f"euro_manual_run_{comp_name}"):
                    with st.spinner(f"Running {_n_sim:,} simulations…"):
                        _manual_result = simulate_competition_winner(
                            field=_field, club_coeff=_club_coeff, ratings_df=_field_ratings_df,
                            n_pots=_n_pots, opponents_per_pot=_opp_per_pot, n_sim=_n_sim,
                            home_advantage=_home_advantage, comp_name=comp_name,
                            track_points=False, schedule=_real_schedule,
                            real_results=_predicted_results,
                        )
                    st.session_state[_sim_store_key] = {"result": _manual_result, "fingerprint": _pred_fp}
                    _cached = st.session_state[_sim_store_key]

                if _cached:
                    if _cached["fingerprint"] != _pred_fp:
                        st.warning("⚠ Predictions changed since last run — press ▶ to update.")
                    _mr = _cached["result"]
                    _mr_pos_cols  = [str(i) for i in range(1, len(_field) + 1)]
                    _mr_ko_cols   = [c for c in _mr_pos_cols if 9 <= int(c) <= 24]
                    _mr_elim_cols = [c for c in _mr_pos_cols if int(c) >= 25]

                    def _fmt_delta_cell(new_frac: float, base_frac: float) -> str:
                        """'XX.X%' plus an arrow + signed change vs the main,
                        locked 30,000-sim baseline (_ls_result, computed once
                        in the shared block above) -- so it's clear how much
                        the user's own entered scorelines moved each band,
                        not just what the new number is."""
                        new_v = round(new_frac * 100, 1)
                        delta = round(new_v - round(base_frac * 100, 1), 1)
                        if delta > 0.05:
                            return f"{new_v:.1f}% (▲+{delta:.1f})"
                        if delta < -0.05:
                            return f"{new_v:.1f}% (▼{delta:.1f})"
                        return f"{new_v:.1f}%"

                    _mr_rows = []
                    for _team, _r in _mr.iterrows():
                        _base = _ls_result.loc[_team]
                        _mr_rows.append({
                            "Badge": badge_lookup.get(_team, ""),
                            "Team": _team,
                            "Top 8": _fmt_delta_cell(_r["reached_top8"], _base["reached_top8"]),
                            "Top 16": _fmt_delta_cell(_r["reached_top16"], _base["reached_top16"]),
                            "Top 24": _fmt_delta_cell(_r["reached_top24"], _base["reached_top24"]),
                            "Knockout Play-offs (9th-24th)": _fmt_delta_cell(
                                _r[_mr_ko_cols].sum(), _base["pct_knockout_band"]),
                            "Elimination (25th-36th)": _fmt_delta_cell(
                                _r[_mr_elim_cols].sum(), _base["pct_elimination_band"]),
                        })
                    _mr_df = pd.DataFrame(_mr_rows)
                    _mr_pct_cols = ["Top 8", "Top 16", "Top 24",
                                    "Knockout Play-offs (9th-24th)", "Elimination (25th-36th)"]
                    _mr_col_cfg = {
                        "Badge": st.column_config.ImageColumn("", width="small"),
                        "Team": st.column_config.TextColumn("Team", width="medium"),
                    }
                    for _c in _mr_pct_cols:
                        _mr_col_cfg[_c] = st.column_config.TextColumn(_c, width="medium")
                    st.caption(
                        "Each cell also shows the change versus the main, locked 30,000-simulation "
                        "baseline (the same numbers shown in League Stage Predictions) -- ▲ = your "
                        "entered results improved that band's chances, ▼ = they hurt it."
                    )
                    st.dataframe(
                        _mr_df, column_config=_mr_col_cfg, width="content",
                        hide_index=True, height=len(_mr_df) * 35 + 38,
                    )
                else:
                    st.info("Enter predictions above then press **▶ Run simulations**.")


# ---------------------------------------------------------------------------
# Tab — Points Needed. For each candidate League Phase points total, the %
# of the shared 30,000-simulation run (_ls_rank_points, same baseline
# League Stage Predictions uses) in which that many points would have been
# enough to finish Top 8 (direct Round of 16) or Top 24 (knockout
# play-off) -- same methodology as theanalyst.com's and arXiv 2508.20075's
# own UCL League Phase points-needed studies: rank every simulated run by
# points (ties broken by GD/GF, this project's existing convention), take
# the 8th/24th-placed club's own points in that run, then see what
# fraction of runs each candidate total would have cleared.
# ---------------------------------------------------------------------------
if tab_points_needed is not None:
    with tab_points_needed:
        if not _field_ready:
            st.info(
                f"Only {len(_field)} of 36 League Phase clubs are known for the {comp_name} so far "
                f"(confirmed direct entrants + each Play-off tie's favoured side{_field_cascade_note}) — "
                "points-needed estimates need the full field and will appear once the rest are confirmed."
            )
        else:
            st.caption(
                "Based on the same 30,000-simulation League Phase run behind League Stage "
                "Predictions. Methodology: "
                "[theanalyst.com](https://theanalyst.com/articles/champions-league-group-stage-how-many-points-qualify-knockouts), "
                "[arXiv:2508.20075](https://arxiv.org/abs/2508.20075)."
            )

            _pn_rank8 = _ls_rank_points["rank8"]
            _pn_rank24 = _ls_rank_points["rank24"]
            _pn_games = _n_pots * _opp_per_pot
            _pn_max_pts = _pn_games * 3

            def _pn_min_points_for(arr: "pd.Series | object", threshold: float) -> int | None:
                """Lowest points total at which >= threshold fraction of simulated
                runs would have been enough to clear that cut-off."""
                for p in range(_pn_max_pts + 1):
                    if (arr <= p).mean() >= threshold:
                        return p
                return None

            _pn_c1, _pn_c2 = st.columns(2)
            for _pn_col, _pn_title, _pn_arr in (
                (_pn_c1, "🏆 Top 8 — direct Round of 16", _pn_rank8),
                (_pn_c2, "🥊 Top 24 — knockout play-off", _pn_rank24),
            ):
                with _pn_col:
                    st.markdown(f"#### {_pn_title}")
                    _pn_50 = _pn_min_points_for(_pn_arr, 0.5)
                    _pn_90 = _pn_min_points_for(_pn_arr, 0.9)
                    _pn_99 = _pn_min_points_for(_pn_arr, 0.99)
                    st.metric("Toss-up (~50%) at", f"{_pn_50} pts" if _pn_50 is not None else "—")
                    st.metric("Safe (~90%) at", f"{_pn_90} pts" if _pn_90 is not None else "—")
                    st.metric("Virtually certain (~99%) at", f"{_pn_99} pts" if _pn_99 is not None else "—")

            st.divider()
            _pn_rows = [
                {
                    "Points": p,
                    "Top 8 chance": float((_pn_rank8 <= p).mean()) * 100,
                    "Top 24 chance": float((_pn_rank24 <= p).mean()) * 100,
                }
                for p in range(_pn_max_pts + 1)
            ]
            _pn_df = pd.DataFrame(_pn_rows)
            _pn_styled = (
                _pn_df.style
                .hide(axis="index")
                .apply(_green_col, axis=0, subset=["Top 8 chance", "Top 24 chance"])
                .format("{:.1f}%", subset=["Top 8 chance", "Top 24 chance"])
                .set_properties(subset=["Points"], **{"font-weight": "bold", "text-align": "center"})
            )
            st.dataframe(
                _pn_styled,
                column_config={
                    "Points": st.column_config.NumberColumn("Points", width=70),
                    "Top 8 chance": st.column_config.TextColumn("Enough for Top 8", width=150),
                    "Top 24 chance": st.column_config.TextColumn("Enough for Top 24", width=150),
                },
                width="content", hide_index=True, height=min(len(_pn_df) * 35 + 38, 600),
            )
            st.caption(
                "\"Enough\" = the share of the 30,000 simulated League Phase seasons in which that "
                "many points would have matched or beaten the 8th/24th-placed club's own total "
                "(ties broken by goal difference, then goals scored)."
            )


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
                and len(legs) >= (1 if rnd in _PLAYOFF_ROUND_NAMES and len(legs) == 1 else 2)
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
# Tab — Trivia
# ---------------------------------------------------------------------------
with tab_trivia:
    st.markdown(f"### {comp_name} — Nations & Clubs")
    with st.spinner("Crunching this competition's numbers…"):
        _trivia = competition_trivia(comp_name, _API_KEY)

    _lp_by_country = _trivia["league_phase"]
    _elim_by_country = _trivia["eliminated"]
    _lp_clubs = sum(len(v) for v in _lp_by_country.values())
    _elim_clubs = sum(len(v) for v in _elim_by_country.values())

    def _country_table(by_country: dict) -> pd.DataFrame:
        rows = [{"Country": c, "Clubs": len(teams), "Teams": ", ".join(teams)}
                for c, teams in by_country.items()]
        return pd.DataFrame(rows).sort_values(["Clubs", "Country"], ascending=[False, True]).reset_index(drop=True)

    st.markdown(f"#### 🏆 League Phase — {_lp_clubs} clubs from {len(_lp_by_country)} nations")
    _lp_df = _country_table(_lp_by_country)
    st.dataframe(
        _lp_df, width="content", hide_index=True,
        column_config={"Clubs": st.column_config.NumberColumn("Clubs", width="small")},
        height=len(_lp_df) * 35 + 38,
    )

    st.markdown(f"#### 🚪 Eliminated in Qualifying — {_elim_clubs} clubs from {len(_elim_by_country)} nations")
    _cascade_note = {
        "Champions League": " (including Play-off losers who cascaded into the Europa League's League Phase instead of dropping out of Europe entirely)",
        "Europa League": " (including Play-off losers who cascaded into the Conference League's League Phase instead of dropping out of Europe entirely)",
    }.get(comp_name, "")
    st.caption(
        f"Clubs knocked out of {comp_name}'s own qualifying bracket (First Qualifying Round through "
        f"the Play-off round) before reaching its League Phase{_cascade_note}."
    )
    _elim_df = _country_table(_elim_by_country)
    st.dataframe(
        _elim_df, width="content", hide_index=True,
        column_config={"Clubs": st.column_config.NumberColumn("Clubs", width="small")},
        height=min(len(_elim_df) * 35 + 38, 700),
    )

    st.divider()
    st.markdown("### 🌍 General Trivia — All Three Competitions Combined")
    with st.spinner("Crunching season-wide numbers…"):
        _overall = overall_trivia(_API_KEY)
    _c1, _c2, _c3 = st.columns(3)
    _c1.metric("Total clubs entered Europe", _overall["total_clubs"])
    _c1.metric("Total nations represented", _overall["total_nations"])
    _c2.metric("Reached a League Phase", _overall["league_phase_clubs"])
    _c2.metric("...from nations", _overall["league_phase_nations"])
    _c3.metric("Eliminated in qualifying", _overall["eliminated_clubs"])
    _c3.metric("...from nations", _overall["eliminated_nations"])
    st.caption(
        "\"Eliminated\" here means genuinely out of Europe this season — a club that lost a "
        "Play-off tie but cascaded into a lower competition's League Phase (Champions League → "
        "Europa League, Europa League → Conference League) counts as having reached a League "
        "Phase, not as eliminated, unlike the per-competition figures above."
    )

    # ── Fixture Difficulty ────────────────────────────────────────────────
    if has_lp:
        st.divider()
        st.markdown(f"### 📊 {comp_name} — Fixture Difficulty")
        _opponents_by_team = partial_opponents_by_team(comp_name)
        _known_field = [f for f in _field if f["team"] in _opponents_by_team]
        if _known_field:
            if len(_known_field) < len(_field):
                st.caption(
                    "Each confirmed club's League Phase opponents ranked by average Opta power "
                    f"rating — higher average = tougher group of 8. {len(_known_field)} of "
                    f"{len(_field)} clubs confirmed so far; the rest join as they're entered."
                )
            else:
                st.caption(
                    "Each club's League Phase opponents ranked by average Opta power rating — "
                    "higher average = tougher group of 8."
                )
            _opta_by_team = dict(zip(_field_ratings_df["team"], _field_ratings_df["opta_rating"]))
            _diff_rows = []
            for _f in _known_field:
                _team = _f["team"]
                _opps = _opponents_by_team[_team]
                _avg_opp_rating = sum(_opta_by_team.get(o, 0.0) for o in _opps) / len(_opps)
                _diff_rows.append({
                    "Badge": badge_lookup.get(_team, ""),
                    "Team": _team,
                    "Country": _f["country"],
                    "Avg Opponent Opta Rating": round(_avg_opp_rating, 1),
                })
            _diff_df = pd.DataFrame(_diff_rows).sort_values(
                "Avg Opponent Opta Rating", ascending=False).reset_index(drop=True)
            _diff_df.insert(0, "Difficulty Rank", _diff_df.index + 1)
            st.dataframe(
                _diff_df,
                column_config={
                    "Badge": st.column_config.ImageColumn("", width="small"),
                    "Avg Opponent Opta Rating": st.column_config.NumberColumn(
                        "Avg Opponent Opta Rating", format="%.1f"),
                },
                width="content", hide_index=True, height=len(_diff_df) * 35 + 38,
            )
        else:
            st.caption(
                "Will rank each club's 8 (or 6, for the Conference League) League Phase opponents "
                "by average Opta power rating once the real draw is known."
            )

