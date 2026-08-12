"""
One-time frozen snapshot from kassiesa.net (UEFA Country Ranking), taken
2026-08-11 — the last time this site pulls data from kassiesa.net at all.

Only the CLOSED seasons (22/23 through 25/26) are kept here — those can't be
cleanly recomputed ourselves since UEFA's coefficient methodology has changed
several times over the years (see coefficients.py's methodology expander).

The current season (26/27 onward) is computed live from API-Football match
results instead (see coefficients.py's _compute_live_coefficients), so this
file never needs to be re-scraped or updated by hand again.

clubs_entered / clubs_active are the "clubs still in competition this season"
counts as of the snapshot date, used as the starting point for this site's
own club-count tracking (which then only decrements on a Conference League
elimination — Champions League and Europa League eliminations parachute
into the next competition down, so they're not a country's final exit).
"""

COUNTRY_BASELINE: dict[str, dict] = {
    "England": {"22/23": 23.000, "23/24": 17.375, "24/25": 29.464, "25/26": 28.680, "clubs_entered": 9, "clubs_active": 9},
    "Italy": {"22/23": 22.357, "23/24": 21.000, "24/25": 21.875, "25/26": 19.000, "clubs_entered": 7, "clubs_active": 7},
    "Spain": {"22/23": 16.571, "23/24": 16.062, "24/25": 23.892, "25/26": 22.093, "clubs_entered": 8, "clubs_active": 8},
    "Germany": {"22/23": 17.125, "23/24": 19.357, "24/25": 18.421, "25/26": 21.785, "clubs_entered": 7, "clubs_active": 7},
    "France": {"22/23": 12.583, "23/24": 16.250, "24/25": 17.928, "25/26": 18.321, "clubs_entered": 7, "clubs_active": 7},
    "Portugal": {"22/23": 12.500, "23/24": 11.000, "24/25": 16.250, "25/26": 20.500, "clubs_entered": 5, "clubs_active": 5},
    "Belgium": {"22/23": 14.200, "23/24": 14.400, "24/25": 15.650, "25/26": 11.400, "clubs_entered": 5, "clubs_active": 5},
    "Netherlands": {"22/23": 13.500, "23/24": 10.000, "24/25": 15.250, "25/26": 9.979, "clubs_entered": 6, "clubs_active": 6},
    "Türkiye": {"22/23": 11.800, "23/24": 12.000, "24/25": 10.300, "25/26": 11.075, "clubs_entered": 5, "clubs_active": 4},
    "Czechia": {"22/23": 6.750, "23/24": 13.500, "24/25": 10.550, "25/26": 11.025, "clubs_entered": 5, "clubs_active": 5},
    "Poland": {"22/23": 7.750, "23/24": 6.875, "24/25": 11.750, "25/26": 15.750, "clubs_entered": 5, "clubs_active": 5},
    "Greece": {"22/23": 2.125, "23/24": 11.400, "24/25": 12.687, "25/26": 14.200, "clubs_entered": 5, "clubs_active": 5},
    "Denmark": {"22/23": 5.900, "23/24": 8.500, "24/25": 7.656, "25/26": 12.250, "clubs_entered": 4, "clubs_active": 4},
    "Norway": {"22/23": 5.750, "23/24": 8.000, "24/25": 11.812, "25/26": 8.050, "clubs_entered": 5, "clubs_active": 5},
    "Cyprus": {"22/23": 5.100, "23/24": 3.750, "24/25": 10.562, "25/26": 12.156, "clubs_entered": 4, "clubs_active": 3},
    "Switzerland": {"22/23": 8.500, "23/24": 5.200, "24/25": 7.050, "25/26": 6.200, "clubs_entered": 4, "clubs_active": 4},
    "Hungary": {"22/23": 5.875, "23/24": 4.500, "24/25": 6.625, "25/26": 7.437, "clubs_entered": 4, "clubs_active": 3},
    "Sweden": {"22/23": 6.250, "23/24": 1.875, "24/25": 11.375, "25/26": 5.000, "clubs_entered": 4, "clubs_active": 3},
    "Austria": {"22/23": 4.900, "23/24": 4.800, "24/25": 9.650, "25/26": 4.100, "clubs_entered": 5, "clubs_active": 5},
    "Scotland": {"22/23": 3.500, "23/24": 6.400, "24/25": 9.250, "25/26": 5.000, "clubs_entered": 5, "clubs_active": 5},
    "Croatia": {"22/23": 3.375, "23/24": 5.875, "24/25": 5.875, "25/26": 7.031, "clubs_entered": 4, "clubs_active": 3},
    "Romania": {"22/23": 6.250, "23/24": 3.250, "24/25": 7.750, "25/26": 5.750, "clubs_entered": 4, "clubs_active": 2},
    "Ukraine": {"22/23": 5.700, "23/24": 4.100, "24/25": 3.600, "25/26": 8.312, "clubs_entered": 4, "clubs_active": 2},
    "Israel": {"22/23": 6.250, "23/24": 8.750, "24/25": 2.875, "25/26": 2.875, "clubs_entered": 4, "clubs_active": 4},
    "Slovenia": {"22/23": 2.125, "23/24": 3.875, "24/25": 9.093, "25/26": 6.375, "clubs_entered": 4, "clubs_active": 1},
    "Azerbaijan": {"22/23": 4.000, "23/24": 5.875, "24/25": 2.875, "25/26": 5.812, "clubs_entered": 4, "clubs_active": 2},
    "Bulgaria": {"22/23": 4.500, "23/24": 4.375, "24/25": 3.625, "25/26": 5.187, "clubs_entered": 4, "clubs_active": 3},
    "Slovakia": {"22/23": 6.000, "23/24": 5.000, "24/25": 4.625, "25/26": 2.625, "clubs_entered": 4, "clubs_active": 2},
    "Serbia": {"22/23": 5.375, "23/24": 1.400, "24/25": 3.725, "25/26": 5.750, "clubs_entered": 4, "clubs_active": 2},
    "Russia": {"22/23": 4.333, "23/24": 4.333, "24/25": 4.333, "25/26": 4.333, "clubs_entered": 0, "clubs_active": 0},
    "Iceland": {"22/23": 3.000, "23/24": 3.833, "24/25": 4.562, "25/26": 3.625, "clubs_entered": 4, "clubs_active": 2},
    "Ireland": {"22/23": 3.375, "23/24": 1.500, "24/25": 5.343, "25/26": 4.250, "clubs_entered": 4, "clubs_active": 3},
    "Armenia": {"22/23": 2.375, "23/24": 2.250, "24/25": 4.375, "25/26": 4.187, "clubs_entered": 4, "clubs_active": 2},
    "Kosovo": {"22/23": 2.875, "23/24": 3.000, "24/25": 2.000, "25/26": 3.781, "clubs_entered": 4, "clubs_active": 1},
    "Bosnia-Herzegovina": {"22/23": 2.000, "23/24": 2.250, "24/25": 4.531, "25/26": 3.312, "clubs_entered": 4, "clubs_active": 1},
    "Latvia": {"22/23": 2.750, "23/24": 1.625, "24/25": 3.875, "25/26": 2.000, "clubs_entered": 4, "clubs_active": 3},
    "Finland": {"22/23": 2.625, "23/24": 1.750, "24/25": 2.250, "25/26": 3.625, "clubs_entered": 4, "clubs_active": 4},
    "Kazakhstan": {"22/23": 1.125, "23/24": 3.125, "24/25": 3.000, "25/26": 3.625, "clubs_entered": 4, "clubs_active": 2},
    "Liechtenstein": {"22/23": 6.500, "23/24": 0.500, "24/25": 0.500, "25/26": 1.000, "clubs_entered": 1, "clubs_active": 1},
    "Moldova": {"22/23": 3.750, "23/24": 2.000, "24/25": 2.125, "25/26": 1.500, "clubs_entered": 4, "clubs_active": 1},
    "Faroe Islands": {"22/23": 2.250, "23/24": 2.750, "24/25": 1.500, "25/26": 1.750, "clubs_entered": 4, "clubs_active": 2},
    "North Macedonia": {"22/23": 1.625, "23/24": 1.500, "24/25": 0.666, "25/26": 3.343, "clubs_entered": 3, "clubs_active": 1},
    "Albania": {"22/23": 0.875, "23/24": 2.125, "24/25": 1.250, "25/26": 2.250, "clubs_entered": 4, "clubs_active": 2},
    "Belarus": {"22/23": 0.625, "23/24": 1.750, "24/25": 1.875, "25/26": 2.125, "clubs_entered": 3, "clubs_active": 2},
    "Lithuania": {"22/23": 2.375, "23/24": 1.125, "24/25": 1.375, "25/26": 1.125, "clubs_entered": 4, "clubs_active": 2},
    "Malta": {"22/23": 2.625, "23/24": 1.500, "24/25": 1.000, "25/26": 2.000, "clubs_entered": 4, "clubs_active": 4},
    "Andorra": {"22/23": 0.666, "23/24": 1.666, "24/25": 1.000, "25/26": 2.000, "clubs_entered": 3, "clubs_active": 1},
    "Estonia": {"22/23": 1.166, "23/24": 0.125, "24/25": 1.625, "25/26": 1.625, "clubs_entered": 4, "clubs_active": 2},
    "Gibraltar": {"22/23": 0.875, "23/24": 0.166, "24/25": 1.500, "25/26": 3.333, "clubs_entered": 3, "clubs_active": 1},
    "Northern Ireland": {"22/23": 1.250, "23/24": 1.125, "24/25": 1.500, "25/26": 1.750, "clubs_entered": 4, "clubs_active": 1},
    "Georgia": {"22/23": 1.125, "23/24": 1.250, "24/25": 1.250, "25/26": 1.125, "clubs_entered": 4, "clubs_active": 1},
    "Luxembourg": {"22/23": 1.125, "23/24": 2.250, "24/25": 1.250, "25/26": 0.750, "clubs_entered": 4, "clubs_active": 4},
    "Montenegro": {"22/23": 1.000, "23/24": 1.333, "24/25": 2.500, "25/26": 1.000, "clubs_entered": 4, "clubs_active": 4},
    "Wales": {"22/23": 1.166, "23/24": 0.625, "24/25": 2.000, "25/26": 0.333, "clubs_entered": 4, "clubs_active": 4},
    "San Marino": {"22/23": 0.833, "23/24": 0.333, "24/25": 0.666, "25/26": 0.833, "clubs_entered": 3, "clubs_active": 1},
}

# LEAGUES config country spelling -> canonical spelling used above (matches
# kassiesa.net's naming). Countries not listed here already match exactly.
COUNTRY_NAME_FIXUP: dict[str, str] = {
    "Bosnia": "Bosnia-Herzegovina",
    "Czech Rep.": "Czechia",
    "Faroe Isl.": "Faroe Islands",
    "N. Ireland": "Northern Ireland",
    "N. Macedonia": "North Macedonia",
    "Turkey": "Türkiye",
}

# Clubs not covered by config.py's LEAGUES (Liechtenstein has no domestic
# league of its own — its clubs play in the Swiss system), plus explicit
# resolutions for names shared by clubs in two different countries (see
# _load_club_country_map's docstring) that are actually relevant this season.
CLUB_COUNTRY_OVERRIDE: dict[str, str] = {
    "Vaduz": "Liechtenstein",
    "FC Vaduz": "Liechtenstein",
    "Vestri": "Iceland",  # Vestri Ísafjörður — not yet in ratings/4642.csv
    "Arsenal": "England",  # also a Belarusian club (Arsenal Dzerzhinsk) — England's is the 2026-27 UCL entrant
    # Names used in CONFIRMED_LEAGUE_PHASE (qualifying_bracket.py, sourced
    # from Wikipedia) that don't match the domestic ratings CSV's team/alias
    # spelling for the same club.
    "Inter Milan": "Italy",       # ratings/4332.csv has "Internazionale" / alias "Inter"
    "Atlético Madrid": "Spain",   # ratings/4335.csv has "Atlético de Madrid" / alias "Atletico Madrid"
    "TSG Hoffenheim": "Germany",  # ratings/4331.csv has "Hoffenheim" / alias "1899 Hoffenheim"
    "Torreense": "Portugal",      # not in ratings/4344.csv at all (not usually top-flight)
}
