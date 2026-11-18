"""
Shared constants for the EURO 2028 qualifying draw and finals-bracket
pipeline. Kept in their own pure module (no Streamlit import, nothing
executed at import time beyond plain data) so euro_2028_finals_bracket.py
can reuse them without importing euro_2028_qualifying_draw.py itself --
that file is a Streamlit PAGE script, and under Streamlit's own page
runner (and streamlit.testing.v1.AppTest) it isn't registered in
sys.modules the normal way, so a cross-import of it from another module
causes it to be exec'd a second time, duplicating every widget's
auto-generated ID (StreamlitDuplicateElementId). See
euro_2028_qualifying_draw.py's own docstring for the full qualifying
rules these feed; euro_2028_finals_bracket.py's docstring for the
finals rules.
"""

HOSTS = {"England", "Wales", "Republic of Ireland", "Scotland"}
NIR = "Northern Ireland"
# The 8 real, now fully-decided 2026-27 Nations League League A
# quarter-finalists (confirmed 2026-11-18, all 4 groups finished) --
# previously a projection (Spain/Portugal/France/England/Netherlands/
# Greece/Belgium/Denmark); Greece and Denmark actually finished 3rd in
# their groups, replaced here by the real qualifiers, Germany and Norway.
QF_TEAMS = {"Spain", "Portugal", "France", "England", "Netherlands", "Belgium", "Germany", "Norway"}

# Euro 2024 qualifying's own named "prohibited clash" pairs (political/security).
POLITICAL_PAIRS = {
    frozenset({"Armenia", "Azerbaijan"}),
    frozenset({"Belarus", "Ukraine"}),
    frozenset({"Gibraltar", "Spain"}),
    frozenset({"Kosovo", "Bosnia and Herzegovina"}),
    frozenset({"Kosovo", "Serbia"}),
}
# Euro 2024 qualifying's own named excessive-travel pairings (max 1 per group).
TRAVEL_PAIRS = {
    frozenset({"Azerbaijan", "Gibraltar"}),
    frozenset({"Azerbaijan", "Iceland"}),
    frozenset({"Azerbaijan", "Portugal"}),
    frozenset({"Iceland", "Cyprus"}),
    frozenset({"Iceland", "Georgia"}),
    frozenset({"Iceland", "Israel"}),
    frozenset({"Kazakhstan", "Andorra"}),
    frozenset({"Kazakhstan", "England"}),
    frozenset({"Kazakhstan", "France"}),
    frozenset({"Kazakhstan", "Gibraltar"}),
    frozenset({"Kazakhstan", "Iceland"}),
    frozenset({"Kazakhstan", "Malta"}),
    frozenset({"Kazakhstan", "Northern Ireland"}),
    frozenset({"Kazakhstan", "Portugal"}),
    frozenset({"Kazakhstan", "Republic of Ireland"}),
    frozenset({"Kazakhstan", "Scotland"}),
    frozenset({"Kazakhstan", "Spain"}),
    frozenset({"Kazakhstan", "Wales"}),
}
# Euro 2024 qualifying's own named high/medium winter-risk-venue teams (max 2 per group).
WINTER_RISK_TEAMS = {
    "Belarus", "Estonia", "Faroe Islands", "Finland", "Iceland", "Latvia", "Lithuania", "Norway",
}
