"""
Monte Carlo simulation of a UEFA League Phase competition (Champions,
Europa, or Conference League) through to a champion, for a projected
36-team field (confirmed entrants + currently-favoured Play-off winners).

The real League Phase draw (which 8 -- or for the Conference League, 6 --
opponents each team faces) is only made by UEFA after the Play-off round
finishes, so there is no real schedule to simulate against yet. Each
simulation run instead draws its own schedule following the *real* draw
rules (pot-based, coefficient-ranked, country-protected) sourced from
kassiesa.net/uefa/seedcl2026.html (and seedel/seedco), so it's a faithful
approximation of the actual mechanism rather than a plain random pairing:

  Champions League / Europa League: 4 pots of 9 (by club coefficient).
    Each team plays 2 opponents from each pot (1 home, 1 away) = 8 games.
  Conference League: 6 pots of 6. Each team plays 1 opponent from each
    pot = 6 games (pots paired 1&2/3&4/5&6 for home/away balance).
  Both: no two clubs from the same country meet, and a team faces at
    most 2 opponents from any other single country.

Knockout stage (identical structure across all three competitions):
  Rank 1-8   -> direct to Round of 16 (seeded).
  Rank 9-24  -> Knockout stage play-off (9-16 seeded, host leg 2),
                paired by rank mirror (9v24, 10v23, ..., 16v17).
  Rank 25-36 -> eliminated.
  R16 winners meet the rank 1-8 seeds (weakest playoff-round product
  paired with the strongest direct seed, i.e. seed 1 draws the weakest
  possible R16 opponent), then a standard bracket-seeded QF/SF keeping
  seeds 1-2 apart until the Final and 1-4 apart until the semis. The
  Final is single-match, neutral venue. This mirrors kassiesa's published
  bracket topology; the exact "which of two mirror-symmetric bracket
  slots" a team lands in isn't modelled since it doesn't affect any
  team's opponent-strength distribution.
"""

import random

import numpy as np
import pandas as pd

from simulator import (
    DEFAULT_HOME_ADVANTAGE,
    DEFAULT_BASE_GOALS,
    OVERDISPERSION,
    _opta_to_attack_defense,
    _build_rat_lookup,
)

_MAX_SCHEDULE_ATTEMPTS = 200
_MAX_COUNTRY_OPPONENTS = 2

# Shakhtar Donetsk have played their UEFA "home" matches at neutral venues
# (outside Ukraine) since 2014 -- no true home crowd/pitch-familiarity
# advantage, so their nominal home leg should be modelled at parity (1.0)
# rather than getting the normal home-advantage boost, in both the League
# Phase schedule and any two-legged knockout tie.
NEUTRAL_VENUE_TEAMS = {"Shakhtar Donetsk"}


def _home_advantage_for(team: str, base: float) -> float:
    return 1.0 if team in NEUTRAL_VENUE_TEAMS else base

# ---------------------------------------------------------------------------
# UEFA association (country) coefficient points -- verified against both
# en.wikipedia.org/wiki/UEFA_coefficient's "Bonus Points" table (2024-25
# through 2026-27 seasons) and kassiesa.net/uefa/calc.html's "Max match
# points" table, which cross-check exactly (e.g. Champions League max
# points per club = League Stage 16 + 3*(R16/QF/SF two-legged max 4) +
# Final max 2 = 30 match points, + 6 participation + 6 ranking-bonus-at-
# rank-1 + 4*1.5 knockout-round bonus = 18 bonus points, totalling the
# documented 48-point maximum).
#
# Match points: 2 for a win, 1 for a draw, in the League Phase, Knockout
# Play-off round, and Round of 16 onward. Qualifying rounds (Q1-Q3) AND the
# Play-off round itself are "qualifying" for country-coefficient purposes
# and get HALF this rate (1 win / 0.5 draw) -- see country_ranking_simulator.
# Penalty-shootout results don't affect points beyond the draw itself.
COEFF_WIN, COEFF_DRAW = 2.0, 1.0

# Knockout-round-reached bonus (flat, once per round actually played).
_KNOCKOUT_ROUND_BONUS = {"Champions League": 1.5, "Europa League": 1.0, "Conference League": 0.5}

# League Phase bonus = flat participation (Champions League only) + a
# final-ranking bonus that increases per rank climbed, in two bands (9-24,
# then 1-8) at a different rate each. Verified exact: this formula
# reproduces the documented rank-1 maximums (12/6/4) precisely.
_LP_PARTICIPATION = {"Champions League": 6.0, "Europa League": 0.0, "Conference League": 0.0}
_LP_INC_9_24 = {"Champions League": 0.25, "Europa League": 0.25, "Conference League": 0.125}
_LP_INC_1_8 = {"Champions League": 0.25, "Europa League": 0.25, "Conference League": 0.25}


def league_phase_bonus(rank: int, comp_name: str) -> float:
    """UEFA coefficient bonus points for finishing League Phase at `rank`
    (1-36) in `comp_name`. Ranks 25-36 (eliminated) still earn the
    participation floor -- 6.0 for Champions League, 0.0 for Europa/
    Conference League -- just no ranking bonus on top."""
    if rank > 24:
        return _LP_PARTICIPATION[comp_name]
    inc_9_24 = _LP_INC_9_24[comp_name]
    if rank >= 9:
        ranking_bonus = (25 - rank) * inc_9_24
    else:
        ranking_bonus = 16 * inc_9_24 + (9 - rank) * _LP_INC_1_8[comp_name]
    return _LP_PARTICIPATION[comp_name] + ranking_bonus


def assign_pots(teams: list[str], club_coeff: dict[str, float], n_pots: int) -> list[list[str]]:
    """Splits teams into n_pots equal-ish pots by descending coefficient
    (pot 1 = strongest), matching the real UEFA pot-assignment method."""
    ranked = sorted(teams, key=lambda t: -club_coeff.get(t, 0.0))
    n = len(ranked)
    base, extra = divmod(n, n_pots)
    pots, i = [], 0
    for p in range(n_pots):
        size = base + (1 if p < extra else 0)
        pots.append(ranked[i:i + size])
        i += size
    return pots


def _build_regular_graph(
    nodes: list[str], k: int, country_ok, record, max_attempts: int = 300,
) -> bool:
    """k-regular graph on one pot's own nodes (each node gets exactly k
    intra-pot opponents), retried on country-constraint conflicts.
    k=1: a random perfect matching (degree 1, needs an even pot size).
    k=2: a single random Hamiltonian cycle -- each node's two cycle
    neighbours give it exactly degree 2, with no separate combination
    step needed (unlike k=1, one shift value already yields degree 2:
    a forward edge to i+1 and a backward edge from i-1).

    The very last attempt always ignores country_ok -- an unconditional
    safety net so a locally-infeasible pot (e.g. one country supplying
    most of a 9-club pot) still produces *some* valid schedule instead of
    raising; a handful of leaked same-country pairings in an already-
    approximate synthetic schedule is far less harmful than failing
    outright."""
    n = len(nodes)
    if k == 0:
        return True
    if k not in (1, 2):
        raise ValueError(f"unsupported intra-pot degree {k}")
    if k == 1 and n % 2 != 0:
        return False  # odd-sized pot can never be perfectly matched
    for attempt in range(max_attempts):
        order = nodes[:]
        random.shuffle(order)
        if k == 1:
            edges = [(order[i], order[i + 1]) for i in range(0, n, 2)]
        else:
            edges = [(order[i], order[(i + 1) % n]) for i in range(n)]
        check = (lambda a, b: True) if attempt == max_attempts - 1 else country_ok
        if all(check(a, b) for a, b in edges):
            for a, b in edges:
                record(a, b)
            return True
    return False


def _build_bipartite_regular_graph(
    left: list[str], right: list[str], k: int, country_ok, record, max_attempts: int = 300,
) -> bool:
    """k-regular bipartite graph between two pots: k independent random
    perfect matchings (permutations) left<->right, retried on conflicts
    (a repeated edge across matchings, or a country-constraint failure).
    The last attempt ignores country_ok -- see _build_regular_graph."""
    for attempt in range(max_attempts):
        matchings = []
        used_pairs = set()
        ok = True
        check = (lambda a, b: True) if attempt == max_attempts - 1 else country_ok
        for _pass in range(k):
            perm = right[:]
            random.shuffle(perm)
            pass_pairs = list(zip(left, perm))
            if any((a, b) in used_pairs for a, b in pass_pairs):
                ok = False
                break
            if not all(check(a, b) for a, b in pass_pairs):
                ok = False
                break
            used_pairs.update(pass_pairs)
            matchings.append(pass_pairs)
        if ok:
            for pass_pairs in matchings:
                for a, b in pass_pairs:
                    record(a, b)
            return True
    return False


def _try_generate_schedule(
    pots: list[list[str]], team_country: dict[str, str], opponents_per_pot: int,
) -> list[dict] | None:
    """One attempt at a full pot-based schedule: for every pair of pots
    (including a pot against itself) builds the required opponents_per_pot
    -regular graph, so every team ends up with exactly opponents_per_pot
    opponents from each pot. Returns None if any pot-pair's construction
    fails even with its own last-resort unconstrained attempt (k=1 on an
    odd pot is the only realistic way that happens)."""
    n_pots = len(pots)
    all_teams = [t for pot in pots for t in pot]
    country_count: dict[str, dict[str, int]] = {t: {} for t in all_teams}
    pairs: list[tuple[str, str]] = []

    def country_ok(a: str, b: str) -> bool:
        ca, cb = team_country.get(a, ""), team_country.get(b, "")
        if ca == cb:
            return False
        return (country_count[a].get(cb, 0) < _MAX_COUNTRY_OPPONENTS
                and country_count[b].get(ca, 0) < _MAX_COUNTRY_OPPONENTS)

    def record(a: str, b: str) -> None:
        ca, cb = team_country.get(a, ""), team_country.get(b, "")
        country_count[a][cb] = country_count[a].get(cb, 0) + 1
        country_count[b][ca] = country_count[b].get(ca, 0) + 1
        pairs.append((a, b))

    for i in range(n_pots):
        if not _build_regular_graph(pots[i], opponents_per_pot, country_ok, record):
            return None
        for j in range(i + 1, n_pots):
            if not _build_bipartite_regular_graph(pots[i], pots[j], opponents_per_pot, country_ok, record):
                return None

    # Assign home/away, balancing each team's overall home-game count.
    home_count = {t: 0 for t in all_teams}
    resolved: list[dict] = []
    for a, b in pairs:
        if home_count[a] <= home_count[b]:
            home, away = a, b
        else:
            home, away = b, a
        home_count[home] += 1
        resolved.append({"strHomeTeam": home, "strAwayTeam": away})
    return resolved


def generate_league_phase_schedule(
    pots: list[list[str]], team_country: dict[str, str], opponents_per_pot: int,
) -> list[dict]:
    """Builds one valid pot-based schedule, retrying with fresh randomness
    on failure. Falls back to a relaxed (no per-country cap) construction
    if every strict attempt fails, and each individual pot-pair build has
    its own last-resort unconstrained fallback below that -- so this
    essentially always succeeds; the only remaining failure mode is an odd
    -sized pot when opponents_per_pot is 1, which the caller controls."""
    for _ in range(_MAX_SCHEDULE_ATTEMPTS):
        result = _try_generate_schedule(pots, team_country, opponents_per_pot)
        if result is not None:
            return result

    global _MAX_COUNTRY_OPPONENTS
    original = _MAX_COUNTRY_OPPONENTS
    try:
        _MAX_COUNTRY_OPPONENTS = 99
        for _ in range(_MAX_SCHEDULE_ATTEMPTS):
            result = _try_generate_schedule(pots, team_country, opponents_per_pot)
            if result is not None:
                return result
    finally:
        _MAX_COUNTRY_OPPONENTS = original
    raise RuntimeError("Could not construct a valid League Phase schedule after retries")


# ---------------------------------------------------------------------------
# Knockout stage bracket (identical structure for CL/EL/ECL) -- see module
# docstring. Ranks below are 1-indexed League Phase finishing positions.
# ---------------------------------------------------------------------------
_KO_PLAYOFF_PAIRS = [(9, 24), (10, 23), (11, 22), (12, 21), (13, 20), (14, 19), (15, 18), (16, 17)]
# seed N (1-8, direct qualifiers) faces the winner of the KO-playoff pair
# whose seeded (lower-rank) member is (17 - N) -- i.e. seed 1 draws the
# weakest surviving playoff product (16v17), seed 8 the strongest (9v24).
_R16_SEED_TO_KO_PAIR = {n: (17 - n, 16 + n) for n in range(1, 9)}  # (seeded, unseeded) rank
# Bracket-seeded QF pairing (by original seed 1-8) keeping 1-4 apart until
# the semis and 1-2 apart until the final, matching kassiesa's SF1(QF1,QF2)
# / SF2(QF3,QF4) topology.
_QF_SEED_PAIRS = [(1, 8), (4, 5), (3, 6), (2, 7)]
_SF_QF_GROUPS = [(0, 1), (2, 3)]  # indices into _QF_SEED_PAIRS


def _pair_lambdas(teams: list[str], rat_lookup: dict, league_avg: float, default: tuple):
    """attack/defense arrays for every team, in `teams` order."""
    att = np.array([rat_lookup.get(t, default)[0] for t in teams])
    dfc = np.array([rat_lookup.get(t, default)[1] for t in teams])
    return att, dfc


def _load_pairwise_advance_odds(
    teams: list[str], ratings_df: pd.DataFrame, home_advantage: float, n_draws: int = 8_000,
) -> dict:
    """Precomputes every pair's two-leg advance probability once (630
    pairs for 36 teams) so the per-simulation knockout walk is just a
    dict lookup instead of repeated fresh computations per simulation.
    Vectorized NegBin Monte Carlo across every pair simultaneously
    (rather than the analytical single-pair two_leg_advance_odds, which
    is too slow to call 630+ times here) -- one leg at team a's ground,
    one at team b's, aggregate score decides, level scores split 50/50
    (penalties), matching this site's existing tie-break convention.
    Keyed both ways -- odds[(a, b)] is a's probability of advancing."""
    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    att, dfc = _pair_lambdas(teams, rat_lookup, league_avg, default)

    i_idx, j_idx = np.triu_indices(len(teams), k=1)
    a_att, a_def = att[i_idx], dfc[i_idx]
    b_att, b_def = att[j_idx], dfc[j_idx]
    ha_a = np.array([_home_advantage_for(teams[i], home_advantage) for i in i_idx])
    ha_b = np.array([_home_advantage_for(teams[j], home_advantage) for j in j_idx])

    # Leg 1: a at home. Leg 2: b at home.
    lam_l1_a = a_att * np.maximum(b_def, 0.01) / league_avg * ha_a
    lam_l1_b = b_att * np.maximum(a_def, 0.01) / league_avg
    lam_l2_b = b_att * np.maximum(a_def, 0.01) / league_avg * ha_b
    lam_l2_a = a_att * np.maximum(b_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    n_pairs = len(i_idx)
    g_l1_a = rng.negative_binomial(np.maximum(lam_l1_a[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    g_l1_b = rng.negative_binomial(np.maximum(lam_l1_b[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    g_l2_a = rng.negative_binomial(np.maximum(lam_l2_a[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    g_l2_b = rng.negative_binomial(np.maximum(lam_l2_b[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))

    agg_a = g_l1_a + g_l2_a
    agg_b = g_l1_b + g_l2_b
    a_adv = (agg_a > agg_b).mean(axis=1) + 0.5 * (agg_a == agg_b).mean(axis=1)

    odds: dict[tuple, float] = {}
    for k in range(n_pairs):
        a, b = teams[i_idx[k]], teams[j_idx[k]]
        odds[(a, b)] = float(a_adv[k])
        odds[(b, a)] = float(1.0 - a_adv[k])
    return odds


def _neutral_final_odds(teams: list[str], ratings_df: pd.DataFrame, n_draws: int = 8_000) -> dict:
    """Single-match (no second leg, no home advantage) win probabilities
    for every pair, for the Final specifically. Vectorized the same way
    as _load_pairwise_advance_odds. Draws are resolved 50/50 (extra time
    + penalties), matching this site's existing convention."""
    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    att, dfc = _pair_lambdas(teams, rat_lookup, league_avg, default)

    i_idx, j_idx = np.triu_indices(len(teams), k=1)
    a_att, a_def = att[i_idx], dfc[i_idx]
    b_att, b_def = att[j_idx], dfc[j_idx]
    lam_a = a_att * np.maximum(b_def, 0.01) / league_avg
    lam_b = b_att * np.maximum(a_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    n_pairs = len(i_idx)
    ga = rng.negative_binomial(np.maximum(lam_a[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    gb = rng.negative_binomial(np.maximum(lam_b[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    a_wins = (ga > gb).mean(axis=1) + 0.5 * (ga == gb).mean(axis=1)

    odds: dict[tuple, float] = {}
    for k in range(n_pairs):
        a, b = teams[i_idx[k]], teams[j_idx[k]]
        odds[(a, b)] = float(a_wins[k])
        odds[(b, a)] = float(1.0 - a_wins[k])
    return odds


def _load_pairwise_expected_points(
    teams: list[str], ratings_df: pd.DataFrame, home_advantage: float, n_draws: int = 8_000,
) -> dict:
    """Expected UEFA-coefficient match points (2 win/1 draw per leg) each
    side of a two-legged tie earns from playing it -- an unconditional
    expectation over the goal distribution (mixing both the "this side
    advances" and "this side is eliminated" outcomes in their true
    proportions), not a further simulated draw. Reused at every knockout
    round (Knockout Play-off, R16, QF, SF) since match points only depend
    on the pairing, not the round. Keyed both ways, like
    _load_pairwise_advance_odds."""
    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    att, dfc = _pair_lambdas(teams, rat_lookup, league_avg, default)

    i_idx, j_idx = np.triu_indices(len(teams), k=1)
    a_att, a_def = att[i_idx], dfc[i_idx]
    b_att, b_def = att[j_idx], dfc[j_idx]
    ha_a = np.array([_home_advantage_for(teams[i], home_advantage) for i in i_idx])
    ha_b = np.array([_home_advantage_for(teams[j], home_advantage) for j in j_idx])

    lam_l1_a = a_att * np.maximum(b_def, 0.01) / league_avg * ha_a
    lam_l1_b = b_att * np.maximum(a_def, 0.01) / league_avg
    lam_l2_b = b_att * np.maximum(a_def, 0.01) / league_avg * ha_b
    lam_l2_a = a_att * np.maximum(b_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    n_pairs = len(i_idx)
    g_l1_a = rng.negative_binomial(np.maximum(lam_l1_a[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    g_l1_b = rng.negative_binomial(np.maximum(lam_l1_b[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    g_l2_a = rng.negative_binomial(np.maximum(lam_l2_a[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    g_l2_b = rng.negative_binomial(np.maximum(lam_l2_b[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))

    def _leg_points(gh, ga):
        return np.where(gh > ga, COEFF_WIN, np.where(gh == ga, COEFF_DRAW, 0.0))

    a_pts = (_leg_points(g_l1_a, g_l1_b) + _leg_points(g_l2_a, g_l2_b)).mean(axis=1)
    b_pts = (_leg_points(g_l1_b, g_l1_a) + _leg_points(g_l2_b, g_l2_a)).mean(axis=1)

    expected: dict[tuple, float] = {}
    for k in range(n_pairs):
        a, b = teams[i_idx[k]], teams[j_idx[k]]
        expected[(a, b)] = float(a_pts[k])
        expected[(b, a)] = float(b_pts[k])
    return expected


def _neutral_final_expected_points(teams: list[str], ratings_df: pd.DataFrame, n_draws: int = 8_000) -> dict:
    """Expected UEFA-coefficient points from the single-match Final (no
    second leg, no home advantage) for every pair -- same unconditional-
    expectation approach as _load_pairwise_expected_points."""
    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    att, dfc = _pair_lambdas(teams, rat_lookup, league_avg, default)

    i_idx, j_idx = np.triu_indices(len(teams), k=1)
    a_att, a_def = att[i_idx], dfc[i_idx]
    b_att, b_def = att[j_idx], dfc[j_idx]
    lam_a = a_att * np.maximum(b_def, 0.01) / league_avg
    lam_b = b_att * np.maximum(a_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    n_pairs = len(i_idx)
    ga = rng.negative_binomial(np.maximum(lam_a[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))
    gb = rng.negative_binomial(np.maximum(lam_b[:, None] / phi, 1e-9), p_nb, size=(n_pairs, n_draws))

    a_pts = np.where(ga > gb, COEFF_WIN, np.where(ga == gb, COEFF_DRAW, 0.0)).mean(axis=1)
    b_pts = np.where(gb > ga, COEFF_WIN, np.where(ga == gb, COEFF_DRAW, 0.0)).mean(axis=1)

    expected: dict[tuple, float] = {}
    for k in range(n_pairs):
        a, b = teams[i_idx[k]], teams[j_idx[k]]
        expected[(a, b)] = float(a_pts[k])
        expected[(b, a)] = float(b_pts[k])
    return expected


def single_match_outcome_probs(
    fixtures: list[dict], ratings_df: pd.DataFrame, home_advantage: float, n_draws: int = 20_000,
) -> list[dict]:
    """Home win / draw / away win probabilities for a specific, already-
    known list of single League Phase matches -- e.g. one real matchday's
    18 fixtures once the League Phase draw is known. Each fixture dict
    needs strHomeTeam/strAwayTeam (any other keys, e.g. matchday, are
    passed through unchanged); results add pct_home, pct_draw, pct_away."""
    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)

    home_teams = [f["strHomeTeam"] for f in fixtures]
    away_teams = [f["strAwayTeam"] for f in fixtures]
    h_att = np.array([rat_lookup.get(t, default)[0] for t in home_teams])
    h_def = np.array([rat_lookup.get(t, default)[1] for t in home_teams])
    a_att = np.array([rat_lookup.get(t, default)[0] for t in away_teams])
    a_def = np.array([rat_lookup.get(t, default)[1] for t in away_teams])
    ha = np.array([_home_advantage_for(t, home_advantage) for t in home_teams])

    lam_h = h_att * np.maximum(a_def, 0.01) / league_avg * ha
    lam_a = a_att * np.maximum(h_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    n = len(fixtures)
    gh = rng.negative_binomial(np.maximum(lam_h[:, None] / phi, 1e-9), p_nb, size=(n, n_draws))
    ga = rng.negative_binomial(np.maximum(lam_a[:, None] / phi, 1e-9), p_nb, size=(n, n_draws))

    pct_home = (gh > ga).mean(axis=1)
    pct_draw = (gh == ga).mean(axis=1)
    pct_away = (gh < ga).mean(axis=1)

    results = []
    for i, f in enumerate(fixtures):
        results.append({**f, "pct_home": float(pct_home[i]), "pct_draw": float(pct_draw[i]), "pct_away": float(pct_away[i])})
    return results


def simulate_competition_winner(
    field: list[dict],
    club_coeff: dict[str, float],
    ratings_df: pd.DataFrame,
    n_pots: int,
    opponents_per_pot: int,
    n_sim: int = 3_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    comp_name: str | None = None,
    track_points: bool = False,
    schedule: list[dict] | None = None,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Full Monte Carlo simulation of a 36-team UEFA League Phase
    competition through to a champion.

    field: [{"team": name, "country": country}, ...] -- the projected
    36-club League Phase lineup (confirmed entrants + currently-favoured
    Play-off winners).

    schedule: if given (a list of {"strHomeTeam", "strAwayTeam"} covering
    all 144/108 games), simulates the REAL League Phase draw instead of
    drawing a synthetic pot-based one -- pass this once
    league_phase_fixtures.is_fixture_list_complete() is True for this
    competition. Otherwise draws ONE representative League Phase schedule
    (see module docstring for why), simulates its 144 (or 108, for the
    Conference League) matches with the same NegBin goals model used
    across the rest of the site, then for each of n_sim simulation runs:
    ranks the resulting table, sends 1-8 direct to the Round of 16, runs
    the 9-24 knockout play-off and the rest of the bracket via precomputed
    two-leg advance odds, and tallies who wins.

    Returns a DataFrame indexed by team with columns: country,
    reached_top8, reached_top16, reached_top24 (all cumulative -- e.g.
    reached_top24 includes clubs that finished in the top 8), reached_r16,
    reached_qf, reached_sf, reached_final, won_competition (all
    probabilities, 0-1).

    If track_points is True (comp_name required), ALSO returns a second
    value: {team: np.ndarray of shape (n_sim,)} of each club's total UEFA
    coefficient points earned in this run of the League Phase + Knockout
    stage -- match points (League Phase from real simulated scorelines;
    Knockout Play-off/R16/QF/SF/Final from each tie's *expected* points
    given the pairing, not a further simulated scoreline -- see
    _load_pairwise_expected_points) plus League Phase and knockout-round
    bonus points. Used by country_ranking_simulator to project each
    association's season coefficient.
    """
    teams = [f["team"] for f in field]
    team_country = {f["team"]: f["country"] for f in field}
    n_teams = len(teams)

    if schedule is None:
        pots = assign_pots(teams, club_coeff, n_pots)
        schedule = generate_league_phase_schedule(pots, team_country, opponents_per_pot)

    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)

    team_idx = {t: i for i, t in enumerate(teams)}
    F = len(schedule)
    home_idx = np.array([team_idx[f["strHomeTeam"]] for f in schedule])
    away_idx = np.array([team_idx[f["strAwayTeam"]] for f in schedule])

    home_lambdas = np.empty(F)
    away_lambdas = np.empty(F)
    for i, f in enumerate(schedule):
        h_att, h_def = rat_lookup.get(f["strHomeTeam"], default)
        a_att, a_def = rat_lookup.get(f["strAwayTeam"], default)
        ha = _home_advantage_for(f["strHomeTeam"], home_advantage)
        home_lambdas[i] = h_att * max(a_def, 0.01) / league_avg * ha
        away_lambdas[i] = a_att * max(h_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    home_goals = rng.negative_binomial(np.maximum(home_lambdas[:, None] / phi, 1e-9), p_nb, size=(F, n_sim))
    away_goals = rng.negative_binomial(np.maximum(away_lambdas[:, None] / phi, 1e-9), p_nb, size=(F, n_sim))

    home_pts = np.where(home_goals > away_goals, 3, np.where(home_goals == away_goals, 1, 0))
    away_pts = np.where(away_goals > home_goals, 3, np.where(home_goals == away_goals, 1, 0))

    pts_matrix = np.zeros((n_teams, n_sim), dtype=np.int64)
    gd_matrix = np.zeros((n_teams, n_sim), dtype=np.int64)
    gf_matrix = np.zeros((n_teams, n_sim), dtype=np.int64)
    coeff_matrix = np.zeros((n_teams, n_sim), dtype=np.float64) if track_points else None
    if track_points:
        home_coeff = np.where(home_goals > away_goals, COEFF_WIN, np.where(home_goals == away_goals, COEFF_DRAW, 0.0))
        away_coeff = np.where(away_goals > home_goals, COEFF_WIN, np.where(home_goals == away_goals, COEFF_DRAW, 0.0))
    for i in range(F):
        h, a = home_idx[i], away_idx[i]
        pts_matrix[h] += home_pts[i]
        pts_matrix[a] += away_pts[i]
        gd_delta = home_goals[i] - away_goals[i]
        gd_matrix[h] += gd_delta
        gd_matrix[a] -= gd_delta
        gf_matrix[h] += home_goals[i]
        gf_matrix[a] += away_goals[i]
        if track_points:
            coeff_matrix[h] += home_coeff[i]
            coeff_matrix[a] += away_coeff[i]

    pairwise_odds = _load_pairwise_advance_odds(teams, ratings_df, home_advantage)
    final_odds = _neutral_final_odds(teams, ratings_df)
    if track_points:
        pairwise_expected_pts = _load_pairwise_expected_points(teams, ratings_df, home_advantage)
        final_expected_pts = _neutral_final_expected_points(teams, ratings_df)
        ko_bonus = _KNOCKOUT_ROUND_BONUS[comp_name]

    reached_top8 = {t: 0 for t in teams}
    reached_top16 = {t: 0 for t in teams}
    reached_top24 = {t: 0 for t in teams}
    reached_r16 = {t: 0 for t in teams}
    reached_qf = {t: 0 for t in teams}
    reached_sf = {t: 0 for t in teams}
    reached_final = {t: 0 for t in teams}
    won = {t: 0 for t in teams}

    def _draw_winner(a: str, b: str, odds: dict) -> str:
        return a if random.random() < odds[(a, b)] else b

    for sim in range(n_sim):
        order = sorted(range(n_teams), key=lambda i: (-pts_matrix[i, sim], -gd_matrix[i, sim], -gf_matrix[i, sim]))
        ranked_teams = [teams[i] for i in order]  # rank 1 first
        rank_of = {t: r + 1 for r, t in enumerate(ranked_teams)}

        for t in ranked_teams[:8]:
            reached_top8[t] += 1
        for t in ranked_teams[:16]:
            reached_top16[t] += 1
        for t in ranked_teams[:24]:
            reached_top24[t] += 1

        team_by_rank = {rank_of[t]: t for t in ranked_teams}

        if track_points:
            for t in teams:
                coeff_matrix[team_idx[t], sim] += league_phase_bonus(rank_of[t], comp_name)

        # Knockout play-off (9-24)
        ko_winner_by_pair = {}
        for seeded_rank, unseeded_rank in _KO_PLAYOFF_PAIRS:
            a, b = team_by_rank[seeded_rank], team_by_rank[unseeded_rank]
            ko_winner_by_pair[(seeded_rank, unseeded_rank)] = _draw_winner(a, b, pairwise_odds)
            if track_points:
                coeff_matrix[team_idx[a], sim] += pairwise_expected_pts[(a, b)]
                coeff_matrix[team_idx[b], sim] += pairwise_expected_pts[(b, a)]

        # Round of 16: seed N vs winner of its assigned KO pair
        r16_winner_by_seed = {}
        for seed_rank in range(1, 9):
            seed_team = team_by_rank[seed_rank]
            ko_pair = _R16_SEED_TO_KO_PAIR[seed_rank]
            opponent = ko_winner_by_pair[ko_pair]
            winner = _draw_winner(seed_team, opponent, pairwise_odds)
            r16_winner_by_seed[seed_rank] = winner
            reached_r16[seed_team] += 1
            reached_r16[opponent] += 1
            if track_points:
                coeff_matrix[team_idx[seed_team], sim] += pairwise_expected_pts[(seed_team, opponent)] + ko_bonus
                coeff_matrix[team_idx[opponent], sim] += pairwise_expected_pts[(opponent, seed_team)] + ko_bonus

        # Quarter-finals
        qf_winner_by_group = {}
        for gi, (s1, s2) in enumerate(_QF_SEED_PAIRS):
            a, b = r16_winner_by_seed[s1], r16_winner_by_seed[s2]
            reached_qf[a] += 1
            reached_qf[b] += 1
            qf_winner_by_group[gi] = _draw_winner(a, b, pairwise_odds)
            if track_points:
                coeff_matrix[team_idx[a], sim] += pairwise_expected_pts[(a, b)] + ko_bonus
                coeff_matrix[team_idx[b], sim] += pairwise_expected_pts[(b, a)] + ko_bonus

        # Semi-finals
        sf_winners = []
        for g1, g2 in _SF_QF_GROUPS:
            a, b = qf_winner_by_group[g1], qf_winner_by_group[g2]
            reached_sf[a] += 1
            reached_sf[b] += 1
            sf_winners.append(_draw_winner(a, b, pairwise_odds))
            if track_points:
                coeff_matrix[team_idx[a], sim] += pairwise_expected_pts[(a, b)] + ko_bonus
                coeff_matrix[team_idx[b], sim] += pairwise_expected_pts[(b, a)] + ko_bonus

        # Final (single match, neutral venue)
        a, b = sf_winners
        reached_final[a] += 1
        reached_final[b] += 1
        champion = a if random.random() < final_odds[(a, b)] else b
        won[champion] += 1
        if track_points:
            coeff_matrix[team_idx[a], sim] += final_expected_pts[(a, b)] + ko_bonus
            coeff_matrix[team_idx[b], sim] += final_expected_pts[(b, a)] + ko_bonus

    rows = []
    for t in teams:
        rows.append({
            "team": t,
            "country": team_country[t],
            "reached_top8": reached_top8[t] / n_sim,
            "reached_top16": reached_top16[t] / n_sim,
            "reached_top24": reached_top24[t] / n_sim,
            "reached_r16": reached_r16[t] / n_sim,
            "reached_qf": reached_qf[t] / n_sim,
            "reached_sf": reached_sf[t] / n_sim,
            "reached_final": reached_final[t] / n_sim,
            "won_competition": won[t] / n_sim,
        })
    result = pd.DataFrame(rows).set_index("team").sort_values("won_competition", ascending=False)
    if track_points:
        points_by_team = {t: coeff_matrix[team_idx[t]] for t in teams}
        return result, points_by_team
    return result


def build_predicted_bracket(
    field: list[dict],
    club_coeff: dict[str, float],
    ratings_df: pd.DataFrame,
    n_pots: int,
    opponents_per_pot: int,
    n_sim: int = 3_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    schedule: list[dict] | None = None,
) -> dict:
    """A single, concrete predicted knockout bracket -- Knockout Play-off
    through Final -- rather than per-team reach probabilities.

    Draws the same representative League Phase schedule and simulates it
    the same way as simulate_competition_winner, but instead of tallying
    probabilities across every simulation run, ranks teams by their MEAN
    points/GD/GF across all n_sim runs to get one "expected" final League
    Phase table, then walks the real fixed bracket exactly once from that
    table, picking the favoured (>=50%) side at each tie using the same
    precomputed two-leg advance odds simulate_competition_winner uses --
    a "chalk" bracket, the standard way to present a single predicted
    tournament path. Each tie's percentages are that tie's own two-leg
    (or, for the Final, single-match) advance probability, not the
    probability of the *bracket path itself* playing out.

    Returns {"ko_playoff": [...], "r16": [...], "qf": [...], "sf": [...],
    "final": [...], "champion": str}, where each round is a list of
    {"team_a", "team_b", "pct_a", "pct_b", "winner"} dicts.
    """
    teams = [f["team"] for f in field]
    team_country = {f["team"]: f["country"] for f in field}
    n_teams = len(teams)

    if schedule is None:
        pots = assign_pots(teams, club_coeff, n_pots)
        schedule = generate_league_phase_schedule(pots, team_country, opponents_per_pot)

    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)

    team_idx = {t: i for i, t in enumerate(teams)}
    F = len(schedule)
    home_idx = np.array([team_idx[f["strHomeTeam"]] for f in schedule])
    away_idx = np.array([team_idx[f["strAwayTeam"]] for f in schedule])

    home_lambdas = np.empty(F)
    away_lambdas = np.empty(F)
    for i, f in enumerate(schedule):
        h_att, h_def = rat_lookup.get(f["strHomeTeam"], default)
        a_att, a_def = rat_lookup.get(f["strAwayTeam"], default)
        ha = _home_advantage_for(f["strHomeTeam"], home_advantage)
        home_lambdas[i] = h_att * max(a_def, 0.01) / league_avg * ha
        away_lambdas[i] = a_att * max(h_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    home_goals = rng.negative_binomial(np.maximum(home_lambdas[:, None] / phi, 1e-9), p_nb, size=(F, n_sim))
    away_goals = rng.negative_binomial(np.maximum(away_lambdas[:, None] / phi, 1e-9), p_nb, size=(F, n_sim))

    home_pts = np.where(home_goals > away_goals, 3, np.where(home_goals == away_goals, 1, 0))
    away_pts = np.where(away_goals > home_goals, 3, np.where(home_goals == away_goals, 1, 0))

    pts_matrix = np.zeros((n_teams, n_sim), dtype=np.int64)
    gd_matrix = np.zeros((n_teams, n_sim), dtype=np.int64)
    gf_matrix = np.zeros((n_teams, n_sim), dtype=np.int64)
    for i in range(F):
        h, a = home_idx[i], away_idx[i]
        pts_matrix[h] += home_pts[i]
        pts_matrix[a] += away_pts[i]
        gd_delta = home_goals[i] - away_goals[i]
        gd_matrix[h] += gd_delta
        gd_matrix[a] -= gd_delta
        gf_matrix[h] += home_goals[i]
        gf_matrix[a] += away_goals[i]

    mean_pts = pts_matrix.mean(axis=1)
    mean_gd = gd_matrix.mean(axis=1)
    mean_gf = gf_matrix.mean(axis=1)
    order = sorted(range(n_teams), key=lambda i: (-mean_pts[i], -mean_gd[i], -mean_gf[i]))
    ranked_teams = [teams[i] for i in order]
    rank_of = {t: r + 1 for r, t in enumerate(ranked_teams)}
    team_by_rank = {rank_of[t]: t for t in ranked_teams}

    pairwise_odds = _load_pairwise_advance_odds(teams, ratings_df, home_advantage)
    final_odds = _neutral_final_odds(teams, ratings_df)

    def _tie(a: str, b: str, odds: dict) -> dict:
        pa = odds[(a, b)]
        winner = a if pa >= 0.5 else b
        return {"team_a": a, "team_b": b, "pct_a": pa, "pct_b": 1.0 - pa, "winner": winner}

    bracket: dict = {"ko_playoff": [], "r16": [], "qf": [], "sf": [], "final": []}

    ko_winner_by_pair = {}
    for seeded_rank, unseeded_rank in _KO_PLAYOFF_PAIRS:
        a, b = team_by_rank[seeded_rank], team_by_rank[unseeded_rank]
        tie = _tie(a, b, pairwise_odds)
        bracket["ko_playoff"].append(tie)
        ko_winner_by_pair[(seeded_rank, unseeded_rank)] = tie["winner"]

    r16_winner_by_seed = {}
    for seed_rank in range(1, 9):
        seed_team = team_by_rank[seed_rank]
        opponent = ko_winner_by_pair[_R16_SEED_TO_KO_PAIR[seed_rank]]
        tie = _tie(seed_team, opponent, pairwise_odds)
        bracket["r16"].append(tie)
        r16_winner_by_seed[seed_rank] = tie["winner"]

    qf_winner_by_group = {}
    for gi, (s1, s2) in enumerate(_QF_SEED_PAIRS):
        a, b = r16_winner_by_seed[s1], r16_winner_by_seed[s2]
        tie = _tie(a, b, pairwise_odds)
        bracket["qf"].append(tie)
        qf_winner_by_group[gi] = tie["winner"]

    sf_winners = []
    for g1, g2 in _SF_QF_GROUPS:
        a, b = qf_winner_by_group[g1], qf_winner_by_group[g2]
        tie = _tie(a, b, pairwise_odds)
        bracket["sf"].append(tie)
        sf_winners.append(tie["winner"])

    a, b = sf_winners
    final_tie = _tie(a, b, final_odds)
    bracket["final"].append(final_tie)
    bracket["champion"] = final_tie["winner"]

    return bracket
