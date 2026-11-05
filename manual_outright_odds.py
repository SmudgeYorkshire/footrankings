"""
Manually-maintained outright "win the competition" odds for the European
club competitions -- comparison-only against this site's own
league_phase_simulator "won_competition" probability, same discipline
nl_odds_calibration.py already uses for its "outright" observations.

Confirmed 2026-11-04: API-Football's /odds endpoint has no outright/
futures market at all (checked all 338 bet types in /odds/bets -- every
one is a per-match market: 1X2, over/under, corners, cards, etc., nothing
season-long). There is no automatable, ToS-safe feed for this, the same
situation nl_odds_calibration.py's own module docstring already documents
for Nations League outright odds -- hence manual entry here too.

Deliberately NOT fed into any rating or prediction (unlike
nl_odds_calibration.py's outright observations, which DO nudge Elo) --
the user explicitly asked for this to stay a side-by-side comparison
against the site's own predictions, not an input that changes them.

Workflow: whenever asked to refresh this, Claude web-searches each
competition's CURRENT outright winner odds from ONE live, dated source
(not a mix of stale preview-season aggregator snippets -- confirmed
2026-11-04 that many outright-odds search results are pre-season August
previews, stale once the League Phase has real results banked), fills in
OUTRIGHT_ODDS below, and the comparison appears automatically on
european.py's Knockout Predictions tab next time it's viewed. No script
to run -- this is pure static data read directly off disk.

OUTRIGHT_ODDS[comp_name] = {
    "as_of": "YYYY-MM-DD",       # the date these prices were checked
    "source": "e.g. bet365.com", # one specific bookmaker/site, not a mix
    "odds": {team: decimal_odds, ...},  # as many runners as were priced
}
team names should match this site's own League Phase field spelling
(qualifying_bracket.CONFIRMED_LEAGUE_PHASE / club ratings CSVs) where
possible -- a near-miss raw bookmaker spelling still gets a fuzzy-match
attempt via qualifying_projection.resolve_to_team when compared, same as
real match results already do, but an exact match is always safest.
"""

OUTRIGHT_ODDS: dict[str, dict] = {
    "Champions League": {
        "as_of": "2026-11-05", "source": "bettingodds.com",
        "odds": {
            "Paris Saint-Germain": 4.55, "Real Madrid": 8.33, "Arsenal": 7.14, "Barcelona": 14.29,
            "Bayern Munich": 16.67, "Manchester City": 25.00, "Liverpool": 33.33,
            "Aston Villa": 100.00, "Como": 100.00, "Borussia Dortmund": 100.00, "Betis": 100.00,
            "Atletico Madrid": 34.00, "Inter": 41.00, "Manchester United": 51.00,
            "Sporting CP": 81.00, "Roma": 67.00, "Stuttgart": 101.00,
            "Club Brugge": 126.00, "Napoli": 101.00, "Galatasaray": 151.00,
            "Villarreal": 81.00, "Porto": 126.00, "RB Leipzig": 151.00,
            "Fenerbahce": 201.00, "PSV Eindhoven": 201.00, "Feyenoord": 126.00,
            "Bodo/Glimt": 201.00, "Shakhtar Donetsk": 201.00, "Lille": 251.00,
            "LASK": 501.00, "Viking": 501.00, "AEK Athens": 501.00,
            "Lens": 201.00, "Slavia Prague": 1001.00,
        },
    },
    "Europa League": {
        # Not today's date like the other two -- bettingodds.com's EL
        # "/winner" page is still stuck on a stale pre-season September
        # snapshot even now (confirmed again 2026-11-05, same as
        # 2026-10-22's refresh), and Squawka/Oddschecker/goal.com all
        # either blocked fetching or returned old-season content.
        # sportsbettingdime.com (DraftKings prices) was the one accessible
        # source with real current-season prices, dated by its own
        # "Last updated" line -- 11 days old, not same-day like the other
        # two, but the freshest available rather than mixing dates within
        # one competition's snapshot. Shorter list than before (16 vs 34
        # teams) since that's everything this source actually prices --
        # the missing long tail is all sub-1% mass, immaterial to the
        # de-vig of the contenders that actually matter for the nudge.
        "as_of": "2026-10-26", "source": "sportsbettingdime.com (DraftKings)",
        "odds": {
            "Benfica": 5.15, "Bayer Leverkusen": 5.55, "Bournemouth": 6.40,
            "Juventus": 7.00, "Sunderland": 15.25, "AC Milan": 17.00,
            "Besiktas": 19.00, "Real Sociedad": 20.00, "Crystal Palace": 20.00,
            "TSG Hoffenheim": 24.00, "Olympiacos": 25.00, "Lyon": 25.00,
            "Union Saint-Gilloise": 27.00, "Celta Vigo": 27.00, "Rennes": 30.00,
            "Ferencvarosi TC": 39.00,
        },
    },
    "Conference League": {
        "as_of": "2026-11-05", "source": "bettingodds.com",
        "odds": {
            "Brighton": 3.23, "Monaco": 6.67, "Atalanta": 9.09, "Ajax": 10.00,
            "Sporting Braga": 14.29, "SC Freiburg": 14.29, "Panathinaikos": 20.00,
            "Trabzonspor": 20.00, "FC Copenhagen": 20.00, "Lugano": 25.00,
            "Twente": 25.00, "FK Crvena Zvezda": 33.33, "St. Truiden": 33.33,
            "Brann": 33.33, "FC Midtjylland": 50.00, "Gent": 50.00,
            "FC Nordsjaelland": 50.00, "Hajduk Split": 100.00, "Getafe": 100.00,
        },
    },
}


def devig_outright(odds: dict[str, float]) -> dict[str, float]:
    """{team: fair/de-vigged win probability}, normalizing out the
    bookmaker's overround across ALL priced runners -- NOT the same as
    odds_validation.devig(), which is a fixed 3-way (home/draw/away)
    devig for a single match; an outright market can have anywhere from a
    handful to 30+ runners, so this normalizes proportionally across
    however many were actually priced. Runners with a non-positive or
    missing price are skipped rather than raising."""
    implied = {t: 1.0 / o for t, o in odds.items() if o and o > 0}
    total = sum(implied.values())
    if total <= 0:
        return {}
    return {t: p / total for t, p in implied.items()}
