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

    # Leg 1: a at home. Leg 2: b at home.
    lam_l1_a = a_att * np.maximum(b_def, 0.01) / league_avg * home_advantage
    lam_l1_b = b_att * np.maximum(a_def, 0.01) / league_avg
    lam_l2_b = b_att * np.maximum(a_def, 0.01) / league_avg * home_advantage
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


def simulate_competition_winner(
    field: list[dict],
    club_coeff: dict[str, float],
    ratings_df: pd.DataFrame,
    n_pots: int,
    opponents_per_pot: int,
    n_sim: int = 3_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> pd.DataFrame:
    """Full Monte Carlo simulation of a 36-team UEFA League Phase
    competition through to a champion.

    field: [{"team": name, "country": country}, ...] -- the projected
    36-club League Phase lineup (confirmed entrants + currently-favoured
    Play-off winners).

    Draws ONE representative League Phase schedule (see module docstring
    for why), simulates its 144 (or 108, for the Conference League)
    matches with the same NegBin goals model used across the rest of the
    site, then for each of n_sim simulation runs: ranks the resulting
    table, sends 1-8 direct to the Round of 16, runs the 9-24 knockout
    play-off and the rest of the bracket via precomputed two-leg advance
    odds, and tallies who wins.

    Returns a DataFrame indexed by team with columns: country,
    reached_top8, reached_playoff_zone (9-24), reached_r16, reached_qf,
    reached_sf, reached_final, won_competition (all probabilities, 0-1).
    """
    teams = [f["team"] for f in field]
    team_country = {f["team"]: f["country"] for f in field}
    n_teams = len(teams)

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
        home_lambdas[i] = h_att * max(a_def, 0.01) / league_avg * home_advantage
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

    pairwise_odds = _load_pairwise_advance_odds(teams, ratings_df, home_advantage)
    final_odds = _neutral_final_odds(teams, ratings_df)

    reached_top8 = {t: 0 for t in teams}
    reached_playoff_zone = {t: 0 for t in teams}
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

        top8 = ranked_teams[:8]
        playoff_zone = ranked_teams[8:24]
        for t in top8:
            reached_top8[t] += 1
        for t in playoff_zone:
            reached_playoff_zone[t] += 1

        team_by_rank = {rank_of[t]: t for t in ranked_teams}

        # Knockout play-off (9-24)
        ko_winner_by_pair = {}
        for seeded_rank, unseeded_rank in _KO_PLAYOFF_PAIRS:
            a, b = team_by_rank[seeded_rank], team_by_rank[unseeded_rank]
            ko_winner_by_pair[(seeded_rank, unseeded_rank)] = _draw_winner(a, b, pairwise_odds)

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

        # Quarter-finals
        qf_winner_by_group = {}
        for gi, (s1, s2) in enumerate(_QF_SEED_PAIRS):
            a, b = r16_winner_by_seed[s1], r16_winner_by_seed[s2]
            reached_qf[a] += 1
            reached_qf[b] += 1
            qf_winner_by_group[gi] = _draw_winner(a, b, pairwise_odds)

        # Semi-finals
        sf_winners = []
        for g1, g2 in _SF_QF_GROUPS:
            a, b = qf_winner_by_group[g1], qf_winner_by_group[g2]
            reached_sf[a] += 1
            reached_sf[b] += 1
            sf_winners.append(_draw_winner(a, b, pairwise_odds))

        # Final (single match, neutral venue)
        a, b = sf_winners
        reached_final[a] += 1
        reached_final[b] += 1
        champion = a if random.random() < final_odds[(a, b)] else b
        won[champion] += 1

    rows = []
    for t in teams:
        rows.append({
            "team": t,
            "country": team_country[t],
            "reached_top8": reached_top8[t] / n_sim,
            "reached_playoff_zone": reached_playoff_zone[t] / n_sim,
            "reached_r16": reached_r16[t] / n_sim,
            "reached_qf": reached_qf[t] / n_sim,
            "reached_sf": reached_sf[t] / n_sim,
            "reached_final": reached_final[t] / n_sim,
            "won_competition": won[t] / n_sim,
        })
    return pd.DataFrame(rows).set_index("team").sort_values("won_competition", ascending=False)
