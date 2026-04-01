"""
Static data for the 2026 FIFA World Cup (USA / Canada / Mexico).

Groups, fixtures, Elo ratings, UEFA/IC playoff brackets.
"""

# ---------------------------------------------------------------------------
# Elo ratings (from eloratings.net, March 2026)
# ---------------------------------------------------------------------------
WC_ELO: dict[str, int] = {
    # All ratings from eloratings.net World.tsv — updated 1 April 2026
    # (Bosnia/Czechia/Iraq estimated — eloratings pending playoff final processing)
    "Spain":              2165,   # -9
    "Argentina":          2113,
    "France":             2082,
    "England":            2020,
    "Portugal":           1984,   # +9
    "Colombia":           1975,
    "Brazil":             1984,   # +14
    "Netherlands":        1961,
    "Croatia":            1930,   # -14
    "Ecuador":            1933,
    "Germany":            1923,
    "Norway":             1912,
    "Uruguay":            1892,
    "Japan":              1904,
    "Turkey":             1902,
    "Switzerland":        1889,
    "Senegal":            1879,   # +1
    "Denmark":            1873,   # eliminated (Elo drop pending eloratings update)
    "Italy":              1866,   # eliminated (Elo drop pending eloratings update)
    "Belgium":            1866,
    "Mexico":             1858,
    "Paraguay":           1833,   # -11
    "Austria":            1827,   # +6
    "Morocco":            1821,   # +11
    "Canada":             1794,
    "Australia":          1783,   # +4
    "Ukraine":            1767,   # +7
    "Scotland":           1767,   # -13
    "South Korea":        1752,   # -6
    "Algeria":            1743,   # +4
    "Iran":               1760,   # +21
    "Sweden":             1719,   # +17 (UEFA playoff final win vs Poland)
    "Bosnia-Herzegovina": 1615,   # estimated +31 (final win vs Italy, eloratings pending)
    "Czechia":            1747,   # estimated +24 (final win vs Denmark, eloratings pending)
    "United States":      1721,   # -9
    "Panama":             1737,   # +7
    "Uzbekistan":         1727,
    "Venezuela":          1727,
    "Kosovo":             1721,   # -17 (eliminated)
    "Poland":             1729,   # -17 (eliminated)
    "Hungary":            1703,   # -2
    "Wales":              1698,   # -5 (eliminated)
    "Jordan":             1690,   # +3
    "Egypt":              1689,   # +9
    "Bolivia":            1645,   # estimated -25 (IC playoff final loss vs Iraq)
    "Ivory Coast":        1676,   # +13
    "Slovakia":           1673,   # +10 (eliminated)
    "Albania":            1646,   # -7 (eliminated)
    "DR Congo":           1655,   # estimated +15 (IC playoff final win vs Jamaica)
    "Romania":            1627,   # -10 (eliminated)
    "Ireland":            1691,   # -5 (eliminated)
    "Tunisia":            1626,
    "Haiti":              1532,   # +2
    "New Caledonia":      1286,
    "N. Macedonia":       1589,   # +5 (eliminated)
    "Iraq":               1607,   # estimated +25 (IC playoff final upset win vs Bolivia)
    "New Zealand":        1585,
    "Ghana":              1505,   # -1
    "Curaçao":            1436,   # -4
    "Qatar":              1425,
    "Cape Verde":         1549,
    "Saudi Arabia":       1568,   # -3
    "Northern Ireland":   1457,   # (eliminated)
    "Jamaica":            1535,   # estimated -15 (IC playoff final loss vs DR Congo)
    "Suriname":           1431,
    "South Africa":       1524,   # -7
}

# ---------------------------------------------------------------------------
# Host nations & advantage
# ---------------------------------------------------------------------------
WC_HOSTS: frozenset[str] = frozenset({"United States", "Canada", "Mexico"})
HOST_ELO_ADV: int = 50   # Elo-point boost for host nations in all matches

# ---------------------------------------------------------------------------
# Team style ratings
# Positive = attacking bias (scores more, concedes more than Elo alone predicts)
# Negative = defensive bias (scores less, concedes less)
# 0.0 (default) = balanced
# ---------------------------------------------------------------------------
WC_STYLE: dict[str, float] = {
    # Attacking teams
    "Norway":             0.20,   # Haaland-powered, high-scoring
    "Brazil":             0.15,
    "Argentina":          0.12,
    "Netherlands":        0.10,
    "Germany":            0.10,
    "Belgium":            0.08,
    "Ivory Coast":        0.08,
    "Ghana":              0.08,
    "Senegal":            0.05,
    "France":             0.05,
    "Portugal":           0.05,
    "Ecuador":            0.05,
    # Defensive teams
    "Morocco":           -0.18,   # WC2022 defence was exceptional
    "Iran":              -0.18,
    "Uruguay":           -0.15,
    "Panama":            -0.15,
    "Jordan":            -0.12,
    "Croatia":           -0.12,
    "Switzerland":       -0.10,
    "Japan":             -0.10,
    "Saudi Arabia":      -0.10,
    "Qatar":             -0.10,
    "South Africa":      -0.08,
    "New Zealand":       -0.08,
    "Haiti":             -0.08,
    "Curaçao":           -0.05,
    "Sweden":            -0.05,
    "Australia":         -0.05,
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
    "A": ["Mexico",        "South Korea",      "South Africa",  "Czechia"],
    "B": ["Canada",        "Switzerland",      "Qatar",         "Bosnia-Herzegovina"],
    "C": ["Brazil",        "Morocco",          "Scotland",      "Haiti"],
    "D": ["United States", "Paraguay",         "Australia",     "Turkey"],
    "E": ["Germany",       "Ecuador",          "Ivory Coast",   "Curaçao"],
    "F": ["Netherlands",   "Japan",            "Tunisia",       "Sweden"],
    "G": ["Belgium",       "Egypt",            "Iran",          "New Zealand"],
    "H": ["Spain",         "Uruguay",          "Saudi Arabia",  "Cape Verde"],
    "I": ["France",        "Senegal",          "Norway",        "Iraq"],
    "J": ["Argentina",     "Austria",          "Algeria",       "Jordan"],
    "K": ["Portugal",      "Colombia",         "Uzbekistan",    "DR Congo"],
    "L": ["England",       "Croatia",          "Ghana",         "Panama"],
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
        "final_winner":   "Bosnia-Herzegovina",
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
        "final_winner":   "Sweden",
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
        "final_winner":   "Turkey",
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
        "final_winner":   "Czechia",
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
        "sf_winner":    "Jamaica",  "sf_score":    "0–1",
        "final_winner": "DR Congo",
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
        "sf_winner":    "Bolivia", "sf_score":    "2–1",
        "final_winner": "Iraq",
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
