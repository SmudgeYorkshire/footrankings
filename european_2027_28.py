"""
2027/28 UEFA European Competitions -- access list, connected live to each
domestic league's CURRENT (2026/27) standings.

Nothing about the 2027/28 qualifying draw, League Phase pairings, or pot
seeding exists yet (UEFA won't draw any of that until mid-2027) -- this
page only answers "who would currently qualify, and via which route,
if the 2026/27 domestic seasons ended today." See european.py for the
fully-live 2026/27 competitions (qualifying ties, League Phase table,
simulations) this page will grow into once the 2027/28 draw exists.

Every row's competition/path/qualifying-round comes from
entrants_2027_28.ACCESS_LIST_2027_28 (UEFA's own published access list,
circular 54/2026). The occupant shown for each slot is resolved live
against that country's own league table on THIS site (config.LEAGUES),
not hardcoded -- exactly the "Top 4 Serie A -> 2027/28 Champions League"
connection a domestic table's own Status column already implies.
"""

import os

import streamlit as st
import pandas as pd

from config import LEAGUES
from flags import flag_url
from api_football_fetcher import ApiFootballClient
from _split_season import compute_full_standings, ensure_full_roster
from entrants_2027_28 import ACCESS_LIST_2027_28, STAGE_ORDER_2027_28, QUALIFYING_DATES_2027_28

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")

# entrants_2027_28.py's country spelling matches config.LEAGUES' own (so a
# row's "league" field can look standings up directly) -- flags.py alone
# spells a handful of these differently, so only the flag lookup needs this.
_FLAG_ALIAS = {
    "Turkey": "Türkiye", "Czech Rep.": "Czechia", "Bosnia": "Bosnia-Herzegovina",
    "Faroe Isl.": "Faroe Islands", "N. Macedonia": "North Macedonia", "N. Ireland": "Northern Ireland",
}


@st.cache_data(ttl=60, show_spinner=False)
def _current_standings(league_id: int, season: int, league_name: str):
    """Mirrors football_rankings.py's own fetch_all -- same shape, same
    staleness-avoidance (self-computed standings, not the provider's own
    lagging aggregate) -- duplicated here rather than imported so this
    page doesn't execute football_rankings.py's whole top-level script
    as an import side effect."""
    client = ApiFootballClient(api_key=_API_KEY)
    roster = client.get_standings(league_id, season)
    played, remaining = client.get_fixtures(league_id, season)
    roster = ensure_full_roster(roster, played + remaining)
    tiebreakers = LEAGUES.get(league_name, {}).get("tiebreakers")
    return compute_full_standings(roster, played, tiebreakers=tiebreakers) if roster else roster


_POSITION_OF_CODE = {"CH": 1, "N2": 2, "N3": 3, "N4": 4, "N5": 5, "N6": 6, "N7": 7}


def _occupant(entry: dict) -> tuple[str, str]:
    """(team, note) currently sitting in this access-list slot, read live
    off the domestic table -- "note" explains anything not a plain live
    read, prefixed with the entry's own note (EPS prediction, Russia's
    suspension, a round promoted to backfill Russia's vacancy) when set."""
    own_note = entry.get("note")
    if own_note and own_note.startswith("Suspended"):
        return "—", own_note
    if entry["league"] is None:
        return "—", own_note or "no tracked league"
    if entry["code"] == "CW":
        return "—", own_note or "2026/27 domestic cup still in progress"
    if not _API_KEY:
        return "—", "no API key configured"
    cfg = LEAGUES.get(entry["league"])
    if not cfg:
        return "—", "league not found"
    try:
        standings = _current_standings(cfg["id"], cfg["af_season"], entry["league"])
    except Exception:
        return "—", "live fetch failed"
    pos = _POSITION_OF_CODE.get(entry["code"])
    if not standings or pos is None or pos > len(standings):
        return "—", own_note or "not yet determined"
    note = "current position, may still change"
    if own_note:
        note = f"{own_note} — {note}"
    return standings[pos - 1].get("strTeam", "—"), note


st.title("🔮 European Competitions 2027/28")
st.caption(
    "UEFA's official 2027/28 access list (circular 54/2026), connected live to each "
    "country's CURRENT 2026/27 league table. Every occupant below is provisional -- "
    "domestic seasons run until roughly May/June 2027, and nothing about the actual "
    "2027/28 qualifying draw exists yet."
)

comp_name = st.selectbox("Competition", list(ACCESS_LIST_2027_28.keys()))
entries = ACCESS_LIST_2027_28[comp_name]

n_direct = sum(1 for e in entries if e["round"] == "League Phase (direct)")
n_total = len(entries)
st.markdown(
    f"**{n_total} slots** in the 2027/28 access list -- **{n_direct} already go straight "
    f"to the 36-team League Phase**, the rest work through qualifying."
)

qd = QUALIFYING_DATES_2027_28[comp_name]

groups: dict[str, list[dict]] = {}
for e in entries:
    groups.setdefault(e["round"], []).append(e)

for stage in STAGE_ORDER_2027_28:
    rows = groups.get(stage)
    if not rows:
        continue
    dates = qd.get(
        {
            "First qualifying round": "First Qualifying Round",
            "Second qualifying round": "Second Qualifying Round",
            "Third qualifying round": "Third Qualifying Round",
            "Play-off round": "Play-off Round",
            "League Phase (direct)": "League Phase",
        }[stage]
    )
    date_str = ""
    if dates:
        date_str = f" — {dates['leg1']}" + (f" / {dates['leg2']}" if dates.get("leg2") else "")
    st.markdown(f"#### {stage}{date_str}")

    table_rows = []
    for e in sorted(rows, key=lambda r: r["country"]):
        occupant, note = _occupant(e)
        table_rows.append({
            "Flag": flag_url(_FLAG_ALIAS.get(e["country"], e["country"])),
            "Country": e["country"],
            "Label": e["label"],
            "Path": e["path"],
            "Route": e["route"],
            "Currently": occupant,
            "Note": note,
        })
    df = pd.DataFrame(table_rows)
    st.dataframe(
        df,
        column_config={
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Country": st.column_config.TextColumn("Country", width="medium"),
            "Label": st.column_config.TextColumn("Label", width="small"),
            "Path": st.column_config.TextColumn("Path", width="small"),
            "Route": st.column_config.TextColumn("Route", width="small"),
            "Currently": st.column_config.TextColumn("Currently", width="medium"),
            "Note": st.column_config.TextColumn("Note", width="large"),
        },
        use_container_width=True, hide_index=True, height=len(df) * 35 + 38,
    )

st.divider()
st.caption(
    "Not shown: UCL/UEL defending-titleholder byes, and the Conference League "
    "titleholder's promotion into the Europa League (all three depend on who wins "
    "the 2026/27 finals). England and Germany's 5th Champions League slot above "
    "assumes they again receive 2027/28's 2 \"European Performance Spot\" bonus "
    "places -- predicted, not yet confirmed by UEFA (awarded after 2026/27 ends, by "
    "aggregate club coefficient) -- see entrants_2027_28.py's own docstring for the "
    "full picture, including how Russia's ongoing suspension is handled."
)
