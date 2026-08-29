"""
Real 2026-27 UEFA League Phase opponent lists.

UEFA's official "Results" page (like the one screenshotted for this
feature) lists each club's 8 (or 6, Conference League) opponents with a
home/away icon per slot, but not grouped into matchday order -- so that's
what gets transcribed here: per club, a list of (opponent, "H"|"A")
tuples. Once every club in a competition has its list filled in,
derive_fixtures() below turns that into a real fixture list (with real
home/away legs, since the icon tells us that much) that
league_phase_simulator can simulate instead of its own synthetic
pot-based schedule, and european.py can use for a real fixture-difficulty
ranking.

Only one side of each pairing needs to be entered -- if Real Madrid's own
list says ("Liverpool", "H"), that already fully determines the match
(Real Madrid home, Liverpool away) without needing Liverpool's list to
also mention it.
"""

LEAGUE_PHASE_OPPONENT_COUNT: dict[str, int] = {
    "Champions League": 8,
    "Europa League": 8,
    "Conference League": 6,
}

# comp -> team -> [(opponent, "H"|"A"), ...]
LEAGUE_PHASE_OPPONENTS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "Champions League": {
        "Paris Saint-Germain": [
            ("Barcelona", "H"), ("Manchester City", "A"),
            ("Roma", "H"), ("Aston Villa", "A"),
            ("Galatasaray", "H"), ("Villarreal", "A"),
            ("Slovan Bratislava", "H"), ("Como", "A"),
        ],
        "Bayern Munich": [
            ("Arsenal", "H"), ("Atlético Madrid", "A"),
            ("Real Betis", "H"), ("Manchester United", "A"),
            ("Bodo/Glimt", "H"), ("Lille", "A"),
            ("Slavia Prague", "H"), ("Viking", "A"),
        ],
        "Real Madrid": [
            ("Inter Milan", "H"), ("Arsenal", "A"),
            ("PSV Eindhoven", "H"), ("Roma", "A"),
            ("RB Leipzig", "H"), ("Shakhtar Donetsk", "A"),
            ("Lask Linz", "H"), ("AEK Athens FC", "A"),
        ],
        "Liverpool": [
            ("Atlético Madrid", "H"), ("Inter Milan", "A"),
            ("Porto", "H"), ("Club Brugge", "A"),
            ("Villarreal", "H"), ("Fenerbahçe", "A"),
            ("Lens", "H"), ("Lask Linz", "A"),
        ],
        "Inter Milan": [
            ("Liverpool", "H"), ("Real Madrid", "A"),
            ("Club Brugge", "H"), ("Borussia Dortmund", "A"),
            ("Shakhtar Donetsk", "H"), ("Feyenoord", "A"),
            ("VfB Stuttgart", "H"), ("Slovan Bratislava", "A"),
        ],
        "Manchester City": [
            ("Paris Saint-Germain", "H"), ("Barcelona", "A"),
            ("Sporting CP", "H"), ("Porto", "A"),
            ("Napoli", "H"), ("RB Leipzig", "A"),
            ("AEK Athens FC", "H"), ("Lens", "A"),
        ],
        "Arsenal": [
            ("Real Madrid", "H"), ("Bayern Munich", "A"),
            ("Borussia Dortmund", "H"), ("Real Betis", "A"),
            ("Lille", "H"), ("Napoli", "A"),
            ("Sabah FA", "H"), ("Slavia Prague", "A"),
        ],
        "Barcelona": [
            ("Manchester City", "H"), ("Paris Saint-Germain", "A"),
            ("Aston Villa", "H"), ("Sporting CP", "A"),
            ("Feyenoord", "H"), ("Galatasaray", "A"),
            ("Como", "H"), ("Sabah FA", "A"),
        ],
        "Atlético Madrid": [
            ("Bayern Munich", "H"), ("Liverpool", "A"),
            ("Manchester United", "H"), ("PSV Eindhoven", "A"),
            ("Fenerbahçe", "H"), ("Bodo/Glimt", "A"),
            ("Viking", "H"), ("VfB Stuttgart", "A"),
        ],
        "Borussia Dortmund": [
            ("Inter Milan", "H"), ("Arsenal", "A"),
            ("Real Betis", "H"), ("Aston Villa", "A"),
            ("Villarreal", "H"), ("Bodo/Glimt", "A"),
            ("AEK Athens FC", "H"), ("Sabah FA", "A"),
        ],
        "Roma": [
            ("Real Madrid", "H"), ("Paris Saint-Germain", "A"),
            ("Sporting CP", "H"), ("Manchester United", "A"),
            ("Lille", "H"), ("Fenerbahçe", "A"),
            ("Slovan Bratislava", "H"), ("AEK Athens FC", "A"),
        ],
        "Sporting CP": [
            ("Barcelona", "H"), ("Manchester City", "A"),
            ("Manchester United", "H"), ("Roma", "A"),
            ("Galatasaray", "H"), ("Shakhtar Donetsk", "A"),
            ("Lask Linz", "H"), ("Lens", "A"),
        ],
        "Aston Villa": [
            ("Paris Saint-Germain", "H"), ("Barcelona", "A"),
            ("Borussia Dortmund", "H"), ("Club Brugge", "A"),
            ("Fenerbahçe", "H"), ("Galatasaray", "A"),
            ("Viking", "H"), ("Slavia Prague", "A"),
        ],
        "Porto": [
            ("Manchester City", "H"), ("Liverpool", "A"),
            ("PSV Eindhoven", "H"), ("Real Betis", "A"),
            ("Napoli", "H"), ("Feyenoord", "A"),
            ("Slavia Prague", "H"), ("Lask Linz", "A"),
        ],
        "Manchester United": [
            ("Bayern Munich", "H"), ("Atlético Madrid", "A"),
            ("Roma", "H"), ("Sporting CP", "A"),
            ("RB Leipzig", "H"), ("Villarreal", "A"),
            ("Sabah FA", "H"), ("Como", "A"),
        ],
        "Club Brugge": [
            ("Liverpool", "H"), ("Inter Milan", "A"),
            ("Aston Villa", "H"), ("PSV Eindhoven", "A"),
            ("Bodo/Glimt", "H"), ("Napoli", "A"),
            ("Lens", "H"), ("VfB Stuttgart", "A"),
        ],
        "Real Betis": [
            ("Arsenal", "H"), ("Bayern Munich", "A"),
            ("Porto", "H"), ("Borussia Dortmund", "A"),
            ("Feyenoord", "H"), ("Lille", "A"),
            ("Como", "H"), ("Slovan Bratislava", "A"),
        ],
        "PSV Eindhoven": [
            ("Atlético Madrid", "H"), ("Real Madrid", "A"),
            ("Club Brugge", "H"), ("Porto", "A"),
            ("Shakhtar Donetsk", "H"), ("RB Leipzig", "A"),
            ("VfB Stuttgart", "H"), ("Viking", "A"),
        ],
        "Feyenoord": [
            ("Inter Milan", "H"), ("Barcelona", "A"),
            ("Porto", "H"), ("Real Betis", "A"),
            ("RB Leipzig", "H"), ("Galatasaray", "A"),
            ("Como", "H"), ("Viking", "A"),
        ],
        "Lille": [
            ("Bayern Munich", "H"), ("Arsenal", "A"),
            ("Real Betis", "H"), ("Roma", "A"),
            ("Galatasaray", "H"), ("Bodo/Glimt", "A"),
            ("Slovan Bratislava", "H"), ("VfB Stuttgart", "A"),
        ],
        "Napoli": [
            ("Arsenal", "H"), ("Manchester City", "A"),
            ("Club Brugge", "H"), ("Porto", "A"),
            ("Bodo/Glimt", "H"), ("Villarreal", "A"),
            ("Viking", "H"), ("Sabah FA", "A"),
        ],
        "Bodo/Glimt": [
            ("Atlético Madrid", "H"), ("Bayern Munich", "A"),
            ("Borussia Dortmund", "H"), ("Club Brugge", "A"),
            ("Lille", "H"), ("Napoli", "A"),
            ("Lask Linz", "H"), ("Lens", "A"),
        ],
        "RB Leipzig": [
            ("Manchester City", "H"), ("Real Madrid", "A"),
            ("PSV Eindhoven", "H"), ("Manchester United", "A"),
            ("Shakhtar Donetsk", "H"), ("Feyenoord", "A"),
            ("Lens", "H"), ("Como", "A"),
        ],
        "Villarreal": [
            ("Paris Saint-Germain", "H"), ("Liverpool", "A"),
            ("Manchester United", "H"), ("Borussia Dortmund", "A"),
            ("Napoli", "H"), ("Fenerbahçe", "A"),
            ("Sabah FA", "H"), ("Slavia Prague", "A"),
        ],
        "Fenerbahçe": [
            ("Liverpool", "H"), ("Atlético Madrid", "A"),
            ("Roma", "H"), ("Aston Villa", "A"),
            ("Villarreal", "H"), ("Shakhtar Donetsk", "A"),
            ("Slavia Prague", "H"), ("Lask Linz", "A"),
        ],
        "Shakhtar Donetsk": [
            ("Real Madrid", "H"), ("Inter Milan", "A"),
            ("Sporting CP", "H"), ("PSV Eindhoven", "A"),
            ("Fenerbahçe", "H"), ("RB Leipzig", "A"),
            ("AEK Athens FC", "H"), ("Slovan Bratislava", "A"),
        ],
        "Viking": [
            ("Bayern Munich", "H"), ("Atlético Madrid", "A"),
            ("PSV Eindhoven", "H"), ("Aston Villa", "A"),
            ("Feyenoord", "H"), ("Napoli", "A"),
            ("Sabah FA", "H"), ("VfB Stuttgart", "A"),
        ],
        "Sabah FA": [
            ("Barcelona", "H"), ("Arsenal", "A"),
            ("Borussia Dortmund", "H"), ("Manchester United", "A"),
            ("Napoli", "H"), ("Villarreal", "A"),
            ("Slavia Prague", "H"), ("Viking", "A"),
        ],
        "Como": [
            ("Paris Saint-Germain", "H"), ("Barcelona", "A"),
            ("Manchester United", "H"), ("Real Betis", "A"),
            ("RB Leipzig", "H"), ("Feyenoord", "A"),
            ("AEK Athens FC", "H"), ("Lens", "A"),
        ],
        "Lens": [
            ("Manchester City", "H"), ("Liverpool", "A"),
            ("Sporting CP", "H"), ("Club Brugge", "A"),
            ("Bodo/Glimt", "H"), ("RB Leipzig", "A"),
            ("Como", "H"), ("Slavia Prague", "A"),
        ],
        "Galatasaray": [
            ("Barcelona", "H"), ("Paris Saint-Germain", "A"),
            ("Aston Villa", "H"), ("Sporting CP", "A"),
            ("Feyenoord", "H"), ("Lille", "A"),
            ("VfB Stuttgart", "H"), ("AEK Athens FC", "A"),
        ],
        "Slavia Prague": [
            ("Arsenal", "H"), ("Bayern Munich", "A"),
            ("Aston Villa", "H"), ("Porto", "A"),
            ("Villarreal", "H"), ("Fenerbahçe", "A"),
            ("Lens", "H"), ("Sabah FA", "A"),
        ],
        "Slovan Bratislava": [
            ("Inter Milan", "H"), ("Paris Saint-Germain", "A"),
            ("Real Betis", "H"), ("Roma", "A"),
            ("Shakhtar Donetsk", "H"), ("Lille", "A"),
            ("VfB Stuttgart", "H"), ("Lask Linz", "A"),
        ],
        "VfB Stuttgart": [
            ("Atlético Madrid", "H"), ("Inter Milan", "A"),
            ("Club Brugge", "H"), ("PSV Eindhoven", "A"),
            ("Lille", "H"), ("Galatasaray", "A"),
            ("Viking", "H"), ("Slovan Bratislava", "A"),
        ],
        "AEK Athens FC": [
            ("Real Madrid", "H"), ("Manchester City", "A"),
            ("Roma", "H"), ("Borussia Dortmund", "A"),
            ("Galatasaray", "H"), ("Shakhtar Donetsk", "A"),
            ("Lask Linz", "H"), ("Como", "A"),
        ],
        "Lask Linz": [
            ("Liverpool", "H"), ("Real Madrid", "A"),
            ("Porto", "H"), ("Sporting CP", "A"),
            ("Fenerbahçe", "H"), ("Bodo/Glimt", "A"),
            ("Slovan Bratislava", "H"), ("AEK Athens FC", "A"),
        ],
    },
    "Europa League": {
        "Bayer Leverkusen": [
            ("Marseille", "H"), ("Lyon", "A"),
            ("Red Bull Salzburg", "H"), ("Dinamo Zagreb", "A"),
            ("Celje", "H"), ("Lech Poznan", "A"),
            ("Beşiktaş", "H"), ("OFI", "A"),
        ],
        "Benfica": [
            ("AZ Alkmaar", "H"), ("AC Milan", "A"),
            ("Celtic", "H"), ("Plzen", "A"),
            ("Lech Poznan", "H"), ("Omonia Nicosia", "A"),
            ("OFI", "H"), ("NEC Nijmegen", "A"),
        ],
        "Juventus": [
            ("Real Sociedad", "H"), ("AZ Alkmaar", "A"),
            ("Rennes", "H"), ("Ferencvarosi TC", "A"),
            ("Omonia Nicosia", "H"), ("Celta Vigo", "A"),
            ("NEC Nijmegen", "H"), ("Hapoel Beer Sheva", "A"),
        ],
        "AC Milan": [
            ("Benfica", "H"), ("Olympiacos", "A"),
            ("Ferencvarosi TC", "H"), ("Red Bull Salzburg", "A"),
            ("Sunderland", "H"), ("Bournemouth", "A"),
            ("Ararat-Armenia", "H"), ("Levski Sofia", "A"),
        ],
        "Lyon": [
            ("Bayer Leverkusen", "H"), ("Real Sociedad", "A"),
            ("Union Saint-Gilloise", "H"), ("Anderlecht", "A"),
            ("Crystal Palace", "H"), ("Jagiellonia", "A"),
            ("Lillestrom", "H"), ("TSG Hoffenheim", "A"),
        ],
        "AZ Alkmaar": [
            ("Juventus", "H"), ("Benfica", "A"),
            ("Dinamo Zagreb", "H"), ("Sparta Prague", "A"),
            ("Sturm Graz", "H"), ("Sunderland", "A"),
            ("Hapoel Beer Sheva", "H"), ("Ararat-Armenia", "A"),
        ],
        "Olympiacos": [
            ("AC Milan", "H"), ("Marseille", "A"),
            ("Sparta Prague", "H"), ("Rennes", "A"),
            ("Jagiellonia", "H"), ("Celje", "A"),
            ("TSG Hoffenheim", "H"), ("Torreense", "A"),
        ],
        "Real Sociedad": [
            ("Lyon", "H"), ("Juventus", "A"),
            ("Plzen", "H"), ("Union Saint-Gilloise", "A"),
            ("Bournemouth", "H"), ("Crystal Palace", "A"),
            ("Torreense", "H"), ("Lillestrom", "A"),
        ],
        "Marseille": [
            ("Olympiacos", "H"), ("Bayer Leverkusen", "A"),
            ("Anderlecht", "H"), ("Celtic", "A"),
            ("Celta Vigo", "H"), ("Sturm Graz", "A"),
            ("Levski Sofia", "H"), ("Beşiktaş", "A"),
        ],
        "Ferencvarosi TC": [
            ("Juventus", "H"), ("AC Milan", "A"),
            ("Plzen", "H"), ("Celtic", "A"),
            ("Celje", "H"), ("Lech Poznan", "A"),
            ("Torreense", "H"), ("TSG Hoffenheim", "A"),
        ],
        "Plzen": [
            ("Benfica", "H"), ("Real Sociedad", "A"),
            ("Union Saint-Gilloise", "H"), ("Ferencvarosi TC", "A"),
            ("Jagiellonia", "H"), ("Bournemouth", "A"),
            ("Levski Sofia", "H"), ("Lillestrom", "A"),
        ],
        "Union Saint-Gilloise": [
            ("Real Sociedad", "H"), ("Lyon", "A"),
            ("Celtic", "H"), ("Plzen", "A"),
            ("Lech Poznan", "H"), ("Celta Vigo", "A"),
            ("Hapoel Beer Sheva", "H"), ("Beşiktaş", "A"),
        ],
        "Dinamo Zagreb": [
            ("Bayer Leverkusen", "H"), ("AZ Alkmaar", "A"),
            ("Anderlecht", "H"), ("Rennes", "A"),
            ("Sturm Graz", "H"), ("Sunderland", "A"),
            ("NEC Nijmegen", "H"), ("Hapoel Beer Sheva", "A"),
        ],
        "Red Bull Salzburg": [
            ("AC Milan", "H"), ("Bayer Leverkusen", "A"),
            ("Sparta Prague", "H"), ("Anderlecht", "A"),
            ("Crystal Palace", "H"), ("Celje", "A"),
            ("Ararat-Armenia", "H"), ("Levski Sofia", "A"),
        ],
        "Celtic": [
            ("Marseille", "H"), ("Benfica", "A"),
            ("Ferencvarosi TC", "H"), ("Union Saint-Gilloise", "A"),
            ("Celta Vigo", "H"), ("Omonia Nicosia", "A"),
            ("Beşiktaş", "H"), ("Torreense", "A"),
        ],
        "Sparta Prague": [
            ("AZ Alkmaar", "H"), ("Olympiacos", "A"),
            ("Rennes", "H"), ("Red Bull Salzburg", "A"),
            ("Bournemouth", "H"), ("Crystal Palace", "A"),
            ("Lillestrom", "H"), ("Ararat-Armenia", "A"),
        ],
        "Rennes": [
            ("Olympiacos", "H"), ("Juventus", "A"),
            ("Dinamo Zagreb", "H"), ("Sparta Prague", "A"),
            ("Omonia Nicosia", "H"), ("Sturm Graz", "A"),
            ("OFI", "H"), ("NEC Nijmegen", "A"),
        ],
        "Anderlecht": [
            ("Lyon", "H"), ("Marseille", "A"),
            ("Red Bull Salzburg", "H"), ("Dinamo Zagreb", "A"),
            ("Sunderland", "H"), ("Jagiellonia", "A"),
            ("TSG Hoffenheim", "H"), ("OFI", "A"),
        ],
        "Sturm Graz": [
            ("Marseille", "H"), ("AZ Alkmaar", "A"),
            ("Rennes", "H"), ("Dinamo Zagreb", "A"),
            ("Celje", "H"), ("Bournemouth", "A"),
            ("OFI", "H"), ("TSG Hoffenheim", "A"),
        ],
        "Lech Poznan": [
            ("Bayer Leverkusen", "H"), ("Benfica", "A"),
            ("Ferencvarosi TC", "H"), ("Union Saint-Gilloise", "A"),
            ("Sunderland", "H"), ("Crystal Palace", "A"),
            ("Torreense", "H"), ("OFI", "A"),
        ],
        "Crystal Palace": [
            ("Real Sociedad", "H"), ("Lyon", "A"),
            ("Sparta Prague", "H"), ("Red Bull Salzburg", "A"),
            ("Lech Poznan", "H"), ("Jagiellonia", "A"),
            ("TSG Hoffenheim", "H"), ("Beşiktaş", "A"),
        ],
        "Bournemouth": [
            ("AC Milan", "H"), ("Real Sociedad", "A"),
            ("Plzen", "H"), ("Sparta Prague", "A"),
            ("Sturm Graz", "H"), ("Celta Vigo", "A"),
            ("Hapoel Beer Sheva", "H"), ("Lillestrom", "A"),
        ],
        "Sunderland": [
            ("AZ Alkmaar", "H"), ("AC Milan", "A"),
            ("Dinamo Zagreb", "H"), ("Anderlecht", "A"),
            ("Jagiellonia", "H"), ("Lech Poznan", "A"),
            ("Levski Sofia", "H"), ("Torreense", "A"),
        ],
        "Celje": [
            ("Olympiacos", "H"), ("Bayer Leverkusen", "A"),
            ("Red Bull Salzburg", "H"), ("Ferencvarosi TC", "A"),
            ("Omonia Nicosia", "H"), ("Sturm Graz", "A"),
            ("NEC Nijmegen", "H"), ("Ararat-Armenia", "A"),
        ],
        "Jagiellonia": [
            ("Lyon", "H"), ("Olympiacos", "A"),
            ("Anderlecht", "H"), ("Plzen", "A"),
            ("Crystal Palace", "H"), ("Sunderland", "A"),
            ("Ararat-Armenia", "H"), ("Levski Sofia", "A"),
        ],
        "Omonia Nicosia": [
            ("Benfica", "H"), ("Juventus", "A"),
            ("Celtic", "H"), ("Rennes", "A"),
            ("Celta Vigo", "H"), ("Celje", "A"),
            ("Beşiktaş", "H"), ("NEC Nijmegen", "A"),
        ],
        "Celta Vigo": [
            ("Juventus", "H"), ("Marseille", "A"),
            ("Union Saint-Gilloise", "H"), ("Celtic", "A"),
            ("Bournemouth", "H"), ("Omonia Nicosia", "A"),
            ("Lillestrom", "H"), ("Hapoel Beer Sheva", "A"),
        ],
        "TSG Hoffenheim": [
            ("Lyon", "H"), ("Olympiacos", "A"),
            ("Ferencvarosi TC", "H"), ("Anderlecht", "A"),
            ("Sturm Graz", "H"), ("Crystal Palace", "A"),
            ("Beşiktaş", "H"), ("OFI", "A"),
        ],
        "Beşiktaş": [
            ("Marseille", "H"), ("Bayer Leverkusen", "A"),
            ("Union Saint-Gilloise", "H"), ("Celtic", "A"),
            ("Crystal Palace", "H"), ("Omonia Nicosia", "A"),
            ("Hapoel Beer Sheva", "H"), ("TSG Hoffenheim", "A"),
        ],
        "Torreense": [
            ("Olympiacos", "H"), ("Real Sociedad", "A"),
            ("Celtic", "H"), ("Ferencvarosi TC", "A"),
            ("Sunderland", "H"), ("Lech Poznan", "A"),
            ("Ararat-Armenia", "H"), ("Lillestrom", "A"),
        ],
        "Hapoel Beer Sheva": [
            ("Juventus", "H"), ("AZ Alkmaar", "A"),
            ("Dinamo Zagreb", "H"), ("Union Saint-Gilloise", "A"),
            ("Celta Vigo", "H"), ("Bournemouth", "A"),
            ("OFI", "H"), ("Beşiktaş", "A"),
        ],
        "NEC Nijmegen": [
            ("Benfica", "H"), ("Juventus", "A"),
            ("Rennes", "H"), ("Dinamo Zagreb", "A"),
            ("Omonia Nicosia", "H"), ("Celje", "A"),
            ("Levski Sofia", "H"), ("Ararat-Armenia", "A"),
        ],
        "OFI": [
            ("Bayer Leverkusen", "H"), ("Benfica", "A"),
            ("Anderlecht", "H"), ("Rennes", "A"),
            ("Sturm Graz", "H"), ("Lech Poznan", "A"),
            ("TSG Hoffenheim", "H"), ("Hapoel Beer Sheva", "A"),
        ],
        "Lillestrom": [
            ("Real Sociedad", "H"), ("Lyon", "A"),
            ("Plzen", "H"), ("Sparta Prague", "A"),
            ("Bournemouth", "H"), ("Celta Vigo", "A"),
            ("Torreense", "H"), ("Levski Sofia", "A"),
        ],
        "Levski Sofia": [
            ("AC Milan", "H"), ("Marseille", "A"),
            ("Red Bull Salzburg", "H"), ("Plzen", "A"),
            ("Jagiellonia", "H"), ("Sunderland", "A"),
            ("Lillestrom", "H"), ("NEC Nijmegen", "A"),
        ],
        "Ararat-Armenia": [
            ("AZ Alkmaar", "H"), ("AC Milan", "A"),
            ("Sparta Prague", "H"), ("Red Bull Salzburg", "A"),
            ("Celje", "H"), ("Jagiellonia", "A"),
            ("NEC Nijmegen", "H"), ("Torreense", "A"),
        ],
    },
    "Conference League": {
        "Atalanta": [
            ("Pafos", "H"), ("Ajax", "A"),
            ("Kairat Almaty", "H"), ("Borac Banja Luka", "A"),
            ("Mjallby AIF", "H"), ("Riga", "A"),
        ],
        "SC Braga": [
            ("Gent", "H"), ("FC Copenhagen", "A"),
            ("KuPS", "H"), ("Brann", "A"),
            ("Egnatia Rrogozhinë", "H"), ("Aarhus", "A"),
        ],
        "Ajax": [
            ("Atalanta", "H"), ("FC Midtjylland", "A"),
            ("Getafe", "H"), ("St. Truiden", "A"),
            ("FC Thun", "H"), ("HNK Hajduk Split", "A"),
        ],
        "SC Freiburg": [
            ("Panathinaikos", "H"), ("Monaco", "A"),
            ("Twente", "H"), ("Trabzonspor", "A"),
            ("FK Jablonec", "H"), ("Kauno Žalgiris", "A"),
        ],
        "Monaco": [
            ("SC Freiburg", "H"), ("Brighton", "A"),
            ("Lincoln Red Imps FC", "H"), ("Heart Of Midlothian", "A"),
            ("FC Nordsjaelland", "H"), ("CSKA Sofia", "A"),
        ],
        "FC Copenhagen": [
            ("SC Braga", "H"), ("FK Crvena Zvezda", "A"),
            ("FC Lugano", "H"), ("Universitatea Craiova", "A"),
            ("FC Iberia 1999", "H"), ("Inter Club d'Escaldes", "A"),
        ],
        "FC Midtjylland": [
            ("Ajax", "H"), ("Pafos", "A"),
            ("St. Truiden", "H"), ("Lincoln Red Imps FC", "A"),
            ("HNK Hajduk Split", "H"), ("Egnatia Rrogozhinë", "A"),
        ],
        "FK Crvena Zvezda": [
            ("FC Copenhagen", "H"), ("Gent", "A"),
            ("Trabzonspor", "H"), ("FC Lugano", "A"),
            ("Inter Club d'Escaldes", "H"), ("FC Iberia 1999", "A"),
        ],
        "Gent": [
            ("FK Crvena Zvezda", "H"), ("SC Braga", "A"),
            ("Brann", "H"), ("KuPS", "A"),
            ("Aarhus", "H"), ("FC Thun", "A"),
        ],
        "Panathinaikos": [
            ("Brighton", "H"), ("SC Freiburg", "A"),
            ("Borac Banja Luka", "H"), ("Kairat Almaty", "A"),
            ("CSKA Sofia", "H"), ("FC Nordsjaelland", "A"),
        ],
        "Pafos": [
            ("FC Midtjylland", "H"), ("Atalanta", "A"),
            ("Heart Of Midlothian", "H"), ("Twente", "A"),
            ("Riga", "H"), ("Mjallby AIF", "A"),
        ],
        "Brighton": [
            ("Monaco", "H"), ("Panathinaikos", "A"),
            ("Universitatea Craiova", "H"), ("Getafe", "A"),
            ("Kauno Žalgiris", "H"), ("FK Jablonec", "A"),
        ],
        "FC Lugano": [
            ("FK Crvena Zvezda", "H"), ("FC Copenhagen", "A"),
            ("St. Truiden", "H"), ("Getafe", "A"),
            ("Kauno Žalgiris", "H"), ("FK Jablonec", "A"),
        ],
        "Getafe": [
            ("Brighton", "H"), ("Ajax", "A"),
            ("FC Lugano", "H"), ("Universitatea Craiova", "A"),
            ("Inter Club d'Escaldes", "H"), ("FC Iberia 1999", "A"),
        ],
        "KuPS": [
            ("Gent", "H"), ("SC Braga", "A"),
            ("Trabzonspor", "H"), ("Borac Banja Luka", "A"),
            ("CSKA Sofia", "H"), ("FC Nordsjaelland", "A"),
        ],
        "Twente": [
            ("Pafos", "H"), ("SC Freiburg", "A"),
            ("Kairat Almaty", "H"), ("Lincoln Red Imps FC", "A"),
            ("FC Thun", "H"), ("Aarhus", "A"),
        ],
        "Lincoln Red Imps FC": [
            ("FC Midtjylland", "H"), ("Monaco", "A"),
            ("Twente", "H"), ("Brann", "A"),
            ("HNK Hajduk Split", "H"), ("Egnatia Rrogozhinë", "A"),
        ],
        "Borac Banja Luka": [
            ("Atalanta", "H"), ("Panathinaikos", "A"),
            ("KuPS", "H"), ("Heart Of Midlothian", "A"),
            ("Riga", "H"), ("Mjallby AIF", "A"),
        ],
        "St. Truiden": [
            ("Ajax", "H"), ("FC Midtjylland", "A"),
            ("Brann", "H"), ("FC Lugano", "A"),
            ("FC Iberia 1999", "H"), ("HNK Hajduk Split", "A"),
        ],
        "Brann": [
            ("SC Braga", "H"), ("Gent", "A"),
            ("Lincoln Red Imps FC", "H"), ("St. Truiden", "A"),
            ("Aarhus", "H"), ("Kauno Žalgiris", "A"),
        ],
        "Heart Of Midlothian": [
            ("Monaco", "H"), ("Pafos", "A"),
            ("Borac Banja Luka", "H"), ("Trabzonspor", "A"),
            ("FC Nordsjaelland", "H"), ("FC Thun", "A"),
        ],
        "Kairat Almaty": [
            ("Panathinaikos", "H"), ("Atalanta", "A"),
            ("Universitatea Craiova", "H"), ("Twente", "A"),
            ("Mjallby AIF", "H"), ("Riga", "A"),
        ],
        "Trabzonspor": [
            ("SC Freiburg", "H"), ("FK Crvena Zvezda", "A"),
            ("Heart Of Midlothian", "H"), ("KuPS", "A"),
            ("FK Jablonec", "H"), ("CSKA Sofia", "A"),
        ],
        "Universitatea Craiova": [
            ("FC Copenhagen", "H"), ("Brighton", "A"),
            ("Getafe", "H"), ("Kairat Almaty", "A"),
            ("Egnatia Rrogozhinë", "H"), ("Inter Club d'Escaldes", "A"),
        ],
        "Riga": [
            ("Atalanta", "H"), ("Pafos", "A"),
            ("Kairat Almaty", "H"), ("Borac Banja Luka", "A"),
            ("FK Jablonec", "H"), ("Kauno Žalgiris", "A"),
        ],
        "HNK Hajduk Split": [
            ("Ajax", "H"), ("FC Midtjylland", "A"),
            ("St. Truiden", "H"), ("Lincoln Red Imps FC", "A"),
            ("FC Nordsjaelland", "H"), ("FC Thun", "A"),
        ],
        "FK Jablonec": [
            ("Brighton", "H"), ("SC Freiburg", "A"),
            ("FC Lugano", "H"), ("Trabzonspor", "A"),
            ("FC Iberia 1999", "H"), ("Riga", "A"),
        ],
        "FC Nordsjaelland": [
            ("Panathinaikos", "H"), ("Monaco", "A"),
            ("KuPS", "H"), ("Heart Of Midlothian", "A"),
            ("CSKA Sofia", "H"), ("HNK Hajduk Split", "A"),
        ],
        "Aarhus": [
            ("SC Braga", "H"), ("Gent", "A"),
            ("Twente", "H"), ("Brann", "A"),
            ("Egnatia Rrogozhinë", "H"), ("Inter Club d'Escaldes", "A"),
        ],
        "Inter Club d'Escaldes": [
            ("FC Copenhagen", "H"), ("FK Crvena Zvezda", "A"),
            ("Universitatea Craiova", "H"), ("Getafe", "A"),
            ("Aarhus", "H"), ("Mjallby AIF", "A"),
        ],
        "FC Thun": [
            ("Gent", "H"), ("Ajax", "A"),
            ("Heart Of Midlothian", "H"), ("Twente", "A"),
            ("HNK Hajduk Split", "H"), ("CSKA Sofia", "A"),
        ],
        "CSKA Sofia": [
            ("Monaco", "H"), ("Panathinaikos", "A"),
            ("Trabzonspor", "H"), ("KuPS", "A"),
            ("FC Thun", "H"), ("FC Nordsjaelland", "A"),
        ],
        "Kauno Žalgiris": [
            ("SC Freiburg", "H"), ("Brighton", "A"),
            ("Brann", "H"), ("FC Lugano", "A"),
            ("Riga", "H"), ("Egnatia Rrogozhinë", "A"),
        ],
        "Mjallby AIF": [
            ("Pafos", "H"), ("Atalanta", "A"),
            ("Borac Banja Luka", "H"), ("Kairat Almaty", "A"),
            ("Inter Club d'Escaldes", "H"), ("FC Iberia 1999", "A"),
        ],
        "FC Iberia 1999": [
            ("FK Crvena Zvezda", "H"), ("FC Copenhagen", "A"),
            ("Getafe", "H"), ("St. Truiden", "A"),
            ("Mjallby AIF", "H"), ("FK Jablonec", "A"),
        ],
        "Egnatia Rrogozhinë": [
            ("FC Midtjylland", "H"), ("SC Braga", "A"),
            ("Lincoln Red Imps FC", "H"), ("Universitatea Craiova", "A"),
            ("Kauno Žalgiris", "H"), ("Aarhus", "A"),
        ],
    },
}


def _resolve_home_by_edge(comp_name: str) -> dict[frozenset, str]:
    """{frozenset({team_a, team_b}): home_team} for every match implied by
    the opponent lists entered so far. First mention of a pairing wins if
    both sides happen to be entered and (incorrectly) disagree."""
    home_by_edge: dict[frozenset, str] = {}
    for team, opponents in LEAGUE_PHASE_OPPONENTS.get(comp_name, {}).items():
        for opp, venue in opponents:
            edge = frozenset({team, opp})
            home = team if venue == "H" else opp
            home_by_edge.setdefault(edge, home)
    return home_by_edge


def is_opponent_list_complete(comp_name: str, field_teams: list[str]) -> bool:
    """True once derive_fixtures() would produce a full, valid schedule:
    every one of the competition's field clubs has exactly the right
    number of distinct opponents, all of them also field clubs."""
    n_needed = LEAGUE_PHASE_OPPONENT_COUNT.get(comp_name, 0)
    edges = _resolve_home_by_edge(comp_name)
    if n_needed <= 0 or not edges:
        return False
    valid = set(field_teams)
    degree = {t: 0 for t in field_teams}
    for edge in edges:
        for t in edge:
            if t not in valid:
                return False
            degree[t] += 1
    return all(d == n_needed for d in degree.values())


def partial_opponents_by_team(comp_name: str) -> dict[str, list[str]]:
    """{team: [opponent, ...]} for every team whose full opponent count is
    already known from the lists entered so far (exactly
    LEAGUE_PHASE_OPPONENT_COUNT distinct opponents) -- lets a
    fixture-difficulty ranking grow incrementally, club by club, rather
    than waiting for the whole competition to be filled in."""
    n_needed = LEAGUE_PHASE_OPPONENT_COUNT.get(comp_name, 0)
    opponents: dict[str, set[str]] = {}
    for edge in _resolve_home_by_edge(comp_name):
        a, b = tuple(edge)
        opponents.setdefault(a, set()).add(b)
        opponents.setdefault(b, set()).add(a)
    return {t: sorted(opps) for t, opps in opponents.items() if len(opps) == n_needed}


def derive_fixtures(comp_name: str) -> list[dict]:
    """The real fixture list as [{"strHomeTeam", "strAwayTeam"}, ...],
    with real home/away legs from the entered opponent lists."""
    fixtures = []
    for edge, home in sorted(_resolve_home_by_edge(comp_name).items(), key=lambda kv: sorted(kv[0])):
        away = next(t for t in edge if t != home)
        fixtures.append({"strHomeTeam": home, "strAwayTeam": away})
    return fixtures


# ---------------------------------------------------------------------------
# Real matchday-dated schedule -- UEFA's own published calendar (matchday
# number, date, kickoff time), once available. Purely a display layer:
# every (home, away) pair here has already been cross-checked to match
# derive_fixtures() above exactly, which stays the source of truth the
# simulation actually runs on. Empty for a competition until its dated
# calendar is entered.
_CL_DATED_SCHEDULE_RAW: list[tuple[int, str, str, str, str]] = [
    (1, "2026-09-08", "18:45", "AEK Athens FC", "Lask Linz"),
    (1, "2026-09-08", "18:45", "Club Brugge", "Aston Villa"),
    (1, "2026-09-08", "21:00", "Borussia Dortmund", "Villarreal"),
    (1, "2026-09-08", "21:00", "Porto", "Manchester City"),
    (1, "2026-09-08", "21:00", "Lille", "Real Betis"),
    (1, "2026-09-08", "21:00", "Real Madrid", "Inter Milan"),
    (1, "2026-09-09", "18:45", "Barcelona", "Feyenoord"),
    (1, "2026-09-09", "18:45", "VfB Stuttgart", "Viking"),
    (1, "2026-09-09", "21:00", "Liverpool", "Atlético Madrid"),
    (1, "2026-09-09", "21:00", "Paris Saint-Germain", "Slovan Bratislava"),
    (1, "2026-09-09", "21:00", "Sporting CP", "Galatasaray"),
    (1, "2026-09-09", "21:00", "Napoli", "Arsenal"),
    (1, "2026-09-10", "18:45", "Fenerbahçe", "Roma"),
    (1, "2026-09-10", "18:45", "PSV Eindhoven", "Shakhtar Donetsk"),
    (1, "2026-09-10", "21:00", "Como", "RB Leipzig"),
    (1, "2026-09-10", "21:00", "Bayern Munich", "Bodo/Glimt"),
    (1, "2026-09-10", "21:00", "Manchester United", "Sabah FA"),
    (1, "2026-09-10", "21:00", "Slavia Prague", "Lens"),

    (2, "2026-10-13", "18:45", "Lens", "Sporting CP"),
    (2, "2026-10-13", "18:45", "Sabah FA", "Slavia Prague"),
    (2, "2026-10-13", "21:00", "Arsenal", "Lille"),
    (2, "2026-10-13", "21:00", "Atlético Madrid", "Manchester United"),
    (2, "2026-10-13", "21:00", "Inter Milan", "Club Brugge"),
    (2, "2026-10-13", "21:00", "Galatasaray", "Barcelona"),
    (2, "2026-10-13", "21:00", "RB Leipzig", "PSV Eindhoven"),
    (2, "2026-10-13", "21:00", "Viking", "Bayern Munich"),
    (2, "2026-10-13", "21:00", "Villarreal", "Napoli"),
    (2, "2026-10-14", "18:45", "Feyenoord", "Como"),
    (2, "2026-10-14", "18:45", "Lask Linz", "Liverpool"),
    (2, "2026-10-14", "21:00", "Roma", "Real Madrid"),
    (2, "2026-10-14", "21:00", "Aston Villa", "Fenerbahçe"),
    (2, "2026-10-14", "21:00", "Shakhtar Donetsk", "AEK Athens FC"),
    (2, "2026-10-14", "21:00", "Bodo/Glimt", "Borussia Dortmund"),
    (2, "2026-10-14", "21:00", "Manchester City", "Paris Saint-Germain"),
    (2, "2026-10-14", "21:00", "Real Betis", "Porto"),
    (2, "2026-10-14", "21:00", "Slovan Bratislava", "VfB Stuttgart"),

    (3, "2026-10-20", "18:45", "Fenerbahçe", "Slavia Prague"),
    (3, "2026-10-20", "18:45", "Sabah FA", "Borussia Dortmund"),
    (3, "2026-10-20", "21:00", "Roma", "Slovan Bratislava"),
    (3, "2026-10-20", "21:00", "Porto", "PSV Eindhoven"),
    (3, "2026-10-20", "21:00", "Liverpool", "Villarreal"),
    (3, "2026-10-20", "21:00", "Manchester City", "AEK Athens FC"),
    (3, "2026-10-20", "21:00", "Paris Saint-Germain", "Barcelona"),
    (3, "2026-10-20", "21:00", "Napoli", "Bodo/Glimt"),
    (3, "2026-10-20", "21:00", "VfB Stuttgart", "Atlético Madrid"),
    (3, "2026-10-21", "18:45", "Como", "Manchester United"),
    (3, "2026-10-21", "18:45", "Lille", "Galatasaray"),
    (3, "2026-10-21", "21:00", "Aston Villa", "Viking"),
    (3, "2026-10-21", "21:00", "Club Brugge", "Lens"),
    (3, "2026-10-21", "21:00", "Bayern Munich", "Arsenal"),
    (3, "2026-10-21", "21:00", "Inter Milan", "Shakhtar Donetsk"),
    (3, "2026-10-21", "21:00", "Real Madrid", "RB Leipzig"),
    (3, "2026-10-21", "21:00", "Real Betis", "Feyenoord"),
    (3, "2026-10-21", "21:00", "Sporting CP", "Lask Linz"),

    (4, "2026-11-03", "18:45", "Shakhtar Donetsk", "Sporting CP"),
    (4, "2026-11-03", "18:45", "Galatasaray", "VfB Stuttgart"),
    (4, "2026-11-03", "21:00", "Atlético Madrid", "Bayern Munich"),
    (4, "2026-11-03", "21:00", "Barcelona", "Aston Villa"),
    (4, "2026-11-03", "21:00", "Feyenoord", "Inter Milan"),
    (4, "2026-11-03", "21:00", "Bodo/Glimt", "Lille"),
    (4, "2026-11-03", "21:00", "Lask Linz", "Slovan Bratislava"),
    (4, "2026-11-03", "21:00", "Manchester United", "Roma"),
    (4, "2026-11-03", "21:00", "Villarreal", "Paris Saint-Germain"),
    (4, "2026-11-04", "18:45", "AEK Athens FC", "Real Madrid"),
    (4, "2026-11-04", "18:45", "Fenerbahçe", "Liverpool"),
    (4, "2026-11-04", "21:00", "Borussia Dortmund", "Real Betis"),
    (4, "2026-11-04", "21:00", "Porto", "Napoli"),
    (4, "2026-11-04", "21:00", "PSV Eindhoven", "Club Brugge"),
    (4, "2026-11-04", "21:00", "RB Leipzig", "Manchester City"),
    (4, "2026-11-04", "21:00", "Lens", "Como"),
    (4, "2026-11-04", "21:00", "Slavia Prague", "Arsenal"),
    (4, "2026-11-04", "21:00", "Viking", "Sabah FA"),

    (5, "2026-11-24", "18:45", "Bodo/Glimt", "Lask Linz"),
    (5, "2026-11-24", "18:45", "Galatasaray", "Aston Villa"),
    (5, "2026-11-24", "21:00", "Arsenal", "Borussia Dortmund"),
    (5, "2026-11-24", "21:00", "Como", "AEK Athens FC"),
    (5, "2026-11-24", "21:00", "Feyenoord", "Porto"),
    (5, "2026-11-24", "21:00", "Manchester City", "Napoli"),
    (5, "2026-11-24", "21:00", "RB Leipzig", "Lens"),
    (5, "2026-11-24", "21:00", "Real Madrid", "PSV Eindhoven"),
    (5, "2026-11-24", "21:00", "Slovan Bratislava", "Real Betis"),
    (5, "2026-11-25", "18:45", "Sabah FA", "Barcelona"),
    (5, "2026-11-25", "18:45", "Slavia Prague", "Villarreal"),
    (5, "2026-11-25", "21:00", "Atlético Madrid", "Viking"),
    (5, "2026-11-25", "21:00", "Club Brugge", "Liverpool"),
    (5, "2026-11-25", "21:00", "Inter Milan", "VfB Stuttgart"),
    (5, "2026-11-25", "21:00", "Shakhtar Donetsk", "Fenerbahçe"),
    (5, "2026-11-25", "21:00", "Lille", "Bayern Munich"),
    (5, "2026-11-25", "21:00", "Paris Saint-Germain", "Roma"),
    (5, "2026-11-25", "21:00", "Sporting CP", "Manchester United"),

    (6, "2026-12-08", "18:45", "Viking", "Feyenoord"),
    (6, "2026-12-08", "18:45", "Villarreal", "Sabah FA"),
    (6, "2026-12-08", "21:00", "AEK Athens FC", "Galatasaray"),
    (6, "2026-12-08", "21:00", "Roma", "Sporting CP"),
    (6, "2026-12-08", "21:00", "Aston Villa", "Paris Saint-Germain"),
    (6, "2026-12-08", "21:00", "Barcelona", "Manchester City"),
    (6, "2026-12-08", "21:00", "Bayern Munich", "Slavia Prague"),
    (6, "2026-12-08", "21:00", "Manchester United", "RB Leipzig"),
    (6, "2026-12-08", "21:00", "Napoli", "Club Brugge"),
    (6, "2026-12-09", "18:45", "Real Betis", "Como"),
    (6, "2026-12-09", "18:45", "Slovan Bratislava", "Shakhtar Donetsk"),
    (6, "2026-12-09", "21:00", "Arsenal", "Real Madrid"),
    (6, "2026-12-09", "21:00", "Borussia Dortmund", "Inter Milan"),
    (6, "2026-12-09", "21:00", "Lask Linz", "Fenerbahçe"),
    (6, "2026-12-09", "21:00", "Liverpool", "Porto"),
    (6, "2026-12-09", "21:00", "PSV Eindhoven", "Atlético Madrid"),
    (6, "2026-12-09", "21:00", "Lens", "Bodo/Glimt"),
    (6, "2026-12-09", "21:00", "VfB Stuttgart", "Lille"),

    (7, "2027-01-19", "18:45", "Bodo/Glimt", "Atlético Madrid"),
    (7, "2027-01-19", "18:45", "Galatasaray", "Feyenoord"),
    (7, "2027-01-19", "21:00", "AEK Athens FC", "Roma"),
    (7, "2027-01-19", "21:00", "Aston Villa", "Borussia Dortmund"),
    (7, "2027-01-19", "21:00", "Inter Milan", "Liverpool"),
    (7, "2027-01-19", "21:00", "Porto", "Slavia Prague"),
    (7, "2027-01-19", "21:00", "Lille", "Slovan Bratislava"),
    (7, "2027-01-19", "21:00", "Real Madrid", "Lask Linz"),
    (7, "2027-01-19", "21:00", "VfB Stuttgart", "Club Brugge"),
    (7, "2027-01-20", "18:45", "Fenerbahçe", "Villarreal"),
    (7, "2027-01-20", "18:45", "Sabah FA", "Napoli"),
    (7, "2027-01-20", "21:00", "Como", "Paris Saint-Germain"),
    (7, "2027-01-20", "21:00", "Manchester United", "Bayern Munich"),
    (7, "2027-01-20", "21:00", "RB Leipzig", "Shakhtar Donetsk"),
    (7, "2027-01-20", "21:00", "Lens", "Manchester City"),
    (7, "2027-01-20", "21:00", "Real Betis", "Arsenal"),
    (7, "2027-01-20", "21:00", "Sporting CP", "Barcelona"),
    (7, "2027-01-20", "21:00", "Viking", "PSV Eindhoven"),

    (8, "2027-01-27", "21:00", "Arsenal", "Sabah FA"),
    (8, "2027-01-27", "21:00", "Roma", "Lille"),
    (8, "2027-01-27", "21:00", "Atlético Madrid", "Fenerbahçe"),
    (8, "2027-01-27", "21:00", "Borussia Dortmund", "AEK Athens FC"),
    (8, "2027-01-27", "21:00", "Club Brugge", "Bodo/Glimt"),
    (8, "2027-01-27", "21:00", "Bayern Munich", "Real Betis"),
    (8, "2027-01-27", "21:00", "Barcelona", "Como"),
    (8, "2027-01-27", "21:00", "Shakhtar Donetsk", "Real Madrid"),
    (8, "2027-01-27", "21:00", "Feyenoord", "RB Leipzig"),
    (8, "2027-01-27", "21:00", "Lask Linz", "Porto"),
    (8, "2027-01-27", "21:00", "Liverpool", "Lens"),
    (8, "2027-01-27", "21:00", "Manchester City", "Sporting CP"),
    (8, "2027-01-27", "21:00", "Paris Saint-Germain", "Galatasaray"),
    (8, "2027-01-27", "21:00", "PSV Eindhoven", "VfB Stuttgart"),
    (8, "2027-01-27", "21:00", "Slavia Prague", "Aston Villa"),
    (8, "2027-01-27", "21:00", "Napoli", "Viking"),
    (8, "2027-01-27", "21:00", "Villarreal", "Manchester United"),
    (8, "2027-01-27", "21:00", "Slovan Bratislava", "Inter Milan"),
]

LEAGUE_PHASE_DATED_SCHEDULE: dict[str, list[dict]] = {
    "Champions League": [
        {"matchday": md, "date": d, "time": t, "home": h, "away": a}
        for md, d, t, h, a in _CL_DATED_SCHEDULE_RAW
    ],
    "Europa League": [],
    "Conference League": [],
}


def dated_schedule(comp_name: str) -> list[dict]:
    """The real matchday-dated schedule for a competition, or [] if it
    hasn't been entered yet (fall back to derive_fixtures() for the
    fixture list itself, which has no matchday/date info)."""
    return LEAGUE_PHASE_DATED_SCHEDULE.get(comp_name, [])
