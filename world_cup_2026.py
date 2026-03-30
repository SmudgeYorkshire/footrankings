"""
Static data for the 2026 FIFA World Cup (USA / Canada / Mexico).

Groups, fixtures, Elo ratings, UEFA/IC playoff brackets.
"""

# ---------------------------------------------------------------------------
# Elo ratings (from eloratings.net, March 2026)
# ---------------------------------------------------------------------------
WC_ELO: dict[str, int] = {
    # All ratings from eloratings.net World.tsv — updated 30 March 2026
    # (post-UEFA playoff semi-finals and IC playoff semi-finals)
    "Spain":              2174,
    "Argentina":          2113,
    "France":             2082,
    "England":            2036,
    "Portugal":           1975,
    "Colombia":           1975,
    "Brazil":             1970,
    "Netherlands":        1965,
    "Croatia":            1944,
    "Ecuador":            1929,
    "Germany":            1922,
    "Norway":             1916,
    "Uruguay":            1896,
    "Japan":              1888,
    "Switzerland":        1885,
    "Turkey":             1885,
    "Senegal":            1878,
    "Denmark":            1873,
    "Italy":              1866,
    "Belgium":            1866,
    "Mexico":             1858,
    "Paraguay":           1844,
    "Austria":            1821,
    "Morocco":            1810,
    "Canada":             1794,
    "Scotland":           1780,
    "Australia":          1779,
    "Ukraine":            1760,
    "South Korea":        1758,
    "Poland":             1746,
    "Algeria":            1739,
    "Iran":               1739,
    "Kosovo":             1738,
    "United States":      1730,
    "Panama":             1730,
    "Uzbekistan":         1727,
    "Venezuela":          1727,
    "Czechia":            1723,
    "Hungary":            1705,
    "Wales":              1703,
    "Sweden":             1702,
    "Jordan":             1687,
    "Egypt":              1680,
    "Bolivia":            1670,
    "Ivory Coast":        1663,
    "Slovakia":           1663,
    "South Africa":       1531,
    "Albania":            1653,
    "DR Congo":           1640,
    "Romania":            1637,
    "Ireland":            1696,
    "Tunisia":            1626,
    "Haiti":              1530,
    "New Caledonia":      1286,
    "N. Macedonia":       1584,
    "Bosnia-Herzegovina": 1584,
    "Iraq":               1582,
    "New Zealand":        1585,
    "Ghana":              1506,
    "Curaçao":            1440,
    "Qatar":              1425,
    "Cape Verde":         1549,
    "Saudi Arabia":       1571,
    "Northern Ireland":   1457,
    "Jamaica":            1550,
    "Suriname":           1431,
    # IC Playoff weighted-average placeholders (used in group projections)
    "IC Playoff 1 Winner": 1606,   # weighted avg: DR Congo (1640) 63% vs Jamaica (1550) 37%
    "IC Playoff 2 Winner": 1637,   # weighted avg: Bolivia (1670) 62% vs Iraq (1582) 38%
}

# ---------------------------------------------------------------------------
# Flag emojis
# ---------------------------------------------------------------------------
WC_FLAGS: dict[str, str] = {
    "Spain":              "🇪🇸",
    "Argentina":          "🇦🇷",
    "France":             "🇫🇷",
    "England":            "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Brazil":             "🇧🇷",
    "Germany":            "🇩🇪",
    "Netherlands":        "🇳🇱",
    "Belgium":            "🇧🇪",
    "Portugal":           "🇵🇹",
    "Uruguay":            "🇺🇾",
    "United States":      "🇺🇸",
    "Mexico":             "🇲🇽",
    "Croatia":            "🇭🇷",
    "Denmark":            "🇩🇰",
    "Switzerland":        "🇨🇭",
    "Colombia":           "🇨🇴",
    "Austria":            "🇦🇹",
    "Morocco":            "🇲🇦",
    "Senegal":            "🇸🇳",
    "Sweden":             "🇸🇪",
    "Japan":              "🇯🇵",
    "South Korea":        "🇰🇷",
    "Ukraine":            "🇺🇦",
    "Poland":             "🇵🇱",
    "Norway":             "🇳🇴",
    "Ecuador":            "🇪🇨",
    "Turkey":             "🇹🇷",
    "Romania":            "🇷🇴",
    "Italy":              "🇮🇹",
    "Scotland":           "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Czechia":            "🇨🇿",
    "Hungary":            "🇭🇺",
    "Slovakia":           "🇸🇰",
    "Iran":               "🇮🇷",
    "Egypt":              "🇪🇬",
    "Australia":          "🇦🇺",
    "Algeria":            "🇩🇿",
    "Ivory Coast":        "🇨🇮",
    "Tunisia":            "🇹🇳",
    "Ghana":              "🇬🇭",
    "Jordan":             "🇯🇴",
    "Paraguay":           "🇵🇾",
    "New Zealand":        "🇳🇿",
    "Kosovo":             "🇽🇰",
    "Northern Ireland":   "🏴󠁧󠁢󠁮󠁩󠁲󠁿",
    "Wales":              "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Bosnia-Herzegovina": "🇧🇦",
    "Venezuela":          "🇻🇪",
    "Uzbekistan":         "🇺🇿",
    "Saudi Arabia":       "🇸🇦",
    "Cape Verde":         "🇨🇻",
    "South Africa":       "🇿🇦",
    "Albania":            "🇦🇱",
    "Panama":             "🇵🇦",
    "N. Macedonia":       "🇲🇰",
    "Haiti":              "🇭🇹",
    "Qatar":              "🇶🇦",
    "Ireland":            "🇮🇪",
    "Curaçao":            "🇨🇼",
    "IC Playoff 1 Winner": "🌐",
    "IC Playoff 2 Winner": "🌐",
    "DR Congo":       "🇨🇩",
    "Iraq":           "🇮🇶",
    "Jamaica":        "🇯🇲",
    "Bolivia":        "🇧🇴",
    "Suriname":       "🇸🇷",
    "New Caledonia":  "🇳🇨",
    "UEFA PO Path A Winner": "🇪🇺",
    "UEFA PO Path B Winner": "🇪🇺",
    "UEFA PO Path C Winner": "🇪🇺",
    "UEFA PO Path D Winner": "🇪🇺",
}

# ---------------------------------------------------------------------------
# Groups (post-draw; UEFA/IC playoff winners are placeholders)
# ---------------------------------------------------------------------------
WC_GROUPS: dict[str, list[str]] = {
    "A": ["Mexico",        "South Korea",  "South Africa",       "UEFA PO Path D Winner"],
    "B": ["Canada",        "Switzerland",  "Qatar",              "UEFA PO Path A Winner"],
    "C": ["Brazil",        "Morocco",      "Scotland",           "Haiti"],
    "D": ["United States", "Paraguay",     "Australia",          "UEFA PO Path C Winner"],
    "E": ["Germany",       "Ecuador",      "Ivory Coast",        "Curaçao"],
    "F": ["Netherlands",   "Japan",        "Tunisia",            "UEFA PO Path B Winner"],
    "G": ["Belgium",       "Egypt",        "Iran",               "New Zealand"],
    "H": ["Spain",         "Uruguay",      "Saudi Arabia",       "Cape Verde"],
    "I": ["France",        "Senegal",      "Norway",             "IC Playoff 2 Winner"],
    "J": ["Argentina",     "Austria",      "Algeria",            "Jordan"],
    "K": ["Portugal",      "Colombia",     "Uzbekistan",         "IC Playoff 1 Winner"],
    "L": ["England",       "Croatia",      "Ghana",              "Panama"],
}

# ---------------------------------------------------------------------------
# UEFA Playoff bracket (semi-finals March 26, finals March 31, 2026)
# ---------------------------------------------------------------------------
# Each path winner goes into the corresponding WC group
UEFA_PLAYOFF_PATHS: dict[str, dict] = {
    "A": {
        "label":          "Path A → Group B",
        "semi_date":      "2026-03-26",
        "final_date":     "2026-03-31",
        "final_city":     "Zenica",
        "semifinal_1":    ("Italy",   "Northern Ireland"),
        "semifinal_2":    ("Wales",   "Bosnia-Herzegovina"),
        "winner_group":   "B",
        "sf1_winner":     "Italy",              "sf1_score": "2–0",
        "sf2_winner":     "Bosnia-Herzegovina", "sf2_score": "1–1 (aet, 4–2 pens)",
    },
    "B": {
        "label":          "Path B → Group F",
        "semi_date":      "2026-03-26",
        "final_date":     "2026-03-31",
        "final_city":     "Solna",
        "semifinal_1":    ("Ukraine", "Sweden"),
        "semifinal_2":    ("Poland",  "Albania"),
        "winner_group":   "F",
        "neutral_sf1":    True,
        "final_host_sf1": True,   # Sweden (SF1 winner) hosts Final in Solna
        "sf1_winner":     "Sweden", "sf1_score": "3–1",
        "sf2_winner":     "Poland", "sf2_score": "2–1",
    },
    "C": {
        "label":          "Path C → Group D",
        "semi_date":      "2026-03-26",
        "final_date":     "2026-03-31",
        "final_city":     "Pristina",
        "semifinal_1":    ("Turkey",  "Romania"),
        "semifinal_2":    ("Slovakia", "Kosovo"),
        "winner_group":   "D",
        "sf1_winner":     "Turkey", "sf1_score": "1–0",
        "sf2_winner":     "Kosovo", "sf2_score": "4–3 (aet)",
    },
    "D": {
        "label":          "Path D → Group A",
        "semi_date":      "2026-03-26",
        "final_date":     "2026-03-31",
        "final_city":     "Prague",
        "semifinal_1":    ("Denmark", "N. Macedonia"),
        "semifinal_2":    ("Czechia", "Ireland"),
        "winner_group":   "A",
        "sf1_winner":     "Denmark", "sf1_score": "4–0",
        "sf2_winner":     "Czechia", "sf2_score": "2–2 (aet, 4–3 pens)",
    },
}

# ---------------------------------------------------------------------------
# FIFA Inter-confederation Play-offs (March 26 semi-finals, March 31 finals)
# All matches played in Mexico (single-leg, extra time + penalties if tied)
# ---------------------------------------------------------------------------
FIFA_IC_PLAYOFFS: dict[str, dict] = {
    "1": {
        "label":        "Pathway 1 → Group K",
        "semi_date":    "2026-03-26",
        "final_date":   "2026-03-31",
        "semi_venue":   "Guadalajara (Estadio Akron)",
        "final_venue":  "Guadalajara (Estadio Akron)",
        "bye_team":     "DR Congo",
        "semifinal":    ("New Caledonia", "Jamaica"),
        "winner_group": "K",
        "sf_winner":    "Jamaica", "sf_score": "0–1",
    },
    "2": {
        "label":        "Pathway 2 → Group I",
        "semi_date":    "2026-03-26",
        "final_date":   "2026-03-31",
        "semi_venue":   "Monterrey (Estadio BBVA)",
        "final_venue":  "Monterrey (Estadio BBVA)",
        "bye_team":     "Iraq",
        "semifinal":    ("Bolivia", "Suriname"),
        "winner_group": "I",
        "sf_winner":    "Bolivia", "sf_score": "2–1",
    },
}

# Legacy alias used in group projections
IC_PLAYOFF_INFO: dict[str, dict] = {
    "IC Playoff 1 Winner": {
        "label":        "IC Playoff 1 → Group K",
        "winner_group": "K",
    },
    "IC Playoff 2 Winner": {
        "label":        "IC Playoff 2 → Group I",
        "winner_group": "I",
    },
}

# ---------------------------------------------------------------------------
# Tournament format
# ---------------------------------------------------------------------------
WC_FORMAT = {
    "groups":           12,
    "teams_per_group":  4,
    "total_teams":      48,
    "auto_advance":     2,   # top 2 per group
    "best_third":       8,   # best 8 of 12 third-place finishers
    "total_r32":        32,
    "venues": {
        "USA":    ["New York/New Jersey", "Los Angeles", "Dallas", "San Francisco",
                   "Seattle", "Boston", "Miami", "Atlanta", "Philadelphia",
                   "Kansas City", "Houston"],
        "Canada": ["Toronto", "Vancouver"],
        "Mexico": ["Mexico City", "Guadalajara", "Monterrey"],
    },
    "dates": {
        "group_stage":  "June 11 – July 2, 2026",
        "round_of_32":  "July 4–7, 2026",
        "round_of_16":  "July 9–12, 2026",
        "quarterfinals":"July 15–18, 2026",
        "semifinals":   "July 21–22, 2026",
        "third_place":  "July 25, 2026",
        "final":        "July 26, 2026",
    },
}
