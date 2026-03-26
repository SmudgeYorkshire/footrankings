"""
Static data for the 2026 FIFA World Cup (USA / Canada / Mexico).

Groups, fixtures, Elo ratings, UEFA/IC playoff brackets.
"""

# ---------------------------------------------------------------------------
# Elo ratings (from eloratings.net, March 2026)
# ---------------------------------------------------------------------------
WC_ELO: dict[str, int] = {
    # Top-ranked qualifiers (UEFA ratings updated March 2026 from eloratings.net)
    "Spain":              2172,
    "Argentina":          2113,
    "France":             2062,
    "England":            2042,
    "Brazil":             2031,
    "Germany":            1910,
    "Netherlands":        1959,
    "Belgium":            1850,
    "Portugal":           1976,
    "Uruguay":            1917,
    "United States":      1902,
    "Mexico":             1887,
    "Croatia":            1932,
    "Denmark":            1864,
    "Switzerland":        1897,
    "Colombia":           1869,
    "Austria":            1818,
    "Morocco":            1864,
    "Senegal":            1863,
    "Sweden":             1755,
    "Japan":              1857,
    "South Korea":        1845,
    "Ukraine":            1730,
    "Poland":             1735,
    "Norway":             1922,
    "Ecuador":            1819,
    "Turkey":             1880,
    "Romania":            1642,
    "Italy":              1859,
    "Scotland":           1790,
    "Czechia":            1731,
    "Hungary":            1698,
    "Slovakia":           1687,
    "Iran":               1780,
    "Egypt":              1779,
    "Australia":          1773,
    "Algeria":            1772,
    "Ivory Coast":        1771,
    "Tunisia":            1757,
    "Ghana":              1748,
    "Jordan":             1735,
    "Paraguay":           1730,
    "New Zealand":        1700,
    "Kosovo":             1714,
    "Northern Ireland":   1602,
    "Wales":              1715,
    "Bosnia-Herzegovina": 1572,
    "Venezuela":          1678,
    "Uzbekistan":         1672,
    "Saudi Arabia":       1670,
    "Cape Verde":         1660,
    "South Africa":       1655,
    "Albania":            1664,
    "Panama":             1648,
    "N. Macedonia":       1592,
    "Haiti":              1636,
    "Qatar":              1635,
    "Ireland":            1688,
    "Curaçao":            1607,
    # IC Playoff teams (updated March 2026)
    "DR Congo":       1639,
    "Iraq":           1582,
    "Jamaica":        1542,
    "Bolivia":        1661,
    "Suriname":       1440,
    "New Caledonia":  1294,
    # IC Playoff weighted-average placeholders (used in group projections)
    "IC Playoff 1 Winner": 1602,   # weighted avg: DR Congo 68%, Jamaica 29%, New Caledonia 2%
    "IC Playoff 2 Winner": 1610,   # weighted avg: Bolivia 48%, Iraq 46%, Suriname 7%
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
        "semifinal_1":    ("Italy",   "Northern Ireland"),
        "semifinal_2":    ("Wales",   "Bosnia-Herzegovina"),
        "winner_group":   "B",
    },
    "B": {
        "label":          "Path B → Group F",
        "semi_date":      "2026-03-26",
        "final_date":     "2026-03-31",
        "semifinal_1":    ("Ukraine", "Sweden"),
        "semifinal_2":    ("Poland",  "Albania"),
        "winner_group":   "F",
        "neutral_sf1":    True,   # SF1 (Ukraine) at neutral ground — Ukraine cannot host
        "neutral_final":  True,   # Final at neutral ground if Ukraine participates
    },
    "C": {
        "label":          "Path C → Group D",
        "semi_date":      "2026-03-26",
        "final_date":     "2026-03-31",
        "semifinal_1":    ("Turkey",  "Romania"),
        "semifinal_2":    ("Slovakia", "Kosovo"),
        "winner_group":   "D",
    },
    "D": {
        "label":          "Path D → Group A",
        "semi_date":      "2026-03-26",
        "final_date":     "2026-03-31",
        "semifinal_1":    ("Denmark", "N. Macedonia"),
        "semifinal_2":    ("Czechia", "Ireland"),
        "winner_group":   "A",
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
        # Top-ranked team receives a bye directly to the final
        "bye_team":     "DR Congo",          # CAF  — seeded, plays final only
        "semifinal":    ("New Caledonia", "Jamaica"),   # OFC vs CONCACAF
        "winner_group": "K",
    },
    "2": {
        "label":        "Pathway 2 → Group I",
        "semi_date":    "2026-03-26",
        "final_date":   "2026-03-31",
        "semi_venue":   "Monterrey (Estadio BBVA)",
        "final_venue":  "Monterrey (Estadio BBVA)",
        # Top-ranked team receives a bye directly to the final
        "bye_team":     "Iraq",              # AFC  — seeded, plays final only
        "semifinal":    ("Bolivia", "Suriname"),        # CONMEBOL vs CONCACAF
        "winner_group": "I",
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
