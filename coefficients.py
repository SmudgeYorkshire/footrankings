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

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd

from config import EUROPEAN_COMPETITIONS
from coefficients_baseline import COUNTRY_BASELINE
from flags import flag_url as _flag_url
from coefficients_live import (
    _load_club_country_map, _fetch_comp_fixtures, _round_points,
    _group_ties, _tie_result, _compute_live_coefficients,
    _compute_live_raw_points, _coefficients_from_raw,
    _compute_todays_raw_points, _compute_ecl_eliminations, _build_ranking_df,
)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_CET = ZoneInfo("Europe/Berlin")

# Short display labels for qualifying-round strRound text, so tables don't
# have to spend width on e.g. "3rd Qualifying Round".
_SHORT_ROUND: dict[str, str] = {
    "1st Qualifying Round": "QR1",
    "2nd Qualifying Round": "QR2",
    "3rd Qualifying Round": "QR3",
    "Play-offs": "PO",
    "Playoff round": "PO",  # Conference League's own spelling for the same round
}

# Colour-coded dot per competition, used instead of the trophy/medal icons
# so the "This Week's Matches" table stays compact.
_COMP_DOT: dict[str, str] = {
    "Champions League": "🔵",
    "Europa League": "🟠",
    "Conference League": "🟢",
}


def _utc_to_cet(date_str: str, time_str: str) -> str:
    if not date_str or not time_str or time_str.startswith("00:00"):
        return date_str
    try:
        dt = datetime.strptime(f"{date_str} {time_str[:8]}", "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(_CET)
        return f"{dt.strftime('%H:%M')} CET"
    except ValueError:
        return time_str[:5]



def _week_range(today: datetime) -> tuple[str, str]:
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
_today = datetime.now(_CET)
_today_str = _today.strftime("%Y-%m-%d")

st.markdown("<h3 style='margin:0'>📈 Coefficients</h3>", unsafe_allow_html=True)
st.caption(
    "UEFA Country Ranking — the sum of each association's national coefficient over the "
    "last 5 seasons. This determines how many clubs a country sends into UEFA club "
    "competitions next season, and at which round they enter."
)
st.divider()

st.markdown("### 🌍 Country Ranking")
_df = _build_ranking_df()

# Rank movement vs. yesterday: back today's match points out of the live
# total to reconstruct where the table stood before today's results.
_todays_raw = _compute_todays_raw_points(_API_KEY, _today_str)
_all_raw = _compute_live_raw_points(_API_KEY)
_yesterday_raw = {
    c: _all_raw.get(c, 0.0) - _todays_raw.get(c, 0.0)
    for c in set(_all_raw) | set(_todays_raw)
}
_df_yesterday = _build_ranking_df(live_override=_coefficients_from_raw(_yesterday_raw))
_curr_rank = dict(zip(_df["Country"], _df["Rank"]))
_prev_rank = dict(zip(_df_yesterday["Country"], _df_yesterday["Rank"]))


def _delta_symbol(country: str) -> str:
    pr, cr = _prev_rank.get(country), _curr_rank.get(country)
    if pr is None or cr is None or pr == cr:
        return "—"
    diff = pr - cr
    return f"▲{diff}" if diff > 0 else f"▼{abs(diff)}"


_df.insert(1, "Δ", _df["Country"].map(_delta_symbol))

_col_cfg = {
    "Rank":  st.column_config.NumberColumn("Rank", width="small"),
    "Δ":     st.column_config.TextColumn("Δ", width="small", help="Rank change vs. yesterday"),
    "Flag":  st.column_config.ImageColumn("", width="small"),
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
    "Δ = rank change vs. yesterday. Click any column header to sort."
)

# ── Overtakes today ─────────────────────────────────────────────────────────
_movers = []
for _country in _curr_rank:
    _pr, _cr = _prev_rank.get(_country), _curr_rank.get(_country)
    if _pr is not None and _cr is not None and _cr < _pr:
        _passed = sorted(
            (b for b in _curr_rank
             if b != _country and _prev_rank.get(b, 10**9) < _pr and _curr_rank.get(b, 10**9) > _cr),
            key=lambda b: _curr_rank[b],
        )
        if _passed:
            _movers.append((_country, _pr, _cr, _passed))

if _movers:
    st.markdown("**Overtakes today:**")
    for _country, _pr, _cr, _passed in sorted(_movers, key=lambda m: m[2]):
        _who = ", ".join(_passed)
        st.markdown(f"🔼 **{_country}** moved from #{_pr} to #{_cr}, overtaking {_who}.")
else:
    st.caption("No rank changes yet today.")

# ── Race for an extra Champions League spot ─────────────────────────────────
st.markdown("### 🏆 Race for an extra Champions League spot")
st.caption(
    "Since 2024/25, the two national associations with the best coefficient "
    "for that season ALONE (not the 5-year total) are each awarded one extra "
    "Champions League place the following season. Ranked here purely by "
    "2026/27 points earned so far."
)
_race_df = _df[_df["Country"].map(
    lambda c: COUNTRY_BASELINE.get(c, {}).get("clubs_entered", 0) > 0
)].sort_values(
    ["26/27", "5-Year Total"], ascending=[False, False]
)[["Flag", "Country", "26/27", "Clubs"]].reset_index(drop=True)
_race_df.insert(0, "Rank", _race_df.index + 1)
st.dataframe(
    _race_df,
    column_config={
        "Rank": st.column_config.NumberColumn("Rank", width="small"),
        "Flag": st.column_config.ImageColumn("", width="small"),
        "Country": st.column_config.TextColumn("Country", width="medium"),
        "26/27": st.column_config.NumberColumn("2026/27 points", format="%.3f", width="small"),
        "Clubs": st.column_config.TextColumn("Clubs", width="small"),
    },
    use_container_width=True, hide_index=True, height=len(_race_df) * 35 + 38,
)
if len(_race_df) >= 2:
    _gold, _silver = _race_df.iloc[0], _race_df.iloc[1]
    st.caption(
        f"If the season ended today: 🥇 **{_gold['Country']}** ({_gold['26/27']:.3f}) and "
        f"🥈 **{_silver['Country']}** ({_silver['26/27']:.3f}) would each gain an extra "
        f"Champions League place."
    )

st.divider()

# ---------------------------------------------------------------------------
# Predicted final ranking
# ---------------------------------------------------------------------------
st.markdown("### 🔮 Predicted Final Ranking")
st.caption(
    "Projects each association's 2026-27 season coefficient the rest of the way — the "
    "remaining Play-off round (not yet started), then League Phase and Knockout stage for "
    "whichever clubs reach it — via the same Monte Carlo model used across this site, then "
    "adds it to the real 22/23-25/26 baseline above to rank every association. Each of the "
    "simulation runs plays out a full season, so the percentages below are a genuine "
    "probability of finishing at each rank band, not just a single point estimate."
)
with st.spinner("Simulating the rest of the season for every association…"):
    from club_coefficients import get_coeff
    from qualifying_projection import _project_league_phase_field, _resolve_field_ratings, _load_combined_ratings
    from country_ranking_simulator import project_country_predicted_ranking

    _pred_ratings_df = _load_combined_ratings()
    _pred_table, _pred_warnings = project_country_predicted_ranking(
        project_league_phase_field=_project_league_phase_field,
        resolve_field_ratings=_resolve_field_ratings,
        ratings_df=_pred_ratings_df,
        get_coeff=get_coeff,
        api_key=_API_KEY,
        n_sim=2_000,
        home_advantage=1.05,
    )

for _w in _pred_warnings:
    st.caption(f"⚠️ {_w}")

_pred_rows = []
for _country, _r in _pred_table.iterrows():
    _pred_rows.append({
        "Flag": _flag_url(_country),
        "Country": _country,
        "Clubs": _r["clubs"],
        "Predicted rank": _r["mean_rank"],
        "Projected total": _r["mean_total"],
        "Top 4": _r["pct_top4"] * 100,
        "Top 6": _r["pct_top6"] * 100,
        "Top 10": _r["pct_top10"] * 100,
        "Top 15": _r["pct_top15"] * 100,
        "Top 20": _r["pct_top20"] * 100,
    })
_pred_df = pd.DataFrame(_pred_rows)
st.dataframe(
    _pred_df,
    column_config={
        "Flag": st.column_config.ImageColumn("", width="small"),
        "Country": st.column_config.TextColumn("Country", width="medium"),
        "Clubs": st.column_config.NumberColumn("Clubs", width="small"),
        "Predicted rank": st.column_config.NumberColumn("Predicted rank", format="%.2f", width="small"),
        "Projected total": st.column_config.NumberColumn("Projected total", format="%.3f", width="small"),
        "Top 4": st.column_config.NumberColumn("Top 4", format="%.1f%%", width="small"),
        "Top 6": st.column_config.NumberColumn("Top 6", format="%.1f%%", width="small"),
        "Top 10": st.column_config.NumberColumn("Top 10", format="%.1f%%", width="small"),
        "Top 15": st.column_config.NumberColumn("Top 15", format="%.1f%%", width="small"),
        "Top 20": st.column_config.NumberColumn("Top 20", format="%.1f%%", width="small"),
    },
    use_container_width=True, hide_index=True, height=len(_pred_df) * 35 + 38,
)
st.caption(
    "\"Predicted rank\" is the average finishing position (in the *5-season* ranking, not "
    "this season alone) across every simulation run — \"Top N\" columns are the probability "
    "of finishing at or above that rank there. Not the same thing as the European Performance "
    "Spot race above, which looks at this season's coefficient alone rather than the 5-season total."
)

st.divider()

# ---------------------------------------------------------------------------
# This week's matches
# ---------------------------------------------------------------------------
_week_start, _week_end = _week_range(_today)
st.markdown(f"### 📅 This Week's Matches ({_week_start} to {_week_end})")

club_country = _load_club_country_map()
_week_rows = []
for comp_name in EUROPEAN_COMPETITIONS:
    played, remaining = _fetch_comp_fixtures(comp_name, _API_KEY)
    played_ids = {f.get("idEvent") for f in played}
    for f in played + remaining:
        d = f.get("dateEvent", "")
        if not (_week_start <= d <= _week_end):
            continue
        home, away = f.get("strHomeTeam", ""), f.get("strAwayTeam", "")
        is_played = f.get("idEvent") in played_ids
        pts_str = ""
        if is_played:
            hs, aws = int(f.get("intHomeScore") or 0), int(f.get("intAwayScore") or 0)
            win_pts, draw_pts = _round_points(f.get("strRound", ""))
            h_entered = COUNTRY_BASELINE.get(club_country.get(home, ""), {}).get("clubs_entered", 0)
            a_entered = COUNTRY_BASELINE.get(club_country.get(away, ""), {}).get("clubs_entered", 0)
            if hs > aws:
                contrib = win_pts / h_entered if h_entered else 0.0
                pts_str = f"{home} +{contrib:.3f}"
            elif aws > hs:
                contrib = win_pts / a_entered if a_entered else 0.0
                pts_str = f"{away} +{contrib:.3f}"
            else:
                h_contrib = draw_pts / h_entered if h_entered else 0.0
                a_contrib = draw_pts / a_entered if a_entered else 0.0
                pts_str = f"{home} +{h_contrib:.3f}, {away} +{a_contrib:.3f}"
        _week_rows.append({
            "_date": d, "_time": f.get("strTime", ""),
            "Comp": _COMP_DOT.get(comp_name, "⚪"),
            "Date": d[5:],
            "Time": _utc_to_cet(d, f.get("strTime", "")),
            "Round": _SHORT_ROUND.get(f.get("strRound", ""), f.get("strRound", "")),
            "Home": home,
            "Score": f"{f.get('intHomeScore','')}–{f.get('intAwayScore','')}" if is_played else "vs",
            "Away": away,
            "Points": pts_str,
        })

if not _week_rows:
    st.info("No Champions League, Europa League, or Conference League matches this week.")
else:
    _week_rows.sort(key=lambda r: (r["_date"], r["_time"]))
    _week_df = pd.DataFrame(_week_rows).drop(columns=["_date", "_time"])
    st.caption("🔵 Champions League · 🟠 Europa League · 🟢 Conference League")
    st.dataframe(
        _week_df,
        column_config={
            "Comp":   st.column_config.TextColumn("", width=32),
            "Date":   st.column_config.TextColumn("Date", width=48),
            "Time":   st.column_config.TextColumn("Time", width=70),
            "Round":  st.column_config.TextColumn("Round", width=48),
            "Home":   st.column_config.TextColumn("Home", width=140),
            "Score":  st.column_config.TextColumn("Score", width=56),
            "Away":   st.column_config.TextColumn("Away", width=140),
            "Points": st.column_config.TextColumn("Coefficient points added", width=220),
        },
        use_container_width=False, hide_index=True, height=len(_week_df) * 35 + 38,
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

    _five_yr_total = dict(zip(_df["Country"], _df["5-Year Total"]))
    _weekly_rows = []
    for c in countries_this_week:
        raw_pts = weekly_totals.get(c, 0.0)
        clubs_entered = COUNTRY_BASELINE.get(c, {}).get("clubs_entered", 0)
        contribution = round(raw_pts / clubs_entered, 3) if clubs_entered else 0.0
        _weekly_rows.append({
            "Flag": _flag_url(c), "Country": c,
            "Coefficient points this week": contribution,
            "_5yr": _five_yr_total.get(c, 0.0),
        })
    _weekly_df = pd.DataFrame(_weekly_rows).sort_values(
        ["Coefficient points this week", "_5yr"], ascending=[False, False]
    ).drop(columns=["_5yr"]).reset_index(drop=True)
    st.caption(
        "Points ÷ that country's total clubs entered this season (UEFA Annex D.3) — "
        "the same division the season-long coefficient uses."
    )
    st.dataframe(
        _weekly_df,
        column_config={
            "Flag": st.column_config.ImageColumn("", width=32),
            "Country": st.column_config.TextColumn("Country", width=120),
            "Coefficient points this week": st.column_config.NumberColumn(
                "Coefficient points", format="%.3f", width=120),
        },
        use_container_width=False, hide_index=True, height=len(_weekly_df) * 35 + 38,
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
            "Flag": _flag_url(country),
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
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Country": st.column_config.TextColumn("Country", width="medium"),
            "Clubs lost": st.column_config.NumberColumn("Clubs lost", width="small"),
            "Eliminated": st.column_config.TextColumn("Eliminated", width="large"),
        },
        use_container_width=True, hide_index=True, height=len(_elim_df) * 35 + 38,
    )
    st.caption("Conference League eliminations only — see the note above on why.")

st.divider()

# ---------------------------------------------------------------------------
# Nations left with 0 clubs this week — i.e. their last remaining club was
# eliminated from the Conference League this week (had at least 1 club
# still active going into the week, none left as of now).
# ---------------------------------------------------------------------------
st.markdown("### 🚫 Nations Eliminated This Week")
_all_ecl_eliminations = _compute_ecl_eliminations(_API_KEY)
_elims_before_week: dict[str, int] = {}
_elims_total: dict[str, int] = {}
_week_clubs_by_country: dict[str, list[str]] = {}
for e in _all_ecl_eliminations:
    _elims_total[e["country"]] = _elims_total.get(e["country"], 0) + 1
    if (e["date"] or "") < _week_start:
        _elims_before_week[e["country"]] = _elims_before_week.get(e["country"], 0) + 1
    elif (e["date"] or "") <= _week_end:
        _week_clubs_by_country.setdefault(e["country"], []).append(e["club"])

_nations_out_rows = []
for _country, _base in COUNTRY_BASELINE.items():
    _entered = _base.get("clubs_entered", 0)
    if _entered <= 0:
        continue
    _active_before = max(0, _entered - _elims_before_week.get(_country, 0))
    _active_now = max(0, _entered - _elims_total.get(_country, 0))
    if _active_before > 0 and _active_now == 0:
        _nations_out_rows.append({
            "Flag": _flag_url(_country),
            "Country": _country,
            "Clubs entered": _entered,
            "Eliminated this week": ", ".join(sorted(_week_clubs_by_country.get(_country, []))),
        })

if not _nations_out_rows:
    st.info("No nation has been eliminated entirely this week.")
else:
    _nations_out_df = pd.DataFrame(_nations_out_rows).sort_values("Country").reset_index(drop=True)
    st.dataframe(
        _nations_out_df,
        column_config={
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Country": st.column_config.TextColumn("Country", width="medium"),
            "Clubs entered": st.column_config.NumberColumn("Clubs entered", width="small"),
            "Eliminated this week": st.column_config.TextColumn("Eliminated this week", width="large"),
        },
        use_container_width=True, hide_index=True, height=len(_nations_out_df) * 35 + 38,
    )
    st.caption(
        "Nations that had at least one club still active going into this week, and now "
        "have none left in any UEFA competition — same Conference-League-only elimination "
        "logic as above (Champions League/Europa League losers parachute down instead of "
        "being fully out)."
    )
