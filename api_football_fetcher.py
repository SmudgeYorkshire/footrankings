"""API-Football (v3.football.api-sports.io) client with file-based caching.

Normalizes API-Football's nested JSON into the site's flat field-naming
convention (strTeam, intHomeScore, dateEvent, etc.), so every downstream
consumer (simulator.py, ratings_manager.py, football_rankings.py, admin.py,
european.py) works against one consistent shape.

Endpoint reference (v3):
    Base URL : https://v3.football.api-sports.io
    Auth     : x-apisports-key header (not embedded in the URL)
"""

import hashlib
import json
import re
import sys
import time
import requests
from pathlib import Path
from typing import Optional

from config import (
    DEFAULT_API_FOOTBALL_KEY,
    CACHE_TTL_STANDINGS,
    CACHE_TTL_FIXTURES,
    CACHE_TTL_META,
    CACHE_TTL_HISTORICAL,
    CACHE_STALE_FALLBACK_MAX_AGE,
)

CACHE_DIR = Path("cache")
BASE_URL = "https://v3.football.api-sports.io"

_FINISHED_SHORT = {"FT", "AET", "PEN", "AWD", "WO"}  # AWD/WO: technical loss / walkover — final result, no further play


def _round_number(round_str: str) -> str:
    """'Regular Season - 12' -> '12'. Falls back to '0' if unparseable."""
    if not round_str:
        return "0"
    m = re.search(r"(\d+)\s*$", round_str)
    return m.group(1) if m else "0"


def _split_iso_datetime(iso: str) -> tuple[str, str]:
    """'2026-08-09T10:15:00+00:00' -> ('2026-08-09', '10:15:00')."""
    if not iso:
        return "", ""
    date_part, _, rest = iso.partition("T")
    return date_part, (rest[:8] if rest else "")


def _normalize_standing_row(row: dict) -> dict:
    team = row.get("team") or {}
    all_stats = row.get("all") or {}
    goals = all_stats.get("goals") or {}
    return {
        "intRank":           row.get("rank"),
        "strTeam":           team.get("name"),
        "strBadge":          team.get("logo"),
        "idTeam":            team.get("id"),
        "intPlayed":         all_stats.get("played"),
        "intWin":            all_stats.get("win"),
        "intDraw":           all_stats.get("draw"),
        "intLoss":           all_stats.get("lose"),
        "intGoalsFor":       goals.get("for"),
        "intGoalsAgainst":   goals.get("against"),
        "intGoalDifference": row.get("goalsDiff"),
        "intPoints":         row.get("points"),
        "strForm":           row.get("form"),
        "strDescription":    row.get("description"),
    }


def _normalize_fixture(fx: dict) -> dict:
    fixture = fx.get("fixture") or {}
    league = fx.get("league") or {}
    teams = fx.get("teams") or {}
    goals = fx.get("goals") or {}
    penalty = (fx.get("score") or {}).get("penalty") or {}
    status = fixture.get("status") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    date_part, time_part = _split_iso_datetime(fixture.get("date", ""))

    status_short = status.get("short")
    if status_short in _FINISHED_SHORT:
        norm_status = "FT"
    else:
        norm_status = status_short or ""

    return {
        "idEvent":          str(fixture.get("id")),
        "strHomeTeam":      home.get("name"),
        "strAwayTeam":      away.get("name"),
        "strHomeTeamBadge": home.get("logo"),
        "strAwayTeamBadge": away.get("logo"),
        "intHomeScore":     goals.get("home"),
        "intAwayScore":     goals.get("away"),
        "intPenaltyHome":   penalty.get("home"),
        "intPenaltyAway":   penalty.get("away"),
        "strStatus":        norm_status,
        "dateEvent":        date_part,
        "strTime":          time_part,
        "intRound":         _round_number(league.get("round", "")),
        "strRound":         league.get("round"),
        "strLeague":        league.get("name"),
    }


class ApiFootballClient:
    def __init__(self, api_key: str = DEFAULT_API_FOOTBALL_KEY):
        self.api_key = api_key
        CACHE_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_league_info(self, league_id: int) -> dict:
        data = self._cached_get(
            "leagues", {"id": league_id},
            cache_key=f"af_league_{league_id}", ttl=CACHE_TTL_META,
        )
        resp = (data or {}).get("response") or []
        if not resp:
            return {}
        league = resp[0].get("league") or {}
        return {
            "strBadge": league.get("logo"),
            "strLogo": league.get("logo"),
            "strLeague": league.get("name"),
        }

    def get_standings(self, league_id: int, season) -> list[dict]:
        """Full team roster (name + badge) for the league. For split-format
        leagues, API-Football returns MULTIPLE standings groups (one per
        conference) once the split has happened — this unions every group
        so no team silently disappears from the roster after a split.
        Per-group stats aren't meaningful here anyway: this is only ever
        used to seed compute_full_standings(), which zeroes and rebuilds
        every stat from actual fixture results."""
        groups = self.get_standings_groups(league_id, season)
        seen: dict[str, dict] = {}
        for group in groups:
            for norm in group:
                name = norm.get("strTeam")
                if name and name not in seen:
                    seen[name] = norm
        return list(seen.values())

    def get_standings_groups(self, league_id: int, season, ttl: int = CACHE_TTL_STANDINGS) -> list[list[dict]]:
        """Per-conference standings groups as API-Football returns them
        (a single group for non-split leagues), each already normalized to
        our row shape. Every group is independently and correctly ranked by
        the provider — safe to trust directly for historical/settled
        seasons (no live-lag risk once a season is finished)."""
        af_season = self._season_year(season)
        data = self._cached_get(
            "standings", {"league": league_id, "season": af_season},
            cache_key=f"af_table_{league_id}_{af_season}", ttl=ttl,
        )
        resp = (data or {}).get("response") or []
        if not resp:
            return []
        try:
            groups = resp[0]["league"]["standings"] or []
        except (KeyError, IndexError):
            return []
        return [[_normalize_standing_row(row) for row in group] for group in groups]

    def get_fixtures(self, league_id: int, season, ttl: int = CACHE_TTL_FIXTURES) -> tuple[list[dict], list[dict]]:
        af_season = self._season_year(season)
        data = self._cached_get(
            "fixtures", {"league": league_id, "season": af_season},
            cache_key=f"af_fixtures_{league_id}_{af_season}", ttl=ttl,
        )
        resp = (data or {}).get("response") or []

        played, remaining = [], []
        for fx in resp:
            norm = _normalize_fixture(fx)
            score = norm["intHomeScore"]
            if score is None or score == "":
                remaining.append(norm)
            elif norm["strStatus"] != "FT":
                remaining.append(norm)
            else:
                played.append(norm)
        return played, remaining

    def get_teams(self, league_id: int, season, ttl: int = CACHE_TTL_META) -> dict[str, str]:
        """{team name: badge URL} for every team API-Football has already
        confirmed into this league/season -- populated as soon as a club is
        drawn in, well before it has played (or even been scheduled for) a
        fixture in the competition. Use this to fill in badges for clubs
        that get_fixtures()'s played/remaining lists don't cover yet, e.g.
        League Phase direct entrants before the League Phase draw/fixture
        list exists."""
        af_season = self._season_year(season)
        data = self._cached_get(
            "teams", {"league": league_id, "season": af_season},
            cache_key=f"af_teams_{league_id}_{af_season}", ttl=ttl,
        )
        resp = (data or {}).get("response") or []
        lookup: dict[str, str] = {}
        for row in resp:
            team = row.get("team") or {}
            name, logo = team.get("name"), team.get("logo")
            if name and logo:
                lookup[name] = logo
        return lookup

    def get_live_fixtures(self, league_ids: list[int], ttl: int = CACHE_TTL_FIXTURES) -> list[dict]:
        """Every fixture currently in-play across the given leagues, in a
        single request — API-Football's `live` filter takes a dash-joined
        list of league IDs, so tracking dozens of leagues still costs one
        call instead of one per league. Adds intElapsed/intExtraTime/
        idLeague on top of the normal normalized fixture shape, since those
        only matter for in-play matches."""
        ids_param = "-".join(str(i) for i in sorted(set(league_ids)))
        # Keyed by a short hash of the exact league set, not a fixed name —
        # two calls with different league sets within the same TTL window
        # must not silently share (and overwrite) one cache entry.
        ids_digest = hashlib.sha1(ids_param.encode()).hexdigest()[:16]
        data = self._cached_get(
            "fixtures", {"live": ids_param},
            cache_key=f"af_live_{ids_digest}", ttl=ttl,
        )
        resp = (data or {}).get("response") or []
        fixtures = []
        for fx in resp:
            norm = _normalize_fixture(fx)
            status = (fx.get("fixture") or {}).get("status") or {}
            norm["intElapsed"] = status.get("elapsed")
            norm["intExtraTime"] = status.get("extra")
            norm["strStatusShort"] = status.get("short")
            norm["idLeague"] = (fx.get("league") or {}).get("id")
            fixtures.append(norm)
        return fixtures

    def get_available_seasons(self, league_id: int) -> list[int]:
        """Past season years (excludes the current/in-progress one) this
        league has fixture data for, most recent first. Cached long-term —
        a league's historical season list barely ever changes."""
        data = self._cached_get(
            "leagues", {"id": league_id},
            cache_key=f"af_league_{league_id}", ttl=CACHE_TTL_HISTORICAL,
        )
        resp = (data or {}).get("response") or []
        if not resp:
            return []
        seasons = resp[0].get("seasons") or []
        return sorted(
            (s["year"] for s in seasons if not s.get("current")),
            reverse=True,
        )

    def invalidate_cache(self, league_id: int, season):
        af_season = self._season_year(season)
        for key in [f"af_table_{league_id}_{af_season}", f"af_fixtures_{league_id}_{af_season}"]:
            (CACHE_DIR / f"{key}.json").unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _season_year(season) -> int:
        """Accept either an int year (explicit config override, needed for
        leagues whose API-Football 'current' season doesn't line up with
        the site's start-year convention) or a "YYYY-YYYY" / "YYYY"
        season string, truncated to its start year."""
        if isinstance(season, int):
            return season
        return int(str(season)[:4])

    def _cached_get(self, endpoint: str, params: dict, cache_key: str, ttl: int) -> Optional[dict]:
        cache_path = CACHE_DIR / f"{cache_key}.json"

        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < ttl:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)

        try:
            resp = requests.get(
                f"{BASE_URL}/{endpoint}",
                headers={"x-apisports-key": self.api_key},
                params=params, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            # API-Football sometimes returns HTTP 200 with an empty result
            # set AND a populated "errors" field reporting an outage on
            # their end (e.g. {"bug": "This is on our side...", "error":
            # "5xEr"}) -- raise_for_status() doesn't catch this since the
            # HTTP status itself is 200. Left unchecked, that "successful"
            # empty response gets cached and served as if it were
            # genuinely zero fixtures/standings, silently zeroing out
            # every downstream table instead of erroring or falling back.
            if isinstance(data, dict) and data.get("errors"):
                raise RuntimeError(f"API-Football returned an error payload: {data['errors']}")
        except (requests.RequestException, ValueError, RuntimeError) as e:
            if cache_path.exists():
                fallback_age = time.time() - cache_path.stat().st_mtime
                if fallback_age <= CACHE_STALE_FALLBACK_MAX_AGE:
                    print(
                        f"[api_football_fetcher] WARNING: live request for "
                        f"{cache_key!r} failed ({e}); serving cached fallback "
                        f"{fallback_age:.0f}s old.",
                        file=sys.stderr,
                    )
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                raise RuntimeError(
                    f"API-Football request for {cache_key!r} failed ({e}) and "
                    f"the cached fallback is {fallback_age / 60:.0f} min old, "
                    f"past the {CACHE_STALE_FALLBACK_MAX_AGE / 60:.0f} min "
                    f"limit — refusing to silently serve stale data"
                ) from e
            raise RuntimeError(f"API-Football request failed: {e}") from e

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
