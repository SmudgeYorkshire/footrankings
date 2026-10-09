"""
2027/28 UEFA European Competition access list.

Source: hand-verified by the user against UEFA circular 54/2026
(enclosure 2, 9 September 2026) and current coefficient-driven
expectations -- this supersedes an earlier draft of this file built by
pixel-parsing the PDF directly, which got some qualifying-round detail
right but missed real-world context a flat column scrape can't carry
(this season's predicted European Performance Spot recipients, and
how Russia's ongoing suspension redistributes the slots it would
otherwise occupy). Treat this version as the authoritative one.

No club names here -- the 2026/27 domestic season that determines
every one of these slots won't finish until roughly May/June 2027, so
every slot is genuinely undetermined this far out. european_2027_28.py
resolves each entry's `route` against the relevant domestic league's
CURRENT standings live, instead of baking a snapshot into this file.

Each access-list entry:
  country  -- matches config.LEAGUES' own country spelling
  league   -- this site's LEAGUES dict key (None for Liechtenstein,
              which has no tracked domestic top flight)
  code     -- which domestic finishing position or the cup winner:
              CH/N2/N3/N4/N5/N6/N7 (league position) or CW (cup winner)
  route    -- human label for that code (e.g. "League 3rd")
  label    -- UEFA's own short-hand (e.g. "CL-Q2", "EL-LS", "CO-PO"):
              CL/EL/CO = Champions/Europa/Conference League; LS = direct
              to the 36-team League Phase; PO/Q1/Q2/Q3 = qualifying
              round; a "Q2nc"/"Q3nc" suffix (Champions League only)
              marks the League Path (the non-champions route) rather
              than the Champions Path
  path     -- "Direct", "Champions Path" / "League Path" (Champions
              League only -- see circular's own split), or "Qualifying"
              (Europa/Conference League, which the circular confirms
              also split into champions/main paths from 2027/28, not
              modelled as a separate field here since no entry below
              needed the distinction to resolve a specific round)
  round    -- the qualifying round in full ("First qualifying round",
              ..., "Play-off round", or "League Phase (direct)")
  note     -- present only on entries where the plain position-based
              rule doesn't give the full picture (see below)

Two things layered on top of the official allocation, both flagged via
each affected entry's `note` field rather than silently assumed:

  - England and Germany are predicted (not yet confirmed by UEFA) to
    receive 2027/28's 2 "European Performance Spot" bonus places --
    awarded after 2026/27 ends to whichever 2 associations have the
    best aggregate CLUB coefficient that season, not fixed in the
    access-list circular itself. Modelled as a 5th direct League Phase
    slot (League 5th) for each of those two countries; if a different
    association ends up with the EPS place instead, that slot moves
    with it.
  - Russia remains suspended from UEFA competitions (Executive
    Committee decision, 28 February 2022, still in force). Russia's
    own access-list slots are kept here for completeness but flagged
    as unoccupied, and the slot immediately above each of Russia's
    cascade points is promoted up one round to absorb the vacancy:
    Ukraine's champion CL-Q1 -> CL-Q2, Switzerland's cup winner
    EL-Q1 -> EL-Q2, and the cup winners of Latvia, Faroe Islands,
    Malta, Liechtenstein, Estonia and Albania CO-Q1 -> CO-Q2.

Not modelled at all (truly unknowable this far out, no placeholder
entry): UCL/UEL defending-titleholder byes (CL-TH/EL-TH -> League
Phase direct) and the Conference League titleholder's promotion
(CO-TH -> EL-LS) -- all three depend on who wins the actual 2026/27
finals.

Last updated: 2026-10-05
"""

import functools

ACCESS_LIST_2027_28 = {
    "Champions League": [
        {"country": 'Italy', "league": 'Italian Serie A', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Italy', "league": 'Italian Serie A', "code": 'N2', "route": 'League 2nd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Italy', "league": 'Italian Serie A', "code": 'N3', "route": 'League 3rd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Italy', "league": 'Italian Serie A', "code": 'N4', "route": 'League 4th', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Spain', "league": 'Spanish La Liga', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Spain', "league": 'Spanish La Liga', "code": 'N2', "route": 'League 2nd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Spain', "league": 'Spanish La Liga', "code": 'N3', "route": 'League 3rd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Spain', "league": 'Spanish La Liga', "code": 'N4', "route": 'League 4th', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'England', "league": 'English Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'England', "league": 'English Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'England', "league": 'English Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'England', "league": 'English Premier League', "code": 'N4', "route": 'League 4th', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'England', "league": 'English Premier League', "code": 'N5', "route": 'League 5th', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)', "note": 'Predicted EPS recipient, not yet confirmed by UEFA -- this slot only exists if that holds'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'N2', "route": 'League 2nd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'N3', "route": 'League 3rd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'N4', "route": 'League 4th', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'N5', "route": 'League 5th', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)', "note": 'Predicted EPS recipient, not yet confirmed by UEFA -- this slot only exists if that holds'},
        {"country": 'France', "league": 'French Ligue 1', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'France', "league": 'French Ligue 1', "code": 'N2', "route": 'League 2nd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'France', "league": 'French Ligue 1', "code": 'N3', "route": 'League 3rd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'France', "league": 'French Ligue 1', "code": 'N4', "route": 'League 4th', "label": 'CL-Q3nc', "path": 'League Path', "round": 'Third qualifying round'},
        {"country": 'Portugal', "league": 'Portuguese Primeira Liga', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Portugal', "league": 'Portuguese Primeira Liga', "code": 'N2', "route": 'League 2nd', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Portugal', "league": 'Portuguese Primeira Liga', "code": 'N3', "route": 'League 3rd', "label": 'CL-Q3nc', "path": 'League Path', "round": 'Third qualifying round'},
        {"country": 'Netherlands', "league": 'Dutch Eredivisie', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Netherlands', "league": 'Dutch Eredivisie', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q3nc', "path": 'League Path', "round": 'Third qualifying round'},
        {"country": 'Belgium', "league": 'Belgian Pro League', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Belgium', "league": 'Belgian Pro League', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q3nc', "path": 'League Path', "round": 'Third qualifying round'},
        {"country": 'Turkey', "league": 'Turkish Super Lig', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Turkey', "league": 'Turkish Super Lig', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q3nc', "path": 'League Path', "round": 'Third qualifying round'},
        {"country": 'Czech Rep.', "league": 'Czech First League', "code": 'CH', "route": 'League champion', "label": 'CL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Czech Rep.', "league": 'Czech First League', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q2nc', "path": 'League Path', "round": 'Second qualifying round'},
        {"country": 'Greece', "league": 'Greek Super League 1', "code": 'CH', "route": 'League champion', "label": 'CL-PO', "path": 'Champions Path', "round": 'Play-off round'},
        {"country": 'Greece', "league": 'Greek Super League 1', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q2nc', "path": 'League Path', "round": 'Second qualifying round'},
        {"country": 'Poland', "league": 'Polish Ekstraklasa', "code": 'CH', "route": 'League champion', "label": 'CL-PO', "path": 'Champions Path', "round": 'Play-off round'},
        {"country": 'Poland', "league": 'Polish Ekstraklasa', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q2nc', "path": 'League Path', "round": 'Second qualifying round'},
        {"country": 'Denmark', "league": 'Danish Superliga', "code": 'CH', "route": 'League champion', "label": 'CL-PO', "path": 'Champions Path', "round": 'Play-off round'},
        {"country": 'Denmark', "league": 'Danish Superliga', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q2nc', "path": 'League Path', "round": 'Second qualifying round'},
        {"country": 'Norway', "league": 'Norwegian Eliteserien', "code": 'CH', "route": 'League champion', "label": 'CL-PO', "path": 'Champions Path', "round": 'Play-off round'},
        {"country": 'Norway', "league": 'Norwegian Eliteserien', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q2nc', "path": 'League Path', "round": 'Second qualifying round'},
        {"country": 'Cyprus', "league": 'Cypriot First Division', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Cyprus', "league": 'Cypriot First Division', "code": 'N2', "route": 'League 2nd', "label": 'CL-Q2nc', "path": 'League Path', "round": 'Second qualifying round'},
        {"country": 'Switzerland', "league": 'Swiss Super League', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Austria', "league": 'Austrian Bundesliga', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Scotland', "league": 'Scottish Premiership', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Sweden', "league": 'Swedish Allsvenskan', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Croatia', "league": 'Croatian First Football League', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Israel', "league": 'Israeli Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Hungary', "league": 'Hungarian NB I', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round'},
        {"country": 'Ukraine', "league": 'Ukrainian Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q2', "path": 'Champions Path', "round": 'Second qualifying round', "note": 'Promoted CL-Q1 -> CL-Q2: Russia ban vacates a slot above it'},
        {"country": 'Serbia', "league": 'Serbian Super Liga', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Romania', "league": 'Romanian Liga I', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Slovenia', "league": 'Slovenian 1. SNL', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Azerbaijan', "league": 'Azerbaijani Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Slovakia', "league": 'Slovak First Football League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Russia', "league": 'Russian Football Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round', "note": 'Suspended from UEFA competitions until further notice (Executive Committee, 28 Feb 2022) -- slot redistributed, no Russian club will actually occupy it'},
        {"country": 'Bulgaria', "league": 'Bulgarian First League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Ireland', "league": 'Irish Premier Division', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Iceland', "league": 'Icelandic Besta deild karla', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Armenia', "league": 'Armenian Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Moldova', "league": 'Moldovan National Division', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Finland', "league": 'Finnish Veikkausliiga', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Kosovo', "league": 'Kosovan Superleague', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Kazakhstan', "league": 'Kazakhstan Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Bosnia', "league": 'Bosnian Premier Liga', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Latvia', "league": 'Latvian Higher League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Faroe Isl.', "league": 'Faroe Islands Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Malta', "league": 'Maltese Premier League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Estonia', "league": 'Estonian Meistriliiga', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Albania', "league": 'Albanian Superliga', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'N. Macedonia', "league": 'Macedonian First League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Lithuania', "league": 'Lithuanian TOPLYGA', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'N. Ireland', "league": 'Northern Irish Premiership', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Gibraltar', "league": 'Gibraltarian National League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Andorra', "league": 'Andorran 1a Divisió', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Belarus', "league": 'Belarus Vyscha Liga', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Luxembourg', "league": 'Luxembourg National Division', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Montenegro', "league": 'Montenegrin First League', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Georgia', "league": 'Georgian Erovnuli Liga', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'Wales', "league": 'Welsh Cymru Premier', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
        {"country": 'San Marino', "league": 'San-Marino Campionato', "code": 'CH', "route": 'League champion', "label": 'CL-Q1', "path": 'Champions Path', "round": 'First qualifying round'},
    ],
    "Europa League": [
        {"country": 'Italy', "league": 'Italian Serie A', "code": 'CW', "route": 'Cup winner', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Italy', "league": 'Italian Serie A', "code": 'N5', "route": 'League 5th', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Spain', "league": 'Spanish La Liga', "code": 'CW', "route": 'Cup winner', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Spain', "league": 'Spanish La Liga', "code": 'N5', "route": 'League 5th', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'England', "league": 'English Premier League', "code": 'CW', "route": 'Cup winner', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'England', "league": 'English Premier League', "code": 'N6', "route": 'League 6th', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'CW', "route": 'Cup winner', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'N6', "route": 'League 6th', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'France', "league": 'French Ligue 1', "code": 'CW', "route": 'Cup winner', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'France', "league": 'French Ligue 1', "code": 'N5', "route": 'League 5th', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Portugal', "league": 'Portuguese Primeira Liga', "code": 'CW', "route": 'Cup winner', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Portugal', "league": 'Portuguese Primeira Liga', "code": 'N4', "route": 'League 4th', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Netherlands', "league": 'Dutch Eredivisie', "code": 'CW', "route": 'Cup winner', "label": 'EL-LS', "path": 'Direct', "round": 'League Phase (direct)'},
        {"country": 'Netherlands', "league": 'Dutch Eredivisie', "code": 'N3', "route": 'League 3rd', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Belgium', "league": 'Belgian Pro League', "code": 'CW', "route": 'Cup winner', "label": 'EL-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Belgium', "league": 'Belgian Pro League', "code": 'N3', "route": 'League 3rd', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Turkey', "league": 'Turkish Super Lig', "code": 'CW', "route": 'Cup winner', "label": 'EL-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Turkey', "league": 'Turkish Super Lig', "code": 'N3', "route": 'League 3rd', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Czech Rep.', "league": 'Czech First League', "code": 'CW', "route": 'Cup winner', "label": 'EL-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Czech Rep.', "league": 'Czech First League', "code": 'N3', "route": 'League 3rd', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Greece', "league": 'Greek Super League 1', "code": 'CW', "route": 'Cup winner', "label": 'EL-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Greece', "league": 'Greek Super League 1', "code": 'N3', "route": 'League 3rd', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Poland', "league": 'Polish Ekstraklasa', "code": 'CW', "route": 'Cup winner', "label": 'EL-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Poland', "league": 'Polish Ekstraklasa', "code": 'N3', "route": 'League 3rd', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Denmark', "league": 'Danish Superliga', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q3', "path": 'Qualifying', "round": 'Third qualifying round'},
        {"country": 'Norway', "league": 'Norwegian Eliteserien', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q3', "path": 'Qualifying', "round": 'Third qualifying round'},
        {"country": 'Cyprus', "league": 'Cypriot First Division', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q3', "path": 'Qualifying', "round": 'Third qualifying round'},
        {"country": 'Switzerland', "league": 'Swiss Super League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Promoted EL-Q1 -> EL-Q2: Russia ban vacates a slot above it'},
        {"country": 'Austria', "league": 'Austrian Bundesliga', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Scotland', "league": 'Scottish Premiership', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Sweden', "league": 'Swedish Allsvenskan', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Croatia', "league": 'Croatian First Football League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Israel', "league": 'Israeli Premier League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Hungary', "league": 'Hungarian NB I', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Ukraine', "league": 'Ukrainian Premier League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Serbia', "league": 'Serbian Super Liga', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Romania', "league": 'Romanian Liga I', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Slovenia', "league": 'Slovenian 1. SNL', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Azerbaijan', "league": 'Azerbaijani Premier League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Slovakia', "league": 'Slovak First Football League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Russia', "league": 'Russian Football Premier League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round', "note": 'Suspended from UEFA competitions until further notice (Executive Committee, 28 Feb 2022) -- slot redistributed, no Russian club will actually occupy it'},
        {"country": 'Bulgaria', "league": 'Bulgarian First League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Ireland', "league": 'Irish Premier Division', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Iceland', "league": 'Icelandic Besta deild karla', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Armenia', "league": 'Armenian Premier League', "code": 'CW', "route": 'Cup winner', "label": 'EL-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
    ],
    "Conference League": [
        {"country": 'Italy', "league": 'Italian Serie A', "code": 'N6', "route": 'League 6th', "label": 'CO-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Spain', "league": 'Spanish La Liga', "code": 'N6', "route": 'League 6th', "label": 'CO-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'England', "league": 'English Premier League', "code": 'N7', "route": 'League 7th', "label": 'CO-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Germany', "league": 'German Bundesliga', "code": 'N7', "route": 'League 7th', "label": 'CO-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'France', "league": 'French Ligue 1', "code": 'N6', "route": 'League 6th', "label": 'CO-PO', "path": 'Qualifying', "round": 'Play-off round'},
        {"country": 'Portugal', "league": 'Portuguese Primeira Liga', "code": 'N5', "route": 'League 5th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Netherlands', "league": 'Dutch Eredivisie', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Belgium', "league": 'Belgian Pro League', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Turkey', "league": 'Turkish Super Lig', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Czech Rep.', "league": 'Czech First League', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Greece', "league": 'Greek Super League 1', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Poland', "league": 'Polish Ekstraklasa', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Denmark', "league": 'Danish Superliga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Denmark', "league": 'Danish Superliga', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Norway', "league": 'Norwegian Eliteserien', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Norway', "league": 'Norwegian Eliteserien', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Cyprus', "league": 'Cypriot First Division', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Cyprus', "league": 'Cypriot First Division', "code": 'N4', "route": 'League 4th', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Switzerland', "league": 'Swiss Super League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Switzerland', "league": 'Swiss Super League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Austria', "league": 'Austrian Bundesliga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Austria', "league": 'Austrian Bundesliga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Scotland', "league": 'Scottish Premiership', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Scotland', "league": 'Scottish Premiership', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Sweden', "league": 'Swedish Allsvenskan', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Sweden', "league": 'Swedish Allsvenskan', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Croatia', "league": 'Croatian First Football League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Croatia', "league": 'Croatian First Football League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Israel', "league": 'Israeli Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Israel', "league": 'Israeli Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Hungary', "league": 'Hungarian NB I', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Hungary', "league": 'Hungarian NB I', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Ukraine', "league": 'Ukrainian Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Ukraine', "league": 'Ukrainian Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Serbia', "league": 'Serbian Super Liga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Serbia', "league": 'Serbian Super Liga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Romania', "league": 'Romanian Liga I', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Romania', "league": 'Romanian Liga I', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Slovenia', "league": 'Slovenian 1. SNL', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Slovenia', "league": 'Slovenian 1. SNL', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Azerbaijan', "league": 'Azerbaijani Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Azerbaijan', "league": 'Azerbaijani Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Slovakia', "league": 'Slovak First Football League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Slovakia', "league": 'Slovak First Football League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Russia', "league": 'Russian Football Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Suspended from UEFA competitions until further notice (Executive Committee, 28 Feb 2022) -- slot redistributed, no Russian club will actually occupy it'},
        {"country": 'Russia', "league": 'Russian Football Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Suspended from UEFA competitions until further notice (Executive Committee, 28 Feb 2022) -- slot redistributed, no Russian club will actually occupy it'},
        {"country": 'Bulgaria', "league": 'Bulgarian First League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Bulgaria', "league": 'Bulgarian First League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Ireland', "league": 'Irish Premier Division', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Ireland', "league": 'Irish Premier Division', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Iceland', "league": 'Icelandic Besta deild karla', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Iceland', "league": 'Icelandic Besta deild karla', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Armenia', "league": 'Armenian Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Armenia', "league": 'Armenian Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Moldova', "league": 'Moldovan National Division', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Moldova', "league": 'Moldovan National Division', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Moldova', "league": 'Moldovan National Division', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Finland', "league": 'Finnish Veikkausliiga', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Finland', "league": 'Finnish Veikkausliiga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Finland', "league": 'Finnish Veikkausliiga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Kosovo', "league": 'Kosovan Superleague', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Kosovo', "league": 'Kosovan Superleague', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Kosovo', "league": 'Kosovan Superleague', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Kazakhstan', "league": 'Kazakhstan Premier League', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Kazakhstan', "league": 'Kazakhstan Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Kazakhstan', "league": 'Kazakhstan Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Bosnia', "league": 'Bosnian Premier Liga', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round'},
        {"country": 'Bosnia', "league": 'Bosnian Premier Liga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Bosnia', "league": 'Bosnian Premier Liga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Latvia', "league": 'Latvian Higher League', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Promoted CO-Q1 -> CO-Q2: Russia ban vacates a slot above it'},
        {"country": 'Latvia', "league": 'Latvian Higher League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Latvia', "league": 'Latvian Higher League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Faroe Isl.', "league": 'Faroe Islands Premier League', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Promoted CO-Q1 -> CO-Q2: Russia ban vacates a slot above it'},
        {"country": 'Faroe Isl.', "league": 'Faroe Islands Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Faroe Isl.', "league": 'Faroe Islands Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Malta', "league": 'Maltese Premier League', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Promoted CO-Q1 -> CO-Q2: Russia ban vacates a slot above it'},
        {"country": 'Malta', "league": 'Maltese Premier League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Malta', "league": 'Maltese Premier League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Estonia', "league": 'Estonian Meistriliiga', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Promoted CO-Q1 -> CO-Q2: Russia ban vacates a slot above it'},
        {"country": 'Estonia', "league": 'Estonian Meistriliiga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Estonia', "league": 'Estonian Meistriliiga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Albania', "league": 'Albanian Superliga', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Promoted CO-Q1 -> CO-Q2: Russia ban vacates a slot above it'},
        {"country": 'Albania', "league": 'Albanian Superliga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Albania', "league": 'Albanian Superliga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Liechtenstein', "league": None, "code": 'CW', "route": 'Cup winner', "label": 'CO-Q2', "path": 'Qualifying', "round": 'Second qualifying round', "note": 'Promoted CO-Q1 -> CO-Q2: Russia ban vacates a slot above it (no domestic league champion -- no tracked top flight)'},
        {"country": 'N. Macedonia', "league": 'Macedonian First League', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'N. Macedonia', "league": 'Macedonian First League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'N. Macedonia', "league": 'Macedonian First League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Lithuania', "league": 'Lithuanian TOPLYGA', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Lithuania', "league": 'Lithuanian TOPLYGA', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Lithuania', "league": 'Lithuanian TOPLYGA', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'N. Ireland', "league": 'Northern Irish Premiership', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'N. Ireland', "league": 'Northern Irish Premiership', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'N. Ireland', "league": 'Northern Irish Premiership', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Gibraltar', "league": 'Gibraltarian National League', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Gibraltar', "league": 'Gibraltarian National League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Gibraltar', "league": 'Gibraltarian National League', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Andorra', "league": 'Andorran 1a Divisió', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Andorra', "league": 'Andorran 1a Divisió', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Andorra', "league": 'Andorran 1a Divisió', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Belarus', "league": 'Belarus Vyscha Liga', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Belarus', "league": 'Belarus Vyscha Liga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Belarus', "league": 'Belarus Vyscha Liga', "code": 'N3', "route": 'League 3rd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Luxembourg', "league": 'Luxembourg National Division', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Luxembourg', "league": 'Luxembourg National Division', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Montenegro', "league": 'Montenegrin First League', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Montenegro', "league": 'Montenegrin First League', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Georgia', "league": 'Georgian Erovnuli Liga', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Georgia', "league": 'Georgian Erovnuli Liga', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Wales', "league": 'Welsh Cymru Premier', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'Wales', "league": 'Welsh Cymru Premier', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'San Marino', "league": 'San-Marino Campionato', "code": 'CW', "route": 'Cup winner', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
        {"country": 'San Marino', "league": 'San-Marino Campionato', "code": 'N2', "route": 'League 2nd', "label": 'CO-Q1', "path": 'Qualifying', "round": 'First qualifying round'},
    ],
}

# UEFA circular 54/2026, enclosure 1: the 2027/28 international match
# calendar's qualifying-round leg dates (League Phase start date too,
# for reference -- not itself a qualifying round).
QUALIFYING_DATES_2027_28 = {
    "Champions League": {
        "First Qualifying Round":  {"leg1": "6/7 Jul 2027",   "leg2": "13/14 Jul 2027"},
        "Second Qualifying Round": {"leg1": "20/21 Jul 2027", "leg2": "27/28 Jul 2027"},
        "Third Qualifying Round":  {"leg1": "3/4 Aug 2027",   "leg2": "10 Aug 2027"},
        "Play-off Round":          {"leg1": "17/18 Aug 2027", "leg2": "24/25 Aug 2027"},
        "League Phase":            {"leg1": "7-9 Sep 2027",   "leg2": None},
    },
    "Europa League": {
        "First Qualifying Round":  {"leg1": "8 Jul 2027",     "leg2": "15 Jul 2027"},
        "Second Qualifying Round": {"leg1": "22 Jul 2027",    "leg2": "29 Jul 2027"},
        "Third Qualifying Round":  {"leg1": "5 Aug 2027",     "leg2": "12 Aug 2027"},
        "Play-off Round":          {"leg1": "19 Aug 2027",    "leg2": "26 Aug 2027"},
        "League Phase":            {"leg1": "15/16 Sep 2027", "leg2": None},
    },
    "Conference League": {
        "First Qualifying Round":  {"leg1": "8 Jul 2027",     "leg2": "15 Jul 2027"},
        "Second Qualifying Round": {"leg1": "22 Jul 2027",    "leg2": "29 Jul 2027"},
        "Third Qualifying Round":  {"leg1": "5 Aug 2027",     "leg2": "12 Aug 2027"},
        "Play-off Round":          {"leg1": "19 Aug 2027",    "leg2": "26 Aug 2027"},
        "League Phase":            {"leg1": "14 Oct 2027",    "leg2": None},
    },
}

# Display order, earliest round first.
STAGE_ORDER_2027_28 = [
    "First qualifying round",
    "Second qualifying round",
    "Third qualifying round",
    "Play-off round",
    "League Phase (direct)",
]


# ---------------------------------------------------------------------------
# Connecting this access list to league_status.py's current-season Status
# column, per explicit instruction (2026-10-09): ACCESS_LIST_2027_28 is the
# single source of truth for which European competition/round a league
# position or cup winner leads to, for BOTH "what does this season's Status
# column show" and "what does 2027/28 Projected Entries show" -- a league's
# Status labels are derived from here, not independently hand-kept, so
# editing a country's entry above is the one place that needs to change for
# both to move together automatically.
#
# Deliberately literal: Russia's own entries use their nominal, undisturbed
# label (e.g. "CL-Q1") exactly as this file already stores it -- the
# suspension's real-world redistribution is already baked into the OTHER
# affected countries' promoted labels (see this module's own docstring), not
# applied a second time here. No separate suspension handling needed.
# ---------------------------------------------------------------------------

_STATUS_LABEL = {
    ("CL", "LS"): "UCL - LS", ("CL", "PO"): "UCL - PO",
    ("CL", "Q1"): "UCL - QR1", ("CL", "Q2"): "UCL - QR2", ("CL", "Q3"): "UCL - QR3",
    ("EL", "LS"): "UEL - LS", ("EL", "PO"): "UEL - PO",
    ("EL", "Q1"): "UEL - QR1", ("EL", "Q2"): "UEL - QR2", ("EL", "Q3"): "UEL - QR3",
    ("CO", "LS"): "UECL - LS", ("CO", "PO"): "UECL - PO",
    ("CO", "Q1"): "UECL - QR1", ("CO", "Q2"): "UECL - QR2", ("CO", "Q3"): "UECL - QR3",
}

_POSITION_CODE = {1: "CH", 2: "N2", 3: "N3", 4: "N4", 5: "N5", 6: "N6", 7: "N7"}


def label_to_status(label: str) -> str:
    """Convert an access-list `label` (e.g. "CL-Q2nc") into this site's
    display Status string (e.g. "UCL - QR2 (LP)"). The "nc" suffix (League
    Path, Champions League only) becomes the existing "(LP)" display
    convention league_status.py already used before this connection."""
    is_lp = label.endswith("nc")
    base = label[:-2] if is_lp else label
    comp, rnd = base.split("-", 1)
    status = _STATUS_LABEL[(comp, rnd)]
    return f"{status} (LP)" if is_lp else status


@functools.lru_cache(maxsize=1)
def _access_by_country() -> dict[str, dict[str, str]]:
    """{country: {code: label}} flattened across all three competitions --
    cached since ACCESS_LIST_2027_28 is static module data."""
    by_country: dict[str, dict[str, str]] = {}
    for entries in ACCESS_LIST_2027_28.values():
        for e in entries:
            by_country.setdefault(e["country"], {})[e["code"]] = e["label"]
    return by_country


def european_status_zones(country: str) -> dict[int, str]:
    """{league position: Status label} for this country's 2027/28-access-
    list-derived European qualification (CH/N2.../N7 only -- CW is
    position-independent, see cup_winner_status). Empty for a country with
    no access-list entries at this position (e.g. no N5+ slot)."""
    access = _access_by_country().get(country, {})
    return {
        pos: label_to_status(access[code])
        for pos, code in _POSITION_CODE.items() if code in access
    }


def cup_winner_status(country: str) -> str | None:
    """This country's cup-winner Status label (e.g. "UEL - QR1"), or None
    if it has no CW entry in the access list. Which TEAM currently holds
    it is a separate, season-specific question (predicted cup winner,
    cascaded if they already occupy a league-position spot) --
    config.py's own team_status_overrides, same as before."""
    label = _access_by_country().get(country, {}).get("CW")
    return label_to_status(label) if label else None
