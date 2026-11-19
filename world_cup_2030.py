"""
2030 FIFA World Cup qualifying -- confederation-by-confederation seeding
details, picked via a dropdown (currently just AFC/Asia; built to add
more confederations as their own seeding is confirmed, without
restructuring). Manually-maintained from the user's own sourced data
(https://bkassies.nl/uefa/forum2/viewtopic.php?t=7075), same convention
euro_2028_draw.py's own pots use -- update by hand as draws/suspensions
are confirmed, no live computation.
"""

import streamlit as st
import pandas as pd

from flags import flag_url

# Pasted-content team name -> flags.py's own key, only where they differ.
_ASIA_FLAG_ALIASES = {
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "DPR Korea": "North Korea",
    "China PR": "China",
    "Hong Kong, China": "Hong Kong",
    "Chinese Taipei": "Taiwan",
    "Kyrgyz Republic": "Kyrgyzstan",
    "Macau, China": "Macao",
    "Timor-Leste": "East Timor",
    "Brunei Darussalam": "Brunei",
}


def _flag(team: str) -> str:
    return flag_url(_ASIA_FLAG_ALIASES.get(team, team))


# As of 2026-11-19. (team, FIFA ranking) -- ranking as given in the source.
ASIA_ROUND2_POT1 = [
    ("Japan", 17), ("IR Iran", 23), ("Australia", 27), ("Korea Republic", 30),
    ("Saudi Arabia", 54), ("Uzbekistan", 60), ("Qatar", 61), ("Iraq", 62),
    ("United Arab Emirates", 66),
]
ASIA_ROUND2_POT2 = [
    ("Jordan", 72), ("Oman", 82), ("Syria", 88), ("Thailand", 90),
    ("Palestine", 92), ("China PR", 95), ("Bahrain", 96), ("Vietnam", 99),
    ("Tajikistan", 100),
]
ASIA_ROUND2_POT3 = [
    ("Kyrgyz Republic", 102), ("Lebanon", 111), ("Indonesia", 116), ("DPR Korea", 121),
    ("Malaysia", 133), ("Kuwait", 134), ("Philippines", 135), ("India", 141),
]
ASIA_ROUND2_POT3_NOTE = (
    "If Nepal are still suspended by FIFA, Turkmenistan will skip Round 1 and be "
    "assigned to Pot 3 directly."
)
ASIA_ROUND2_POT4_NOTE = (
    "Pot 4 is the 10 Round 1 winners. 1 of the 10 will be drawn to Position 3; if "
    "Nepal are still suspended, there will be only 9 Round 1 winners."
)

ASIA_ROUND1_SEEDED = [
    ("Turkmenistan", 142), ("Yemen", 148), ("Singapore", 149), ("Hong Kong, China", 152),
    ("Myanmar", 159), ("Afghanistan", 169), ("Maldives", 172), ("Cambodia", 176),
    ("Chinese Taipei", 177), ("Nepal", 178),
]
ASIA_ROUND1_SEEDED_NOTE = "If Nepal are still suspended by FIFA, Bangladesh will be seeded instead."
ASIA_ROUND1_UNSEEDED = [
    ("Bangladesh", 182), ("Sri Lanka", 185), ("Laos", 187), ("Mongolia", 190),
    ("Bhutan", 192), ("Macau, China", 193), ("Brunei Darussalam", 196), ("Pakistan", 197),
    ("Timor-Leste", 202), ("Guam", 203),
]

_POT_COLUMN_CONFIG = {
    "Flag": st.column_config.ImageColumn("", width="small"),
    "Team": st.column_config.TextColumn("Team", width="medium"),
    "FIFA Ranking": st.column_config.NumberColumn("FIFA Ranking", width="small"),
}


def _pot_table(entries: list[tuple[str, int]]) -> pd.DataFrame:
    return pd.DataFrame([
        {"Flag": _flag(team), "Team": team, "FIFA Ranking": rank}
        for team, rank in entries
    ])


def _render_pot(label: str, entries: list[tuple[str, int]], note: str | None = None) -> None:
    st.markdown(f"**{label}**")
    df = _pot_table(entries)
    st.dataframe(
        df, column_config=_POT_COLUMN_CONFIG,
        width="content", hide_index=True, height=len(df) * 35 + 38,
    )
    if note:
        st.caption(note)


def _render_asia_qualifiers() -> None:
    st.caption(
        "AFC (Asia) qualifying seeding for the 2030 FIFA World Cup, as of 2026-11-19 "
        "-- pre-draw pots, not yet an actual group draw. Source: "
        "[bkassies.nl forum](https://bkassies.nl/uefa/forum2/viewtopic.php?t=7075). "
        "Manually-maintained -- update by hand once Nepal's suspension status is "
        "resolved and once the real draws are made."
    )

    st.markdown("### Round 1 draw")
    st.caption(
        "20 lowest-ranked AFC nations -- the 10 Round 1 winners join Round 2's Pot 4."
    )
    _r1_cols = st.columns(2)
    with _r1_cols[0]:
        _render_pot("Seeded", ASIA_ROUND1_SEEDED, ASIA_ROUND1_SEEDED_NOTE)
    with _r1_cols[1]:
        _render_pot("Unseeded", ASIA_ROUND1_UNSEEDED)

    st.divider()

    st.markdown("### Round 2 draw")
    st.caption("The remaining 36 AFC nations, seeded by FIFA ranking, plus the 10 Round 1 winners.")
    _r2_cols = st.columns(4)
    with _r2_cols[0]:
        _render_pot("Pot 1", ASIA_ROUND2_POT1)
    with _r2_cols[1]:
        _render_pot("Pot 2", ASIA_ROUND2_POT2)
    with _r2_cols[2]:
        _render_pot("Pot 3", ASIA_ROUND2_POT3, ASIA_ROUND2_POT3_NOTE)
    with _r2_cols[3]:
        st.markdown("**Pot 4**")
        st.caption(ASIA_ROUND2_POT4_NOTE)


st.title("🌐 2030 World Cup")

confederation = st.selectbox("Confederation", ["Asia - Qualifiers"])

if confederation == "Asia - Qualifiers":
    _render_asia_qualifiers()
