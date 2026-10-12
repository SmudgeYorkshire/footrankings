"""
European Leagues — Trivia.

Scans every tracked top-flight league's live standings once (undefeated/
winless/perfect-season clubs, same real-fixture-results basis as every
other table on the site -- see _split_season.compute_full_standings) and
renders five ranked lists: Undefeated (Top 5 / All), Winless (Top 5 /
All), Perfect Season (All).

A full sweep touches all 54 leagues' live standings + fixtures, so this
is cached for an hour rather than football_rankings.py's usual 60s --
"who's still undefeated" doesn't need to-the-minute freshness, and
refetching 54 leagues on every page view isn't worth the API quota.
Any single league that fails to fetch is skipped rather than failing the
whole page.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from config import LEAGUES
from api_football_fetcher import ApiFootballClient
from _split_season import compute_full_standings, ensure_full_roster
from league_display import TOP5_LEAGUES
from coefficients_baseline import COUNTRY_BASELINE

# config.py's "country" field uses short display names for a handful of
# countries that don't match COUNTRY_BASELINE's real UEFA names.
_COUNTRY_ALIASES = {
    "Bosnia": "Bosnia-Herzegovina",
    "Czech Rep.": "Czechia",
    "Faroe Isl.": "Faroe Islands",
    "N. Ireland": "Northern Ireland",
    "N. Macedonia": "North Macedonia",
    "Turkey": "Türkiye",
}

_COUNTRY_RANK = {
    country: rank
    for rank, country in enumerate(
        sorted(COUNTRY_BASELINE, key=lambda c: sum(
            v for k, v in COUNTRY_BASELINE[c].items() if k not in ("clubs_entered", "clubs_active")
        ), reverse=True),
        start=1,
    )
}


def _country_rank(country: str) -> int:
    """1 = strongest (frozen 4-season UEFA country-coefficient total, same
    baseline coefficients.py's own ranking starts from) -- used only to
    break a tie when two clubs match on every other sort key (matches
    played, wins, draws), so e.g. Barcelona/Porto/Noah/UNA Strassen all
    sitting at a perfect 8-0-0 sort by their countries' actual European
    strength rather than arbitrary insertion order. A country not in the
    baseline (shouldn't happen for a tracked league) sorts last."""
    return _COUNTRY_RANK.get(_COUNTRY_ALIASES.get(country, country), len(_COUNTRY_RANK) + 1)


@st.cache_data(ttl=3_600, show_spinner=False)
def _sweep_all_leagues(api_key: str) -> tuple[list[dict], list[str], str]:
    """[{team, league, flag, badge, P, W, D, L}, ...] across every tracked
    league with at least one match played, plus the list of leagues that
    failed to fetch and an ISO timestamp of when this ran."""
    client = ApiFootballClient(api_key=api_key)
    rows: list[dict] = []
    failed: list[str] = []

    for league_name, cfg in LEAGUES.items():
        # Liechtenstein's entry is a domestic-cup placeholder, not a real
        # league (id == cup_id -- same competition both ways, see its own
        # comment in config.py: "nothing ever fetches standings for it").
        # Swept in here anyway before this check, its cup results (knockout
        # ties against wildly mismatched opposition, not a balanced league
        # season) were silently counted as league form for Undefeated/
        # Winless/Perfect Season.
        if cfg.get("id") == cfg.get("cup_id"):
            continue
        try:
            roster = client.get_standings(cfg["id"], cfg["af_season"])
            played, remaining = client.get_fixtures(cfg["id"], cfg["af_season"])
            roster = ensure_full_roster(roster, played + remaining)
            standings = compute_full_standings(roster, played, tiebreakers=cfg.get("tiebreakers"))
        except Exception:
            failed.append(league_name)
            continue
        for r in standings:
            p = int(r.get("intPlayed", 0) or 0)
            if p == 0:
                continue
            rows.append({
                "team": r.get("strTeam", ""),
                "league": league_name,
                "country": cfg.get("country", ""),
                "flag": cfg.get("flag", ""),
                "badge": r.get("strBadge", ""),
                "P": p,
                "W": int(r.get("intWin", 0) or 0),
                "D": int(r.get("intDraw", 0) or 0),
                "L": int(r.get("intLoss", 0) or 0),
            })

    return rows, failed, datetime.now(timezone.utc).isoformat()


def _build_table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "No.": i,
            "Badge": r["badge"],
            "Club": r["team"],
            "League": f"{r['flag']} {r['league']}",
            "P": r["P"],
            "Record (W-D-L)": f"{r['W']}-{r['D']}-{r['L']}",
        }
        for i, r in enumerate(rows, start=1)
    ])


_COL_CFG = {
    "No.":    st.column_config.NumberColumn("No.", width="small"),
    "Badge":  st.column_config.ImageColumn("", width="small"),
    "Club":   st.column_config.TextColumn("Club", width="medium"),
    "League": st.column_config.TextColumn("League", width="medium"),
    "P":      st.column_config.NumberColumn("P", width="small"),
    "Record (W-D-L)": st.column_config.TextColumn("Record (W-D-L)", width="small"),
}


def _render_section(title: str, rows: list[dict], empty_msg: str, full_height: bool = False) -> None:
    st.markdown(f"#### {title} ({len(rows)})")
    if not rows:
        st.caption(empty_msg)
        return
    df = _build_table(rows)
    # full_height: these sections are small enough to show every row with
    # no internal scrollbar; the others still cap at 10 rows tall.
    row_count = len(df) if full_height else min(len(df), 10)
    st.dataframe(df, column_config=_COL_CFG, hide_index=True,
                 width="content", height=row_count * 35 + 38)


def render_european_trivia() -> None:
    import os
    api_key = os.getenv("API_FOOTBALL_KEY", "")

    st.markdown("### 📊 European Leagues — Trivia")
    st.caption(
        "Pulled from this site's own live standings across all 54 tracked top-flight "
        "leagues (same real-fixture-results basis as every other table here). Refreshed hourly."
    )

    with st.spinner("Scanning every tracked league's live standings…"):
        rows, failed, fetched_at = _sweep_all_leagues(api_key)

    if not rows:
        st.error("Couldn't fetch standings for any tracked league right now — try again shortly.")
        return

    try:
        ts = datetime.fromisoformat(fetched_at).strftime("%d %b %Y, %H:%M UTC")
        st.caption(f"📅 Last refreshed: **{ts}**")
    except ValueError:
        pass
    if failed:
        st.caption(f"⚠️ {len(failed)} league(s) couldn't be fetched this run and are excluded below.")

    top5_rows = [r for r in rows if r["league"] in TOP5_LEAGUES]

    undefeated_top5 = sorted((r for r in top5_rows if r["L"] == 0),
                              key=lambda r: (-r["P"], -r["W"], -r["D"], _country_rank(r["country"])))
    undefeated_all = sorted((r for r in rows if r["L"] == 0),
                             key=lambda r: (-r["P"], -r["W"], -r["D"], _country_rank(r["country"])))
    winless_top5 = sorted((r for r in top5_rows if r["W"] == 0),
                           key=lambda r: (-r["P"], -r["L"], _country_rank(r["country"])))
    winless_all = sorted((r for r in rows if r["W"] == 0),
                          key=lambda r: (-r["P"], -r["L"], _country_rank(r["country"])))
    perfect_all = sorted((r for r in rows if r["D"] == 0 and r["L"] == 0),
                          key=lambda r: (-r["P"], _country_rank(r["country"])))

    st.divider()
    _render_section("🛡️ Undefeated Clubs — Top 5 Leagues", undefeated_top5,
                     "No undefeated clubs in the Top 5 leagues right now.", full_height=True)
    st.divider()
    _render_section("💔 Winless Clubs — Top 5 Leagues", winless_top5,
                     "No winless clubs in the Top 5 leagues right now.", full_height=True)
    st.divider()
    _render_section("🏆 Perfect Season (all wins) — All European Leagues", perfect_all,
                     "No club has a perfect season across tracked leagues right now.", full_height=True)
    st.divider()
    _render_section("🛡️ Undefeated Clubs — All European Leagues", undefeated_all,
                     "No undefeated clubs across tracked leagues right now.")
    st.divider()
    _render_section("💔 Winless Clubs — All European Leagues", winless_all,
                     "No winless clubs across tracked leagues right now.")
