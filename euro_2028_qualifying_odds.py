"""
Monte Carlo estimate of every nation's TRUE chance to reach the Euro
2028 finals tournament at all (not conditioned on any one sampled
draw) -- the real qualifying draw hasn't happened yet (still scheduled
6 December 2026), so which pot-mates end up in the same group is
itself part of what needs averaging over, on top of the usual match-
result randomness euro_2028_group_predictions.simulate_group already
averages within one fixed draw.

Each trial: draw the groups fresh (euro_2028_draw.generate_draw, already
constraint-valid), realize ONE round-robin outcome per group (not a
probability table -- re-deriving a full probability table inside a
single Monte Carlo trial would be its own, much slower, nested
simulation), then resolve that trial's 24 finalists with the exact same
rules euro_2028_finals_bracket.resolve_finalists uses -- ported here
(_resolve_trial_finalists) to work from one realized {team: points} per
group instead of a probability DataFrame. See euro_2028_finals_bracket.py's
own docstring for what the "Host reservation"/"Play-off (simplified)"
routes stand in for -- unchanged here, just aggregated over many draws.
"""

import random

import pandas as pd

import euro_2028_group_predictions as gp
from euro_2028_constants import HOSTS
from euro_2028_draw import POTS, generate_draw

ROUTES = ["Qualifying winner", "Qualifying runner-up", "Host reservation", "Play-off (simplified)"]
N_SIM = 5_000


def _games_played(group_size: int) -> int:
    return 2 * (group_size - 1)


def _realize_group_order(
    teams: list[str], ratings: dict[str, float], rng: random.Random,
) -> list[tuple[str, int]]:
    """One random round-robin outcome: [(team, points), ...] sorted by
    points descending, ties broken randomly for this trial -- the same
    per-fixture mechanic euro_2028_finals_bracket.simulate_finals already
    uses for its own group stage."""
    fixtures = gp.round_robin_fixtures(teams)
    pts = {t: 0 for t in teams}
    for h, a in fixtures:
        p_h, p_d, _p_a = gp.match_probabilities(gp.team_rating(h, ratings), gp.team_rating(a, ratings))
        r = rng.random()
        if r < p_h:
            pts[h] += 3
        elif r < p_h + p_d:
            pts[h] += 1
            pts[a] += 1
        else:
            pts[a] += 3
    order = sorted(teams, key=lambda t: (-pts[t], rng.random()))
    return [(t, pts[t]) for t in order]


def _resolve_trial_finalists(group_order: dict[str, list[tuple[str, int]]]) -> dict[str, str]:
    """{team: route} for this trial's 24 finalists -- ports
    euro_2028_finals_bracket.resolve_finalists's exact rules (12 winners
    direct; rank the 12 runners-up by points-per-game to take the top 8;
    host-reservation priority by real finishing position, points-per-game
    as the tiebreak; remaining slots filled by the next-best runners-up
    as the play-off stand-in) to work from one realized {team: points}
    per group instead of a probability DataFrame."""
    winners = []
    runners_up = []  # (team, points_per_game)
    for order in group_order.values():
        games = _games_played(len(order))
        winners.append(order[0][0])
        runner_team, runner_pts = order[1]
        runners_up.append((runner_team, runner_pts / games))

    runners_up.sort(key=lambda r: -r[1])
    top8 = [t for t, _ in runners_up[:8]]
    rest = [t for t, _ in runners_up[8:]]

    routes: dict[str, str] = {}
    for t in winners:
        routes[t] = "Qualifying winner"
    for t in top8:
        routes[t] = "Qualifying runner-up"
    already_in = set(routes)

    def _host_rank_key(team: str) -> tuple[int, float]:
        for order in group_order.values():
            order_teams = [t for t, _ in order]
            if team in order_teams:
                pos = order_teams.index(team)
                games = _games_played(len(order))
                return (pos, -order[pos][1] / games)
        return (len(group_order) + 1, 0.0)

    missing_hosts = sorted((h for h in HOSTS if h not in already_in), key=_host_rank_key)
    for h in missing_hosts[:2]:
        routes[h] = "Host reservation"
        already_in.add(h)

    slots_left = 24 - len(routes)
    for t in rest:
        if slots_left <= 0:
            break
        if t in already_in:
            continue
        routes[t] = "Play-off (simplified)"
        already_in.add(t)
        slots_left -= 1

    return routes


def simulate_qualifying_chances(
    ratings: dict[str, float], n_sim: int = N_SIM, seed: int | None = None,
) -> pd.DataFrame:
    """One row per of the 54 nations: team, pot, each route's probability
    (summing to "qualified"), sorted by "qualified" descending."""
    rng = random.Random(seed)
    all_teams = [t for pot in POTS.values() for t in pot]
    team_pot = {t: p for p, pot in POTS.items() for t in pot}
    counts = {t: {r: 0 for r in ROUTES} for t in all_teams}

    for i in range(n_sim):
        groups = generate_draw(("qualifying_chances", seed, i))
        group_order = {letter: _realize_group_order(teams, ratings, rng) for letter, teams in groups.items()}
        routes = _resolve_trial_finalists(group_order)
        for t, route in routes.items():
            counts[t][route] += 1

    rows = []
    for t in all_teams:
        c = counts[t]
        row = {"team": t, "pot": team_pot[t]}
        for r in ROUTES:
            row[r] = c[r] / n_sim
        row["qualified"] = sum(c[r] for r in ROUTES) / n_sim
        rows.append(row)
    return pd.DataFrame(rows).sort_values("qualified", ascending=False).reset_index(drop=True)
