# TheSportsDB league IDs for all 54 UEFA first-tier leagues.
# (Liechtenstein excluded — no domestic league; clubs play in Swiss system)
#
# season_type:
#   "winter" – season spans two calendar years (Aug–May), e.g. "2025-2026"
#   "summer" – season runs within one calendar year (Apr–Nov), e.g. "2025"

LEAGUES = {
    # ── Top 5 (pinned) ───────────────────────────────────────────────────────
    "English Premier League":       {"id": 4328, "country": "England",     "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "season_type": "winter",
                                     "season_end": "24 May 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_away_gf", "playoffs"],
                                     "home_advantage": 1.18,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UCL - LS", 6: "UEL - LS", 7: "UEL - LS", 8: "UECL - PO"},
                                     "cup_details": (
                                         "2025/26 FA Cup winner qualifies for the UEL – LS. "
                                         "As Arsenal are predicted to win the 2025/26 FA Cup and secure a European place through their league position, "
                                         "the UEL – LS spot is projected to pass to the 7th-placed team.\n\n"
                                         "2025/26 EFL Cup winner qualifies for the UECL – PO. "
                                         "As Manchester City won the 2025/26 EFL Cup and are predicted to secure a European place through their league position, "
                                         "the UECL – PO spot is projected to pass to the 8th-placed team."
                                     ),
                                     "team_status_note": "*Crystal Palace are projected to qualify for the UEL – LS as the predicted winners of the 2025/26 Conference League.",
                                     "team_status_overrides": {"Crystal Palace": "UEL - LS*"}},
    "Italian Serie A":              {"id": 4332, "country": "Italy",       "flag": "🇮🇹", "season_type": "winter",
                                     "season_end": "24 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "gd", "gf", "playoffs_title_or_rel3"],
                                     "home_advantage": 1.16,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UEL - LS", 6: "UEL - LS", 7: "UECL - PO"},
                                     "cup_details": (
                                         "2025/26 Coppa Italia winner qualifies for the UEL – LS. "
                                         "As Inter are predicted to win the 2025/26 Coppa Italia and secure a European place through their league position, "
                                         "the UEL – LS spot is projected to pass to the 6th-placed team."
                                     )},
    "Spanish La Liga":              {"id": 4335, "country": "Spain",       "flag": "🇪🇸", "season_type": "winter",
                                     "season_end": "24 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "gd", "gf", "fair_play"],
                                     "home_advantage": 1.16,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UCL - LS", 6: "UEL - LS", 7: "UEL - LS", 8: "UECL - PO"},
                                     "cup_details": (
                                         "2025/26 Copa del Rey winner qualifies for the UEL – LS. "
                                         "As Atlético Madrid are predicted to win the 2025/26 Copa del Rey and secure a European place through their league position, "
                                         "the UEL – LS spot is projected to pass to the 7th-placed team."
                                     )},
    "German Bundesliga":            {"id": 4331, "country": "Germany",     "flag": "🇩🇪", "season_type": "winter",
                                     "season_end": "16 May 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_away_gf", "away_gf", "playoffs"],
                                     "home_advantage": 1.15,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - LS", 5: "UEL - LS", 6: "UEL - LS", 7: "UECL - PO"},
                                     "zone_notes": {"relegation - po": "16th plays two-legged play-off against 3rd-placed team from 2. Bundesliga. Higher-ranked team plays second leg at home."},
                                     "cup_details": (
                                         "2025/26 DFB-Pokal winner qualifies for the UEL – LS. "
                                         "As Bayern Munich are predicted to win the 2025/26 DFB-Pokal and secure a European place through their league position, "
                                         "the UEL – LS spot is projected to pass to the 6th-placed team."
                                     )},
    "French Ligue 1":               {"id": 4334, "country": "France",      "flag": "🇫🇷", "season_type": "winter",
                                     "season_end": "16 May 2026",
                                     "tiebreakers": ["gd", "h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gf", "away_gf", "fair_play"],
                                     "home_advantage": 1.17,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - LS", 3: "UCL - LS", 4: "UCL - QR3 (LP)", 5: "UEL - LS", 6: "UEL - LS", 7: "UECL - PO"},
                                     "zone_notes": {"relegation - po": "16th plays two-legged play-off against 3rd-placed team from Ligue 2. Away goals do not apply; extra time and penalties if level after two legs."},
                                     "cup_details": (
                                         "2025/26 Coupe de France winner qualifies for the UEL – LS. "
                                         "As RC Lens are predicted to win the 2025/26 Coupe de France and secure a European place through their league position, "
                                         "the UEL – LS spot is projected to pass to the 6th-placed team."
                                     )},
    # ── Rest (alphabetical) ──────────────────────────────────────────────────
    "Albanian Superliga":           {"id": 4617, "country": "Albania",     "flag": "🇦🇱", "season_type": "winter",
                                     "season_end": "24 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "draw"],
                                     "home_advantage": 1.23,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1"},
                                     "final_four": True,
                                     "zones": {
                                         "Final Four": [1, 2, 3, 4],
                                         "Relegation - PO": [8],
                                         "Relegation": [9, 10],
                                     },
                                     "zone_notes": {
                                         "final four": "Top 4 teams play a knock-out Final Four to determine the champion. Draw is conducted with two seeded teams (1st, 2nd) and two unseeded (3rd, 4th). Seeded teams cannot meet in the semi-finals. If level after 90 minutes in a semi-final, the higher-ranked team advances. The final is decided by extra time and penalties if necessary.",
                                         "relegation - po": "The 8th ranked team qualifies to the play-off round, which they play against the Kategoria e Parë play-off winner.",
                                     },
                                     "cup_details": (
                                         "2025/26 Albanian Cup winner qualifies for the UECL – QR1. "
                                         "As Egnatia are predicted to win the 2025/26 Albanian Cup and secure a European place through their league position, "
                                         "the UECL – QR1 spot is projected to pass to the 4th-placed team."
                                     )},
    "Andorran Primera Divisió":     {"id": 4618, "country": "Andorra",     "flag": "🇦🇩", "season_type": "winter",
                                     "season_end": "17 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf"],
                                     "home_advantage": 1.28,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1"},
                                     "cup_details": (
                                         "2026 Copa Constitució winner qualifies for the UECL – QR1. "
                                         "As Inter Club d'Escaldes are predicted to win the 2026 Copa Constitució and secure a European place through their league position, "
                                         "the UECL – QR1 spot is projected to pass to the 3rd-placed team."
                                     )},
    "Armenian Premier League":      {"id": 4619, "country": "Armenia",     "flag": "🇦🇲", "season_type": "winter",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "wins", "gd", "less_red_cards", "less_yellow_cards", "fair_play", "draw"],
                                     "home_advantage": 1.42,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 10: "Relegation"},
                                     "cup_details": (
                                         "2025/26 Armenian Cup winner qualifies for the UECL – QR2. "
                                         "Noah are predicted to win the 2025/26 Armenian Cup and secure a UECL – QR2 spot."
                                     ),
                                     "team_status_note": "*Noah are projected to qualify for the UECL – QR2 as the predicted winners of the 2025/26 Armenian Cup.",
                                     "team_status_overrides": {"Noah": "UECL - QR2*"}},
    "Austrian Bundesliga":          {"id": 4621, "country": "Austria",     "flag": "🇦🇹", "season_type": "winter",
                                     "season_end": "24 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf"],
                                     "home_advantage": 1.10,
                                     "champ_tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "wins", "away_wins", "away_gf"],
                                     "european_spots": {1: "UCL - PO", 2: "UCL - QR2 (LP)", 3: "UEL - QR3", 4: "UECL - QR2"},
                                     "split_round": 22, "n_champ": 6, "pts_factor": 0.5,
                                     "uecl_playoff": True,
                                     "zone_notes": {"relegation": "Last-placed team in the Relegation Round plays a two-legged play-off against 2nd-placed team from 2. Liga. Home team in first leg is the lower-ranked club."},
                                     "cup_details": (
                                         "2025/26 Austrian Cup winner qualifies for the UEL – QR3. "
                                         "As LASK are predicted to win the 2025/26 Austrian Cup and finish 3rd in the league, "
                                         "there are no additional movements when it comes to European spots."
                                     )},
    "Azerbaijani Premier League":   {"id": 4693, "country": "Azerbaijan",  "flag": "🇦🇿", "season_type": "winter",
                                     "tiebreakers": ["wins", "gd", "gf", "h2h_pts", "h2h_gd", "disciplinary", "draw"],
                                     "home_advantage": 1.00,
                                     "european_spots": {1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1", 11: "Relegation - PO", 12: "Relegation"},
                                     "cup_details": (
                                         "2025/26 Azerbaijan Cup winner qualifies for the UEL – QR1. "
                                         "As Qarabağ are predicted to win the 2025/26 Azerbaijan Cup and finish 2nd in the league, "
                                         "there are no additional movements when it comes to European spots."
                                     )},
    "Belarus Vyscha Liga":          {"id": 4622, "country": "Belarus",     "flag": "🇧🇾", "season_type": "summer",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "wins", "gf"],
                                     "home_advantage": 1.14,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1", 14: "Relegation - PO", 15: "Relegation", 16: "Relegation"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Belgian Pro League":           {"id": 4338, "country": "Belgium",     "flag": "🇧🇪", "season_type": "winter",
                                     "season_end": "17 May 2026",
                                     "tiebreakers": ["wins", "gd", "gf", "away_gf", "away_wins"],
                                     "home_advantage": 1.13,
                                     "champ_tiebreakers": ["pts_no_round", "regular_pts"],
                                     "mid_tiebreakers":   ["pts_no_round", "regular_pts"],
                                     "relg_tiebreakers":  ["regular_position"],
                                     "european_spots": {1: "UCL - LS", 2: "UCL - QR3 (LP)", 3: "UEL - PO", 4: "UEL - QR2", 5: "UECL - PO", 7: "UECL - PO", 16: "Relegation - PO"},
                                     "split_round": 30, "n_champ": 6, "n_mid": 6, "pts_factor": 0.5, "relg_pts_factor": 1.0,
                                     "pts_round": "up",
                                     "mid_label": "Europe Play-offs",
                                     "zone_notes": {"europa": "Europe Play-offs (7th–12th, pts halved rounded up): two sub-groups of 3. Group winners meet in a final for one spot. The Europe Play-offs winner plays 5th from the Championship Round in a one-legged tie hosted by 5th. Winner qualifies for UECL – QR2.", "relegation": "Relegation Play-offs (13th–16th, full pts): bottom 4 play a round-robin. Only last place (16th) plays a promotion/relegation play-off vs Challenger Pro League winner."},
                                     "cup_details": (
                                         "2025/26 Belgian Cup winner qualifies for the UEL – PO. "
                                         "As Union SG are predicted to win the 2025/26 Belgian Cup and secure a European place through their league position, "
                                         "the UEL – PO spot is projected to pass to the 4th-placed team."
                                     ),
                                     "champ_mid_playoff": {
                                         "champ_pos": 5,
                                         "winner_spot": "UECL - QR2",
                                         "caption": "5th-placed team (Championship Round) hosts a one-legged tie against the winner of the Europe Play-offs. Winner qualifies for UECL – QR2.",
                                     }},
    "Bosnian Premier Liga":         {"id": 4624, "country": "Bosnia",      "flag": "🇧🇦", "season_type": "winter",
                                     "season_end": "31 May 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "h2h_away_gf", "h2h_gf", "playoffs"],
                                     "home_advantage": 1.47,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1", 9: "Relegation", 10: "Relegation"},
                                     "cup_details": (
                                         "2025/26 Bosnia and Herzegovina Football Cup winner qualifies for the UECL – QR2. "
                                         "As Zrinjski Mostar are predicted to win the 2025/26 Bosnia and Herzegovina Football Cup and finish 2nd in the league, "
                                         "there are no additional movements when it comes to European spots."
                                     )},
    "Bulgarian First League":       {"id": 4626, "country": "Bulgaria",    "flag": "🇧🇬", "season_type": "winter",
                                     "season_end": "29 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "fair_play", "draw"],
                                     "home_advantage": 1.17,
                                     "european_spots": {1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - PO", 5: "UECL - PO", 13: "Relegation - PO", 14: "Relegation - PO", 15: "Relegation", 16: "Relegation"},
                                     "split_round": 30, "n_champ": 4, "n_mid": 4, "pts_factor": 1.0,
                                     "mid_label": "Conference League Play-offs",
                                     "zone_notes": {"europa": "Conference League Play-offs (5th–8th): round-robin. Winner plays 4th from Championship Group in a one-legged tie hosted by 4th. Winner qualifies for UECL – QR2.", "relegation": "Relegation Round (9th–16th): 13th and 14th play promotion/relegation play-offs against teams from the Second Professional Football League. 15th and 16th are directly relegated."},
                                     "cup_details": (
                                         "2025/26 Bulgarian Cup winner qualifies for the UEL – QR1. "
                                         "As Ludogorets Razgrad are predicted to win the 2025/26 Bulgarian Cup and finish 2nd in the league, "
                                         "there are no additional movements when it comes to European spots."
                                     ),
                                     "champ_mid_playoff": {
                                         "champ_pos": 4,
                                         "winner_spot": "UECL - QR2",
                                         "caption": "4th-placed team (Championship Group) hosts a one-legged tie against the winner of the Conference League Play-offs (5th–8th). Winner qualifies for UECL – QR2.",
                                     }},
    "Croatian First League":        {"id": 4629, "country": "Croatia",     "flag": "🇭🇷", "season_type": "winter",
                                     "season_end": "23 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "playoffs"],
                                     "home_advantage": 1.25,
                                     "european_spots": {1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2", 10: "Relegation"},
                                     "cup_details": (
                                         "2025/26 Croatian Football Cup winner qualifies for the UEL – QR1. "
                                         "As Dinamo Zagreb are predicted to win the 2025/26 Croatian Football Cup and secure a European place through their league position, "
                                         "the UEL – QR1 spot is projected to pass to the 2nd-placed team."
                                     )},
    "Czech First League":           {"id": 4631, "country": "Czech Rep.",  "flag": "🇨🇿", "season_type": "winter",
                                     "season_end": "31 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "fair_play", "draw"],
                                     "home_advantage": 1.15,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - QR3 (LP)", 3: "UEL - QR2", 4: "UEL - PO", 5: "UECL - QR2"},
                                     "split_round": 30, "n_champ": 6, "n_mid": 4, "pts_factor": 0.5,
                                     "mid_label": "Middle Group",
                                     "zone_notes": {"relegation": "16th is directly relegated. 14th and 15th play two-legged play-offs against 2nd and 3rd of Czech National Football League."},
                                     "cup_details": (
                                         "2025/26 Czech Cup winner qualifies for the UECL – QR2. "
                                         "As Jablonec are predicted to win the 2025/26 Czech Cup and finish 4th in the Championship Round, "
                                         "they will qualify for the UEL – PO through their league position. "
                                         "The UECL – QR2 cup spot is projected to pass to the 5th-placed team."
                                     ),
                                     "team_status_note": "*Jablonec are projected to finish 4th in the Championship Round, qualifying for the UEL – PO. As predicted Czech Cup winners, their UECL – QR2 cup spot passes to the 5th-placed team.",
                                     "team_status_overrides": {"Jablonec": "UEL - PO*"}},
    "Cypriot First Division":       {"id": 4630, "country": "Cyprus",      "flag": "🇨🇾", "season_type": "winter",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "playoffs"],
                                     "home_advantage": 1.25,
                                     "european_spots": {1: "UCL - QR2", 2: "UECL - QR2", 3: "UECL - QR2", 4: "UEL - QR2", 12: "Relegation", 13: "Relegation", 14: "Relegation"},
                                     "split_round": 26, "n_champ": 6, "pts_factor": 1.0,
                                     "cup_details": (
                                         "2025/26 Cypriot Cup winner qualifies for the UEL – QR2. "
                                         "As Pafos are predicted to win the 2025/26 Cypriot Cup and finish 4th in the Championship Round, "
                                         "they will qualify for the UEL – QR2 through their league position. "
                                         "The cup spot is covered by their league placing."
                                     ),
                                     "team_status_note": "*Pafos are projected to finish 4th in the Championship Round, qualifying for the UEL – QR2 as predicted Cypriot Cup winners.",
                                     "team_status_overrides": {"Pafos": "UEL - QR2*"}},
    "Danish Superliga":             {"id": 4340, "country": "Denmark",     "flag": "🇩🇰", "season_type": "winter",
                                     "season_end": "26 May 2026",
                                     "tiebreakers": ["gd", "gf", "away_gf", "playoffs", "draw"],
                                     "home_advantage": 1.12,
                                     "european_spots": {1: "UCL - QR2", 2: "UEL - QR2", 3: "UECL - QR3", 4: "UECL - PO", 7: "UECL - PO", 11: "Relegation", 12: "Relegation"},
                                     "split_round": 22, "n_champ": 6, "pts_factor": 1.0,
                                     "zone_notes": {"relegation": "11th and 12th are directly relegated."},
                                     "cup_details": (
                                         "2025/26 Danish Cup winner qualifies for the UEL – QR2. "
                                         "As Midtjylland are predicted to win the 2025/26 Danish Cup and secure a European place through their league position, "
                                         "the UEL – QR2 spot is projected to pass to the 2nd-placed team."
                                     ),
                                     "champ_mid_playoff": {
                                         "champ_pos": 4,
                                         "away_conf": "relg",
                                         "away_pos": 1,
                                         "away_label": "1st (Relegation Round / 7th overall)",
                                         "winner_spot": "UECL - QR3",
                                         "caption": "4th-placed team (Championship Round) hosts a one-legged tie against the 1st-placed team of the Relegation Round (7th overall). Winner qualifies for UECL – QR3.",
                                     }},
    "Dutch Eredivisie":             {"id": 4337, "country": "Netherlands", "flag": "🇳🇱", "season_type": "winter",
                                     "season_end": "24 May 2026",
                                     "tiebreakers": ["less_losses", "gd", "gf", "h2h_pts", "h2h_gd", "h2h_away_gf", "playoffs"],
                                     "home_advantage": 1.24,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - LS", 3: "UCL - QR3 (LP)", 4: "UEL - QR2",
                                                        5: "UECL - PO", 6: "UEL - LS", 7: "UECL - PO", 8: "UECL - PO", 9: "UECL - PO",
                                                        16: "Relegation - PO", 17: "Relegation", 18: "Relegation"},
                                     "cup_details": (
                                         "2025/26 KNVB Cup winner qualifies for the UEL – LS. "
                                         "As AZ Alkmaar are predicted to win the 2025/26 KNVB Cup and their 6th-place finish already secures a UEL – LS spot, "
                                         "no cascade applies."
                                     ),
                                     "team_status_overrides": {"AZ Alkmaar": "UEL - LS*"},
                                     "uecl_4team_playoff": {
                                         "sf1_home": 5, "sf1_away": 9,
                                         "sf2_home": 7, "sf2_away": 8,
                                         "winner_spot": "UECL - LS",
                                         "caption": (
                                             "5th-placed team hosts 9th in SF1; 7th-placed team hosts 8th in SF2 (one-legged ties). "
                                             "Final hosted by the highest-ranked SF winner. Winner qualifies for UECL – LS."
                                         ),
                                     }},
    "Estonian Meistriliiga":        {"id": 4634, "country": "Estonia",     "flag": "🇪🇪", "season_type": "summer",
                                     "season_end": "8 November 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "wins", "gd", "gf", "away_gf", "fair_play", "draw"],
                                     "home_advantage": 1.20,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Faroe Islands Premier League": {"id": 4635, "country": "Faroe Isl.",  "flag": "🇫🇴", "season_type": "summer",
                                     "season_end": "25 October 2026",
                                     "tiebreakers": ["gd", "gf"],
                                     "home_advantage": 1.10,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Finnish Veikkausliiga":        {"id": 4636, "country": "Finland",     "flag": "🇫🇮", "season_type": "summer",
                                     "season_end": "26 October 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "fair_play", "draw"],
                                     "home_advantage": 1.02,
                                     "champ_tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "h2h_away_gf", "playoffs"],
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "split_round": 22, "n_champ": 6, "pts_factor": 1.0,
                                     "zone_notes": {"relegation": "11th is directly relegated. 12th plays two-legged play-off against a Ykkönen team. Higher-ranked club plays second leg at home."},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Georgian Erovnuli Liga":       {"id": 4638, "country": "Georgia",     "flag": "🇬🇪", "season_type": "summer",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf"],
                                     "home_advantage": 1.20,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Gibraltar National League":    {"id": 4964, "country": "Gibraltar",   "flag": "🇬🇮", "season_type": "winter",
                                     "season_end": "26 April 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "fair_play", "draw"],
                                     "home_advantage": 1.00,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1"},
                                     "split_round": 22, "n_champ": 6, "pts_factor": 1.0, "champ_only": True,
                                     "cup_details": (
                                         "2025/26 Peninsula Rock Cup winner qualifies for the UECL – QR1. "
                                         "As Lincoln Red Imps won the 2025/26 Peninsula Rock Cup and secured a European place through their league position (2nd), "
                                         "the UECL – QR1 cup spot passes to the 3rd-placed team."
                                     )},
    "Greek Super League":           {"id": 4336, "country": "Greece",      "flag": "🇬🇷", "season_type": "winter",
                                     "season_end": "21 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "gd", "gf", "playoffs"],
                                     "home_advantage": 1.25,
                                     "champ_tiebreakers": ["h2h_pts", "h2h_gd", "gd", "gf", "playoffs_champion"],
                                     "european_spots": {1: "UCL - LS", 2: "UCL - QR2 (LP)", 3: "UEL - PO", 4: "UEL - QR2", 5: "UECL - QR2"},
                                     "split_round": 26, "n_champ": 4, "n_mid": 4, "pts_factor": 0.5,
                                     "mid_label": "European Group",
                                     "zone_notes": {"europa": "5th–8th play an additional round-robin (European Group, pts halved). Winner qualifies for UECL – QR2.", "relegation": "13th and 14th are directly relegated. 12th plays a two-legged play-off against a Super League 2 team."},
                                     "cup_details": (
                                         "2025/26 Greek Football Cup winner qualifies for the UEL – PO. "
                                         "As PAOK are predicted to win the 2025/26 Greek Football Cup and secure a European place through their league position, "
                                         "the UEL – PO spot is projected to pass to the 3rd-placed team."
                                     )},
    "Hungarian NB I":               {"id": 4690, "country": "Hungary",     "flag": "🇭🇺", "season_type": "winter",
                                     "season_end": "17 May 2026",
                                     "tiebreakers": ["wins", "gd", "gf", "h2h_pts", "h2h_gd", "fair_play", "draw"],
                                     "home_advantage": 1.01,
                                     "european_spots": {1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
                                                        11: "Relegation", 12: "Relegation"},
                                     "cup_details": (
                                         "2025/26 Magyar Kupa winner qualifies for the UEL – QR1. "
                                         "As Ferencváros are predicted to win the 2025/26 Magyar Kupa and secure a European place through their league position, "
                                         "the UEL – QR1 spot is projected to pass to the 2nd-placed team."
                                     ),
                                     "team_status_overrides": {"Ferencváros": "UCL - QR2*"}},
    "Icelandic Úrvalsdeild":        {"id": 4642, "country": "Iceland",     "flag": "🇮🇸", "season_type": "summer",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf"],
                                     "home_advantage": 1.40,
                                     "european_spots": {1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Irish Premier Division":       {"id": 4643, "country": "Ireland",     "flag": "🇮🇪", "season_type": "summer",
                                     "season_end": "1 November 2026",
                                     "tiebreakers": ["gd", "gf"],
                                     "home_advantage": 1.22,
                                     "european_spots": {1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Israeli Premier League":       {"id": 4644, "country": "Israel",      "flag": "🇮🇱", "season_type": "winter",
                                     "tiebreakers": ["gd", "wins", "gf", "h2h_pts", "h2h_gd", "h2h_gf", "playoffs"],
                                     "home_advantage": 1.05,
                                     "european_spots": {1: "UEL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2"},
                                     "cup_details": (
                                         "2025/26 Israel State Cup winner qualifies for the UEL – QR1. "
                                         "As Hapoel Beer Sheva are predicted to win the 2025/26 Israel State Cup and secure a European place through their league position, "
                                         "the UEL – QR1 spot is projected to pass to the 2nd-placed team."
                                     ),
                                     "team_status_overrides": {"Hapoel Beer Sheva": "UEL - QR2*"},
                                     "split_round": 26, "n_champ": 6, "pts_factor": 1.0},
    "Kazakhstan Premier League":    {"id": 4649, "country": "Kazakhstan",  "flag": "🇰🇿", "season_type": "summer",
                                     "season_end": "26 October 2026",
                                     "tiebreakers": ["gd", "wins", "gf", "away_gf", "h2h_pts", "h2h_wins", "h2h_gd", "h2h_gf", "h2h_away_gf", "draw"],
                                     "home_advantage": 1.27,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Kosovan Superleague":          {"id": 4968, "country": "Kosovo",      "flag": "🇽🇰", "season_type": "winter",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "gd", "gf", "playoffs"],
                                     "home_advantage": 1.07,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "cup_details": (
                                         "2025/26 Kosovar Cup winner qualifies for the UECL – QR2. "
                                         "As Ballkani are predicted to win the 2025/26 Kosovar Cup and finish 2nd in the league, "
                                         "there are no additional movements when it comes to European spots."
                                     ),
                                     "team_status_overrides": {"Ballkani": "UECL - QR2*"}},
    "Latvian Higher League":        {"id": 4650, "country": "Latvia",      "flag": "🇱🇻", "season_type": "summer",
                                     "season_end": "23 November 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "gd", "gf", "fair_play", "playoffs"],
                                     "home_advantage": 1.07,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Lithuanian A Lyga":            {"id": 4651, "country": "Lithuania",   "flag": "🇱🇹", "season_type": "summer",
                                     "season_end": "8 November 2026",
                                     "tiebreakers": ["playoffs_champion", "h2h_pts", "h2h_gd", "h2h_gf", "h2h_wins", "gd", "gf", "wins", "fair_play", "draw"],
                                     "home_advantage": 1.17,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Luxembourgish National Div":   {"id": 4694, "country": "Luxembourg",  "flag": "🇱🇺", "season_type": "winter",
                                     "tiebreakers": ["gd", "wins", "h2h_pts", "h2h_gd", "h2h_gf", "playoffs"],
                                     "home_advantage": 1.20,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1"},
                                     "cup_details": (
                                         "2025/26 Luxembourg Cup winner qualifies for the UECL – QR1. "
                                         "As Differdange 03 are predicted to win the 2025/26 Luxembourg Cup and secure a European place through their league position, "
                                         "the UECL – QR1 spot is projected to pass to the 4th-placed team."
                                     ),
                                     "team_status_overrides": {"Differdange 03": "UECL - QR1*"}},
    "Macedonian First League":      {"id": 4652, "country": "N. Macedonia","flag": "🇲🇰", "season_type": "winter",
                                     "season_end": "31 May 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "h2h_away_gf", "h2h_gf", "draw", "playoffs"],
                                     "home_advantage": 1.22,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1",
                                                        8: "Relegation - PO", 9: "Relegation - PO",
                                                        10: "Relegation", 11: "Relegation", 12: "Relegation"},
                                     "cup_details": (
                                         "2025/26 Macedonian Football Cup winner qualifies for the UECL – QR1. "
                                         "As Shkëndija are predicted to win the 2025/26 Macedonian Football Cup and secure a European place through their league position, "
                                         "the UECL – QR1 spot is projected to pass to the 3rd-placed team."
                                     ),
                                     "team_status_overrides": {"Shkëndija": "UECL - QR1*"}},
    "Maltese Premier League":       {"id": 4653, "country": "Malta",       "flag": "🇲🇹", "season_type": "winter",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "playoffs"],
                                     "home_advantage": 1.18,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1"},
                                     "split_round": 27, "n_champ": 6, "pts_factor": 1.0,
                                     "zone_notes": {
                                         "championship": "Opening Round (Rd 1–16) and Closing Round (Rd 17–32) each split into a top-6 Championship Group and bottom-6 Relegation Group. Points reset to zero between rounds.",
                                         "relegation": "Teams finishing 11th/12th across both rounds face relegation or a playoff depending on the scenario.",
                                     },
                                     "cup_details": (
                                         "2025/26 Maltese FA Trophy winner qualifies for the UECL – QR2. "
                                         "Valletta are predicted to win the 2025/26 Maltese FA Trophy and secure a UECL – QR2 spot."
                                     ),
                                     "team_status_overrides": {"Valletta": "UECL - QR2*"}},
    "Moldovan National Division":   {"id": 4655, "country": "Moldova",     "flag": "🇲🇩", "season_type": "winter",
                                     "season_end": "17 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "wins", "gd", "gf", "less_red_cards", "less_yellow_cards"],
                                     "home_advantage": 1.03,
                                     "champ_tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "wins", "gd", "gf", "less_red_cards", "less_yellow_cards"],
                                     "european_spots": {1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR1"},
                                     "split_round": 21, "n_champ": 6, "pts_factor": 0.5, "champ_only": True,
                                     "h2h_pts_only": True, "h2h_phase1_cutoff": "2026-01-01",
                                     "zone_notes": {"relegation": "Bottom 2 teams (7th–8th) enter a 6-team Relegation Playoff alongside 4 Liga 1 clubs. Only the playoff winner earns a Super Liga spot for next season."},
                                     "cup_details": (
                                         "2025/26 Moldovan Cup winner qualifies for the UEL – QR1. "
                                         "As Sheriff Tiraspol are predicted to win the 2025/26 Moldovan Cup and secure a European place through their league position, "
                                         "the UEL – QR1 spot is projected to pass to the 2nd-placed team."
                                     ),
                                     "team_status_overrides": {"Sheriff Tiraspol": "UCL - QR1*"}},
    "Montenegrin First League":     {"id": 4656, "country": "Montenegro",  "flag": "🇲🇪", "season_type": "winter",
                                     "season_end": "4 June 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "draw"],
                                     "home_advantage": 1.47,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - QR1", 4: "UECL - QR1",
                                                        8: "Relegation - PO", 9: "Relegation - PO", 10: "Relegation"},
                                     "cup_details": ("2025/26 Montenegrin Cup winner qualifies for the UECL – QR1. "
                                                     "As Mornar Bar are predicted to win the 2025/26 Montenegrin Cup and secure a European place through their league position, "
                                                     "the UECL – QR1 spot is projected to pass to the 4th-placed team."),
                                     "team_status_overrides": {"Mornar Bar": "UECL - QR1*"}},
    "Northern Irish Premiership":   {"id": 4659, "country": "N. Ireland",  "flag": "🇬🇧", "season_type": "winter",
                                     "season_end": "26 April 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "draw"],
                                     "home_advantage": 1.20,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1",
                                                        4: "UECL - PO", 5: "UECL - PO", 6: "UECL - PO", 7: "UECL - PO",
                                                        11: "Relegation - PO", 12: "Relegation"},
                                     "cup_details": ("2025/26 Irish Cup winner qualifies for the UECL – QR2. "
                                                     "As Larne are predicted to win the 2025/26 Irish Cup and secure a European place through their league position, "
                                                     "the UECL – QR2 spot is projected to pass to the 2nd-placed team."),
                                     "team_status_overrides": {"Larne": "UECL - QR2*"},
                                     "uecl_4team_playoff": {
                                         "sf1_home": 4, "sf1_away": 1,
                                         "sf1_away_from_relg": True,
                                         "sf1_home_rank": 4, "sf1_away_rank": 7,
                                         "sf2_home": 5, "sf2_away": 6,
                                         "sf2_home_rank": 5, "sf2_away_rank": 6,
                                         "winner_spot": "UECL - QR1",
                                         "caption": ("4th-placed team hosts 7th in SF1; 5th-placed team hosts 6th in SF2 (one-legged ties). "
                                                     "Final hosted by the highest-ranked SF winner. Winner qualifies for UECL – QR1."),
                                     },
                                     "split_round": 33, "n_champ": 6, "pts_factor": 1.0},
    "Norwegian Eliteserien":        {"id": 4358, "country": "Norway",      "flag": "🇳🇴", "season_type": "summer",
                                     "season_end": "7 December 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "h2h_gf"],
                                     "home_advantage": 1.19,
                                     "european_spots": {1: "UCL - PO", 2: "UCL - QR2 (LP)", 3: "UEL - QR3", 4: "UECL - QR2", 5: "UECL - QR2",
                                                        14: "Relegation - PO", 15: "Relegation", 16: "Relegation"},
                                     "zone_notes": {"relegation - po": "14th plays two-legged play-off against 3rd of OBOS-ligaen. Away goals do not apply; higher-placed team plays second leg at home."},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Polish Ekstraklasa":           {"id": 4422, "country": "Poland",      "flag": "🇵🇱", "season_type": "winter",
                                     "season_end": "23 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "gd", "gf", "wins", "away_wins", "disciplinary", "fair_play", "draw"],
                                     "home_advantage": 1.33,
                                     "european_spots": {1: "UCL - QR2", 2: "UCL - QR2 (LP)", 3: "UECL - QR2", 4: "UECL - QR2", 5: "UEL - QR3",
                                                        16: "Relegation", 17: "Relegation", 18: "Relegation"},
                                     "cup_details": ("2025/26 Polish Cup winner qualifies for the UEL – QR3. "
                                                     "Raków Częstochowa are predicted to win the 2025/26 Polish Cup and secure a UEL – QR3 spot."),
                                     "team_status_overrides": {"Raków Częstochowa": "UEL - QR3*"},
                                     "zone_notes": {"relegation - po": "17th plays two-legged play-off against 3rd of I liga. Higher-placed team plays second leg at home."}},
    "Portuguese Primeira Liga":     {"id": 4344, "country": "Portugal",    "flag": "🇵🇹", "season_type": "winter",
                                     "season_end": "17 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "gd", "wins", "gf", "playoffs"],
                                     "home_advantage": 1.30,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - LS", 3: "UEL - LS", 4: "UEL - QR2", 5: "UECL - QR2",
                                                        16: "Relegation - PO", 17: "Relegation", 18: "Relegation"},
                                     "cup_details": ("2025/26 Taça de Portugal winner qualifies for the UEL – LS. "
                                                     "As Sporting CP are predicted to win the 2025/26 Taça de Portugal and secure a European place through their league position, "
                                                     "the UEL – LS spot is projected to pass to the 3rd-placed team."),
                                     "team_status_overrides": {"Sporting CP": "UCL - LS*"}},
    "Romanian Liga I":              {"id": 4691, "country": "Romania",     "flag": "🇷🇴", "season_type": "winter",
                                     "season_end": "24 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "playoffs"],
                                     "home_advantage": 1.24,
                                     "champ_tiebreakers": ["pts_no_round", "regular_pts", "h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "playoffs"],
                                     "european_spots": {1: "UCL - QR1", 2: "UEL - QR1", 3: "UECL - QR2",
                                                        4: "UECL - PO", 7: "UECL - PO", 8: "UECL - PO",
                                                        13: "Relegation - PO", 14: "Relegation - PO",
                                                        15: "Relegation", 16: "Relegation"},
                                     "cup_details": ("2025/26 Cupa României winner qualifies for the UEL – QR1. "
                                                     "As Universitatea Craiova are predicted to win the 2025/26 Cupa României and finish 2nd in the league, "
                                                     "there are no additional movements when it comes to European spots."),
                                     "team_status_overrides": {"Universitatea Craiova": "UEL - QR1*"},
                                     "uecl_3team_playoff": {
                                         "bye_home": 4, "bye_home_rank": 4,
                                         "sf_home": 1, "sf_home_rank": 7,
                                         "sf_away": 2, "sf_away_rank": 8,
                                         "winner_spot": "UECL - QR2",
                                         "caption": ("7th-placed team hosts 8th in one-legged semi-final; "
                                                     "4th-placed team (Championship Round) hosts SF winner in one-legged final. "
                                                     "Winner qualifies for UECL – QR2."),
                                     },
                                     "split_round": 30, "n_champ": 6, "pts_factor": 0.5, "pts_round": "up",
                                     "relg_tiebreakers": ["pts_no_round", "regular_pts", "h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "playoffs"],
                                     "zone_notes": {"relegation": "Bottom two of the Play-out are directly relegated. 13th and 14th play two-legged play-offs against Liga II teams."}},
    "Russian Premier League":       {"id": 4355, "country": "Russia",      "flag": "🇷🇺", "season_type": "winter",
                                     "tiebreakers": ["h2h_pts", "h2h_wins", "h2h_gd", "h2h_gf", "wins", "gd", "gf", "away_wins", "away_gf", "disciplinary", "playoffs"],
                                     "home_advantage": 1.38,
                                     "european_spots": {13: "Relegation - PO", 14: "Relegation - PO",
                                                        15: "Relegation", 16: "Relegation"},
                                     "cup_details": ("2025/26 Russian Cup Final: Dinamo Moskva vs Krasnodar. "
                                                     "Due to Russia's suspension, winner is not awarded a European spot.")},
    "San Marino Campionato":        {"id": 4667, "country": "San Marino",  "flag": "🇸🇲", "season_type": "winter",
                                     "season_end": "17 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf"],
                                     "home_advantage": 0.97,
                                     "european_spots": {1: "UCL - QR1", 4: "UECL - QR1",
                                                        2: "UECL - PO", 3: "UECL - PO", 5: "UECL - PO",
                                                        6: "UECL - PO", 7: "UECL - PO", 8: "UECL - PO",
                                                        9: "UECL - PO", 10: "UECL - PO", 11: "UECL - PO", 12: "UECL - PO"},
                                     "cup_details": ("2025/26 Coppa Titano winner qualifies for the UECL – QR1. "
                                                     "La Fiorita are predicted to win the 2025/26 Coppa Titano and secure a UECL – QR1 spot."),
                                     "team_status_overrides": {"La Fiorita": "UECL - QR1*"},
                                     "uecl_8team_playoff": {
                                         "winner_spot": "UECL - QR1",
                                         "caption": ("R1 (one-legged): 9th vs 12th, 10th vs 11th. "
                                                     "QF (one-legged): 2nd vs R1 winner, 6th vs 7th, 3rd vs R1 winner, 5th vs 8th. "
                                                     "SF and Final one-legged; higher-ranked team hosts each tie. "
                                                     "Winner qualifies for UECL – QR1."),
                                     }},
    "Scottish Premiership":         {"id": 4330, "country": "Scotland",    "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "season_type": "winter",
                                     "season_end": "26 May 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "playoffs"],
                                     "home_advantage": 1.35,
                                     "european_spots": {1: "UCL - PO", 2: "UCL - QR2 (LP)", 3: "UEL - QR3",
                                                        4: "UECL - QR2", 5: "UECL - QR2",
                                                        11: "Relegation - PO", 12: "Relegation"},
                                     "cup_details": ("2025/26 Scottish Cup winner qualifies for the UEL – QR3. "
                                                     "As Celtic are predicted to win the 2025/26 Scottish Cup and secure a European place through their league position, "
                                                     "the UEL – QR3 spot is projected to pass to the 3rd-placed team."),
                                     "team_status_overrides": {"Celtic": "UCL - PO*"},
                                     "split_round": 33, "n_champ": 6, "pts_factor": 1.0,
                                     "zone_notes": {"relegation": "11th plays two-legged play-off against 2nd of the Championship. Higher-placed team plays second leg at home. 12th is directly relegated."}},
    "Serbian Super Liga":           {"id": 4671, "country": "Serbia",      "flag": "🇷🇸", "season_type": "winter",
                                     "season_end": "25 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "fair_play", "draw"],
                                     "home_advantage": 1.28,
                                     "european_spots": {1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
                                                        13: "Relegation - PO", 14: "Relegation - PO",
                                                        15: "Relegation", 16: "Relegation"},
                                     "cup_details": ("2025/26 Serbian Cup winner qualifies for the UEL – QR1. "
                                                     "As Crvena zvezda are predicted to win the 2025/26 Serbian Cup and secure a European place through their league position, "
                                                     "the UEL – QR1 spot is projected to pass to the 2nd-placed team."),
                                     "team_status_overrides": {"Crvena zvezda": "UCL - QR2*"},
                                     "split_round": 30, "n_champ": 8, "pts_factor": 0.5},
    "Slovak First League":          {"id": 4672, "country": "Slovakia",    "flag": "🇸🇰", "season_type": "winter",
                                     "season_end": "23 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "fair_play", "draw"],
                                     "home_advantage": 1.07,
                                     "champ_tiebreakers": ["regular_pts", "h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "fair_play", "draw"],
                                     "relg_tiebreakers":  ["regular_pts", "h2h_pts", "h2h_gd", "h2h_gf", "h2h_away_gf", "gd", "gf", "fair_play", "draw"],
                                     "european_spots": {1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
                                                        11: "Relegation - PO", 12: "Relegation"},
                                     "cup_details": ("2025/26 Slovak Cup winner Žilina qualifies directly for the UEL – QR1."),
                                     "team_status_overrides": {"Žilina": "UEL - QR1*"},
                                     "split_round": 22, "n_champ": 6, "pts_factor": 1.0,
                                     "zone_notes": {"relegation": "11th plays two-legged play-off against 2nd of Slovak 2. liga. 12th is directly relegated."}},
    "Slovenian 1. SNL":             {"id": 4692, "country": "Slovenia",    "flag": "🇸🇮", "season_type": "winter",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf"],
                                     "home_advantage": 1.20,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR2",
                                                        9: "Relegation - PO", 10: "Relegation"},
                                     "cup_details": ("2025/26 Slovenian Football Cup winner Bravo qualifies for the UEL – QR1."),
                                     "team_status_overrides": {"Bravo": "UEL - QR1*"}},
    "Swedish Allsvenskan":          {"id": 4347, "country": "Sweden",      "flag": "🇸🇪", "season_type": "summer",
                                     "season_end": "29 November 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_pts", "h2h_gd", "h2h_away_gf", "playoffs"],
                                     "home_advantage": 1.02,
                                     "european_spots": {1: "UCL - QR2", 2: "UEL - QR1", 3: "UECL - QR2", 4: "UECL - QR2",
                                                        14: "Relegation - PO", 15: "Relegation", 16: "Relegation"},
                                     "zone_notes": {"relegation - po": "14th plays two-legged play-off against 3rd of Superettan. Higher-placed club plays second leg at home."},
                                     "cup_details": "Cup winner will enter 2027/28 European competitions."},
    "Swiss Super League":           {"id": 4675, "country": "Switzerland", "flag": "🇨🇭", "season_type": "winter",
                                     "season_end": "23 May 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_gd", "h2h_gf", "away_gf", "draw"],
                                     "home_advantage": 1.19,
                                     "european_spots": {1: "UCL - QR2", 2: "UEL - QR2", 3: "UECL - QR2", 4: "UECL - QR2",
                                                        11: "Relegation - PO", 12: "Relegation"},
                                     "cup_details": ("2025/26 Swiss Cup winner St. Gallen qualifies for the UEL – QR2. "
                                                     "As St. Gallen are predicted to finish 2nd in the league, "
                                                     "no additional movement of European spots is required."),
                                     "team_status_overrides": {"St. Gallen": "UEL - QR2*"},
                                     "split_round": 33, "n_champ": 6, "pts_factor": 1.0,
                                     "zone_notes": {"relegation": "11th plays two-legged play-off against 2nd of Challenge League. 12th is directly relegated."}},
    "Turkish Super Lig":            {"id": 4339, "country": "Turkey",      "flag": "🇹🇷", "season_type": "winter",
                                     "season_end": "17 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "playoffs"],
                                     "home_advantage": 1.10,
                                     "european_spots": {1: "UCL - LS", 2: "UCL - QR3 (LP)", 3: "UEL - PO", 4: "UEL - QR2", 5: "UECL - QR2",
                                                        16: "Relegation", 17: "Relegation", 18: "Relegation"},
                                     "cup_details": ("2025/26 Turkish Cup winner Galatasaray qualifies for the UEL – PO. "
                                                     "As Galatasaray are predicted to win the 2025/26 Turkish Cup and secure a European place through their league position, "
                                                     "the UEL – PO spot is projected to pass to the 3rd-placed team."),
                                     "team_status_overrides": {"Galatasaray": "UCL - LS*"}},
    "Ukrainian Premier League":     {"id": 4354, "country": "Ukraine",     "flag": "🇺🇦", "season_type": "winter",
                                     "season_end": "29 May 2026",
                                     "tiebreakers": ["h2h_pts", "h2h_gd", "h2h_gf", "gd", "gf", "draw"],
                                     "home_advantage": 1.20,
                                     "european_spots": {1: "UCL - PO", 2: "UECL - QR2", 3: "UECL - QR2", 4: "UEL - QR1",
                                                        13: "Relegation - PO", 14: "Relegation - PO",
                                                        15: "Relegation", 16: "Relegation"},
                                     "cup_details": ("2025/26 Ukrainian Cup winner Dynamo Kyiv qualifies for the UEL – QR1."),
                                     "team_status_overrides": {"Dynamo Kyiv": "UEL - QR1*"}},
    "Welsh Premier League":         {"id": 4472, "country": "Wales",       "flag": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "season_type": "winter",
                                     "season_end": "3 May 2026",
                                     "tiebreakers": ["gd", "gf", "h2h_gd", "h2h_gf", "h2h_away_gf", "wins", "away_wins", "playoffs"],
                                     "home_advantage": 1.06,
                                     "european_spots": {1: "UCL - QR1", 2: "UECL - QR1", 3: "UECL - PO",
                                                        4: "UECL - PO", 5: "UECL - PO", 7: "UECL - PO", 8: "UECL - PO"},
                                     "cup_details": ("2025/26 Welsh Cup winner Caernarfon Town qualifies for the UECL – QR1."),
                                     "team_status_overrides": {"Caernarfon Town": "UECL - QR1*"},
                                     "uecl_5team_playoff": {
                                         "final_host": 3, "final_host_rank": 3,
                                         "qf1_home": 4, "qf1_home_rank": 4,
                                         "qf1_away": 2, "qf1_away_rank": 8,
                                         "qf2_home": 5, "qf2_home_rank": 5,
                                         "qf2_away": 1, "qf2_away_rank": 7,
                                         "winner_spot": "UECL - QR1",
                                         "caption": ("QF: 4th vs 8th, 5th vs 7th (one-legged, higher-ranked hosts). "
                                                      "SF: one-legged, higher-ranked hosts. "
                                                      "Final: 3rd hosts SF winner (one-legged). Winner qualifies for UECL – QR1."),
                                     },
                                     "split_round": 22, "n_champ": 6, "pts_factor": 1.0},
}


def get_current_season(season_type: str) -> str:
    """
    Return the TheSportsDB season string currently active.

    Winter leagues (Aug–May):  Jan–Jun → "{year-1}-{year}"  | Jul–Dec → "{year}-{year+1}"
    Summer leagues (Apr–Nov):  Jan–Mar → str(year-1)        | Apr–Dec → str(year)
    """
    from datetime import datetime
    now = datetime.now()
    year = now.year
    if season_type == "summer":
        return str(year)
    return f"{year - 1}-{year}" if now.month < 7 else f"{year}-{year + 1}"


# ---------------------------------------------------------------------------
# UEFA European Competitions (2025-2026)
# IDs sourced from TheSportsDB — verify at thesportsdb.com if data is missing.
#   n_direct  = teams advancing directly to R16 from league phase
#   n_playoff = additional teams entering knockout play-offs
# ---------------------------------------------------------------------------
EUROPEAN_COMPETITIONS = {
    "Champions League": {
        "id": 4480, "flag": "🏆",
        "n_direct": 8, "n_playoff": 16,
        "league_phase_rounds": 8,
        "has_league_phase": True,
        "qualifying_rounds": {400, 1128, 128, 125},
    },
    "Europa League": {
        "id": 4481, "flag": "🥈",
        "n_direct": 8, "n_playoff": 16,
        "league_phase_rounds": 8,
        "has_league_phase": True,
        "qualifying_rounds": {400, 1128, 128, 125},
    },
    "Conference League": {
        "id": 5071, "flag": "🏅",
        "n_direct": 8, "n_playoff": 16,
        "league_phase_rounds": 8,
        "has_league_phase": True,
        "qualifying_rounds": {400, 1128, 128, 125},
    },
}

# Default API key — the public demo key (limited to 5 standings rows / 15 fixtures).
# Subscribe at thesportsdb.com (Single Developer $9/mo) for full data.
# Set env var THESPORTSDB_API_KEY or enter in the sidebar.
DEFAULT_API_KEY = "3"

# Simulation defaults
DEFAULT_N_SIMULATIONS = 10_000
DEFAULT_HOME_ADVANTAGE = 1.20
DEFAULT_BASE_GOALS = 1.35

# Cache TTL in seconds
CACHE_TTL_STANDINGS = 7_200     # 2 hours
CACHE_TTL_FIXTURES = 3_600      # 1 hour
CACHE_TTL_META = 86_400         # 24 hours
