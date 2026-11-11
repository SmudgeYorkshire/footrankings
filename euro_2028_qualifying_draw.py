"""
2028 EURO Qualifying Draw simulator.

Pots are the user-provided predicted pot assignments (derived from the
interim 2026-27 UEFA Nations League ranking, per UEFA's own stated
seeding criterion) for all 54 eligible nations (Russia remains suspended
and excluded, same as everywhere else on this site) -- confirmed against
https://en.wikipedia.org/wiki/UEFA_Euro_2028_qualifying (2026-11-11) for
the parts that page actually commits to:

  - 54 teams, 12 groups (A-L). Groups A-F have 4 teams (one each from
    Pots 1-4); Groups G-L have 5 teams (one each from Pots 1-5). The
    page doesn't state this split explicitly, but it's the only way
    6x4 + 6x5 = 54 works out, and it matches Pot 5 (shown as "Groups
    G-L", i.e. a 6-team pot that only ever feeds the six 5-team groups).
  - Hosts (England, Wales, Republic of Ireland, Scotland) "will be drawn
    into separate groups" -- a direct quote. Northern Ireland is also
    kept out of every host's group: "All host teams, as well as Northern
    Ireland, will be drawn into different groups."
  - Teams predicted to reach the real 2026-27 Nations League quarter-
    finals (8 teams, all Pot 1 in this snapshot -- NL quarter-finals are
    a League A-only mechanic, 8 teams) need a 4-team group specifically,
    since those quarter-finals run on matchdays that only the 5-team
    groups also use ("drawn into groups of four, because those quarter-
    finals run alongside matchdays 1 and 2, which only five-team groups
    play"). Only 6 of the 8 can actually get one, since only 6 four-team
    groups exist -- Wikipedia doesn't resolve this overflow, so this sim
    treats it as a soft preference: the six 4-team-group Pot 1 slots are
    filled from the QF-tagged teams first, with the 2 unlucky leftovers
    (and the 4 plain Pot 1 teams) landing in 5-team groups instead.
  - Wikipedia mentions further conditions (other political/security
    restrictions, Nations League promotion/relegation play-off
    scheduling, winter travel) without ever naming concrete pairs or
    rules for THIS cycle, so none of those are modeled here -- only the
    two explicit, concretely-stated rules above (host/NIR separation,
    QF-team group size) are enforced.

Draw mechanics: randomized retry-until-valid (reshuffle, recheck the
host/NIR constraint, redo on failure) -- the same approach this site's
own league_phase_simulator.py already uses for club-competition pot
draws, not true backtracking. A session-state-keyed redraw button
produces a fresh, reproducible-until-the-next-click seed via
simulator.seed_from_key, same convention used across this site's other
simulations.
"""

import random

import streamlit as st
import pandas as pd

from flags import flag_url
from nations_league_data import NL_FLAG_ALIASES
from simulator import seed_from_key


def _flag(team: str) -> str:
    return flag_url(NL_FLAG_ALIASES.get(team, team))


st.title("🎲 2028 EURO Qualifying Draw")
st.caption(
    "Simulates the UEFA Euro 2028 qualifying group draw from predicted pots (interim "
    "2026-27 Nations League ranking). Format rules sourced from "
    "[Wikipedia](https://en.wikipedia.org/wiki/UEFA_Euro_2028_qualifying) -- see this "
    "page's own module docstring for exactly which rules are modeled and which aren't "
    "yet confirmed for this cycle."
)

# ---------------------------------------------------------------------------
# Pots -- team: (tags,)  "Host" / "QF" (predicted Nations League
# quarter-finalist) / "Play-off" (Nations League promotion/relegation
# play-off participant, informational only -- no concrete draw rule is
# tied to it on the Wikipedia page) / "NIR" (Northern Ireland, kept apart
# from every host but not itself a host).
# ---------------------------------------------------------------------------
POT_1 = [
    ("Spain", ("QF",)), ("Portugal", ("QF",)), ("France", ("QF",)),
    ("England", ("Host", "QF")), ("Netherlands", ("QF",)), ("Greece", ("QF",)),
    ("Italy", ()), ("Belgium", ("QF",)), ("Denmark", ("QF",)),
    ("Germany", ()), ("Croatia", ()), ("Norway", ("Play-off",)),
]
POT_2 = [
    ("Wales", ("Host", "Play-off")), ("Czechia", ()), ("Serbia", ("Play-off",)),
    ("Türkiye", ()), ("Switzerland", ()), ("Sweden", ()),
    ("Austria", ()), ("Bosnia and Herzegovina", ("Play-off",)), ("Slovenia", ("Play-off",)),
    ("Northern Ireland", ("NIR",)), ("Hungary", ("Play-off",)), ("Republic of Ireland", ("Host", "Play-off")),
]
POT_3 = [
    ("Kosovo", ()), ("Ukraine", ()), ("Poland", ()),
    ("Scotland", ("Host",)), ("Georgia", ("Play-off",)), ("Israel", ()),
    ("Romania", ()), ("North Macedonia", ("Play-off",)), ("Slovakia", ()),
    ("Montenegro", ()), ("Iceland", ()), ("Albania", ()),
]
POT_4 = [
    ("Belarus", ("Play-off",)), ("Finland", ()), ("Cyprus", ("Play-off",)),
    ("Estonia", ()), ("Bulgaria", ()), ("Luxembourg", ()),
    ("Faroe Islands", ("Play-off",)), ("Armenia", ()), ("Moldova", ()),
    ("Kazakhstan", ()), ("Latvia", ()), ("San Marino", ()),
]
POT_5 = [
    ("Malta", ()), ("Azerbaijan", ()), ("Lithuania", ()),
    ("Gibraltar", ()), ("Andorra", ()), ("Liechtenstein", ()),
]
POTS = {1: POT_1, 2: POT_2, 3: POT_3, 4: POT_4, 5: POT_5}

HOSTS = {"England", "Wales", "Republic of Ireland", "Scotland"}
NIR = "Northern Ireland"
GROUPS_4 = list("ABCDEF")  # 6 four-team groups, fed from Pots 1-4
GROUPS_5 = list("GHIJKL")  # 6 five-team groups, fed from Pots 1-5
_MAX_ATTEMPTS = 2_000


def _split_pot1(pot1: list[tuple], rng: random.Random) -> tuple[list[tuple], list[tuple]]:
    """(six teams for the 4-team groups, six for the 5-team groups) --
    QF-tagged teams get first claim on the six 4-team-group slots (see
    module docstring for why only 6 of the 8 QF teams can get one)."""
    qf = [t for t in pot1 if "QF" in t[1]]
    non_qf = [t for t in pot1 if "QF" not in t[1]]
    rng.shuffle(qf)
    rng.shuffle(non_qf)
    ordered = qf + non_qf
    return ordered[:6], ordered[6:]


def _split_evenly(pot: list[tuple], rng: random.Random) -> tuple[list[tuple], list[tuple]]:
    shuffled = pot[:]
    rng.shuffle(shuffled)
    return shuffled[:6], shuffled[6:]


def _attempt_draw(rng: random.Random) -> dict[str, list[tuple]] | None:
    pot1_af, pot1_gl = _split_pot1(POT_1, rng)
    pot2_af, pot2_gl = _split_evenly(POT_2, rng)
    pot3_af, pot3_gl = _split_evenly(POT_3, rng)
    pot4_af, pot4_gl = _split_evenly(POT_4, rng)
    pot5_gl = POT_5[:]  # all 6 feed the 5-team groups, already exactly 6

    groups: dict[str, list[tuple]] = {g: [] for g in GROUPS_4 + GROUPS_5}

    for pool in (pot1_af, pot2_af, pot3_af, pot4_af):
        letters = GROUPS_4[:]
        rng.shuffle(letters)
        for team_tags, letter in zip(pool, letters):
            groups[letter].append(team_tags)

    for pool in (pot1_gl, pot2_gl, pot3_gl, pot4_gl, pot5_gl):
        letters = GROUPS_5[:]
        rng.shuffle(letters)
        for team_tags, letter in zip(pool, letters):
            groups[letter].append(team_tags)

    host_group: dict[str, str] = {}
    nir_group: str | None = None
    for letter, teams in groups.items():
        for team, _tags in teams:
            if team in HOSTS:
                host_group[team] = letter
            elif team == NIR:
                nir_group = letter

    if len(set(host_group.values())) != len(HOSTS):
        return None  # two hosts landed in the same group
    if nir_group in host_group.values():
        return None  # Northern Ireland landed with a host
    return groups


def generate_draw(seed_key: tuple) -> dict[str, list[tuple]]:
    """One full, constraint-satisfying draw. Retries with fresh randomness
    (same session-seeded Random instance throughout, for reproducibility
    given the same seed_key) until the host/NIR separation rule is met;
    the very last attempt is accepted unconditionally as a safety net,
    same convention league_phase_simulator.py's own pot-draw functions
    use, rather than ever raising on an exhausted retry budget."""
    rng = random.Random(seed_from_key(seed_key))
    result = None
    for _ in range(_MAX_ATTEMPTS):
        result = _attempt_draw(rng)
        if result is not None:
            return result
    return result or {g: [] for g in GROUPS_4 + GROUPS_5}


# ---------------------------------------------------------------------------
# Pots display
# ---------------------------------------------------------------------------
st.markdown("### Predicted Pots")
_pot_cols = st.columns(5)
for _pot_num, _col in zip(POTS, _pot_cols):
    with _col:
        st.markdown(f"**POT {_pot_num}**")
        _rows = [
            {
                "Flag": _flag(team),
                "Team": team,
                "Tags": ", ".join(tags) if tags else "",
            }
            for team, tags in POTS[_pot_num]
        ]
        _df = pd.DataFrame(_rows)
        st.dataframe(
            _df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Tags": st.column_config.TextColumn("Tags", width="small"),
            },
            width="content", hide_index=True, height=len(_df) * 35 + 38,
        )

st.divider()

# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
st.markdown("### Run the draw")
st.caption(
    "Each click produces a fresh, valid draw (hosts in separate groups, Northern Ireland "
    "apart from every host). Groups A-F have 4 teams (Pots 1-4); Groups G-L have 5 "
    "(Pots 1-5)."
)
_ver_key = "euro2028_draw_version"
if _ver_key not in st.session_state:
    st.session_state[_ver_key] = 0

if st.button("🎲  Run the draw", type="primary", use_container_width=True):
    st.session_state[_ver_key] += 1

if st.session_state[_ver_key] == 0:
    st.info("Press **🎲 Run the draw** to simulate the group draw.")
else:
    _groups = generate_draw(("euro2028_draw", st.session_state[_ver_key]))
    _team_to_pot = {t: p for p, teams in POTS.items() for t, _tags in teams}

    def _render_group(letter: str) -> None:
        st.markdown(f"**Group {letter}**")
        rows = [
            {"Flag": _flag(team), "Team": team, "Pot": _team_to_pot.get(team),
             "Tags": ", ".join(tags) if tags else ""}
            for team, tags in _groups[letter]
        ]
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Pot": st.column_config.NumberColumn("Pot", width="small"),
                "Tags": st.column_config.TextColumn("Tags", width="small"),
            },
            width="content", hide_index=True, height=len(df) * 35 + 38,
        )

    st.divider()
    st.markdown("#### Groups A-F (4 teams)")
    _af_cols = st.columns(3)
    for _i, _letter in enumerate(GROUPS_4):
        with _af_cols[_i % 3]:
            _render_group(_letter)

    st.markdown("#### Groups G-L (5 teams)")
    _gl_cols = st.columns(3)
    for _i, _letter in enumerate(GROUPS_5):
        with _gl_cols[_i % 3]:
            _render_group(_letter)
