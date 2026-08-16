"""
Tests for api_football_fetcher.py's caching layer — no real network calls
(requests.get is mocked throughout). Covers the two bugs fixed in this
pass: silently-unbounded stale-cache fallback, and the live-fixtures
cache key collapsing different league sets into one entry.
"""

import json
import time
from unittest.mock import patch, MagicMock

import pytest

import api_football_fetcher as aff
from api_football_fetcher import ApiFootballClient
import config


@pytest.fixture()
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(aff, "CACHE_DIR", tmp_path)
    return tmp_path


def _client():
    return ApiFootballClient(api_key="test-key")


def _mock_response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = __import__("requests").HTTPError(f"{status} error")
    else:
        resp.raise_for_status.side_effect = None
    return resp


def test_cached_get_writes_and_reads_disk_cache(isolated_cache_dir):
    client = _client()
    with patch("api_football_fetcher.requests.get", return_value=_mock_response({"response": [1, 2, 3]})) as mock_get:
        data = client._cached_get("fixtures", {"league": 1}, cache_key="k1", ttl=60)
    assert data == {"response": [1, 2, 3]}
    assert mock_get.call_count == 1

    # second call within TTL must not hit the network again
    with patch("api_football_fetcher.requests.get") as mock_get2:
        data2 = client._cached_get("fixtures", {"league": 1}, cache_key="k1", ttl=60)
    assert data2 == {"response": [1, 2, 3]}
    mock_get2.assert_not_called()


def test_cached_get_falls_back_to_recent_stale_cache_on_failure(isolated_cache_dir):
    cache_path = isolated_cache_dir / "k2.json"
    cache_path.write_text(json.dumps({"response": ["stale"]}))
    client = _client()

    with patch("api_football_fetcher.requests.get", side_effect=__import__("requests").ConnectionError("boom")):
        data = client._cached_get("fixtures", {}, cache_key="k2", ttl=60)
    assert data == {"response": ["stale"]}


def test_cached_get_refuses_to_serve_cache_older_than_the_stale_limit(isolated_cache_dir):
    """Regression test: this used to serve arbitrarily-old cache data
    forever on any request failure, with no signal anything was wrong."""
    cache_path = isolated_cache_dir / "k3.json"
    cache_path.write_text(json.dumps({"response": ["ancient"]}))
    old_time = time.time() - (config.CACHE_STALE_FALLBACK_MAX_AGE + 60)
    import os
    os.utime(cache_path, (old_time, old_time))

    client = _client()
    with patch("api_football_fetcher.requests.get", side_effect=__import__("requests").ConnectionError("boom")):
        with pytest.raises(RuntimeError, match="refusing to silently serve stale data"):
            client._cached_get("fixtures", {}, cache_key="k3", ttl=60)


def test_cached_get_raises_when_no_fallback_exists(isolated_cache_dir):
    client = _client()
    with patch("api_football_fetcher.requests.get", side_effect=__import__("requests").ConnectionError("boom")):
        with pytest.raises(RuntimeError):
            client._cached_get("fixtures", {}, cache_key="never-cached", ttl=60)


def test_get_live_fixtures_uses_different_cache_keys_for_different_league_sets(isolated_cache_dir):
    """Regression test: get_live_fixtures used a fixed cache_key regardless
    of which leagues were requested, so two different league sets queried
    within the same TTL window would silently share one cache entry."""
    client = _client()

    call_keys = []
    real_cached_get = client._cached_get

    def spy(endpoint, params, cache_key, ttl):
        call_keys.append(cache_key)
        return real_cached_get(endpoint, params, cache_key, ttl)

    with patch("api_football_fetcher.requests.get", return_value=_mock_response({"response": []})):
        with patch.object(client, "_cached_get", side_effect=spy):
            client.get_live_fixtures([1, 2, 3])
            client.get_live_fixtures([4, 5, 6])

    assert len(set(call_keys)) == 2, f"expected 2 distinct cache keys, got {call_keys}"


def test_normalize_fixture_treats_awd_and_wo_as_finished():
    """Regression test: technical-loss/walkover results have a real final
    score but weren't recognized as finished, so get_fixtures() routed
    them into 'remaining' instead of 'played'."""
    for short_status in ("AWD", "WO"):
        fx = {
            "fixture": {"id": 1, "date": "2026-08-01T18:00:00+00:00", "status": {"short": short_status}},
            "league": {"round": "Regular Season - 1"},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
            "goals": {"home": 3, "away": 0},
            "score": {"penalty": {}},
        }
        norm = aff._normalize_fixture(fx)
        assert norm["strStatus"] == "FT", f"{short_status} should normalize to FT"
