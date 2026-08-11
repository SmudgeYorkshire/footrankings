"""
Coefficients — UEFA Country Ranking, computed by this site from live results.

22/23 through 25/26 are a frozen one-time snapshot from kassiesa.net (see
coefficients_baseline.py) — those seasons are closed and UEFA's methodology
has changed over the years, so they can't be cleanly reconstructed. The
current season (26/27) is computed live from every Champions League, Europa
League and Conference League match played so far, using the same point
rules kassiesa.net documents (qualifying rounds count at half value; group/
league stage onwards and the knockout play-off round count at full value).

Bonus points for *reaching* the Round of 16 / Quarter-finals / Semi-finals /
Final aren't modelled yet — not relevant until the knockout stage starts in
February 2027, but worth revisiting before then.
"""

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

# Exact strRound text that counts at the halved qualifying rate. Everything
# else that's a real match round (league stage onward, incl. the knockout
# play-off round) counts at full rate — see the docstring above.
_QUALIFYING_ROUNDS = {
    "1st Qualifying Round", "2nd Qualifying Round", "3rd Qualifying Round", "Play-offs",
}
_QUAL_POINTS = (1.0, 0.5)   # (win, draw)
_FULL_POINTS = (2.0, 1.0)


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
    """{club or alias name: country}, sourced from every domestic league's ratings CSV."""
    mapping: dict[str, str] = {}
    for cfg in LEAGUES.values():
        country = COUNTRY_NAME_FIXUP.get(cfg.get("country", ""), cfg.get("country", ""))
        csv_path = Path("ratings") / f"{cfg.get('tsdb_id', cfg['id'])}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str)
        if "team" not in df.columns:
            continue
        for _, row in df.iterrows():
            team = str(row.get("team", "")).strip()
            alias = str(row.get("alias", "")).strip()
            if team:
                mapping[team] = country
            if alias and alias.lower() != "nan":
                mapping[alias] = country
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


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_live_coefficients(key: str) -> dict[str, float]:
    """This season's country points so far, from every played CL/EL/ECL match."""
    club_country = _load_club_country_map()
    points: dict[str, float] = {}
    for comp_name in EUROPEAN_COMPETITIONS:
        played, _ = _fetch_comp_fixtures(comp_name, key)
        for f in played:
            hs, aws = f.get("intHomeScore"), f.get("intAwayScore")
            if hs in (None, "") or aws in (None, ""):
                continue
            hs, aws = int(hs), int(aws)
            win_pts, draw_pts = _round_points(f.get("strRound", ""))
            home_country = club_country.get(f.get("strHomeTeam", ""))
            away_country = club_country.get(f.get("strAwayTeam", ""))
            if hs > aws:
                h_add, a_add = win_pts, 0.0
            elif aws > hs:
                h_add, a_add = 0.0, win_pts
            else:
                h_add, a_add = draw_pts, draw_pts
            if home_country:
                points[home_country] = points.get(home_country, 0.0) + h_add
            if away_country:
                points[away_country] = points.get(away_country, 0.0) + a_add
    return points


@st.cache_data(ttl=3_600, show_spinner=False)
def _compute_ecl_eliminations(key: str) -> list[dict]:
    """Every Conference League club knocked out so far this season (aggregate
    loss, no further competition to drop into) — one entry per elimination,
    with the date of the decisive leg so callers can scope to a date range."""
    club_country = _load_club_country_map()
    played, remaining = _fetch_comp_fixtures("Conference League", key)
    played_ids = {f.get("idEvent") for f in played}
    all_fx = played + remaining
    rounds_map: dict[str, list] = {}
    for f in all_fx:
        rounds_map.setdefault(f.get("strRound", ""), []).append(f)

    eliminations: list[dict] = []
    for round_name, fixtures in rounds_map.items():
        for legs in _group_ties(fixtures):
            leg1 = legs[0]
            leg2 = legs[1] if len(legs) > 1 else None
            t1, t2 = leg1.get("strHomeTeam", ""), leg1.get("strAwayTeam", "")
            l1_played = leg1.get("idEvent") in played_ids
            l2_played = leg2 is not None and leg2.get("idEvent") in played_ids
            loser, decisive_date = None, None
            if leg2 is not None and l1_played and l2_played:
                agg1 = int(leg1.get("intHomeScore") or 0) + int(leg2.get("intAwayScore") or 0)
                agg2 = int(leg1.get("intAwayScore") or 0) + int(leg2.get("intHomeScore") or 0)
                if agg1 > agg2:   loser = t2
                elif agg2 > agg1: loser = t1
                decisive_date = leg2.get("dateEvent", "")
            elif leg2 is None and l1_played:
                h, a = int(leg1.get("intHomeScore") or 0), int(leg1.get("intAwayScore") or 0)
                if h > a:   loser = t2
                elif a > h: loser = t1
                decisive_date = leg1.get("dateEvent", "")
            if loser:
                country = club_country.get(loser)
                if country:
                    eliminations.append({
                        "country": country, "club": loser,
                        "round": round_name, "date": decisive_date,
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
        })
    df = pd.DataFrame(rows).sort_values("5-Year Total", ascending=False).reset_index(drop=True)
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
    "26/27 onward: computed live by this site from every played match. "
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

st.divider()

with st.expander("ℹ️ How coefficient points are calculated"):
    st.markdown(
        """
Each **country coefficient** for a season is the average number of points earned by that
country's clubs, divided by the number of clubs it sent into UEFA competitions that year.
The **country ranking** is the sum of those yearly coefficients over the last 5 seasons —
last year's ranking is what determines how many clubs (and starting round) each country
gets *this* season, since the entry list has to be fixed before a new season's results exist.

**How clubs earn points (this site's live 26/27 calculation):**
- **Qualifying rounds (Q1–Q3, Play-off round):** 1 point for a win, 0.5 for a draw.
- **League Stage onwards, and the Round-of-16 knockout play-off round:** 2 points for a
  win, 1 for a draw.
- **Not yet modelled:** bonus points for *reaching* the Round of 16, Quarter-finals,
  Semi-finals or Final (1.5 pts/stage in the Champions League, 1.0 in the Europa League,
  0.5 in the Conference League) — not relevant until the knockout stage starts in
  February 2027, but worth adding before then.

Full methodology: [kassiesa.net — UEFA Coefficients calculation method](https://kassiesa.net/uefa/calc.html)
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
