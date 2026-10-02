"""
Tier-2 equivalent of league_display.py's dropdown helpers. Unlike the
top-flight LEAGUES (hand-written "Country - League" labels per entry,
plus a pinned "Top 5" group), LEAGUES_TIER2's own keys are already in
"Country - League" form (see config.py), and there's no pinned-leagues
concept for second divisions -- so this is just the key list itself,
sorted alphabetically by country, with no hand-maintained label dict to
keep in sync.
"""

from config import LEAGUES_TIER2

DROPDOWN_LABELS: dict[str, str] = {name: name for name in LEAGUES_TIER2}
DROPDOWN_ORDER = sorted(LEAGUES_TIER2.keys())
