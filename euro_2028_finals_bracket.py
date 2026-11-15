"""
EURO 2028 FINALS tournament pipeline (pure logic, Streamlit-free) --
carries this page's qualifying-group predictions all the way to a
simulated champion, following the real UEFA Euro 2028 finals format
(en.wikipedia.org/wiki/UEFA_Euro_2028 -- a SEPARATE page from
qualifying, with its own 6 groups of 4, also labelled A-F, unrelated to
the 12 qualifying groups A-L already on this page).

Several real pieces of the 2028 finals format aren't published yet
anywhere (tie-break order, third-place ranking criteria, Pot 1-4
composition) -- this module documents each stand-in it uses inline,
same transparency convention as euro_2028_qualifying_draw.py's own
precedent-based political/travel/winter restrictions. One piece (the
Nations League-only play-off pool feeding some of the 4 "extra" finals
slots) has no data source on this site at all, so it's approximated by
the next-best qualifying runners-up instead -- see resolve_finalists.
"""

import random

import pandas as pd

import euro_2028_group_predictions as gp
from euro_2028_constants import HOSTS, NIR, POLITICAL_PAIRS

FINALS_GROUPS = list("ABCDEF")
HEAD_BY_GROUP = {"A": "Wales", "B": "England", "E": "Republic of Ireland", "F": "Scotland"}
_MAX_ATTEMPTS = 20_000

# The page's own 15-row permutation table: {qualifying 3rd-place groups}
# -> (opponent group for 1B, 1C, 1E, 1F).
THIRD_PLACE_PERMUTATION: dict[frozenset, tuple[str, str, str, str]] = {
    frozenset("ABCD"): ("A", "D", "B", "C"),
    frozenset("ABCE"): ("A", "E", "B", "C"),
    frozenset("ABCF"): ("A", "F", "B", "C"),
    frozenset("ABDE"): ("D", "E", "A", "B"),
    frozenset("ABDF"): ("D", "F", "A", "B"),
    frozenset("ABEF"): ("E", "F", "B", "A"),
    frozenset("ACDE"): ("E", "D", "C", "A"),
    frozenset("ACDF"): ("F", "D", "C", "A"),
    frozenset("ACEF"): ("E", "F", "C", "A"),
    frozenset("ADEF"): ("E", "F", "D", "A"),
    frozenset("BCDE"): ("E", "D", "B", "C"),
    frozenset("BCDF"): ("F", "D", "C", "B"),
    frozenset("BCEF"): ("F", "E", "C", "B"),
    frozenset("BDEF"): ("F", "E", "D", "B"),
    frozenset("CDEF"): ("F", "E", "D", "C"),
}


def _games_played(group_size: int) -> int:
    return 2 * (group_size - 1)


def resolve_finalists(qual_predictions: dict[str, pd.DataFrame]) -> list[dict]:
    """The 24 finals teams, each {"team", "route"}. route is one of
    "Qualifying winner" / "Qualifying runner-up" / "Host reservation" /
    "Play-off (simplified)" -- see module docstring for what the last
    two stand in for."""
    winners = []
    runners_up = []  # (team, points_per_game)
    for df in qual_predictions.values():
        games = _games_played(len(df))
        winners.append(df.iloc[0]["team"])
        runner = df.iloc[1]
        runners_up.append((runner["team"], runner["predicted_points"] / games))

    runners_up.sort(key=lambda r: -r[1])
    top8 = [t for t, _ in runners_up[:8]]
    rest = [t for t, _ in runners_up[8:]]

    finalists = [{"team": t, "route": "Qualifying winner"} for t in winners]
    finalists += [{"team": t, "route": "Qualifying runner-up"} for t in top8]
    already_in = {f["team"] for f in finalists}

    # "Two spots are held in reserve for host nations that fail to
    # qualify... if more than two hosts fail, spots are allocated by
    # qualifying ranking" -- rank any missing host by its own actual
    # finishing position in its qualifying group (winner < runner-up <
    # 3rd < ...), points-per-game as the tiebreak within the same
    # position. Iterating a set (HOSTS) has no defined order on its
    # own, so this key must fully determine the sort -- it always does,
    # since every finalist candidate appears in exactly one group table.
    def _host_rank_key(team: str) -> tuple[int, float]:
        for df in qual_predictions.values():
            teams = df["team"].tolist()
            if team in teams:
                pos = teams.index(team)
                games = _games_played(len(df))
                return (pos, -df.iloc[pos]["predicted_points"] / games)
        return (len(qual_predictions) + 1, 0.0)

    missing_hosts = sorted((h for h in HOSTS if h not in already_in), key=_host_rank_key)
    for h in missing_hosts[:2]:
        finalists.append({"team": h, "route": "Host reservation"})
        already_in.add(h)

    # Remaining slots (always just enough to reach 24) stand in for the
    # real play-off pool, which also includes Nations League teams this
    # site has no data for -- the next-best qualifying runners-up are
    # the most defensible substitute available.
    slots_left = 24 - len(finalists)
    for t in rest:
        if slots_left <= 0:
            break
        if t in already_in:
            continue
        finalists.append({"team": t, "route": "Play-off (simplified)"})
        already_in.add(t)
        slots_left -= 1

    return finalists


def build_finals_pots(
    finalists: list[dict], ratings: dict[str, float],
) -> tuple[dict[int, list[str]], dict[str, str | None]]:
    """Returns (pots, head_assignment). head_assignment maps each of the
    6 Finals groups to its fixed head team, or to None for a group whose
    head is drawn randomly from Pot 1's extra member(s) -- always Group
    C; also Group D whenever Northern Ireland isn't one of the 24; and,
    in the rare case a designated host itself misses out on all 24
    slots (only possible if 3+ hosts fail direct qualification at once,
    since only 2 reserved spots exist), that host's own group too --
    only ever treat a team as a fixed head if it's actually a finalist,
    otherwise draw_finals_groups would place a non-finalist into a
    group and simulate_finals would have no rating/route for it."""
    finalist_teams = {f["team"] for f in finalists}

    head_assignment: dict[str, str | None] = {
        g: (head if head in finalist_teams else None) for g, head in HEAD_BY_GROUP.items()
    }
    head_assignment["D"] = NIR if NIR in finalist_teams else None
    head_assignment["C"] = None

    n_extra_pot1 = sum(1 for h in head_assignment.values() if h is None)
    fixed_heads = {h for h in head_assignment.values() if h}
    remaining = [f["team"] for f in finalists if f["team"] not in fixed_heads]
    remaining.sort(key=lambda t: -gp.team_rating(t, ratings))

    pot1 = list(fixed_heads) + remaining[:n_extra_pot1]
    rest = remaining[n_extra_pot1:]
    pots = {1: pot1}
    for i in range(3):
        pots[i + 2] = rest[i * 6:(i + 1) * 6]
    return pots, head_assignment


def _attempt_finals_draw(
    pots: dict[int, list[str]], head_assignment: dict[str, str | None], rng: random.Random,
) -> dict[str, list[str]] | None:
    groups: dict[str, list[str]] = {g: [] for g in FINALS_GROUPS}

    for g, h in head_assignment.items():
        if h:
            groups[g].append(h)

    fixed_heads = {h for h in head_assignment.values() if h}
    extra_pot1 = [t for t in pots[1] if t not in fixed_heads]
    random_head_groups = [g for g, h in head_assignment.items() if h is None]
    shuffled_extra = extra_pot1[:]
    rng.shuffle(shuffled_extra)
    shuffled_groups = random_head_groups[:]
    rng.shuffle(shuffled_groups)
    for team, g in zip(shuffled_extra, shuffled_groups):
        groups[g].append(team)

    for pot_num in (2, 3, 4):
        pool = pots[pot_num][:]
        rng.shuffle(pool)
        letters = FINALS_GROUPS[:]
        rng.shuffle(letters)
        for team, letter in zip(pool, letters):
            groups[letter].append(team)

    for teams in groups.values():
        team_set = set(teams)
        if any(pair <= team_set for pair in POLITICAL_PAIRS):
            return None
    return groups


def draw_finals_groups(
    pots: dict[int, list[str]], head_assignment: dict[str, str | None], seed: int | None = None,
) -> dict[str, list[str]]:
    """One full, constraint-satisfying Finals draw. Host separation is
    automatic by construction (each host is already a different group's
    fixed head) -- the only retry condition is POLITICAL_PAIRS, reused
    from euro_2028_qualifying_draw.py rather than duplicated. Travel and
    winter-venue restrictions are NOT reused here -- both were about
    spreading 2027's qualifying fixtures across many matchdays/venues;
    the finals are a single short tournament entirely within England/
    Wales/Scotland/Northern Ireland/Republic of Ireland, so neither
    concern applies."""
    rng = random.Random(seed)
    result = None
    for _ in range(_MAX_ATTEMPTS):
        result = _attempt_finals_draw(pots, head_assignment, rng)
        if result is not None:
            return result
    return result or {g: [] for g in FINALS_GROUPS}


def simulate_knockout_match(
    team_a: str, team_b: str, ratings: dict[str, float], rng: random.Random,
) -> str:
    """Winner after 90 minutes, or (if level) the extra-time-then-
    penalties outcome -- modeled as a straight 50/50 split of the draw
    probability, since shoot-outs are close to a coin flip regardless of
    team strength. Neutral probabilities (no home advantage) -- see
    euro_2028_group_predictions.neutral_match_probabilities's own
    docstring for why."""
    p_a, p_draw, _p_b = gp.neutral_match_probabilities(
        gp.team_rating(team_a, ratings), gp.team_rating(team_b, ratings),
    )
    return team_a if rng.random() < p_a + p_draw / 2 else team_b


def most_likely_bracket(drawn_groups: dict[str, list[str]], ratings: dict[str, float]) -> dict:
    """A single deterministic "most likely" playthrough of the finals --
    the higher-rated side at every group ranking and every knockout
    match (a drawn 50/50 split broken toward the higher-rated side) --
    a plausible path, not the probability-weighted outcome simulate_finals
    produces."""
    group_order = {
        letter: sorted(teams, key=lambda t: -gp.team_rating(t, ratings))
        for letter, teams in drawn_groups.items()
    }
    winner = {g: order[0] for g, order in group_order.items()}
    runner_up = {g: order[1] for g, order in group_order.items()}
    third = {g: order[2] for g, order in group_order.items()}

    third_ranked_groups = sorted(third.keys(), key=lambda g: -gp.team_rating(third[g], ratings))
    qualifying_third_groups = third_ranked_groups[:4]
    quartet = frozenset(qualifying_third_groups)
    opp_for = dict(zip("BCEF", THIRD_PLACE_PERMUTATION[quartet]))

    def third_of(letter: str) -> str:
        return third[opp_for[letter]]

    def pick(a: str, b: str) -> str:
        p_a, p_draw, _p_b = gp.neutral_match_probabilities(gp.team_rating(a, ratings), gp.team_rating(b, ratings))
        return a if p_a + p_draw / 2 >= 0.5 else b

    r16 = {
        "M37": pick(winner["A"], runner_up["C"]),
        "M38": pick(runner_up["A"], runner_up["B"]),
        "M39": pick(winner["B"], third_of("B")),
        "M40": pick(winner["C"], third_of("C")),
        "M41": pick(winner["F"], third_of("F")),
        "M42": pick(runner_up["D"], runner_up["E"]),
        "M43": pick(winner["D"], runner_up["F"]),
        "M44": pick(winner["E"], third_of("E")),
    }
    qf = {
        "M45": pick(r16["M39"], r16["M37"]),
        "M46": pick(r16["M41"], r16["M42"]),
        "M47": pick(r16["M44"], r16["M43"]),
        "M48": pick(r16["M40"], r16["M38"]),
    }
    sf = {"M49": pick(qf["M45"], qf["M46"]), "M50": pick(qf["M47"], qf["M48"])}
    champion = pick(sf["M49"], sf["M50"])

    return {
        "winner": winner, "runner_up": runner_up, "third": third,
        "qualifying_third_groups": qualifying_third_groups,
        "r16": r16, "qf": qf, "sf": sf, "champion": champion,
    }


def simulate_finals(
    finalists: list[dict],
    drawn_groups: dict[str, list[str]],
    ratings: dict[str, float],
    n_sim: int = 10_000,
    seed: int | None = None,
) -> pd.DataFrame:
    """Monte Carlo the finals group stage AND the knockout bracket
    together n_sim times (neither is fixed given the draw). Returns one
    row per team: team, group, p_win_group, p_r16, p_qf, p_sf, p_final,
    p_champion -- sorted by p_champion descending."""
    rng = random.Random(seed)
    all_teams = [f["team"] for f in finalists]
    team_group = {t: g for g, teams in drawn_groups.items() for t in teams}
    counts = {t: {"win_group": 0, "r16": 0, "qf": 0, "sf": 0, "final": 0, "champion": 0} for t in all_teams}

    for _ in range(n_sim):
        group_pts: dict[str, dict[str, int]] = {}
        group_order: dict[str, list[str]] = {}
        for letter, teams in drawn_groups.items():
            fixtures = gp.round_robin_fixtures(teams)
            pts = {t: 0 for t in teams}
            for h, a in fixtures:
                p_h, p_d, _p_a = gp.match_probabilities(
                    gp.team_rating(h, ratings), gp.team_rating(a, ratings),
                )
                r = rng.random()
                if r < p_h:
                    pts[h] += 3
                elif r < p_h + p_d:
                    pts[h] += 1
                    pts[a] += 1
                else:
                    pts[a] += 3
            group_pts[letter] = pts
            group_order[letter] = sorted(teams, key=lambda t: (-pts[t], rng.random()))

        winner = {g: order[0] for g, order in group_order.items()}
        runner_up = {g: order[1] for g, order in group_order.items()}
        third = {g: order[2] for g, order in group_order.items()}

        for t in winner.values():
            counts[t]["win_group"] += 1

        third_ranked_groups = sorted(
            third.keys(), key=lambda g: (-group_pts[g][third[g]], rng.random()),
        )
        qualifying_third_groups = third_ranked_groups[:4]
        quartet = frozenset(qualifying_third_groups)
        opp_for = dict(zip("BCEF", THIRD_PLACE_PERMUTATION[quartet]))

        def third_of(letter: str) -> str:
            return third[opp_for[letter]]

        r16 = {
            "M37": simulate_knockout_match(winner["A"], runner_up["C"], ratings, rng),
            "M38": simulate_knockout_match(runner_up["A"], runner_up["B"], ratings, rng),
            "M39": simulate_knockout_match(winner["B"], third_of("B"), ratings, rng),
            "M40": simulate_knockout_match(winner["C"], third_of("C"), ratings, rng),
            "M41": simulate_knockout_match(winner["F"], third_of("F"), ratings, rng),
            "M42": simulate_knockout_match(runner_up["D"], runner_up["E"], ratings, rng),
            "M43": simulate_knockout_match(winner["D"], runner_up["F"], ratings, rng),
            "M44": simulate_knockout_match(winner["E"], third_of("E"), ratings, rng),
        }
        r16_teams = set(winner.values()) | set(runner_up.values()) | {third[g] for g in qualifying_third_groups}
        for t in r16_teams:
            counts[t]["r16"] += 1
        for t in r16.values():
            counts[t]["qf"] += 1

        m45 = simulate_knockout_match(r16["M39"], r16["M37"], ratings, rng)
        m46 = simulate_knockout_match(r16["M41"], r16["M42"], ratings, rng)
        m47 = simulate_knockout_match(r16["M44"], r16["M43"], ratings, rng)
        m48 = simulate_knockout_match(r16["M40"], r16["M38"], ratings, rng)
        for t in (m45, m46, m47, m48):
            counts[t]["sf"] += 1

        m49 = simulate_knockout_match(m45, m46, ratings, rng)
        m50 = simulate_knockout_match(m47, m48, ratings, rng)
        for t in (m49, m50):
            counts[t]["final"] += 1

        champion = simulate_knockout_match(m49, m50, ratings, rng)
        counts[champion]["champion"] += 1

    rows = []
    for t in all_teams:
        c = counts[t]
        rows.append({
            "team": t,
            "group": team_group[t],
            "p_win_group": c["win_group"] / n_sim,
            "p_r16": c["r16"] / n_sim,
            "p_qf": c["qf"] / n_sim,
            "p_sf": c["sf"] / n_sim,
            "p_final": c["final"] / n_sim,
            "p_champion": c["champion"] / n_sim,
        })
    return pd.DataFrame(rows).sort_values("p_champion", ascending=False).reset_index(drop=True)
