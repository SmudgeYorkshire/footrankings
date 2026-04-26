"""TheSportsDB API client with file-based caching.

Endpoint reference (v1 free / paid):
    Base URL : https://www.thesportsdb.com/api/v1/json/{key}/
    Auth     : API key embedded in URL path

Free demo key "3" returns limited rows (5 standings, 15 fixtures).
Single Developer ($9/mo) key returns full data for all leagues.

All responses are normalised to the same internal field names used
throughout this project (simulator.py, ratings_manager.py, app.py).
"""

import json
import time
import requests
from pathlib import Path
from typing import Optional

from config import (
    DEFAULT_API_KEY,
    CACHE_TTL_STANDINGS,
    CACHE_TTL_FIXTURES,
    CACHE_TTL_META,
)

CACHE_DIR = Path("cache")
BASE_URL = "https://www.thesportsdb.com/api/v1/json"


class SportsDBClient:
    def __init__(self, api_key: str = DEFAULT_API_KEY):
        self.api_key = api_key
        CACHE_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_league_info(self, league_id: int) -> dict:
        """Return league metadata including badge/logo URL."""
        data = self._cached_get(
            f"lookupleague.php?id={league_id}",
            cache_key=f"league_{league_id}",
            ttl=CACHE_TTL_META,
        )
        if not data or not data.get("leagues"):
            return {}
        return data["leagues"][0]

    def get_standings(self, league_id: int, season: str) -> list[dict]:
        """Return current league table as a list of normalised row dicts."""
        data = self._cached_get(
            f"lookuptable.php?l={league_id}&s={season}",
            cache_key=f"table_{league_id}_{season}",
            ttl=CACHE_TTL_STANDINGS,
        )
        if not data or not data.get("table"):
            return []
        return data["table"]

    def get_fixtures(self, league_id: int, season: str) -> tuple[list[dict], list[dict]]:
        """
        Return (played_fixtures, remaining_fixtures) for the season.
        Remaining = events where intHomeScore is null/empty.
        Committed fixture patches in presplit/fixture_patches.json override
        API results (e.g. when the API lags behind with live/2H status).
        """
        data = self._cached_get(
            f"eventsseason.php?id={league_id}&s={season}",
            cache_key=f"fixtures_{league_id}_{season}",
            ttl=CACHE_TTL_FIXTURES,
        )
        if not data or not data.get("events"):
            return [], []

        # Apply committed fixture patches (overrides stale API status)
        _patch_file = Path("presplit/fixture_patches.json")
        _patch_key  = f"{league_id}_{season}"
        if _patch_file.exists():
            try:
                with open(_patch_file) as _pf:
                    _all_patches = json.load(_pf)
                _patches = _all_patches.get(_patch_key, [])
                if _patches:
                    # Index API events by (home, away, date) for fast lookup
                    _event_idx: dict[tuple, int] = {}
                    for _i, _ev in enumerate(data["events"]):
                        _k = (
                            _ev.get("strHomeTeam", ""),
                            _ev.get("strAwayTeam", ""),
                            _ev.get("dateEvent", ""),
                        )
                        _event_idx[_k] = _i
                    for _p in _patches:
                        _k = (_p.get("strHomeTeam", ""), _p.get("strAwayTeam", ""), _p.get("dateEvent", ""))
                        if _k in _event_idx:
                            data["events"][_event_idx[_k]].update(_p)
                        else:
                            data["events"].append(_p)
            except Exception:
                pass

        _FINISHED = {"Match Finished", "FT", "AOT", "AET", "AP"}
        played, remaining = [], []
        for event in data["events"]:
            score = event.get("intHomeScore")
            status = (event.get("strStatus") or "").strip()
            if score is None or score == "":
                remaining.append(event)
            elif status and status not in _FINISHED:
                # Score exists but status says not finished (live, HT, in-progress, etc.)
                remaining.append(event)
            else:
                # Score exists and status confirms finished, or no status (historical match)
                played.append(event)

        return played, remaining

    def invalidate_cache(self, league_id: int, season: str):
        """Force re-fetch of standings and fixtures for a league/season."""
        for key in [f"table_{league_id}_{season}", f"fixtures_{league_id}_{season}"]:
            path = CACHE_DIR / f"{key}.json"
            path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cached_get(self, endpoint: str, cache_key: str, ttl: int) -> Optional[dict]:
        cache_path = CACHE_DIR / f"{cache_key}.json"

        # Return cached value if still fresh
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < ttl:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)

        url = f"{BASE_URL}/{self.api_key}/{endpoint}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            body = resp.text.strip()
            if not body:
                return None
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            # Fall back to stale cache rather than crashing
            if cache_path.exists():
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            raise RuntimeError(f"API request failed: {e}") from e

        # Persist to cache
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        return data
