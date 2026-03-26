"""
League status labels — single source of truth for ALL leagues and ALL phases.

Structure per league:
  "regular" — used during the regular season
               For non-split leagues: European spots + relegation positions
               For split leagues: group assignment labels (→ Championship etc.)
               For Albania (Final Four): group/playoff labels
  "champ"   — Championship conference after split (positions within the conference)
  "relg"    — Relegation conference after split (positions within the conference)

Each phase is a flat dict:  {position (int): label (str)}
Only positions that need a label require an entry; all others show blank.

Used identically in Current Table and Predicted Table.
Edit this file to adjust any label — changes apply everywhere automatically.
"""

LEAGUE_STATUS: dict[str, dict[str, dict[int, str]]] = {

    # ─────────────────────────────────────────────────────────────────────────
    # TOP 5 LEAGUES
    # ─────────────────────────────────────────────────────────────────────────

    "English Premier League": {"regular": {
        1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UCL - LS",
        6: "UEL - LS", 7: "UEL - LS",
        8: "UECL - PO",
        18: "Relegation", 19: "Relegation", 20: "Relegation",
    }},

    "Italian Serie A": {"regular": {
        1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UEL - LS",
        6: "UEL - LS",
        7: "UECL - PO",
        18: "Relegation", 19: "Relegation", 20: "Relegation",
    }},

    "Spanish La Liga": {"regular": {
        1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UCL - LS",
        6: "UEL - LS", 7: "UEL - LS",
        8: "UECL - PO",
        18: "Relegation", 19: "Relegation", 20: "Relegation",
    }},

    "German Bundesliga": {"regular": {
        1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UEL - LS",
        6: "UEL - LS", 7: "UECL - PO",
        16: "Relegation - PO",
        17: "Relegation", 18: "Relegation",
    }},

    "French Ligue 1": {"regular": {
        1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - QR3 (LP)", 5: "UEL - LS",
        6: "UEL - LS", 7: "UECL - PO",
        16: "Relegation - PO",
        17: "Relegation", 18: "Relegation",
    }},

    # ─────────────────────────────────────────────────────────────────────────
    # NON-SPLIT LEAGUES  (alphabetical)
    # ─────────────────────────────────────────────────────────────────────────

    # Albania: Final Four playoff after regular season (not a traditional split)
    "Albanian Superliga": {
        "regular": {
            1: "Final Four", 2: "Final Four", 3: "Final Four", 4: "Final Four",
            8: "Relegation - PO",
            9: "Relegation", 10: "Relegation",
        },
        "final_four": {  # prizes at stake in the Final Four tournament
            1: "UCL - QR1",
            2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
        },
    },

    "Andorran Primera Divisió": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1",
        9: "Relegation - PO",
    }},

    "Armenian Premier League": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1",
    }},

    "Azerbaijani Premier League": {"regular": {
        1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1",
        11: "Relegation - PO", 12: "Relegation",
    }},

    "Belarus Vyscha Liga": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
        14: "Relegation - PO", 15: "Relegation", 16: "Relegation",
    }},

    "Bosnian Premier Liga": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1",
        9: "Relegation", 10: "Relegation",
    }},

    "Croatian First League": {"regular": {
        1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
        10: "Relegation",
    }},

    "Dutch Eredivisie": {"regular": {
        1: "UCL - LS", 2: "UCL - LS", 3: "UCL - QR3 (LP)", 4: "UEL - QR2",
        5: "UECL - PO", 6: "UEL - LS", 7: "UECL - PO", 8: "UECL - PO", 9: "UECL - PO",
        16: "Relegation - PO", 17: "Relegation", 18: "Relegation",
    }},

    "Estonian Meistriliiga": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
    }},

    "Faroe Islands Premier League": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
    }},

    "Georgian Erovnuli Liga": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1",
    }},

    "Hungarian NB I": {"regular": {
        1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
        11: "Relegation", 12: "Relegation",
    }},

    "Icelandic Úrvalsdeild": {"regular": {
        1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1",
    }},

    "Irish Premier Division": {"regular": {
        1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1",
    }},

    "Kazakhstan Premier League": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1",
    }},

    "Kosovan Superleague": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1",
    }},

    "Latvian Higher League": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
    }},

    "Lithuanian A Lyga": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
    }},

    "Luxembourgish National Div": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
    }},

    "Macedonian First League": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1",
        8: "Relegation - PO", 9: "Relegation - PO",
        10: "Relegation", 11: "Relegation", 12: "Relegation",
    }},

    # ── Moldovan National Division ── 8 teams · split Rd 21 · top 6 → Champ · pts ×0.5
    # Bottom 2 stay in pre-split table (champ_only) with Relegation - PO labels
    "Moldovan National Division": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation - PO", 8: "Relegation - PO",
        },
        "champ": {  # 6 teams · pts ×0.5 · 2nd = cup winner Sheriff cascade (UEL – QR1)
            1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1",
        },
    },

    "Montenegrin First League": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
        8: "Relegation - PO", 9: "Relegation - PO", 10: "Relegation",
    }},

    "Norwegian Eliteserien": {"regular": {
        1: "UCL - PO", 2: "UCL - QR2 (LP)", 3: "UEL - QR3", 4: "UECL - QR2", 5: "UECL - QR2",
        14: "Relegation - PO",
        15: "Relegation", 16: "Relegation",
    }},

    "Polish Ekstraklasa": {"regular": {
        1: "UCL - QR2", 2: "UCL - QR2 (LP)", 3: "UECL - QR2", 4: "UECL - QR2", 5: "UEL - QR3",
        16: "Relegation", 17: "Relegation", 18: "Relegation",
    }},

    "Portuguese Primeira Liga": {"regular": {
        1: "UCL - LS", 2: "UCL - LS", 3: "UEL - LS", 4: "UEL - QR2", 5: "UECL - QR2",
        16: "Relegation - PO", 17: "Relegation", 18: "Relegation",
    }},

    "Russian Premier League": {"regular": {
        13: "Relegation - PO", 14: "Relegation - PO",
        15: "Relegation", 16: "Relegation",
    }},

    "San Marino Campionato": {"regular": {
        1: "UCL - QR1", 2: "UECL - PO", 3: "UECL - PO", 4: "UECL - QR1",
        5: "UECL - PO", 6: "UECL - PO", 7: "UECL - PO", 8: "UECL - PO",
        9: "UECL - PO", 10: "UECL - PO", 11: "UECL - PO", 12: "UECL - PO",
    }},

    "Slovenian 1. SNL": {"regular": {
        1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR2",
        9: "Relegation - PO", 10: "Relegation",
    }},

    "Swedish Allsvenskan": {"regular": {
        1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
        14: "Relegation - PO",
        15: "Relegation", 16: "Relegation",
    }},

    "Turkish Super Lig": {"regular": {
        1: "UCL - LS", 2: "UCL - QR3 (LP)", 3: "UEL - PO", 4: "UEL - QR2", 5: "UECL - QR2",
        16: "Relegation", 17: "Relegation", 18: "Relegation",
    }},

    "Ukrainian Premier League": {"regular": {
        1: "UCL - PO", 2: "UECL - QR2", 3: "UECL - QR2", 4: "UEL - QR1",
        13: "Relegation - PO", 14: "Relegation - PO",
        15: "Relegation", 16: "Relegation",
    }},

    # ─────────────────────────────────────────────────────────────────────────
    # SPLIT LEAGUES
    # "regular" = group assignment labels shown during the pre-split regular season
    # "champ"   = status within Championship conference (pos 1 = best in champ)
    # "relg"    = status within Relegation conference  (pos 1 = best in relg)
    # Positions in "champ"/"relg" are within-conference positions, 1-indexed.
    # ─────────────────────────────────────────────────────────────────────────

    # ── Austrian Bundesliga ── 12 teams · split Rd 22 (11×2) · top 6 → Champ · pts ×0.5
    "Austrian Bundesliga": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams
            1: "UCL - PO", 2: "UCL - QR2 (LP)", 3: "UEL - QR3",
            4: "UECL - QR2", 5: "UECL Play-offs*",
        },
        "relg": {  # 6 teams · 1st (7th) and 2nd (8th) enter domestic UECL play-offs · last plays relegation PO
            1: "UECL Play-offs*", 2: "UECL Play-offs*",
            6: "Relegation",
        },
    },

    # ── Belgian Pro League ── 16 teams · split Rd 30 · top 6 → Champ · pts ×0.5
    # 7–12 → Europe Play-Offs (PO II, pts ×0.5), 13–16 → Relegation Play-Offs (full pts)
    "Belgian Pro League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "European Group", 8: "European Group", 9: "European Group",
            10: "European Group", 11: "European Group", 12: "European Group",
            13: "Relegation Group", 14: "Relegation Group",
            15: "Relegation Group", 16: "Relegation Group",
        },
        "champ": {  # 6 teams · pts halved (rounded up)
            1: "UCL - LS", 2: "UCL - QR3 (LP)", 3: "UEL - PO", 4: "UEL - QR2", 5: "UECL Play-offs*",
        },
        "mid": {  # 6 teams (Europe Play-offs, pts halved rounded up) · winner plays 5th from Champ
            1: "UECL Play-offs*",
        },
        "relg": {  # 4 teams (full pts) · last place plays relg PO vs Challenger Pro League
            4: "Relegation - PO",  # 16th overall (only relegation risk this season due to expansion)
        },
    },

    # ── Bulgarian First League ── 16 teams · split Rd 26 · top 4 → Champ · mid 4 → UECL PO · bottom 8 → Relg
    "Bulgarian First League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group",
            3: "Championship Group", 4: "Championship Group",
            5: "European Group", 6: "European Group",
            7: "European Group", 8: "European Group",
            9: "Relegation Group", 10: "Relegation Group", 11: "Relegation Group",
            12: "Relegation Group", 13: "Relegation Group", 14: "Relegation Group",
            15: "Relegation Group", 16: "Relegation Group",
        },
        "champ": {  # 4 teams · 4th plays CL Play-offs group winner for UECL spot
            1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL Play-offs*",
        },
        "mid": {  # 4 teams · winner plays 4th from Champ for UECL – QR2 spot
            1: "UECL Play-offs*",
        },
        "relg": {  # 8 teams (pos 9-16 overall) · 13th/14th (5th/6th) play PO · 15th/16th relegated
            5: "Relegation - PO", 6: "Relegation - PO",
            7: "Relegation", 8: "Relegation",
        },
    },

    # ── Czech First League ── 16 teams · split Rd 30 · top 6 → Champ · mid 4 → Middle · pts ×0.5
    # 7–10 → Middle Group · 11–16 → Relegation Group
    "Czech First League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Middle Group", 8: "Middle Group", 9: "Middle Group", 10: "Middle Group",
            11: "Relegation Group", 12: "Relegation Group", 13: "Relegation Group",
            14: "Relegation Group", 15: "Relegation Group", 16: "Relegation Group",
        },
        "champ": {  # 6 teams · pts ×0.5
            1: "UCL - LS", 2: "UCL - QR3 (LP)", 3: "UEL - QR2", 4: "UEL - PO", 5: "UECL - QR2",
        },
        "mid": {  # 4 teams · no European spots (placement group)
        },
        "relg": {  # 6 teams · 14th (4th) and 15th (5th) play PO vs Czech National League · 16th (6th) relegated
            4: "Relegation - PO",
            5: "Relegation - PO",
            6: "Relegation",
        },
    },

    # ── Cypriot First Division ── 14 teams · split Rd 26 (13×2) · top 6 → Champ · pts ×1.0
    "Cypriot First Division": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
            13: "Relegation Group", 14: "Relegation Group",
        },
        "champ": {  # 6 teams · 4th = cup winner Pafos → UEL – QR2
            1: "UCL - QR2", 2: "UECL - QR2", 3: "UECL - QR2", 4: "UEL - QR2*",
        },
        "relg": {  # 8 teams (pos 7-14 overall) · 12th (6th), 13th (7th), 14th (8th) relegated
            6: "Relegation",
            7: "Relegation",
            8: "Relegation",
        },
    },

    # ── Danish Superliga ── 12 teams · split Rd 22 (11×2) · top 6 → Champ · pts ×1.0
    "Danish Superliga": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams
            1: "UCL - QR2", 2: "UEL - QR2", 3: "UECL - QR3", 4: "UECL Play-offs*",
        },
        "relg": {  # 6 teams · 1st plays 4th from Champ (one-legged) · 11th/12th relegated
            1: "UECL Play-offs*",
            5: "Relegation",
            6: "Relegation",
        },
    },

    # ── Finnish Veikkausliiga ── 12 teams · split Rd 22 (11×2) · top 6 → Champ · pts ×1.0
    "Finnish Veikkausliiga": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams
            1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1",
        },
        "relg": {  # 6 teams · 11th (5th) = PO vs Ykkönen · 12th (6th) = relegated
            5: "Relegation - PO",
            6: "Relegation",
        },
    },

    # ── Gibraltar National League ── 12 teams · split Rd 22 (11×2) · top 6 → Champ only · pts ×1.0
    # Bottom 6 keep their regular-season positions — no Relegation Round
    "Gibraltar National League": {
        "regular": {
            1: "Championship Round", 2: "Championship Round", 3: "Championship Round",
            4: "Championship Round", 5: "Championship Round", 6: "Championship Round",
            12: "Relegation",
        },
        "champ": {  # 6 teams · 3rd = cup winner Lincoln Red Imps cascades here
            1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1",
        },
    },

    # ── Greek Super League ── 14 teams · split Rd 26 (13×2) · top 4 → Champ, next 4 → European · pts ×0.5
    "Greek Super League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group",
            3: "Championship Group", 4: "Championship Group",
            5: "European Group", 6: "European Group",
            7: "European Group", 8: "European Group",
            9: "Relegation Group", 10: "Relegation Group", 11: "Relegation Group",
            12: "Relegation Group", 13: "Relegation Group", 14: "Relegation Group",
        },
        "champ": {  # 4 teams · pts ×0.5 · 3rd = cup winner PAOK cascades here
            1: "UCL - LS", 2: "UCL - QR2 (LP)", 3: "UEL - PO", 4: "UEL - QR2",
        },
        "mid": {  # 4 teams (European Group) · winner → UECL – QR2
            1: "UECL - QR2",
        },
        "relg": {  # 6 teams · 12th overall (4th in relg) = PO vs SL2
                   #         · 13th–14th overall (5th–6th in relg) = directly relegated
            4: "Relegation - PO",
            5: "Relegation",
            6: "Relegation",
        },
    },

    # ── Israeli Premier League ── 14 teams · split Rd 26 (13×2) · top 6 → Champ · pts ×1.0
    "Israeli Premier League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
            13: "Relegation Group", 14: "Relegation Group",
        },
        "champ": {  # 6 teams · 2nd = cup winner Beer Sheva cascade (UEL – QR1)
            1: "UEL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
        },
        "relg": {  # 8 teams (pos 7-14 overall) · 12th (6th) = PO · 13th (7th), 14th (8th) = relegated
            6: "Relegation - PO",
            7: "Relegation",
            8: "Relegation",
        },
    },

    # ── Maltese Premier League ── 12 teams · Opening + Closing Round · split Rd 27 (11 OR + 5 OR + 11 CR)
    # Each round: top 6 → Championship Group · bottom 6 → Relegation Group · pts carry over within round
    "Maltese Premier League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams · pts carry over
            1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1",
        },
        "relg": {  # 6 teams (pos 7-12 overall) · 10th (4th) = PO · 11th (5th), 12th (6th) = relegated
            4: "Relegation - PO",
            5: "Relegation",
            6: "Relegation",
        },
    },

    # ── Northern Irish Premiership ── 12 teams · split Rd 33 (11×3) · top 6 → Champ · pts ×1.0
    # 4th–6th in Champ + 1st in Relg (7th overall) enter UECL 4-team Play-off
    "Northern Irish Premiership": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams · 2nd = cup winner Larne cascade (UECL – QR2)
            1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1",
            4: "UECL - PO", 5: "UECL - PO", 6: "UECL - PO",
        },
        "relg": {  # 6 teams · 1st (7th overall) enters UECL PO · 5th/6th relegated
            1: "UECL - PO",
            5: "Relegation - PO",
            6: "Relegation",
        },
    },

    # ── Romanian Liga I ── 16 teams · split Rd 30 (15×2) · top 6 → Champ · pts ×0.5 (rounded up)
    # Bottom 10 → Play-out; 1st/2nd in play-out (7th/8th overall) enter UECL 3-team PO with 4th (champ)
    "Romanian Liga I": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group", 10: "Relegation Group",
            11: "Relegation Group", 12: "Relegation Group", 13: "Relegation Group", 14: "Relegation Group",
            15: "Relegation Group", 16: "Relegation Group",
        },
        "champ": {  # 6 teams · pts ×0.5 · 2nd = Craiova (cup winner, no cascade) · 4th enters UECL PO
            1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - PO",
        },
        "relg": {  # 10 teams (play-out) · 1st/2nd enter UECL PO · 7th/8th = Relegation PO · 9th/10th relegated
            1: "UECL - PO",
            2: "UECL - PO",
            7: "Relegation - PO",
            8: "Relegation - PO",
            9: "Relegation",
            10: "Relegation",
        },
    },

    # ── Scottish Premiership ── 12 teams · split Rd 33 (11×3) · top 6 → Champ · pts ×1.0
    "Scottish Premiership": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams · 3rd = cup winner Celtic cascade (UEL – QR3)
            1: "UCL - PO", 2: "UCL - QR2 (LP)", 3: "UEL - QR3",
            4: "UECL - QR2", 5: "UECL - QR2",
        },
        "relg": {  # 6 teams · 11th overall (5th) = PO vs Championship 2nd · 12th (6th) = relegated
            5: "Relegation - PO",
            6: "Relegation",
        },
    },

    # ── Serbian Super Liga ── 16 teams · split Rd 30 (15×2) · top 8 → Champ · pts ×0.5
    "Serbian Super Liga": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Championship Group", 8: "Championship Group",
            9: "Relegation Group", 10: "Relegation Group", 11: "Relegation Group",
            12: "Relegation Group", 13: "Relegation Group", 14: "Relegation Group",
            15: "Relegation Group", 16: "Relegation Group",
        },
        "champ": {  # 8 teams · pts ×0.5
            1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
        },
        "relg": {  # 8 teams (pos 9-16 overall) · pts ×0.5 · 13th–14th (5th–6th) = PO · 15th–16th (7th–8th) relegated
            5: "Relegation - PO",
            6: "Relegation - PO",
            7: "Relegation",
            8: "Relegation",
        },
    },

    # ── Slovak First League ── 12 teams · split Rd 22 (11×2) · top 6 → Champ · pts ×1.0
    "Slovak First League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams
            1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
        },
        "relg": {  # 6 teams · 11th (5th) = PO vs Slovak 2. liga · 12th (6th) = relegated
            5: "Relegation - PO",
            6: "Relegation",
        },
    },

    # ── Swiss Super League ── 12 teams · split Rd 33 (11×3) · top 6 → Champ · pts ×1.0
    "Swiss Super League": {
        "regular": {
            1: "Championship Group", 2: "Championship Group", 3: "Championship Group",
            4: "Championship Group", 5: "Championship Group", 6: "Championship Group",
            7: "Relegation Group", 8: "Relegation Group", 9: "Relegation Group",
            10: "Relegation Group", 11: "Relegation Group", 12: "Relegation Group",
        },
        "champ": {  # 6 teams
            1: "UCL - QR2", 2: "UEL - QR2", 3: "UECL - QR2", 4: "UECL - QR2",
        },
        "relg": {  # 6 teams · 11th (5th) = PO vs Challenge League · 12th (6th) = relegated
            5: "Relegation - PO",
            6: "Relegation",
        },
    },

    # ── Welsh Premier League ── 12 teams · split Rd 22 (11×2) · top 6 → Championship Conference · pts ×1.0
    "Welsh Premier League": {
        "regular": {
            1: "Championship Conference", 2: "Championship Conference", 3: "Championship Conference",
            4: "Championship Conference", 5: "Championship Conference", 6: "Championship Conference",
            7: "Play-Off Conference", 8: "Play-Off Conference", 9: "Play-Off Conference",
            10: "Play-Off Conference", 11: "Play-Off Conference", 12: "Play-Off Conference",
        },
        "champ": {  # 6 teams
            1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - PO", 4: "UECL - PO", 5: "UECL - PO",
        },
        "relg": {  # 6 teams (pos 7-12 overall) · 1st and 2nd enter UECL play-offs
            1: "UECL - PO", 2: "UECL - PO",
        },
    },
}


def get_status(league_name: str, pos: int, phase: str = "regular") -> str:
    """Return the status label for a given league, position, and phase.

    phase: "regular" | "champ" | "relg"
    Returns empty string if no label is defined.
    """
    return LEAGUE_STATUS.get(league_name, {}).get(phase, {}).get(pos, "")
