"""
Live cup-winner cascade resolver.

Replaces config.py's static, hand-maintained team_status_overrides with a
value computed fresh from live data: which team is currently predicted to
win this country's domestic cup, where that team is projected to finish in
the league, and whether their cup-winner Status slot (from
entrants_2027_28.cup_winner_status) actually improves on what their
projected table position already gives them. If it doesn't, the extra slot
cascades down to the first team not already covered by a real zone or
multi-team play-off -- the exact logic this project's hand-applied fixes
have followed all session (Ireland, Montenegro, Moldova, Turkey, ...), now
run on every page load instead of needing a manual re-check every time a
prediction or table position shifts.

Falls back to {} (not an exception) on any missing data -- a missing cup_id,
empty ratings, a fetch failure, or a country with no CW slot in the access
list are all legitimate "nothing to show" cases, not bugs.
"""

import re

import pandas as pd

from cup_predictions import resolve_predicted_cup_winner, fetch_cup_fixtures, _team_name_set
from entrants_2027_28 import cup_winner_status
from simulator import simulate_season
from update_ratings_from_opta import _normalize

_COMP_RANK = {"UCL": 3, "UEL": 2, "UECL": 1}
_ROUND_RANK = {"LS": 6, "PO": 5, "QR3": 4, "QR2": 3, "QR1": 2}
_LABEL_RE = re.compile(r"^(UCL|UEL|UECL)\s*-\s*(LS|PO|QR3|QR2|QR1)")


def _parse_tier(label: str | None) -> tuple[int, int] | None:
    """(competition_rank, round_rank) for a "UCL - QR2 (LP)"-style label,
    comparable via normal tuple ordering (higher = better). None for
    anything that isn't a real UCL/UEL/UECL zone label (relegation spots,
    "Championship Group" placeholders, etc.)."""
    if not label:
        return None
    m = _LABEL_RE.match(label.strip())
    if not m:
        return None
    comp, rnd = m.groups()
    return (_COMP_RANK[comp], _ROUND_RANK[rnd])


def _playoff_claimed_positions(cfg: dict) -> set[int]:
    """Overall table positions already spoken for by a multi-team play-off
    mechanism (these don't show up as plain {pos: label} zone entries, but
    the position is still "claimed" -- a cup-winner cascade shouldn't land
    on a team that's already in line for a different European route)."""
    claimed: set[int] = set()
    for key in ("uecl_3team_playoff", "uecl_4team_playoff", "uecl_5team_playoff"):
        pcfg = cfg.get(key)
        if not pcfg:
            continue
        for k, v in pcfg.items():
            if k.endswith("_rank") and isinstance(v, int):
                claimed.add(v)
    if cfg.get("uecl_8team_playoff"):
        # Same position set football_rankings.py's own San Marino renderer
        # uses (_u8_roles) -- the only league with this exact mechanism.
        claimed |= {2, 3, 5, 6, 7, 8, 9, 10, 11, 12}
    cm = cfg.get("champ_mid_playoff")
    if cm and isinstance(cm.get("champ_pos"), int):
        claimed.add(cm["champ_pos"])
    return claimed


def _match_live_name(candidates: set[str], ranked_teams: list[str]) -> tuple[int, str] | None:
    """(1-indexed position, live team name) for the first ranked_teams entry
    matching one of `candidates` (ratings-file team/alias strings) -- exact
    match first, normalized match as a fallback for cases like "Ferencváros"
    (ratings) vs "Ferencvarosi TC" (live provider)."""
    for i, t in enumerate(ranked_teams, 1):
        if t in candidates:
            return i, t
    norm_candidates = {_normalize(c) for c in candidates}
    for i, t in enumerate(ranked_teams, 1):
        if _normalize(t) in norm_candidates:
            return i, t
    return None


def _first_unclaimed(ranked_teams: list[str], claimed: set[int], exclude: frozenset[str] = frozenset()) -> str | None:
    for i, t in enumerate(ranked_teams, 1):
        if i in claimed or t in exclude:
            continue
        return t
    return None


def resolve_live_overrides(league_name: str, cfg: dict, standings: list[dict],
                            played_fixtures: list[dict], remaining_fixtures: list[dict],
                            ratings_df: pd.DataFrame, zones: dict[int, str],
                            api_key: str, n_sim: int = 3_000) -> dict[str, str]:
    """{team_name: "STATUS*"} for this league's cup-winner cascade, resolved
    live -- see module docstring. zones should be whichever {pos: label}
    dict actually reflects real UCL/UEL/UECL zones for this league/phase
    (the "regular"-phase spot zones for a non-split league, or the "champ"
    zones treated as overall rank 1..n for a split one -- the same
    pragmatic approximation this project's manual fixes used all session,
    since fully simulating post-split brackets is a much larger project)."""
    cup_id = cfg.get("cup_id")
    country = cfg.get("country")
    if not cup_id or not country or ratings_df is None or ratings_df.empty:
        return {}

    cw_status = cup_winner_status(country)
    if not cw_status:
        return {}
    cw_tier = _parse_tier(cw_status)
    if cw_tier is None:
        return {}

    season = cfg.get("cup_af_seasons", {}).get(cup_id, cfg.get("af_season"))
    try:
        cup_played, cup_remaining = fetch_cup_fixtures(cup_id, season, api_key)
    except Exception:
        return {}

    try:
        predicted_row, _predicted_status, _skipped = resolve_predicted_cup_winner(
            ratings_df, cup_played, cup_remaining, home_advantage=cfg.get("home_advantage", 1.0)
        )
    except Exception:
        return {}
    if predicted_row is None:
        return {}

    try:
        probs = simulate_season(
            standings, remaining_fixtures, ratings_df, n_sim=n_sim,
            home_advantage=cfg.get("home_advantage", 1.0),
            tiebreakers=cfg.get("tiebreakers"), played_fixtures=played_fixtures,
        )
    except Exception:
        return {}
    if probs is None or probs.empty:
        return {}

    pos_nums = pd.Series({c: int(c) for c in probs.columns})
    expected_rank = probs.mul(pos_nums, axis=1).sum(axis=1)
    ranked_teams = expected_rank.sort_values(ascending=True).index.tolist()

    match = _match_live_name(_team_name_set(predicted_row), ranked_teams)
    if match is None:
        return {}
    cw_pos, cw_live_name = match

    claimed = set(zones.keys()) | _playoff_claimed_positions(cfg)
    natural_label = zones.get(cw_pos)
    natural_tier = _parse_tier(natural_label)

    overrides: dict[str, str] = {}
    if natural_tier is None:
        # No deterministic zone at the cup winner's projected position
        # (genuinely below every zone, or only in an uncertain multi-team
        # play-off pool) -- guarantee them the cup-winner slot directly
        # rather than leaving it to a play-off's probabilistic outcome.
        overrides[cw_live_name] = f"{cw_status}*"
    elif natural_tier >= cw_tier:
        # Their own projected position already matches or beats the
        # cup-winner slot -- no override needed for them; the extra slot
        # passes to the first team with no zone or play-off claim at all.
        target = _first_unclaimed(ranked_teams, claimed)
        if target:
            overrides[target] = f"{cw_status}*"
    else:
        # Cup-winner slot beats their natural zone -- upgrade them
        # directly, and their vacated natural zone cascades down.
        overrides[cw_live_name] = f"{cw_status}*"
        target = _first_unclaimed(ranked_teams, claimed, exclude=frozenset({cw_live_name}))
        if target:
            overrides[target] = f"{natural_label}*"

    return overrides
