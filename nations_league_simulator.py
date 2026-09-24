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

import numpy as np
import pandas as pd
import streamlit as st

from config import DEFAULT_HOME_ADVANTAGE
from simulator import (
    _opta_to_attack_defense, simulate_season, fixture_odds, two_leg_advance_odds, _sort_cascade,
    _build_rat_lookup, DEFAULT_BASE_GOALS, OVERDISPERSION,
)
from nations_league_data import NL_GROUPS, ALL_NL_TEAMS, NEUTRAL_VENUE_NATIONS, NEUTRAL_VENUE_FIXTURES, NL_TIEBREAKERS

RATINGS_PATH = "ratings/nations_league_elo.csv"

# Exponent for the Elo -> attack/defense power transform (see
# simulator._opta_to_attack_defense). Kept separate from the club game's
# OPTA_K=4.0 rather than reused: that value was fit to Opta's 0-100 club
# scale, whose spread within a single domestic league is wide (e.g.
# Arsenal ~100 vs a relegation candidate ~40). Elo ratings within one
# seeded Nations League group are much closer together by construction
# (Group A1: France 2070 vs Türkiye 1852 is about as wide as League A
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


def _expected_points(
    fixtures: list[dict],
    ratings_df: pd.DataFrame,
    home_advantage: float,
    base_points: dict[str, float] | None = None,
) -> dict[str, float]:
    """Projected total points: base_points (0 for every team if not given,
    e.g. a team's real points-so-far otherwise) + 3*P(win) + 1*P(draw)
    summed across every one of `fixtures` the team plays, home or away."""
    teams = sorted({t for f in fixtures for t in (f["strHomeTeam"], f["strAwayTeam"])})
    overrides = _home_advantage_overrides(teams, home_advantage)
    odds = fixture_odds(fixtures, ratings_df, home_advantage=home_advantage, home_advantage_overrides=overrides)
    pts = {t: float((base_points or {}).get(t, 0.0)) for t in teams}
    for f, o in zip(fixtures, odds):
        pts[f["strHomeTeam"]] += 3 * o["home_win"] + o["draw"]
        pts[f["strAwayTeam"]] += 3 * o["away_win"] + o["draw"]
    return pts


def simulate_group(
    teams: list[str],
    ratings_df: pd.DataFrame,
    n_sim: int = 10_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    standings: list[dict] | None = None,
    remaining_fixtures: list[dict] | None = None,
    played_fixtures: list[dict] | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Position-probability matrix (index=team, columns "1".."n") plus
    projected points, for one group's full double round-robin.

    With no arguments beyond teams/ratings_df, simulates a fresh double
    round-robin from a blank slate (a synthetic but structurally correct
    schedule -- see _round_robin_fixtures) since the League Phase hasn't
    started yet. Once it has, callers (nations_league.py) pass the real
    current standings/remaining fixtures instead, so real results lock in
    and only what's left to play gets simulated -- same "real results +
    simulate the rest" approach used across the rest of this site."""
    group_ratings = _scoped_attack_defense(teams, ratings_df)
    fixtures = remaining_fixtures if remaining_fixtures is not None else _round_robin_fixtures(teams)
    base_standings = standings if standings is not None else _blank_standings(teams)
    overrides = _home_advantage_overrides(teams, home_advantage)
    probs = simulate_season(
        standings=base_standings, remaining_fixtures=fixtures, ratings=group_ratings,
        n_sim=n_sim, home_advantage=home_advantage, tiebreakers=NL_TIEBREAKERS,
        played_fixtures=played_fixtures, home_advantage_overrides=overrides,
    )
    base_points = {row["strTeam"]: row.get("intPoints", 0) for row in base_standings}
    exp_pts = _expected_points(fixtures, group_ratings, home_advantage, base_points)
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


# UEFA's own criteria for ranking one finishing position's four (or
# fewer) representatives -- one per group -- against each other: since
# they never play one another, criteria 1-4 (head-to-head) never apply,
# so this starts straight at NL_TIEBREAKERS' criterion 5 (overall GD),
# same order (GD, GF, away GF, wins, away wins) -- disciplinary points
# and access-list position (criteria 10-11) still aren't representable.
_CROSS_GROUP_SORT_KEY = (
    "intPoints", "intGoalDifference", "intGoalsFor", "intAwayGoalsFor", "intWin", "intAwayWin",
)


def cross_group_ranking(group_standings: dict[str, list[dict]], position: int) -> list[dict]:
    """A league's "Ranking of Nth-placed teams" table: pulls that
    finishing position's row out of each group's current standings, then
    ranks those rows against each other by Pts/GD/GF/away GF/wins/away
    wins (see _CROSS_GROUP_SORT_KEY). Each returned row is the group's
    standings row plus "group" (which group it came from)."""
    reps = []
    for gname, standings in group_standings.items():
        row = next((r for r in standings if int(r.get("intRank", 0)) == position), None)
        if row is not None:
            reps.append({**row, "group": gname})
    reps.sort(key=lambda r: tuple(-int(r.get(k, 0)) for k in _CROSS_GROUP_SORT_KEY))
    return reps


def _rule_labels(rule: tuple) -> list[str]:
    return [rule[2]] if rule[0] == "direct" else [lbl for lbl in (rule[3], rule[5]) if lbl]


# "Relegation Play-offs" (see LEAGUE_OUTCOME_RULES) is a pool, not a final
# outcome -- whichever teams land there (2 or 4, always even under every
# league's current rules) actually play a two-legged tie for a place in
# the higher-standing side of the pool's fate. simulate_league_outcomes
# below plays that tie out per replicate (using two_leg_advance_odds,
# precomputed once like simulate_league_a_knockouts' QF pairings) and
# reports these two labels instead.
_PLAYOFF_POOL_LABEL = "Relegation Play-offs"
_PLAYOFF_WIN_LABEL = "Promoted in Play-offs"
_PLAYOFF_LOSE_LABEL = "Relegated in Play-offs"


def _pair_playoff_pool(ranked_pool: list[str]) -> list[tuple[str, str]]:
    """Seeded knockout pairing (strongest vs weakest, 2nd vs 2nd-last, ...)
    for a play-off pool already ordered strongest-to-weakest by the same
    Pts/GD/GF criteria used to place these teams in the pool."""
    n = len(ranked_pool)
    return [(ranked_pool[i], ranked_pool[n - 1 - i]) for i in range(n // 2)]


def simulate_league_outcomes(
    group_states: dict[str, dict],
    outcome_rules: list[tuple],
    ratings_df: pd.DataFrame,
    n_sim: int = 8_000,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> pd.DataFrame:
    """Monte Carlo every team's chance of landing in each of its
    league's group-stage outcome buckets (Quarterfinals, Promotion,
    Relegation Play-offs, direct relegation, ... -- see
    nations_league_data.LEAGUE_OUTCOME_RULES), jointly simulating every
    group in the league per replicate so a cross-group-ranked rule (e.g.
    League A's 3rd/4th-place pools) is correctly correlated rather than
    computed from independent per-group marginals.

    group_states: {group_name: {"teams": [...], "base_stats": {team:
    {"pts","gd","gf"}}, "remaining": [fixture dicts]}} -- base_stats is
    each team's REAL points/GD/GF so far (0 if the group hasn't started,
    or reflecting manually-entered results too), remaining is whatever
    hasn't been locked in yet and gets simulated here.

    outcome_rules: ordered list of either
      ("direct", position, label) -- every team finishing `position` in
        its own group gets `label`, no cross-group ranking needed.
      ("ranked", position, n_top, label_top, n_bottom, label_bottom) --
        the teams finishing `position` (one per group) are ranked
        against each other by Pts/GD/GF; the top n_top get label_top,
        the bottom n_bottom get label_bottom. Either label may be None
        for "no bucket" (the team is simply safe).

    Returns a DataFrame indexed by team with one probability column per
    distinct label across all rules.
    """
    all_teams = [t for g in group_states.values() for t in g["teams"]]
    pts = {t: np.zeros(n_sim) for t in all_teams}
    gd = {t: np.zeros(n_sim) for t in all_teams}
    gf = {t: np.zeros(n_sim) for t in all_teams}

    rng = np.random.default_rng()
    phi = OVERDISPERSION
    p_nb = 1.0 / (1.0 + phi)
    default = (DEFAULT_BASE_GOALS, DEFAULT_BASE_GOALS)

    for gname, state in group_states.items():
        teams = state["teams"]
        for t in teams:
            base = state["base_stats"].get(t, {})
            pts[t][:] = base.get("pts", 0)
            gd[t][:] = base.get("gd", 0)
            gf[t][:] = base.get("gf", 0)

        group_ratings = _scoped_attack_defense(teams, ratings_df)
        rat_lookup, league_avg = _build_rat_lookup(group_ratings, DEFAULT_BASE_GOALS)
        overrides = _home_advantage_overrides(teams, home_advantage)

        for f in state["remaining"]:
            h, a = f["strHomeTeam"], f["strAwayTeam"]
            h_att, h_def = rat_lookup.get(h, default)
            a_att, a_def = rat_lookup.get(a, default)
            ha = overrides.get((h, a), home_advantage)
            lam_h = h_att * max(a_def, 0.01) / league_avg * ha
            lam_a = a_att * max(h_def, 0.01) / league_avg
            gh = rng.negative_binomial(max(lam_h / phi, 1e-9), p_nb, n_sim)
            ga = rng.negative_binomial(max(lam_a / phi, 1e-9), p_nb, n_sim)
            pts[h] += np.where(gh > ga, 3, np.where(gh == ga, 1, 0))
            pts[a] += np.where(ga > gh, 3, np.where(ga == gh, 1, 0))
            gd[h] += gh - ga
            gd[a] += ga - gh
            gf[h] += gh
            gf[a] += ga

    # Preserve each rule's own order of first appearance (rather than
    # alphabetical) so a league's Predictions columns read as a natural
    # best-to-worst progression -- see nations_league.py's _render_outcome_
    # predictions, which relies on column 0 being the league's best/direct
    # outcome (e.g. "Quarterfinals") to place "Stay in {league}" right
    # after it.
    labels: list[str] = []
    for rule in outcome_rules:
        for lbl in _rule_labels(rule):
            if lbl not in labels:
                labels.append(lbl)
    has_playoff_pool = _PLAYOFF_POOL_LABEL in labels
    if has_playoff_pool:
        labels = [
            lbl for orig in labels
            for lbl in ([_PLAYOFF_WIN_LABEL, _PLAYOFF_LOSE_LABEL] if orig == _PLAYOFF_POOL_LABEL else [orig])
        ]
    counts = {lbl: {t: 0 for t in all_teams} for lbl in labels}

    # Every pairing the play-off pool could possibly draw is knowable up
    # front (any of the league's own teams vs any other) and only depends
    # on the two teams' ratings, not the replicate -- precompute once
    # rather than re-running the analytical two-leg calculation inside the
    # n_sim loop (see simulate_league_a_knockouts for why that's needed).
    tie_odds: dict[tuple[str, str], float] = {}
    if has_playoff_pool:
        ko_ratings = _scoped_attack_defense(all_teams, ratings_df)
        ha_pairs = _home_advantage_overrides(all_teams, home_advantage)
        for i, t1 in enumerate(all_teams):
            for t2 in all_teams[i + 1:]:
                adv = two_leg_advance_odds(
                    t1, t2, ko_ratings,
                    home_advantage_team1=ha_pairs.get((t1, t2), home_advantage),
                    home_advantage_team2=ha_pairs.get((t2, t1), home_advantage),
                )
                tie_odds[(t1, t2)] = adv["team1_adv"]
                tie_odds[(t2, t1)] = adv["team2_adv"]

    # n_sim is only ever a few thousand and each group has just 3-4 teams,
    # so a plain per-replicate Python loop for the ranking step (goal
    # simulation above is the only part that actually needs vectorizing)
    # is simplest and still runs in a fraction of a second.
    group_items = list(group_states.items())
    for i in range(n_sim):
        order_by_group = {
            gname: sorted(state["teams"], key=lambda t: (-pts[t][i], -gd[t][i], -gf[t][i]))
            for gname, state in group_items
        }
        playoff_pool: list[tuple[str, float, float, float]] = []
        for rule in outcome_rules:
            if rule[0] == "direct":
                _, position, label = rule
                for order in order_by_group.values():
                    if position <= len(order):
                        t = order[position - 1]
                        if has_playoff_pool and label == _PLAYOFF_POOL_LABEL:
                            playoff_pool.append((t, pts[t][i], gd[t][i], gf[t][i]))
                        else:
                            counts[label][t] += 1
            else:
                _, position, n_top, label_top, n_bottom, label_bottom = rule
                reps = []
                for order in order_by_group.values():
                    if position <= len(order):
                        t = order[position - 1]
                        reps.append((t, pts[t][i], gd[t][i], gf[t][i]))
                reps.sort(key=lambda r: (-r[1], -r[2], -r[3]))
                if label_top:
                    top_reps = reps[:n_top]
                    if has_playoff_pool and label_top == _PLAYOFF_POOL_LABEL:
                        playoff_pool.extend(top_reps)
                    else:
                        for t, *_ in top_reps:
                            counts[label_top][t] += 1
                if label_bottom:
                    bottom_reps = reps[len(reps) - n_bottom:]
                    if has_playoff_pool and label_bottom == _PLAYOFF_POOL_LABEL:
                        playoff_pool.extend(bottom_reps)
                    else:
                        for t, *_ in bottom_reps:
                            counts[label_bottom][t] += 1

        if playoff_pool:
            playoff_pool.sort(key=lambda r: (-r[1], -r[2], -r[3]))
            pool_teams = [t for t, *_ in playoff_pool]
            for t1, t2 in _pair_playoff_pool(pool_teams):
                t1_wins = rng.random() < tie_odds[(t1, t2)]
                counts[_PLAYOFF_WIN_LABEL][t1 if t1_wins else t2] += 1
                counts[_PLAYOFF_LOSE_LABEL][t2 if t1_wins else t1] += 1

    rows = []
    for t in all_teams:
        row = {"team": t}
        for lbl in labels:
            row[lbl] = counts[lbl][t] / n_sim
        rows.append(row)
    return pd.DataFrame(rows).set_index("team")
