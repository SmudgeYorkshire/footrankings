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
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import EUROPEAN_COMPETITIONS, LEAGUES
from api_football_fetcher import ApiFootballClient
from _split_season import build_h2h, rank_tied_group
from simulator import two_leg_advance_odds
from qualifying_bracket import PLAYOFF_BRACKET, CONFIRMED_LEAGUE_PHASE
from club_coefficients import CLUB_COEFFICIENTS, get_coeff
from league_phase_simulator import simulate_competition_winner, build_predicted_bracket, single_match_outcome_probs
from league_phase_fixtures import (
    is_opponent_list_complete, derive_fixtures, partial_opponents_by_team, dated_schedule,
)
from qualifying_projection import (
    _PLAYOFF_ROUND_NAMES,
    _load_combined_ratings, _resolve_field_ratings,
    _leg_aggregate_winner, _resolve_bracket_side,
    _resolve_playoff_tie_odds, _project_league_phase_field,
    _normalize_club_name,
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


_NAME_FILLER_TOKENS = {"fc", "cf", "sc", "as", "ac", "kv", "sv", "afc", "cfc", "ss", "tsg"}
# English exonym -> API-Football's local-language spelling, for city names
# that show up as part of a club name (our static entrant lists sometimes
# use the English form, API-Football's domestic-league data the local one).
_CITY_EXONYMS = {"munich": "munchen", "prague": "praha", "milan": "milano", "st": "saint"}


def _fuzzy_key(name: str) -> str:
    """Accent/case-folded name with common club-name filler tokens (FC, AS,
    KV, ...) dropped and known city exonyms normalized, for matching e.g.
    our "Porto" against API-Football's "FC Porto", or "Bayern Munich"
    against "Bayern München"."""
    tokens = [_CITY_EXONYMS.get(t, t) for t in _normalize_club_name(name).replace("-", " ").replace(".", " ").split()
              if t not in _NAME_FILLER_TOKENS]
    return " ".join(tokens)


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


# ---------------------------------------------------------------------------
# Play-off bracket resolution
# ---------------------------------------------------------------------------

def _playoff_tie_odds_html(resolved: dict, badge_lookup: dict) -> str:
    """Renders a resolved Play-off tie: either the decided winner
    (highlighted, matching _tie_card_html's style) or each side's live
    advance probability for this specific tie."""
    t1, t2 = resolved["team1"], resolved["team2"]
    b1, b2 = badge_lookup.get(t1, ""), badge_lookup.get(t2, "")

    if resolved["status"] == "decided":
        winner = resolved["winner"]
        t1s = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
               if winner == t1 else "padding:2px 5px;")
        t2s = ("font-weight:700;background:#d4edda;border-radius:3px;padding:2px 5px;"
               if winner == t2 else "padding:2px 5px;")
        return (
            f"<div style='{t1s}'>{_img(b1)}{t1}</div>"
            f"<div style='text-align:center;color:#888;font-size:11px;margin:3px 0'>vs</div>"
            f"<div style='{t2s}'>{_img(b2)}{t2}</div>"
            f"<div style='text-align:center;font-size:11px;color:#2e7d32;font-weight:bold;"
            f"margin-top:3px'>Decided — {winner} advances</div>"
        )

    t1_pct, t2_pct = resolved["team1_adv"], resolved["team2_adv"]
    leg1_note = ""
    if resolved.get("leg1_played") and resolved.get("leg1_score"):
        hs, aws = resolved["leg1_score"]
        leg1_note = (f"<div style='text-align:center;font-size:10px;color:#888;"
                     f"margin-top:3px'>Leg 1: {hs}–{aws}</div>")
    return (
        f"<div style='padding:2px 5px'>{_img(b1)}{t1} "
        f"<span style='color:#856404;font-size:10px'>({t1_pct:.0%})</span></div>"
        f"<div style='text-align:center;color:#888;font-size:11px;margin:3px 0'>vs</div>"
        f"<div style='padding:2px 5px'>{_img(b2)}{t2} "
        f"<span style='color:#856404;font-size:10px'>({t2_pct:.0%})</span></div>"
        f"{leg1_note}"
    )


def _bracket_tie_html(tie: dict, badge_lookup: dict) -> str:
    """Renders one tie of a predicted knockout bracket (build_predicted_
    bracket's output): the favoured side highlighted, each side's own
    advance % for this specific matchup -- same visual language as
    _playoff_tie_odds_html's undecided-tie case."""
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
    tab_league, tab_lp_results, tab_lp_pred, tab_qual, tab_qual_pred = st.tabs(
        ["📊 Standings", "📋 League Stage", "📈 League Stage Predictions", "🔍 Qualifying", "🔮 Qualifying Predictions"]
    )
else:
    tab_qual, tab_qual_pred = st.tabs(["🔍 Qualifying", "🔮 Qualifying Predictions"])
    tab_league = None
    tab_lp_results = None
    tab_lp_pred = None


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
# Tab — League Stage Predictions (Monte Carlo, works before the phase starts)
# ---------------------------------------------------------------------------
if tab_lp_pred is not None:
    with tab_lp_pred:
        _field = _project_league_phase_field(comp_name, ratings_df)
        _fill_missing_badges([(f["team"], f["country"]) for f in _field], badge_lookup, _API_KEY)
        _cascade_note = {
            "Europa League": " + Champions League Play-off losers (parachuted down)",
            "Conference League": " + Europa League Play-off losers (parachuted down)",
        }.get(comp_name, "")
        if len(_field) < 36:
            st.info(
                f"Only {len(_field)} of 36 League Phase clubs are known for the {comp_name} so far "
                f"(confirmed direct entrants + each Play-off tie's favoured side{_cascade_note}) — "
                "competition-winner predictions need the full field and will appear once the rest are confirmed."
            )
        else:
            _real_schedule_ready = is_opponent_list_complete(comp_name, [f["team"] for f in _field])
            _real_schedule = derive_fixtures(comp_name) if _real_schedule_ready else None
            if _real_schedule_ready:
                st.caption(
                    "Simulates the full 36-club League Phase through to a champion, using the **real, "
                    "confirmed opponent list and home/away legs** below — then applies the real, fixed "
                    "knockout bracket (top 8 direct to the Round of 16, 9th-24th via a knockout "
                    "play-off, 25th-36th eliminated). Recomputes when the page cache refreshes."
                )
            else:
                st.caption(
                    "Simulates the full 36-club League Phase through to a champion, using each Play-off "
                    f"tie's currently favoured side{_cascade_note} — no waiting for legs to actually be "
                    "played. UEFA's real League Phase draw hasn't been made yet, so each run draws its "
                    "own representative schedule following the *real* pot-based draw rules "
                    "(coefficient-ranked pots, no same-country pairings) rather than the actual fixture "
                    "list — then applies the real, fixed knockout bracket (top 8 direct to the Round of "
                    "16, 9th-24th via a knockout play-off, 25th-36th eliminated). Once the real opponent "
                    "list is entered below, this switches over to it automatically. Recomputes when the "
                    "page cache refreshes."
                )
            _n_pots, _opp_per_pot = _LEAGUE_PHASE_POTS[comp_name]
            _club_coeff = {f["team"]: get_coeff(f["team"], f["country"]) for f in _field}
            _field_ratings_df = _resolve_field_ratings(_field)
            # A fixed real schedule holds still across reruns, so more simulations
            # buys real precision -- for the synthetic pot-based schedule (which is
            # freshly re-drawn every rerun), that variance dominates instead, so
            # there's less to gain from raising n_sim there.
            _n_sim = 10_000 if _real_schedule_ready else 3_000
            with st.spinner("Simulating the League Phase and knockout stage…"):
                _ls_result = simulate_competition_winner(
                    field=_field, club_coeff=_club_coeff, ratings_df=_field_ratings_df,
                    n_pots=_n_pots, opponents_per_pot=_opp_per_pot, n_sim=_n_sim,
                    home_advantage=1.05, schedule=_real_schedule,
                )
            _ls_rows = []
            for _team, _r in _ls_result.iterrows():
                _ls_rows.append({
                    "Badge": badge_lookup.get(_team, ""),
                    "Team": _team,
                    "Top 8": round(_r["reached_top8"] * 100, 1),
                    "Top 16": round(_r["reached_top16"] * 100, 1),
                    "Top 24": round(_r["reached_top24"] * 100, 1),
                    "Reach R16": round(_r["reached_r16"] * 100, 1),
                    "Reach QF": round(_r["reached_qf"] * 100, 1),
                    "Reach SF": round(_r["reached_sf"] * 100, 1),
                    "Reach Final": round(_r["reached_final"] * 100, 1),
                    "Win it all": round(_r["won_competition"] * 100, 1),
                })
            _ls_df = pd.DataFrame(_ls_rows)
            _pct_cols = ["Top 8", "Top 16", "Top 24", "Reach R16", "Reach QF", "Reach SF", "Reach Final", "Win it all"]
            _ls_col_cfg = {
                "Badge": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
            }
            for _c in _pct_cols:
                _ls_col_cfg[_c] = st.column_config.NumberColumn(_c, format="%.1f%%", width="small")
            st.dataframe(
                _ls_df, column_config=_ls_col_cfg, use_container_width=True,
                hide_index=True, height=len(_ls_df) * 35 + 38,
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
                    home_advantage=1.05, schedule=_real_schedule,
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

            # ── League Phase Fixtures ─────────────────────────────────────
            st.markdown("#### League Phase Fixtures")
            _cl_dated = dated_schedule(comp_name)
            if _cl_dated:
                st.caption(
                    "UEFA's real, dated League Phase calendar, with each match's outcome probability."
                )
                _probs_by_pair = {
                    (_fx["strHomeTeam"], _fx["strAwayTeam"]): _fx
                    for _fx in single_match_outcome_probs(_real_schedule, _field_ratings_df, home_advantage=1.05)
                }
                _by_md: dict[int, list[dict]] = {}
                for _fx in _cl_dated:
                    _by_md.setdefault(_fx["matchday"], []).append(_fx)
                for _md in sorted(_by_md):
                    st.markdown(f"**Matchday {_md}**")
                    _md_rows = []
                    for _fx in sorted(_by_md[_md], key=lambda f: (f["date"], f["time"])):
                        _p = _probs_by_pair.get((_fx["home"], _fx["away"]), {})
                        _dt = datetime.strptime(_fx["date"], "%Y-%m-%d")
                        _md_rows.append({
                            "Date": f"{_dt.strftime('%a %d %b %Y')} {_fx['time']}",
                            "HB": badge_lookup.get(_fx["home"], ""),
                            "Home": _fx["home"],
                            "Home Win": round(_p.get("pct_home", 0.0) * 100, 1),
                            "Draw": round(_p.get("pct_draw", 0.0) * 100, 1),
                            "Away Win": round(_p.get("pct_away", 0.0) * 100, 1),
                            "Away": _fx["away"],
                            "AB": badge_lookup.get(_fx["away"], ""),
                        })
                    st.dataframe(
                        pd.DataFrame(_md_rows),
                        column_config={
                            "HB": st.column_config.ImageColumn("", width="small"),
                            "AB": st.column_config.ImageColumn("", width="small"),
                            "Home Win": st.column_config.NumberColumn("Home Win", format="%.1f%%"),
                            "Draw": st.column_config.NumberColumn("Draw", format="%.1f%%"),
                            "Away Win": st.column_config.NumberColumn("Away Win", format="%.1f%%"),
                        },
                        use_container_width=True, hide_index=True, height=len(_md_rows) * 35 + 38,
                    )
            elif _real_schedule_ready:
                st.caption(
                    "The real League Phase opponent list, with each match's outcome probability. "
                    "UEFA doesn't publish matchday-by-matchday order/dates alongside the opponent "
                    "list itself, so these aren't grouped or dated — home/away legs are real, though."
                )
                _fx_probs = single_match_outcome_probs(_real_schedule, _field_ratings_df, home_advantage=1.05)
                _fx_rows = [{
                    "HB": badge_lookup.get(_fx["strHomeTeam"], ""),
                    "Home": _fx["strHomeTeam"],
                    "Home Win": round(_fx["pct_home"] * 100, 1),
                    "Draw": round(_fx["pct_draw"] * 100, 1),
                    "Away Win": round(_fx["pct_away"] * 100, 1),
                    "Away": _fx["strAwayTeam"],
                    "AB": badge_lookup.get(_fx["strAwayTeam"], ""),
                } for _fx in sorted(_fx_probs, key=lambda f: f["strHomeTeam"])]
                st.dataframe(
                    pd.DataFrame(_fx_rows),
                    column_config={
                        "HB": st.column_config.ImageColumn("", width="small"),
                        "AB": st.column_config.ImageColumn("", width="small"),
                        "Home Win": st.column_config.NumberColumn("Home Win", format="%.1f%%"),
                        "Draw": st.column_config.NumberColumn("Draw", format="%.1f%%"),
                        "Away Win": st.column_config.NumberColumn("Away Win", format="%.1f%%"),
                    },
                    use_container_width=True, hide_index=True, height=len(_fx_rows) * 35 + 38,
                )
            else:
                st.caption(
                    "UEFA's real League Phase draw hasn't been made yet. Once each club's opponent "
                    "list is entered, the real fixture list (with outcome probabilities) goes here "
                    "and the predictions above switch to using it."
                )

            # ── Fixture Difficulty ────────────────────────────────────────
            st.markdown("#### Fixture Difficulty")
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
                    use_container_width=True, hide_index=True, height=len(_diff_df) * 35 + 38,
                )
            else:
                st.caption(
                    "Will rank each club's 8 (or 6, for the Conference League) League Phase opponents "
                    "by average Opta power rating once the real draw is known."
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
        "in as a Third Qualifying Round *loser*), with its probability. Once both "
        "sides of a Play-off tie are confirmed, the percentages switch to that tie's "
        "own advance odds — updated with the real leg 1 result once it's played."
    )
    bracket = PLAYOFF_BRACKET.get(comp_name, [])
    if not bracket:
        st.info("No Play-off bracket data available for this competition.")
    else:
        po_cards = []
        for side_a, side_b in bracket:
            ra = _resolve_bracket_side(side_a, ratings_df)
            rb = _resolve_bracket_side(side_b, ratings_df)

            tie_odds = None
            if ra["status"] == "confirmed" and rb["status"] == "confirmed" and ra["label"] and rb["label"]:
                tie_odds = _resolve_playoff_tie_odds(ra["label"], rb["label"], comp_name, ratings_df)

            if tie_odds:
                inner_html = _playoff_tie_odds_html(tie_odds, badge_lookup)
            else:
                html_a = _proj_side_html(ra, badge_lookup, winner=False)
                html_b = _proj_side_html(rb, badge_lookup, winner=False)
                inner_html = (f"{html_a}"
                              f"<div style='text-align:center;color:#888;font-size:11px;margin:3px 0'>vs</div>"
                              f"{html_b}")

            po_cards.append(f"""
<div style="border:1px solid #dee2e6;border-radius:8px;padding:8px 10px;
            margin:0 8px 8px 0;background:#fff;width:230px;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  {inner_html}
</div>""")
        st.markdown(f"<div style='display:flex;flex-wrap:wrap'>{''.join(po_cards)}</div>",
                    unsafe_allow_html=True)

