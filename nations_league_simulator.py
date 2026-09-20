"""
Simulation engine for the 2026-27 UEFA Nations League, built on top of
simulator.py's existing Dixon-Coles/NegBin match model rather than a
separate one -- the model itself (goals from ratings, home advantage,
low-score correlation) doesn't care whether "team" means a club or a
country, only the ratings scale fed into it.

Two things ARE specific to international football and handled here:

  - Ratings come from eloratings.net (ratings/nations_league_elo.csv),
    not Opta, and are scoped per Nations League *group* (4 teams, or 3 in
    League D) rather than per domestic league -- see load_nl_ratings().
  - The group stage hasn't kicked off yet (first ball Sep 2026), so every
    group is simulated as a fresh double round-robin from a blank
    standings table, and League A's knockout stage (quarter-finals ->
    Finals Four) is layered on top using simulator.py's two_leg_advance_odds
    and fixture_odds directly.
"""

import random

import pandas as pd
import streamlit as st

from config import DEFAULT_HOME_ADVANTAGE
from simulator import (
    _opta_to_attack_defense, simulate_season, fixture_odds, two_leg_advance_odds, _sort_cascade,
)
from nations_league_data import NL_GROUPS, ALL_NL_TEAMS, NEUTRAL_VENUE_NATIONS, NEUTRAL_VENUE_FIXTURES

RATINGS_PATH = "ratings/nations_league_elo.csv"

# Exponent for the Elo -> attack/defense power transform (see
# simulator._opta_to_attack_defense). Kept separate from the club game's
# OPTA_K=4.0 rather than reused: that value was fit to Opta's 0-100 club
# scale, whose spread within a single domestic league is wide (e.g.
# Arsenal ~100 vs a relegation candidate ~40). Elo ratings within one
# seeded Nations League group are much closer together by construction
# (Group A1: France 2070 vs Turkey 1852 is about as wide as League A
# groups get, relative range only ~0.96-1.07), so a much lower exponent
# is needed to reach a comparable level of separation.
#
# Validated 2026-09-16 against 26 real Matchday 1/2 fixtures' closing 1X2
# odds from oddsportal.com (a first pass at k=3.5, checked only against
# eloratings.net's own logistic win-probability formula rather than real
# market odds, turned out a bit too aggressive): scored a Brier score
# sweep of k=1.5..6.0 at group-scoped ratings and the shipped
# home_advantage=1.20 (config.DEFAULT_HOME_ADVANTAGE -- confirmed well
# calibrated already, mean model-vs-market home-win error ~0.3pp
# regardless of k, so this was purely a k problem, not a home-advantage
# one). k=3.0 was the clear minimum (Brier 0.00777) vs k=3.5's 0.00885
# (~14% worse) and k=4.0's 0.01160; error rises on both sides of 3.0.
# Nine other "Nations League" listings on oddsportal (e.g. Montenegro vs
# Cyprus, Andorra vs Malta) paired teams from different groups entirely
# and were excluded as likely mislabelled friendlies -- they can't be
# real group-stage fixtures under UEFA's confirmed draw either way. Worth
# re-running this check (see nl_odds_check.py in conversation history)
# once more matchdays' odds are available for a bigger sample.
NATIONS_LEAGUE_K = 3.0


@st.cache_data(ttl=3_600, show_spinner=False)
def load_nl_ratings() -> pd.DataFrame:
    """Raw eloratings.net ratings for all 54 tracked nations, columns
    [team, alias, opta_rating] (Elo points; see scrape_elo_ratings.py for
    why the opta_rating name is reused)."""
    try:
        df = pd.read_csv(RATINGS_PATH, dtype={"team": str, "alias": str})
    except FileNotFoundError:
        return pd.DataFrame(columns=["team", "alias", "opta_rating"])
    df["alias"] = df["alias"].fillna("")
    df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
    return df.dropna(subset=["opta_rating"])


def _scoped_attack_defense(teams: list[str], ratings_df: pd.DataFrame) -> pd.DataFrame:
    """Opta-style attack/defense columns for exactly `teams`, with the
    relative-strength transform's mean scoped to just those teams -- e.g.
    a group's own 4 (or a whole league's 16), matching how domestic
    ratings are scoped per-league rather than across all 54 leagues at
    once (see qualifying_projection._load_ratings_by_country)."""
    scoped = ratings_df[ratings_df["team"].isin(teams)].reset_index(drop=True)
    return _opta_to_attack_defense(scoped, k=NATIONS_LEAGUE_K)


def _round_robin_fixtures(teams: list[str]) -> list[dict]:
    """Every ordered pair as a home fixture -- the double round-robin
    every Nations League group plays (n*(n-1) matches: 12 for a 4-team
    League A/B/C group, 6 for a 3-team League D group, matching the 6-
    and 4-matches-per-team the real competition uses)."""
    return [
        {"strHomeTeam": h, "strAwayTeam": a}
        for h in teams for a in teams if h != a
    ]


def _blank_standings(teams: list[str]) -> list[dict]:
    return [
        {"strTeam": t, "intRank": i + 1, "intPoints": 0, "intGoalDifference": 0, "intGoalsFor": 0}
        for i, t in enumerate(teams)
    ]


def _home_advantage_overrides(teams: list[str], home_advantage: float) -> dict[tuple[str, str], float]:
    """{(home, away): 1.0} for every one of `teams`' home fixtures that's
    actually played at a neutral venue -- either because the home team
    itself never gets to host at all (NEUTRAL_VENUE_NATIONS, e.g. every
    one of Israel's "home" games), or because this specific matchup was
    relocated even though the home team's other fixtures are normal
    (NEUTRAL_VENUE_FIXTURES, e.g. Ireland hosting Israel specifically).
    Any (home, away) pair not in this dict uses the normal home_advantage."""
    overrides = {}
    for h in teams:
        for a in teams:
            if h == a:
                continue
            if h in NEUTRAL_VENUE_NATIONS or (h, a) in NEUTRAL_VENUE_FIXTURES:
                overrides[(h, a)] = 1.0
    return overrides


def _expected_points(fixtures: list[dict], ratings_df: pd.DataFrame, home_advantage: float) -> dict[str, float]:
    """Projected total points from a blank start: 3*P(win) + 1*P(draw)
    summed across every fixture the team plays, home or away."""
    teams = sorted({t for f in fixtures for t in (f["strHomeTeam"], f["strAwayTeam"])})
    overrides = _home_advantage_overrides(teams, home_advantage)
    odds = fixture_odds(fixtures, ratings_df, home_advantage=home_advantage, home_advantage_overrides=overrides)
    pts = {t: 0.0 for t in teams}
    for f, o in zip(fixtures, odds):
        pts[f["strHomeTeam"]] += 3 * o["home_win"] + o["draw"]
        pts[f["strAwayTeam"]] += 3 * o["away_win"] + o["draw"]
    return pts


def simulate_group(
    teams: list[str],
    ratings_df: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Position-probability matrix (index=team, columns "1".."n") plus
    projected points, for one group's full double round-robin simulated
    from a blank slate (the league phase hasn't started yet)."""
    group_ratings = _scoped_attack_defense(teams, ratings_df)
    fixtures = _round_robin_fixtures(teams)
    standings = _blank_standings(teams)
    overrides = _home_advantage_overrides(teams, home_advantage)
    probs = simulate_season(
        standings=standings, remaining_fixtures=fixtures, ratings=group_ratings,
        n_sim=n_sim, home_advantage=home_advantage, tiebreakers=["gd", "gf"],
        home_advantage_overrides=overrides,
    )
    exp_pts = _expected_points(fixtures, group_ratings, home_advantage)
    return probs, exp_pts


@st.cache_data(ttl=3_600, show_spinner=False)
def simulate_league_a_knockouts(
    group_probs: dict[str, pd.DataFrame],
    ratings_df: pd.DataFrame,
    n_sim: int = 5_000,
    home_advantage: float = 1.05,
) -> pd.DataFrame:
    """Monte Carlo the quarter-finals -> Finals Four for League A.

    UEFA doesn't draw the actual QF pairings (winners vs runners-up from
    a different group) or the Finals Four bracket until after the group
    stage, so -- same approach qualifying_projection.py already uses for
    the League Phase draw before it's made -- each replicate draws its
    own valid representative pairing rather than assuming a fixed one.

    Approximation: which team finishes 1st/2nd in each group is sampled
    sequentially from that group's own marginal position probabilities
    (1st, then 2nd from the remaining teams reweighted) rather than from
    the true joint distribution, since simulate_season only returns
    marginals. Good enough to rank realistic favourites vs longshots, but
    the exact reach-Finals-Four percentages shouldn't be read as precise.

    Returns a DataFrame indexed by team with columns reached_qf (exact,
    = P(top 2 in own group)), reached_finals_four, won_competition.
    """
    group_names = list(group_probs.keys())
    all_teams = [t for g in group_names for t in group_probs[g].index]
    ko_ratings = _scoped_attack_defense(all_teams, ratings_df)

    reached_qf = {t: 0.0 for t in all_teams}
    reached_ff = {t: 0 for t in all_teams}
    won = {t: 0 for t in all_teams}

    for g in group_names:
        p = group_probs[g]
        for t in p.index:
            reached_qf[t] = float(p.loc[t, "1"] + p.loc[t, "2"])

    # Every pairing two_leg_advance_odds()/fixture_odds() could possibly be
    # asked about is knowable up front (any of the 16 teams vs any other),
    # and both only depend on the two teams' ratings -- not on the
    # replicate -- so precompute all of them once rather than re-running
    # the analytical (and fairly expensive, O(11^4)) two-leg calculation
    # inside the n_sim loop. That's what made an early version of this
    # unusably slow (thousands of replicates x 4 QF ties x 14k grid cells).
    qf_odds: dict[tuple[str, str], float] = {}
    sf_odds: dict[tuple[str, str], dict] = {}
    ha_pairs = _home_advantage_overrides(all_teams, home_advantage)
    for i, t1 in enumerate(all_teams):
        for t2 in all_teams[i + 1:]:
            adv = two_leg_advance_odds(
                t1, t2, ko_ratings,
                home_advantage_team1=ha_pairs.get((t1, t2), home_advantage),
                home_advantage_team2=ha_pairs.get((t2, t1), home_advantage),
            )
            qf_odds[(t1, t2)] = adv["team1_adv"]
            qf_odds[(t2, t1)] = adv["team2_adv"]
            # Finals Four is already single-venue/host-determined for every
            # team regardless of country, so home_advantage=1.0 here is
            # unrelated to NEUTRAL_VENUE_NATIONS -- it's neutral for everyone.
            o = fixture_odds([{"strHomeTeam": t1, "strAwayTeam": t2}], ko_ratings, home_advantage=1.0)[0]
            sf_odds[(t1, t2)] = o
            sf_odds[(t2, t1)] = {"home_win": o["away_win"], "draw": o["draw"], "away_win": o["home_win"]}

    rng = random.Random(42)

    def _sample_winner_runnerup(p: pd.DataFrame) -> tuple[str, str]:
        teams = list(p.index)
        w1 = [float(p.loc[t, "1"]) for t in teams]
        winner = rng.choices(teams, weights=w1, k=1)[0]
        remaining = [t for t in teams if t != winner]
        w2 = [max(float(p.loc[t, "2"]), 1e-6) for t in remaining]
        runner_up = rng.choices(remaining, weights=w2, k=1)[0]
        return winner, runner_up

    def _play_single_leg(h: str, a: str) -> str:
        o = sf_odds[(h, a)]
        r = rng.random()
        if r < o["home_win"]:
            return h
        if r < o["home_win"] + o["draw"]:
            return rng.choice([h, a])  # ET/pens: 50/50
        return a

    for _ in range(n_sim):
        winners: dict[str, str] = {}
        runners_up: dict[str, str] = {}
        for g in group_names:
            w, r = _sample_winner_runnerup(group_probs[g])
            winners[g] = w
            runners_up[g] = r

        # Draw QF pairings: each winner faces a runner-up from a different group.
        ru_groups = group_names[:]
        rng.shuffle(ru_groups)
        # Avoid a winner facing their own group's runner-up.
        for i, g in enumerate(group_names):
            if ru_groups[i] == g:
                j = (i + 1) % len(group_names)
                ru_groups[i], ru_groups[j] = ru_groups[j], ru_groups[i]

        qf_winners = []
        for g, ru_g in zip(group_names, ru_groups):
            home, away = winners[g], runners_up[ru_g]
            qf_winners.append(home if rng.random() < qf_odds[(home, away)] else away)

        for t in qf_winners:
            reached_ff[t] += 1

        # Finals Four: random semi-final draw, neutral-venue single matches.
        rng.shuffle(qf_winners)
        f1 = _play_single_leg(qf_winners[0], qf_winners[1])
        f2 = _play_single_leg(qf_winners[2], qf_winners[3])
        won[_play_single_leg(f1, f2)] += 1

    rows = [
        {
            "team": t,
            "reached_qf": reached_qf[t],
            "reached_finals_four": reached_ff[t] / n_sim,
            "won_competition": won[t] / n_sim,
        }
        for t in all_teams
    ]
    df = _sort_cascade(pd.DataFrame(rows), ["won_competition", "reached_finals_four", "reached_qf"])
    return df.set_index("team")
