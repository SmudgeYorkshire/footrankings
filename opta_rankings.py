"""
Opta Rankings — public page.

Shows Opta Power Ranking ratings (0-100 scale) used to project match outcomes:
  • Overall — every club from every league, ranked on one global table
  • By League — per-league ratings table
  • Non-Top 5 — every club except those from the Top 5 leagues, ranked on one table
  • Complete Rankings — the full global Opta list (~13,800 teams from every
    country, not just the 54 we track), scraped separately by
    scrape_opta_power_rankings.py, with our tracked clubs flagged
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from config import LEAGUES, get_current_season
from ratings_manager import load_ratings
from api_football_fetcher import ApiFootballClient
from league_display import TOP5_LEAGUES as _TOP5_LEAGUES, DROPDOWN_LABELS, DROPDOWN_ORDER

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_GLOBAL_RANKINGS_PATH = "opta_power_rankings.csv"
_GLOBAL_RANKINGS_META_PATH = "opta_power_rankings_meta.json"


def _load_opta_meta() -> dict:
    if not Path(_GLOBAL_RANKINGS_META_PATH).exists():
        return {}
    try:
        with open(_GLOBAL_RANKINGS_META_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _fmt_date(iso_date: str | None) -> str | None:
    if not iso_date:
        return None
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
    except ValueError:
        return iso_date
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"  # avoids %-d, not portable on Windows


st.markdown(
    "<h3 style='margin:0'>⭐ Opta Rankings</h3>",
    unsafe_allow_html=True,
)
st.caption("Opta Power Ranking ratings used to project match outcomes across all European leagues.")

_opta_meta = _load_opta_meta()
_opta_updated = _fmt_date(_opta_meta.get("opta_last_updated"))
if _opta_updated:
    st.caption(f"📅 Opta data last updated **{_opta_updated}** — synced to this site's ratings below.")

st.divider()

tab_overall, tab_league, tab_non_top5, tab_global = st.tabs(
    ["🌍 Overall", "🏆 By League", "🌐 Non-Top 5", "🗺️ Complete Rankings"]
)

_RATING_COL_CFG = {
    "Rank":          st.column_config.NumberColumn("Rank", width="small"),
    "Badge":         st.column_config.ImageColumn("", width="small"),
    "Team":          st.column_config.TextColumn("Team", width="medium"),
    "League Badge":  st.column_config.ImageColumn("", width="small"),
    "League":        st.column_config.TextColumn("League", width="medium"),
    "Opta Rating":   st.column_config.NumberColumn("Opta Rating", format="%.1f", width="small"),
}


def _league_badge_url(league_id: int) -> str:
    """API-Football's league logo CDN URL — deterministic, no API call needed."""
    return f"https://media.api-sports.io/football/leagues/{league_id}.png"


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_team_badges(league_id: int, season, key: str) -> dict[str, str]:
    """{team_name: badge_url} for one league's current roster."""
    try:
        client = ApiFootballClient(api_key=key)
        roster = client.get_standings(league_id, season)
    except Exception as e:
        # A real failure (bad key, rate limit, provider outage) looks
        # identical to "no badges available" in the UI either way, but at
        # least log it so it's not completely invisible.
        print(f"[opta_rankings] WARNING: badge fetch failed for league {league_id}: {e}", file=sys.stderr)
        return {}
    return {r["strTeam"]: r["strBadge"] for r in roster if r.get("strTeam") and r.get("strBadge")}


# ---------------------------------------------------------------------------
# Combine every league's ratings into one table (shared by Overall/Non-Top 5)
# Team names are shown as the live-data provider (API-Football) has them,
# matching the rest of the site. The Opta <-> provider name mapping itself
# lives in club_aliases.csv.
# ---------------------------------------------------------------------------
_all_rows = []
for league_name, cfg in LEAGUES.items():
    ratings_df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [])
    season = cfg.get("af_season") or get_current_season(cfg["season_type"])
    team_badges = _fetch_team_badges(cfg["id"], season, _API_KEY)
    league_badge = _league_badge_url(cfg["id"])
    time.sleep(0.3)  # pacing on a cold cache — avoids API-Football's burst rate-limit

    for _, row in ratings_df.iterrows():
        if pd.isna(row["opta_rating"]):
            continue
        opta_name = row["team"]
        alias = str(row.get("alias", "")).strip()
        display_name = alias if alias else opta_name
        # Badge lookup checks both fields — alias isn't always the one that
        # actually matches the live provider's current name (sometimes the
        # primary team name already matches and alias is a stale leftover).
        badge = team_badges.get(display_name) or team_badges.get(opta_name) or team_badges.get(alias, "")
        _all_rows.append({
            "Team":         display_name,
            "Badge":        badge,
            "League":       f"{cfg['flag']} {league_name}",
            "League Badge": league_badge,
            "_league_name": league_name,
            "Opta Rating":  row["opta_rating"],
        })
_all_df = pd.DataFrame(_all_rows)


def _ranked(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("Opta Rating", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", out.index + 1)
    return out[["Rank", "Badge", "Team", "League Badge", "League", "Opta Rating"]]


# ---------------------------------------------------------------------------
# Overall — every club from every league
# ---------------------------------------------------------------------------
with tab_overall:
    st.dataframe(
        _ranked(_all_df),
        column_config=_RATING_COL_CFG,
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# By League — pick one league, show its ratings table
# ---------------------------------------------------------------------------
with tab_league:
    league_name = st.selectbox(
        "League", options=DROPDOWN_ORDER,
        format_func=lambda n: DROPDOWN_LABELS.get(n, n),
        key="opta_league_select",
    )
    cfg = LEAGUES[league_name]

    league_df = _ranked(_all_df[_all_df["_league_name"] == league_name]).drop(columns=["League", "League Badge"])

    col_logo, col_title = st.columns([1, 9])
    with col_logo:
        st.image(_league_badge_url(cfg["id"]), width=60)
    with col_title:
        st.markdown(f"#### {cfg['flag']} {league_name}")
    st.dataframe(
        league_df,
        column_config=_RATING_COL_CFG,
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# Non-Top 5 — every club except England/France/Germany/Italy/Spain
# ---------------------------------------------------------------------------
with tab_non_top5:
    non_top5_df = _all_df[~_all_df["_league_name"].isin(_TOP5_LEAGUES)]
    st.dataframe(
        _ranked(non_top5_df),
        column_config=_RATING_COL_CFG,
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# Complete Rankings — the full global Opta list, our tracked clubs flagged
# ---------------------------------------------------------------------------
with tab_global:
    if not Path(_GLOBAL_RANKINGS_PATH).exists():
        st.info(
            "No global rankings scrape found yet. Run `scrape_opta_power_rankings.py` "
            "(scheduled weekdaily via the Update Opta Ratings workflow) to generate "
            f"{_GLOBAL_RANKINGS_PATH}."
        )
    else:
        from update_ratings_from_opta import _normalize

        @st.cache_data(ttl=3_600, show_spinner=False)
        def _load_global_rankings_df(mtime: float) -> pd.DataFrame:
            df = pd.read_csv(_GLOBAL_RANKINGS_PATH)
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
            return df

        _global_df = _load_global_rankings_df(Path(_GLOBAL_RANKINGS_PATH).stat().st_mtime)

        # Tag every globally-ranked team that matches one of our tracked
        # clubs with which league we track it in. Matches against both the
        # `team` and `alias` columns of each league's ratings CSV (not the
        # single alias-preferred display name _all_df uses) -- e.g. Brighton
        # & Hove Albion's alias is the short "Brighton", so matching only
        # the display name would miss the full name this scrape uses.
        _tracked_by_norm: dict[str, str] = {}
        for _league_name, _cfg in LEAGUES.items():
            _label = f"{_cfg['flag']} {_league_name}"
            _csv_path = Path("ratings") / f"{_cfg.get('tsdb_id', _cfg['id'])}.csv"
            if not _csv_path.exists():
                continue
            _rdf = pd.read_csv(_csv_path, dtype=str)
            for _, _rrow in _rdf.iterrows():
                for _col in ("team", "alias"):
                    _name = str(_rrow.get(_col, "")).strip()
                    if _name and _name.lower() != "nan":
                        _tracked_by_norm.setdefault(_normalize(_name), _label)
        _global_df["Tracked League"] = _global_df["team"].map(
            lambda t: _tracked_by_norm.get(_normalize(t), "")
        )

        st.caption(
            f"Every men's team Opta rates worldwide ({len(_global_df):,} teams), not just the 54 "
            f"leagues this site tracks in detail (Opta data last updated {_opta_updated or 'unknown'}). "
            f"Rows highlighted with a league name are one of our tracked clubs."
        )

        col_search, col_toggle = st.columns([3, 1])
        with col_search:
            _search = st.text_input("Search team", key="global_rankings_search", placeholder="e.g. Boca Juniors")
        with col_toggle:
            _tracked_only = st.checkbox("Tracked clubs only", key="global_rankings_tracked_only")

        _view = _global_df
        if _search:
            _view = _view[_view["team"].str.contains(_search, case=False, na=False)]
        if _tracked_only:
            _view = _view[_view["Tracked League"] != ""]

        _view = _view.rename(columns={
            "rank": "Rank", "team": "Team", "rating": "Rating",
            "change_7d": "7-Day Change", "badge_url": "Badge",
        })[["Rank", "Badge", "Team", "Rating", "7-Day Change", "Tracked League"]]

        st.dataframe(
            _view,
            column_config={
                "Rank":           st.column_config.NumberColumn("Rank", width="small"),
                "Badge":          st.column_config.ImageColumn("", width="small"),
                "Team":           st.column_config.TextColumn("Team", width="medium"),
                "Rating":         st.column_config.NumberColumn("Rating", format="%.1f", width="small"),
                "7-Day Change":   st.column_config.NumberColumn("7-Day Change", width="small"),
                "Tracked League": st.column_config.TextColumn("Tracked League", width="medium"),
            },
            use_container_width=True,
            hide_index=True,
            height=600,
        )
