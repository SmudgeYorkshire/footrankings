"""
Shared "Country - League" display labels for league dropdowns, so every
page (European Leagues, Opta Rankings, ...) sorts and labels leagues the
same way: Top 5 first, then alphabetical by country.

The underlying LEAGUES key is untouched everywhere else (page headers,
admin, ratings files, etc. all keep showing the full league name) — this
is purely a dropdown-display concern.
"""

from config import LEAGUES

TOP5_LEAGUES = {
    "English Premier League", "Italian Serie A", "Spanish La Liga",
    "German Bundesliga", "French Ligue 1",
}

DROPDOWN_LABELS: dict[str, str] = {
    "English Premier League":          "England - Premier League",
    "Italian Serie A":                 "Italy - Serie A",
    "Spanish La Liga":                 "Spain - La Liga",
    "German Bundesliga":               "Germany - Bundesliga",
    "French Ligue 1":                  "France - Ligue 1",
    "Albanian Superliga":              "Albania - Superliga",
    "Andorran 1a Divisió":             "Andorra - 1a Divisió",
    "Armenian Premier League":         "Armenia - Premier League",
    "Austrian Bundesliga":             "Austria - Bundesliga",
    "Azerbaijani Premier League":      "Azerbaijan - Premier League",
    "Belarus Vyscha Liga":             "Belarus - Vyscha Liga",
    "Belgian Pro League":              "Belgium - Pro League",
    "Bosnian Premier Liga":            "Bosnia and Herzegovina - Premier Liga",
    "Bulgarian First League":          "Bulgaria - First League",
    "Croatian First Football League":  "Croatia - First Football League",
    "Czech First League":              "Czech Republic - First League",
    "Cypriot First Division":          "Cyprus - First Division",
    "Danish Superliga":                "Denmark - Superliga",
    "Dutch Eredivisie":                "Netherlands - Eredivisie",
    "Estonian Meistriliiga":           "Estonia - Meistriliiga",
    "Faroe Islands Premier League":    "Faroe Islands - Premier League",
    "Finnish Veikkausliiga":           "Finland - Veikkausliiga",
    "Georgian Erovnuli Liga":          "Georgia - Erovnuli Liga",
    "Gibraltarian National League":    "Gibraltar - National League",
    "Greek Super League 1":            "Greece - Super League 1",
    "Hungarian NB I":                  "Hungary - NB I",
    "Icelandic Besta deild karla":     "Iceland - Besta deild karla",
    "Irish Premier Division":          "Ireland - Premier Division",
    "Israeli Premier League":          "Israel - Premier League",
    "Kazakhstan Premier League":       "Kazakhstan - Premier League",
    "Kosovan Superleague":             "Kosovo - Superleague",
    "Latvian Higher League":           "Latvia - Higher League",
    "Lithuanian TOPLYGA":              "Lithuania - TOPLYGA",
    "Luxembourg National Division":    "Luxembourg - National Division",
    "Macedonian First League":         "North Macedonia - First League",
    "Maltese Premier League":          "Malta - Premier League",
    "Moldovan National Division":      "Moldova - National Division",
    "Montenegrin First League":        "Montenegro - First League",
    "Northern Irish Premiership":      "Northern Ireland - Premiership",
    "Norwegian Eliteserien":           "Norway - Eliteserien",
    "Polish Ekstraklasa":              "Poland - Ekstraklasa",
    "Portuguese Primeira Liga":        "Portugal - Primeira Liga",
    "Romanian Liga I":                 "Romania - Liga I",
    "Russian Football Premier League": "Russia - Football Premier League",
    "San-Marino Campionato":           "San Marino - Campionato",
    "Scottish Premiership":            "Scotland - Premiership",
    "Serbian Super Liga":              "Serbia - Super Liga",
    "Slovak First Football League":    "Slovakia - First Football League",
    "Slovenian 1. SNL":                "Slovenia - 1. SNL",
    "Swedish Allsvenskan":             "Sweden - Allsvenskan",
    "Swiss Super League":              "Switzerland - Super League",
    "Turkish Super Lig":               "Turkey - Süper Lig",
    "Ukrainian Premier League":        "Ukraine - Premier League",
    "Welsh Cymru Premier":             "Wales - Cymru Premier",
}


def dropdown_sort_key(league_name: str) -> tuple:
    label = DROPDOWN_LABELS.get(league_name, league_name)
    country = label.split(" - ", 1)[0]
    return (0 if league_name in TOP5_LEAGUES else 1, country)


DROPDOWN_ORDER = sorted(LEAGUES.keys(), key=dropdown_sort_key)
