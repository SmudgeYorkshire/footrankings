"""
Projects each UEFA association's 5-season country coefficient (and thus its
predicted finishing rank among all associations) for the 2026-27 season,
combining:

  1. Each country's real, frozen 2022-23 through 2025-26 coefficients
     (coefficients_baseline.COUNTRY_BASELINE) plus its known number of
     clubs entered this season (the fixed divisor UEFA's Annex D.3 uses).
  2. Real points already earned this season from qualifying-round matches
     played so far (Q1-Q3) -- exact, no simulation, halved qualifying rate.
     Nothing else has happened yet this season (the Play-off round hasn't
     started), so this is the *entire* real component right now; it will
     naturally grow to cover the Play-off round too once those matches
     start being played for real.
  3. A Monte Carlo projection of everything not yet decided: the Play-off
     round itself (halved rate), then League Phase + Knockout stage (full
     rate + bonus points) for whichever clubs reach the League Phase, via
     league_phase_simulator.simulate_competition_winner's track_points
     mode.

Deliberately does NOT reuse coefficients_live._compute_live_raw_points for
the "real" component -- that function already folds in bonus points (e.g.
the Champions League's secured-League-Phase-spot floor, credited the
moment a club is confirmed), which would double-count against this
module's own *simulated* League Phase bonus (which computes the full,
final bonus from scratch for every club that reaches the League Phase in
each simulation run, floor included). Keeping the "real" side to match
points only, and the "simulated" side to everything else UEFA awards,
avoids needing to reconcile the two.

Each of the n_sim runs produces one fully-determined 2026-27 season
coefficient per country (summed across Champions/Europa/Conference League,
divided by that country's clubs_entered per UEFA's method); added to the
fixed 4-season baseline and ranked against every other country, this gives
a genuine probability distribution over final rank -- not just a point
estimate.
"""

import numpy as np
import pandas as pd

from config import EUROPEAN_COMPETITIONS
from coefficients_baseline import COUNTRY_BASELINE
from coefficients_live import (
    _load_club_country_map, _fetch_comp_fixtures, _group_ties, _tie_result,
)
from qualifying_bracket import PLAYOFF_BRACKET
from league_phase_simulator import simulate_competition_winner
from simulator import (
    DEFAULT_HOME_ADVANTAGE, DEFAULT_BASE_GOALS, OVERDISPERSION,
    _opta_to_attack_defense, _build_rat_lookup,
)

# Qualifying rounds (Q1-Q3) AND the Play-off round both count as
# "qualifying" for country-coefficient purposes -- half the League
# Phase/Knockout rate (UEFA Annex D.3).
QUAL_WIN, QUAL_DRAW = 1.0, 0.5


def real_points_from_played(played_fixtures: list[dict], club_country: dict[str, str]) -> dict[str, float]:
    """Real (already-known) UEFA country-coefficient MATCH points earned
    so far this season from played qualifying-round fixtures, halved rate
    (1 win / 0.5 draw). No bonus points -- see module docstring for why.
    Clubs not found in club_country are silently skipped (a small
    conservative undercount rather than a guess)."""
    points: dict[str, float] = {}
    for f in played_fixtures:
        h, a = f.get("strHomeTeam", ""), f.get("strAwayTeam", "")
        try:
            hg, ag = int(f.get("intHomeScore") or 0), int(f.get("intAwayScore") or 0)
        except (TypeError, ValueError):
            continue
        hc, ac = club_country.get(h), club_country.get(a)
        if hg > ag:
            if hc:
                points[hc] = points.get(hc, 0.0) + QUAL_WIN
        elif ag > hg:
            if ac:
                points[ac] = points.get(ac, 0.0) + QUAL_WIN
        else:
            if hc:
                points[hc] = points.get(hc, 0.0) + QUAL_DRAW
            if ac:
                points[ac] = points.get(ac, 0.0) + QUAL_DRAW
    return points


def resolve_current_playoff_ties(comp_name: str, key: str) -> list[tuple[str, str]]:
    """The real team-vs-team pairing for every Play-off round tie in
    `comp_name`, resolved from PLAYOFF_BRACKET plus already-played
    Qualifying Round results. Simpler than european.py's general-purpose
    bracket resolver (which also has to handle a QR3 tie still being
    undecided) because right now, with all of Q1-Q3 already complete,
    every QR3 tie this feeds from IS decided -- so a side is always either
    a literal confirmed team, or a real, already-known QR3 winner/loser."""
    played, remaining = _fetch_comp_fixtures(comp_name, key)
    played_ids = {f.get("idEvent") for f in played}
    tie_map: dict[frozenset, list[dict]] = {}
    for f in played:
        key_ = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
        tie_map.setdefault(key_, []).append(f)

    def _resolve_side(side: tuple) -> str | None:
        if side[0] == "team":
            return side[1]
        _, tie_comp, name_pair, which = side
        if tie_comp != comp_name:
            # A cross-competition drop-down (e.g. an EL tie feeding an ECL
            # Play-off slot) -- resolve against that OTHER competition's
            # played fixtures instead.
            other_played, _ = _fetch_comp_fixtures(tie_comp, key)
            other_played_ids = {f.get("idEvent") for f in other_played}
            other_tie_map: dict[frozenset, list[dict]] = {}
            for f in other_played:
                k = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
                other_tie_map.setdefault(k, []).append(f)
            legs = other_tie_map.get(frozenset(name_pair))
            if legs is None:
                for fpair, flegs in other_tie_map.items():
                    if fpair & name_pair:
                        legs = flegs
                        break
            if legs is None:
                return None
            winner, loser = _tie_result(legs, other_played_ids)
            return winner if which == "winner" else loser
        legs = tie_map.get(frozenset(name_pair))
        if legs is None:
            for fpair, flegs in tie_map.items():
                if fpair & name_pair:
                    legs = flegs
                    break
        if legs is None:
            return None
        winner, loser = _tie_result(legs, played_ids)
        return winner if which == "winner" else loser

    ties: list[tuple[str, str]] = []
    for side_a, side_b in PLAYOFF_BRACKET.get(comp_name, []):
        a, b = _resolve_side(side_a), _resolve_side(side_b)
        if a and b:
            ties.append((a, b))
    return ties


def simulate_remaining_playoff_points(
    po_ties: list[tuple[str, str]],
    ratings_df: pd.DataFrame,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    n_sim: int = 3_000,
) -> dict[str, np.ndarray]:
    """Monte Carlo two-leg goal simulation (halved qualifying rate: 1 win /
    0.5 draw per leg) of every Play-off tie, vectorized across all ties at
    once. Returns {club: array(n_sim)} of points earned from the tie -- for
    BOTH sides of every tie, not just winners."""
    if not po_ties:
        return {}
    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)

    n_ties = len(po_ties)
    a_att = np.array([rat_lookup.get(a, default)[0] for a, _ in po_ties])
    a_def = np.array([rat_lookup.get(a, default)[1] for a, _ in po_ties])
    b_att = np.array([rat_lookup.get(b, default)[0] for _, b in po_ties])
    b_def = np.array([rat_lookup.get(b, default)[1] for _, b in po_ties])

    lam_l1_a = a_att * np.maximum(b_def, 0.01) / league_avg * home_advantage
    lam_l1_b = b_att * np.maximum(a_def, 0.01) / league_avg
    lam_l2_b = b_att * np.maximum(a_def, 0.01) / league_avg * home_advantage
    lam_l2_a = a_att * np.maximum(b_def, 0.01) / league_avg

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    g_l1_a = rng.negative_binomial(np.maximum(lam_l1_a[:, None] / phi, 1e-9), p_nb, size=(n_ties, n_sim))
    g_l1_b = rng.negative_binomial(np.maximum(lam_l1_b[:, None] / phi, 1e-9), p_nb, size=(n_ties, n_sim))
    g_l2_a = rng.negative_binomial(np.maximum(lam_l2_a[:, None] / phi, 1e-9), p_nb, size=(n_ties, n_sim))
    g_l2_b = rng.negative_binomial(np.maximum(lam_l2_b[:, None] / phi, 1e-9), p_nb, size=(n_ties, n_sim))

    def _leg_pts(gh, ga):
        return np.where(gh > ga, QUAL_WIN, np.where(gh == ga, QUAL_DRAW, 0.0))

    a_pts = _leg_pts(g_l1_a, g_l1_b) + _leg_pts(g_l2_a, g_l2_b)
    b_pts = _leg_pts(g_l1_b, g_l1_a) + _leg_pts(g_l2_b, g_l2_a)

    result: dict[str, np.ndarray] = {}
    for i, (a, b) in enumerate(po_ties):
        result[a] = a_pts[i]
        result[b] = b_pts[i]
    return result


def aggregate_by_country(
    club_points: dict[str, np.ndarray], club_country: dict[str, str], n_sim: int,
) -> dict[str, np.ndarray]:
    """Sums per-club point arrays into per-country totals."""
    totals: dict[str, np.ndarray] = {}
    for club, arr in club_points.items():
        country = club_country.get(club)
        if not country:
            continue
        if country not in totals:
            totals[country] = np.zeros(n_sim)
        totals[country] += arr
    return totals


def build_country_rank_table(
    real_points: dict[str, float],
    simulated_points: list[dict[str, np.ndarray]],
    n_sim: int,
) -> pd.DataFrame:
    """Combines real match points with the simulated components (Play-off
    round, League Phase + Knockout per competition), divides by each
    country's clubs_entered, adds the fixed 4-season baseline, and ranks
    every country in every one of the n_sim runs to build a genuine
    rank-probability table.

    Returns a DataFrame indexed by country with columns: clubs,
    baseline_4yr, mean_season_coeff, mean_total, mean_rank, and pct_topN
    for N in (1, 4, 6, 10, 15, 20) -- probability of finishing at or above
    that rank (band cutoffs that matter in practice: title-race context,
    European Performance Spot contention, guaranteed extra Champions
    League berths, etc).
    """
    season_raw: dict[str, np.ndarray] = {c: np.full(n_sim, p) for c, p in real_points.items()}
    for comp in simulated_points:
        for country, arr in comp.items():
            if country not in season_raw:
                season_raw[country] = np.zeros(n_sim)
            season_raw[country] += arr

    countries = sorted(set(season_raw) | set(COUNTRY_BASELINE))
    n_countries = len(countries)
    totals = np.zeros((n_countries, n_sim))
    baselines = np.zeros(n_countries)
    clubs_entered = np.zeros(n_countries, dtype=int)
    for i, c in enumerate(countries):
        base = COUNTRY_BASELINE.get(c, {})
        entered = base.get("clubs_entered", 0)
        clubs_entered[i] = entered
        baseline = base.get("22/23", 0.0) + base.get("23/24", 0.0) + base.get("24/25", 0.0) + base.get("25/26", 0.0)
        baselines[i] = baseline
        if entered > 0:
            season_coeff = season_raw.get(c, np.zeros(n_sim)) / entered
        else:
            # Suspended (e.g. Russia) -- no clubs to earn anything new this
            # season, carry the frozen 25/26 figure forward as UEFA does.
            season_coeff = np.full(n_sim, base.get("25/26", 0.0))
            baseline -= base.get("25/26", 0.0)
            baselines[i] = baseline
        totals[i] = baseline + season_coeff

    order = np.argsort(-totals, axis=0)
    ranks = np.empty_like(order)
    for s in range(n_sim):
        ranks[order[:, s], s] = np.arange(1, n_countries + 1)

    bands = [1, 4, 6, 10, 15, 20]
    rows = []
    for i, c in enumerate(countries):
        row = {
            "country": c,
            "clubs": int(clubs_entered[i]),
            "baseline_4yr": round(baselines[i], 3),
            "mean_season_coeff": round(float((totals[i] - baselines[i]).mean()), 3),
            "mean_total": round(float(totals[i].mean()), 3),
            "mean_rank": round(float(ranks[i].mean()), 2),
        }
        for b in bands:
            row[f"pct_top{b}"] = float((ranks[i] <= b).mean())
        rows.append(row)
    return pd.DataFrame(rows).set_index("country").sort_values("mean_rank")


_LEAGUE_PHASE_POTS = {"Champions League": (4, 2), "Europa League": (4, 2), "Conference League": (6, 1)}


def project_country_predicted_ranking(
    project_league_phase_field,
    resolve_field_ratings,
    ratings_df: pd.DataFrame,
    get_coeff,
    api_key: str,
    n_sim: int = 3_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> tuple[pd.DataFrame, list[str]]:
    """Orchestrates the full predicted country ranking: real Q1-Q3 points +
    simulated Play-off/League Phase/Knockout points for all three
    competitions, combined into one rank-probability table.

    project_league_phase_field / resolve_field_ratings are european.py's
    functions (passed in rather than imported -- european.py is a
    Streamlit page script with top-level rendering code that runs
    immediately on import, so it can't be imported directly; the caller,
    which IS european.py or another page script already running in a
    Streamlit context, passes its own already-loaded functions in instead).

    Returns (table, warnings) -- warnings lists any competition whose
    League Phase field wasn't fully known yet (so its future Play-off
    winners' League Phase + Knockout points are simply omitted for now,
    same graceful-degradation approach as League Stage Predictions).
    """
    club_country = _load_club_country_map()
    all_played_fixtures: list[dict] = []
    simulated_points: list[dict[str, np.ndarray]] = []
    warnings: list[str] = []

    for comp_name in EUROPEAN_COMPETITIONS:
        played, _remaining = _fetch_comp_fixtures(comp_name, api_key)
        all_played_fixtures.extend(played)

        po_ties = resolve_current_playoff_ties(comp_name, api_key)
        po_points = simulate_remaining_playoff_points(po_ties, ratings_df, home_advantage, n_sim)
        simulated_points.append(aggregate_by_country(po_points, club_country, n_sim))

        field = project_league_phase_field(comp_name, ratings_df)
        if len(field) < 36:
            warnings.append(
                f"{comp_name}: only {len(field)}/36 League Phase clubs known, so its League "
                "Phase + Knockout points aren't projected yet (Play-off points still are)."
            )
            continue
        club_coeff = {f["team"]: get_coeff(f["team"], f["country"]) for f in field}
        field_ratings_df = resolve_field_ratings(field)
        n_pots, opp_per_pot = _LEAGUE_PHASE_POTS[comp_name]
        _, points_by_club = simulate_competition_winner(
            field=field, club_coeff=club_coeff, ratings_df=field_ratings_df,
            n_pots=n_pots, opponents_per_pot=opp_per_pot, n_sim=n_sim,
            home_advantage=home_advantage, comp_name=comp_name, track_points=True,
        )
        simulated_points.append(aggregate_by_country(points_by_club, club_country, n_sim))

    real_points = real_points_from_played(all_played_fixtures, club_country)
    table = build_country_rank_table(real_points, simulated_points, n_sim)
    return table, warnings
