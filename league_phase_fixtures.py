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
