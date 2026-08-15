"""
Live — public page.

Shows every match currently in progress, across all 54 tracked domestic
leagues plus the Champions/Europa/Conference League, grouped by league in
the site's own display order (matches within a league stacked one below
another).

Fetched via API-Football's dedicated `live` filter, which returns every
in-play fixture across every requested league in a single request no
matter how many leagues are tracked — one API call per page load/refresh,
regardless of how much is going on. Cached for 60s: no need for
instant/second-by-second updates, so this deliberately doesn't poll any
faster than that.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from config import LEAGUES, EUROPEAN_COMPETITIONS
from api_football_fetcher import ApiFootballClient
from flags import flag_url

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_CET = ZoneInfo("Europe/Berlin")

# Domestic leagues first in the site's own order, then the 3 European
# competitions — same order as the sidebar nav (European Leagues page
# before European Competitions page). Domestic leagues get a real
# flagcdn.com flag (via their country); the European competitions aren't
# tied to one country, so they keep their trophy/medal emoji instead.
_TRACKED: list[tuple[str, int, str]] = (
    [(name, cfg["id"], flag_url(cfg.get("country", ""))) for name, cfg in LEAGUES.items()]
    + [(name, cfg["id"], "") for name, cfg in EUROPEAN_COMPETITIONS.items()]
)
_LEAGUE_ORDER = {lid: i for i, (_name, lid, _flag) in enumerate(_TRACKED)}
_LEAGUE_NAME = {lid: name for name, lid, _flag in _TRACKED}
_LEAGUE_FLAG_URL = {lid: flag for _name, lid, flag in _TRACKED}
_LEAGUE_EMOJI = {cfg["id"]: cfg.get("flag", "") for cfg in EUROPEAN_COMPETITIONS.values()}


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_live(key: str) -> tuple[list[dict], datetime]:
    client = ApiFootballClient(api_key=key)
    fixtures = client.get_live_fixtures([lid for _name, lid, _flag in _TRACKED])
    return fixtures, datetime.now(_CET)


def _status_label(short: str | None, elapsed, extra) -> str:
    mins = str(elapsed) if elapsed is not None else "?"
    if short in ("1H", "2H"):
        return f"{mins}+{extra}'" if extra else f"{mins}'"
    if short == "HT":
        return "HT"
    if short == "ET":
        return f"ET {mins}+{extra}'" if extra else f"ET {mins}'"
    if short == "BT":
        return "Break"
    if short == "P":
        return "Penalties"
    if short == "SUSP":
        return "Suspended"
    if short == "INT":
        return "Interrupted"
    return short or "Live"


def _img(url: str, side: str) -> str:
    if not url:
        return ""
    return f"<img src='{url}' height='20' style='margin-{side}:8px;vertical-align:middle'>"


def _match_row_html(f: dict) -> str:
    home, away = f.get("strHomeTeam") or "—", f.get("strAwayTeam") or "—"
    hs, aws = f.get("intHomeScore"), f.get("intAwayScore")
    score = f"{hs if hs is not None else 0}–{aws if aws is not None else 0}"
    status = _status_label(f.get("strStatusShort") or f.get("strStatus"),
                            f.get("intElapsed"), f.get("intExtraTime"))
    round_str = f.get("strRound") or ""
    round_html = (f"<div style='font-size:10px;color:#999;text-align:center;"
                  f"margin-top:2px'>{round_str}</div>") if round_str else ""

    return f"""
<div style="display:flex;align-items:center;justify-content:space-between;
            border:1px solid #dee2e6;border-radius:8px;padding:8px 14px;
            margin-bottom:6px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.06)">
  <div style="display:flex;align-items:center;flex:1;min-width:0">
    {_img(f.get("strHomeTeamBadge", ""), "right")}<span style="font-weight:600;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{home}</span>
  </div>
  <div style="display:flex;flex-direction:column;align-items:center;min-width:100px;padding:0 10px">
    <span style="font-size:17px;font-weight:700;color:#212529">{score}</span>
    <span style="font-size:11px;font-weight:700;color:#d32f2f">\U0001f534 {status}</span>
    {round_html}
  </div>
  <div style="display:flex;align-items:center;flex:1;min-width:0;justify-content:flex-end;text-align:right">
    <span style="font-weight:600;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap">{away}</span>{_img(f.get("strAwayTeamBadge", ""), "left")}
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.markdown("<h3 style='margin:0'>🔴 Live</h3>", unsafe_allow_html=True)
st.caption(
    "Every match being played right now, across all tracked leagues and the "
    "Champions/Europa/Conference League, grouped by league. Refreshes at "
    "most once a minute to keep API usage low — reopen or refresh the page "
    "for the latest."
)

_col_title, _col_btn = st.columns([5, 1])
with _col_btn:
    if st.button("🔄 Refresh", use_container_width=True):
        _fetch_live.clear()
        st.rerun()

try:
    _live_fixtures, _fetched_at = _fetch_live(_API_KEY)
except RuntimeError as e:
    st.error(f"Couldn't load live matches: {e}")
    st.stop()

st.caption(f"As of {_fetched_at.strftime('%H:%M:%S')} CET.")
st.divider()

if not _live_fixtures:
    st.info("No matches are currently being played.")
else:
    _by_league: dict[int, list[dict]] = {}
    for _f in _live_fixtures:
        _by_league.setdefault(_f.get("idLeague"), []).append(_f)

    _ordered_ids = sorted(_by_league, key=lambda lid: _LEAGUE_ORDER.get(lid, 10**9))
    _n_matches = len(_live_fixtures)
    st.markdown(
        f"**\U0001f534 {_n_matches} match{'es' if _n_matches != 1 else ''} live "
        f"right now, across {len(_ordered_ids)} league{'s' if len(_ordered_ids) != 1 else ''}.**"
    )

    for _lid in _ordered_ids:
        _matches = sorted(_by_league[_lid], key=lambda f: (f.get("dateEvent", ""), f.get("strTime", "")))
        _name = _LEAGUE_NAME.get(_lid) or _matches[0].get("strLeague") or f"League {_lid}"
        _flag_url = _LEAGUE_FLAG_URL.get(_lid, "")
        _emoji = _LEAGUE_EMOJI.get(_lid, "")
        _icon = (f"<img src='{_flag_url}' height='22' style='vertical-align:middle;"
                 f"margin-right:8px;border-radius:2px'>") if _flag_url else f"{_emoji} "
        st.markdown(f"<h4>{_icon}{_name}</h4>", unsafe_allow_html=True)
        st.markdown("".join(_match_row_html(f) for f in _matches), unsafe_allow_html=True)
