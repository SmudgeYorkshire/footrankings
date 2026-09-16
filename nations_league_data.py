"""
Static competition data for the 2026-27 UEFA Nations League, sourced from
https://en.wikipedia.org/wiki/2026%E2%80%9327_UEFA_Nations_League (group
draw) — this is a fixed, already-completed draw, unlike the European club
competitions' qualifying brackets, so it's hardcoded rather than fetched
live. Russia remains suspended, so League D has only 6 teams (2 groups of
3) instead of a full complement.

Group play (Sep-Nov 2026): Leagues A/B/C are 4-team groups (double
round-robin, 6 matches/team); League D is two 3-team groups (double
round-robin, 4 matches/team).

Promotion/relegation after the group stage:
  - League A: bottom side in each group relegated to League B.
  - League B: group winners promoted to League A; bottom side relegated to C.
  - League C: group winners promoted to B; the two lowest-ranked 4th-place
    teams relegated to League D.
  - League D: group winners promoted to League C.
  - Playoffs (March 2027, not modelled here — see nations_league.py):
    League A 3rd-place teams vs League B runners-up, League B 3rd-place
    teams vs League C runners-up, League C's two best 4th-place teams vs
    League D runners-up.

League A knockout stage: the 4 group winners play the 4 runners-up
(from a different group) over two legs in the quarter-finals (Mar 2027);
the 4 winners reach the Nations League Finals (semis, 3rd-place playoff
and final, Jun 2027). UEFA's actual quarter-final draw isn't made until
after the group stage, so nations_league.py mirrors qualifying_projection's
existing "own representative draw per simulation run" approach for the
League Phase rather than guessing a fixed pairing.
"""

NL_GROUPS: dict[str, dict[str, list[str]]] = {
    "League A": {
        "A1": ["France", "Italy", "Belgium", "Turkey"],
        "A2": ["Germany", "Netherlands", "Serbia", "Greece"],
        "A3": ["Spain", "Croatia", "England", "Czechia"],
        "A4": ["Portugal", "Denmark", "Norway", "Wales"],
    },
    "League B": {
        "B1": ["Scotland", "Switzerland", "Slovenia", "North Macedonia"],
        "B2": ["Hungary", "Ukraine", "Georgia", "Northern Ireland"],
        "B3": ["Israel", "Austria", "Republic of Ireland", "Kosovo"],
        "B4": ["Poland", "Bosnia and Herzegovina", "Romania", "Sweden"],
    },
    "League C": {
        "C1": ["Iceland", "Albania", "Montenegro", "Kazakhstan"],
        "C2": ["Finland", "Slovakia", "Bulgaria", "Armenia"],
        "C3": ["Belarus", "Faroe Islands", "Cyprus", "Estonia"],
        "C4": ["Latvia", "Luxembourg", "Moldova", "San Marino"],
    },
    "League D": {
        "D1": ["Azerbaijan", "Lithuania", "Malta"],
        "D2": ["Gibraltar", "Liechtenstein", "Andorra"],
    },
}

# nations_league.py display name -> flags.py FLAG_CODES key, only where they differ.
NL_FLAG_ALIASES = {
    "Turkey": "Türkiye",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Republic of Ireland": "Ireland",
}

ALL_NL_TEAMS: list[str] = [t for league in NL_GROUPS.values() for group in league.values() for t in group]
