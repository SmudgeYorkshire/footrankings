"""
Shared country-flag lookup, used instead of flag emoji — Unicode regional-
indicator flag emoji fall back to raw two-letter text (e.g. "NO", "KZ") on
Windows browsers lacking flag glyphs, so every page that needs a flag next
to a country name renders one from flagcdn.com instead.
"""

FLAG_CODES: dict[str, str] = {
    "England": "gb-eng", "Italy": "it", "Spain": "es", "Germany": "de", "France": "fr",
    "Portugal": "pt", "Belgium": "be", "Netherlands": "nl", "Türkiye": "tr",
    "Czechia": "cz", "Poland": "pl", "Greece": "gr", "Denmark": "dk", "Norway": "no",
    "Cyprus": "cy", "Switzerland": "ch", "Hungary": "hu", "Sweden": "se",
    "Austria": "at", "Scotland": "gb-sct", "Croatia": "hr", "Romania": "ro",
    "Ukraine": "ua", "Israel": "il", "Slovenia": "si", "Azerbaijan": "az",
    "Bulgaria": "bg", "Slovakia": "sk", "Serbia": "rs", "Russia": "ru",
    "Iceland": "is", "Ireland": "ie", "Armenia": "am", "Kosovo": "xk",
    "Bosnia-Herzegovina": "ba", "Latvia": "lv", "Finland": "fi", "Kazakhstan": "kz",
    "Liechtenstein": "li", "Moldova": "md", "Faroe Islands": "fo",
    "North Macedonia": "mk", "Albania": "al", "Belarus": "by", "Lithuania": "lt",
    "Malta": "mt", "Andorra": "ad", "Estonia": "ee", "Gibraltar": "gi",
    "Northern Ireland": "gb-nir", "Georgia": "ge", "Luxembourg": "lu",
    "Montenegro": "me", "Wales": "gb-wls", "San Marino": "sm",
}


def flag_url(country: str) -> str:
    code = FLAG_CODES.get(country)
    return f"https://flagcdn.com/w40/{code}.png" if code else ""
