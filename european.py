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

from config import EUROPEAN_COMPETITIONS, LEAGUES, get_current_season
from data_fetcher import SportsDBClient
from simulator import fixture_odds
from entrants_2026_27 import ENTRANTS as ENTRANTS_2026_27, STAGE_ORDER, QUALIFYING_DATES
from club_coefficients import get_coeff, get_tiebreak


# Country name (as used in entrants_2026_27.py) → LEAGUES key
_UCL_QR1_COUNTRY_TO_LEAGUE: dict[str, str] = {
    "Slovenia":      "Slovenian 1. SNL",
    "Moldova":       "Moldovan National Division",
    "Ireland":       "Irish Premier Division",
    "Kosovo":        "Kosovan Superleague",
    "Gibraltar":     "Gibraltar National League",
    "Bosnia-Herz.":  "Bosnian Premier Liga",
    "N. Ireland":    "Northern Irish Premiership",
    "Wales":         "Welsh Premier League",
    "Malta":         "Maltese Premier League",
    "Andorra":       "Andorran Primera Divisió",
    "Bulgaria":      "Bulgarian First League",
    "Armenia":       "Armenian Premier League",
    "Albania":       "Albanian Superliga",
    "Luxembourg":    "Luxembourgish National Div",
    "Azerbaijan":    "Azerbaijani Premier League",
    "Montenegro":    "Montenegrin First League",
    "Romania":       "Romanian Liga I",
    "N. Macedonia":  "Macedonian First League",
    "San Marino":    "San Marino Campionato",
    "Ukraine":       "Ukrainian Premier League",
    "Hungary":       "Hungarian NB I",
    "Slovakia":      "Slovak First League",
}


# League IDs for all QR1-participating countries (winter + summer leagues)
_UCL_QR1_COUNTRY_TO_LEAGUE_ID: dict[str, int] = {
    "Slovenia":      4692, "Moldova":       4655, "Ireland":       4643,
    "Kosovo":        4968, "Gibraltar":     4964, "Bosnia-Herz.":  4624,
    "N. Ireland":    4659, "Wales":         4472, "Malta":         4653,
    "Andorra":       4618, "Bulgaria":      4626, "Armenia":       4619,
    "Albania":       4617, "Luxembourg":    4694, "Azerbaijan":    4693,
    "Montenegro":    4656, "Romania":       4691, "N. Macedonia":  4652,
    "San Marino":    4667, "Latvia":        4650, "Estonia":       4634,
    "Lithuania":     4651, "Iceland":       4642, "Faroe Islands": 4635,
    "Finland":       4636, "Kazakhstan":    4649, "Belarus":       4622,
    "Georgia":       4638,
    # QR2 Champions Path direct entries
    "Hungary":       4690,
    "Denmark":       4340,
    "Croatia":       4629,
    "Serbia":        4671,
    "Slovakia":      4672,
    "Poland":        4422,
    "Cyprus":        4630,
    "Israel":        4644,
    "Switzerland":   4675,
    "Sweden":        4347,
    # QR2 League Path direct entries
    "Greece":        4336,
    "Austria":       4621,
    "Scotland":      4330,
    # QR3 League Path direct entries
    "Netherlands":   4337,
    "Belgium":       4338,
    "Norway":        4358,
    "Turkey":        4339,
    "Czech Rep.":    4631,
    "France":        4334,
    "Portugal":      4344,
}


@st.cache_data(ttl=3_600, show_spinner=False)
def _load_qr1_opta_lookup() -> dict[str, dict]:
    """Load Opta ratings for all QR1 countries from ratings CSVs.
    Returns {country: {"ratings": {normalized_name: float}, "max": float}}.
    """
    import unicodedata, pandas as pd
    from pathlib import Path

    def _norm(s: str) -> str:
        return unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower().strip()

    result: dict[str, dict] = {}
    for country, lid in _UCL_QR1_COUNTRY_TO_LEAGUE_ID.items():
        csv_path = Path(f"ratings/{lid}.csv")
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path)
        df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
        df = df.dropna(subset=["opta_rating"])
        if df.empty:
            continue
        lookup: dict[str, float] = {}
        for _, row in df.iterrows():
            r = float(row["opta_rating"])
            lookup[_norm(row["team"])] = r
            alias = str(row.get("alias", "")).strip()
            if alias and alias.lower() != "nan":
                lookup[_norm(alias)] = r
        result[country] = {"ratings": lookup, "max": float(df["opta_rating"].max())}
    return result


# Extra league IDs for League Phase clubs not in the qualifying mapping
_BADGE_EXTRA_IDS = [4328, 4335, 4331, 4332]  # Premier League, La Liga, Bundesliga, Serie A


@st.cache_data(ttl=86_400, show_spinner=False)
def _load_qual_badge_lookup(api_key: str) -> dict[str, str]:
    """Build {normalised_name: badge_url} from standings across all qualifying + major leagues."""
    import unicodedata
    from config import LEAGUES, get_current_season

    def _norm(s: str) -> str:
        return unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower().strip()

    client    = SportsDBClient(api_key)
    id_to_cfg = {cfg["id"]: (name, cfg) for name, cfg in LEAGUES.items()}
    all_ids   = set(_UCL_QR1_COUNTRY_TO_LEAGUE_ID.values()) | set(_BADGE_EXTRA_IDS)

    result: dict[str, str] = {}
    for lid in all_ids:
        entry = id_to_cfg.get(lid)
        if not entry:
            continue
        _, lcfg = entry
        season = get_current_season(lcfg["season_type"])
        try:
            rows = client.get_standings(lid, season)
        except Exception:
            continue
        for row in rows:
            badge = row.get("strBadge") or row.get("strTeamBadge") or ""
            name  = row.get("strTeam") or row.get("strTeamName") or ""
            if badge and name:
                result[_norm(name)] = badge
    return result


def _get_qr1_opta(club: str | None, country: str, lookup: dict) -> float:
    """Return Opta rating for a QR1 club. Falls back to league champion (max) if not found."""
    import unicodedata

    def _norm(s: str) -> str:
        return unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower().strip()

    data = lookup.get(country, {})
    if not data:
        return 75.0
    ratings = data["ratings"]
    max_r   = data["max"]
    if not club:
        return max_r
    cn = _norm(club)
    if cn in ratings:
        return ratings[cn]
    # Partial match
    for key, val in ratings.items():
        if cn in key or key in cn:
            return val
    return max_r


@st.cache_data(ttl=3_600, show_spinner=False)
def _simulate_ucl_qr1(entries_key: tuple, n_sim: int = 10_000) -> tuple:
    """Simulate UCL QR1 draw + two-legged ties.

    entries_key: tuple of (display_name, flag, coeff) sorted by coeff desc.
    Top half = seeded, bottom half = unseeded.
    Returns tuple of (display_name, flag, coeff, seeded_bool, advance_pct) sorted by pct desc.
    """
    import numpy as np
    from config import DEFAULT_HOME_ADVANTAGE, DEFAULT_BASE_GOALS

    all_e   = list(entries_key)
    n_total = len(all_e)
    n       = n_total // 2           # 14 seeded, 14 unseeded

    coeffs  = np.array([e[2] for e in all_e], dtype=float)
    mean_c  = coeffs.mean()
    base    = DEFAULT_BASE_GOALS
    k       = 2.0
    home_adv = DEFAULT_HOME_ADVANTAGE

    rels     = coeffs / mean_c
    attacks  = base * rels ** k
    defenses = base * rels ** (-k)
    league_avg = attacks.mean()

    s_atk = attacks[:n];   s_def = defenses[:n]
    u_atk = attacks[n:];   u_def = defenses[n:]

    advance_s = np.zeros(n, dtype=np.int32)
    advance_u = np.zeros(n, dtype=np.int32)

    rng = np.random.default_rng(42)

    # Vectorised: for each seeded slot i, draw its opponent for all sims at once.
    perms = np.array([rng.permutation(n) for _ in range(n_sim)])  # (n_sim, n)

    for i in range(n):
        j_arr = perms[:, i]                                   # (n_sim,) unseeded index per sim

        lam_s1 = s_atk[i] * u_def[j_arr] / league_avg * home_adv  # seeded home, leg 1
        lam_u1 = u_atk[j_arr] * s_def[i] / league_avg              # unseeded away, leg 1
        lam_s2 = s_atk[i] * u_def[j_arr] / league_avg              # seeded away, leg 2
        lam_u2 = u_atk[j_arr] * s_def[i] / league_avg * home_adv  # unseeded home, leg 2

        s_g = rng.poisson(lam_s1) + rng.poisson(lam_s2)
        u_g = rng.poisson(lam_u1) + rng.poisson(lam_u2)

        s_win = (s_g > u_g).astype(np.int32)
        u_win = (u_g > s_g).astype(np.int32)
        tie   = (s_g == u_g)
        pen_s = rng.integers(0, 2, size=n_sim, dtype=np.int32)   # 0 or 1, 50/50
        s_win += tie * pen_s
        u_win += tie * (1 - pen_s)

        advance_s[i] += s_win.sum()
        np.add.at(advance_u, j_arr, u_win)

    pcts = np.concatenate([advance_s, advance_u]) / n_sim

    results = []
    for idx, (name, flag, coeff) in enumerate(all_e):
        results.append((name, flag, coeff, idx < n, float(pcts[idx])))

    results.sort(key=lambda x: x[4], reverse=True)
    return tuple(results)


@st.cache_data(ttl=3_600, show_spinner=False)
def _fetch_ucl_qr1_projections(api_key: str) -> dict[str, str]:
    """Return {country: projected_champion} for winter UCL QR1 leagues."""
    client = SportsDBClient(api_key)
    result = {}
    for country, league_name in _UCL_QR1_COUNTRY_TO_LEAGUE.items():
        lcfg = LEAGUES.get(league_name)
        if not lcfg:
            continue
        ssn = get_current_season(lcfg["season_type"])
        standings = client.get_standings(lcfg["id"], ssn)
        if standings:
            leader = min(standings, key=lambda r: int(r.get("intRank") or 99))
            result[country] = leader.get("strTeam")
    return result


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


def _resolve_dynamic(entries: list[dict], albania_top4: list[str],
                     ucl_qr1_proj: dict = None) -> list[dict]:
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
        elif (ucl_qr1_proj and e.get("status") == "tbd"
              and e.get("route", "") == "League 1st"
              and e.get("country") in ucl_qr1_proj):
            club = ucl_qr1_proj[e["country"]]
            out.append({**e, "club": club, "status": "projected" if club else "tbd"})
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
                          "Third Qualifying Round", "Play-off Round", "League Phase"]
        _STATUS_BG = {
            "confirmed":   "#d4edda",
            "provisional": "#fff3cd",
            "projected":   "#cce5ff",
            "tbd":         "#f8f9fa",
        }
        _STATUS_LABEL = {
            "confirmed":   "✅ Confirmed",
            "provisional": "⏳ Provisional",
            "projected":   "🔮 Projected",
            "tbd":         "— TBD",
        }
        _albania_top4   = _fetch_albania_top4(_API_KEY)
        _ucl_qr1_proj   = _fetch_ucl_qr1_projections(_API_KEY) if comp_name == "Champions League" else {}
        _badge_lu       = _load_qual_badge_lookup(_API_KEY)
        st.caption(
            "🟢 Confirmed — domestic season complete  "
            "🟡 Provisional — season still running  "
            "🔮 Projected — based on current standings  "
            "⬜ TBD — club not yet determined  ·  "
            "Draws and individual matchups not yet made"
        )
        _COUNTRY_CODE: dict[str, str] = {
            "England": "ENG", "Scotland": "SCO", "Wales": "WAL", "N. Ireland": "NIR",
            "Germany": "GER", "Spain": "ESP", "Italy": "ITA", "France": "FRA",
            "Netherlands": "NED", "Portugal": "POR", "Belgium": "BEL",
            "Czech Rep.": "CZE", "Czechia": "CZE", "Turkey": "TUR", "Türkiye": "TUR",
            "Greece": "GRE", "Norway": "NOR", "Austria": "AUT", "Switzerland": "SUI",
            "Denmark": "DEN", "Poland": "POL", "Croatia": "CRO", "Serbia": "SRB",
            "Slovakia": "SVK", "Cyprus": "CYP", "Israel": "ISR", "Sweden": "SWE",
            "Hungary": "HUN", "Romania": "ROU", "Slovenia": "SVN", "Bulgaria": "BUL",
            "Latvia": "LAT", "Faroe Islands": "FRO", "Faroe Isl.": "FRO",
            "Estonia": "EST", "Lithuania": "LTU", "Iceland": "ISL", "Ireland": "IRL",
            "Finland": "FIN", "Kazakhstan": "KAZ", "Belarus": "BLR", "Georgia": "GEO",
            "Kosovo": "XKX", "Malta": "MLT", "Albania": "ALB", "Montenegro": "MNE",
            "Luxembourg": "LUX", "N. Macedonia": "MKD", "Andorra": "AND",
            "Gibraltar": "GIB", "San Marino": "SMR", "Moldova": "MDA",
            "Armenia": "ARM", "Azerbaijan": "AZE", "Bosnia-Herz.": "BIH",
            "Ukraine": "UKR", "Russia": "RUS", "Ukraine": "UKR",
        }
        _STATUS_ICON = {
            "confirmed":   "✅",
            "provisional": "⏳",
            "projected":   "🔮",
            "tbd":         "—",
        }

        def _short_route(route: str) -> str:
            """'League 3rd' → '3rd', 'Cup winner' → 'Cup', 'EPS' → 'EPS', etc."""
            r = route.strip()
            if r.lower().startswith("league "):
                return r[7:]          # '1st', '2nd', …
            if r.lower().startswith("cup"):
                return "Cup"
            if r.lower().startswith("final four"):
                return "FF"
            if r.upper() == "EPS":
                return "EPS"
            # Generic: take first word
            return r.split()[0] if r else r

        import unicodedata as _ud
        def _bn(s: str) -> str:
            return _ud.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower().strip()

        def _entry_table_html(clubs, header_label):
            """Build a compact HTML table for a list of entrant clubs."""
            rows = ""
            for i, e in enumerate(clubs, 1):
                bg          = _STATUS_BG.get(e["status"], "#f8f9fa")
                raw_name    = e["club"]
                country     = e.get("country", "")
                ctry_code   = _COUNTRY_CODE.get(country, country[:3].upper())
                route_s     = _short_route(e.get("route", ""))
                coeff       = get_coeff(raw_name, country) if raw_name else None
                coeff_str   = f"{coeff:.3f}" if coeff else "—"
                status_icon = _STATUS_ICON.get(e["status"], "")
                badge_url   = _badge_lu.get(_bn(raw_name or ""), "") if raw_name else ""
                logo_html   = (f"<img src='{badge_url}' style='width:16px;height:16px;"
                               f"object-fit:contain;vertical-align:middle;margin-right:3px'>"
                               if badge_url else
                               "<span style='display:inline-block;width:16px'></span>")
                if raw_name:
                    club_cell = (f"{logo_html}{raw_name} "
                                 f"<span style='color:#6c757d;font-size:10px;font-weight:normal'>{ctry_code}</span>")
                else:
                    club_cell = f"<span style='color:#666;font-style:italic'>{e.get('route','TBD')}</span>"
                rows += (
                    f"<tr style='background:{bg}'>"
                    f"<td style='padding:1px 3px;color:#555;font-size:10px;text-align:right;width:14px'>{i}</td>"
                    f"<td style='padding:1px 3px;font-size:13px;width:18px'>{e['flag']}</td>"
                    f"<td style='padding:1px 3px;font-weight:bold;color:#212529;font-size:12px'>{club_cell}</td>"
                    f"<td style='padding:1px 3px;color:#999;font-size:10px;white-space:nowrap;text-align:center'>{route_s}</td>"
                    f"<td style='padding:1px 3px;color:#856404;font-size:10px;font-weight:600;text-align:right;white-space:nowrap'>{coeff_str}</td>"
                    f"<td style='padding:1px 3px;font-size:10px;text-align:center'>{status_icon}</td>"
                    f"</tr>"
                )
            return (
                f"<table style='width:auto;border-collapse:collapse;font-family:sans-serif'>"
                f"<thead><tr style='background:#e9ecef'>"
                f"<th style='padding:1px 3px;color:#555;text-align:right;font-size:9px'>#</th>"
                f"<th style='padding:1px 3px;color:#888;text-align:left'></th>"
                f"<th style='padding:1px 3px;color:#888;text-align:left;font-size:10px'>{header_label}</th>"
                f"<th style='padding:1px 3px;color:#888;text-align:center;font-size:9px'>Pos</th>"
                f"<th style='padding:1px 3px;color:#888;text-align:right;font-size:9px'>Coeff.</th>"
                f"<th style='padding:1px 3px;color:#888;text-align:center;font-size:9px'></th>"
                f"</tr></thead><tbody>{rows}</tbody></table>"
            )

        # Projected winners carried forward between rounds
        _qr1_cp_projected: list[dict] = []
        _qr2_lp_projected: list[dict] = []

        def _pred_table_html(club_list, header_label, pct_lookup, advancing_names):
            """Compact advance-probability table for qualifying predictions."""
            _SIM_BG = {"adv": "#d4edda", "elim": "#f8d7da"}
            rows = ""
            for i, e in enumerate(club_list, 1):
                raw_name = e.get("club")
                name     = raw_name or f"{e.get('country','?')} (TBD)"
                country  = e.get("country", "")
                flag     = e["flag"]
                pct      = pct_lookup.get(name, 0.0)
                advance  = name in advancing_names
                bg       = _SIM_BG["adv"] if advance else _SIM_BG["elim"]
                icon     = "✅" if advance else "❌"
                pct_s    = f"{pct * 100:.1f}%"
                pct_col  = "#155724" if advance else "#842029"
                ctry_code = _COUNTRY_CODE.get(country, country[:3].upper()) if country else ""
                badge_url = _badge_lu.get(_bn(raw_name or ""), "") if raw_name else ""
                logo_html = (f"<img src='{badge_url}' style='width:15px;height:15px;"
                             f"object-fit:contain;vertical-align:middle;margin-right:3px'>"
                             if badge_url else
                             "<span style='display:inline-block;width:15px'></span>")
                name_cell = (f"{logo_html}{name} "
                             f"<span style='color:#6c757d;font-size:10px;font-weight:normal'>{ctry_code}</span>"
                             if raw_name else name)
                rows += (
                    f"<tr style='background:{bg}'>"
                    f"<td style='padding:1px 3px;color:#555;font-size:10px;text-align:right;width:14px'>{i}</td>"
                    f"<td style='padding:1px 3px;font-size:13px;width:18px'>{flag}</td>"
                    f"<td style='padding:1px 3px;font-weight:bold;color:#212529;font-size:12px'>{name_cell}</td>"
                    f"<td style='padding:1px 4px;color:{pct_col};font-weight:600;"
                    f"font-size:11px;text-align:right;white-space:nowrap'>{pct_s}</td>"
                    f"<td style='padding:1px 3px;font-size:12px;text-align:center;width:20px'>{icon}</td>"
                    f"</tr>"
                )
            return (
                "<table style='width:auto;border-collapse:collapse;font-family:sans-serif'>"
                "<thead><tr style='background:#e9ecef'>"
                "<th style='padding:1px 3px;color:#555;text-align:right;font-size:9px'>#</th>"
                "<th></th>"
                f"<th style='padding:1px 3px;color:#888;text-align:left;font-size:10px'>{header_label}</th>"
                "<th style='padding:1px 4px;color:#888;text-align:right;font-size:9px'>Advance%</th>"
                "<th></th>"
                f"</tr></thead><tbody>{rows}</tbody></table>"
            )

        def _run_predictions(confirmed_clubs, stage_label):
            """Run simulation, render two-column predictions, return list of projected winners."""
            _opta_lu = _load_qr1_opta_lookup()
            _entries = []
            for e in confirmed_clubs:
                club    = e.get("club")
                country = e.get("country", "")
                flag    = e.get("flag", "🏳")
                opta    = _get_qr1_opta(club, country, _opta_lu)
                name    = club if club else f"{country} (TBD)"
                _entries.append((name, flag, opta))
            _entries.sort(key=lambda x: x[2], reverse=True)
            if len(_entries) < 4:
                return []
            st.markdown("#### 🎯 Predictions (10,000 simulations)")
            _sim_out      = _simulate_ucl_qr1(tuple(_entries))
            _pct          = {nm: p for nm, fl, op, sd, p in _sim_out}
            n_advance     = len(confirmed_clubs) // 2
            _sorted_pct   = sorted(_pct.items(), key=lambda x: x[1], reverse=True)
            advancing_names = {nm for nm, _ in _sorted_pct[:n_advance]}
            _mid          = (len(confirmed_clubs) + 1) // 2
            _col_l, _col_r = st.columns(2)
            with _col_l:
                st.markdown(_pred_table_html(confirmed_clubs[:_mid], "🥇 Seeded", _pct, advancing_names), unsafe_allow_html=True)
            with _col_r:
                st.markdown(_pred_table_html(confirmed_clubs[_mid:], "Unseeded", _pct, advancing_names), unsafe_allow_html=True)
            st.caption("✅ Projected to advance · ❌ Projected to be eliminated")
            # Return projected winners (top n_advance by advance%) as entry dicts
            _name_to_e = {
                (e.get("club") or f"{e.get('country','?')} (TBD)"): e
                for e in confirmed_clubs
            }
            return [
                {
                    "club":    _name_to_e.get(nm, {}).get("club"),
                    "country": _name_to_e.get(nm, {}).get("country", ""),
                    "flag":    _name_to_e.get(nm, {}).get("flag", "🏳"),
                    "route":   f"{stage_label} winner",
                    "status":  "projected",
                }
                for nm, _ in _sorted_pct[:n_advance]
            ]

        for stage in _QUAL_STAGES:
            if stage not in _comp_entrants:
                continue
            dates = _comp_dates.get(stage, {})
            leg1  = dates.get("leg1", "TBD")
            leg2  = dates.get("leg2")
            if stage == "League Phase":
                date_str = f"Starts: **{leg1}**"
            elif leg2:
                date_str = f"1st leg: **{leg1}** &nbsp;·&nbsp; 2nd leg: **{leg2}**"
            else:
                date_str = f"1st leg: **{leg1}**"
            st.markdown(f"### {stage}")
            st.markdown(date_str, unsafe_allow_html=True)
            paths = _comp_entrants[stage]
            for path_label, clubs in paths.items():
                resolved = _resolve_dynamic(clubs, _albania_top4, _ucl_qr1_proj)
                # Expand projected winners from previous rounds into current field
                if (stage == "Second Qualifying Round" and path_label == "Champions Path"
                        and comp_name == "Champions League" and _qr1_cp_projected):
                    resolved = [
                        e for e in resolved
                        if e.get("route") != "QR1 Champions Path winners"
                    ] + _qr1_cp_projected
                elif (stage == "Third Qualifying Round" and path_label == "League Path"
                        and comp_name == "Champions League" and _qr2_lp_projected):
                    resolved = [
                        e for e in resolved
                        if e.get("route") != "QR2 League Path winners"
                    ] + _qr2_lp_projected
                if len(paths) > 1:
                    st.markdown(f"*{path_label}*")
                confirmed_clubs = [e for e in resolved if e["status"] != "tbd"]
                tbd_clubs       = [e for e in resolved if e["status"] == "tbd"]
                # Sort by coefficient desc, then 25/26 pts desc, then 24/25 pts desc
                confirmed_clubs.sort(
                    key=lambda e: (
                        get_coeff(e.get("club"), e.get("country", "")),
                        *get_tiebreak(e.get("club")),
                    ),
                    reverse=True
                )
                # League Phase: four pots of 9 ranked by coefficient
                if stage == "League Phase" and confirmed_clubs:
                    def _pot_table_html(clubs, header):
                        rows = ""
                        for i, e in enumerate(clubs, 1):
                            bg        = _STATUS_BG.get(e["status"], "#f8f9fa")
                            raw_name  = e["club"]
                            country   = e.get("country", "")
                            ctry_code = _COUNTRY_CODE.get(country, country[:3].upper()) if country else ""
                            coeff     = get_coeff(raw_name, country) if raw_name else None
                            coeff_str = f"{coeff:.3f}" if coeff else "—"
                            badge_url = _badge_lu.get(_bn(raw_name or ""), "") if raw_name else ""
                            logo_html = (f"<img src='{badge_url}' style='width:16px;height:16px;"
                                         f"object-fit:contain;vertical-align:middle;margin-right:3px'>"
                                         if badge_url else
                                         "<span style='display:inline-block;width:16px'></span>")
                            if raw_name:
                                name_cell = (f"{logo_html}{raw_name} "
                                             f"<span style='color:#6c757d;font-size:9px;font-weight:normal'>{ctry_code}</span>")
                            else:
                                name_cell = f"<span style='color:#666;font-style:italic'>{e.get('route','TBD')}</span>"
                            rows += (
                                f"<tr style='background:{bg}'>"
                                f"<td style='padding:1px 2px;color:#555;font-size:10px;text-align:right;width:12px'>{i}</td>"
                                f"<td style='padding:1px 2px;font-size:12px;width:16px'>{e['flag']}</td>"
                                f"<td style='padding:1px 2px;font-weight:bold;color:#212529;font-size:11px'>{name_cell}</td>"
                                f"<td style='padding:1px 3px;color:#856404;font-size:10px;font-weight:600;"
                                f"text-align:right;white-space:nowrap'>{coeff_str}</td>"
                                f"</tr>"
                            )
                        return (
                            f"<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                            f"<thead><tr style='background:#e9ecef'>"
                            f"<th style='padding:1px 2px;color:#555;text-align:right;font-size:9px'>#</th>"
                            f"<th></th>"
                            f"<th style='padding:1px 2px;color:#888;text-align:left;font-size:10px'>{header}</th>"
                            f"<th style='padding:1px 3px;color:#888;text-align:right;font-size:9px'>Coeff.</th>"
                            f"</tr></thead><tbody>{rows}</tbody></table>"
                        )
                    _pot_cols = st.columns(4)
                    for _pi, _pcol in enumerate(_pot_cols, 1):
                        _pot_clubs = confirmed_clubs[(_pi - 1) * 9 : _pi * 9]
                        with _pcol:
                            st.markdown(_pot_table_html(_pot_clubs, f"🏆 Pot {_pi}"), unsafe_allow_html=True)

                # All other stages: seeded / unseeded halves when large enough
                elif stage != "League Phase" and confirmed_clubs:
                    if len(confirmed_clubs) >= 4:
                        mid      = (len(confirmed_clubs) + 1) // 2
                        seeded   = confirmed_clubs[:mid]
                        unseeded = confirmed_clubs[mid:]
                        col_l, col_r = st.columns(2)
                        with col_l:
                            st.markdown(_entry_table_html(seeded, "🥇 Seeded"), unsafe_allow_html=True)
                        with col_r:
                            st.markdown(_entry_table_html(unseeded, "Unseeded"), unsafe_allow_html=True)
                    else:
                        st.markdown(_entry_table_html(confirmed_clubs, "Club"), unsafe_allow_html=True)
                # TBD slots — compact text list
                if tbd_clubs:
                    tbd_items = " · ".join(
                        f"{e['flag']} {e['country']} ({e['route']})" for e in tbd_clubs
                    )
                    st.markdown(
                        f"<div style='background:#f8f9fa;border-left:3px solid #adb5bd;"
                        f"padding:8px 12px;border-radius:4px;color:#495057;"
                        f"font-size:12px;margin-bottom:10px'>"
                        f"<b style='color:#495057'>TBD slots:</b> {tbd_items}</div>",
                        unsafe_allow_html=True,
                    )

                # ── Inline predictions for UCL QR1 Champions Path ────────────
                if (stage == "First Qualifying Round" and path_label == "Champions Path"
                        and comp_name == "Champions League"):
                    _opta_lu     = _load_qr1_opta_lookup()
                    _qr1_entries = []
                    _name_to_entry: dict[str, dict] = {}
                    for e in resolved:
                        club    = e.get("club")
                        country = e.get("country", "")
                        flag    = e.get("flag", "🏳")
                        opta    = _get_qr1_opta(club, country, _opta_lu)
                        name    = club if club else f"{country} (TBD)"
                        _qr1_entries.append((name, flag, opta))
                        _name_to_entry[name] = e
                    _qr1_entries.sort(key=lambda x: x[2], reverse=True)

                    if len(_qr1_entries) >= 4:
                        _qr1_sim      = _simulate_ucl_qr1(tuple(_qr1_entries))
                        _qr1_pct      = {nm: p for nm, fl, op, sd, p in _qr1_sim}
                        n_adv         = len(_qr1_entries) // 2
                        _qr1_sorted   = sorted(_qr1_pct.items(), key=lambda x: x[1], reverse=True)
                        _qr1_advancing = {nm for nm, _ in _qr1_sorted[:n_adv]}
                        # Store top-n_adv as projected QR2 entrants
                        _qr1_cp_projected = []
                        for nm, _ in _qr1_sorted[:n_adv]:
                            _orig = _name_to_entry.get(nm, {})
                            _qr1_cp_projected.append({
                                "club":    _orig.get("club"),
                                "country": _orig.get("country", ""),
                                "flag":    _orig.get("flag", "🏳"),
                                "route":   "QR1 winner",
                                "status":  "projected",
                            })
                        # Display predictions (confirmed clubs in coefficient order)
                        st.markdown("#### 🎯 Predictions (10,000 simulations)")
                        _p_mid = (len(confirmed_clubs) + 1) // 2
                        _pc_l, _pc_r = st.columns(2)
                        with _pc_l:
                            st.markdown(_pred_table_html(confirmed_clubs[:_p_mid], "🥇 Seeded", _qr1_pct, _qr1_advancing), unsafe_allow_html=True)
                        with _pc_r:
                            st.markdown(_pred_table_html(confirmed_clubs[_p_mid:], "Unseeded", _qr1_pct, _qr1_advancing), unsafe_allow_html=True)
                        st.caption("✅ Projected to advance · ❌ Projected to be eliminated")

                # ── Inline predictions for UCL QR2 Champions Path ─────────────
                elif (stage == "Second Qualifying Round" and path_label == "Champions Path"
                        and comp_name == "Champions League"):
                    _run_predictions(confirmed_clubs, "QR2 Champions Path")

                # ── Inline predictions for UCL QR2 League Path ────────────────
                elif (stage == "Second Qualifying Round" and path_label == "League Path"
                        and comp_name == "Champions League"):
                    _qr2_lp_projected = _run_predictions(confirmed_clubs, "QR2 League Path")

                # ── Inline predictions for UCL QR3 League Path ────────────────
                elif (stage == "Third Qualifying Round" and path_label == "League Path"
                        and comp_name == "Champions League"):
                    _run_predictions(confirmed_clubs, "QR3 League Path")

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
                "🔮 Projected — based on current standings  "
                "⬜ TBD — club not yet determined"
            )

            _STATUS_BG = {
                "confirmed":   "#d4edda",
                "provisional": "#fff3cd",
                "projected":   "#cce5ff",
                "tbd":         "#f8f9fa",
            }
            _STATUS_LABEL = {
                "confirmed":   "✅ Confirmed",
                "provisional": "⏳ Provisional",
                "projected":   "🔮 Projected",
                "tbd":         "— TBD",
            }

            # Resolve projections (Albania Final Four + UCL QR1 winter leaders)
            _ent_albania_top4  = _fetch_albania_top4(_API_KEY)
            _ent_ucl_qr1_proj  = _fetch_ucl_qr1_projections(_API_KEY) if comp_name == "Champions League" else {}
            _badge_lu          = _load_qual_badge_lookup(_API_KEY)  # cached — essentially free

            # Iterate stages in chronological order
            for stage in STAGE_ORDER:
                if stage not in comp_entrants:
                    continue
                paths = comp_entrants[stage]
                with st.expander(f"**{stage}**", expanded=(stage == "League Phase")):
                    for path_label, clubs in paths.items():
                        if len(paths) > 1:
                            st.markdown(f"*{path_label}*")
                        clubs = _resolve_dynamic(clubs, _ent_albania_top4, _ent_ucl_qr1_proj)
                        # Sort known clubs by coefficient desc; TBD slots at the end
                        known  = [e for e in clubs if e.get("club")]
                        tbds   = [e for e in clubs if not e.get("club")]
                        known.sort(
                            key=lambda e: (
                                get_coeff(e["club"], e.get("country", "")),
                                *get_tiebreak(e["club"]),
                            ),
                            reverse=True
                        )
                        # Split into seeded / unseeded halves when large enough
                        if len(known) >= 4:
                            mid      = (len(known) + 1) // 2
                            seeded   = known[:mid]
                            unseeded = known[mid:]
                            col_l, col_r = st.columns(2)
                            with col_l:
                                st.markdown(_entry_table_html(seeded, "🥇 Seeded"), unsafe_allow_html=True)
                            with col_r:
                                st.markdown(_entry_table_html(unseeded, "Unseeded"), unsafe_allow_html=True)
                        elif known:
                            st.markdown(_entry_table_html(known, "Club"), unsafe_allow_html=True)
                        if tbds:
                            tbd_items = " · ".join(
                                f"{e['flag']} {e.get('country','')} ({e['route']})" for e in tbds
                            )
                            st.markdown(
                                f"<div style='background:#f8f9fa;border-left:3px solid #adb5bd;"
                                f"padding:8px 12px;border-radius:4px;color:#495057;"
                                f"font-size:12px;margin-bottom:6px'>"
                                f"<b style='color:#495057'>TBD slots:</b> {tbd_items}</div>",
                                unsafe_allow_html=True,
                            )
                        st.markdown("")

if False:
    with tab_qual:  # placeholder — QR1 predictions rendered inline inside tab_qual above
        st.markdown("### First Qualifying Round — Predictions")
        st.caption(
            "10,000 Monte Carlo simulations of the QR1 draw and two-legged ties. "
            "Strength is derived from UEFA coefficients using the same Poisson model "
            "as league projections. Seeded clubs host leg 1; unseeded host leg 2. "
            "Ties on aggregate go to 50/50 penalties."
        )

        # Resolve all 28 QR1 entries (same logic as Qualifying tab)
        _qr1_raw      = ENTRANTS_2026_27.get("Champions League", {}).get("First Qualifying Round", {}).get("Champions Path", [])
        _qr1_al4      = _fetch_albania_top4(_API_KEY)
        _qr1_proj     = _fetch_ucl_qr1_projections(_API_KEY)
        _qr1_resolved = _resolve_dynamic(_qr1_raw, _qr1_al4, _qr1_proj)

        # Build (display_name, flag, coeff) for each entry; TBDs use nation coefficient
        _qr1_entries = []
        for e in _qr1_resolved:
            club    = e.get("club")
            country = e.get("country", "")
            flag    = e.get("flag", "🏳")
            coeff   = get_coeff(club, country) if club else get_coeff(None, country)
            name    = club if club else f"{country} (TBD)"
            _qr1_entries.append((name, flag, coeff))

        # Sort by (coeff desc, tiebreak) to replicate seeded/unseeded split
        _qr1_entries.sort(
            key=lambda x: (x[2], get_tiebreak(x[0] if "TBD" not in x[0] else None)),
            reverse=True,
        )

        if len(_qr1_entries) < 2:
            st.info("Not enough clubs resolved yet to simulate.")
        else:
            entries_key = tuple(_qr1_entries)

            with st.spinner("Running 10,000 simulations…"):
                sim_results = _simulate_ucl_qr1(entries_key)

            # ── HTML table ──────────────────────────────────────────────────
            n_advance = len(sim_results) // 2   # top half projected to advance
            _SIM_BG = {"advance": "#d4edda", "eliminate": "#f8d7da"}

            rows_html = ""
            for rank, (name, flag, coeff, is_seeded, pct) in enumerate(sim_results, 1):
                advance   = rank <= n_advance
                bg        = _SIM_BG["advance"] if advance else _SIM_BG["eliminate"]
                seed_lbl  = "<span style='color:#856404;font-size:10px'>S</span>" if is_seeded \
                            else "<span style='color:#888;font-size:10px'>U</span>"
                result_icon = "✅" if advance else "❌"
                pct_str   = f"{pct * 100:.1f}%"
                bar_w     = int(pct * 100)
                bar_html  = (
                    f"<div style='background:#dee2e6;border-radius:3px;width:80px;height:6px;display:inline-block;vertical-align:middle'>"
                    f"<div style='background:{'#4caf50' if advance else '#e53935'};width:{bar_w}%;height:100%;border-radius:3px'></div>"
                    f"</div>"
                )
                rows_html += (
                    f"<tr style='background:{bg}'>"
                    f"<td style='padding:3px 6px;color:#555;font-size:11px;text-align:right;width:18px'>{rank}</td>"
                    f"<td style='padding:3px 6px;font-size:14px;width:22px'>{flag}</td>"
                    f"<td style='padding:3px 6px;font-weight:bold;color:#212529;font-size:13px'>{name}</td>"
                    f"<td style='padding:3px 6px;text-align:center;width:20px'>{seed_lbl}</td>"
                    f"<td style='padding:3px 6px;color:{'#155724' if advance else '#842029'};font-weight:600;font-size:12px;text-align:right;width:50px'>{pct_str}</td>"
                    f"<td style='padding:3px 10px;width:100px'>{bar_html}</td>"
                    f"<td style='padding:3px 6px;font-size:13px;text-align:center;width:22px'>{result_icon}</td>"
                    f"</tr>"
                )

            table_html = (
                "<table style='width:100%;border-collapse:collapse;font-family:sans-serif'>"
                "<thead><tr style='background:#e9ecef'>"
                "<th style='padding:3px 6px;color:#555;text-align:right;font-size:10px'>#</th>"
                "<th style='padding:3px 6px'></th>"
                "<th style='padding:3px 6px;color:#888;text-align:left;font-size:11px'>Club</th>"
                "<th style='padding:3px 6px;color:#888;text-align:center;font-size:10px'>Seed</th>"
                "<th style='padding:3px 6px;color:#888;text-align:right;font-size:10px'>Advance%</th>"
                "<th style='padding:3px 6px;color:#888;font-size:10px'></th>"
                "<th style='padding:3px 6px;color:#888;text-align:center;font-size:10px'></th>"
                f"</tr></thead><tbody>{rows_html}</tbody></table>"
            )
            st.markdown(table_html, unsafe_allow_html=True)
            st.caption(
                "🟡 **S** = Seeded (top 14 by coefficient)  ·  ⬜ **U** = Unseeded  ·  "
                "✅ Projected to advance  ·  ❌ Projected to be eliminated"
            )
