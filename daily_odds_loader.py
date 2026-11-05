"""
Shared reader for fetch_daily_odds.py's output (odds_coverage/daily_odds/
{date}.json), extracted from club_rating_calibration.py so it can also be
called from simulator.py without a circular import -- club_rating_
calibration.py itself imports fixture_odds FROM simulator.py, so simulator.py
can never import anything back from club_rating_calibration.py.

load_windowed_observations() is byte-for-byte the same pooling/dedup logic
club_rating_calibration.py always used (moved, not rewritten): pool every
api_football observation from the trailing window_days calendar days ending
at end_date, keeping only the freshest capture of each real-world fixture.
The one behavior difference from the original is deliberate, not an
oversight -- it never exits the process when no odds files exist in the
window; it simply returns an empty list. club_rating_calibration.py's own
CLI still wants a hard, noisy failure when it has nothing to fit from (see
its own _load_windowed_observations wrapper), but a live Streamlit page
building a same-match odds override should degrade gracefully to the
model's own lambdas instead of crashing the whole page.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path

DAILY_ODDS_DIR = Path("odds_coverage") / "daily_odds"

# Short in-process TTL cache (not functools.lru_cache -- that would never
# expire for a given (end_date, window_days) key, and "today" stays the
# same key all day, so a long-lived Streamlit process would keep serving
# pre-fetch_daily_odds.py-run content for the rest of the process's life
# once cached). Real need for this cache: a live page calling
# load_live_odds_for_league once per league/competition (e.g.
# european_2027_28.py, ~50 countries in one render) was re-reading and
# re-parsing the SAME up-to-7 JSON files from scratch every single call --
# confirmed live 2026-11-05 as the actual cause of that page timing out
# after this module was wired in. 300s comfortably covers one page
# render without risking stale-for-long odds data.
_CACHE_TTL_SECONDS = 300
_window_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}


def daily_odds_files_exist(end_date: str, window_days: int) -> bool:
    """True if at least one odds_coverage/daily_odds/*.json file exists
    anywhere in the window_days calendar days ending at end_date."""
    end = date.fromisoformat(end_date)
    return any(
        (DAILY_ODDS_DIR / f"{(end - timedelta(days=offset)).isoformat()}.json").exists()
        for offset in range(window_days)
    )


def load_windowed_observations(end_date: str, window_days: int) -> list[dict]:
    """Pool api_football observations from the window_days calendar days
    ending at end_date (inclusive), keeping only the freshest capture of
    each real-world fixture (the odds closest to kickoff reflect the most
    information -- team news, latest market movement). Hard-filters to
    source == "api_football": window days from before the 2026-10-11 Odds
    API removal still have old "odds_api"-sourced rows mixed in on disk.
    Returns [] (never raises or exits) if no odds files exist in the
    window at all.

    Cached for _CACHE_TTL_SECONDS per (end_date, window_days) -- see that
    constant's own comment. Returns the SAME list object to every caller
    within the TTL window, so a caller must treat it as read-only."""
    cache_key = (end_date, window_days)
    cached = _window_cache.get(cache_key)
    if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    end = date.fromisoformat(end_date)
    # Oldest day first, so a later day's capture of the same fixture
    # overwrites an earlier one -- "freshest capture wins".
    by_fixture: dict[tuple, dict] = {}
    for offset in range(window_days - 1, -1, -1):
        d = (end - timedelta(days=offset)).isoformat()
        path = DAILY_ODDS_DIR / f"{d}.json"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            day_obs = json.load(f)
        for o in day_obs:
            if o.get("source") != "api_football":
                continue
            key = (o.get("league"), o.get("home_team"), o.get("away_team"))
            by_fixture[key] = o
    result = list(by_fixture.values())
    _window_cache[cache_key] = (time.monotonic(), result)
    return result


def load_live_odds_for_league(
    league_name: str, as_of_date: str | None = None, window_days: int = 7,
) -> dict[tuple[str, str], dict]:
    """{(home_team, away_team): {home_prob, draw_prob, away_prob,
    bookmaker_count}} for one tracked league or European competition's
    name, exactly as fetch_daily_odds.py/_LEAGUE_ID_TO_NAME tags it.

    window_days=7 matches fetch_daily_odds.py's own forward lookahead
    (--days 7) -- long enough that a single missed day's fetch run still
    gets the freshest available capture for every fixture that's still
    within that window, short enough it never pulls in oddsfor a fixture
    far enough out that fetch_daily_odds.py itself has no real coverage
    for yet (see that module's own docstring)."""
    as_of = as_of_date or date.today().isoformat()
    observations = load_windowed_observations(as_of, window_days)
    return {
        (o["home_team"], o["away_team"]): {
            "home_prob": o["home_prob"], "draw_prob": o["draw_prob"],
            "away_prob": o["away_prob"], "bookmaker_count": o.get("bookmaker_count", 0),
        }
        for o in observations if o.get("league") == league_name
    }
