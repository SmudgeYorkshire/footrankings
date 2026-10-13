"""
Live cup-winner cascade resolver.

Replaces config.py's static, hand-maintained team_status_overrides with a
value computed fresh from live data: which team is currently predicted to
win this country's domestic cup(s), where that team is projected to finish
in the league, and whether their cup-winner Status slot (from
access_list_permutations_2027_28.cup_winner_status -- the permutation-
applied access list, not entrants_2027_28's untouched default) actually
improves on what their projected table position already gives them.

If it doesn't (their own position already matches or beats the cup prize),
the prize is a redundant, vacant slot that cascades down the table: it's
inserted at the first position whose own zone is lower-tier (or has none at
all), and if that position already had its own real zone, THAT zone is in
turn carried one position further down the same way, chain-style, until it
reaches a position with nothing to carry (or is absorbed into an already-
cascaded position of equal-or-better tier from an earlier cup this round --
see _cascade_insert's own docstring). Confirmed against three worked
examples 2026-10-13: Italy's single-cup Coppa Italia case (Inter already in
the Champions League zone -> their Europa League prize upgrades the next
position down, 6th, whose own now-vacated Conference League zone is carried
to 7th) and England's two-cup case at both a 4-UCL and a 5-UCL (EPS bonus)
baseline (confirmed "5th and 6th UEL, 7th UECL - PO" and "6th and 7th UEL,
8th UECL - PO" respectively) -- the exact logic this project's hand-applied
fixes have followed all session (Ireland, Montenegro, Moldova, Turkey, ...),
now run on every page load instead of needing a manual re-check every time
a prediction or table position shifts.

Multiple cups (cfg["cup_id"] plus cfg.get("extra_cup_ids", [])) are each
resolved in turn against SHARED, growing `overrides`/`claimed` state --
confirmed as a real gap 2026-10-13 (England): with only cfg["cup_id"] (the
FA Cup) ever read, the League Cup's own cascade was never computed at all.
Resolving cups one at a time and feeding each cup's own placements into the
next keeps cascades sequential: the second cup's own redundant prize, if an
earlier cup's own chain already placed an equal-or-better tier at the
position it would have landed on, is treated as already accounted for and
places nothing further (confirmed directly against the England examples
above: two redundant cups there produce exactly two new positions, not a
third -- a plain "each cup independently finds its own first open slot"
model overshoots to a third, unconfirmed position instead).

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


def _set_override(overrides: dict[int, str], pos: int, label: str) -> None:
    """overrides[pos] = label, keeping whichever tier is higher if `pos`
    already has an override from an earlier cup this round (a double cup
    winner occupying the same position, rare but has happened) instead of
    letting the later write silently clobber the earlier one's label."""
    existing = overrides.get(pos)
    if existing is not None:
        existing_tier, new_tier = _parse_tier(existing), _parse_tier(label)
        if existing_tier is not None and new_tier is not None and existing_tier >= new_tier:
            return
    overrides[pos] = label


def _cascade_insert(ranked_teams: list[str], zones: dict[int, str],
                     overrides: dict[int, str], claimed: set[int],
                     label: str, tier: tuple[int, int],
                     exclude_pos: frozenset[int] = frozenset()) -> bool:
    """Places `label` (of `tier`) at the first POSITION whose EFFECTIVE zone
    -- an earlier cup's own override this round if it has one, else its
    plain natural zone from `zones` -- is lower-tier than `label` (or has
    none at all). If that position's own effective zone was real (not
    None), that displaced zone is carried one position further down the
    same way, recursively, chain-style, until a position with nothing to
    carry is reached.

    Keyed by POSITION, not by whichever team currently sits there (changed
    2026-10-13: an earlier team-keyed version looked up each row's status
    by team name regardless of what position that team was actually shown
    at, so a team that fell sharply out of contention after being resolved
    as a cascade target would keep displaying its old European-zone label
    wherever it now appeared -- e.g. Leeds still showing "UECL - PO" if a
    later run had them projected to finish 12th. Position-keying makes that
    structurally impossible: whichever team the display shows AT that
    position is the one the label applies to, full stop.)

    Stops immediately and places nothing (returns False) the moment the
    scan reaches a position an EARLIER cup already overrode this round
    whose tier already covers `tier`: that position's own cascade already
    represents an equal-or-better slot, so this cup's own redundant prize
    needs no separate placement of its own. Without this, two independently
    redundant cup winners would produce one cascaded position each (three
    total changed positions for two cups) instead of the confirmed-correct
    two total -- see this module's own docstring for the worked examples.

    A position genuinely reserved by a play-off mechanism
    (_playoff_claimed_positions, already in `claimed` with no override of
    its own) is skipped outright -- a different kind of reservation this
    chain doesn't touch, not a signal to stop or to carry anything into."""
    for pos, _team in enumerate(ranked_teams, 1):
        if pos in exclude_pos:
            continue
        cascaded_label = overrides.get(pos)
        effective_label = cascaded_label if cascaded_label is not None else zones.get(pos)
        effective_tier = _parse_tier(effective_label)
        if effective_tier is not None and effective_tier >= tier:
            if cascaded_label is not None:
                return False
            continue
        if pos in claimed:
            continue
        _set_override(overrides, pos, label)
        claimed.add(pos)
        if effective_label is not None:
            # Carry the displaced zone further, excluding the position we
            # just set -- otherwise the recursive scan would immediately
            # see this position's own brand-new (higher-tier) override and
            # mistake it for an EARLIER cup's cascade, stopping right here
            # instead of continuing the chain.
            _cascade_insert(ranked_teams, zones, overrides, claimed, effective_label, effective_tier,
                             exclude_pos=exclude_pos | {pos})
        return True
    return False


def _resolve_one_cup(cup_id, cw_status: str, cfg: dict, ratings_df: pd.DataFrame,
                      ranked_teams: list[str], zones: dict[int, str],
                      overrides: dict[int, str], claimed: set[int],
                      api_key: str) -> None:
    """Cascade logic for ONE domestic cup. Mutates `overrides` (keyed by
    POSITION, not team -- see _cascade_insert's own docstring for why) and
    `claimed` in place -- so a second cup resolved right after this one sees
    this one's own placements too, both for the growing claimed-position
    set and for _cascade_insert's "already covered by an earlier cup this
    round" check -- see resolve_live_overrides and this module's own
    docstring for why cascades need to stack sequentially."""
    cw_tier = _parse_tier(cw_status)
    if cw_tier is None:
        return

    season = cfg.get("cup_af_seasons", {}).get(cup_id, cfg.get("af_season"))
    try:
        cup_played, cup_remaining = fetch_cup_fixtures(cup_id, season, api_key)
    except Exception:
        return

    try:
        predicted_row, _predicted_status, _skipped = resolve_predicted_cup_winner(
            ratings_df, cup_played, cup_remaining, home_advantage=cfg.get("home_advantage", 1.0)
        )
    except Exception:
        return
    if predicted_row is None:
        return

    match = _match_live_name(_team_name_set(predicted_row), ranked_teams)
    if match is None:
        return
    cw_pos, _cw_live_name = match

    natural_label = zones.get(cw_pos)
    natural_tier = _parse_tier(natural_label)

    if natural_tier is None:
        # No deterministic zone at the cup winner's projected position
        # (genuinely below every zone, or only in an uncertain multi-team
        # play-off pool) -- guarantee them the cup-winner slot directly
        # rather than leaving it to a play-off's probabilistic outcome.
        _set_override(overrides, cw_pos, cw_status)
        claimed.add(cw_pos)
    elif natural_tier >= cw_tier:
        # Their own projected position already matches or beats the
        # cup-winner slot -- it's a redundant, vacant prize: insert it at
        # the first position it would improve on, carrying whatever real
        # zone that position already had further down in turn.
        _cascade_insert(ranked_teams, zones, overrides, claimed, cw_status, cw_tier)
    else:
        # Cup-winner slot beats their natural zone -- upgrade them
        # directly, and their vacated natural zone cascades down the same
        # chain-insert way.
        _set_override(overrides, cw_pos, cw_status)
        claimed.add(cw_pos)
        if natural_label is not None:
            _cascade_insert(ranked_teams, zones, overrides, claimed, natural_label, natural_tier,
                             exclude_pos=frozenset({cw_pos}))


def resolve_live_overrides(league_name: str, cfg: dict, standings: list[dict],
                            played_fixtures: list[dict], remaining_fixtures: list[dict],
                            ratings_df: pd.DataFrame, zones: dict[int, str],
                            api_key: str, n_sim: int = 3_000,
                            probs: pd.DataFrame | None = None) -> dict[int, str]:
    """{position: "STATUS"} for this league's cup-winner cascade(s),
    resolved live -- see module docstring. Keyed by table POSITION, not
    team name (changed 2026-10-13 -- see _cascade_insert's own docstring
    for the bug this fixes): merge this directly into whatever {pos: label}
    status_map the caller already passes to render_prob_table/_table_rows
    (e.g. status_map={**_main_zones, **these_overrides}), rather than
    passing it as a separate team_overrides= argument -- a team-keyed
    lookup would reapply a stale label wherever that team is NOW displayed,
    even if they've since moved far away from the position the cascade
    actually concerns. No "*" or other marker on the label itself (dropped
    2026-10-13: it was reading as a parsing/display error rather than
    "derived live" and causing more confusion than it resolved -- a
    per-spot footnote explaining a live override may come back later, but
    as separate text below the table, not punctuation stuck on the label).
    zones should be whichever
    {pos: label} dict actually reflects real UCL/UEL/UECL zones for this
    league/phase (the "regular"-phase spot zones for a non-split league, or
    the "champ" zones treated as overall rank 1..n for a split one -- the
    same pragmatic approximation this project's manual fixes used all
    session, since fully simulating post-split brackets is a much larger
    project).

    probs: an already-simulated {position: probability} DataFrame (same
    shape simulate_season returns) to rank teams from, instead of running a
    fresh, separately-seeded simulation here. Pass the EXACT DataFrame the
    Predictions tab itself displays (when one exists -- a non-split league
    only) so the cascade's choice of team can never disagree with what the
    table actually shows for a closely-matched pair. Confirmed as a real,
    reproducible bug 2026-10-13 (England, Man Utd vs Leeds): this
    function's own independent n_sim=3_000 run and the Predictions tab's
    cached 30_000-run simulation used different seeds and sample sizes, so
    for two teams separated by a fraction of an expected point they
    disagreed on which ranked higher -- the cascade awarded the slot to the
    team IT ranked just inside the cutoff, while the displayed table showed
    that team one row below where the slot's blank cell actually was.
    Falls back to running its own simulation (the pre-existing behavior)
    when not given, e.g. for a split league where no single full-table
    probs exists yet at this point in the page."""
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

    if probs is None or probs.empty:
        # No pre-computed probs given (split league, or no remaining
        # fixtures to simulate yet) -- fall back to this function's own
        # independent simulation, deterministically seeded from the inputs
        # that actually determine this result.
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

    claimed = _playoff_claimed_positions(cfg)
    overrides: dict[int, str] = {}
    for cup_id, cw_status in cups:
        _resolve_one_cup(cup_id, cw_status, cfg, ratings_df, ranked_teams, zones, overrides, claimed, api_key)

    return overrides
