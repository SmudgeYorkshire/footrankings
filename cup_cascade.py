"""
Live cup-winner cascade resolver.

Replaces config.py's static, hand-maintained team_status_overrides with a
value computed fresh from live data: which team is currently predicted to
win this country's domestic cup(s), where that team is projected to finish
in the league, and whether their cup-winner Status slot (from
access_list_permutations_2027_28.cup_winner_status -- the permutation-
applied access list, not entrants_2027_28's untouched default) actually
improves on what their projected table position already gives them. If it
doesn't, the extra slot cascades down to the first team not already covered
by a real zone or multi-team play-off -- the exact logic this project's
hand-applied fixes have followed all session (Ireland, Montenegro, Moldova,
Turkey, ...), now run on every page load instead of needing a manual
re-check every time a prediction or table position shifts.

Multiple cups (cfg["cup_id"] plus cfg.get("extra_cup_ids", [])) are each
resolved in turn against a SHARED, growing `claimed` set of positions --
confirmed as a real gap 2026-10-13 (England): with only cfg["cup_id"] (the
FA Cup) ever read, the League Cup's own cascade was never computed at all,
and the one cascade that did run landed on whichever position happened to
be first unclaimed overall rather than the next one in priority order after
the FA Cup's own cascade. Resolving cups one at a time and feeding each
cup's claimed position(s) into the next keeps cascades sequential: the
first cup's extra slot takes the next open position, the second cup's takes
the one after that, rather than each starting from the same claimed set and
potentially landing on the exact same spot (or skipping straight past the
other cup's slot to some unrelated position further down).

A second cup's own reserved status (e.g. England's League Cup -> UECL - PO)
has no equivalent in access_list_permutations_2027_28.cup_winner_status,
which only reads the single "CW" (Cup Winner) route the 2027/28 access-list
data models -- England's League Cup route doesn't appear there at all (it's
a this-season-only extra route, not part of next season's planning), so a
second cup's status is read from cfg["extra_cup_status"] (keyed by cup id)
instead, set explicitly per league rather than derived.

simulate_season here is now deterministically seeded (simulator.
seed_from_key, same mechanism as the Predictions tab's own cache) from
"what actually determines this result" -- before this it used a fresh
OS-entropy seed on every call, so which team happened to catch a cascade
slot near the cutoff could flicker between page loads from pure Monte Carlo
sampling noise alone, even with nothing about the real standings or
predictions having changed (confirmed as a real issue 2026-10-13: the same
call returned a different team across two runs seconds apart with
unchanged input data).

Falls back to {} (not an exception) on any missing data -- a missing cup_id,
empty ratings, a fetch failure, or a country with no CW slot in the access
list are all legitimate "nothing to show" cases, not bugs.
"""

import re

import pandas as pd

from cup_predictions import resolve_predicted_cup_winner, fetch_cup_fixtures, _team_name_set
from access_list_permutations_2027_28 import cup_winner_status
from simulator import simulate_season, seed_from_key
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


def _effective_claimed(zones: dict[int, str], cfg: dict) -> set[int]:
    """Positions treated as already spoken for before any cup cascade
    runs -- cup_cascade's own starting `claimed` set, before
    _playoff_claimed_positions is added on top.

    For a league with extra_cup_ids (more domestic cup competitions than
    league_status.py's own data models for -- currently only England,
    whose League Cup route has no equivalent anywhere in
    access_list_permutations_2027_28's data at all, see this module's own
    docstring), the TRAILING non-UCL zone entries -- as many of them as
    there are extra cups -- are excluded here rather than claimed
    outright: that's where those extra cups' own slots belong once
    resolved, confirmed directly 2026-10-13 against TWO separate
    worked examples (both cup winners already in the Champions League
    zone): "5th and 6th should be UEL, 7th UECL - PO" at the 4-UCL
    baseline, "6th and 7th UEL, 8th UECL - PO" once the 5th Champions
    League spot applied -- in both, only ONE non-UCL position (the
    natural UEL one) stayed fixed; the next one down was NOT a second,
    independent, untouchable route, it was simply where the cascade
    landed once the first one did.

    Treating league_status.py's trailing "...UECL - PO" entry as already
    claimed -- which a plain `set(zones.keys())` does -- was exactly the
    bug: it's generated from entrants_2027_28.ACCESS_LIST_2027_28, which
    has no concept of England's second, this-season-only cup route at
    all, so that entry is only really valid as a label in the simplest
    case (neither cup winner redundant). Treating it as a hard claim made
    a cascade skip past it to some unrelated further-down position instead
    of being allowed to flow into it, the same way a league with only one
    cup already correctly lets a cascade claim its own single trailing
    non-UCL position.

    Every other league's zones entries (no extra_cup_ids) stay fully
    claimed exactly as before -- this function is a no-op for them."""
    n_extra = len(cfg.get("extra_cup_ids", []))
    if n_extra == 0:
        return set(zones.keys())
    non_ucl_positions = sorted(
        pos for pos, label in zones.items()
        if (tier := _parse_tier(label)) is not None and tier[0] != _COMP_RANK["UCL"]
    )
    keep = max(0, len(non_ucl_positions) - n_extra)
    excluded = set(non_ucl_positions[keep:])
    return set(zones.keys()) - excluded


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


def _first_unclaimed(ranked_teams: list[str], claimed: set[int],
                      exclude: frozenset[str] = frozenset()) -> tuple[int, str] | None:
    for i, t in enumerate(ranked_teams, 1):
        if i in claimed or t in exclude:
            continue
        return i, t
    return None


def _resolve_one_cup(cup_id, cw_status: str, cfg: dict, ratings_df: pd.DataFrame,
                      ranked_teams: list[str], zones: dict[int, str], claimed: set[int],
                      api_key: str) -> dict[str, str]:
    """Cascade logic for ONE domestic cup. Mutates `claimed` in place with
    whichever position(s) this cup's resolution ends up using, so a second
    cup resolved right after this one won't land on the same spot -- see
    resolve_live_overrides and this module's own docstring for why cascades
    need to stack sequentially."""
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

    match = _match_live_name(_team_name_set(predicted_row), ranked_teams)
    if match is None:
        return {}
    cw_pos, cw_live_name = match

    natural_label = zones.get(cw_pos)
    natural_tier = _parse_tier(natural_label)

    overrides: dict[str, str] = {}
    if natural_tier is None:
        # No deterministic zone at the cup winner's projected position
        # (genuinely below every zone, or only in an uncertain multi-team
        # play-off pool) -- guarantee them the cup-winner slot directly
        # rather than leaving it to a play-off's probabilistic outcome.
        overrides[cw_live_name] = cw_status
        claimed.add(cw_pos)
    elif natural_tier >= cw_tier:
        # Their own projected position already matches or beats the
        # cup-winner slot -- no override needed for them; the extra slot
        # passes to the first team with no zone or play-off claim at all.
        target = _first_unclaimed(ranked_teams, claimed)
        if target:
            t_pos, t_name = target
            overrides[t_name] = cw_status
            claimed.add(t_pos)
    else:
        # Cup-winner slot beats their natural zone -- upgrade them
        # directly, and their vacated natural zone cascades down.
        overrides[cw_live_name] = cw_status
        claimed.add(cw_pos)
        target = _first_unclaimed(ranked_teams, claimed, exclude=frozenset({cw_live_name}))
        if target:
            t_pos, t_name = target
            overrides[t_name] = natural_label
            claimed.add(t_pos)

    return overrides


def resolve_live_overrides(league_name: str, cfg: dict, standings: list[dict],
                            played_fixtures: list[dict], remaining_fixtures: list[dict],
                            ratings_df: pd.DataFrame, zones: dict[int, str],
                            api_key: str, n_sim: int = 3_000) -> dict[str, str]:
    """{team_name: "STATUS"} for this league's cup-winner cascade(s),
    resolved live -- see module docstring. No "*" or other marker on the
    label itself (dropped 2026-10-13: it was reading as a parsing/display
    error rather than "derived live" and causing more confusion than it
    resolved -- a per-spot footnote explaining a live override may come
    back later, but as separate text below the table, not punctuation
    stuck on the label). zones should be whichever
    {pos: label} dict actually reflects real UCL/UEL/UECL zones for this
    league/phase (the "regular"-phase spot zones for a non-split league, or
    the "champ" zones treated as overall rank 1..n for a split one -- the
    same pragmatic approximation this project's manual fixes used all
    session, since fully simulating post-split brackets is a much larger
    project)."""
    country = cfg.get("country")
    if not country or ratings_df is None or ratings_df.empty:
        return {}

    cups: list[tuple[int, str]] = []
    primary_cup_id = cfg.get("cup_id")
    if primary_cup_id:
        primary_status = cup_winner_status(country)
        if primary_status:
            cups.append((primary_cup_id, primary_status))
    extra_status = cfg.get("extra_cup_status", {})
    for cid in cfg.get("extra_cup_ids", []):
        status = extra_status.get(cid)
        if status:
            cups.append((cid, status))
    if not cups:
        return {}

    # Deterministic seed from the inputs that actually determine this
    # result -- see module docstring.
    seed_key = (
        league_name, len(played_fixtures),
        tuple((r.get("strTeam"), r.get("intPoints"), r.get("intGoalDifference")) for r in standings),
    )
    try:
        probs = simulate_season(
            standings, remaining_fixtures, ratings_df, n_sim=n_sim,
            home_advantage=cfg.get("home_advantage", 1.0),
            tiebreakers=cfg.get("tiebreakers"), played_fixtures=played_fixtures,
            seed=seed_from_key(seed_key),
        )
    except Exception:
        return {}
    if probs is None or probs.empty:
        return {}

    pos_nums = pd.Series({c: int(c) for c in probs.columns})
    expected_rank = probs.mul(pos_nums, axis=1).sum(axis=1)
    ranked_teams = expected_rank.sort_values(ascending=True).index.tolist()

    claimed = _effective_claimed(zones, cfg) | _playoff_claimed_positions(cfg)
    overrides: dict[str, str] = {}
    for cup_id, cw_status in cups:
        new_overrides = _resolve_one_cup(cup_id, cw_status, cfg, ratings_df, ranked_teams, zones, claimed, api_key)
        for team, label in new_overrides.items():
            if team in overrides:
                # A double cup winner (rare, but has happened) -- keep
                # whichever tier is higher instead of letting the cup
                # processed later silently clobber the earlier one's label.
                existing_tier = _parse_tier(overrides[team])
                new_tier = _parse_tier(label)
                if existing_tier is not None and new_tier is not None and existing_tier >= new_tier:
                    continue
            overrides[team] = label

    return overrides
