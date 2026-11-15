"""
Pure (non-Streamlit-page) prediction engine behind european_2027_28.py's
three most expensive per-country computations: predicted final standings,
the full finishing-position probability matrix, and the predicted
domestic cup winner.

Extracted here, unchanged in logic, so build_european_2027_28_predictions.py
can run this exact same code ONCE A DAY for every tracked country and save
the result to disk, instead of european_2027_28.py re-running it live for
~50+ countries on every page load (confirmed several minutes to load,
2026-11-15) -- the same "precompute daily, page just reads the result"
pattern build_club_power_rankings.py / build_nation_power_rankings.py
already use. Importing this module (or the utility modules it in turn
imports, several of which use @st.cache_data purely as an in-memory cache)
is safe from a plain script -- unlike importing european_2027_28.py or
football_rankings.py themselves, which are Streamlit PAGE scripts whose
top-level code runs widgets and full simulations on import.
"""

from __future__ import annotations

import pandas as pd

from config import LEAGUES, DEFAULT_HOME_ADVANTAGE
from api_football_fetcher import ApiFootballClient
from ratings_manager import load_ratings
from _split_season import (
    compute_full_standings, ensure_full_roster,
    compute_expected_pts, playoff_standings, roundrobin_fixtures,
)
from simulator import simulate_season, build_live_odds_lambda_overrides
from nations_league_simulator import most_likely_group_order
from cup_predictions import resolve_predicted_cup_winner, fetch_cup_fixtures

PREDICTION_N_SIM = 1_000  # an ORDER is needed, not precise probabilities -- see below


def predicted_standings_and_probs(
    league_id: int, season: int, league_name: str, api_key: str,
) -> tuple[list[dict] | None, pd.DataFrame]:
    """(predicted final standings, full position-probability matrix) for
    one league, computed from a SINGLE simulate_season() run of the
    regular season (plus, for a true split league, a second run scoped to
    the Championship Play-off -- see the "n_champ" branch below).

    Every slot on european_2027_28.py's pages resolves against the
    PREDICTED FINAL table, not the live current-season one -- this early
    in a season (a handful of matchweeks in), the current table is noisy
    (e.g. a promoted side's hot start can sit them above clubs who'll
    finish well clear of them by May; confirmed on real data, Leeds
    showing in a Champions League slot off a small-sample current
    position). n_sim is deliberately much lower than the Predictions
    tab's own DEFAULT_N_SIMULATIONS (10,000): an ORDER is needed, not
    precise probabilities, for up to ~50 countries at once, where the
    Predictions tab only ever runs one league at a time.

    For a true split league (cfg["n_champ"] set, not a Final Four), the
    raw regular-season order is NOT the real European-slot decider --
    football_rankings.py's own "Projected Play-offs / Play-outs" ->
    "Championship Play-off" sub-simulation is (same mini round-robin among
    the n_champ teams most likely to reach it, seeded from each team's
    PROJECTED points at the split via compute_expected_pts, not today's
    raw points). Confirmed as a real bug 2026-11-15 (Greek Super League
    1): Panathinaikos led the raw regular-season simulation, but
    Olympiacos was the actual Championship Play-off favourite. Only
    positions 1..n_champ are ever resolved against this re-ranked order;
    positions beyond n_champ keep the regular-season order (confirmed
    live: every split-league country's access-list entries only ever
    reach as deep as its own n_champ, never into the Mid/Relegation
    groups), so those groups don't need their own sub-simulation here.

    Original standings rows (badges, etc.) are kept, just reordered and
    re-ranked (intRank) to the predicted finish. Returns (None, empty
    DataFrame) if the live fetch or the roster is empty."""
    client = ApiFootballClient(api_key=api_key)
    roster = client.get_standings(league_id, season)
    played, remaining = client.get_fixtures(league_id, season)
    roster = ensure_full_roster(roster, played + remaining)
    cfg = LEAGUES.get(league_name, {})
    tiebreakers = cfg.get("tiebreakers")
    standings = compute_full_standings(
        roster, played, tiebreakers=tiebreakers, points_adjustments=cfg.get("points_deductions"),
    ) if roster else roster
    if not standings:
        return standings, pd.DataFrame()
    ratings_df = load_ratings(cfg.get("tsdb_id", league_id), standings)
    home_advantage = cfg.get("home_advantage", DEFAULT_HOME_ADVANTAGE)
    live_odds_overrides = build_live_odds_lambda_overrides(remaining, ratings_df, home_advantage, league_name)
    probs = simulate_season(
        standings, remaining, ratings_df, n_sim=PREDICTION_N_SIM,
        home_advantage=home_advantage,
        tiebreakers=tiebreakers, played_fixtures=played,
        live_odds_lambda_overrides=live_odds_overrides,
    )
    if probs.empty:
        return standings, probs
    order = most_likely_group_order(probs)

    n_champ = cfg.get("n_champ")
    if n_champ and not cfg.get("final_four"):
        champ_pos = [str(i) for i in range(1, n_champ + 1) if str(i) in probs.columns]
        p_champ = probs[champ_pos].sum(axis=1) if champ_pos else None
        if p_champ is not None and len(p_champ):
            top_champ = list(p_champ.sort_values(ascending=False).index[:n_champ])
            st_lookup = {row["strTeam"]: row for row in standings}
            exp_pts = compute_expected_pts(standings, remaining, ratings_df, home_advantage)
            champ_probs = simulate_season(
                playoff_standings(top_champ, st_lookup, cfg.get("pts_factor", 1.0), exp_pts=exp_pts),
                roundrobin_fixtures(top_champ), ratings_df, n_sim=PREDICTION_N_SIM,
                home_advantage=home_advantage, tiebreakers=tiebreakers,
            )
            if not champ_probs.empty:
                champ_order = most_likely_group_order(champ_probs)
                order = champ_order + [t for t in order if t not in top_champ]

    by_team = {row["strTeam"]: row for row in standings}
    ranked = [{**by_team[t], "intRank": i} for i, t in enumerate(order, start=1) if t in by_team]
    return ranked, probs


def predict_cup_winner(league_name: str, api_key: str) -> tuple[str | None, str]:
    """(predicted winner team name, note) for one league's main domestic
    cup -- the same point-estimate engine (resolve_predicted_cup_winner:
    highest-Opta-rated team not yet eliminated from its cup) that powers
    football_rankings.py's live Cup Details tab."""
    if not api_key:
        return None, "no API key configured"
    cfg = LEAGUES.get(league_name)
    cup_id = cfg.get("cup_id") if cfg else None
    if not cfg or not cup_id:
        return None, "no cup data available for this country"
    try:
        league_season = cfg.get("af_season") or cfg["af_season"]
        season = cfg.get("cup_af_seasons", {}).get(cup_id, league_season)
        played, remaining = fetch_cup_fixtures(cup_id, season, api_key)
        ratings_df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [])
        pred_row, _pred_status, _skipped = resolve_predicted_cup_winner(
            ratings_df, played, remaining, home_advantage=cfg.get("home_advantage", 1.0)
        )
    except Exception:
        return None, "live cup fetch failed"
    alias = str(pred_row.get("alias", "")).strip()
    name = alias if alias else pred_row["team"]
    return name, "predicted cup winner — domestic cup still in progress"
