"""
Live UEFA country-coefficient computation logic, shared by coefficients.py
(the Coefficients page) and country_ranking_simulator.py (the predicted
final ranking, built on top of these real, already-known numbers).

Split out from coefficients.py so this reusable logic can be imported
without pulling in that file's top-level page-rendering code (st.markdown/
st.dataframe calls and live API fetches that run immediately on import) --
see coefficients.py's own module docstring for the full UEFA Annex D
methodology this implements.
"""

import math
import os

import streamlit as st
import pandas as pd
from pathlib import Path

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
_SEASON = "2026-2027"

# Exact strRound text that counts at the halved qualifying rate (D.3).
# Everything else that's a real match round (League Stage onward, incl. the
# Round-of-16 knockout play-off round) counts at full rate. The Play-off
# round's own name isn't consistent across competitions -- Champions/Europa
# League use "Play-offs", Conference League uses "Playoff round" -- so both
# spellings need to be in this set, or Conference League Play-off matches
# silently fall through to the full (non-qualifying) rate and get double
# -counted.
_PLAYOFF_ROUND_NAMES = frozenset({"Play-offs", "Playoff round"})
_QUALIFYING_ROUNDS = {
    "1st Qualifying Round", "2nd Qualifying Round", "3rd Qualifying Round",
} | _PLAYOFF_ROUND_NAMES
_QUAL_POINTS = (1.0, 0.5)   # (win, draw)
_FULL_POINTS = (2.0, 1.0)

# D.5(a): bonus points per knockout stage reached, by competition.
_BONUS_PER_STAGE = {"Champions League": 1.5, "Europa League": 1.0, "Conference League": 0.5}


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


@st.cache_data(ttl=60, show_spinner=False)
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
    """(winner, loser) once a tie (1 or 2 legs) is decided, else (None, None).
    D.7: penalty shootouts don't count for POINTS (a shootout-decided leg
    still scores as a draw), but they do decide who advances — so an
    aggregate tie falls back to the deciding leg's penalty score, which
    API-Football reports separately from the goal score."""
    legs = sorted(legs, key=lambda x: x.get("dateEvent", ""))
    leg1 = legs[0]
    leg2 = legs[1] if len(legs) > 1 else None
    t1, t2 = leg1.get("strHomeTeam", ""), leg1.get("strAwayTeam", "")
    l1_played = leg1.get("idEvent") in played_ids
    l2_played = leg2 is not None and leg2.get("idEvent") in played_ids

    def _pens(leg, home_team, away_team):
        ph, pa = leg.get("intPenaltyHome"), leg.get("intPenaltyAway")
        if ph is None or pa is None:
            return None, None
        return (home_team, away_team) if ph > pa else (away_team, home_team)

    if leg2 is not None and l1_played and l2_played:
        agg1 = int(leg1.get("intHomeScore") or 0) + int(leg2.get("intAwayScore") or 0)
        agg2 = int(leg1.get("intAwayScore") or 0) + int(leg2.get("intHomeScore") or 0)
        if agg1 > agg2: return t1, t2
        if agg2 > agg1: return t2, t1
        winner, loser = _pens(leg2, t2, t1)  # leg2: t2 home, t1 away
        return (winner, loser) if winner else (None, None)
    if leg2 is None and l1_played:
        h, a = int(leg1.get("intHomeScore") or 0), int(leg1.get("intAwayScore") or 0)
        if h > a: return t1, t2
        if a > h: return t2, t1
        winner, loser = _pens(leg1, t1, t2)
        return (winner, loser) if winner else (None, None)
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


@st.cache_data(ttl=60, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
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
        po_fixtures = [f for f in played + remaining if f.get("strRound") in _PLAYOFF_ROUND_NAMES]
        for legs in _group_ties(po_fixtures):
            winner, _loser = _tie_result(legs, played_ids)
            if winner:
                secured.add(winner)

        for club in secured:
            bonus[club] = floor
    return bonus


@st.cache_data(ttl=60, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
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


def _coefficients_from_raw(raw: dict[str, float]) -> dict[str, float]:
    """D.3: country coefficient = total points / clubs entered, truncated
    (not rounded) to 3 decimals."""
    result: dict[str, float] = {}
    for country, pts in raw.items():
        entered = COUNTRY_BASELINE.get(country, {}).get("clubs_entered", 0)
        if entered > 0:
            result[country] = math.floor(pts / entered * 1000 + 1e-9) / 1000
    return result


@st.cache_data(ttl=60, show_spinner=False)
def _compute_live_coefficients(key: str) -> dict[str, float]:
    return _coefficients_from_raw(_compute_live_raw_points(key))


@st.cache_data(ttl=60, show_spinner=False)
def _compute_todays_raw_points(key: str, today_str: str) -> dict[str, float]:
    """Match points only (no bonus events expected on a single day at this
    stage of the season) earned specifically on today_str — used to back out
    a "yesterday" snapshot for rank-change tracking without having to
    re-run every bonus calculation with a date filter."""
    club_country = _load_club_country_map()
    points: dict[str, float] = {}

    def add(club, amount):
        country = club_country.get(club)
        if country:
            points[country] = points.get(country, 0.0) + amount

    for comp_name in EUROPEAN_COMPETITIONS:
        played, _ = _fetch_comp_fixtures(comp_name, key)
        for f in played:
            if f.get("dateEvent", "") != today_str:
                continue
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
    return points


@st.cache_data(ttl=60, show_spinner=False)
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


def _build_ranking_df(live_override: dict[str, float] | None = None) -> pd.DataFrame:
    from flags import flag_url as _flag_url
    live = live_override if live_override is not None else _compute_live_coefficients(_API_KEY)
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
        if base["clubs_entered"] == 0:
            # Suspended (no clubs entered this season, e.g. Russia) — UEFA
            # carries the last computed coefficient forward rather than
            # scoring 0, since there's nothing to divide by.
            current = base["25/26"]
        else:
            current = round(live.get(country, 0.0), 3)
        total = round(base["22/23"] + base["23/24"] + base["24/25"] + base["25/26"] + current, 3)
        # "clubs_entered" (fixed at season start) minus every Conference
        # League elimination this site has tracked live — not kassiesa's own
        # "clubs_active" baseline, which turned out to be stale for some
        # countries (e.g. showed Wales at 4/4 active weeks after 3 of its 4
        # clubs had already been eliminated).
        active = max(0, base["clubs_entered"] - ecl_out.get(country, 0))
        rows.append({
            "Flag": _flag_url(country),
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
