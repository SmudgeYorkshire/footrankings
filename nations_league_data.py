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

# Ukraine (since Russia's 2022 invasion) and Israel (since the war
# triggered by the October 2023 Hamas-led attack) play their UEFA "home"
# matches at a neutral venue outside their own country -- Ukraine's own
# football association confirmed Trnava, Slovakia for their 2026-27
# Nations League "home" games; Israel's are split across Hungary/Serbia/
# Cyprus depending on opponent. No real home crowd/pitch-familiarity
# advantage applies, so their nominal home fixtures should be modelled at
# parity (1.0) rather than the normal home-advantage boost -- see
# nations_league_simulator.py's home_advantage_overrides usage. Checked
# directly against real closing odds for Israel's actual Sep 27 2026
# "home" fixture vs Republic of Ireland (at Debrecen, Hungary): the
# match's odds looked internally inconsistent (summed to well under
# 100%, an oddsportal cross-bookmaker-best-price artifact rather than one
# book's own prices, the same kind of parsing noise seen elsewhere), so
# treat this as a reasoned default rather than a market-validated one --
# revisit once cleaner odds data is available for one of these fixtures.
NEUTRAL_VENUE_NATIONS = {"Ukraine", "Israel"}

# A handful of UEFA associations have privately refused to host Israel at
# all, relocating THEIR OWN home fixture against Israel specifically --
# not a blanket neutral-venue status the way Ukraine/Israel's own "home"
# games are (their other home fixtures, vs a different opponent, are
# played normally at their real ground). Republic of Ireland's home leg
# vs Israel (originally 4 Oct 2026 at the Aviv Stadium, Dublin) has been
# moved behind closed doors to a neutral venue in Serbia; Spain, Scotland,
# Slovenia and Norway have reportedly made the same private refusal but
# aren't drawn against Israel this Nations League cycle (different
# groups), so there's nothing to add for them yet. Keyed (home, away) --
# see NL_GROUPS: Israel's own reciprocal "home" leg vs Ireland is already
# covered by NEUTRAL_VENUE_NATIONS above regardless of this set.
NEUTRAL_VENUE_FIXTURES = {("Republic of Ireland", "Israel")}
