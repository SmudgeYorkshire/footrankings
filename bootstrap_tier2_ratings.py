"""
Seeds ratings/{tsdb_id}.csv for every LEAGUES_TIER2 league from the global
Opta scrape (opta_power_rankings.csv, ~14,200 clubs worldwide -- already
proven in build_club_power_rankings.py to reach far beyond just the 54
tracked top-flight rosters) instead of leaving it to ratings_manager's
crude goal-difference fallback, which the project plan's research
confirmed would otherwise produce a flat, undifferentiated rating for
every team until several matchdays have been played.

For each league: fetch its real roster via ApiFootballClient.get_standings,
then resolve each team name against the global scrape using EXACT and
normalized (diacritics/club-suffix-stripped) matching only -- deliberately
NOT the fuzzy token-subset tier club_rating_calibration.py also uses.
That tier is only safe when matching INTO a small, scoped pool (one
league's own ~20-team ratings_df); here the match target is the full
~14,200-club GLOBAL list, which is exactly the large/ambiguous pool that
already produced one false positive this project ("Villa" stealing Aston
Villa's rating in build_club_power_rankings.py). Tried here first without
this restriction, it immediately reproduced the same failure mode on a
real run: "Bristol City" fuzzy-matched some unrelated club via the single
generic token "City", and "Sheffield Utd" similarly via "Sheffield",
both landing implausibly low ratings for well-known Championship sides.
Exact/normalized-only trades a little coverage for not being confidently
wrong about a famous club.

Unmatched teams fall back to ratings_manager.DEFAULT_OPTA, the same
constant the existing no-CSV fallback already uses, so a team genuinely
missing from Opta's list isn't rated zero or dropped.

Usage: py bootstrap_tier2_ratings.py [--league "England - Championship"]
(omit --league to bootstrap every LEAGUES_TIER2 entry)
"""

import argparse
import csv
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from config import LEAGUES_TIER2
from api_football_fetcher import ApiFootballClient
from ratings_manager import RATINGS_DIR, DEFAULT_OPTA
from update_ratings_from_opta import _normalize
from _split_season import ensure_full_roster

GLOBAL_RANKINGS_PATH = "opta_power_rankings.csv"

# Exact/normalized matching deliberately can't bridge a club being stored
# under a shorter/colloquial name in the global scrape than our roster's
# full "Club Town" name (e.g. our "Famos Vojkovići" vs Opta's "Vojkovići").
# Confirmed via Opta's own published power-ranking list for Bosnian clubs
# (user-supplied screenshots, 2026-10-02) that these are the same club.
# Values are the RATING itself, not just an alias name to re-look-up --
# several of these short names are non-unique in the global list (e.g.
# "Sutjeska" has two entries, 66.7 and 51.7; "Rudar" has seven), and
# _build_lookups' exact dict keeps only the highest-rated duplicate, which
# would silently pick the wrong one. Each value below is the specific
# rating confirmed to match this club from Opta's own Bosnia list, with
# ambiguous siblings noted for context.
MANUAL_RATINGS: dict[str, dict[str, float]] = {
    "Bosnia - 1st League - RS": {
        "Famos Vojkovići": 54.5,
        "Velež Nevesinje": 52.4,
        "Kozara Gradiška": 55.4,
        "Sutjeska Foča": 51.7,  # not the 66.7 entry (likely Sutjeska Nikšić, Montenegro)
        "FK Majevica Lopare": 56.2,
        "Drina Zvornik": 57.6,
        "Rudar Prijedor": 55.8,  # not Rudar Kakanj (52.8, separate FBiH club) or the other 5 "Rudar" entries worldwide
    },
    "Bosnia - 1st League - FBiH": {
        "Stupčanica Olovo": 60.2,
        "GOŠK Gabela": 59.3,
        "Sloboda Tuzla": 59.4,  # Opta stores it as "Sloboda T"
        "Igman Konjic": 56.7,
        "Jedinstvo Bihać": 56.6,  # Opta stores it as "Jedinstvo B"
        "Bratstvo Gračanica": 56.2,
        "Zvijezda Gradačac": 55.0,  # Opta stores it as "Zvijezda G"
        "Budućnost Banovići": 55.2,  # not the 65.9 entry (likely Budućnost Podgorica, Montenegro)
        "Radnik Hadžići": 55.4,  # Opta stores it as "Hadžići"; not the "Radnik" entries (66-72, a different, higher-level club)
    },
    # 13 of 17 -- the other 4 (1. FC Nürnberg, 1. FC Kaiserslautern, Karlsruher
    # SC, Eintracht Braunschweig) have no senior-team entry in the scrape at
    # all, only reserve sides (e.g. "Nürnberg II") -- a genuine coverage gap,
    # not a name mismatch, so left at the default.
    "Germany - 2. Bundesliga": {
        "Hertha BSC": 81.1,
        "1. FC Heidenheim": 79.0,
        "VfL Wolfsburg": 79.5,
        "1. FC Magdeburg": 77.8,
        "Energie Cottbus": 76.9,
        "VfL Bochum": 77.8,
        "Hannover 96": 80.0,
        "VfL Osnabrück": 76.3,
        "SpVgg Greuther Fürth": 75.5,
        "Arminia Bielefeld": 76.7,
        "Holstein Kiel": 76.6,
        "Dynamo Dresden": 76.0,
        "SV Darmstadt 98": 76.4,
    },
    # 17 of 19 -- "Swansea University" skipped (the scrape's only plain
    # "Swansea" entry at 83.1 is clearly Swansea City, the English Championship
    # club, not this amateur university side; "Pure Swansea" at 46.4 is a
    # plausible but unconfirmed guess). "Bangor City 1876 FC" skipped (two
    # unresolvable plain "Bangor" entries, 54.5 and 44.3, could be this club
    # or Bangor FC Northern Ireland).
    "Wales - FAW Championship": {
        "Aberystwyth Town": 46.6,
        "Pontypridd Town": 44.7,
        "Carmarthen Town": 45.3,
        "Caerau (Ely)": 47.8,
        "Trethomas Bluebirds": 42.9,
        "Ynyshir Albions": 42.3,
        "Caerphilly Athletic": 41.1,
        "Cardiff Draconians": 42.7,
        "Pontardawe Town": 42.5,
        "Llantwit Major": 42.2,
        "llanelli AFC": 40.6,  # Opta stores it as "Llanelli Town"
        "Brickfield Rangers": 47.9,  # Opta stores it as "Brickfield R."
        "Bala Town": 47.1,  # not "Bala Azul" (59.8, unrelated club elsewhere)
        "Buckley Town": 42.5,
        "Rhyl": 43.6,  # Opta stores it as "Y Rhyl 1879"
        "Holyhead Hotspur": 41.9,
        "Gresford Athletic": 40.1,
    },
    # 6 Championship clubs resolved (Chindia Targoviste from the original
    # "Chindia" lookup, plus 5 more below); the remaining 9 (Popești-Leordeni,
    # Cetatea Suceava, Gloria Bistriţa, ASA Targu Mures, Bihor Oradea, CSM Satu
    # Mare, CS Dinamo București) have no plausible scrape entry found.
    "Romania - Liga II": {
        "FC Politehnica Timisoara": 60.4,
        "CSM Reşiţa": 64.5,
        "Chindia Targoviste": 65.4,
        "CS Afumati": 62.4,  # Opta stores it as "Afumaţi"
        "CSM Ramnicu Valcea": 61.3,  # Opta stores it as "Râmnicu Vâlcea"
        "Viitorul Şelimbăr": 61.1,  # Opta stores it as "1599 Şelimbăr"
        "CSA Steaua Bucureşti": 63.5,  # Opta stores it as "CSA Steaua"; not "Steaua Nord" (33.0, a separate, much weaker club)
        "Unirea Slobozia": 63.0,  # Opta stores it as "Slobozia"
    },
    "Greece - Super League 2": {
        "Ellas Syros": 62.4,  # Opta stores it as "Syros"
        "Nestos Chrisoupolis": 60.3,  # Opta stores it as "Nestos"
    },
    # 2 of 12 -- the other 10 have only a reserve-team entry in the scrape
    # (e.g. "Lechia Gdańsk" only appears as nothing at all, "Ruch Chorzów"
    # only as "Ruch Chorzów II") or no entry at all.
    "Poland - I Liga": {
        "Miedz Legnica": 70.3,  # Opta stores it as "Miedź"
        "Chrobry Głogów": 69.8,  # Opta stores it as "Chrobry"
    },
    # 9 of 12 -- Turkish lower-tier clubs are consistently stored without
    # the "-spor" suffix. "Manisa F.K." and "Vanspor FK" skipped (each has
    # two plain, similarly-rated scrape entries with no way to tell them
    # apart); "Fatih Karagümrük" not found at all.
    "Turkey - 1. Lig": {
        "Mardin 1969": 67.2,  # Opta stores it as "Mardin"
        "Kayserispor": 72.9,  # Opta stores it as "Kayseri"
        "Batman Petrolspor": 68.4,  # Opta stores it as "Batman"
        "Muğlaspor": 66.8,  # Opta stores it as "Muğla"
        "Bandırmaspor": 68.8,  # Opta stores it as "Bandırma"
        "Pendikspor": 68.5,  # Opta stores it as "Pendik"
        "Sivasspor": 67.5,  # Opta stores it as "Sivas"
        "Ümraniyespor": 65.9,  # Opta stores it as "Ümraniye"
        "Esenler Erokspor": 69.6,  # Opta stores it as "Erokspor"
    },
    "Austria - 2. Liga": {
        "SKU Amstetten": 68.0,  # Opta stores it as "Amstetten"
        "Schwarz-Weiß Bregenz": 62.9,  # Opta stores it as "Bregenz SW"
        "SKN ST. Polten": 69.5,  # Opta stores it as "St. Pölten"
    },
    "Belgium - Challenger Pro League": {
        "Excelsior Virton": 69.5,  # Opta stores it as "Virton"
        "Lokeren-Temse": 70.8,  # Opta stores it as "Lokeren"
        "K. Lierse S.K.": 68.5,  # Opta stores it as "Lierse"
        "Seraing United": 67.6,  # Opta stores it as "Seraing"
        "Sporting Hasselt": 68.5,  # moderate confidence: the scrape's other plain "Hasselt" entry (44.0) looks like an unrelated amateur side, not a serious alternative
    },
    # 5 of 10 -- "Dinamo Zagreb U21" is itself a reserve side (correctly
    # left at the default, there's no meaningful separate rating for it).
    "Croatia - First NL": {
        "Croatia Zmijavci": 66.1,  # Opta stores it as "Zmijavci"
        "Segesta Sisak": 65.7,  # Opta stores it as "Segesta"
        "Dubrava Zagreb": 66.1,  # Opta stores it as "Dubrava"
        "Karlovac 1919": 64.4,  # Opta stores it as "Karlovac"
        "Orijent 1919": 66.2,  # Opta stores it as "Orijent"
    },
    "Israel - Liga Leumit": {
        "Hapoel Rishon LeZion": 66.4,  # Opta stores it as "Rishon LeZion"
        "Hapoel Ra'anana": 67.0,  # Opta stores it as "H Ra'anana"
        "Hapoel Kfar Shalem": 67.3,  # Opta stores it as "H Kfar Shalem"
        "Maccabi Bnei Raina": 66.9,  # Opta stores it as "Bnei Raina"
        "Maccabi Kiryat Gat": 63.6,  # Opta stores it as "M Kiryat Gat"
        "Maccabi Herzliya": 66.5,  # Opta stores it as "M Herzliya"; not "H Herzliya" (59.3, that's Hapoel Herzliya)
        "Maccabi Ahi Nazareth": 62.4,  # Opta stores it as "M Ahi Nazareth"
        "Hapoel Kfar Saba": 64.4,  # Opta stores it as "H Kfar Saba"; not the plain "Kfar Saba" (57.7) or "B Kfar Saba" (48.5) entries
        "Hapoel Acre": 61.0,  # Opta stores it as "H Acre"
    },
    "Malta - Challenge League": {
        "Tarxien Rainbows": 53.5,  # Opta stores it as "Tarxien"
        "Fgura United": 52.3,  # Opta stores it as "Fgura"
        "Vittoriosa Stars": 47.9,  # Opta stores it as "Vittoriosa"
        "Swieqi United": 56.3,  # Opta stores it as "Swieqi Utd"
        "Naxxar Lions": 53.3,  # Opta stores it as "Naxxar"
        "Mgarr United": 50.3,  # Opta stores it as "Mgarr Utd"
        "Gudja United": 48.5,  # Opta stores it as "Gudja Utd"
        "Zebbug Rangers": 45.1,  # Opta stores it as "Zebbug"; not "Birzebbuga" (61.1, a different club despite the substring overlap)
    },
    "Netherlands - Eerste Divisie": {
        "Almere City FC": 71.0,  # Opta stores it as "Almere"
        "VVV Venlo": 67.3,  # Opta stores it as "VVV"
        "Helmond Sport": 64.2,  # Opta stores it as "Helmond"
    },
    "Kazakhstan - 1. Division": {
        "Akademiya Ontustik": 54.4,  # Opta stores it as "Ontustik"
        "Yelimay Semey 2": 47.4,  # Opta stores it as "Yelimay II" -- the plain "Yelimay" (72.1) is the senior Premier League club, not this reserve side
    },
    "Russia - First League": {
        "Rotor Volgograd": 69.9,  # Opta stores it as "Rotor"
        "Shinnik Yaroslavl": 69.1,  # Opta stores it as "Shinnik"
        "Enisey": 67.9,  # Opta stores it as "Yenisey" (alternate transliteration)
    },
    "Bulgaria - Second League": {
        "Rilski Sportist": 56.0,  # Opta stores it as "Rilski"
        "Yantra 2019": 59.9,  # Opta stores it as "Yantra"
        "Etar Veliko Tarnovo": 56.9,  # Opta stores it as "Etar VT"
        "Pirin Blagoevgrad": 51.5,  # Opta stores it as plain "Pirin"; not "Pirin GD" (Gotse Delchev) or "Pirin Razlog", different clubs
    },
    "Northern Ireland - Championship": {
        "Newington Youth": 49.6,  # Opta stores it as "Newington"
        "Annagh United": 51.4,  # Opta stores it as "Annagh Utd"
        "Queen's University": 49.3,  # Opta stores it as "Queen's Uni"
        "Warrenpoint Town": 45.1,  # Opta stores it as "Warrenpoint"
        "Ballinamallard United": 44.8,  # Opta stores it as "Ballinamallard"
        "Strabane Athletic": 43.1,  # Opta stores it as "Strabane"
    },
    "Sweden - Superettan": {
        "IFK Norrkoping": 73.5,  # Opta stores it as "Norrköping"
        "Falkenbergs FF": 70.5,  # Opta stores it as "Falkenberg"
        "Varbergs BoIS FC": 69.8,  # Opta stores it as "Varberg"; not "Varbergs GIF" (47.6), a separate club
        "Landskrona BoIS": 69.2,  # Opta stores it as "Landskrona"
        "Osters IF": 67.8,  # Opta stores it as "Öster"; not "Östersund"/"Östersunds" (a different city/club)
        "IFK Varnamo": 66.8,  # Opta stores it as "Värnamo"
        "GIF Sundsvall": 61.8,  # Opta stores it as "Sundsvall"
    },
    "Armenia - First League": {
        "Bentonit Ijevan": 51.7,  # Opta stores it as "Bentonit"
        "Mika": 47.6,  # Opta stores it as "Mika Yerevan"
        "Sardarapat 2": 46.8,  # Opta stores it as "Sardarapat II"; not the plain "Sardarapat" (65.2), that's the senior club this is the reserve side of
    },
    "Cyprus - 2. Division": {
        "Iraklis Yerolakkou": 60.8,  # Opta stores it as "Yerolakkou"
    },
    "Hungary - NB II": {
        "Mezokovesd-zsory": 67.4,  # Opta stores it as "Mezőkövesd"
        "Szeged 2011": 65.3,  # Opta stores it as "Szeged-Csanád"
        "Csakvar": 63.4,  # Opta stores it as "Csákvári"
    },
    "Serbia - Prva Liga": {
        "Jedinstvo Ub": 58.9,  # Opta stores it as plain "Ub"
    },
    "Albania - 1st Division": {
        "Besa Kavajë": 61.6,  # Opta stores it as plain "Besa"; Kosovo's "FC Besa Peja" has no scrape coverage, no ambiguity
        "Korabi Peshkopi": 57.8,  # Opta stores it as plain "Korabi"
        "Iliria Fushë-Krujë": 58.8,  # Opta stores it as plain "Iliria"; not "Nacka Iliria" (Swedish club)
        "Kastrioti Krujë": 57.3,  # Opta stores it as plain "Kastrioti"
        "Sopoti Librazhd": 57.1,  # Opta stores it as plain "Sopoti"
        "Besëlidhja Lezhë": 56.8,  # Opta stores it as plain "Besëlidhja"
    },
    # Dukla Praha/Arsenal Česká Lípa/Vysočina Jihlava/Hanácká all skipped --
    # either only a reserve-team ("II") entry exists, or the only plain-name
    # match ("Dukla") is ambiguous with other Dukla-named clubs (Banská
    # Bystrica etc.) elsewhere in the former Eastern Bloc.
    "Czech Republic - FNL": {
        "Viktoria Žižkov": 64.9,  # Opta stores it as plain "Žižkov"
        "Ústí nad Labem": 70.4,  # Opta stores it as plain "Ústí"; not "Ústí Orlicí" (different club) or "...II" (reserve)
    },
    "Latvia - 1. Liga": {
        "Metta / LU": 56.6,  # Opta stores it as plain "Metta"
        "Valmiera / BSS": 52.0,  # Opta stores it as plain "Valmiera"
        "Leevon / PPK": 51.3,  # Opta stores it as plain "Leevon"
        "Super Nova 2": 44.5,  # Opta stores it as "Super Nova II"; plain "Super Nova" (63.4) is already the top-flight FK Super Nova (ratings/4650.csv)
    },
    # Univer Comrat/Spartanii Selemet/Oguzsport/FC National Ialoveni/Victoria
    # Bardar all skipped -- no scrape coverage found under any name variant.
    "Moldova - Liga 1": {
        "Vulturii Cutezători": 50.4,  # Opta stores it as plain "Vulturii"
    },
    "Norway - 1. Division": {
        "Stromsgodset": 75.4,  # Opta stores it as "Strømsgodset"
        "Stabaek": 72.5,  # Opta stores it as "Stabæk"
        "ODD Ballklubb": 70.7,  # Opta stores it as plain "Odd"
        "hodd": 68.6,  # Opta stores it as "Hødd"
        "Strommen": 66.8,  # Opta stores it as "Strømmen"
        "Sandnes ULF": 67.1,  # Opta stores it as plain "Sandnes"; not "Sandnes Ulf II" (reserve)
    },
    # Sporting CP B/Benfica B/FC Porto B all skipped -- no "Sporting CP
    # II"/"Benfica II"/"FC Porto II"-style entry found (other "Sporting B"/
    # "Porto B" hits in the scrape are unrelated clubs, e.g. Sporting Braga's
    # reserve side, not Sporting CP's).
    "Portugal - Segunda Liga": {
        "Lusitânia Lourosa": 74.2,  # Opta stores it as plain "Lourosa"
        "União de Leiria": 75.5,  # Opta stores it as "União Leiria"
        "Felgueiras 1932": 73.5,  # Opta stores it as plain "Felgueiras"
    },
    # Inter Bratislava/Tatran Prešov/Liptovský Mikuláš/Lokomotíva Zvolen all
    # skipped -- either no scrape coverage, or (Tatran) two equally generic,
    # unlabeled "Tatran" rows with no way to tell which (if either) is Prešov.
    "Slovakia - 2. liga": {
        "Považská Bystrica": 61.1,  # Opta stores it as plain "Považská"
        "Baník Lehota p.Vtáčnikom": 58.7,  # Opta stores it as "Baník Lehota"
    },
    # Viktoriya Mykolaivka/Ahrobiznes Volochysk/Lokomotiv Kyiv all skipped --
    # no scrape coverage. "Metal Kharkiv" skipped too -- the historic
    # "Metalist Kharkiv" club (scraped as "FK Metalist") is a different,
    # unrelated club from this smaller "FC Metal Kharkiv" (founded 2015);
    # "Yarud Mariupol'" skipped since the only close name, "FSC Mariupol",
    # isn't actually the same club.
    "Ukraine - Persha Liga": {
        "Probiy Horodenka": 53.5,  # Opta stores it as plain "Probiy"
    },
    # Cork City skipped -- no scrape coverage found.
    "Ireland - First Division": {
        "Bray Wanderers": 58.5,  # Opta stores it as plain "Bray"
        "Longford Town": 56.2,  # Opta stores it as plain "Longford"
        "Cobh Ramblers": 57.6,  # Opta stores it as plain "Cobh"; not "Cobh Wanderers" (40.8), a different, lower-profile club
        "Athlone Town": 55.6,  # Opta stores it as plain "Athlone"
    },
    # Stade Lausanne-Ouchy/FC WIL 1900/Stade Nyonnais all skipped -- no
    # scrape coverage found under any name variant.
    "Switzerland - Challenge League": {
        "Yverdon Sport": 72.5,  # Opta stores it as plain "Yverdon"; not "Yverdon Sport II" (reserve)
        "Neuchatel Xamax FC": 67.8,  # Opta stores it as plain "Xamax"
    },
    # AB Copenhagen skipped -- no scrape coverage found.
    "Denmark - 1. Division": {
        "Aalborg": 66.3,  # Opta stores it as "AaB" (standard club abbreviation)
        "Vendsyssel FF": 65.3,  # Opta stores it as plain "Vendsyssel"
        "HB Koge": 63.9,  # Opta stores it as "HB Køge"
    },
    # Sheffield Utd skipped -- the only "Sheffield" scrape row (31.1) is far
    # too low to plausibly be a Championship club; it's some other, unrelated
    # Sheffield-named side, not a safe match.
    "England - Championship": {
        "Stoke City": 79.4,  # Opta stores it as plain "Stoke"
        "Bristol City": 80.5,  # Opta stores it as "Bristol C"; not "Bristol R" (Rovers, a different club)
    },
    # Throttur Reykjavik/HK Kopavogur/IR Reykjavik all skipped -- no scrape
    # coverage found under any name variant.
    "Iceland - 1. Deild": {},
    "Italy - Serie B": {
        "Padova": 73.9,  # Opta stores it as "Calcio Padova"
        "Hellas Verona": 76.8,  # Opta stores it as plain "Verona"; not "Virtus Verona" (58.0), a different club
        "Vicenza Virtus": 74.1,  # Opta stores it as plain "Vicenza"
    },
    # Be1 NFA skipped despite a plausible "Be1" (55.7) match -- too
    # name-truncated to be confident; everything else resolved cleanly.
    "Lithuania - 1 Lyga": {
        "Neptūną Klaipėda": 57.4,  # Opta stores it as plain "Neptūną"
        "Transinvest 2": 48.7,  # Opta stores it as "TransINVEST Vilnius II"; plain "TransINVEST" (69.1) is the senior club
    },
    # Tabor Sežana/Slovan Ljubljana skipped -- no scrape coverage found.
    # "Dren Vrhnika" skipped too -- the only close name, "Drenica", is an
    # unrelated Kosovar club, not the same team.
    "Slovenia - 2. SNL": {},
    # Tampere United skipped -- only "Tampere United II" (reserve) has scrape
    # coverage, no senior entry to match against. "KPV-j" skipped too --
    # ambiguous whether it's the senior club or an academy side, and the
    # scrape's "KPV"/"KPV Akatemia" split doesn't resolve that cleanly.
    "Finland - Ykkönen": {},
    "France - Ligue 2": {
        "RED Star FC 93": 77.3,  # Opta stores it as plain "Red Star"; a second unlabeled "Red Star" row (45.3) exists but is far too low to be this club
        "Clermont Foot": 72.9,  # Opta stores it as plain "Clermont"
    },
    "Georgia - Erovnuli Liga 2": {
        "Merani Martvili": 55.0,  # Opta stores it as plain "Merani"; not "Merani Tbilisi" (43.5), a different club
        "Aragvi Dusheti": 54.8,  # Opta stores it as plain "Aragvi"
    },
    # Mladost Lješkopolje/Mogren both skipped -- no scrape coverage found.
    "Montenegro - Second League": {},
    # Sporting Gijon skipped -- no scrape coverage found.
    "Spain - Segunda División": {
        "AD Ceuta FC": 76.1,  # Opta stores it as plain "Ceuta"; not "Ceuta II" (reserve) or "Sporting Ceuta" (54.9), a different club
    },
    "Azerbaijan - Birinci Dasta": {},  # "Cəbrayıl" skipped -- no scrape coverage found under this or the "Jabrayil" transliteration.
    "Estonia - Esiliiga A": {},  # "Tartu Welco" skipped -- no scrape coverage found.
    "Scotland - Championship": {
        "Inverness CT": 62.8,  # Opta stores it as plain "Inverness"
    },
    # FC Energetik-Bgu Minsk/Shakhter Soligorsk/Osipovichy all skipped -- no
    # scrape coverage found under any name variant.
    "Belarus - 1. Division": {
        "Niva": 58.5,  # Opta stores it as "Niva Dolbizno" (full location-suffixed name)
        "Molodechno-DYuSSh 4": 55.4,  # Opta stores it as plain "Molodechno"
    },
    # Akademija Pandev/Makedonija GjP/Detonit Plachkovica/Kozuv Gevgelija all
    # skipped -- no scrape coverage found under any name variant.
    "Macedonia - Second League": {
        "Shkupi 1927": 52.0,  # Opta stores it as plain "Shkupi"
    },
}


def _build_lookups(global_df: pd.DataFrame) -> tuple[dict[str, tuple[float, str]], dict[str, tuple[float, str]]]:
    """{team: (rating, team)} exact + {normalized: (rating, team)}, built
    once rather than re-scanning/re-normalizing all ~14,200 rows per team
    looked up (50 leagues x ~20 teams would otherwise mean ~14,200 x 1,000
    redundant normalize() calls).

    451 of the ~14,200 names in the global scrape aren't unique -- lots of
    unrelated real clubs worldwide happen to share a short/generic name
    (confirmed: "Wolves" alone has 4 entries, the real Wolverhampton
    Wanderers at 84.9 plus three unrelated clubs down at 37-50). Keeping
    "whichever happens to end up in the dict" picked the WRONG one on a
    real run (37.5 for Wolves, right after they'd been relegated FROM the
    Premier League). For a duplicate, keep the HIGHEST-rated entry: a club
    good enough to play in a European country's top two tiers will almost
    always be the prominent, highly-rated side behind a shared name, not
    an obscure unrelated club elsewhere in the world that coincidentally
    shares it. Not bulletproof, but far better than file-order luck.
    """
    exact: dict[str, tuple[float, str]] = {}
    normalized: dict[str, tuple[float, str]] = {}
    for _, row in global_df.iterrows():
        rating, team = float(row["rating"]), row["team"]
        if team not in exact or rating > exact[team][0]:
            exact[team] = (rating, team)
        key = _normalize(team)
        if key not in normalized or rating > normalized[key][0]:
            normalized[key] = (rating, team)
    return exact, normalized


def _resolve_rating(team_name: str, exact: dict, normalized: dict, manual: dict) -> tuple[float, str]:
    """Returns (rating, matched_name_or_empty). Manual override -> exact ->
    normalized only -- see module docstring for why fuzzy matching against
    this large a pool is deliberately not attempted here."""
    if team_name in manual:
        return manual[team_name], team_name
    if team_name in exact:
        return exact[team_name]
    hit = normalized.get(_normalize(team_name))
    if hit:
        return hit
    return DEFAULT_OPTA, ""


def bootstrap_league(league_name: str, cfg: dict, key: str, exact: dict, normalized: dict) -> None:
    csv_path = RATINGS_DIR / f"{cfg['tsdb_id']}.csv"
    client = ApiFootballClient(api_key=key)
    season = cfg.get("af_season")
    try:
        roster = client.get_standings(cfg["id"], season)
        played, remaining = client.get_fixtures(cfg["id"], season)
    except RuntimeError as e:
        print(f"  WARNING: couldn't fetch roster for {league_name}: {e}", file=sys.stderr)
        return
    # The standings endpoint has been observed to come back empty even once
    # fixtures exist (same quirk football_rankings.py's fetch_all() already
    # works around) -- pad the roster out from the fixture list before
    # giving up on it.
    roster = ensure_full_roster(roster, played + remaining) if roster or played or remaining else roster
    if not roster:
        print(f"  WARNING: no roster or fixtures for {league_name} yet (season not published)", file=sys.stderr)
        return

    manual = MANUAL_RATINGS.get(league_name, {})
    rows, unmatched = [], []
    for team in roster:
        name = team.get("strTeam")
        if not name:
            continue
        rating, matched = _resolve_rating(name, exact, normalized, manual)
        alias = matched if matched and matched != name else ""
        rows.append({"team": name, "alias": alias, "opta_rating": round(rating, 1)})
        if not matched:
            unmatched.append(name)

    RATINGS_DIR.mkdir(exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "alias", "opta_rating"])
        writer.writeheader()
        writer.writerows(rows)

    msg = f"  {league_name}: {len(rows)} teams -> {csv_path}"
    if unmatched:
        msg += f" ({len(unmatched)} unmatched, using default {DEFAULT_OPTA}: {', '.join(unmatched)})"
    print(msg)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default=None, help="Bootstrap just this one LEAGUES_TIER2 key")
    args = parser.parse_args()

    if not Path(GLOBAL_RANKINGS_PATH).exists():
        print(f"{GLOBAL_RANKINGS_PATH} not found -- run scrape_opta_power_rankings.py first.", file=sys.stderr)
        sys.exit(1)
    global_df = pd.read_csv(GLOBAL_RANKINGS_PATH)
    global_df["rating"] = pd.to_numeric(global_df["rating"], errors="coerce")
    global_df = global_df.dropna(subset=["rating"])
    exact, normalized = _build_lookups(global_df)

    import os
    key = os.getenv("API_FOOTBALL_KEY", "")

    targets = {args.league: LEAGUES_TIER2[args.league]} if args.league else LEAGUES_TIER2
    print(f"Bootstrapping {len(targets)} second-tier league(s)...\n")
    for league_name, cfg in targets.items():
        bootstrap_league(league_name, cfg, key, exact, normalized)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
