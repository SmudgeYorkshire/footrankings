"""
Projects each UEFA association's 5-season country coefficient (and thus its
predicted finishing rank among all associations) for the 2026-27 season,
combining:

  1. Each country's real, frozen 2022-23 through 2025-26 coefficients
     (coefficients_baseline.COUNTRY_BASELINE) plus its known number of
     clubs entered this season (the fixed divisor UEFA's Annex D.3 uses).
  2. Real points already earned this season from qualifying-round matches
     played so far -- Q1-Q3 in full, plus whichever Play-off round legs
     have actually been played -- exact, no simulation, halved qualifying
     rate throughout (Q1-Q3 and the Play-off round are both "qualifying"
     for country-coefficient purposes).
  3. A Monte Carlo projection of everything not yet decided: whichever
     Play-off leg(s) haven't been played yet (halved rate -- see
     simulate_remaining_playoff_points, which skips any leg already
     covered by #2), then League Phase + Knockout stage (full rate +
     bonus points) for whichever clubs reach the League Phase, via
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
    _PLAYOFF_ROUND_NAMES, _QUALIFYING_ROUNDS, _is_league_stage,
    _BONUS_PER_STAGE, _league_phase_bonus,
)
from qualifying_bracket import PLAYOFF_BRACKET
from league_phase_simulator import cached_league_phase_simulation, league_phase_sim_cache_key
from league_phase_fixtures import is_opponent_list_complete, derive_fixtures
from qualifying_projection import real_league_phase_results
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
    conservative undercount rather than a guess).

    Restricted to _QUALIFYING_ROUNDS (Q1-Q3 + the Play-off round) --
    League Phase fixtures are deliberately excluded here even once they
    start getting played for real, since the SIMULATED component
    (cached_league_phase_simulation, fed real_results= for exactly this
    reason) already accounts for real League Phase results at the
    correct FULL rate. Before this exclusion, a real League Phase match
    would've been double-counted: once here at the wrong HALVED
    (qualifying) rate, and again inside the simulation at the right
    rate -- latent until the League Phase actually starts (nothing else
    is played yet this season), confirmed and fixed 2026-10-13 while
    wiring real_results= through."""
    points: dict[str, float] = {}
    for f in played_fixtures:
        if f.get("strRound") not in _QUALIFYING_ROUNDS:
            continue
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


# Knockout Play-off + Round of 16 + Quarter-finals + Semi-finals (2 legs
# each) + Final (1 leg, neutral venue) = 9 matches, every one assumed WON
# (2.0 pts each, full rate) -- the single biggest chunk of
# max_remaining_points' deliberately generous knockout-stage ceiling (see
# its own docstring for why future knockout pairings can't be bounded any
# tighter than this).
_KO_CEILING_MATCHES = 9


def max_remaining_points(club_country: dict[str, str], api_key: str) -> dict[str, float]:
    """{club: maximum additional UEFA coefficient points still
    mathematically reachable this season}, raw (not yet divided by
    clubs_entered or aggregated by country) -- the sound (never
    underestimates) upper-bound counterpart to real_points_from_played's
    exact floor, for country_rank_bounds below.

    Exact wherever the real calendar already settles it: remaining
    qualifying/Play-off legs for a club still mid-tie (1.0 per leg, the
    halved rate), and remaining League Phase fixtures for a club already
    confirmed into it (2.0 per game, full rate) -- both are published by
    the provider ahead of time, so "how many games has this specific club
    got left here" is a real, exact count, not a guess. Only the
    knockout stage (Knockout Play-off through Final) falls back to a
    flat, deliberately generous ceiling for any club not yet eliminated
    from the whole competition (_KO_CEILING_MATCHES worth of guaranteed
    wins + the maximum possible D.5(a) reach-bonus and D.5(b) final-rank
    bonus) -- future knockout pairings genuinely aren't published until
    the previous round concludes, so there's no real fixture list to
    count there the way there is for qualifying/League Phase. This makes
    the bound LOOSER (not wrong) for a club already deep into the
    knockout bracket than for one only just entering the League Phase --
    acceptable, since soundness (never claiming a reachable rank is
    impossible) matters more than tightness here.

    A club eliminated from a competition's qualifying bracket before ever
    reaching its League Phase contributes 0 for that competition --
    there's nothing left to add. A club already alive in the League Phase
    is credited the same generous knockout ceiling as a qualifying-stage
    club, since the League Phase hasn't concluded this season yet (no
    club's knockout chances are decided one way or the other at this
    point) -- this stays correct even once the phase does conclude, since
    any club that finishes 25th-36th stops showing up in `remaining`
    fixtures entirely (nothing left to simulate), so this function
    naturally credits only genuinely live clubs regardless of season
    stage."""
    out: dict[str, float] = {}
    for comp_name in EUROPEAN_COMPETITIONS:
        played, remaining = _fetch_comp_fixtures(comp_name, api_key)
        played_ids = {f.get("idEvent") for f in played}
        all_fx = played + remaining
        clubs = {
            f.get(side) for f in all_fx for side in ("strHomeTeam", "strAwayTeam") if f.get(side)
        }
        lp_clubs = {
            f.get(side) for f in all_fx if _is_league_stage(f.get("strRound", ""))
            for side in ("strHomeTeam", "strAwayTeam") if f.get(side)
        }
        max_bonus = 4 * _BONUS_PER_STAGE[comp_name] + _league_phase_bonus(1, comp_name)
        ko_ceiling = _KO_CEILING_MATCHES * 2.0 + max_bonus

        for club in clubs:
            if club not in club_country:
                continue
            if club in lp_clubs:
                lp_remaining = sum(
                    1 for f in remaining
                    if _is_league_stage(f.get("strRound", ""))
                    and club in (f.get("strHomeTeam"), f.get("strAwayTeam"))
                )
                out[club] = out.get(club, 0.0) + 2.0 * lp_remaining + ko_ceiling
                continue
            # Not yet in the League Phase -- still alive in qualifying, or
            # already knocked out of this competition's bracket entirely.
            club_fixtures = [
                f for f in all_fx if club in (f.get("strHomeTeam"), f.get("strAwayTeam"))
            ]
            if not club_fixtures:
                continue
            eliminated = False
            qual_remaining_legs = 0
            for legs in _group_ties(club_fixtures):
                _winner, loser = _tie_result(legs, played_ids)
                if loser == club:
                    eliminated = True
                qual_remaining_legs += sum(1 for leg in legs if leg.get("idEvent") not in played_ids)
            if eliminated:
                continue
            out[club] = out.get(club, 0.0) + 1.0 * qual_remaining_legs + 2.0 * 8 + ko_ceiling
    return out


def aggregate_scalar_by_country(club_points: dict[str, float], club_country: dict[str, str]) -> dict[str, float]:
    """Same idea as aggregate_by_country, for a single scalar per club
    (max_remaining_points' own output) rather than an n_sim-shaped array."""
    totals: dict[str, float] = {}
    for club, pts in club_points.items():
        country = club_country.get(club)
        if not country:
            continue
        totals[country] = totals.get(country, 0.0) + pts
    return totals


def country_rank_bounds(
    real_points: dict[str, float], max_remaining: dict[str, float],
) -> dict[str, tuple[int, int]]:
    """{country: (best_reachable, worst_reachable)} for the 5-season
    ranking -- same sound algorithm as simulator.position_bounds (see its
    own docstring), adapted to country coefficients: floor = baseline_4yr
    + real match points already banked this season (guaranteed, no
    assumptions, already exact since real_points_from_played only counts
    played fixtures); ceiling = floor + the maximum additional points
    still mathematically reachable (max_remaining_points, already a sound
    upper bound by construction). A suspended association (clubs_entered
    == 0, e.g. Russia) has nothing to add or lose -- its floor and
    ceiling are both just the frozen 25/26 figure carried forward, same
    as build_country_rank_table's own handling.

    real_points/max_remaining are raw per-COUNTRY totals (already
    aggregated via aggregate_scalar_by_country), not yet divided by
    clubs_entered -- this function does that division itself, same as
    build_country_rank_table, so every caller passes the same raw shape."""
    countries = sorted(set(COUNTRY_BASELINE))
    floor: dict[str, float] = {}
    ceiling: dict[str, float] = {}
    for c in countries:
        base = COUNTRY_BASELINE.get(c, {})
        entered = base.get("clubs_entered", 0)
        baseline_4yr = base.get("22/23", 0.0) + base.get("23/24", 0.0) + base.get("24/25", 0.0) + base.get("25/26", 0.0)
        if entered <= 0:
            floor[c] = ceiling[c] = baseline_4yr
            continue
        real = real_points.get(c, 0.0) / entered
        extra = max_remaining.get(c, 0.0) / entered
        floor[c] = baseline_4yr + real
        ceiling[c] = baseline_4yr + real + extra

    bounds: dict[str, tuple[int, int]] = {}
    for c in countries:
        above = sum(1 for o in countries if o != c and floor[o] > ceiling[c])
        below = sum(1 for o in countries if o != c and ceiling[o] < floor[c])
        bounds[c] = (1 + above, len(countries) - below)
    return bounds


def season_rank_bounds(
    real_points: dict[str, float], max_remaining: dict[str, float],
) -> dict[str, tuple[int, int]]:
    """{country: (best_reachable, worst_reachable)} for THIS SEASON's
    coefficient alone (not the 5-season total) -- the actual metric the
    European Performance Spot race uses. Same sound floor-vs-ceiling
    algorithm as country_rank_bounds, but with no 4-season baseline to
    add (the EPS race is decided purely on this season's own points) and
    scoped to active associations only (clubs_entered > 0), matching
    season_pct_top1/season_pct_top2's own scope in build_country_rank_table
    -- a suspended association can't enter this race at all.

    This is what makes "X" for a country that can't reach 1st/2nd/Top 2
    correct in every case, not just the typical one: a country is
    guaranteed to beat another whose own floor already exceeds this
    country's ceiling, so counting how many OTHER active countries are
    guaranteed above you gives the true best-reachable rank -- equivalent
    to (and more robust than) checking only against today's actual 1st-
    and 2nd-placed countries' current points, since floor == current
    points here and countries are already ranked by current points, but
    this also stays correct for a country that's itself currently 1st or
    2nd, or when two countries are tied on current points."""
    countries = [c for c in COUNTRY_BASELINE if COUNTRY_BASELINE[c].get("clubs_entered", 0) > 0]
    floor: dict[str, float] = {}
    ceiling: dict[str, float] = {}
    for c in countries:
        entered = COUNTRY_BASELINE[c]["clubs_entered"]
        real = real_points.get(c, 0.0) / entered
        extra = max_remaining.get(c, 0.0) / entered
        floor[c] = real
        ceiling[c] = real + extra

    bounds: dict[str, tuple[int, int]] = {}
    for c in countries:
        above = sum(1 for o in countries if o != c and floor[o] > ceiling[c])
        below = sum(1 for o in countries if o != c and ceiling[o] < floor[c])
        bounds[c] = (1 + above, len(countries) - below)
    return bounds


def resolve_current_playoff_ties(comp_name: str, key: str) -> list[dict]:
    """Every Play-off round tie in `comp_name`, resolved from
    PLAYOFF_BRACKET plus already-played Qualifying Round results, with each
    leg's real play status. Simpler than european.py's general-purpose
    bracket resolver (which also has to handle a QR3 tie still being
    undecided) because right now, with all of Q1-Q3 already complete,
    every QR3 tie this feeds from IS decided -- so a side is always either
    a literal confirmed team, or a real, already-known QR3 winner/loser.

    Returns [{"team_a", "team_b", "leg1_played", "leg2_played"}, ...] --
    team_a/team_b are leg 1's home/away teams (in whichever spelling the
    real Play-off fixture itself uses, which can drift slightly from the
    QR3-resolved name, e.g. "LASK" vs "Lask Linz" -- same drift
    qualifying_projection.py's resolvers already correct for). A tie whose
    real Play-off fixture can't be found yet (not yet scheduled) is
    reported as neither leg played, so callers simulate it fully."""
    played, remaining = _fetch_comp_fixtures(comp_name, key)
    played_ids = {f.get("idEvent") for f in played}
    qr3_tie_map: dict[frozenset, list[dict]] = {}
    for f in played:
        key_ = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
        qr3_tie_map.setdefault(key_, []).append(f)
    po_tie_map: dict[frozenset, list[dict]] = {}
    for f in played + remaining:
        if f.get("strRound") not in _PLAYOFF_ROUND_NAMES:
            continue
        k = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
        po_tie_map.setdefault(k, []).append(f)

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
        legs = qr3_tie_map.get(frozenset(name_pair))
        if legs is None:
            for fpair, flegs in qr3_tie_map.items():
                if fpair & name_pair:
                    legs = flegs
                    break
        if legs is None:
            return None
        winner, loser = _tie_result(legs, played_ids)
        return winner if which == "winner" else loser

    ties: list[dict] = []
    for side_a, side_b in PLAYOFF_BRACKET.get(comp_name, []):
        a, b = _resolve_side(side_a), _resolve_side(side_b)
        if not (a and b):
            continue
        pair = frozenset({a, b})
        legs = po_tie_map.get(pair)
        if legs is None:
            for fpair, flegs in po_tie_map.items():
                if fpair & pair:
                    legs = flegs
                    break
        if legs is None:
            ties.append({"team_a": a, "team_b": b, "leg1_played": False, "leg2_played": False})
            continue
        legs = sorted(legs, key=lambda x: x.get("dateEvent", ""))
        leg1 = legs[0]
        leg2 = legs[1] if len(legs) > 1 else None
        ties.append({
            "team_a": leg1.get("strHomeTeam", a), "team_b": leg1.get("strAwayTeam", b),
            "leg1_played": leg1.get("idEvent") in played_ids,
            "leg2_played": leg2 is not None and leg2.get("idEvent") in played_ids,
        })
    return ties


def simulate_remaining_playoff_points(
    ties: list[dict],
    ratings_df: pd.DataFrame,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    n_sim: int = 3_000,
) -> dict[str, np.ndarray]:
    """Monte Carlo goal simulation (halved qualifying rate: 1 win / 0.5
    draw per leg) of whichever leg(s) of each Play-off tie haven't
    actually been played yet -- a tie already fully decided (both legs
    played for real) contributes nothing here, since its points are
    already in real_points_from_played's real total; a tie with a real
    leg 1 result only has leg 2 simulated (leg 2's own points don't depend
    on leg 1's score, so no conditioning is needed, unlike advance-
    probability elsewhere on this site). Returns {club: array(n_sim)} for
    BOTH sides of every not-fully-decided tie."""
    if not ties:
        return {}
    if "attack" not in ratings_df.columns:
        ratings_df = _opta_to_attack_defense(ratings_df)
    rat_lookup, league_avg = _build_rat_lookup(ratings_df, DEFAULT_BASE_GOALS)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)
    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)

    def _leg_pts(gh, ga):
        return np.where(gh > ga, QUAL_WIN, np.where(gh == ga, QUAL_DRAW, 0.0))

    def _lambdas(batch):
        a_att = np.array([rat_lookup.get(t["team_a"], default)[0] for t in batch])
        a_def = np.array([rat_lookup.get(t["team_a"], default)[1] for t in batch])
        b_att = np.array([rat_lookup.get(t["team_b"], default)[0] for t in batch])
        b_def = np.array([rat_lookup.get(t["team_b"], default)[1] for t in batch])
        return a_att, a_def, b_att, b_def

    result: dict[str, np.ndarray] = {}

    def _add(team, pts):
        result[team] = result.get(team, np.zeros(n_sim)) + pts

    fresh = [t for t in ties if not t["leg1_played"] and not t["leg2_played"]]
    if fresh:
        n = len(fresh)
        a_att, a_def, b_att, b_def = _lambdas(fresh)
        lam_l1_a = a_att * np.maximum(b_def, 0.01) / league_avg * home_advantage
        lam_l1_b = b_att * np.maximum(a_def, 0.01) / league_avg
        lam_l2_b = b_att * np.maximum(a_def, 0.01) / league_avg * home_advantage
        lam_l2_a = a_att * np.maximum(b_def, 0.01) / league_avg
        g_l1_a = rng.negative_binomial(np.maximum(lam_l1_a[:, None] / phi, 1e-9), p_nb, size=(n, n_sim))
        g_l1_b = rng.negative_binomial(np.maximum(lam_l1_b[:, None] / phi, 1e-9), p_nb, size=(n, n_sim))
        g_l2_a = rng.negative_binomial(np.maximum(lam_l2_a[:, None] / phi, 1e-9), p_nb, size=(n, n_sim))
        g_l2_b = rng.negative_binomial(np.maximum(lam_l2_b[:, None] / phi, 1e-9), p_nb, size=(n, n_sim))
        a_pts = _leg_pts(g_l1_a, g_l1_b) + _leg_pts(g_l2_a, g_l2_b)
        b_pts = _leg_pts(g_l1_b, g_l1_a) + _leg_pts(g_l2_b, g_l2_a)
        for i, t in enumerate(fresh):
            _add(t["team_a"], a_pts[i])
            _add(t["team_b"], b_pts[i])

    leg2_only = [t for t in ties if t["leg1_played"] and not t["leg2_played"]]
    if leg2_only:
        n = len(leg2_only)
        a_att, a_def, b_att, b_def = _lambdas(leg2_only)
        lam_l2_b = b_att * np.maximum(a_def, 0.01) / league_avg * home_advantage
        lam_l2_a = a_att * np.maximum(b_def, 0.01) / league_avg
        g_l2_a = rng.negative_binomial(np.maximum(lam_l2_a[:, None] / phi, 1e-9), p_nb, size=(n, n_sim))
        g_l2_b = rng.negative_binomial(np.maximum(lam_l2_b[:, None] / phi, 1e-9), p_nb, size=(n, n_sim))
        a_pts = _leg_pts(g_l2_a, g_l2_b)
        b_pts = _leg_pts(g_l2_b, g_l2_a)
        for i, t in enumerate(leg2_only):
            _add(t["team_a"], a_pts[i])
            _add(t["team_b"], b_pts[i])

    # Both legs already played -- fully decided, already counted in
    # real_points_from_played -- nothing to simulate.
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
    that rank in the 5-SEASON total (band cutoffs that matter in practice:
    title-race context, guaranteed extra Champions League berths, etc) --
    plus season_mean_rank, season_pct_top1, and season_pct_top2, ranked by
    THIS season's coefficient alone (not the 5-year total) among countries
    with clubs_entered > 0 only, matching how UEFA's real European
    Performance Spot race works (the two best single-season coefficients
    each get an extra Champions League place the following season) --
    suspended associations with no clubs entered can't earn anything new
    so are excluded, same as the live EPS race on this page.
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

    # EPS race: rank by THIS season's coefficient alone, active countries
    # only. totals[i] - baselines[i] recovers season_coeff without storing
    # it separately (see the loop above -- totals[i] = baselines[i] +
    # season_coeff for every country, active or suspended).
    active_idx = [i for i in range(n_countries) if clubs_entered[i] > 0]
    season_mean_rank: dict[str, float] = {}
    season_pct_top1: dict[str, float] = {}
    season_pct_top2: dict[str, float] = {}
    if active_idx:
        season_coeff_matrix = totals[active_idx] - baselines[active_idx][:, None]
        season_order = np.argsort(-season_coeff_matrix, axis=0)
        season_ranks = np.empty_like(season_order)
        n_active = len(active_idx)
        for s in range(n_sim):
            season_ranks[season_order[:, s], s] = np.arange(1, n_active + 1)
        for j, i in enumerate(active_idx):
            c = countries[i]
            season_mean_rank[c] = float(season_ranks[j].mean())
            season_pct_top1[c] = float((season_ranks[j] <= 1).mean())
            season_pct_top2[c] = float((season_ranks[j] <= 2).mean())

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
            "season_mean_rank": round(season_mean_rank[c], 2) if c in season_mean_rank else None,
            "season_pct_top1": season_pct_top1.get(c, 0.0),
            "season_pct_top2": season_pct_top2.get(c, 0.0),
        }
        for b in bands:
            row[f"pct_top{b}"] = float((ranks[i] <= b).mean())
        # Exact per-position probabilities (5-season total ranking) -- same
        # "1".."N" column shape render_prob_table expects everywhere else on
        # the site (league standings, European League Phase), for a full
        # wide finish-probability table here too, not just the cumulative
        # Top N bands above.
        for pos in range(1, n_countries + 1):
            row[str(pos)] = float((ranks[i] == pos).mean())
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
) -> tuple[pd.DataFrame, list[str], list[dict[str, np.ndarray]], dict[str, str]]:
    """Orchestrates the full predicted country ranking: real Q1-Q3 points +
    simulated Play-off/League Phase/Knockout points for all three
    competitions, combined into one rank-probability table.

    project_league_phase_field / resolve_field_ratings are european.py's
    functions (passed in rather than imported -- european.py is a
    Streamlit page script with top-level rendering code that runs
    immediately on import, so it can't be imported directly; the caller,
    which IS european.py or another page script already running in a
    Streamlit context, passes its own already-loaded functions in instead).

    Returns (table, warnings, simulated_club_points, club_country):
    - warnings lists any competition whose League Phase field wasn't fully
      known yet (so its future Play-off winners' League Phase + Knockout
      points are simply omitted for now, same graceful-degradation
      approach as League Stage Predictions).
    - simulated_club_points is the PRE-aggregation per-club version of
      `simulated_points` below (one dict per competition's Play-off round,
      one per competition's League Phase + Knockout, same {club:
      array(n_sim)} shape `aggregate_by_country` consumes) -- kept
      alongside the country-level totals instead of being discarded, so
      callers needing club-level predicted points (coefficients.py's
      Predicted Club Coefficients tab) don't have to re-run this same
      expensive simulation a second time.
    - club_country is the same {club: country} map used internally, handed
      back so callers don't need their own separate
      _load_club_country_map() call.
    """
    club_country = _load_club_country_map()
    all_played_fixtures: list[dict] = []
    simulated_points: list[dict[str, np.ndarray]] = []
    simulated_club_points: list[dict[str, np.ndarray]] = []
    warnings: list[str] = []

    for comp_name in EUROPEAN_COMPETITIONS:
        home_advantage = EUROPEAN_COMPETITIONS[comp_name]["home_advantage"]
        played, _remaining = _fetch_comp_fixtures(comp_name, api_key)
        all_played_fixtures.extend(played)

        po_ties = resolve_current_playoff_ties(comp_name, api_key)
        po_points = simulate_remaining_playoff_points(po_ties, ratings_df, home_advantage, n_sim)
        simulated_points.append(aggregate_by_country(po_points, club_country, n_sim))
        simulated_club_points.append(po_points)

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

        # Real schedule + already-decided results once known -- same
        # source european.py's own League Stage Predictions uses, and the
        # SAME shared, cached simulation call (cached_league_phase_
        # simulation), so the two pages can never disagree on the same
        # competition state. Confirmed as a real gap 2026-10-13: this used
        # to always draw a fresh synthetic schedule and ignore real
        # results entirely, even once the real League Phase draw existed
        # and real matches had been played.
        real_schedule_ready = is_opponent_list_complete(comp_name, [f["team"] for f in field])
        real_schedule = derive_fixtures(comp_name) if real_schedule_ready else None
        real_results = (
            real_league_phase_results(comp_name, api_key, tuple(f["team"] for f in field))
            if real_schedule_ready else {}
        )
        cache_key = league_phase_sim_cache_key(
            comp_name, n_sim, home_advantage, field, field_ratings_df, real_results,
        )
        _, points_by_club, _rank_points = cached_league_phase_simulation(
            cache_key, field, club_coeff, field_ratings_df,
            n_pots, opp_per_pot, n_sim, home_advantage, comp_name,
            real_schedule, real_results,
        )
        simulated_points.append(aggregate_by_country(points_by_club, club_country, n_sim))
        simulated_club_points.append(points_by_club)

    real_points = real_points_from_played(all_played_fixtures, club_country)
    table = build_country_rank_table(real_points, simulated_points, n_sim)

    # Mathematical best/worst-reachable 5-season rank per country --
    # real_points (exact, already computed above) is each country's
    # guaranteed floor; max_remaining_points' own sound upper bound gives
    # the ceiling. Attached as extra columns (not a separate return value)
    # so every existing caller/unpacking site keeps working unchanged.
    club_ceiling = max_remaining_points(club_country, api_key)
    country_ceiling_raw = aggregate_scalar_by_country(club_ceiling, club_country)
    bounds = country_rank_bounds(real_points, country_ceiling_raw)
    table["best_rank"] = [bounds.get(c, (1, len(table)))[0] for c in table.index]
    table["worst_rank"] = [bounds.get(c, (1, len(table)))[1] for c in table.index]

    # Same, for the European Performance Spot race's own season-only
    # metric (see season_rank_bounds' own docstring for why this stays
    # sound even though it's conceptually "today's Top 2 nations' current
    # points as the bar to clear").
    _season_bounds = season_rank_bounds(real_points, country_ceiling_raw)
    table["best_season_rank"] = [_season_bounds.get(c, (1, len(table)))[0] for c in table.index]
    table["worst_season_rank"] = [_season_bounds.get(c, (1, len(table)))[1] for c in table.index]

    return table, warnings, simulated_club_points, club_country
