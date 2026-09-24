"""
Static competition data for the 2026-27 UEFA Nations League, sourced from
https://en.wikipedia.org/wiki/2026%E2%80%9327_UEFA_Nations_League (group
draw) — this is a fixed, already-completed draw, unlike the European club
competitions' qualifying brackets, so it's hardcoded rather than fetched
live. Russia remains suspended, so League D has only 6 teams (2 groups of
3) instead of a full complement.

League C's group composition here was corrected 2026-09-23 against
API-Football's actual fixture list (league id 5, season 2026) after
nations_league_fixtures.py came up with zero real fixtures for every
League C group -- the original Wikipedia-sourced grouping was wrong
(e.g. it had Montenegro/Cyprus in different groups; the real schedule
has them playing each other, along with Latvia and Armenia). League D's
two groups' team lists were right but swapped between the D1/D2 labels;
fixed too, though it made no functional difference (nothing here keys
off which specific group is called D1 vs D2). Re-verify against a live
fixture pull if UEFA ever reshuffles anything.

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
        "C1": ["Montenegro", "Cyprus", "Latvia", "Armenia"],
        "C2": ["Iceland", "Estonia", "Luxembourg", "Bulgaria"],
        "C3": ["Faroe Islands", "Kazakhstan", "Moldova", "Slovakia"],
        "C4": ["Albania", "Belarus", "San Marino", "Finland"],
    },
    "League D": {
        "D1": ["Azerbaijan", "Lithuania", "Liechtenstein"],
        "D2": ["Gibraltar", "Malta", "Andorra"],
    },
}

# nations_league.py display name -> flags.py FLAG_CODES key, only where they differ.
NL_FLAG_ALIASES = {
    "Turkey": "Türkiye",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Republic of Ireland": "Ireland",
}

ALL_NL_TEAMS: list[str] = [t for league in NL_GROUPS.values() for group in league.values() for t in group]

# Each league's group-stage outcome buckets, reconstructed from the
# playoff notes above (League A 3rd-place teams vs League B runners-up,
# League B 3rd-place teams vs League C runners-up, League C's two best
# 4th-place teams vs League D runners-up) plus the direct promotion/
# relegation rules -- corrected 2026-09-23 after the user caught League
# A's original version wrongly sending all four 3rd-placed teams to the
# relegation play-offs (only the bottom two, cross-group ranked, actually
# do; the top two stay safe in League A).
#
# Two rule shapes:
#   ("direct", position, label) -- every team finishing `position` in its
#     own group gets `label`, no cross-group ranking needed. Used
#     wherever a whole position column feeds a same-sized pool on the
#     other side (e.g. League B's 4 runners-up vs League A's 4-team
#     relegation pool -- clean 4-for-4, nothing to narrow).
#   ("ranked", position, n_top, label_top, n_bottom, label_bottom) --
#     the teams finishing `position` (one per group) are ranked against
#     each other by Pts/GD/GF (they never play each other, so there's no
#     head-to-head), since the destination pool is SMALLER than the
#     number of groups (e.g. League C's 4th-place teams narrow to
#     League D's 2 runners-up). label_top/label_bottom may be None for
#     "no bucket" (i.e. safe, stays in the current league).
#
# League B and D need no "ranked" rule at all -- every position feeds a
# same-sized neighbouring pool. League C's 3rd-placed teams and League
# D's bottom (3rd) place have no rule at all: they're just safe. Treat
# this reconstruction as reasoned rather than confirmed for B/C/D
# (League A's was directly corrected by the user against UEFA's own
# published tables; B/C/D follow the same documented cross-league
# playoff pairings but haven't been individually checked against
# UEFA's own ranking tables the way League A's was) -- flag it if any
# label or split looks wrong once real standings are in.
LEAGUE_OUTCOME_RULES: dict[str, list[tuple]] = {
    "League A": [
        ("direct", 1, "Quarterfinals"),
        ("direct", 2, "Quarterfinals"),
        ("ranked", 3, 2, None, 2, "Relegation Play-offs"),
        ("ranked", 4, 2, "Relegation Play-offs", 2, "Relegation to League B"),
    ],
    "League B": [
        ("direct", 1, "Promotion"),
        ("direct", 2, "Promotion Play-offs"),
        ("direct", 3, "Relegation Play-offs"),
        ("direct", 4, "Relegation to League C"),
    ],
    "League C": [
        ("direct", 1, "Promotion"),
        ("direct", 2, "Promotion Play-offs"),
        ("ranked", 4, 2, "Relegation Play-offs", 2, "Relegation to League D"),
    ],
    "League D": [
        ("direct", 1, "Promotion"),
        ("direct", 2, "Promotion Play-offs"),
    ],
}


def position_status_labels(league_name: str, n_teams: int) -> dict[int, str]:
    """Status text for each finishing position 1..n_teams in a group of
    this league, for the group table's own Status column -- derived
    straight from LEAGUE_OUTCOME_RULES so it can never drift out of sync
    with what the Predictions/Promotion & Relegation tabs actually
    compute. A "direct" rule gives a firm outcome; a "ranked" rule (whose
    fate depends on ranking against the other groups' teams in the same
    position, not just this group) is hedged the same way Wikipedia's own
    group tables word it ("Possible qualification for..." / "... or
    ..."). A position with no rule at all is simply safe."""
    labels = {pos: "Safe" for pos in range(1, n_teams + 1)}
    for rule in LEAGUE_OUTCOME_RULES[league_name]:
        if rule[0] == "direct":
            _, position, label = rule
            labels[position] = label
        else:
            _, position, n_top, label_top, n_bottom, label_bottom = rule
            if label_top and label_bottom:
                labels[position] = f"{label_top} or {label_bottom}"
            elif label_bottom:
                labels[position] = f"Possible {label_bottom}"
            elif label_top:
                labels[position] = f"Possible {label_top}"
    return labels

# Official tiebreaking order for teams level on points within a group,
# from https://en.wikipedia.org/wiki/2026%E2%80%9327_UEFA_Nations_League
# #Tiebreakers. Criteria 1-3 apply only to matches among the tied teams
# ("mini-league"); if a 3+-way tie survives all of 1-3 the article notes
# they're re-applied restricted to just the group that's still tied
# (this site's tiebreak engine already does that by construction --
# simulator._rank_group/​_split_season.rank_tied_group both re-scope the
# head-to-head sums to whichever smaller subgroup they recurse into, the
# same convention already used for every domestic league here). Criteria
# 5-9 fall back to each team's whole-group record once 1-4 are
# exhausted. Two of UEFA's eleven official criteria have NO representation
# here -- disciplinary points (needs card-by-card data this site doesn't
# fetch for any competition) and position on the UEFA access list (not a
# football result at all) -- both are vanishingly unlikely to ever be
# reached in practice (needs 5+ criteria to all tie exactly) and are
# listed in NL_TIEBREAK_RULES/the Rules tab for completeness with a note
# that they aren't applied, rather than silently pretended away.
NL_TIEBREAKERS: list[str] = ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "away_gf", "wins", "away_wins"]

# (description, implemented) for every one of UEFA's 11 official criteria,
# in order -- used to render the Rules tab. "implemented" teams whether
# NL_TIEBREAKERS (fed to simulator.py/​_split_season.py's shared tiebreak
# engine, already used for every domestic league's own standings/
# simulations on this site) actually applies that specific criterion.
NL_TIEBREAK_RULES: list[tuple[str, bool]] = [
    ("Higher number of points obtained in the matches played among the teams in question", True),
    ("Superior goal difference in matches played among the teams in question", True),
    ("Higher number of goals scored in the matches played among the teams in question", True),
    ("If more than two teams are tied and, after applying criteria 1-3, some of these teams "
     "are still tied, criteria 1-3 are reapplied exclusively to the matches between the "
     "teams still tied, to determine their final rankings", True),
    ("Superior goal difference in all group matches", True),
    ("Higher number of goals scored in all group matches", True),
    ("Higher number of away goals scored in all group matches", True),
    ("Higher number of wins in all group matches", True),
    ("Higher number of away wins in all group matches", True),
    ("Lower number of disciplinary points (1 for a single yellow card, 3 for a red card "
     "resulting from two yellow cards, 4 for a direct red card, 5 for a yellow card followed "
     "by a direct red card) in all group matches", False),
    ("Higher position in the 2026-27 UEFA Nations League access list", False),
]

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
