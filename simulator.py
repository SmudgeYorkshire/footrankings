"""
Monte Carlo season simulator using a Poisson goals model.

Model
-----
For a match between home team H and away team A:

    home_lambda = (H_attack * A_defense / league_avg) * home_advantage
    away_lambda =  A_attack * H_defense / league_avg

where:
    - H_attack / A_attack : expected goals scored per game (higher = better)
    - H_defense / A_defense: expected goals conceded per game (lower = better)
    - league_avg           : mean attack value across all rated teams
    - home_advantage       : multiplicative boost for home team (e.g. 1.20)

When Opta ratings are supplied (single 0-100 scale), they are first
converted to attack/defense via a power transform:

    relative   = opta_rating / mean(opta_ratings)
    attack     = league_avg_goals * relative ^ k
    defense    = league_avg_goals * relative ^ (-k)

where k (default 2.0) controls how much the ratings spread translates to
goal differences.  Higher k → stronger teams dominate more.

Tiebreakers
-----------
Each league can specify a list of tiebreaker rules (from config.py).
Supported rules:
    gd            – overall goal difference
    gf            – overall goals scored
    away_gf       – overall away goals scored
    h2h_pts       – head-to-head points (among tied teams only)
    h2h_gd        – head-to-head goal difference
    h2h_gf        – head-to-head goals scored
    h2h_away_gf   – head-to-head away goals scored

H2H stats are accumulated from both played_fixtures (already completed
matches) and simulated remaining fixtures.  If played_fixtures is not
supplied, base H2H is omitted (only simulated H2H is used).
"""

import math
import numpy as np
import pandas as pd

from config import DEFAULT_HOME_ADVANTAGE, DEFAULT_BASE_GOALS

_MAX_GOALS = 10  # upper bound for Poisson grid (captures >99.9% of probability mass)


def _poisson_pmf(lam: float) -> list[float]:
    """Return P(X=k) for k=0..._MAX_GOALS for X ~ Poisson(lam)."""
    exp_lam = math.exp(-lam)
    pmf = [0.0] * (_MAX_GOALS + 1)
    pmf[0] = exp_lam
    for k in range(1, _MAX_GOALS + 1):
        pmf[k] = pmf[k - 1] * lam / k
    return pmf


def _build_rat_lookup(ratings: pd.DataFrame, base_goals: float) -> tuple[dict, float]:
    """Build {name: (attack, defense)} lookup and league_avg from a ratings DataFrame."""
    if ratings.empty:
        return {}, base_goals
    avg_attack  = ratings["attack"].mean()
    avg_defense = ratings["defense"].mean()
    league_avg  = (avg_attack + avg_defense) / 2
    lookup: dict[str, tuple[float, float]] = {}
    for _, row in ratings.iterrows():
        pair = (row["attack"], row["defense"])
        lookup[row["team"]] = pair
        alias = str(row.get("alias", "")).strip()
        if alias:
            lookup[alias] = pair
    return lookup, league_avg


def fixture_odds(
    fixtures: list[dict],
    ratings: pd.DataFrame,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> list[dict]:
    """
    Compute home-win / draw / away-win probabilities analytically for each fixture.

    Uses the same Poisson model as simulate_season — no simulation needed.
    Returns a list of dicts (parallel to `fixtures`) with keys:
        home_win, draw, away_win  (floats, sum ≈ 1.0)
    """
    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    avg = DEFAULT_BASE_GOALS
    rat_lookup, league_avg = _build_rat_lookup(ratings, avg)
    default = (avg, avg)

    results = []
    for f in fixtures:
        h_att, h_def = rat_lookup.get(f.get("strHomeTeam", ""), default)
        a_att, a_def = rat_lookup.get(f.get("strAwayTeam", ""), default)

        lam_h = h_att * max(a_def, 0.01) / league_avg * home_advantage
        lam_a = a_att * max(h_def, 0.01) / league_avg

        pmf_h = _poisson_pmf(lam_h)
        pmf_a = _poisson_pmf(lam_a)

        p_home = p_draw = 0.0
        for gh in range(_MAX_GOALS + 1):
            for ga in range(_MAX_GOALS + 1):
                p = pmf_h[gh] * pmf_a[ga]
                if gh > ga:
                    p_home += p
                elif gh == ga:
                    p_draw += p
        results.append({"home_win": p_home, "draw": p_draw, "away_win": 1.0 - p_home - p_draw})

    return results

# Exponent for Opta → attack/defense conversion
OPTA_K = 2.0


def _opta_to_attack_defense(
    ratings: pd.DataFrame,
    base_goals: float = DEFAULT_BASE_GOALS,
    k: float = OPTA_K,
) -> pd.DataFrame:
    """Convert a DataFrame with 'opta_rating' column to 'attack'/'defense'."""
    df = ratings.copy()
    mean_rating = df["opta_rating"].mean()
    relative = df["opta_rating"] / mean_rating
    df["attack"] = base_goals * (relative ** k)
    df["defense"] = base_goals * (relative ** (-k))
    return df


def _rank_group(
    group: list[int],
    rules: list[str],
    gd: np.ndarray,
    gf: np.ndarray,
    away_gf: np.ndarray,
    h2h_pts: np.ndarray,
    h2h_gd: np.ndarray,
    h2h_gf: np.ndarray,
    h2h_agf: np.ndarray,
) -> list[int]:
    """
    Rank a group of tied-on-points team indices using the given tiebreaker rules.
    H2H stats are computed only among teams within the group.
    Returns the group in ranked order (best first).
    """
    if len(group) <= 1:
        return list(group)

    for idx, rule in enumerate(rules):
        scores = {}
        for t in group:
            if rule == "h2h_pts":
                scores[t] = sum(int(h2h_pts[t, o]) for o in group if o != t)
            elif rule == "h2h_gd":
                scores[t] = sum(int(h2h_gd[t, o]) for o in group if o != t)
            elif rule == "h2h_gf":
                scores[t] = sum(int(h2h_gf[t, o]) for o in group if o != t)
            elif rule == "h2h_away_gf":
                scores[t] = sum(int(h2h_agf[t, o]) for o in group if o != t)
            elif rule == "gd":
                scores[t] = int(gd[t])
            elif rule == "gf":
                scores[t] = int(gf[t])
            elif rule == "away_gf":
                scores[t] = int(away_gf[t])
            else:
                scores[t] = 0

        if len(set(scores.values())) == 1:
            continue  # still all tied, try next rule

        remaining_rules = rules[idx + 1:]
        sorted_group = sorted(group, key=lambda t: scores[t], reverse=True)

        result = []
        i = 0
        while i < len(sorted_group):
            j = i + 1
            while j < len(sorted_group) and scores[sorted_group[j]] == scores[sorted_group[i]]:
                j += 1
            subgroup = sorted_group[i:j]
            result.extend(
                _rank_group(subgroup, remaining_rules, gd, gf, away_gf, h2h_pts, h2h_gd, h2h_gf, h2h_agf)
                if len(subgroup) > 1 else subgroup
            )
            i = j
        return result

    return list(group)  # all rules exhausted, keep original order


def simulate_season(
    standings: list[dict],
    remaining_fixtures: list[dict],
    ratings: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    tiebreakers: list[str] | None = None,
    played_fixtures: list[dict] | None = None,
) -> pd.DataFrame:
    """
    Run a Monte Carlo simulation of the remaining season.

    Parameters
    ----------
    standings          : list of TheSportsDB table row dicts
    remaining_fixtures : list of TheSportsDB event dicts (unplayed only)
    ratings            : DataFrame with columns ['team', 'opta_rating']
                         OR ['team', 'attack', 'defense']
    n_sim              : number of simulations
    home_advantage     : multiplicative factor applied to home team expected goals
    tiebreakers        : ordered list of tiebreaker rules (from config LEAGUES entry)
    played_fixtures    : list of already-played TheSportsDB event dicts (for base H2H)

    Returns
    -------
    DataFrame  shape (n_teams, n_teams)
        Index   = team names sorted by current position
        Columns = finishing positions 1 .. n_teams
        Values  = probability (0–1) of each team finishing in that position
    """
    if not standings:
        return pd.DataFrame()

    if tiebreakers is None:
        tiebreakers = ["gd", "gf"]

    needs_h2h   = any(r.startswith("h2h") for r in tiebreakers)
    needs_away  = "away_gf" in tiebreakers

    # Convert Opta ratings → attack/defense if needed
    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    # Sort standings by current rank
    standings_sorted = sorted(standings, key=lambda r: int(r.get("intRank", 99)))
    teams = [row["strTeam"] for row in standings_sorted]
    n_teams = len(teams)
    team_idx = {t: i for i, t in enumerate(teams)}

    # Build ratings lookup (supports both primary name and alias)
    avg_attack = ratings["attack"].mean() if not ratings.empty else DEFAULT_BASE_GOALS
    rat_lookup, league_avg = _build_rat_lookup(ratings, DEFAULT_BASE_GOALS)
    default_rating = (avg_attack, avg_attack)

    def get_rating(team: str) -> tuple[float, float]:
        return rat_lookup.get(team, default_rating)

    # Base state vectors
    base_points = np.array([int(row.get("intPoints", 0)) for row in standings_sorted], dtype=np.int64)
    base_gd     = np.array([int(row.get("intGoalDifference", 0)) for row in standings_sorted], dtype=np.int64)
    base_gf     = np.array([int(row.get("intGoalsFor", 0)) for row in standings_sorted], dtype=np.int64)

    # Base H2H / away goals from already-played fixtures
    base_h2h_pts  = np.zeros((n_teams, n_teams), dtype=np.int64)
    base_h2h_gd   = np.zeros((n_teams, n_teams), dtype=np.int64)
    base_h2h_gf   = np.zeros((n_teams, n_teams), dtype=np.int64)
    base_h2h_agf  = np.zeros((n_teams, n_teams), dtype=np.int64)
    base_away_gf  = np.zeros(n_teams, dtype=np.int64)

    if played_fixtures and (needs_h2h or needs_away):
        for f in played_fixtures:
            h_name = f.get("strHomeTeam", "")
            a_name = f.get("strAwayTeam", "")
            if h_name not in team_idx or a_name not in team_idx:
                continue
            h, a = team_idx[h_name], team_idx[a_name]
            try:
                hg = int(f.get("intHomeScore") or 0)
                ag = int(f.get("intAwayScore") or 0)
            except (TypeError, ValueError):
                continue
            if hg > ag:
                base_h2h_pts[h, a] += 3
            elif hg == ag:
                base_h2h_pts[h, a] += 1
                base_h2h_pts[a, h] += 1
            else:
                base_h2h_pts[a, h] += 3
            base_h2h_gd[h, a]  += hg - ag
            base_h2h_gd[a, h]  += ag - hg
            base_h2h_gf[h, a]  += hg
            base_h2h_gf[a, h]  += ag
            base_h2h_agf[a, h] += ag   # team a scored away goals at h's ground
            base_away_gf[a]    += ag   # team a scored away goals

    # Filter to fixtures where both teams appear in the standings
    valid_fixtures = [
        f for f in remaining_fixtures
        if f.get("strHomeTeam") in team_idx and f.get("strAwayTeam") in team_idx
    ]

    if not valid_fixtures:
        # No remaining fixtures — deterministic ranking
        probs = np.zeros((n_teams, n_teams))
        gd_v = base_gd.copy()
        gf_v = base_gf.copy()
        aw_v = base_away_gf.copy()
        sorted_by_pts = list(np.argsort(-base_points, kind="stable"))
        ranked = []
        i = 0
        while i < n_teams:
            j = i + 1
            while j < n_teams and base_points[sorted_by_pts[j]] == base_points[sorted_by_pts[i]]:
                j += 1
            group = sorted_by_pts[i:j]
            ranked.extend(
                _rank_group(group, tiebreakers, gd_v, gf_v, aw_v,
                            base_h2h_pts, base_h2h_gd, base_h2h_gf, base_h2h_agf)
                if len(group) > 1 else group
            )
            i = j
        for pos, team_i in enumerate(ranked):
            probs[team_i, pos] = 1.0
        return _build_dataframe(probs, teams)

    F = len(valid_fixtures)
    home_idx = np.array([team_idx[f["strHomeTeam"]] for f in valid_fixtures])
    away_idx = np.array([team_idx[f["strAwayTeam"]] for f in valid_fixtures])

    # Pre-compute expected goals for every fixture
    home_lambdas = np.empty(F)
    away_lambdas = np.empty(F)
    for i, f in enumerate(valid_fixtures):
        h_att, h_def = get_rating(f["strHomeTeam"])
        a_att, a_def = get_rating(f["strAwayTeam"])
        home_lambdas[i] = h_att * max(a_def, 0.01) / league_avg * home_advantage
        away_lambdas[i] = a_att * max(h_def, 0.01) / league_avg

    # Simulate all goals at once: shape (F, n_sim)
    rng = np.random.default_rng()
    home_goals = rng.poisson(home_lambdas[:, None] * np.ones((F, n_sim)))
    away_goals = rng.poisson(away_lambdas[:, None] * np.ones((F, n_sim)))

    # Points per fixture
    home_pts = np.where(home_goals > away_goals, 3, np.where(home_goals == away_goals, 1, 0))
    away_pts = np.where(away_goals > home_goals, 3, np.where(home_goals == away_goals, 1, 0))

    # Accumulate across simulations (n_teams, n_sim)
    pts_matrix = np.tile(base_points[:, None], n_sim).astype(np.int64)
    gd_matrix  = np.tile(base_gd[:, None],     n_sim).astype(np.int64)
    gf_matrix  = np.tile(base_gf[:, None],     n_sim).astype(np.int64)

    # H2H / away_gf matrices (n_teams, n_teams, n_sim) — only built when needed
    if needs_h2h or needs_away:
        sim_h2h_pts  = np.zeros((n_teams, n_teams, n_sim), dtype=np.int64)
        sim_h2h_gd   = np.zeros((n_teams, n_teams, n_sim), dtype=np.int64)
        sim_h2h_gf   = np.zeros((n_teams, n_teams, n_sim), dtype=np.int64)
        sim_h2h_agf  = np.zeros((n_teams, n_teams, n_sim), dtype=np.int64)
        sim_away_gf  = np.zeros((n_teams, n_sim), dtype=np.int64)

    for i in range(F):
        h, a = home_idx[i], away_idx[i]
        pts_matrix[h] += home_pts[i]
        pts_matrix[a] += away_pts[i]
        gd_delta = home_goals[i] - away_goals[i]
        gd_matrix[h] += gd_delta
        gd_matrix[a] -= gd_delta
        gf_matrix[h] += home_goals[i]
        gf_matrix[a] += away_goals[i]

        if needs_h2h or needs_away:
            sim_h2h_pts[h, a]  += home_pts[i]
            sim_h2h_pts[a, h]  += away_pts[i]
            sim_h2h_gd[h, a]   += gd_delta
            sim_h2h_gd[a, h]   -= gd_delta
            sim_h2h_gf[h, a]   += home_goals[i]
            sim_h2h_gf[a, h]   += away_goals[i]
            sim_h2h_agf[a, h]  += away_goals[i]   # away team scored away goals
            sim_away_gf[a]     += away_goals[i]

    # ── Rank teams for each simulation ──────────────────────────────────────
    position_counts = np.zeros((n_teams, n_teams), dtype=np.int64)

    if not (needs_h2h or needs_away):
        # Fast vectorized path (no H2H needed)
        sort_key = pts_matrix * 100_000 + (gd_matrix + 200) * 100 + gf_matrix
        ranks = np.argsort(-sort_key, axis=0)
        for pos in range(n_teams):
            counts = np.bincount(ranks[pos], minlength=n_teams)
            position_counts[:, pos] = counts
    else:
        # Per-simulation loop with tiebreaker-aware ranking
        for sim in range(n_sim):
            pts_s    = pts_matrix[:, sim]
            gd_s     = gd_matrix[:, sim]
            gf_s     = gf_matrix[:, sim]
            aw_s     = base_away_gf + sim_away_gf[:, sim]
            h2h_p_s  = base_h2h_pts + sim_h2h_pts[:, :, sim]
            h2h_gd_s = base_h2h_gd  + sim_h2h_gd[:, :, sim]
            h2h_gf_s = base_h2h_gf  + sim_h2h_gf[:, :, sim]
            h2h_ag_s = base_h2h_agf + sim_h2h_agf[:, :, sim]

            sorted_by_pts = list(np.argsort(-pts_s, kind="stable"))
            ranked = []
            i = 0
            while i < n_teams:
                j = i + 1
                while j < n_teams and pts_s[sorted_by_pts[j]] == pts_s[sorted_by_pts[i]]:
                    j += 1
                group = sorted_by_pts[i:j]
                ranked.extend(
                    _rank_group(group, tiebreakers, gd_s, gf_s, aw_s,
                                h2h_p_s, h2h_gd_s, h2h_gf_s, h2h_ag_s)
                    if len(group) > 1 else group
                )
                i = j

            for pos, team_i in enumerate(ranked):
                position_counts[team_i, pos] += 1

    return _build_dataframe(position_counts / n_sim, teams)


def _build_dataframe(probs: np.ndarray, teams: list[str]) -> pd.DataFrame:
    n = len(teams)
    return pd.DataFrame(probs, index=teams, columns=[str(i + 1) for i in range(n)])
