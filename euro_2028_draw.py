"""
EURO 2028 qualifying pots and draw generation (pure logic, Streamlit-free).

Kept separate from euro_2028_qualifying_draw.py (a Streamlit PAGE script)
for the same reason euro_2028_constants.py already exists: under
Streamlit's own page runner (and streamlit.testing.v1.AppTest), a page
script isn't registered in sys.modules the normal way, so another module
importing it directly causes it to be exec'd a second time, duplicating
every widget's auto-generated ID (StreamlitDuplicateElementId).
euro_2028_qualifying_odds.py's own Monte Carlo needs to call
generate_draw() thousands of times, so this had to move out of the page
to be importable at all -- the page itself now imports POTS/GROUPS_4/
GROUPS_5/generate_draw from here instead of defining them.

Pots are UEFA's own OFFICIALLY CONFIRMED final pot assignment for all 54
eligible nations (Russia remains suspended and excluded, same as
everywhere else on this site) -- confirmed against
https://en.wikipedia.org/wiki/UEFA_Euro_2028_qualifying (2026-11-18),
which as of that date shows every team resolved to a single pot (no more
"Pot 1 or Pot 2"-style transitional entries -- those were only ever
provisional ahead of the final 2026-27 Nations League table). The real
draw itself is still scheduled for 6 December 2026 in Belfast --
generate_draw() simulates that still-upcoming event, not something
that's already happened.

Format:
  - 54 teams, 12 groups (A-L). Groups A-F have 4 teams (one each from
    Pots 1-4); Groups G-L have 5 teams (one each from Pots 1-5).
  - Hosts (England, Wales, Republic of Ireland, Scotland) "will be drawn
    into separate groups" -- a direct Wikipedia quote. Northern Ireland
    is also kept out of every host's group: "All host teams, as well as
    Northern Ireland, will be drawn into different groups."
  - QF_TEAMS (the 8 Pot-1 teams that reached the real 2026-27 Nations
    League quarter-finals, a League-A-only mechanic, now fully decided:
    France, Belgium, Germany, Netherlands, England, Spain, Portugal,
    Norway) get first claim on the six 4-team-group Pot-1 slots, since
    those quarter-finals run on matchdays only the 5-team groups also
    use. Only 6 of the 8 can actually get one -- Wikipedia doesn't
    resolve this overflow, so this sim treats it as a soft preference.

Draw restrictions beyond host/NIR separation and the QF-group-of-4 rule:
Wikipedia's own Euro 2028 page confirms that political/security
prohibited pairs, excessive-travel conditions, and winter-venue
conditions all apply to this cycle too, but names no concrete
teams/pairs yet for 2028. POLITICAL_PAIRS, TRAVEL_PAIRS and
WINTER_RISK_TEAMS (euro_2028_constants.py) are carried over from the
most recent fully-resolved cycle, Euro 2024 qualifying, as the best
available precedent -- update those once UEFA names the real 2028 list.

Draw mechanics: randomized retry-until-valid (reshuffle, recheck every
constraint, redo on failure) -- the same approach this site's own
league_phase_simulator.py already uses for club-competition pot draws,
not true backtracking.
"""

import random

from simulator import seed_from_key
from euro_2028_constants import HOSTS, NIR, QF_TEAMS, POLITICAL_PAIRS, TRAVEL_PAIRS, WINTER_RISK_TEAMS

POT_1 = [
    "Spain", "Portugal", "France", "England", "Netherlands", "Greece",
    "Italy", "Belgium", "Denmark", "Germany", "Croatia", "Norway",
]
POT_2 = [
    "Wales", "Czechia", "Serbia", "Türkiye", "Switzerland", "Sweden",
    "Austria", "Bosnia and Herzegovina", "Slovenia", "Northern Ireland",
    "Hungary", "Republic of Ireland",
]
POT_3 = [
    "Kosovo", "Ukraine", "Poland", "Scotland", "Georgia", "Israel",
    "Romania", "North Macedonia", "Slovakia", "Montenegro", "Iceland", "Albania",
]
POT_4 = [
    "Belarus", "Finland", "Cyprus", "Estonia", "Bulgaria", "Luxembourg",
    "Faroe Islands", "Armenia", "Moldova", "Kazakhstan", "Latvia", "San Marino",
]
POT_5 = ["Malta", "Azerbaijan", "Lithuania", "Gibraltar", "Andorra", "Liechtenstein"]
POTS = {1: POT_1, 2: POT_2, 3: POT_3, 4: POT_4, 5: POT_5}

GROUPS_4 = list("ABCDEF")  # 6 four-team groups, fed from Pots 1-4
GROUPS_5 = list("GHIJKL")  # 6 five-team groups, fed from Pots 1-5
_MAX_ATTEMPTS = 20_000


def _split_pot1(pot1: list[str], rng: random.Random) -> tuple[list[str], list[str]]:
    """(six teams for the 4-team groups, six for the 5-team groups) --
    QF_TEAMS get first claim on the six 4-team-group slots (see module
    docstring for why only 6 of the 8 QF teams can get one)."""
    qf = [t for t in pot1 if t in QF_TEAMS]
    non_qf = [t for t in pot1 if t not in QF_TEAMS]
    rng.shuffle(qf)
    rng.shuffle(non_qf)
    ordered = qf + non_qf
    return ordered[:6], ordered[6:]


def _split_evenly(pot: list[str], rng: random.Random) -> tuple[list[str], list[str]]:
    shuffled = pot[:]
    rng.shuffle(shuffled)
    return shuffled[:6], shuffled[6:]


def _attempt_draw(rng: random.Random) -> dict[str, list[str]] | None:
    pot1_af, pot1_gl = _split_pot1(POT_1, rng)
    pot2_af, pot2_gl = _split_evenly(POT_2, rng)
    pot3_af, pot3_gl = _split_evenly(POT_3, rng)
    pot4_af, pot4_gl = _split_evenly(POT_4, rng)
    pot5_gl = POT_5[:]  # all 6 feed the 5-team groups, already exactly 6

    groups: dict[str, list[str]] = {g: [] for g in GROUPS_4 + GROUPS_5}

    for pool in (pot1_af, pot2_af, pot3_af, pot4_af):
        letters = GROUPS_4[:]
        rng.shuffle(letters)
        for team, letter in zip(pool, letters):
            groups[letter].append(team)

    for pool in (pot1_gl, pot2_gl, pot3_gl, pot4_gl, pot5_gl):
        letters = GROUPS_5[:]
        rng.shuffle(letters)
        for team, letter in zip(pool, letters):
            groups[letter].append(team)

    host_group: dict[str, str] = {}
    nir_group: str | None = None
    for letter, teams in groups.items():
        team_set = set(teams)
        for team in teams:
            if team in HOSTS:
                host_group[team] = letter
            elif team == NIR:
                nir_group = letter
        if any(pair <= team_set for pair in POLITICAL_PAIRS):
            return None
        if sum(1 for pair in TRAVEL_PAIRS if pair <= team_set) > 1:
            return None
        if sum(1 for t in teams if t in WINTER_RISK_TEAMS) > 2:
            return None

    if len(set(host_group.values())) != len(HOSTS):
        return None  # two hosts landed in the same group
    if nir_group in host_group.values():
        return None  # Northern Ireland landed with a host
    return groups


def generate_draw(seed_key: tuple) -> dict[str, list[str]]:
    """One full, constraint-satisfying draw. Retries with fresh randomness
    (same session-seeded Random instance throughout, for reproducibility
    given the same seed_key) until every constraint is met; the very last
    attempt is accepted unconditionally as a safety net, same convention
    league_phase_simulator.py's own pot-draw functions use, rather than
    ever raising on an exhausted retry budget."""
    rng = random.Random(seed_from_key(seed_key))
    result = None
    for _ in range(_MAX_ATTEMPTS):
        result = _attempt_draw(rng)
        if result is not None:
            return result
    return result or {g: [] for g in GROUPS_4 + GROUPS_5}
