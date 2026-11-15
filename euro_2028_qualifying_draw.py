"""
2028 EURO Qualifying Draw simulator.

Pots are the user's own definite, final predicted pot assignment for all
54 eligible nations (Russia remains suspended and excluded, same as
everywhere else on this site), resolving every one of UEFA's 3
"transitional pot" overlaps (Croatia/Czechia, Kosovo/Republic of
Ireland/Scotland/Slovenia, Albania/Belarus/Estonia/Iceland) into a
single fixed pot each -- confirmed against
https://en.wikipedia.org/wiki/UEFA_Euro_2028_qualifying (2026-11-16) for
the parts that page actually commits to. This is a manually-edited
snapshot, not a live-recomputed one -- update it by hand as the real
2026-27 Nations League table (and so the real pot seeding) develops.

Format:
  - 54 teams, 12 groups (A-L). Groups A-F have 4 teams (one each from
    Pots 1-4); Groups G-L have 5 teams (one each from Pots 1-5).
  - Hosts (England, Wales, Republic of Ireland, Scotland) "will be drawn
    into separate groups" -- a direct Wikipedia quote. Northern Ireland
    is also kept out of every host's group: "All host teams, as well as
    Northern Ireland, will be drawn into different groups."
  - QF_TEAMS (8 Pot-1 teams predicted to reach the real 2026-27 Nations
    League quarter-finals, a League-A-only mechanic) get first claim on
    the six 4-team-group Pot-1 slots, since those quarter-finals run on
    matchdays only the 5-team groups also use. Only 6 of the 8 can
    actually get one -- Wikipedia doesn't resolve this overflow, so this
    sim treats it as a soft preference, same as before.

Draw restrictions beyond host/NIR separation and the QF-group-of-4 rule:
Wikipedia's own Euro 2028 page confirms that political/security
prohibited pairs, excessive-travel conditions, and winter-venue
conditions all apply to this cycle too, but (as of 2026-11-16) names no
concrete teams/pairs yet for 2028. POLITICAL_PAIRS, TRAVEL_PAIRS and
WINTER_RISK_TEAMS below are carried over from the most recent fully-
resolved cycle, Euro 2024 qualifying (every team involved is still a
UEFA-eligible 2028 Pot 1-5 nation), as the best available precedent --
update these once UEFA names the real 2028 list:
  - POLITICAL_PAIRS (hard constraint): Euro 2024's own 5 named
    "prohibited clash" pairs.
  - TRAVEL_PAIRS (soft constraint, max 1 such pair per group): Euro
    2024's own named excessive-travel pairings.
  - WINTER_RISK_TEAMS (soft constraint, max 2 such teams per group):
    Euro 2024's own named high/medium winter-risk-venue teams.

Draw mechanics: randomized retry-until-valid (reshuffle, recheck every
constraint, redo on failure) -- the same approach this site's own
league_phase_simulator.py already uses for club-competition pot draws,
not true backtracking. A session-state-keyed redraw button produces a
fresh, reproducible-until-the-next-click seed via simulator.seed_from_key,
same convention used across this site's other simulations.

Once a draw exists, "Predict all groups" simulates every group's
round-robin from today's Nation Strength Rankings (nation_power_rankings.csv)
via euro_2028_group_predictions.py's lightweight classic-Elo model --
see that module's own docstring for why it doesn't reuse the Opta-goal
Poisson engine.
"""

import random

import streamlit as st
import pandas as pd

from flags import flag_url
from nations_league_data import NL_FLAG_ALIASES
from simulator import seed_from_key
import euro_2028_group_predictions as gp


def _flag(team: str) -> str:
    return flag_url(NL_FLAG_ALIASES.get(team, team))


st.title("🎲 2028 EURO Qualifying Draw")
st.caption(
    "Simulates the UEFA Euro 2028 qualifying group draw from predicted pots (interim "
    "2026-27 Nations League ranking). Format rules sourced from "
    "[Wikipedia](https://en.wikipedia.org/wiki/UEFA_Euro_2028_qualifying); the "
    "political/security, travel and winter-venue restrictions are carried over from "
    "[Euro 2024 qualifying](https://en.wikipedia.org/wiki/UEFA_Euro_2024_qualifying)'s "
    "own named list as the best available precedent, pending UEFA's official 2028 "
    "confirmation -- see this page's own module docstring for the full breakdown."
)

# ---------------------------------------------------------------------------
# Pots -- definite, manually-edited entries (one nation per slot).
# ---------------------------------------------------------------------------
POT_1 = [
    "Spain", "Portugal", "France", "England", "Netherlands", "Greece",
    "Italy", "Belgium", "Denmark", "Germany", "Croatia", "Norway",
]
POT_2 = [
    "Wales", "Czechia", "Serbia", "Türkiye", "Switzerland", "Sweden",
    "Austria", "Bosnia and Herzegovina", "Slovenia", "Northern Ireland",
    "Hungary", "Kosovo",
]
POT_3 = [
    "Republic of Ireland", "Ukraine", "Poland", "Scotland", "Georgia", "Israel",
    "Romania", "North Macedonia", "Slovakia", "Montenegro", "Iceland", "Albania",
]
POT_4 = [
    "Belarus", "Finland", "Cyprus", "Estonia", "Bulgaria", "Luxembourg",
    "Faroe Islands", "Armenia", "Moldova", "Kazakhstan", "Latvia", "San Marino",
]
POT_5 = ["Malta", "Azerbaijan", "Lithuania", "Gibraltar", "Andorra", "Liechtenstein"]
POTS = {1: POT_1, 2: POT_2, 3: POT_3, 4: POT_4, 5: POT_5}

HOSTS = {"England", "Wales", "Republic of Ireland", "Scotland"}
NIR = "Northern Ireland"
QF_TEAMS = {"Spain", "Portugal", "France", "England", "Netherlands", "Greece", "Belgium", "Denmark"}

# Euro 2024 qualifying's own named "prohibited clash" pairs (political/security).
POLITICAL_PAIRS = {
    frozenset({"Armenia", "Azerbaijan"}),
    frozenset({"Belarus", "Ukraine"}),
    frozenset({"Gibraltar", "Spain"}),
    frozenset({"Kosovo", "Bosnia and Herzegovina"}),
    frozenset({"Kosovo", "Serbia"}),
}
# Euro 2024 qualifying's own named excessive-travel pairings (max 1 per group).
TRAVEL_PAIRS = {
    frozenset({"Azerbaijan", "Gibraltar"}),
    frozenset({"Azerbaijan", "Iceland"}),
    frozenset({"Azerbaijan", "Portugal"}),
    frozenset({"Iceland", "Cyprus"}),
    frozenset({"Iceland", "Georgia"}),
    frozenset({"Iceland", "Israel"}),
    frozenset({"Kazakhstan", "Andorra"}),
    frozenset({"Kazakhstan", "England"}),
    frozenset({"Kazakhstan", "France"}),
    frozenset({"Kazakhstan", "Gibraltar"}),
    frozenset({"Kazakhstan", "Iceland"}),
    frozenset({"Kazakhstan", "Malta"}),
    frozenset({"Kazakhstan", "Northern Ireland"}),
    frozenset({"Kazakhstan", "Portugal"}),
    frozenset({"Kazakhstan", "Republic of Ireland"}),
    frozenset({"Kazakhstan", "Scotland"}),
    frozenset({"Kazakhstan", "Spain"}),
    frozenset({"Kazakhstan", "Wales"}),
}
# Euro 2024 qualifying's own named high/medium winter-risk-venue teams (max 2 per group).
WINTER_RISK_TEAMS = {
    "Belarus", "Estonia", "Faroe Islands", "Finland", "Iceland", "Latvia", "Lithuania", "Norway",
}

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


# ---------------------------------------------------------------------------
# Pots display
# ---------------------------------------------------------------------------
st.markdown("### Predicted Pots")
_pot_cols = st.columns(5)
for _pot_num, _col in zip(POTS, _pot_cols):
    with _col:
        st.markdown(f"**POT {_pot_num}**")
        _rows = [{"Flag": _flag(team), "Team": team} for team in POTS[_pot_num]]
        _df = pd.DataFrame(_rows)
        st.dataframe(
            _df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
            },
            width="content", hide_index=True, height=len(_df) * 35 + 38,
        )

st.divider()

# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
st.markdown("### Run the draw")
st.caption(
    "Each click produces a fresh, valid draw: hosts in separate groups, Northern "
    "Ireland apart from every host, no political/security prohibited pair together, "
    "at most 1 excessive-travel pair and at most 2 winter-risk-venue teams per group. "
    "Groups A-F have 4 teams (Pots 1-4); Groups G-L have 5 (Pots 1-5)."
)
_ver_key = "euro2028_draw_version"
if _ver_key not in st.session_state:
    st.session_state[_ver_key] = 0

if st.button("🎲  Run the draw", type="primary", use_container_width=True):
    st.session_state[_ver_key] += 1
    st.session_state.pop("euro2028_predict_clicked", None)

if st.session_state[_ver_key] == 0:
    st.info("Press **🎲 Run the draw** to simulate the group draw.")
else:
    _groups = generate_draw(("euro2028_draw", st.session_state[_ver_key]))
    _team_to_pot = {t: p for p, teams in POTS.items() for t in teams}

    def _render_group(letter: str) -> None:
        st.markdown(f"**Group {letter}**")
        rows = [
            {"Flag": _flag(team), "Team": team, "Pot": _team_to_pot.get(team)}
            for team in _groups[letter]
        ]
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Pot": st.column_config.NumberColumn("Pot", width="small"),
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

    # -----------------------------------------------------------------
    # Group predictions, from today's Nation Strength Rankings
    # -----------------------------------------------------------------
    st.divider()
    st.markdown("### Predict all groups")
    st.caption(
        "Uses today's [Nation Strength Rankings](/nation_power_rankings) combined "
        "rating to simulate each group's round-robin 10,000 times (classic-Elo "
        "win-expectancy + a symmetric draw model -- see euro_2028_group_predictions.py's "
        "own docstring for why this doesn't reuse the site's Opta-goal engine)."
    )
    _pred_key = "euro2028_predict_clicked"
    if st.button("🔮  Predict all groups", use_container_width=True):
        st.session_state[_pred_key] = True

    if st.session_state.get(_pred_key):
        _ratings = gp.load_ratings()
        if not _ratings:
            st.warning(
                "nation_power_rankings.csv isn't available yet -- predictions are "
                "falling back to a flat default rating for every team."
            )

        def _render_prediction(letter: str) -> None:
            st.markdown(f"**Group {letter}**")
            _team_rows = _groups[letter]
            _pred_df = gp.simulate_group(
                _team_rows, _ratings,
                seed=seed_from_key(("euro2028_predict", letter, st.session_state[_ver_key])),
            )
            _n = len(_team_rows)
            _rows = []
            for _pos, _row in _pred_df.iterrows():
                _team = _row["team"]
                _rows.append({
                    "Flag": _flag(_team),
                    "Team": _team,
                    "Pos": _pos + 1,
                    "Pts": round(_row["predicted_points"], 1),
                    "Top-2 %": round(100 * (_row["pos_1_prob"] + _row["pos_2_prob"]), 1) if _n >= 2 else None,
                })
            _out = pd.DataFrame(_rows)
            st.dataframe(
                _out,
                column_config={
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "Pos": st.column_config.NumberColumn("Pos", width="small"),
                    "Pts": st.column_config.NumberColumn("Pts", width="small"),
                    "Top-2 %": st.column_config.NumberColumn("Top-2 %", width="small"),
                },
                width="content", hide_index=True, height=len(_out) * 35 + 38,
            )

        st.divider()
        st.markdown("#### Groups A-F")
        _paf_cols = st.columns(3)
        for _i, _letter in enumerate(GROUPS_4):
            with _paf_cols[_i % 3]:
                _render_prediction(_letter)

        st.markdown("#### Groups G-L")
        _pgl_cols = st.columns(3)
        for _i, _letter in enumerate(GROUPS_5):
            with _pgl_cols[_i % 3]:
                _render_prediction(_letter)
