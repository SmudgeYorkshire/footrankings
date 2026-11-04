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
        "as_of": "2026-11-04", "source": "bettingodds.com",
        "odds": {
            "Paris Saint-Germain": 4.50, "Real Madrid": 9.00, "Barcelona": 4.50, "Arsenal": 6.50,
            "Bayern Munich": 7.00, "Liverpool": 21.00, "Manchester City": 11.00,
            "Aston Villa": 51.00, "Betis": 67.00, "Inter": 41.00,
            "Borussia Dortmund": 67.00, "Atletico Madrid": 34.00, "Como": 67.00,
            "Sporting CP": 81.00, "Stuttgart": 126.00, "Manchester United": 51.00,
            "Club Brugge": 151.00, "Napoli": 101.00, "Roma": 67.00,
            "Galatasaray": 201.00, "PSV Eindhoven": 251.00, "RB Leipzig": 151.00,
            "Villarreal": 81.00, "Porto": 151.00, "Bodo/Glimt": 251.00,
            "Fenerbahce": 251.00, "Lens": 351.00, "Feyenoord": 251.00,
            "Shakhtar Donetsk": 501.00, "LASK": 1001.00, "AEK Athens": 501.00,
            "Viking": 1001.00, "Slovan Bratislava": 4501.00, "Lille": 351.00,
            "Slavia Prague": 1001.00,
        },
    },
    "Europa League": {
        # Not today's date like the other two -- bettingodds.com's EL page
        # was still showing a stale pre-season September snapshot, and
        # every other aggregator tried (Squawka, Oddschecker, Scotsman,
        # bet365's own news site, SportyTrader, OddsPortal) blocked
        # automated fetching. odds1x2.com was the one accessible source
        # with real post-League-Phase-start prices; its own page doesn't
        # give one clean timestamp, but the latest price-change date shown
        # was 2026-10-22, so that's used as a conservative as_of.
        "as_of": "2026-10-22", "source": "odds1x2.com",
        "odds": {
            "Benfica": 6.00, "Bayer Leverkusen": 6.00, "Bournemouth": 7.00,
            "Juventus": 8.00, "AC Milan": 19.00, "Sunderland": 17.00,
            "Besiktas": 21.00, "Crystal Palace": 21.00, "Real Sociedad": 21.00,
            "TSG Hoffenheim": 26.00, "Celta Vigo": 34.00, "Olympiacos": 26.00,
            "Lyon": 26.00, "Union Saint-Gilloise": 34.00, "Rennes": 34.00,
            "AZ Alkmaar": 51.00, "Ferencvarosi TC": 41.00, "Omonia Nicosia": 201.00,
            "Marseille": 101.00, "Anderlecht": 101.00, "NEC Nijmegen": 101.00,
            "Red Bull Salzburg": 151.00, "Sparta Prague": 151.00, "Dinamo Zagreb": 151.00,
            "Celtic": 201.00, "Sturm Graz": 201.00, "Plzen": 201.00,
            "Levski Sofia": 201.00, "Jagiellonia": 251.00, "Lillestrom": 351.00,
            "Celje": 501.00, "Torreense": 501.00, "Lech Poznan": 501.00,
            "OFI": 751.00,
        },
    },
    "Conference League": {
        "as_of": "2026-11-04", "source": "bettingodds.com",
        "odds": {
            "Brighton": 3.25, "Monaco": 6.50, "Atalanta": 8.50, "Ajax": 10.00,
            "Sporting Braga": 15.00, "SC Freiburg": 15.00, "Panathinaikos": 19.00,
            "Trabzonspor": 21.00, "FC Copenhagen": 21.00, "Lugano": 26.00,
            "Twente": 26.00, "FK Crvena Zvezda": 34.00, "St. Truiden": 34.00,
            "Brann": 26.00, "FC Midtjylland": 51.00, "Gent": 51.00,
            "FC Nordsjaelland": 51.00, "Hajduk Split": 51.00, "Getafe": 67.00,
            "Pafos FC": 81.00, "Universitatea Craiova": 101.00, "Borac Banja Luka": 101.00,
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
