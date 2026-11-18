"""
2028 EURO page -- qualifying draw simulator, group/knockout predictions,
and (via the "Qualifying Chances" view) each nation's own overall chance
to reach the finals tournament at all.

Pots/draw mechanics live in euro_2028_draw.py (pure logic, see that
module's own docstring for the full UEFA format/constraint breakdown --
pots re-confirmed against Wikipedia 2026-11-18, every team now resolved
to a single pot). Qualifying-chances Monte Carlo lives in
euro_2028_qualifying_odds.py. Both are kept out of this page script on
purpose -- a Streamlit page isn't registered in sys.modules the normal
way, so another module importing it directly would get it exec'd a
second time, duplicating every widget's ID.
"""

import streamlit as st
import pandas as pd

from flags import flag_url
from nations_league_data import NL_FLAG_ALIASES
from simulator import seed_from_key
import euro_2028_group_predictions as gp
import euro_2028_finals_bracket as fb
import euro_2028_qualifying_odds as qo
from euro_2028_draw import POTS, GROUPS_4, GROUPS_5, generate_draw


def _flag(team: str) -> str:
    return flag_url(NL_FLAG_ALIASES.get(team, team))


st.title("🎲 2028 Euro")

view = st.radio("View", ["Simulator", "Qualifying Chances"], horizontal=True)


def _render_simulator() -> None:
    st.caption(
        "Simulates the UEFA Euro 2028 qualifying group draw from the official pots. "
        "Format rules sourced from "
        "[Wikipedia](https://en.wikipedia.org/wiki/UEFA_Euro_2028_qualifying); the "
        "political/security, travel and winter-venue restrictions are carried over from "
        "[Euro 2024 qualifying](https://en.wikipedia.org/wiki/UEFA_Euro_2024_qualifying)'s "
        "own named list as the best available precedent, pending UEFA's official 2028 "
        "confirmation -- see euro_2028_draw.py's own module docstring for the full breakdown."
    )

    # -----------------------------------------------------------------
    # Pots display
    # -----------------------------------------------------------------
    st.markdown("### Predicted Pots")
    _pot_cols = st.columns(5)
    for _pot_num, _col in zip(POTS, _pot_cols):
        with _col:
            st.markdown(f"**POT {_pot_num}**")
            _rows = [{"Flag": _flag(team), "Team": team} for team in POTS[_pot_num]]
            _df = pd.DataFrame(_rows)
            st.dataframe(
                _df,
                column_config={
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                },
                width="content", hide_index=True, height=len(_df) * 35 + 38,
            )

    st.divider()

    # -----------------------------------------------------------------
    # Draw
    # -----------------------------------------------------------------
    st.markdown("### Run the draw")
    st.caption(
        "Each click produces a fresh, valid draw: hosts in separate groups, Northern "
        "Ireland apart from every host, no political/security prohibited pair together, "
        "at most 1 excessive-travel pair and at most 2 winter-risk-venue teams per group. "
        "Groups A-F have 4 teams (Pots 1-4); Groups G-L have 5 (Pots 1-5)."
    )
    _ver_key = "euro2028_draw_version"
    if _ver_key not in st.session_state:
        st.session_state[_ver_key] = 0

    if st.button("🎲  Run the draw", type="primary", use_container_width=True):
        st.session_state[_ver_key] += 1
        st.session_state.pop("euro2028_predict_clicked", None)

    if st.session_state[_ver_key] == 0:
        st.info("Press **🎲 Run the draw** to simulate the group draw.")
        return

    _groups = generate_draw(("euro2028_draw", st.session_state[_ver_key]))
    _team_to_pot = {t: p for p, teams in POTS.items() for t in teams}

    def _render_group(letter: str) -> None:
        st.markdown(f"**Group {letter}**")
        rows = [
            {"Flag": _flag(team), "Team": team, "Pot": _team_to_pot.get(team)}
            for team in _groups[letter]
        ]
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Pot": st.column_config.NumberColumn("Pot", width="small"),
            },
            width="content", hide_index=True, height=len(df) * 35 + 38,
        )

    st.divider()
    st.markdown("#### Groups A-F (4 teams)")
    _af_cols = st.columns(3)
    for _i, _letter in enumerate(GROUPS_4):
        with _af_cols[_i % 3]:
            _render_group(_letter)

    st.markdown("#### Groups G-L (5 teams)")
    _gl_cols = st.columns(3)
    for _i, _letter in enumerate(GROUPS_5):
        with _gl_cols[_i % 3]:
            _render_group(_letter)

    # -----------------------------------------------------------------
    # Group predictions, from today's Nation Strength Rankings
    # -----------------------------------------------------------------
    st.divider()
    st.markdown("### Predict all groups")
    st.caption(
        "Uses today's [Nation Strength Rankings](/nation_power_rankings) combined "
        "rating to simulate each group's round-robin 10,000 times (classic-Elo "
        "win-expectancy + a symmetric draw model -- see euro_2028_group_predictions.py's "
        "own docstring for why this doesn't reuse the site's Opta-goal engine)."
    )
    _pred_key = "euro2028_predict_clicked"
    if st.button("🔮  Predict all groups", use_container_width=True):
        st.session_state[_pred_key] = True

    if not st.session_state.get(_pred_key):
        return

    _ratings = gp.load_ratings()
    if not _ratings:
        st.warning(
            "nation_power_rankings.csv isn't available yet -- predictions are "
            "falling back to a flat default rating for every team."
        )

    _qual_predictions: dict[str, pd.DataFrame] = {}

    def _render_prediction(letter: str) -> None:
        st.markdown(f"**Group {letter}**")
        _team_rows = _groups[letter]
        _pred_df = gp.simulate_group(
            _team_rows, _ratings,
            seed=seed_from_key(("euro2028_predict", letter, st.session_state[_ver_key])),
        )
        _qual_predictions[letter] = _pred_df
        _n = len(_team_rows)
        _rows = []
        for _pos, _row in _pred_df.iterrows():
            _team = _row["team"]
            _rows.append({
                "Flag": _flag(_team),
                "Team": _team,
                "Pos": _pos + 1,
                "Pts": round(_row["predicted_points"], 1),
                "Top-2 %": round(100 * (_row["pos_1_prob"] + _row["pos_2_prob"]), 1) if _n >= 2 else None,
            })
        _out = pd.DataFrame(_rows)
        st.dataframe(
            _out,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Pos": st.column_config.NumberColumn("Pos", width="small"),
                "Pts": st.column_config.NumberColumn("Pts", width="small"),
                "Top-2 %": st.column_config.NumberColumn("Top-2 %", width="small"),
            },
            width="content", hide_index=True, height=len(_out) * 35 + 38,
        )

    st.divider()
    st.markdown("#### Groups A-F")
    _paf_cols = st.columns(3)
    for _i, _letter in enumerate(GROUPS_4):
        with _paf_cols[_i % 3]:
            _render_prediction(_letter)

    st.markdown("#### Groups G-L")
    _pgl_cols = st.columns(3)
    for _i, _letter in enumerate(GROUPS_5):
        with _pgl_cols[_i % 3]:
            _render_prediction(_letter)

    # -----------------------------------------------------------------
    # EURO 2028 Finals -- resolve the 24, run the Finals draw, predict
    # the knockout bracket. See euro_2028_finals_bracket.py's own
    # docstring for every stand-in this uses for real 2028 rules that
    # aren't published yet.
    # -----------------------------------------------------------------
    st.divider()
    st.markdown("### EURO 2028 Finals")
    st.caption(
        "Carries these qualifying predictions into the real UEFA Euro 2028 "
        "**finals** tournament (24 teams, 6 groups of 4 -- also labelled A-F, but "
        "a completely separate draw from the 12 qualifying groups above; always "
        "shown as \"Finals Group X\" below to avoid confusion). Several pieces of "
        "the real 2028 finals format aren't published anywhere yet (tie-break "
        "order, third-place ranking criteria, Pot 1-4 composition) -- see "
        "euro_2028_finals_bracket.py's own module docstring for the stand-ins used "
        "here, including how the 4 qualification slots beyond the 12 group "
        "winners, 8 best-ranked runners-up and host reservation are filled (the "
        "real pool also includes Nations League teams this site has no data for)."
    )

    _finalists = fb.resolve_finalists(_qual_predictions)
    _pots, _head_assignment = fb.build_finals_pots(_finalists, _ratings)
    _pot_of = {t: p for p, teams in _pots.items() for t in teams}

    st.markdown("#### Resolve the 24 finalists")
    _fin_rows = [
        {
            "Flag": _flag(f["team"]), "Team": f["team"],
            "Route": f["route"], "Finals Pot": _pot_of.get(f["team"]),
        }
        for f in _finalists
    ]
    _fin_df = pd.DataFrame(_fin_rows)
    st.dataframe(
        _fin_df,
        column_config={
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Team": st.column_config.TextColumn("Team", width="medium"),
            "Route": st.column_config.TextColumn("Route", width="medium"),
            "Finals Pot": st.column_config.NumberColumn("Finals Pot", width="small"),
        },
        width="content", hide_index=True, height=len(_fin_df) * 35 + 38,
    )

    st.markdown("#### Run the Finals draw")
    _fin_ver_key = "euro2028_finals_draw_version"
    if _fin_ver_key not in st.session_state:
        st.session_state[_fin_ver_key] = 0
    if st.button("🎲  Run the Finals draw", use_container_width=True):
        st.session_state[_fin_ver_key] += 1
        st.session_state.pop("euro2028_finals_predict_clicked", None)

    if st.session_state[_fin_ver_key] == 0:
        st.info("Press **🎲 Run the Finals draw** to draw the 6 Finals groups.")
        return

    _finals_groups = fb.draw_finals_groups(
        _pots, _head_assignment,
        seed=seed_from_key(("euro2028_finals_draw", st.session_state[_fin_ver_key])),
    )

    def _render_finals_group(letter: str) -> None:
        st.markdown(f"**Finals Group {letter}**")
        rows = [
            {"Flag": _flag(team), "Team": team, "Pot": _pot_of.get(team)}
            for team in _finals_groups[letter]
        ]
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Pot": st.column_config.NumberColumn("Pot", width="small"),
            },
            width="content", hide_index=True, height=len(df) * 35 + 38,
        )

    _fcols = st.columns(3)
    for _i, _letter in enumerate(fb.FINALS_GROUPS):
        with _fcols[_i % 3]:
            _render_finals_group(_letter)

    st.markdown("#### 🏆 Predict the knockout bracket")
    st.caption(
        "Simulates the Finals group stage and the full knockout bracket "
        "together, 10,000 times, using the exact round-of-16 permutation "
        "table and match schedule from "
        "[Wikipedia](https://en.wikipedia.org/wiki/UEFA_Euro_2028). Knockout "
        "matches use neutral win probabilities (no home advantage); a drawn "
        "90 minutes is resolved as a 50/50 split, standing in for extra time "
        "plus a penalty shoot-out."
    )
    _fin_pred_key = "euro2028_finals_predict_clicked"
    if st.button("🏆  Predict the knockout bracket", use_container_width=True):
        st.session_state[_fin_pred_key] = True

    if not st.session_state.get(_fin_pred_key):
        return

    _bracket_df = fb.simulate_finals(
        _finalists, _finals_groups, _ratings,
        seed=seed_from_key(("euro2028_finals_predict", st.session_state[_fin_ver_key])),
    )
    _bracket_rows = [
        {
            "Flag": _flag(r["team"]), "Team": r["team"], "Group": r["group"],
            "Win Group %": round(100 * r["p_win_group"], 1),
            "R16 %": round(100 * r["p_r16"], 1),
            "QF %": round(100 * r["p_qf"], 1),
            "SF %": round(100 * r["p_sf"], 1),
            "Final %": round(100 * r["p_final"], 1),
            "Champion %": round(100 * r["p_champion"], 1),
        }
        for _, r in _bracket_df.iterrows()
    ]
    _bracket_out = pd.DataFrame(_bracket_rows)
    st.dataframe(
        _bracket_out,
        column_config={
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Team": st.column_config.TextColumn("Team", width="medium"),
            "Group": st.column_config.TextColumn("Group", width="small"),
        },
        width="content", hide_index=True,
        height=min(len(_bracket_out) * 35 + 38, 850),
    )

    _path = fb.most_likely_bracket(_finals_groups, _ratings)
    st.markdown("##### Most likely path to the trophy")
    st.caption(
        "The higher-rated side at every single match, start to finish -- "
        "a plausible path through this exact draw, not the same thing as "
        "the probability table above."
    )
    _r16_labels = {
        "M37": "Winner A v Runner-up C", "M38": "Runner-up A v Runner-up B",
        "M39": "Winner B v 3rd place", "M40": "Winner C v 3rd place",
        "M41": "Winner F v 3rd place", "M42": "Runner-up D v Runner-up E",
        "M43": "Winner D v Runner-up F", "M44": "Winner E v 3rd place",
    }
    _path_rows = [
        {"Stage": "Round of 16", "Fixture": _label, "Winner": _path["r16"][_m]}
        for _m, _label in _r16_labels.items()
    ]
    for _m, _label in (
        ("M45", "M39 v M37"), ("M46", "M41 v M42"), ("M47", "M44 v M43"), ("M48", "M40 v M38"),
    ):
        _path_rows.append({"Stage": "Quarter-final", "Fixture": _label, "Winner": _path["qf"][_m]})
    for _m, _label in (("M49", "M45 v M46"), ("M50", "M47 v M48")):
        _path_rows.append({"Stage": "Semi-final", "Fixture": _label, "Winner": _path["sf"][_m]})
    _path_rows.append({"Stage": "Final", "Fixture": "M49 v M50", "Winner": _path["champion"]})
    _path_df = pd.DataFrame(_path_rows)
    st.dataframe(_path_df, width="content", hide_index=True, height=len(_path_df) * 35 + 38)
    st.success(f"🏆 Most likely champion: **{_path['champion']}**")


def _render_qualifying_chances() -> None:
    st.caption(
        "Each nation's own overall chance to reach the Euro 2028 finals tournament at "
        "all, broken down by route -- unlike \"Predict all groups\" above (which "
        "conditions everything on ONE sampled draw), this averages over the draw's "
        "own randomness too, since the real draw hasn't happened yet (still scheduled "
        "6 December 2026). Uses today's [Nation Strength Rankings](/nation_power_rankings); "
        "\"Host reservation\" and \"Play-off\" are the same documented stand-ins "
        "euro_2028_finals_bracket.py's own module docstring explains (the real "
        "play-off pool also includes Nations League teams this site has no data "
        "for), just aggregated here over many simulated draws instead of one."
    )
    if st.button("🎯  Calculate qualifying chances", type="primary", use_container_width=True):
        st.session_state["euro2028_qual_chances_clicked"] = True

    if not st.session_state.get("euro2028_qual_chances_clicked"):
        st.info("Press **🎯 Calculate qualifying chances** to run the simulation.")
        return

    _ratings = gp.load_ratings()
    if not _ratings:
        st.warning(
            "nation_power_rankings.csv isn't available yet -- predictions are "
            "falling back to a flat default rating for every team."
        )

    with st.spinner("Simulating thousands of possible draws and qualifying campaigns…"):
        _chances_df = qo.simulate_qualifying_chances(_ratings, seed=seed_from_key(("euro2028_qual_chances",)))

    _rows = [
        {
            "Flag": _flag(r["team"]), "Team": r["team"], "Pot": r["pot"],
            "Win Group %": round(100 * r["Qualifying winner"], 1),
            "Runner-up %": round(100 * r["Qualifying runner-up"], 1),
            "Host Reservation %": round(100 * r["Host reservation"], 1),
            "Play-off %": round(100 * r["Play-off (simplified)"], 1),
            "Qualified %": round(100 * r["qualified"], 1),
        }
        for _, r in _chances_df.iterrows()
    ]
    _out = pd.DataFrame(_rows)
    st.dataframe(
        _out,
        column_config={
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Team": st.column_config.TextColumn("Team", width="medium"),
            "Pot": st.column_config.NumberColumn("Pot", width="small"),
        },
        width="content", hide_index=True, height=min(len(_out) * 35 + 38, 1200),
    )


if view == "Simulator":
    _render_simulator()
else:
    _render_qualifying_chances()
