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

# Rest-of-world ISO 3166-1 alpha-2 codes, for eloratings.net's own global
# national-team roster (nation_power_rankings.py, "Nation Strength
# Rankings") -- kept separate from FLAG_CODES above (this site's existing
# 54-UEFA-nation scope) rather than merged into it, so nothing about that
# dict's own key set changes for any existing caller. Standard ISO codes
# throughout; a genuinely non-ISO disputed territory or sub-national
# region eloratings.net tracks (Northern Cyprus, Kurdistan, Tibet,
# Zanzibar, Somaliland, Chagos Islands, ...) is deliberately left out --
# flagcdn.com has no flag for those regardless, so a blank result is
# correct, not a gap to fill.
_GLOBAL_FLAG_CODES: dict[str, str] = {
    "Argentina": "ar", "Colombia": "co", "Brazil": "br", "Japan": "jp", "Morocco": "ma",
    "Uruguay": "uy", "Ecuador": "ec", "Paraguay": "py", "Mexico": "mx", "Senegal": "sn",
    "United States": "us", "Australia": "au", "Turkey": "tr", "Canada": "ca", "Iran": "ir",
    "Algeria": "dz", "Venezuela": "ve", "Ivory Coast": "ci", "Chile": "cl", "Egypt": "eg",
    "South Korea": "kr", "Nigeria": "ng", "DR Congo": "cd", "Peru": "pe",
    "Bosnia and Herzegovina": "ba", "Saudi Arabia": "sa", "Panama": "pa", "Uzbekistan": "uz",
    "Mali": "ml", "Cameroon": "cm", "Jordan": "jo", "Bolivia": "bo", "Costa Rica": "cr",
    "South Africa": "za", "Jamaica": "jm", "United Arab Emirates": "ae", "Cape Verde": "cv",
    "Angola": "ao", "New Zealand": "nz", "Haiti": "ht", "Iraq": "iq", "Burkina Faso": "bf",
    "Honduras": "hn", "Ghana": "gh", "Guatemala": "gt", "Palestine": "ps", "Curaçao": "cw",
    "Tunisia": "tn", "Guinea": "gn", "Gambia": "gm", "Qatar": "qa", "Syria": "sy",
    "Suriname": "sr", "Benin": "bj", "Oman": "om", "Libya": "ly", "Uganda": "ug",
    "Gabon": "ga", "Vietnam": "vn", "Equatorial Guinea": "gq", "Zimbabwe": "zw",
    "Rwanda": "rw", "Zambia": "zm", "Thailand": "th", "North Korea": "kp",
    "Madagascar": "mg", "Niger": "ne", "Togo": "tg", "Comoros": "km", "Kenya": "ke",
    "China": "cn", "Guinea-Bissau": "gw", "Mozambique": "mz", "Reunion": "re",
    "Trinidad and Tobago": "tt", "Sudan": "sd", "El Salvador": "sv", "Bahrain": "bh",
    "Dominican Republic": "do", "Mauritania": "mr", "Indonesia": "id", "Guyana": "gy",
    "Malaysia": "my", "Kyrgyzstan": "kg", "Tajikistan": "tj", "Kuwait": "kw",
    "Botswana": "bw", "Sierra Leone": "sl", "Burundi": "bi", "Namibia": "na",
    "Martinique": "mq", "Ethiopia": "et", "Lebanon": "lb", "Tanzania": "tz",
    "Liberia": "lr", "Nicaragua": "ni", "French Guiana": "gf", "Cuba": "cu",
    "Guadeloupe": "gp", "Malawi": "mw", "Yemen": "ye", "Congo": "cg",
    "Saint Vincent and the Grenadines": "vc", "Mayotte": "yt", "Turkmenistan": "tm",
    "Eritrea": "er", "Central African Republic": "cf", "New Caledonia": "nc",
    "Lesotho": "ls", "Puerto Rico": "pr", "Tahiti": "pf", "Eswatini": "sz",
    "Vanuatu": "vu", "Singapore": "sg", "India": "in", "Fiji": "fj",
    "Philippines": "ph", "Hong Kong": "hk", "Papua New Guinea": "pg",
    "Solomon Islands": "sb", "Saint Lucia": "lc", "South Sudan": "ss", "Chad": "td",
    "Mauritius": "mu", "Saint Kitts and Nevis": "kn", "Sao Tome and Principe": "st",
    "Grenada": "gd", "Saint Martin": "mf", "Montserrat": "ms", "Belize": "bz",
    "Myanmar": "mm", "Barbados": "bb", "Aruba": "aw", "Bermuda": "bm",
    "Western Sahara": "eh", "Somalia": "so", "Afghanistan": "af", "Pakistan": "pk",
    "Greenland": "gl", "Djibouti": "dj", "Sint Maarten": "sx", "Bangladesh": "bd",
    "Antigua and Barbuda": "ag", "Monaco": "mc", "Nepal": "np", "Cambodia": "kh",
    "Dominica": "dm", "Sri Lanka": "lk", "Bonaire": "bq", "Taiwan": "tw",
    "Seychelles": "sc", "Cayman Islands": "ky", "Maldives": "mv", "Tuvalu": "tv",
    "Samoa": "ws", "Mongolia": "mn", "Laos": "la", "Saint Barthelemy": "bl",
    "East Timor": "tl", "Guam": "gu", "Wallis and Futuna": "wf",
    "US Virgin Islands": "vi", "Vatican": "va", "Turks and Caicos Islands": "tc",
    "Saint Pierre and Miquelon": "pm", "British Virgin Islands": "vg",
    "Cook Islands": "ck", "Bahamas": "bs", "Bhutan": "bt", "Anguilla": "ai",
    "Macao": "mo", "Christmas Island": "cx", "Falkland Islands": "fk",
    "FS Micronesia": "fm", "Marshall Islands": "mh", "Brunei": "bn",
    "Kiribati": "ki", "Tonga": "to", "Niue": "nu", "Northern Mariana Islands": "mp",
    "Cocos Islands": "cc", "Palau": "pw", "Eastern Samoa": "as",
    "Sint Eustatius": "bq", "Saba": "bq",  # share Bonaire's own "bq" (Caribbean Netherlands) ISO subdivision
}


def flag_url(country: str) -> str:
    code = FLAG_CODES.get(country) or _GLOBAL_FLAG_CODES.get(country)
    return f"https://flagcdn.com/w40/{code}.png" if code else ""
