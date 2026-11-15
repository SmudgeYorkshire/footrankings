"""
2028/29 UEFA Nations League -- projected League A/B/C entries and
example groups for the next Nations League cycle. Format confirmed via
https://en.wikipedia.org/wiki/2028%E2%80%9329_UEFA_Nations_League
(2026-11-16): three leagues (A/B/C) of 18 teams each, three groups of
6 per league (one team from each of 3 pots per group) -- League D is
retired for this cycle, its teams folding up into League C, per
UEFA's own stated format change.

Team assignments and example groupings below are the user's own
confirmed projection, not this site's nations_league_simulator.py
engine -- that engine's own "Projections" tab on the (now-renamed)
2026/27 Nations League page is a SEPARATE, algorithmically-derived
single point estimate from the live simulation; this page is a plain,
manually-maintained snapshot, the same convention euro_2028_qualifying_draw.py
and entrants_2027_28.py already use for next-cycle data -- edit the
lists below by hand as the real 2026/27 Nations League develops.
"""

import streamlit as st
import pandas as pd

from flags import flag_url
from nations_league_data import NL_FLAG_ALIASES


def _flag(team: str) -> str:
    return flag_url(NL_FLAG_ALIASES.get(team, team))


st.title("🏅 2028/29 Nations League")
st.caption(
    "Projected entries for the next UEFA Nations League cycle, per the user's own "
    "manually-set projection -- treated as confirmed for now, edited by hand as the "
    "real 2026/27 Nations League develops. Format confirmed via "
    "[Wikipedia](https://en.wikipedia.org/wiki/2028%E2%80%9329_UEFA_Nations_League)."
)

with st.expander("Format (per Wikipedia)"):
    st.markdown(
        "- **3 leagues** (A/B/C), 18 teams each -- **League D is retired** for this "
        "cycle, its teams folding into League C.\n"
        "- **3 groups of 6 per league**, seeded from 3 pots of 6 (one team from each "
        "pot per group).\n"
        "- **Promotion/relegation**: League B/C group winners promote directly; "
        "League A/B last-placed teams relegate directly.\n"
        "- **Play-offs** (March 2029, two legs each): League A 4th/5th vs League B "
        "2nd/3rd; League B 4th/5th vs League C 2nd/3rd -- winners move up, losers "
        "move down.\n"
        "- **League A knockout**: group winners, runners-up and the 2 best "
        "third-placed teams reach two-legged quarter-finals (March 2029); the 4 "
        "winners reach the Finals (semi-finals, third-place play-off, final -- "
        "June 2029).\n"
        "- **55 UEFA members eligible; Russia remains suspended** and excluded, "
        "same as everywhere else on this site."
    )

LEAGUES = {
    "League A": {
        "entries": [
            ("Spain", "League A Quarterfinalist"), ("England", "League A Quarterfinalist"),
            ("France", "League A Quarterfinalist"), ("Portugal", "League A Quarterfinalist"),
            ("Netherlands", "League A Quarterfinalist"), ("Italy", "League A Quarterfinalist"),
            ("Denmark", "League A Quarterfinalist"), ("Germany", "League A Quarterfinalist"),
            ("Belgium", "3rd-placed in League A"), ("Greece", "3rd-placed in League A"),
            ("Switzerland", "League B group winner"), ("Sweden", "League B group winner"),
            ("Austria", "League B group winner"), ("Hungary", "League B group winner"),
            ("Norway", "League A/B play-off winner"), ("Croatia", "League A/B play-off winner"),
            ("Wales", "League A/B play-off winner"), ("Serbia", "League A/B play-off winner"),
        ],
        "groups": {
            "A1": ["Spain", "Portugal", "Denmark", "Greece", "Austria", "Croatia"],
            "A2": ["England", "Netherlands", "Germany", "Switzerland", "Hungary", "Wales"],
            "A3": ["France", "Italy", "Belgium", "Sweden", "Norway", "Serbia"],
        },
    },
    "League B": {
        "entries": [
            ("Czechia", "Lowest-ranked 4th-placed League A nation"),
            ("Türkiye", "Lowest-ranked 4th-placed League A nation"),
            ("Northern Ireland", "Defeated in League A/B play-off"),
            ("Slovenia", "Defeated in League A/B play-off"),
            ("Bosnia and Herzegovina", "Defeated in League A/B play-off"),
            ("Kosovo", "Defeated in League A/B play-off"),
            ("Scotland", "3rd-placed in League B"), ("Republic of Ireland", "3rd-placed in League B"),
            ("Ukraine", "3rd-placed in League B"), ("Poland", "3rd-placed in League B"),
            ("Montenegro", "League C group winner"), ("Albania", "League C group winner"),
            ("Iceland", "League C group winner"), ("Slovakia", "League C group winner"),
            ("Romania", "League B/C play-off winner"), ("Israel", "League B/C play-off winner"),
            ("Georgia", "League B/C play-off winner"), ("North Macedonia", "League B/C play-off winner"),
        ],
        "groups": {
            "B1": ["Czechia", "Slovenia", "Scotland", "Poland", "Iceland", "Israel"],
            "B2": ["Türkiye", "Bosnia and Herzegovina", "Republic of Ireland", "Montenegro", "Slovakia", "Georgia"],
            "B3": ["Northern Ireland", "Kosovo", "Ukraine", "Albania", "Romania", "North Macedonia"],
        },
    },
    "League C": {
        "entries": [
            ("Belarus", "Defeated in League B/C play-off"), ("Estonia", "Defeated in League B/C play-off"),
            ("Cyprus", "Defeated in League B/C play-off"), ("Faroe Islands", "Defeated in League B/C play-off"),
            ("Finland", "3rd/4th-placed in League C"), ("Moldova", "3rd/4th-placed in League C"),
            ("Armenia", "3rd/4th-placed in League C"), ("Bulgaria", "3rd/4th-placed in League C"),
            ("Luxembourg", "3rd/4th-placed in League C"), ("Kazakhstan", "3rd/4th-placed in League C"),
            ("Latvia", "3rd/4th-placed in League C"), ("San Marino", "3rd/4th-placed in League C"),
            ("Malta", "League D nation (retired, folded into League C)"),
            ("Azerbaijan", "League D nation (retired, folded into League C)"),
            ("Lithuania", "League D nation (retired, folded into League C)"),
            ("Andorra", "League D nation (retired, folded into League C)"),
            ("Gibraltar", "League D nation (retired, folded into League C)"),
            ("Liechtenstein", "League D nation (retired, folded into League C)"),
        ],
        "groups": {
            "C1": ["Belarus", "Faroe Islands", "Armenia", "Kazakhstan", "Malta", "Andorra"],
            "C2": ["Estonia", "Finland", "Bulgaria", "Latvia", "Azerbaijan", "Gibraltar"],
            "C3": ["Cyprus", "Moldova", "Luxembourg", "San Marino", "Lithuania", "Liechtenstein"],
        },
    },
}

_ENTRY_COLUMN_CONFIG = {
    "Flag": st.column_config.ImageColumn("", width="small"),
    "Team": st.column_config.TextColumn("Team", width="medium"),
    "Route": st.column_config.TextColumn("Route", width="large"),
}
_GROUP_COLUMN_CONFIG = {
    "Flag": st.column_config.ImageColumn("", width="small"),
    "Team": st.column_config.TextColumn("Team", width="medium"),
}

_metric_cols = st.columns(4)
for _col, _league in zip(_metric_cols, LEAGUES):
    _col.metric(_league, f"{len(LEAGUES[_league]['entries'])} teams")
_metric_cols[3].metric("Total", f"{sum(len(l['entries']) for l in LEAGUES.values())} teams")

st.divider()

_tabs = st.tabs(list(LEAGUES))
for _tab, _league in zip(_tabs, LEAGUES):
    with _tab:
        st.markdown(f"#### Projected {_league} entries")
        _rows = [{"Flag": _flag(team), "Team": team, "Route": route} for team, route in LEAGUES[_league]["entries"]]
        _df = pd.DataFrame(_rows)
        st.dataframe(
            _df, column_config=_ENTRY_COLUMN_CONFIG,
            width="content", hide_index=True, height=min(len(_df) * 35 + 38, 700),
        )

        st.markdown(f"#### Example {_league} groups")
        st.caption("One team from each of 3 pots per group -- illustrative, not yet the real UEFA draw.")
        _group_cols = st.columns(3)
        for _gcol, (_glabel, _teams) in zip(_group_cols, LEAGUES[_league]["groups"].items()):
            with _gcol:
                st.markdown(f"**Group {_glabel}**")
                _gdf = pd.DataFrame([{"Flag": _flag(t), "Team": t} for t in _teams])
                st.dataframe(
                    _gdf, column_config=_GROUP_COLUMN_CONFIG,
                    width="content", hide_index=True, height=len(_gdf) * 35 + 38,
                )
