"""
2026-27 UEFA qualifying Play-off round bracket — which Third Qualifying Round
tie (or direct entrant) feeds each Play-off slot, per competition.

Sourced from Wikipedia's qualifying-phase articles (draw held 3 Aug 2026).
Team names here are matched fuzzily against live API-Football data rather
than trusted verbatim — Wikipedia's cached "Winner/Loser of X" placeholder
text can go stale when an earlier round doesn't go as originally seeded
(e.g. Larne's third-round opponent was drafted as "Iberia 1999" but ended
up being Saburtalo, who eliminated Iberia 1999 in the second round).

A "side" is one of:
  ("team", "Literal Name")                      — direct entrant, no QR3 tie
  ("tie", competition, {"Team A", "Team B"}, "winner" | "loser")
      — resolves against that competition's live QR3 ties by team-pair;
        "loser" sides are cross-competition drop-downs (CL QR3 losers feed
        EL play-offs; EL QR3 losers feed ECL play-offs).
"""

# Clubs already confirmed for the 2026-27 League Phase, entering directly
# (not through qualifying) — sourced from Wikipedia's "Teams" section for
# each competition. Champions League: 29 of 36 slots confirmed, the other 7
# go to Play-off round winners. Europa League: 17 of 36 slots confirmed, the
# rest fill via its own qualifying plus Champions League Play-off drop-downs.
CONFIRMED_LEAGUE_PHASE: dict[str, list[tuple[str, str, str]]] = {
    "Champions League": [
        ("Paris Saint-Germain", "France", "🇫🇷"),
        ("Aston Villa", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("Arsenal", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("Manchester City", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("Manchester United", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("Liverpool", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("Inter Milan", "Italy", "🇮🇹"),
        ("Napoli", "Italy", "🇮🇹"),
        ("Roma", "Italy", "🇮🇹"),
        ("Como", "Italy", "🇮🇹"),
        ("Barcelona", "Spain", "🇪🇸"),
        ("Real Madrid", "Spain", "🇪🇸"),
        ("Villarreal", "Spain", "🇪🇸"),
        ("Atlético Madrid", "Spain", "🇪🇸"),
        ("Real Betis", "Spain", "🇪🇸"),
        ("Bayern Munich", "Germany", "🇩🇪"),
        ("Borussia Dortmund", "Germany", "🇩🇪"),
        ("RB Leipzig", "Germany", "🇩🇪"),
        ("VfB Stuttgart", "Germany", "🇩🇪"),
        ("Lens", "France", "🇫🇷"),
        ("Lille", "France", "🇫🇷"),
        ("PSV Eindhoven", "Netherlands", "🇳🇱"),
        ("Feyenoord", "Netherlands", "🇳🇱"),
        ("Porto", "Portugal", "🇵🇹"),
        ("Sporting CP", "Portugal", "🇵🇹"),
        ("Club Brugge", "Belgium", "🇧🇪"),
        ("Slavia Prague", "Czechia", "🇨🇿"),
        ("Galatasaray", "Türkiye", "🇹🇷"),
        ("Shakhtar Donetsk", "Ukraine", "🇺🇦"),
    ],
    "Europa League": [
        ("Crystal Palace", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("Bournemouth", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("Sunderland", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ("AC Milan", "Italy", "🇮🇹"),
        ("Juventus", "Italy", "🇮🇹"),
        ("Real Sociedad", "Spain", "🇪🇸"),
        ("Celta Vigo", "Spain", "🇪🇸"),
        ("TSG Hoffenheim", "Germany", "🇩🇪"),
        ("Bayer Leverkusen", "Germany", "🇩🇪"),
        ("Marseille", "France", "🇫🇷"),
        ("Rennes", "France", "🇫🇷"),
        ("AZ Alkmaar", "Netherlands", "🇳🇱"),
        ("Torreense", "Portugal", "🇵🇹"),
        ("Olympiacos", "Greece", "🇬🇷"),
        ("Union Saint-Gilloise", "Belgium", "🇧🇪"),
        ("Sparta Prague", "Czechia", "🇨🇿"),
        ("Sturm Graz", "Austria", "🇦🇹"),
    ],
}


PLAYOFF_BRACKET: dict[str, list[tuple]] = {
    "Champions League": [
        (("team", "Celtic"), ("team", "LASK")),
        (("tie", "Champions League", {"Levski Sofia", "Kairat Almaty"}, "winner"),
         ("team", "AEK Athens")),
        (("tie", "Champions League", {"Dinamo Zagreb", "Kauno Žalgiris"}, "winner"),
         ("team", "Viking")),
        (("tie", "Champions League", {"Mjallby AIF", "Slovan Bratislava"}, "winner"),
         ("tie", "Champions League", {"Ararat-Armenia", "Celje"}, "winner")),
        (("tie", "Champions League", {"Hapoel Beer Sheva", "FK Crvena Zvezda"}, "winner"),
         ("tie", "Champions League", {"Aarhus", "Sabah FA"}, "winner")),
        (("tie", "Champions League", {"Fenerbahçe", "Sturm Graz"}, "winner"),
         ("tie", "Champions League", {"Lyon", "Sparta Praha"}, "winner")),
        (("tie", "Champions League", {"NEC Nijmegen", "Olympiakos Piraeus"}, "winner"),
         ("tie", "Champions League", {"Bodo/Glimt", "Union St. Gilloise"}, "winner")),
    ],
    "Europa League": [
        (("team", "Trabzonspor"),
         ("tie", "Europa League", {"Ferencvarosi TC", "Gornik Zabrze"}, "winner")),
        (("tie", "Europa League", {"KuPS", "Universitatea Craiova"}, "winner"),
         ("tie", "Champions League", {"Ararat-Armenia", "Celje"}, "loser")),
        (("team", "Sint-Truiden"),
         ("tie", "Europa League", {"Lincoln Red Imps FC", "Omonia Nicosia"}, "winner")),
        (("tie", "Champions League", {"Hapoel Beer Sheva", "FK Crvena Zvezda"}, "loser"),
         ("team", "Viktoria Plzen")),
        (("tie", "Europa League", {"Egnatia Rrogozhinë", "Shamrock Rovers"}, "winner"),
         ("team", "Lillestrom")),
        (("tie", "Europa League", {"Jagiellonia", "Rangers"}, "winner"),
         ("tie", "Europa League", {"Larne", "Saburtalo"}, "winner")),
        (("tie", "Champions League", {"Mjallby AIF", "Slovan Bratislava"}, "loser"),
         ("tie", "Europa League", {"Pafos", "Red Bull Salzburg"}, "winner")),
        (("tie", "Champions League", {"Levski Sofia", "Kairat Almaty"}, "loser"),
         ("tie", "Europa League", {"Anderlecht", "PAOK"}, "winner")),
        (("tie", "Europa League", {"KI Klaksvik", "Lech Poznan"}, "winner"),
         ("tie", "Europa League", {"FC Thun", "Vikingur Reykjavik"}, "winner")),
        (("tie", "Europa League", {"Beşiktaş", "Hradec Králové"}, "winner"),
         ("tie", "Champions League", {"Dinamo Zagreb", "Kauno Žalgiris"}, "loser")),
        (("tie", "Europa League", {"Benfica", "Heart Of Midlothian"}, "winner"),
         ("tie", "Champions League", {"Aarhus", "Sabah FA"}, "loser")),
        (("team", "OFI Crete"),
         ("tie", "Europa League", {"CSKA Sofia", "Maccabi Tel Aviv"}, "winner")),
    ],
    "Conference League": [
        (("tie", "Conference League", {"HJK Helsinki", "Motherwell"}, "winner"),
         ("team", "SC Freiburg")),
        (("tie", "Europa League", {"Ferencvarosi TC", "Gornik Zabrze"}, "loser"),
         ("team", "Monaco")),
        (("tie", "Conference League", {"FC Vaduz", "Inter Turku"}, "winner"),
         ("tie", "Conference League", {"Debreceni VSC", "FC Copenhagen"}, "winner")),
        (("tie", "Europa League", {"Benfica", "Heart Of Midlothian"}, "loser"),
         ("tie", "Conference League", {"Paide", "Rapid Vienna"}, "winner")),
        (("tie", "Conference League", {"CFR 1907 Cluj", "Tromso"}, "winner"),
         ("team", "Brighton & Hove Albion")),
        (("tie", "Conference League", {"FK Zalgiris Vilnius", "HNK Hajduk Split"}, "winner"),
         ("tie", "Conference League", {"Hammarby FF", "Raków Częstochowa"}, "winner")),
        (("tie", "Conference League", {"CSKA 1948", "Panathinaikos"}, "winner"),
         ("tie", "Europa League", {"Beşiktaş", "Hradec Králové"}, "loser")),
        (("tie", "Conference League", {"Gent", "IFK Goteborg"}, "winner"),
         ("tie", "Conference League", {"Hibernian", "Shkendija"}, "winner")),
        (("tie", "Europa League", {"Anderlecht", "PAOK"}, "loser"),
         ("tie", "Conference League", {"Apollon Limassol", "Brann"}, "winner")),
        (("team", "Atalanta"),
         ("tie", "Conference League", {"GKS Katowice", "Hapoel Tel Aviv"}, "winner")),
        (("tie", "Conference League", {"Bohemians", "FC Midtjylland"}, "winner"),
         ("tie", "Conference League", {"HNK Rijeka", "Ilves"}, "winner")),
        (("tie", "Europa League", {"Jagiellonia", "Rangers"}, "loser"),
         ("tie", "Conference League", {"FK Jablonec", "Rīgas FS"}, "winner")),
        (("tie", "Conference League", {"FC Nordsjaelland", "Valur Reykjavik"}, "winner"),
         ("tie", "Conference League", {"FC ST. Gallen", "Sheriff Tiraspol"}, "winner")),
        (("tie", "Conference League", {"Auda", "Dinamo Tirana"}, "winner"),
         ("tie", "Europa League", {"Pafos", "Red Bull Salzburg"}, "loser")),
        (("tie", "Conference League", {"FC Noah", "FC Sion"}, "winner"),
         ("tie", "Conference League", {"Ajax", "Shelbourne"}, "winner")),
        (("tie", "Conference League", {"SC Braga", "Dinamo Minsk"}, "winner"),
         ("tie", "Conference League", {"Austria Vienna", "Beitar Jerusalem"}, "winner")),
        (("tie", "Conference League", {"Dunajska Streda", "Twente"}, "winner"),
         ("tie", "Conference League", {"Dynamo Kyiv", "Qarabag"}, "winner")),
        (("team", "Getafe"),
         ("tie", "Conference League", {"FK Partizan", "FK Tobol Kostanay"}, "winner")),
        (("tie", "Conference League", {"FC Lugano", "NSI Runavik"}, "winner"),
         ("tie", "Europa League", {"CSKA Sofia", "Maccabi Tel Aviv"}, "loser")),
        # Champions Path ties -- both sides already confirmed teams (no QR3
        # resolution needed) by the time the Play-off round is reached.
        (("team", "Borac Banja Luka"), ("team", "Vikingur Reykjavik")),
        (("team", "Drita"), ("team", "Inter Club d'Escaldes")),
        (("team", "KI Klaksvik"), ("team", "Riga")),
        (("team", "KuPS"), ("team", "Shamrock Rovers")),
        (("team", "Larne"), ("team", "Lincoln Red Imps FC")),
    ],
}
