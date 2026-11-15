"""
Pure (Streamlit-free) win/draw/loss model + round-robin Monte Carlo for
EURO 2028 qualifying groups, driven by today's Nation Strength Rankings
(nation_power_rankings.csv's combined_rating) rather than this site's
Opta-goal Poisson engine (simulator.py) -- these are plain classic-Elo
numbers (~1200-2300) with no natural mapping onto that engine's
attack/defense goal model, so a lightweight classic-Elo win/draw/loss
model is used instead. Reuses the exact win-expectancy formula and
home-advantage constant nation_odds_ratings.py/nl_odds_calibration.py
already use for odds calibration, rather than reinventing either.
"""

import random

import pandas as pd

from nation_odds_ratings import _elo_expectancy, HOME_ADVANTAGE_ELO_PTS
from scrape_elo_ratings import _NAME_ALIASES

RANKINGS_CSV = "nation_power_rankings.csv"
DEFAULT_RATING = 1500.0
# International football's roughly-average draw rate -- the draw
# probability peaks at this value when the two teams are exactly evenly
# matched (e_home == 0.5) and tapers to 0 as the mismatch grows.
DRAW_PEAK = 0.26
N_SIM = 10_000


def load_ratings() -> dict[str, float]:
    try:
        df = pd.read_csv(RANKINGS_CSV)
    except FileNotFoundError:
        return {}
    return dict(zip(df["team"], df["combined_rating"]))


def team_rating(team: str, ratings: dict[str, float]) -> float:
    return ratings.get(_NAME_ALIASES.get(team, team), DEFAULT_RATING)


def match_probabilities(home_rating: float, away_rating: float) -> tuple[float, float, float]:
    """(p_home_win, p_draw, p_away_win)."""
    e_home = _elo_expectancy(home_rating + HOME_ADVANTAGE_ELO_PTS - away_rating)
    p_draw = DRAW_PEAK * (1 - abs(2 * e_home - 1))
    p_home = e_home - p_draw / 2
    p_away = 1 - p_home - p_draw
    return p_home, p_draw, p_away


def round_robin_fixtures(teams: list[str]) -> list[tuple[str, str]]:
    """Home-and-away -- every team plays every other team twice."""
    return [(home, away) for home in teams for away in teams if home != away]


def simulate_group(
    teams: list[str], ratings: dict[str, float], n_sim: int = N_SIM, seed: int | None = None,
) -> pd.DataFrame:
    """Monte Carlo the group's round robin n_sim times. Returns one row
    per team, sorted by predicted (mean) points descending: team,
    predicted_points, pos_1_prob..pos_N_prob."""
    rng = random.Random(seed)
    fixtures = round_robin_fixtures(teams)
    probs = {
        (h, a): match_probabilities(team_rating(h, ratings), team_rating(a, ratings))
        for h, a in fixtures
    }
    n = len(teams)
    position_counts = {t: [0] * n for t in teams}
    points_total = {t: 0 for t in teams}

    for _ in range(n_sim):
        pts = {t: 0 for t in teams}
        for h, a in fixtures:
            p_h, p_d, _p_a = probs[(h, a)]
            r = rng.random()
            if r < p_h:
                pts[h] += 3
            elif r < p_h + p_d:
                pts[h] += 1
                pts[a] += 1
            else:
                pts[a] += 3
        order = sorted(teams, key=lambda t: (-pts[t], rng.random()))
        for pos, t in enumerate(order):
            position_counts[t][pos] += 1
            points_total[t] += pts[t]

    rows = []
    for t in teams:
        row = {"team": t, "predicted_points": points_total[t] / n_sim}
        for pos in range(n):
            row[f"pos_{pos + 1}_prob"] = position_counts[t][pos] / n_sim
        rows.append(row)
    return pd.DataFrame(rows).sort_values("predicted_points", ascending=False).reset_index(drop=True)
