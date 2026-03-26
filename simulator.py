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

Goals model
-----------
Goals are drawn from a Negative Binomial distribution rather than Poisson.
NegBin(r, p) where r = λ/φ, p = 1/(1+φ), φ = OVERDISPERSION (default 0.15).
This captures real-football overdispersion: Var[goals] = λ(1+φ) > λ.
Reduces to Poisson as φ → 0.

Form adjustment
---------------
Each team's last FORM_GAMES (default 5) results are used to compute a
small attack multiplier (±FORM_STRENGTH = ±5%).  Good recent form boosts
expected goals scored; poor form reduces them.

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

_MAX_GOALS    = 10    # upper bound for goal grid (captures >99.9% of probability mass)
OVERDISPERSION = 0.15 # NegBin overdispersion φ: Var[goals] = λ(1+φ)
FORM_GAMES     = 5    # number of recent results used for form adjustment
FORM_STRENGTH  = 0.05 # max ±5% attack multiplier from form


def _goals_pmf(lam: float) -> list[float]:
    """
    Return P(X=k) for k=0..._MAX_GOALS using a Negative Binomial distribution.

    NegBin(r, p) where r = lam/OVERDISPERSION, p = 1/(1+OVERDISPERSION).
    Var[X] = lam*(1+OVERDISPERSION) — captures real-football overdispersion.
    Reduces to Poisson as OVERDISPERSION → 0.
    """
    phi = OVERDISPERSION
    r   = lam / phi
    p   = 1.0 / (1.0 + phi)
    q   = phi / (1.0 + phi)          # = 1 - p
    pmf = [0.0] * (_MAX_GOALS + 1)
    pmf[0] = math.exp(r * math.log(p)) if lam > 0 else 1.0
    for k in range(1, _MAX_GOALS + 1):
        pmf[k] = pmf[k - 1] * (r + k - 1) / k * q
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


def _compute_form(
    teams: list[str],
    played_fixtures: list[dict],
    team_idx: dict[str, int],
) -> np.ndarray:
    """
    Compute a per-team attack multiplier from their last FORM_GAMES results.

    Returns array shape (n_teams,). Values near 1.0:
      - perfect recent form  → 1.0 + FORM_STRENGTH
      - average form         → 1.0
      - poor recent form     → 1.0 - FORM_STRENGTH
    """
    n = len(teams)
    results: list[list[float]] = [[] for _ in range(n)]
    for f in played_fixtures:
        h = team_idx.get(f.get("strHomeTeam", ""))
        a = team_idx.get(f.get("strAwayTeam", ""))
        if h is None or a is None:
            continue
        try:
            hg = int(f.get("intHomeScore") or 0)
            ag = int(f.get("intAwayScore") or 0)
        except (TypeError, ValueError):
            continue
        if hg > ag:
            results[h].append(1.0); results[a].append(0.0)
        elif hg == ag:
            results[h].append(0.5); results[a].append(0.5)
        else:
            results[h].append(0.0); results[a].append(1.0)

    multipliers = np.ones(n)
    for i in range(n):
        recent = results[i][-FORM_GAMES:]
        if recent:
            form_score = sum(recent) / len(recent)   # 0.0 (all losses) … 1.0 (all wins)
            multipliers[i] = 1.0 + FORM_STRENGTH * (2.0 * form_score - 1.0)
    return multipliers


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

        pmf_h = _goals_pmf(lam_h)
        pmf_a = _goals_pmf(lam_a)

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

    # Apply form multipliers to attacking lambdas (based on last FORM_GAMES results)
    if played_fixtures:
        _form = _compute_form(teams, played_fixtures, team_idx)
        home_lambdas *= _form[home_idx]
        away_lambdas *= _form[away_idx]

    # Draw goals from Negative Binomial (overdispersed Poisson)
    _phi  = OVERDISPERSION
    _p_nb = 1.0 / (1.0 + _phi)
    home_goals = rng.negative_binomial(
        home_lambdas[:, None] / _phi * np.ones((F, n_sim)), _p_nb
    )
    away_goals = rng.negative_binomial(
        away_lambdas[:, None] / _phi * np.ones((F, n_sim)), _p_nb
    )

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


def simulate_final_four(
    teams_4: list[str],
    ratings: pd.DataFrame,
    n_sim: int = 10_000,
) -> pd.DataFrame:
    """
    Simulate a Final Four tournament (Albanian Superliga format).

    Format
    ------
    - 2 seeded teams (1st, 2nd by league rank) and 2 unseeded (3rd, 4th).
    - Draw decides semi-final pairings: Seed1 vs Unseeded? / Seed2 vs other.
    - Semi-final tie after 90 min → higher-ranked team advances.
    - Final tie → extra time (30 min), then 50/50 penalties.

    Parameters
    ----------
    teams_4 : [1st, 2nd, 3rd, 4th] by current projected league rank
    ratings : DataFrame with opta_rating or attack/defense columns
    n_sim   : number of tournament simulations

    Returns
    -------
    DataFrame with columns [Team, SF Win %, Final %, Title %]
    ordered highest title % first.
    """
    if len(teams_4) < 4:
        return pd.DataFrame()

    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    rat_lookup, l_avg = _build_rat_lookup(ratings, DEFAULT_BASE_GOALS)
    default_r = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)

    def get_lams(ta: str, tb: str) -> tuple[float, float]:
        a_att, a_def = rat_lookup.get(ta, default_r)
        b_att, b_def = rat_lookup.get(tb, default_r)
        return a_att * max(b_def, 0.01) / l_avg, b_att * max(a_def, 0.01) / l_avg

    rng = np.random.default_rng()
    s1, s2, u1, u2 = teams_4[0], teams_4[1], teams_4[2], teams_4[3]

    sf_wins    = {t: 0 for t in teams_4}
    final_apps = {t: 0 for t in teams_4}
    titles     = {t: 0 for t in teams_4}

    # Draw: True = (s1 vs u1, s2 vs u2); False = (s1 vs u2, s2 vs u1)
    draw_a = rng.integers(0, 2, n_sim).astype(bool)

    for opp_for_s1, opp_for_s2, n in [
        (u1, u2, int(draw_a.sum())),
        (u2, u1, int((~draw_a).sum())),
    ]:
        if n == 0:
            continue

        # ── Semi-finals: tie → higher-ranked (seeded) team wins ─────────────
        lam_s1h, lam_s1a = get_lams(s1, opp_for_s1)
        g_s1  = rng.poisson(lam_s1h, n)
        g_op1 = rng.poisson(lam_s1a, n)
        # tie → s1 wins (higher rank)
        sf1_s1_wins = g_s1 >= g_op1

        lam_s2h, lam_s2a = get_lams(s2, opp_for_s2)
        g_s2  = rng.poisson(lam_s2h, n)
        g_op2 = rng.poisson(lam_s2a, n)
        sf2_s2_wins = g_s2 >= g_op2

        sf_wins[s1]        += int(sf1_s1_wins.sum())
        sf_wins[opp_for_s1]+= int((~sf1_s1_wins).sum())
        sf_wins[s2]        += int(sf2_s2_wins.sum())
        sf_wins[opp_for_s2]+= int((~sf2_s2_wins).sum())

        # ── Final participants ───────────────────────────────────────────────
        fin_a = np.where(sf1_s1_wins, s1, opp_for_s1)   # object array
        fin_b = np.where(sf2_s2_wins, s2, opp_for_s2)

        for t in teams_4:
            final_apps[t] += int((fin_a == t).sum()) + int((fin_b == t).sum())

        # ── Final: group by unique matchup, simulate each ───────────────────
        unique_pairs = set(zip(fin_a.tolist(), fin_b.tolist()))
        for (ta, tb) in unique_pairs:
            mask   = (fin_a == ta) & (fin_b == tb)
            n_m    = int(mask.sum())
            if n_m == 0:
                continue
            la, lb = get_lams(ta, tb)
            ga = rng.poisson(la, n_m)
            gb = rng.poisson(lb, n_m)
            # Extra time (30 min ≈ 1/3 of 90 min)
            tied = ga == gb
            if tied.any():
                ga = np.where(tied, ga + rng.poisson(la * 0.767, n_m), ga)
                gb = np.where(tied, gb + rng.poisson(lb * 0.767, n_m), gb)
                # Penalties
                still = ga == gb
                coin  = rng.integers(0, 2, n_m).astype(bool)
                ga    = np.where(still, ga + coin.astype(int), ga)
                gb    = np.where(still, gb + (~coin).astype(int), gb)
            titles[ta] += int((ga > gb).sum())
            titles[tb] += int((gb > ga).sum())

    df = pd.DataFrame({
        "Team":       teams_4,
        "SF Win %":   [round(sf_wins[t]    / n_sim * 100, 1) for t in teams_4],
        "Final %":    [round(final_apps[t] / n_sim / 2 * 100, 1) for t in teams_4],
        "Title %":    [round(titles[t]     / n_sim * 100, 1) for t in teams_4],
    }).sort_values("Title %", ascending=False).reset_index(drop=True)
    return df


def simulate_uecl_playoff(
    bye_team: str,
    team_a: str,
    team_b: str,
    ratings: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> pd.DataFrame:
    """
    Simulate the Austrian 3-team UECL play-off.

    Format
    ------
    Semi-final (one leg, at team_a's ground): team_a (7th) hosts team_b (8th).
        If level after 90 min → extra time → 50/50 penalties.
    Final (two legs): SF winner hosts bye_team in leg 1;
        bye_team (5th) hosts SF winner in leg 2.
        Aggregate score decides. If level → extra time at bye_team's ground → 50/50 penalties.
    Winner qualifies for UECL QR2.

    Returns
    -------
    DataFrame with columns [Team, Role, SF Win %, Final %, Winner %]
    sorted by Winner % descending.
    """
    if not bye_team or not team_a or not team_b:
        return pd.DataFrame()

    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    rat_lookup, l_avg = _build_rat_lookup(ratings, DEFAULT_BASE_GOALS)
    default_r = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    _phi  = OVERDISPERSION
    _p_nb = 1.0 / (1.0 + _phi)

    def get_lams(home: str, away: str) -> tuple[float, float]:
        h_att, h_def = rat_lookup.get(home, default_r)
        a_att, a_def = rat_lookup.get(away, default_r)
        return (h_att * max(a_def, 0.01) / l_avg * home_advantage,
                a_att * max(h_def, 0.01) / l_avg)

    def draw(lam: float, n: int) -> np.ndarray:
        return rng.negative_binomial(max(lam / _phi, 1e-6), _p_nb, n)

    rng = np.random.default_rng()

    # ── Semi-final: team_a (7th) hosts team_b (8th), one leg ─────────────────
    lam_ah, lam_ba = get_lams(team_a, team_b)
    ga_sf = draw(lam_ah, n_sim)
    gb_sf = draw(lam_ba, n_sim)
    tied_sf = ga_sf == gb_sf
    if tied_sf.any():
        ga_sf = np.where(tied_sf, ga_sf + draw(lam_ah * 0.767, n_sim), ga_sf)
        gb_sf = np.where(tied_sf, gb_sf + draw(lam_ba * 0.767, n_sim), gb_sf)
        still_sf = ga_sf == gb_sf
        coin_sf  = rng.integers(0, 2, n_sim).astype(bool)
        ga_sf = np.where(still_sf, ga_sf + coin_sf.astype(int),    ga_sf)
        gb_sf = np.where(still_sf, gb_sf + (~coin_sf).astype(int), gb_sf)

    a_wins_sf = ga_sf > gb_sf
    sf_win = {team_a: int(a_wins_sf.sum()), team_b: int((~a_wins_sf).sum()), bye_team: 0}

    # ── Final: two legs ───────────────────────────────────────────────────────
    # Leg 1: SF winner hosts bye_team  |  Leg 2: bye_team hosts SF winner
    final_wins = {team_a: 0, team_b: 0, bye_team: 0}

    for sf_winner, sf_mask in [(team_a, a_wins_sf), (team_b, ~a_wins_sf)]:
        n_m = int(sf_mask.sum())
        if n_m == 0:
            continue
        lam_sf_h, lam_bye_a = get_lams(sf_winner, bye_team)  # leg 1: SF winner at home
        lam_bye_h, lam_sf_a = get_lams(bye_team, sf_winner)  # leg 2: bye_team at home

        g_sf_1  = draw(lam_sf_h,  n_m)
        g_bye_1 = draw(lam_bye_a, n_m)
        g_bye_2 = draw(lam_bye_h, n_m)
        g_sf_2  = draw(lam_sf_a,  n_m)

        agg_sf  = g_sf_1  + g_sf_2
        agg_bye = g_bye_1 + g_bye_2

        # If level on aggregate → ET at bye_team's ground → pens
        tied_f = agg_sf == agg_bye
        if tied_f.any():
            agg_sf  = np.where(tied_f, agg_sf  + draw(lam_sf_a  * 0.767, n_m), agg_sf)
            agg_bye = np.where(tied_f, agg_bye + draw(lam_bye_h * 0.767, n_m), agg_bye)
            still_f = agg_sf == agg_bye
            coin_f  = rng.integers(0, 2, n_m).astype(bool)
            agg_sf  = np.where(still_f, agg_sf  + coin_f.astype(int),    agg_sf)
            agg_bye = np.where(still_f, agg_bye + (~coin_f).astype(int), agg_bye)

        final_wins[sf_winner] += int((agg_sf > agg_bye).sum())
        final_wins[bye_team]  += int((agg_bye > agg_sf).sum())

    final_apps = {
        bye_team: n_sim,
        team_a:   int(a_wins_sf.sum()),
        team_b:   int((~a_wins_sf).sum()),
    }

    teams_3 = [bye_team, team_a, team_b]
    roles   = {
        bye_team: "Bye to Final (hosts leg 2)",
        team_a:   "SF host (7th)",
        team_b:   "SF away (8th)",
    }

    df = pd.DataFrame({
        "Team":      teams_3,
        "Role":      [roles[t]                                        for t in teams_3],
        "SF Win %":  ["-" if t == bye_team
                      else round(sf_win[t] / n_sim * 100, 1)         for t in teams_3],
        "Final %":   [round(final_apps[t] / n_sim * 100, 1)          for t in teams_3],
        "Winner %":  [round(final_wins[t] / n_sim * 100, 1)          for t in teams_3],
    }).sort_values("Winner %", ascending=False).reset_index(drop=True)
    return df


def simulate_uecl_3team_playoff(
    bye_team: str,   # hosts the one-legged final (e.g. 4th in champ)
    team_a: str,     # SF home (e.g. 7th overall / 1st in relg)
    team_b: str,     # SF away (e.g. 8th overall / 2nd in relg)
    ratings: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> pd.DataFrame:
    """
    Simulate a 3-team UECL play-off with one-legged SF and one-legged final.

    Format
    ------
    Semi-final (one leg, at team_a's ground): team_a hosts team_b.
        If level after 90 min → extra time → 50/50 penalties.
    Final (one leg, at bye_team's ground): bye_team hosts SF winner.
        If level after 90 min → extra time → 50/50 penalties.
    Winner qualifies for UECL – QR2.

    Returns
    -------
    DataFrame with columns [Team, Role, SF Win %, Final %, Winner %]
    sorted by Winner % descending.
    """
    if not bye_team or not team_a or not team_b:
        return pd.DataFrame()

    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    rat_lookup, l_avg = _build_rat_lookup(ratings, DEFAULT_BASE_GOALS)
    default_r = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    _phi  = OVERDISPERSION
    _p_nb = 1.0 / (1.0 + _phi)

    def get_lams(home: str, away: str) -> tuple[float, float]:
        h_att, h_def = rat_lookup.get(home, default_r)
        a_att, a_def = rat_lookup.get(away, default_r)
        return (h_att * max(a_def, 0.01) / l_avg * home_advantage,
                a_att * max(h_def, 0.01) / l_avg)

    def draw(lam: float, n: int) -> np.ndarray:
        return rng.negative_binomial(max(lam / _phi, 1e-6), _p_nb, n)

    def play_one_leg(home: str, away: str, n: int) -> np.ndarray:
        """Return boolean array: True = home wins."""
        lam_h, lam_a = get_lams(home, away)
        g_h = draw(lam_h, n)
        g_a = draw(lam_a, n)
        tied = g_h == g_a
        if tied.any():
            g_h = np.where(tied, g_h + draw(lam_h * 0.767, n), g_h)
            g_a = np.where(tied, g_a + draw(lam_a * 0.767, n), g_a)
            still = g_h == g_a
            coin = rng.integers(0, 2, n).astype(bool)
            g_h = np.where(still, g_h + coin.astype(int),    g_h)
            g_a = np.where(still, g_a + (~coin).astype(int), g_a)
        return g_h > g_a

    rng = np.random.default_rng()

    # ── Semi-final: team_a hosts team_b (one leg) ────────────────────────────
    a_wins_sf = play_one_leg(team_a, team_b, n_sim)
    sf_win = {team_a: int(a_wins_sf.sum()), team_b: int((~a_wins_sf).sum()), bye_team: 0}

    # ── Final: bye_team hosts SF winner (one leg) ────────────────────────────
    final_wins = {team_a: 0, team_b: 0, bye_team: 0}
    for sf_winner, sf_mask in [(team_a, a_wins_sf), (team_b, ~a_wins_sf)]:
        n_m = int(sf_mask.sum())
        if n_m == 0:
            continue
        bye_wins = play_one_leg(bye_team, sf_winner, n_m)
        final_wins[bye_team]   += int(bye_wins.sum())
        final_wins[sf_winner]  += int((~bye_wins).sum())

    final_apps = {bye_team: n_sim, team_a: int(a_wins_sf.sum()), team_b: int((~a_wins_sf).sum())}

    teams_3 = [bye_team, team_a, team_b]
    roles   = {bye_team: "Final host (4th)", team_a: "SF host (7th)", team_b: "SF away (8th)"}
    df = pd.DataFrame({
        "Team":     teams_3,
        "Role":     [roles[t]                                          for t in teams_3],
        "SF Win %": ["-" if t == bye_team
                     else round(sf_win[t] / n_sim * 100, 1)           for t in teams_3],
        "Final %":  [round(final_apps[t] / n_sim * 100, 1)            for t in teams_3],
        "Winner %": [round(final_wins[t] / n_sim * 100, 1)            for t in teams_3],
    }).sort_values("Winner %", ascending=False).reset_index(drop=True)
    return df


def simulate_uecl_8team_playoff(
    pos2: str, pos3: str, pos5: str, pos6: str, pos7: str, pos8: str,
    pos9: str, pos10: str, pos11: str, pos12: str,
    ratings: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> pd.DataFrame:
    """
    San Marino UECL 8-team play-off (all ties one-legged, ET+pens on ties).

    R1: 9th hosts 12th (Match A),  10th hosts 11th (Match B)
    QF: 2nd hosts R1-B winner,  6th hosts 7th,
        3rd hosts R1-A winner,  5th hosts 8th
    SF: QF1 winner hosts QF2 winner,  QF3 winner hosts QF4 winner
    Final: lower-position-number (higher-ranked) SF winner hosts.

    Returns
    -------
    DataFrame [Team, Role, R1 Win %, QF Win %, SF Win %, Win %]
    sorted by Win % descending.
    """
    all_args = [pos2, pos3, pos5, pos6, pos7, pos8, pos9, pos10, pos11, pos12]
    if any(not t for t in all_args):
        return pd.DataFrame()

    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    rat_lookup, l_avg = _build_rat_lookup(ratings, DEFAULT_BASE_GOALS)
    default_r = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    _phi  = OVERDISPERSION
    _p_nb = 1.0 / (1.0 + _phi)

    # teams_list order: positions [2,3,5,6,7,8,9,10,11,12] → indices [0..9]
    teams_list = [pos2, pos3, pos5, pos6, pos7, pos8, pos9, pos10, pos11, pos12]
    n_teams = len(teams_list)
    idx = {t: i for i, t in enumerate(teams_list)}

    # Pre-compute pairwise lambda matrices
    lam_h_mat = np.zeros((n_teams, n_teams))
    lam_a_mat = np.zeros((n_teams, n_teams))
    for i, h in enumerate(teams_list):
        h_att, h_def = rat_lookup.get(h, default_r)
        for j, a in enumerate(teams_list):
            if i != j:
                a_att, a_def = rat_lookup.get(a, default_r)
                lam_h_mat[i, j] = h_att * max(a_def, 0.01) / l_avg * home_advantage
                lam_a_mat[i, j] = a_att * max(h_def, 0.01) / l_avg

    rng = np.random.default_rng()

    def play_v(home_i: np.ndarray, away_i: np.ndarray) -> np.ndarray:
        """Vectorized one-legged tie. True = home wins."""
        lh = lam_h_mat[home_i, away_i]
        la = lam_a_mat[home_i, away_i]
        g_h = rng.negative_binomial(np.maximum(lh / _phi, 1e-6), _p_nb)
        g_a = rng.negative_binomial(np.maximum(la / _phi, 1e-6), _p_nb)
        tied = g_h == g_a
        g_h = np.where(tied, g_h + rng.negative_binomial(np.maximum(lh * 0.767 / _phi, 1e-6), _p_nb), g_h)
        g_a = np.where(tied, g_a + rng.negative_binomial(np.maximum(la * 0.767 / _phi, 1e-6), _p_nb), g_a)
        still = g_h == g_a
        coin = rng.integers(0, 2, g_h.shape[0]).astype(bool)
        g_h = np.where(still, g_h + coin.astype(int),    g_h)
        g_a = np.where(still, g_a + (~coin).astype(int), g_a)
        return g_h > g_a

    N = n_sim
    i2, i3, i5, i6, i7, i8, i9, i10, i11, i12 = (idx[t] for t in teams_list)

    # ── R1 ────────────────────────────────────────────────────────────────────
    r1a = play_v(np.full(N, i9,  dtype=int), np.full(N, i12, dtype=int))  # True=9th wins
    r1b = play_v(np.full(N, i10, dtype=int), np.full(N, i11, dtype=int))  # True=10th wins
    r1a_win = np.where(r1a, i9,  i12)
    r1b_win = np.where(r1b, i10, i11)

    # ── QF ────────────────────────────────────────────────────────────────────
    qf1_res = play_v(np.full(N, i2, dtype=int), r1b_win)    # 2nd hosts R1B winner
    qf1_win = np.where(qf1_res, i2, r1b_win)

    qf2_res = play_v(np.full(N, i6, dtype=int), np.full(N, i7, dtype=int))
    qf2_win = np.where(qf2_res, i6, i7)

    qf3_res = play_v(np.full(N, i3, dtype=int), r1a_win)    # 3rd hosts R1A winner
    qf3_win = np.where(qf3_res, i3, r1a_win)

    qf4_res = play_v(np.full(N, i5, dtype=int), np.full(N, i8, dtype=int))
    qf4_win = np.where(qf4_res, i5, i8)

    # ── SF ────────────────────────────────────────────────────────────────────
    sf1_res = play_v(qf1_win, qf2_win)   # QF1 winner hosts QF2 winner
    sf1_win = np.where(sf1_res, qf1_win, qf2_win)

    sf2_res = play_v(qf3_win, qf4_win)   # QF3 winner hosts QF4 winner
    sf2_win = np.where(sf2_res, qf3_win, qf4_win)

    # ── Final ─────────────────────────────────────────────────────────────────
    # Lower team index = lower position number = higher rank = hosts
    fin_home = np.where(sf1_win < sf2_win, sf1_win, sf2_win)
    fin_away = np.where(sf1_win < sf2_win, sf2_win, sf1_win)
    fin_res  = play_v(fin_home, fin_away)
    fin_win  = np.where(fin_res, fin_home, fin_away)

    # ── Collect stats ─────────────────────────────────────────────────────────
    def pct(c): return round(c / N * 100, 1)
    r1_roles = {i9: "R1 home (9th)", i10: "R1 home (10th)",
                i11: "R1 away (11th)", i12: "R1 away (12th)"}
    qf_roles = {i2: "QF seed (2nd)", i3: "QF seed (3rd)", i5: "QF seed (5th)",
                i6: "QF seed (6th)", i7: "QF seed (7th)", i8: "QF seed (8th)"}
    r1_wins = {i9: pct(r1a.sum()), i10: pct(r1b.sum()),
               i11: pct((~r1b).sum()), i12: pct((~r1a).sum())}

    rows = []
    for i, team in enumerate(teams_list):
        qf_w = sum(int((w == i).sum()) for w in [qf1_win, qf2_win, qf3_win, qf4_win])
        sf_w = sum(int((w == i).sum()) for w in [sf1_win, sf2_win])
        rows.append({
            "Team":      team,
            "Role":      r1_roles.get(i, qf_roles.get(i, "")),
            "R1 Win %":  r1_wins.get(i, "–"),
            "QF Win %":  pct(qf_w),
            "SF Win %":  pct(sf_w),
            "Win %":     pct(int((fin_win == i).sum())),
        })
    return (pd.DataFrame(rows)
            .sort_values("Win %", ascending=False)
            .reset_index(drop=True))


def simulate_uecl_5team_playoff(
    pos3: str,   # Final host (3rd in champ)
    pos4: str,   # QF1 home (4th in champ)
    pos5: str,   # QF2 home (5th in champ)
    pos7: str,   # QF2 away (7th overall / 1st in play-off conf)
    pos8: str,   # QF1 away (8th overall / 2nd in play-off conf)
    ratings: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    qf1_home_rank: int = 4, qf1_away_rank: int = 8,
    qf2_home_rank: int = 5, qf2_away_rank: int = 7,
    final_host_rank: int = 3,
) -> pd.DataFrame:
    """
    Simulate a 5-team UECL play-off with one-legged QF, SF, and Final.

    Format
    ------
    QF1 (one leg, at pos4's ground): pos4 hosts pos8.
    QF2 (one leg, at pos5's ground): pos5 hosts pos7.
    SF  (one leg): lower position number (higher rank) hosts.
    Final (one leg, at pos3's ground): pos3 hosts SF winner.
        If level after 90 min → extra time → 50/50 penalties.
    Winner qualifies for UECL – QR1.

    Returns
    -------
    DataFrame with columns [Team, Role, QF Win %, SF Win %, Winner %]
    sorted by Winner % descending.
    """
    if not all([pos3, pos4, pos5, pos7, pos8]):
        return pd.DataFrame()

    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    rat_lookup, l_avg = _build_rat_lookup(ratings, DEFAULT_BASE_GOALS)
    default_r = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    _phi  = OVERDISPERSION
    _p_nb = 1.0 / (1.0 + _phi)

    def get_lams(home: str, away: str) -> tuple[float, float]:
        h_att, h_def = rat_lookup.get(home, default_r)
        a_att, a_def = rat_lookup.get(away, default_r)
        return (h_att * max(a_def, 0.01) / l_avg * home_advantage,
                a_att * max(h_def, 0.01) / l_avg)

    def draw(lam: float, n: int) -> np.ndarray:
        return rng.negative_binomial(max(lam / _phi, 1e-6), _p_nb, n)

    def play_one_leg(home: str, away: str, n: int) -> np.ndarray:
        """Return boolean array: True = home wins."""
        lam_h, lam_a = get_lams(home, away)
        g_h = draw(lam_h, n)
        g_a = draw(lam_a, n)
        tied = g_h == g_a
        if tied.any():
            g_h = np.where(tied, g_h + draw(lam_h * 0.767, n), g_h)
            g_a = np.where(tied, g_a + draw(lam_a * 0.767, n), g_a)
            still = g_h == g_a
            coin = rng.integers(0, 2, n).astype(bool)
            g_h = np.where(still, g_h + coin.astype(int),    g_h)
            g_a = np.where(still, g_a + (~coin).astype(int), g_a)
        return g_h > g_a

    rng = np.random.default_rng()
    rank = {pos3: final_host_rank, pos4: qf1_home_rank, pos5: qf2_home_rank,
            pos7: qf2_away_rank,   pos8: qf1_away_rank}

    # ── QF1: pos4 hosts pos8 ─────────────────────────────────────────────────
    pos4_wins_qf1 = play_one_leg(pos4, pos8, n_sim)
    qf_wins = {pos3: 0, pos4: int(pos4_wins_qf1.sum()), pos5: 0,
               pos7: 0, pos8: int((~pos4_wins_qf1).sum())}

    # ── QF2: pos5 hosts pos7 ─────────────────────────────────────────────────
    pos5_wins_qf2 = play_one_leg(pos5, pos7, n_sim)
    qf_wins[pos5] = int(pos5_wins_qf2.sum())
    qf_wins[pos7] = int((~pos5_wins_qf2).sum())

    sf_wins    = {t: 0 for t in [pos3, pos4, pos5, pos7, pos8]}
    winner_cnt = {t: 0 for t in [pos3, pos4, pos5, pos7, pos8]}

    # ── SF & Final: iterate over 4 QF outcome combinations ───────────────────
    for qf1_winner, qf1_mask in [(pos4, pos4_wins_qf1), (pos8, ~pos4_wins_qf1)]:
        for qf2_winner, qf2_mask in [(pos5, pos5_wins_qf2), (pos7, ~pos5_wins_qf2)]:
            mask = qf1_mask & qf2_mask
            n_m  = int(mask.sum())
            if n_m == 0:
                continue
            # Lower rank number = higher seed = hosts
            sf_home, sf_away = ((qf1_winner, qf2_winner)
                                if rank[qf1_winner] < rank[qf2_winner]
                                else (qf2_winner, qf1_winner))
            home_wins_sf = play_one_leg(sf_home, sf_away, n_m)
            for sf_winner, sf_mask2 in [(sf_home, home_wins_sf), (sf_away, ~home_wins_sf)]:
                n_sf = int(sf_mask2.sum())
                if n_sf == 0:
                    continue
                sf_wins[sf_winner] += n_sf
                # Final: pos3 hosts
                pos3_wins = play_one_leg(pos3, sf_winner, n_sf)
                winner_cnt[pos3]      += int(pos3_wins.sum())
                winner_cnt[sf_winner] += int((~pos3_wins).sum())

    all_teams = [pos3, pos4, pos5, pos7, pos8]
    roles = {
        pos3: f"Final host ({final_host_rank}th)",
        pos4: f"QF host ({qf1_home_rank}th)",
        pos5: f"QF host ({qf2_home_rank}th)",
        pos7: f"QF away ({qf2_away_rank}th)",
        pos8: f"QF away ({qf1_away_rank}th)",
    }
    df = pd.DataFrame({
        "Team":     all_teams,
        "Role":     [roles[t] for t in all_teams],
        "QF Win %": ["-" if t == pos3 else round(qf_wins[t] / n_sim * 100, 1)
                     for t in all_teams],
        "SF Win %": ["-" if t == pos3 else round(sf_wins[t] / n_sim * 100, 1)
                     for t in all_teams],
        "Winner %": [round(winner_cnt[t] / n_sim * 100, 1) for t in all_teams],
    }).sort_values("Winner %", ascending=False).reset_index(drop=True)
    return df


def simulate_uecl_4team_playoff(
    sf1_home: str, sf1_away: str,   # e.g. 5th hosts 9th
    sf2_home: str, sf2_away: str,   # e.g. 7th hosts 8th
    ratings: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    sf1_home_rank: int = 5,
    sf1_away_rank: int = 9,
    sf2_home_rank: int = 7,
    sf2_away_rank: int = 8,
) -> pd.DataFrame:
    """
    Simulate a 4-team single-elimination UECL play-off.

    Format
    ------
    SF1 (one leg): sf1_home (5th) hosts sf1_away (9th)
    SF2 (one leg): sf2_home (7th) hosts sf2_away (8th)
    Final (one leg): hosted by the SF winner with the higher league rank
        (lower rank number = higher rank, e.g. 5 > 7)
    If level after 90 min → extra time → 50/50 penalties.
    Winner qualifies for UECL.

    Returns
    -------
    DataFrame with columns [Team, Role, SF Win %, Winner %]
    sorted by Winner % descending.
    """
    if not sf1_home or not sf1_away or not sf2_home or not sf2_away:
        return pd.DataFrame()

    if "opta_rating" in ratings.columns and "attack" not in ratings.columns:
        ratings = _opta_to_attack_defense(ratings)

    rat_lookup, l_avg = _build_rat_lookup(ratings, DEFAULT_BASE_GOALS)
    default_r = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    _phi  = OVERDISPERSION
    _p_nb = 1.0 / (1.0 + _phi)

    def get_lams(home: str, away: str) -> tuple[float, float]:
        h_att, h_def = rat_lookup.get(home, default_r)
        a_att, a_def = rat_lookup.get(away, default_r)
        return (h_att * max(a_def, 0.01) / l_avg * home_advantage,
                a_att * max(h_def, 0.01) / l_avg)

    def draw(lam: float, n: int) -> np.ndarray:
        return rng.negative_binomial(max(lam / _phi, 1e-6), _p_nb, n)

    def play_one_leg(home: str, away: str, n: int) -> np.ndarray:
        """Returns boolean array: True = home wins (after ET + pens if needed)."""
        lam_h, lam_a = get_lams(home, away)
        gh = draw(lam_h, n)
        ga = draw(lam_a, n)
        tied = gh == ga
        if tied.any():
            gh = np.where(tied, gh + draw(lam_h * 0.767, n), gh)
            ga = np.where(tied, ga + draw(lam_a * 0.767, n), ga)
            still = gh == ga
            coin = rng.integers(0, 2, n).astype(bool)
            gh = np.where(still, gh + coin.astype(int),    gh)
            ga = np.where(still, ga + (~coin).astype(int), ga)
        return gh > ga

    rng = np.random.default_rng()

    # ── Semi-finals ──────────────────────────────────────────────────────────
    sf1_home_wins = play_one_leg(sf1_home, sf1_away, n_sim)
    sf2_home_wins = play_one_leg(sf2_home, sf2_away, n_sim)

    sf_wins = {
        sf1_home: int(sf1_home_wins.sum()),
        sf1_away: int((~sf1_home_wins).sum()),
        sf2_home: int(sf2_home_wins.sum()),
        sf2_away: int((~sf2_home_wins).sum()),
    }

    # ── Final: host = SF winner with lower rank number ───────────────────────
    final_wins = {sf1_home: 0, sf1_away: 0, sf2_home: 0, sf2_away: 0}

    for mask, f1_team, f1_rank, f2_team, f2_rank in [
        (sf1_home_wins  &  sf2_home_wins,  sf1_home, sf1_home_rank, sf2_home, sf2_home_rank),
        (sf1_home_wins  & ~sf2_home_wins,  sf1_home, sf1_home_rank, sf2_away, sf2_away_rank),
        (~sf1_home_wins &  sf2_home_wins,  sf1_away, sf1_away_rank, sf2_home, sf2_home_rank),
        (~sf1_home_wins & ~sf2_home_wins,  sf1_away, sf1_away_rank, sf2_away, sf2_away_rank),
    ]:
        n_m = int(mask.sum())
        if n_m == 0:
            continue
        host, visitor = (f1_team, f2_team) if f1_rank < f2_rank else (f2_team, f1_team)
        host_wins_f = play_one_leg(host, visitor, n_m)
        final_wins[host]    += int(host_wins_f.sum())
        final_wins[visitor] += int((~host_wins_f).sum())

    teams = [sf1_home, sf1_away, sf2_home, sf2_away]
    roles = {
        sf1_home: f"SF1 host ({sf1_home_rank}th)",
        sf1_away: f"SF1 away ({sf1_away_rank}th)",
        sf2_home: f"SF2 host ({sf2_home_rank}th)",
        sf2_away: f"SF2 away ({sf2_away_rank}th)",
    }

    df = pd.DataFrame({
        "Team":      teams,
        "Role":      [roles[t]                                    for t in teams],
        "SF Win %":  [round(sf_wins[t]    / n_sim * 100, 1)      for t in teams],
        "Winner %":  [round(final_wins[t] / n_sim * 100, 1)      for t in teams],
    }).sort_values("Winner %", ascending=False).reset_index(drop=True)
    return df
