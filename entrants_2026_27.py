"""
2026-27 UEFA European Competition Entrants.

Status values:
  "confirmed"   – club name known, domestic season complete
  "provisional" – club name known but season still running (may change)
  "tbd"         – slot known but club not yet determined

Sources: Wikipedia 2026-27 UCL / UEL / UECL pages, UEFA Access List 2026-27.
Last updated: 2026-03-17
"""

# Each entry: {"club": str|None, "country": str, "flag": str, "route": str, "status": str}
# club=None for tbd entries (route shown instead)

_CL = {
    "League Phase": {
        "League Path": [
            # England (4 spots)
            {"club": "Arsenal",           "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "League 1st",  "status": "provisional"},
            {"club": "Manchester City",   "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "League 2nd",  "status": "provisional"},
            {"club": "Manchester United", "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "League 3rd",  "status": "provisional"},
            {"club": "Aston Villa",       "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "League 4th",  "status": "provisional"},
            # Spain (4 spots)
            {"club": "Barcelona",         "country": "Spain",       "flag": "🇪🇸", "route": "League 1st",  "status": "provisional"},
            {"club": "Real Madrid",       "country": "Spain",       "flag": "🇪🇸", "route": "League 2nd",  "status": "provisional"},
            {"club": "Atlético Madrid",   "country": "Spain",       "flag": "🇪🇸", "route": "League 3rd",  "status": "provisional"},
            {"club": "Villarreal",        "country": "Spain",       "flag": "🇪🇸", "route": "League 4th",  "status": "provisional"},
            # Germany (4 spots)
            {"club": "Bayern München",    "country": "Germany",     "flag": "🇩🇪", "route": "League 1st",  "status": "provisional"},
            {"club": "Borussia Dortmund", "country": "Germany",     "flag": "🇩🇪", "route": "League 2nd",  "status": "provisional"},
            {"club": "Hoffenheim",        "country": "Germany",     "flag": "🇩🇪", "route": "League 3rd",  "status": "provisional"},
            {"club": "Stuttgart",         "country": "Germany",     "flag": "🇩🇪", "route": "League 4th",  "status": "provisional"},
            # Italy (4 spots)
            {"club": "Inter Milan",       "country": "Italy",       "flag": "🇮🇹", "route": "League 1st",  "status": "provisional"},
            {"club": "AC Milan",          "country": "Italy",       "flag": "🇮🇹", "route": "League 2nd",  "status": "provisional"},
            {"club": "Napoli",            "country": "Italy",       "flag": "🇮🇹", "route": "League 3rd",  "status": "provisional"},
            {"club": "Como",              "country": "Italy",       "flag": "🇮🇹", "route": "League 4th",  "status": "provisional"},
            # France (3 spots)
            {"club": "Paris Saint-Germain", "country": "France",   "flag": "🇫🇷", "route": "League 1st",  "status": "provisional"},
            {"club": "Lens",              "country": "France",      "flag": "🇫🇷", "route": "League 2nd",  "status": "provisional"},
            {"club": "Marseille",         "country": "France",      "flag": "🇫🇷", "route": "League 3rd",  "status": "provisional"},
            # Netherlands (2 spots)
            {"club": "PSV",               "country": "Netherlands", "flag": "🇳🇱", "route": "League 1st",  "status": "provisional"},
            {"club": "Feyenoord",         "country": "Netherlands", "flag": "🇳🇱", "route": "League 2nd",  "status": "provisional"},
            # Portugal (1 spot)
            {"club": "Porto",             "country": "Portugal",    "flag": "🇵🇹", "route": "League 1st",  "status": "provisional"},
            # Belgium, Czechia, Türkiye (1 spot each)
            {"club": "Union SG",          "country": "Belgium",     "flag": "🇧🇪", "route": "League 1st",  "status": "provisional"},
            {"club": "Slavia Praha",      "country": "Czechia",     "flag": "🇨🇿", "route": "League 1st",  "status": "provisional"},
            {"club": "Galatasaray",       "country": "Türkiye",     "flag": "🇹🇷", "route": "League 1st",  "status": "provisional"},
            # European Performance Spots (2)
            {"club": "Liverpool",         "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "EPS",         "status": "provisional"},
            {"club": "Real Betis",        "country": "Spain",       "flag": "🇪🇸", "route": "EPS",         "status": "provisional"},
            # Title holders (2)
            {"club": None, "country": "-", "flag": "🏆", "route": "UCL 25/26 Winner", "status": "tbd"},
            {"club": None, "country": "-", "flag": "🥈", "route": "UEL 25/26 Winner", "status": "tbd"},
            # 5 more via play-off round
            {"club": None, "country": "-", "flag": "🔢", "route": "5× Play-off winners", "status": "tbd"},
        ],
    },

    "Play-off Round": {
        "Champions Path (5 into League Phase)": [
            {"club": "Viking",            "country": "Norway",      "flag": "🇳🇴", "route": "League 1st",  "status": "confirmed"},
            {"club": None, "country": "Greece",      "flag": "🇬🇷", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Austria",     "flag": "🇦🇹", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Scotland",    "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "-", "flag": "🔢", "route": "6× QR3 Champions Path winners", "status": "tbd"},
        ],
        "League Path (2 into League Phase)": [
            {"club": None, "country": "France",      "flag": "🇫🇷", "route": "League 4th", "status": "tbd"},
            {"club": None, "country": "-", "flag": "🔢", "route": "3× QR3 League Path winners", "status": "tbd"},
        ],
    },

    "Third Qualifying Round": {
        "Champions Path": [
            {"club": "Mjällby AIF",       "country": "Sweden",      "flag": "🇸🇪", "route": "League 1st",  "status": "confirmed"},
            {"club": None, "country": "Poland",      "flag": "🇵🇱", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Denmark",     "flag": "🇩🇰", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Switzerland", "flag": "🇨🇭", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Israel",      "flag": "🇮🇱", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Cyprus",      "flag": "🇨🇾", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Croatia",     "flag": "🇭🇷", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Serbia",      "flag": "🇷🇸", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "-", "flag": "🔢", "route": "QR2 Champions Path winners", "status": "tbd"},
        ],
        "League Path": [
            {"club": None, "country": "Netherlands", "flag": "🇳🇱", "route": "League 3rd", "status": "tbd"},
            {"club": None, "country": "Portugal",    "flag": "🇵🇹", "route": "League 2nd", "status": "tbd"},
            {"club": None, "country": "Belgium",     "flag": "🇧🇪", "route": "League 2nd", "status": "tbd"},
            {"club": None, "country": "Czechia",     "flag": "🇨🇿", "route": "League 2nd", "status": "tbd"},
            {"club": None, "country": "Türkiye",     "flag": "🇹🇷", "route": "League 2nd", "status": "tbd"},
            {"club": None, "country": "-", "flag": "🔢", "route": "QR2 League Path winners", "status": "tbd"},
        ],
    },

    "Second Qualifying Round": {
        "Champions Path": [
            {"club": "Shamrock Rovers",   "country": "Ireland",     "flag": "🇮🇪", "route": "League 1st",  "status": "confirmed"},
            {"club": "Vikingur Reykjavik","country": "Iceland",     "flag": "🇮🇸", "route": "League 1st",  "status": "confirmed"},
            {"club": "Riga FC",           "country": "Latvia",      "flag": "🇱🇻", "route": "League 1st",  "status": "confirmed"},
            {"club": "KuPS Kuopio",       "country": "Finland",     "flag": "🇫🇮", "route": "League 1st",  "status": "confirmed"},
            {"club": "Kairat Almaty",     "country": "Kazakhstan",  "flag": "🇰🇿", "route": "League 1st",  "status": "confirmed"},
            {"club": "KI Klaksvik",       "country": "Faroe Islands","flag": "🇫🇴", "route": "League 1st",  "status": "confirmed"},
            {"club": "Kauno Žalgiris",    "country": "Lithuania",   "flag": "🇱🇹", "route": "League 1st",  "status": "confirmed"},
            {"club": "Flora Tallinn",     "country": "Estonia",     "flag": "🇪🇪", "route": "League 1st",  "status": "confirmed"},
            {"club": "The New Saints",    "country": "Wales",       "flag": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "route": "League 1st",  "status": "confirmed"},
            {"club": "Iberia 1999",       "country": "Georgia",     "flag": "🇬🇪", "route": "League 1st",  "status": "confirmed"},
            {"club": "ML Vitebsk",        "country": "Belarus",     "flag": "🇧🇾", "route": "League 1st",  "status": "confirmed"},
            # TBD champions path
            {"club": None, "country": "Ukraine",      "flag": "🇺🇦", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Hungary",      "flag": "🇭🇺", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Romania",      "flag": "🇷🇴", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Slovakia",     "flag": "🇸🇰", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Slovenia",     "flag": "🇸🇮", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Bulgaria",     "flag": "🇧🇬", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Azerbaijan",   "flag": "🇦🇿", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Moldova",      "flag": "🇲🇩", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Bosnia-Herz.", "flag": "🇧🇦", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Armenia",      "flag": "🇦🇲", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Kosovo",       "flag": "🇽🇰", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Malta",        "flag": "🇲🇹", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "N. Ireland",   "flag": "🏴󠁧󠁢󠁮󠁩󠁲󠁿", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Albania",      "flag": "🇦🇱", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Montenegro",   "flag": "🇲🇪", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Luxembourg",   "flag": "🇱🇺", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "N. Macedonia", "flag": "🇲🇰", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Andorra",      "flag": "🇦🇩", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Gibraltar",    "flag": "🇬🇮", "route": "League 1st (likely Lincoln Red Imps)", "status": "tbd"},
            {"club": None, "country": "San Marino",   "flag": "🇸🇲", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "-", "flag": "🔢", "route": "QR1 Champions Path winners", "status": "tbd"},
        ],
        "League Path": [
            {"club": "Bodø/Glimt",        "country": "Norway",      "flag": "🇳🇴", "route": "League 2nd",  "status": "confirmed"},
            {"club": None, "country": "Greece",      "flag": "🇬🇷", "route": "League 2nd", "status": "tbd"},
            {"club": None, "country": "Austria",     "flag": "🇦🇹", "route": "League 2nd", "status": "tbd"},
            {"club": None, "country": "Scotland",    "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "route": "League 2nd", "status": "tbd"},
            {"club": None, "country": "Poland",      "flag": "🇵🇱", "route": "League 2nd", "status": "tbd"},
        ],
    },

    "First Qualifying Round": {
        "Champions Path": [
            # Confirmed clubs from completed seasons (seeded / direct entry to QR1)
            {"club": "Riga FC",           "country": "Latvia",      "flag": "🇱🇻", "route": "League 1st",  "status": "confirmed"},
            {"club": "KI Klaksvik",       "country": "Faroe Islands","flag": "🇫🇴", "route": "League 1st",  "status": "confirmed"},
            {"club": "Flora Tallinn",     "country": "Estonia",     "flag": "🇪🇪", "route": "League 1st",  "status": "confirmed"},
            {"club": "The New Saints",    "country": "Wales",       "flag": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "route": "League 1st",  "status": "confirmed"},
            {"club": "Kauno Žalgiris",    "country": "Lithuania",   "flag": "🇱🇹", "route": "League 1st",  "status": "confirmed"},
            {"club": "Vikingur Reykjavik","country": "Iceland",     "flag": "🇮🇸", "route": "League 1st",  "status": "confirmed"},
            # TBD from lowest-ranked associations
            {"club": None, "country": "Ukraine",      "flag": "🇺🇦", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Hungary",      "flag": "🇭🇺", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Romania",      "flag": "🇷🇴", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Slovakia",     "flag": "🇸🇰", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Slovenia",     "flag": "🇸🇮", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Bulgaria",     "flag": "🇧🇬", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Azerbaijan",   "flag": "🇦🇿", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Moldova",      "flag": "🇲🇩", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Bosnia-Herz.", "flag": "🇧🇦", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Armenia",      "flag": "🇦🇲", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Kosovo",       "flag": "🇽🇰", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Malta",        "flag": "🇲🇹", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "N. Ireland",   "flag": "🏴󠁧󠁢󠁮󠁩󠁲󠁿", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Albania",      "flag": "🇦🇱", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Montenegro",   "flag": "🇲🇪", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Luxembourg",   "flag": "🇱🇺", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "N. Macedonia", "flag": "🇲🇰", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Andorra",      "flag": "🇦🇩", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "Gibraltar",    "flag": "🇬🇮", "route": "League 1st", "status": "tbd"},
            {"club": None, "country": "San Marino",   "flag": "🇸🇲", "route": "League 1st", "status": "tbd"},
        ],
    },
}

_EL = {
    "League Phase": {
        "Direct entries (24 clubs)": [
            # Title holder path
            {"club": None, "country": "-",           "flag": "🏅", "route": "UECL 25/26 Winner",       "status": "tbd"},
            # England
            {"club": None, "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "FA Cup winner",            "status": "tbd"},
            {"club": None, "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "League 5th",               "status": "tbd"},
            # Spain
            {"club": None, "country": "Spain",       "flag": "🇪🇸", "route": "Copa del Rey winner",     "status": "tbd"},
            {"club": None, "country": "Spain",       "flag": "🇪🇸", "route": "League 5th",               "status": "tbd"},
            # Germany
            {"club": None, "country": "Germany",     "flag": "🇩🇪", "route": "DFB-Pokal winner",        "status": "tbd"},
            {"club": None, "country": "Germany",     "flag": "🇩🇪", "route": "League 5th",               "status": "tbd"},
            # Italy
            {"club": None, "country": "Italy",       "flag": "🇮🇹", "route": "Coppa Italia winner",     "status": "tbd"},
            {"club": None, "country": "Italy",       "flag": "🇮🇹", "route": "League 5th",               "status": "tbd"},
            # France
            {"club": None, "country": "France",      "flag": "🇫🇷", "route": "Coupe de France winner",  "status": "tbd"},
            {"club": None, "country": "France",      "flag": "🇫🇷", "route": "League 5th",               "status": "tbd"},
            # Netherlands
            {"club": None, "country": "Netherlands", "flag": "🇳🇱", "route": "KNVB Cup winner",         "status": "tbd"},
            # Portugal
            {"club": None, "country": "Portugal",    "flag": "🇵🇹", "route": "Taça de Portugal winner", "status": "tbd"},
            # Belgium
            {"club": None, "country": "Belgium",     "flag": "🇧🇪", "route": "League 3rd",               "status": "tbd"},
            # Czechia
            {"club": None, "country": "Czechia",     "flag": "🇨🇿", "route": "Czech Cup winner",        "status": "tbd"},
            # Türkiye
            {"club": None, "country": "Türkiye",     "flag": "🇹🇷", "route": "Turkish Cup winner",      "status": "tbd"},
            # Norway
            {"club": None, "country": "Norway",      "flag": "🇳🇴", "route": "Norwegian Cup winner",    "status": "tbd"},
            # Greece
            {"club": None, "country": "Greece",      "flag": "🇬🇷", "route": "Greek Cup winner",        "status": "tbd"},
            # 12 more via play-off round
            {"club": None, "country": "-",           "flag": "🔢", "route": "12× Play-off winners",    "status": "tbd"},
        ],
    },

    "Play-off Round": {
        "Main Path": [
            {"club": None, "country": "Norway",      "flag": "🇳🇴", "route": "CW / League 3rd", "status": "tbd"},
            {"club": None, "country": "Greece",      "flag": "🇬🇷", "route": "Cup winner",       "status": "tbd"},
            {"club": None, "country": "Austria",     "flag": "🇦🇹", "route": "Cup winner",       "status": "tbd"},
            {"club": None, "country": "Scotland",    "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "route": "Cup winner",       "status": "tbd"},
            {"club": None, "country": "-",           "flag": "🔢", "route": "CL play-off losers (League Path) — drop-down", "status": "tbd"},
        ],
    },

    "Third Qualifying Round": {
        "Main Path": [
            {"club": None, "country": "Austria",     "flag": "🇦🇹", "route": "Cup winner",       "status": "tbd"},
            {"club": None, "country": "Scotland",    "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "route": "Cup winner",       "status": "tbd"},
            {"club": None, "country": "Poland",      "flag": "🇵🇱", "route": "Cup winner",       "status": "tbd"},
            {"club": None, "country": "-",           "flag": "🔢", "route": "CL QR3 losers — drop-down", "status": "tbd"},
        ],
    },

    "Second Qualifying Round": {
        "Main Path": [
            {"club": "Derry City",        "country": "Ireland",     "flag": "🇮🇪", "route": "League 2nd",  "status": "confirmed"},
            {"club": "IF Vestri",         "country": "Iceland",     "flag": "🇮🇸", "route": "Cup winner",  "status": "confirmed"},
            {"club": None, "country": "Denmark",     "flag": "🇩🇰", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Switzerland", "flag": "🇨🇭", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Israel",      "flag": "🇮🇱", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Cyprus",      "flag": "🇨🇾", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Sweden",      "flag": "🇸🇪", "route": "Cup winner / League 2nd", "status": "tbd"},
            {"club": None, "country": "Croatia",     "flag": "🇭🇷", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Serbia",      "flag": "🇷🇸", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Ukraine",     "flag": "🇺🇦", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Hungary",     "flag": "🇭🇺", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Romania",     "flag": "🇷🇴", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Slovakia",    "flag": "🇸🇰", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Slovenia",    "flag": "🇸🇮", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Bulgaria",    "flag": "🇧🇬", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Azerbaijan",  "flag": "🇦🇿", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Moldova",     "flag": "🇲🇩", "route": "Cup winner", "status": "tbd"},
        ],
    },

    "First Qualifying Round": {
        "Main Path": [
            # Cup winners from associations ~16-33 (summer leagues already determined)
            {"club": None, "country": "Denmark",     "flag": "🇩🇰", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Switzerland", "flag": "🇨🇭", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Israel",      "flag": "🇮🇱", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Cyprus",      "flag": "🇨🇾", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Sweden",      "flag": "🇸🇪", "route": "Cup winner / League 2nd", "status": "tbd"},
            {"club": None, "country": "Croatia",     "flag": "🇭🇷", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Serbia",      "flag": "🇷🇸", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Ukraine",     "flag": "🇺🇦", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Hungary",     "flag": "🇭🇺", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Romania",     "flag": "🇷🇴", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Slovakia",    "flag": "🇸🇰", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Slovenia",    "flag": "🇸🇮", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Bulgaria",    "flag": "🇧🇬", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Azerbaijan",  "flag": "🇦🇿", "route": "Cup winner", "status": "tbd"},
            {"club": None, "country": "Moldova",     "flag": "🇲🇩", "route": "Cup winner", "status": "tbd"},
        ],
    },
}

_UECL = {
    "League Phase": {
        "Direct entries (24 clubs)": [
            # England
            {"club": None, "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "EFL Cup winner",           "status": "tbd"},
            # Spain
            {"club": None, "country": "Spain",       "flag": "🇪🇸", "route": "League 6th",               "status": "tbd"},
            # Germany
            {"club": None, "country": "Germany",     "flag": "🇩🇪", "route": "League 6th",               "status": "tbd"},
            # Italy
            {"club": None, "country": "Italy",       "flag": "🇮🇹", "route": "League 6th",               "status": "tbd"},
            # France
            {"club": None, "country": "France",      "flag": "🇫🇷", "route": "League 6th",               "status": "tbd"},
            # Netherlands
            {"club": None, "country": "Netherlands", "flag": "🇳🇱", "route": "League 5th",               "status": "tbd"},
            # Portugal
            {"club": None, "country": "Portugal",    "flag": "🇵🇹", "route": "League 4th",               "status": "tbd"},
            # Belgium
            {"club": None, "country": "Belgium",     "flag": "🇧🇪", "route": "League 3rd/4th",           "status": "tbd"},
            # Czechia
            {"club": None, "country": "Czechia",     "flag": "🇨🇿", "route": "League 3rd",               "status": "tbd"},
            # Türkiye
            {"club": None, "country": "Türkiye",     "flag": "🇹🇷", "route": "League 3rd",               "status": "tbd"},
            # Norway
            {"club": None, "country": "Norway",      "flag": "🇳🇴", "route": "League 4th",               "status": "tbd"},
            # Greece
            {"club": None, "country": "Greece",      "flag": "🇬🇷", "route": "League 4th",               "status": "tbd"},
            # 12 via play-off round
            {"club": None, "country": "-",           "flag": "🔢", "route": "12× Play-off winners",      "status": "tbd"},
        ],
    },

    "Play-off Round": {
        "Direct entries": [
            {"club": None, "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "route": "EFL Cup winner",           "status": "tbd"},
            {"club": None, "country": "Italy",       "flag": "🇮🇹", "route": "League 6th",               "status": "tbd"},
            {"club": None, "country": "Spain",       "flag": "🇪🇸", "route": "League 6th",               "status": "tbd"},
            {"club": None, "country": "Germany",     "flag": "🇩🇪", "route": "League 6th",               "status": "tbd"},
            {"club": None, "country": "France",      "flag": "🇫🇷", "route": "League 6th",               "status": "tbd"},
            {"club": None, "country": "Netherlands", "flag": "🇳🇱", "route": "League 5th",               "status": "tbd"},
            {"club": None, "country": "-",           "flag": "🔢", "route": "EL play-off losers — drop-down",  "status": "tbd"},
            {"club": None, "country": "-",           "flag": "🔢", "route": "EL QR3 losers — drop-down",       "status": "tbd"},
        ],
    },

    "Third Qualifying Round": {
        "Direct entries + drop-downs": [
            {"club": None, "country": "Portugal",    "flag": "🇵🇹", "route": "League 3rd",   "status": "tbd"},
            {"club": None, "country": "Belgium",     "flag": "🇧🇪", "route": "League 4th/5th","status": "tbd"},
            {"club": None, "country": "Czechia",     "flag": "🇨🇿", "route": "League 3rd/4th","status": "tbd"},
            {"club": None, "country": "Türkiye",     "flag": "🇹🇷", "route": "League 3rd/4th","status": "tbd"},
            {"club": None, "country": "Norway",      "flag": "🇳🇴", "route": "League 4th/5th","status": "tbd"},
            {"club": None, "country": "Greece",      "flag": "🇬🇷", "route": "League 3rd/4th","status": "tbd"},
            {"club": None, "country": "Austria",     "flag": "🇦🇹", "route": "League 3rd/4th","status": "tbd"},
            {"club": None, "country": "Scotland",    "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "route": "League 3rd/4th","status": "tbd"},
            {"club": None, "country": "Poland",      "flag": "🇵🇱", "route": "League 3rd/4th","status": "tbd"},
            {"club": None, "country": "-",           "flag": "🔢", "route": "CL & EL qualifying losers — drop-down", "status": "tbd"},
        ],
    },

    "Second Qualifying Round": {
        "Direct entries": [
            # Confirmed (completed seasons)
            {"club": "Shelbourne",        "country": "Ireland",     "flag": "🇮🇪", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Valur Reykjavik",   "country": "Iceland",     "flag": "🇮🇸", "route": "League 2nd",  "status": "confirmed"},
            {"club": "FK Auda",           "country": "Latvia",      "flag": "🇱🇻", "route": "Cup winner",  "status": "confirmed"},
            {"club": "HJK Helsinki",      "country": "Finland",     "flag": "🇫🇮", "route": "Cup winner (special provision)", "status": "confirmed"},
            {"club": "Tobol Kustanai",    "country": "Kazakhstan",  "flag": "🇰🇿", "route": "Cup winner",  "status": "confirmed"},
            {"club": "FK Panevėžys",      "country": "Lithuania",   "flag": "🇱🇹", "route": "Cup winner (special provision)", "status": "confirmed"},
            {"club": "HB Tórshavn",       "country": "Faroe Islands","flag": "🇫🇴", "route": "Cup winner (special provision)", "status": "confirmed"},
            # TBD special provisions (assoc. 38-44 cup winners)
            {"club": None, "country": "Malta",        "flag": "🇲🇹", "route": "Cup winner (special provision)", "status": "tbd"},
            {"club": None, "country": "N. Ireland",   "flag": "🏴󠁧󠁢󠁮󠁩󠁲󠁿", "route": "Cup winner (special provision)", "status": "tbd"},
            {"club": None, "country": "Liechtenstein","flag": "🇱🇮", "route": "Cup winner (special provision)", "status": "tbd"},
            # Other direct entries
            {"club": None, "country": "Netherlands",  "flag": "🇳🇱", "route": "League 4th",  "status": "tbd"},
            {"club": None, "country": "Portugal",     "flag": "🇵🇹", "route": "League 3rd",  "status": "tbd"},
            {"club": None, "country": "Belgium",      "flag": "🇧🇪", "route": "League 4th",  "status": "tbd"},
            {"club": None, "country": "Czechia",      "flag": "🇨🇿", "route": "League 3rd/4th", "status": "tbd"},
            {"club": None, "country": "Türkiye",      "flag": "🇹🇷", "route": "League 3rd",  "status": "tbd"},
            {"club": None, "country": "Norway",       "flag": "🇳🇴", "route": "League 4th/5th", "status": "tbd"},
            {"club": None, "country": "Greece",       "flag": "🇬🇷", "route": "League 3rd/4th", "status": "tbd"},
            {"club": None, "country": "Austria",      "flag": "🇦🇹", "route": "League 3rd/4th", "status": "tbd"},
            {"club": None, "country": "Scotland",     "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "route": "League 3rd/4th", "status": "tbd"},
            {"club": None, "country": "Poland",       "flag": "🇵🇱", "route": "League 3rd/4th", "status": "tbd"},
            {"club": None, "country": "Denmark",      "flag": "🇩🇰", "route": "League 2nd/3rd", "status": "tbd"},
            {"club": None, "country": "Switzerland",  "flag": "🇨🇭", "route": "League 2nd/3rd", "status": "tbd"},
            {"club": None, "country": "Israel",       "flag": "🇮🇱", "route": "League 2nd/3rd", "status": "tbd"},
            {"club": None, "country": "Cyprus",       "flag": "🇨🇾", "route": "League 2nd/3rd", "status": "tbd"},
            {"club": None, "country": "Sweden",       "flag": "🇸🇪", "route": "League 2nd/3rd", "status": "tbd"},
            {"club": None, "country": "Croatia",      "flag": "🇭🇷", "route": "League 2nd/3rd", "status": "tbd"},
            {"club": None, "country": "Serbia",       "flag": "🇷🇸", "route": "League 2nd/3rd", "status": "tbd"},
            {"club": None, "country": "Ukraine",      "flag": "🇺🇦", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Hungary",      "flag": "🇭🇺", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Romania",      "flag": "🇷🇴", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Slovakia",     "flag": "🇸🇰", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Slovenia",     "flag": "🇸🇮", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Bulgaria",     "flag": "🇧🇬", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Azerbaijan",   "flag": "🇦🇿", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Moldova",      "flag": "🇲🇩", "route": "League 2nd",  "status": "tbd"},
            {"club": None, "country": "Bosnia-Herz.", "flag": "🇧🇦", "route": "Cup winner",  "status": "tbd"},
            {"club": None, "country": "Armenia",      "flag": "🇦🇲", "route": "Cup winner",  "status": "tbd"},
            {"club": None, "country": "Kosovo",       "flag": "🇽🇰", "route": "Cup winner",  "status": "tbd"},
        ],
    },

    "First Qualifying Round": {
        "Direct entries": [
            # Confirmed (completed seasons)
            {"club": "Bohemians Dublin",  "country": "Ireland",     "flag": "🇮🇪", "route": "League 4th",  "status": "confirmed"},
            {"club": "Stjarnan FC",       "country": "Iceland",     "flag": "🇮🇸", "route": "League 3rd",  "status": "confirmed"},
            {"club": "RFS Riga",          "country": "Latvia",      "flag": "🇱🇻", "route": "League 2nd",  "status": "confirmed"},
            {"club": "FK Liepāja",        "country": "Latvia",      "flag": "🇱🇻", "route": "League 3rd",  "status": "confirmed"},
            {"club": "Inter Turku",       "country": "Finland",     "flag": "🇫🇮", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Ilves Tampere",     "country": "Finland",     "flag": "🇫🇮", "route": "League 3rd",  "status": "confirmed"},
            {"club": "FK Astana",         "country": "Kazakhstan",  "flag": "🇰🇿", "route": "League 2nd",  "status": "confirmed"},
            {"club": "FK Yelimay",        "country": "Kazakhstan",  "flag": "🇰🇿", "route": "League 3rd",  "status": "confirmed"},
            {"club": "NSÍ Runavík",       "country": "Faroe Islands","flag": "🇫🇴", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Víkingur",          "country": "Faroe Islands","flag": "🇫🇴", "route": "League 3rd",  "status": "confirmed"},
            {"club": "FC Hegelmann",      "country": "Lithuania",   "flag": "🇱🇹", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Žalgiris Vilnius",  "country": "Lithuania",   "flag": "🇱🇹", "route": "League 3rd",  "status": "confirmed"},
            {"club": "Dila Gori",         "country": "Georgia",     "flag": "🇬🇪", "route": "Cup winner",  "status": "confirmed"},
            {"club": "Torpedo Kutaisi",   "country": "Georgia",     "flag": "🇬🇪", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Dinamo Tbilisi",    "country": "Georgia",     "flag": "🇬🇪", "route": "League 3rd",  "status": "confirmed"},
            {"club": "Dinamo Minsk",      "country": "Belarus",     "flag": "🇧🇾", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Connah's Quay",     "country": "Wales",       "flag": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Levadia Tallinn",   "country": "Estonia",     "flag": "🇪🇪", "route": "League 2nd",  "status": "confirmed"},
            {"club": "Kalju Nõmme",       "country": "Estonia",     "flag": "🇪🇪", "route": "League 3rd",  "status": "confirmed"},
            # TBD — ~2-3 clubs each from lowest associations
            {"club": None, "country": "Bosnia-Herz.", "flag": "🇧🇦", "route": "League 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "Armenia",      "flag": "🇦🇲", "route": "League 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "Kosovo",       "flag": "🇽🇰", "route": "League 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "Malta",        "flag": "🇲🇹", "route": "League 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "N. Ireland",   "flag": "🏴󠁧󠁢󠁮󠁩󠁲󠁿", "route": "League 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "Albania",      "flag": "🇦🇱", "route": "League 1st, 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "Montenegro",   "flag": "🇲🇪", "route": "League 1st, 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "Luxembourg",   "flag": "🇱🇺", "route": "League 1st, 2nd, 3rd", "status": "tbd"},
            {"club": None, "country": "Wales",        "flag": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "route": "Cup winner, League 3rd", "status": "tbd"},
            {"club": None, "country": "Estonia",      "flag": "🇪🇪", "route": "Cup winner",  "status": "tbd"},
            {"club": None, "country": "N. Macedonia", "flag": "🇲🇰", "route": "League 1st, 2nd", "status": "tbd"},
            {"club": None, "country": "Andorra",      "flag": "🇦🇩", "route": "League 1st, 2nd", "status": "tbd"},
            {"club": None, "country": "Gibraltar",    "flag": "🇬🇮", "route": "League 1st (likely Lincoln Red Imps), 2nd", "status": "tbd"},
            {"club": None, "country": "San Marino",   "flag": "🇸🇲", "route": "League 1st, 2nd", "status": "tbd"},
        ],
    },
}

# Ordered display list: chronological (earliest round first)
STAGE_ORDER = [
    "First Qualifying Round",
    "Second Qualifying Round",
    "Third Qualifying Round",
    "Play-off Round",
    "League Phase",
]

ENTRANTS = {
    "Champions League": _CL,
    "Europa League":    _EL,
    "Conference League": _UECL,
}
