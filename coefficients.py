"""
Coefficients — UEFA Country Ranking, computed by this site from live results.

22/23 through 25/26 are a frozen one-time snapshot from kassiesa.net (see
coefficients_baseline.py) — those seasons are closed and UEFA's methodology
has changed over the years, so they can't be cleanly reconstructed. The
current season (26/27) is computed live from every Champions League, Europa
League and Conference League match played so far, following UEFA's official
rules (Annex D of the Champions League regulations):

  D.3 — a country's season coefficient is the SUM of all points earned by
        all its clubs, DIVIDED BY the number of clubs it entered. Points:
        2 for a win / 1 for a draw (1 / 0.5 in qualifying and the play-off
        round). Coefficients are truncated (not rounded) to 3 decimals.
  D.5 — bonus points, also divided into the coefficient the same way:
        (a) reaching the Round of 16 / QF / SF / Final: 1.5 / 1.0 / 0.5
            points per stage in the CL / EL / ECL respectively;
        (b) final League Phase ranking: a sliding scale from 12.000 (CL) /
            6.000 (EL) / 4.000 (ECL) at rank 1 down to 6.000 / 0.000 / 0.000
            by rank 25, flat after that (exact formula in _league_phase_bonus).
  D.7 — penalty shootouts don't count for points (a shootout-decided tie
        scores as a draw).
"""

import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd

from config import LEAGUES, EUROPEAN_COMPETITIONS
from api_football_fetcher import ApiFootballClient
from coefficients_baseline import (
    COUNTRY_BASELINE, COUNTRY_NAME_FIXUP, CLUB_COUNTRY_OVERRIDE,
)
from qualifying_bracket import CONFIRMED_LEAGUE_PHASE

# D.5(b) floor — the worst possible league-phase-ranking bonus (rank 36),
# guaranteed to every club that secures a League Phase spot regardless of
# how the phase itself goes. Only non-zero for the Champions League.
_SECURED_LP_FLOOR = {"Champions League": 6.0, "Europa League": 0.0, "Conference League": 0.0}

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_CET = ZoneInfo("Europe/Berlin")
_SEASON = "2026-2027"

_FLAGS: dict[str, str] = {
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Italy": "🇮🇹", "Spain": "🇪🇸", "Germany": "🇩🇪", "France": "🇫🇷",
    "Portugal": "🇵🇹", "Belgium": "🇧🇪", "Netherlands": "🇳🇱", "Türkiye": "🇹🇷",
    "Czechia": "🇨🇿", "Poland": "🇵🇱", "Greece": "🇬🇷", "Denmark": "🇩🇰", "Norway": "🇳🇴",
    "Cyprus": "🇨🇾", "Switzerland": "🇨🇭", "Hungary": "🇭🇺", "Sweden": "🇸🇪",
    "Austria": "🇦🇹", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Croatia": "🇭🇷", "Romania": "🇷🇴",
    "Ukraine": "🇺🇦", "Israel": "🇮🇱", "Slovenia": "🇸🇮", "Azerbaijan": "🇦🇿",
    "Bulgaria": "🇧🇬", "Slovakia": "🇸🇰", "Serbia": "🇷🇸", "Russia": "🇷🇺",
    "Iceland": "🇮🇸", "Ireland": "🇮🇪", "Armenia": "🇦🇲", "Kosovo": "🇽🇰",
    "Bosnia-Herzegovina": "🇧🇦", "Latvia": "🇱🇻", "Finland": "🇫🇮", "Kazakhstan": "🇰🇿",
    "Liechtenstein": "🇱🇮", "Moldova": "🇲🇩", "Faroe Islands": "🇫🇴",
    "North Macedonia": "🇲🇰", "Albania": "🇦🇱", "Belarus": "🇧🇾", "Lithuania": "🇱🇹",
    "Malta": "🇲🇹", "Andorra": "🇦🇩", "Estonia": "🇪🇪", "Gibraltar": "🇬🇮",
    "Northern Ireland": "🇬🇧", "Georgia": "🇬🇪", "Luxembourg": "🇱🇺",
    "Montenegro": "🇲🇪", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "San Marino": "🇸🇲",
}

# Exact strRound text that counts at the halved qualifying rate (D.3).
# Everything else that's a real match round (League Stage onward, incl. the
# Round-of-16 knockout play-off round) counts at full rate.
_QUALIFYING_ROUNDS = {
    "1st Qualifying Round", "2nd Qualifying Round", "3rd Qualifying Round", "Play-offs",
}
_QUAL_POINTS = (1.0, 0.5)   # (win, draw)
_FULL_POINTS = (2.0, 1.0)

# D.5(a): bonus points per knockout stage reached, by competition.
_BONUS_PER_STAGE = {"Champions League": 1.5, "Europa League": 1.0, "Conference League": 0.5}


def _utc_to_cet(date_str: str, time_str: str) -> str:
    if not date_str or not time_str or time_str.startswith("00:00"):
        return date_str
    try:
        dt = datetime.strptime(f"{date_str} {time_str[:8]}", "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(_CET)
        return f"{dt.strftime('%H:%M')} CET"
    except ValueError:
        return time_str[:5]


@st.cache_data(ttl=86_400, show_spinner=False)
def _load_club_country_map() -> dict[str, str]:
    """{club or alias name: country}, sourced from every domestic league's ratings CSV.

    A handful of names are used by clubs in two different countries (e.g.
    "Arsenal" is both the English club and a Belarusian one) — silently
    letting whichever league happened to load last win would misattribute
    points. Any name that maps to more than one country is dropped from the
    auto-built map entirely rather than guessed at; known, currently-relevant
    collisions are resolved explicitly via CLUB_COUNTRY_OVERRIDE instead.
    """
    name_countries: dict[str, set[str]] = {}
    for cfg in LEAGUES.values():
        country = COUNTRY_NAME_FIXUP.get(cfg.get("country", ""), cfg.get("country", ""))
        csv_path = Path("ratings") / f"{cfg.get('tsdb_id', cfg['id'])}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str)
        if "team" not in df.columns:
            continue
        for _, row in df.iterrows():
            for col in ("team", "alias"):
                name = str(row.get(col, "")).strip()
                if name and name.lower() != "nan":
                    name_countries.setdefault(name, set()).add(country)

    mapping = {name: next(iter(countries)) for name, countries in name_countries.items()
               if len(countries) == 1}
    mapping.update(CLUB_COUNTRY_OVERRIDE)
    return mapping


@st.cache_data(ttl=3_600, show_spinner=False)
def _fetch_comp_fixtures(comp_name: str, key: str):
    cid = EUROPEAN_COMPETITIONS[comp_name]["id"]
    client = ApiFootballClient(api_key=key)
    return client.get_fixtures(cid, _SEASON)


def _round_points(round_str: str) -> tuple[float, float]:
    return _QUAL_POINTS if round_str in _QUALIFYING_ROUNDS else _FULL_POINTS


def _group_ties(fixtures: list[dict]) -> list[list[dict]]:
    tie_map: dict[frozenset, list[dict]] = {}
    for f in fixtures:
        key = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
        tie_map.setdefault(key, []).append(f)
    return [sorted(legs, key=lambda x: x.get("dateEvent", "")) for legs in tie_map.values()]


def _tie_result(legs: list[dict], played_ids: set) -> tuple[str | None, str | None]:
    """(winner, loser) once a tie (1 or 2 legs) is decided on aggregate, else
    (None, None). D.7: penalty shootouts don't show up in the score fields,
    so a shootout-decided tie won't register a winner/loser here — a known
    gap (shootouts don't count for points either, but they do decide who
    advances in real life)."""
    legs = sorted(legs, key=lambda x: x.get("dateEvent", ""))
    leg1 = legs[0]
    leg2 = legs[1] if len(legs) > 1 else None
    t1, t2 = leg1.get("strHomeTeam", ""), leg1.get("strAwayTeam", "")
    l1_played = leg1.get("idEvent") in played_ids
    l2_played = leg2 is not None and leg2.get("idEvent") in played_ids
    if leg2 is not None and l1_played and l2_played:
        agg1 = int(leg1.get("intHomeScore") or 0) + int(leg2.get("intAwayScore") or 0)
        agg2 = int(leg1.get("intAwayScore") or 0) + int(leg2.get("intHomeScore") or 0)
        if agg1 > agg2: return t1, t2
        if agg2 > agg1: return t2, t1
        return None, None
    if leg2 is None and l1_played:
        h, a = int(leg1.get("intHomeScore") or 0), int(leg1.get("intAwayScore") or 0)
        if h > a: return t1, t2
        if a > h: return t2, t1
    return None, None


def _is_league_stage(round_str: str) -> bool:
    s = round_str.lower()
    return "league stage" in s or "league phase" in s


def _classify_knockout_round(round_str: str) -> str | None:
    """R16 / QF / SF / FINAL / KPO (the Round-of-16 knockout play-off round
    among 9th-24th), or None if this isn't a knockout-stage round at all."""
    s = round_str.strip().lower()
    if "quarter" in s:
        return "QF"
    if "semi" in s:
        return "SF"
    if s == "final":
        return "FINAL"
    if "round of 16" in s:
        return "R16"
    if "knockout" in s and "play" in s:
        return "KPO"
    return None


@st.cache_data(ttl=3_600, show_spinner=False)
def _final_league_phase_standings(comp_name: str, key: str) -> list[dict] | None:
    """Full 36-club League Stage table, sorted points/GD/GF. Returns None
    until every League Stage match has been played — the ranking bonus
    (D.5b) is only meaningful once the phase is actually complete."""
    played, remaining = _fetch_comp_fixtures(comp_name, key)
    lp_played = [f for f in played if _is_league_stage(f.get("strRound", ""))]
    lp_remaining = [f for f in remaining if _is_league_stage(f.get("strRound", ""))]
    if not lp_played or lp_remaining:
        return None

    teams: dict[str, dict] = {}
    for f in lp_played:
        home, away = f.get("strHomeTeam", ""), f.get("strAwayTeam", "")
        hs, aws = int(f.get("intHomeScore") or 0), int(f.get("intAwayScore") or 0)
        for t in (home, away):
            teams.setdefault(t, {"club": t, "pts": 0, "gd": 0, "gf": 0})
        teams[home]["gf"] += hs
        teams[home]["gd"] += hs - aws
        teams[away]["gf"] += aws
        teams[away]["gd"] += aws - hs
        if hs > aws:
            teams[home]["pts"] += 3
        elif aws > hs:
            teams[away]["pts"] += 3
        else:
            teams[home]["pts"] += 1
            teams[away]["pts"] += 1
    return sorted(teams.values(), key=lambda r: (-r["pts"], -r["gd"], -r["gf"]))


def _league_phase_bonus(rank: int, comp_name: str) -> float:
    """D.5(b): sliding-scale bonus by final League Phase rank."""
    if rank <= 0:
        return 0.0
    if comp_name == "Champions League":
        return 6.0 if rank > 25 else round(12.0 - 0.25 * (rank - 1), 3)
    if comp_name == "Europa League":
        return 0.0 if rank > 25 else round(6.0 - 0.25 * (rank - 1), 3)
    if comp_name == "Conference League":
        if rank > 25:
            return 0.0
        if rank <= 9:
            return round(4.0 - 0.25 * (rank - 1), 3)
        return round(2.0 - 0.125 * (rank - 9), 3)
    return 0.0


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_league_phase_bonus_points(key: str) -> dict[str, float]:
    """{club: bonus points} from D.5(b), for competitions whose League Phase
    has fully concluded."""
    bonus: dict[str, float] = {}
    for comp_name in EUROPEAN_COMPETITIONS:
        standings = _final_league_phase_standings(comp_name, key)
        if not standings:
            continue
        for i, row in enumerate(standings, start=1):
            bonus[row["club"]] = bonus.get(row["club"], 0.0) + _league_phase_bonus(i, comp_name)
    return bonus


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_secured_league_phase_bonus(key: str) -> dict[str, float]:
    """Every club guaranteed a League Phase spot gets the worst-case (rank
    36) league-phase-ranking bonus floor immediately, rather than waiting
    for the whole phase to finish to credit anything — updated live as more
    clubs secure their spot (the initial confirmed-entrant list plus every
    Play-off round tie winner as those get decided). Once a competition's
    League Phase actually concludes, _compute_league_phase_bonus_points
    takes over with the real per-rank value (always >= this floor), so
    there's no double-counting."""
    bonus: dict[str, float] = {}
    for comp_name, floor in _SECURED_LP_FLOOR.items():
        if floor <= 0.0:
            continue
        if _final_league_phase_standings(comp_name, key):
            continue  # real per-rank bonus already applies instead

        secured: set[str] = {club for club, _c, _f in CONFIRMED_LEAGUE_PHASE.get(comp_name, [])}
        played, remaining = _fetch_comp_fixtures(comp_name, key)
        played_ids = {f.get("idEvent") for f in played}
        po_fixtures = [f for f in played + remaining if f.get("strRound") == "Play-offs"]
        for legs in _group_ties(po_fixtures):
            winner, _loser = _tie_result(legs, played_ids)
            if winner:
                secured.add(winner)

        for club in secured:
            bonus[club] = floor
    return bonus


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_round_reached_bonus(key: str) -> dict[str, float]:
    """{club: bonus points} from D.5(a) — reaching R16 (via League Phase
    top 8 or winning the knockout play-off round), QF, SF, or the Final."""
    bonus: dict[str, float] = {}

    def credit(club, amount):
        if club:
            bonus[club] = bonus.get(club, 0.0) + amount

    for comp_name, per_stage in _BONUS_PER_STAGE.items():
        played, remaining = _fetch_comp_fixtures(comp_name, key)
        played_ids = {f.get("idEvent") for f in played}
        rounds_map: dict[str, list] = {}
        for f in played + remaining:
            cls = _classify_knockout_round(f.get("strRound", ""))
            if cls:
                rounds_map.setdefault(cls, []).append(f)

        lp_standings = _final_league_phase_standings(comp_name, key)
        if lp_standings:
            for row in lp_standings[:8]:
                credit(row["club"], per_stage)              # reached R16 directly

        if "KPO" in rounds_map:
            for legs in _group_ties(rounds_map["KPO"]):
                winner, _ = _tie_result(legs, played_ids)
                credit(winner, per_stage)                    # reached R16 via play-off

        for stage in ("R16", "QF", "SF"):                    # winner reaches the NEXT stage
            for legs in _group_ties(rounds_map.get(stage, [])):
                winner, _ = _tie_result(legs, played_ids)
                credit(winner, per_stage)
    return bonus


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_live_raw_points(key: str) -> dict[str, float]:
    """Total points earned by each country's clubs this season — match
    points plus both bonus types — NOT yet divided by clubs entered."""
    club_country = _load_club_country_map()
    points: dict[str, float] = {}

    def add(club, amount):
        country = club_country.get(club)
        if country:
            points[country] = points.get(country, 0.0) + amount

    for comp_name in EUROPEAN_COMPETITIONS:
        played, _ = _fetch_comp_fixtures(comp_name, key)
        for f in played:
            hs, aws = f.get("intHomeScore"), f.get("intAwayScore")
            if hs in (None, "") or aws in (None, ""):
                continue
            hs, aws = int(hs), int(aws)
            win_pts, draw_pts = _round_points(f.get("strRound", ""))
            home, away = f.get("strHomeTeam", ""), f.get("strAwayTeam", "")
            if hs > aws:
                add(home, win_pts)
            elif aws > hs:
                add(away, win_pts)
            else:
                add(home, draw_pts)
                add(away, draw_pts)

    for club, amount in _compute_round_reached_bonus(key).items():
        add(club, amount)
    for club, amount in _compute_league_phase_bonus_points(key).items():
        add(club, amount)
    for club, amount in _compute_secured_league_phase_bonus(key).items():
        add(club, amount)

    return points


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_live_coefficients(key: str) -> dict[str, float]:
    """D.3: country coefficient = total points / clubs entered, truncated
    (not rounded) to 3 decimals."""
    raw = _compute_live_raw_points(key)
    result: dict[str, float] = {}
    for country, pts in raw.items():
        entered = COUNTRY_BASELINE.get(country, {}).get("clubs_entered", 0)
        if entered > 0:
            result[country] = math.floor(pts / entered * 1000 + 1e-9) / 1000
    return result


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_ecl_eliminations(key: str) -> list[dict]:
    """Every Conference League club knocked out so far this season (aggregate
    loss, no further competition to drop into) — one entry per elimination,
    with the date of the decisive leg so callers can scope to a date range."""
    club_country = _load_club_country_map()
    played, remaining = _fetch_comp_fixtures("Conference League", key)
    played_ids = {f.get("idEvent") for f in played}
    rounds_map: dict[str, list] = {}
    for f in played + remaining:
        rounds_map.setdefault(f.get("strRound", ""), []).append(f)

    eliminations: list[dict] = []
    for round_name, fixtures in rounds_map.items():
        for legs in _group_ties(fixtures):
            _winner, loser = _tie_result(legs, played_ids)
            if loser:
                country = club_country.get(loser)
                if country:
                    eliminations.append({
                        "country": country, "club": loser, "round": round_name,
                        "date": legs[-1].get("dateEvent", ""),
                    })
    return eliminations


def _build_ranking_df() -> pd.DataFrame:
    live = _compute_live_coefficients(_API_KEY)
    ecl_eliminations = _compute_ecl_eliminations(_API_KEY)
    ecl_out: dict[str, int] = {}
    for e in ecl_eliminations:
        ecl_out[e["country"]] = ecl_out.get(e["country"], 0) + 1
    rows = []
    all_countries = set(COUNTRY_BASELINE) | set(live)
    for country in all_countries:
        base = COUNTRY_BASELINE.get(country, {
            "22/23": 0.0, "23/24": 0.0, "24/25": 0.0, "25/26": 0.0,
            "clubs_entered": 0, "clubs_active": 0,
        })
        current = round(live.get(country, 0.0), 3)
        total = round(base["22/23"] + base["23/24"] + base["24/25"] + base["25/26"] + current, 3)
        active = max(0, base["clubs_active"] - ecl_out.get(country, 0))
        rows.append({
            "Flag": _FLAGS.get(country, "🏳️"),
            "Country": country,
            "22/23": base["22/23"], "23/24": base["23/24"],
            "24/25": base["24/25"], "25/26": base["25/26"],
            "26/27": current,
            "5-Year Total": total,
            "Clubs": f"{active}/{base['clubs_entered']}" if base["clubs_entered"] else "0",
            # D.8 tiebreak: most recent season in which coefficients differ
            "_sort": (total, current, base["25/26"], base["24/25"], base["23/24"], base["22/23"]),
        })
    df = pd.DataFrame(rows).sort_values("_sort", ascending=False).drop(columns=["_sort"]).reset_index(drop=True)
    df.insert(0, "Rank", df.index + 1)
    return df


def _week_range(today: datetime) -> tuple[str, str]:
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.markdown("<h3 style='margin:0'>📈 Coefficients</h3>", unsafe_allow_html=True)
st.caption(
    "UEFA Country Ranking — the sum of each association's national coefficient over the "
    "last 5 seasons. This determines how many clubs a country sends into UEFA club "
    "competitions next season, and at which round they enter."
)
st.divider()

st.markdown("### 🌍 Country Ranking")
_df = _build_ranking_df()
_col_cfg = {
    "Rank":  st.column_config.NumberColumn("Rank", width="small"),
    "Flag":  st.column_config.TextColumn("", width="small"),
    "Country": st.column_config.TextColumn("Country", width="medium"),
    "22/23": st.column_config.NumberColumn("22/23", format="%.3f", width="small"),
    "23/24": st.column_config.NumberColumn("23/24", format="%.3f", width="small"),
    "24/25": st.column_config.NumberColumn("24/25", format="%.3f", width="small"),
    "25/26": st.column_config.NumberColumn("25/26", format="%.3f", width="small"),
    "26/27": st.column_config.NumberColumn("26/27", format="%.3f", width="small"),
    "5-Year Total": st.column_config.NumberColumn("5-Year Total", format="%.3f", width="small"),
    "Clubs": st.column_config.TextColumn(
        "Clubs", width="small",
        help="Clubs still active in UEFA competition this season / clubs entered. "
             "Only decrements on a Conference League elimination — Champions League "
             "and Europa League losers drop into the next competition down instead "
             "of being fully out.",
    ),
}
st.dataframe(_df, column_config=_col_cfg, use_container_width=True,
             hide_index=True, height=len(_df) * 35 + 38)
st.caption(
    "22/23–25/26: frozen snapshot from kassiesa.net (2026-08-11). "
    "26/27 onward: computed live by this site from every played match, per UEFA's "
    "official rules (Annex D of the Champions League regulations). "
    "Click any column header to sort."
)

st.divider()

# ---------------------------------------------------------------------------
# This week's matches
# ---------------------------------------------------------------------------
_today = datetime.now(_CET)
_week_start, _week_end = _week_range(_today)
st.markdown(f"### 📅 This Week's Matches ({_week_start} to {_week_end})")

club_country = _load_club_country_map()
_week_rows = []
for comp_name, comp_cfg in EUROPEAN_COMPETITIONS.items():
    played, remaining = _fetch_comp_fixtures(comp_name, _API_KEY)
    played_ids = {f.get("idEvent") for f in played}
    for f in played + remaining:
        d = f.get("dateEvent", "")
        if not (_week_start <= d <= _week_end):
            continue
        home, away = f.get("strHomeTeam", ""), f.get("strAwayTeam", "")
        is_played = f.get("idEvent") in played_ids
        h_country = club_country.get(home, "—")
        a_country = club_country.get(away, "—")
        pts_str = ""
        if is_played:
            hs, aws = int(f.get("intHomeScore") or 0), int(f.get("intAwayScore") or 0)
            win_pts, draw_pts = _round_points(f.get("strRound", ""))
            if hs > aws:
                pts_str = f"{home} +{win_pts:.1f}"
            elif aws > hs:
                pts_str = f"{away} +{win_pts:.1f}"
            else:
                pts_str = f"both +{draw_pts:.1f}"
        _week_rows.append({
            "_date": d, "_time": f.get("strTime", ""),
            "Comp": comp_cfg["flag"],
            "Date": d,
            "Time": _utc_to_cet(d, f.get("strTime", "")),
            "Round": f.get("strRound", ""),
            "Home": f"{_FLAGS.get(h_country, '')} {home}",
            "Score": f"{f.get('intHomeScore','')}–{f.get('intAwayScore','')}" if is_played else "vs",
            "Away": f"{away} {_FLAGS.get(a_country, '')}",
            "Points": pts_str,
        })

if not _week_rows:
    st.info("No Champions League, Europa League, or Conference League matches this week.")
else:
    _week_rows.sort(key=lambda r: (r["_date"], r["_time"]))
    _week_df = pd.DataFrame(_week_rows).drop(columns=["_date", "_time"])
    st.dataframe(
        _week_df,
        column_config={
            "Comp":   st.column_config.TextColumn("", width="small"),
            "Date":   st.column_config.TextColumn("Date", width="small"),
            "Time":   st.column_config.TextColumn("Time", width="small"),
            "Round":  st.column_config.TextColumn("Round", width="medium"),
            "Home":   st.column_config.TextColumn("Home", width="medium"),
            "Score":  st.column_config.TextColumn("Score", width="small"),
            "Away":   st.column_config.TextColumn("Away", width="medium"),
            "Points": st.column_config.TextColumn("Points added", width="medium"),
        },
        use_container_width=True, hide_index=True, height=len(_week_df) * 35 + 38,
    )

    # ── Points won this week by nation ──────────────────────────────────────
    st.markdown("#### Points won this week, by nation")
    weekly_totals: dict[str, float] = {}
    for comp_name in EUROPEAN_COMPETITIONS:
        played, _ = _fetch_comp_fixtures(comp_name, _API_KEY)
        for f in played:
            d = f.get("dateEvent", "")
            if not (_week_start <= d <= _week_end):
                continue
            hs, aws = f.get("intHomeScore"), f.get("intAwayScore")
            if hs in (None, "") or aws in (None, ""):
                continue
            hs, aws = int(hs), int(aws)
            win_pts, draw_pts = _round_points(f.get("strRound", ""))
            h_country = club_country.get(f.get("strHomeTeam", ""))
            a_country = club_country.get(f.get("strAwayTeam", ""))
            if hs > aws:
                h_add, a_add = win_pts, 0.0
            elif aws > hs:
                h_add, a_add = 0.0, win_pts
            else:
                h_add, a_add = draw_pts, draw_pts
            if h_country:
                weekly_totals[h_country] = weekly_totals.get(h_country, 0.0) + h_add
            if a_country:
                weekly_totals[a_country] = weekly_totals.get(a_country, 0.0) + a_add
    # Include every nation with a club playing this week, even at 0.0 so far
    countries_this_week = set()
    for comp_name in EUROPEAN_COMPETITIONS:
        played, remaining = _fetch_comp_fixtures(comp_name, _API_KEY)
        for f in played + remaining:
            d = f.get("dateEvent", "")
            if not (_week_start <= d <= _week_end):
                continue
            for t in (f.get("strHomeTeam", ""), f.get("strAwayTeam", "")):
                c = club_country.get(t)
                if c:
                    countries_this_week.add(c)

    _weekly_rows = [
        {"Flag": _FLAGS.get(c, "🏳️"), "Country": c, "Points this week": round(weekly_totals.get(c, 0.0), 3)}
        for c in countries_this_week
    ]
    _weekly_df = pd.DataFrame(_weekly_rows).sort_values(
        "Points this week", ascending=False).reset_index(drop=True)
    st.dataframe(
        _weekly_df,
        column_config={
            "Flag": st.column_config.TextColumn("", width="small"),
            "Country": st.column_config.TextColumn("Country", width="medium"),
            "Points this week": st.column_config.NumberColumn("Points this week", format="%.3f", width="small"),
        },
        use_container_width=True, hide_index=True, height=len(_weekly_df) * 35 + 38,
    )
    st.caption(
        "This table shows raw match points, not yet divided by clubs entered — see the "
        "note above the main ranking table for why the Country Ranking above divides."
    )

st.divider()

with st.expander("ℹ️ How coefficient points are calculated"):
    st.markdown(
        """
Sourced from **Annex D of the official UEFA Champions League regulations**.

**D.3 — Association (country) coefficient:** add up every point earned by all of a
country's clubs in a season, across the Champions League, Europa League and Conference
League, then **divide by the number of clubs that country entered**. So a country with 4
clubs earns 0.25 of a coefficient point per qualifying-round win by any one of them, not
1.0 — the win is shared across the whole entry, not credited in full. Coefficients are
**truncated** (not rounded) to 3 decimal places. The country ranking is the sum of 5
seasons of these coefficients.

**Match points:**
- 2 points for a win, 1 for a draw — from the League Stage onward, including the
  Round-of-16 knockout play-off round.
- 1 point for a win, 0.5 for a draw — in the qualifying rounds and the pre-season
  Play-off round (halved).
- Penalty shootouts don't count — a shootout-decided tie scores as a draw for points,
  even though it still decides who advances.

**D.5 — Bonus points** (also divided by clubs entered, same as match points):
- **Reaching a knockout stage:** 1.5 points in the Champions League, 1.0 in the Europa
  League, 0.5 in the Conference League — for each of the Round of 16, Quarter-finals,
  Semi-finals and Final a club reaches (awarded to whoever wins the tie that gets them
  there, or to the top 8 in the League Phase who go straight to the Round of 16).
- **Final League Phase position:** a sliding scale — 12.000 / 6.000 / 4.000 (CL / EL /
  ECL) for finishing 1st, decreasing by 0.25 per rank (0.125 per rank from 9th–25th in
  the Conference League) down to 6.000 / 0.000 / 0.000 by 25th, then flat for 26th–36th.
- **Secured-spot floor:** the worst possible League Phase ranking bonus (6.000 for the
  Champions League; 0.000 for the Europa League/Conference League, i.e. no different
  from crediting nothing) is guaranteed the moment a club secures its League Phase
  place — this site credits it immediately rather than waiting for the whole phase to
  finish, and updates the list of secured clubs live as more win their Play-off round
  tie. Once a League Phase actually concludes, the real per-rank value (always ≥ the
  floor) takes over.

**Known gap:** ties decided by a penalty shootout don't register a winner/loser in this
site's tracking, since the score fields used don't carry shootout results — a rare edge
case in qualifying rounds, but worth revisiting.

Source: [kassiesa.net — UEFA Coefficients calculation method](https://kassiesa.net/uefa/calc.html)
(itself a summary of UEFA's official Annex D)
        """
    )

st.divider()

# ---------------------------------------------------------------------------
# Nations that lost a club this week (Conference League eliminations only —
# Champions League / Europa League losers drop into the next competition
# down, so they're not a final exit)
# ---------------------------------------------------------------------------
st.markdown("### ⬇️ Clubs Eliminated This Week")
_week_eliminations = [
    e for e in _compute_ecl_eliminations(_API_KEY)
    if _week_start <= (e["date"] or "") <= _week_end
]
if not _week_eliminations:
    st.info("No Conference League clubs were eliminated this week.")
else:
    _by_country: dict[str, list[str]] = {}
    for e in _week_eliminations:
        _by_country.setdefault(e["country"], []).append(e["club"])
    _elim_rows = [
        {
            "Flag": _FLAGS.get(country, "🏳️"),
            "Country": country,
            "Clubs lost": len(clubs),
            "Eliminated": ", ".join(sorted(clubs)),
        }
        for country, clubs in _by_country.items()
    ]
    _elim_df = pd.DataFrame(_elim_rows).sort_values(
        "Clubs lost", ascending=False).reset_index(drop=True)
    st.dataframe(
        _elim_df,
        column_config={
            "Flag": st.column_config.TextColumn("", width="small"),
            "Country": st.column_config.TextColumn("Country", width="medium"),
            "Clubs lost": st.column_config.NumberColumn("Clubs lost", width="small"),
            "Eliminated": st.column_config.TextColumn("Eliminated", width="large"),
        },
        use_container_width=True, hide_index=True, height=len(_elim_df) * 35 + 38,
    )
    st.caption("Conference League eliminations only — see the note above on why.")
