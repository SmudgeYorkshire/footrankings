"""
2026 FIFA World Cup — Projections, Playoff Bracket, Group Stage, Knockout.

Predictions are based on national-team Elo ratings (eloratings.net).
"""

from __future__ import annotations
import random
import streamlit as st
import pandas as pd
import numpy as np

from world_cup_2026 import (
    WC_GROUPS, WC_ELO, WC_FLAGS,
    UEFA_PLAYOFF_PATHS, FIFA_IC_PLAYOFFS, IC_PLAYOFF_INFO, WC_FORMAT,
)

# ---------------------------------------------------------------------------
# Elo model helpers (neutral ground — no home advantage in WC)
# ---------------------------------------------------------------------------

_UEFA_HOME_ADV = 75  # Elo-point home advantage for UEFA qualifying play-off matches


def _elo_win_prob(elo_a: float, elo_b: float, home_adv: float = 0.0) -> float:
    """P(A beats B). home_adv adds Elo points to A (use for home-ground matches)."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a - home_adv) / 400.0))


def _match_probs(elo_a: float, elo_b: float) -> tuple[float, float, float]:
    """Returns (p_win_A, p_draw, p_win_B)."""
    diff = abs(elo_a - elo_b)
    p_draw = max(0.18, 0.27 - diff * 0.00022)
    p_raw = _elo_win_prob(elo_a, elo_b)
    p_win_a = p_raw * (1.0 - p_draw)
    p_win_b = (1.0 - p_raw) * (1.0 - p_draw)
    return p_win_a, p_draw, p_win_b


def _resolve_elo(team: str) -> float:
    """Return Elo, falling back to average for unknown teams."""
    return float(WC_ELO.get(team, 1700))


def _flag(team: str) -> str:
    return WC_FLAGS.get(team, "🏳️")


def _path_winner_elo(path_key: str) -> float:
    """Weighted average Elo of likely winner of a UEFA playoff path."""
    path = UEFA_PLAYOFF_PATHS[path_key]
    s1a, s1b = path["semifinal_1"]
    s2a, s2b = path["semifinal_2"]
    e1a, e1b = _resolve_elo(s1a), _resolve_elo(s1b)
    e2a, e2b = _resolve_elo(s2a), _resolve_elo(s2b)
    # P(each team wins their semi — respect per-match neutral flags)
    _h1 = 0.0 if path.get("neutral_sf1", path.get("neutral", False)) else _UEFA_HOME_ADV
    _h2 = 0.0 if path.get("neutral_sf2", path.get("neutral", False)) else _UEFA_HOME_ADV
    _hf = path.get("neutral_final", path.get("neutral", False))
    p_s1a = _elo_win_prob(e1a, e1b, _h1)
    p_s1b = 1 - p_s1a
    p_s2a = _elo_win_prob(e2a, e2b, _h2)
    p_s2b = 1 - p_s2a
    # Build all 4 possible final matchups and weight
    # Final hosted by SF2 winner — SF1 winner plays away
    total_elo = 0.0
    for winner1, elo1, p1 in [(s1a, e1a, p_s1a), (s1b, e1b, p_s1b)]:
        for winner2, elo2, p2 in [(s2a, e2a, p_s2a), (s2b, e2b, p_s2b)]:
            _fadv = 0.0 if _hf else -_UEFA_HOME_ADV  # winner2 (SF2 winner) hosts
            p_final_w1 = _elo_win_prob(elo1, elo2, _fadv)
            total_elo += p1 * p2 * (p_final_w1 * elo1 + (1 - p_final_w1) * elo2)
    return total_elo


def _effective_elo(team: str) -> float:
    """Elo, resolving UEFA playoff placeholders to expected winner Elo."""
    if team.startswith("UEFA PO Path "):
        key = team.replace("UEFA PO Path ", "").replace(" Winner", "")
        return _path_winner_elo(key)
    return _resolve_elo(team)


# ---------------------------------------------------------------------------
# Group stage Monte Carlo simulation
# ---------------------------------------------------------------------------

def _simulate_group_once(teams: list[str], elos: list[float]) -> list[tuple[str, int, int, int]]:
    """
    Single group simulation.
    Returns list of (team, pts, gf, ga) sorted by (pts desc, gd desc, gf desc).
    """
    pts  = {t: 0 for t in teams}
    gf   = {t: 0 for t in teams}
    ga   = {t: 0 for t in teams}
    elo  = dict(zip(teams, elos))

    # All pairings: MD1 (0v1, 2v3), MD2 (0v2, 1v3), MD3 (0v3, 1v2)
    matchups = [(0,1),(2,3),(0,2),(1,3),(0,3),(1,2)]
    for i, j in matchups:
        ta, tb = teams[i], teams[j]
        pa, pd_, pb = _match_probs(elo[ta], elo[tb])
        # Expected goals proportional to Elo advantage, base 1.25 per team
        base = 1.25
        ratio = (elo[ta] - elo[tb]) / 400.0
        exp_a = base * 10 ** (ratio * 0.5)
        exp_b = base * 10 ** (-ratio * 0.5)
        ga_goals = max(0, int(np.random.poisson(exp_a)))
        gb_goals = max(0, int(np.random.poisson(exp_b)))
        if ga_goals > gb_goals:
            pts[ta] += 3
        elif ga_goals == gb_goals:
            pts[ta] += 1
            pts[tb] += 1
        else:
            pts[tb] += 3
        gf[ta] += ga_goals;  ga[ta] += gb_goals
        gf[tb] += gb_goals;  ga[tb] += ga_goals

    results = [(t, pts[t], gf[t], ga[t]) for t in teams]
    results.sort(key=lambda x: (x[1], x[2]-x[3], x[2]), reverse=True)
    return results


def _simulate_group_once_with_preds(
    teams: list[str],
    elos:  list[float],
    fixed: dict,
) -> list[tuple]:
    """Like _simulate_group_once but with some match results pre-fixed."""
    pts = {t: 0 for t in teams}
    gf  = {t: 0 for t in teams}
    ga  = {t: 0 for t in teams}
    elo = dict(zip(teams, elos))
    for i, j in [(0,1),(2,3),(0,2),(1,3),(0,3),(1,2)]:
        ta, tb = teams[i], teams[j]
        if (ta, tb) in fixed:
            g_a, g_b = fixed[(ta, tb)]
        elif (tb, ta) in fixed:
            g_b, g_a = fixed[(tb, ta)]
        else:
            ratio = (elo[ta] - elo[tb]) / 400.0
            base  = 1.25
            g_a = max(0, int(np.random.poisson(base * 10 ** ( ratio * 0.5))))
            g_b = max(0, int(np.random.poisson(base * 10 ** (-ratio * 0.5))))
        if g_a > g_b:    pts[ta] += 3
        elif g_a == g_b: pts[ta] += 1; pts[tb] += 1
        else:            pts[tb] += 3
        gf[ta] += g_a; ga[ta] += g_b
        gf[tb] += g_b; ga[tb] += g_a
    res = [(t, pts[t], gf[t], ga[t]) for t in teams]
    res.sort(key=lambda x: (x[1], x[2] - x[3], x[2]), reverse=True)
    return res


def simulate_group_manual(group_key: str, fixed: dict, n: int = 20_000) -> pd.DataFrame:
    """Monte Carlo group simulation with some results pre-fixed (uncached)."""
    teams = WC_GROUPS[group_key]
    elos  = [_effective_elo(t) for t in teams]
    finish = {t: [0, 0, 0, 0] for t in teams}
    for _ in range(n):
        for pos, (team, *_) in enumerate(
            _simulate_group_once_with_preds(teams, elos, fixed)
        ):
            finish[team][pos] += 1
    rows = []
    for t, elo in zip(teams, elos):
        p1, p2, p3, p4 = [c / n * 100 for c in finish[t]]
        rows.append({
            "Team":      _flag(t) + " " + t,
            "Elo":       int(elo),
            "1st %":     round(p1, 1),
            "2nd %":     round(p2, 1),
            "3rd %":     round(p3, 1),
            "4th %":     round(p4, 1),
            "Advance %": round(p1 + p2 + (8 / 12) * p3, 1),
        })
    df = (pd.DataFrame(rows)
          .sort_values("Advance %", ascending=False)
          .reset_index(drop=True))
    df.index += 1
    return df


@st.cache_data(show_spinner=False)
def simulate_group(group_key: str, n: int = 20_000) -> pd.DataFrame:
    """
    Monte Carlo group simulation.
    Returns DataFrame: Team, Elo, Avg Pts, 1st%, 2nd%, 3rd%, 4th%, Advance%
    """
    teams = WC_GROUPS[group_key]
    elos  = [_effective_elo(t) for t in teams]

    finish_counts = {t: [0, 0, 0, 0] for t in teams}

    np.random.seed(42)
    for _ in range(n):
        res = _simulate_group_once(teams, elos)
        for pos, (team, *_) in enumerate(res):
            finish_counts[team][pos] += 1

    rows = []
    for t, elo in zip(teams, elos):
        cnts = finish_counts[t]
        p1, p2, p3, p4 = [c/n*100 for c in cnts]
        # 8 of 12 third-place teams advance → 67% of 3rd-place finishers advance
        adv = p1 + p2 + (8/12) * p3
        rows.append({
            "Team":     _flag(t) + " " + t,
            "Elo":      int(elo),
            "1st %":    p1,
            "2nd %":    p2,
            "3rd %":    p3,
            "4th %":    p4,
            "Advance %": adv,
        })

    df = pd.DataFrame(rows)
    df.sort_values("Advance %", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.index += 1
    return df


# ---------------------------------------------------------------------------
# Tournament winner simulation (all 48 teams)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def simulate_tournament(n: int = 20_000) -> pd.DataFrame:
    """
    Full Monte Carlo tournament simulation.
    Returns DataFrame: Team, Elo, Groups%, R16%, QF%, SF%, Final%, Win%
    """
    all_teams: dict[str, list[str]] = {}
    for g, teams in WC_GROUPS.items():
        all_teams[g] = teams

    elo_map = {t: _effective_elo(t) for g in WC_GROUPS.values() for t in g}

    reach = {t: {k: 0 for k in ["groups","r16","qf","sf","final","win"]}
             for teams in WC_GROUPS.values() for t in teams}

    def _ko_match(ta, tb):
        pa = _elo_win_prob(elo_map[ta], elo_map[tb])
        return ta if random.random() < pa else tb

    np.random.seed(42)
    random.seed(42)
    for _ in range(n):
        # Simulate all groups
        group_results: dict[str, list[tuple]] = {}
        for g, teams in WC_GROUPS.items():
            elos = [elo_map[t] for t in teams]
            group_results[g] = _simulate_group_once(teams, elos)

        # Collect 1st, 2nd, 3rd per group
        firsts   = {g: group_results[g][0][0] for g in WC_GROUPS}
        seconds  = {g: group_results[g][1][0] for g in WC_GROUPS}
        thirds   = {g: group_results[g][2][0] for g in WC_GROUPS}

        # Pick 8 best third-place teams (by pts then gd then gf)
        third_sorted = sorted(
            [(g, group_results[g][2]) for g in WC_GROUPS],
            key=lambda x: (x[1][1], x[1][2]-x[1][3], x[1][2]),
            reverse=True,
        )
        best_thirds = {g for g, _ in third_sorted[:8]}

        # All R32 participants
        r32_teams: list[str] = []
        for g in sorted(WC_GROUPS.keys()):
            r32_teams.append(firsts[g])
            r32_teams.append(seconds[g])
        for g in sorted(WC_GROUPS.keys()):
            if g in best_thirds:
                r32_teams.append(thirds[g])

        for t in r32_teams:
            reach[t]["groups"] += 1

        # Knockout: simplified random bracket (full FIFA bracket is complex)
        random.shuffle(r32_teams)
        bracket = r32_teams[:32]

        def _run_round(pool):
            winners = []
            for i in range(0, len(pool), 2):
                if i+1 < len(pool):
                    winners.append(_ko_match(pool[i], pool[i+1]))
                else:
                    winners.append(pool[i])
            return winners

        r16 = _run_round(bracket)
        for t in r16:
            reach[t]["r16"] += 1

        qf = _run_round(r16)
        for t in qf:
            reach[t]["qf"] += 1

        sf = _run_round(qf)
        for t in sf:
            reach[t]["sf"] += 1

        final = _run_round(sf)
        for t in final:
            reach[t]["final"] += 1

        champion = _run_round(final)
        for t in champion:
            reach[t]["win"] += 1

    rows = []
    for t in (team for teams in WC_GROUPS.values() for team in teams):
        r = reach[t]
        rows.append({
            "Team":      _flag(t) + " " + t,
            "Elo":       int(elo_map[t]),
            "Groups %":  r["groups"] / n * 100,
            "R16 %":     r["r16"]    / n * 100,
            "QF %":      r["qf"]     / n * 100,
            "SF %":      r["sf"]     / n * 100,
            "Final %":   r["final"]  / n * 100,
            "Win %":     r["win"]    / n * 100,
        })

    df = pd.DataFrame(rows)
    df.sort_values("Win %", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.index += 1
    return df


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _pct_bar(value: float, max_val: float = 100.0, color: str = "#1a73e8") -> str:
    """Returns an HTML progress bar string."""
    width = min(100, value / max_val * 100) if max_val else 0
    return (
        f'<div style="background:#e8e8e8;border-radius:4px;height:8px;width:100%">'
        f'<div style="background:{color};width:{width:.1f}%;height:8px;border-radius:4px"></div>'
        f'</div>'
    )


def _render_match_odds(team_a: str, team_b: str) -> None:
    """Display a single match with Elo win probabilities."""
    ea = _resolve_elo(team_a)
    eb = _resolve_elo(team_b)
    pa, pd_, pb = _match_probs(ea, eb)

    fa, fb = _flag(team_a), _flag(team_b)
    col1, col2, col3 = st.columns([3, 1, 3])
    with col1:
        st.markdown(f"### {fa} {team_a}")
        st.caption(f"Elo: **{ea}**")
    with col2:
        st.markdown(
            f"<div style='text-align:center;margin-top:8px'>"
            f"<b style='color:#1a73e8'>{pa*100:.0f}%</b> | "
            f"<b style='color:#888'>{pd_*100:.0f}%</b> | "
            f"<b style='color:#e53935'>{pb*100:.0f}%</b></div>",
            unsafe_allow_html=True,
        )
        st.caption("W · D · W")
    with col3:
        st.markdown(f"### {fb} {team_b}")
        st.caption(f"Elo: **{eb}**")


def _style_group_df(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Colour-code the group projection table."""
    def _row_style(row):
        styles = [""] * len(row)
        adv = row.get("Advance %", 0)
        if adv >= 70:
            bg = "background-color:#e8f5e9"  # green
        elif adv >= 40:
            bg = "background-color:#fff9c4"  # yellow
        else:
            bg = "background-color:#ffebee"  # red
        return [bg] * len(row)

    fmt = {
        "1st %":     "{:.1f}%",
        "2nd %":     "{:.1f}%",
        "3rd %":     "{:.1f}%",
        "4th %":     "{:.1f}%",
        "Advance %": "{:.1f}%",
    }
    return df.style.apply(_row_style, axis=1).format(fmt)


def _style_tournament_df(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    fmt = {
        "Groups %": "{:.1f}%",
        "R16 %":    "{:.1f}%",
        "QF %":     "{:.1f}%",
        "SF %":     "{:.1f}%",
        "Final %":  "{:.1f}%",
        "Win %":    "{:.1f}%",
    }
    def _row_style(row):
        win = row.get("Win %", 0)
        if win >= 10:
            bg = "background-color:#e3f2fd"
        elif win >= 5:
            bg = "background-color:#e8f5e9"
        elif win >= 1:
            bg = "background-color:#fff9c4"
        else:
            bg = ""
        return [bg] * len(row)
    return df.style.apply(_row_style, axis=1).format(fmt)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_uefa_playoff() -> None:
    st.markdown("## UEFA Play-off for World Cup")
    st.markdown(
        "Four paths decide the final four European spots. "
        "**Semi-finals: March 26** — **Finals: March 31, 2026.** "
        "Predictions are based on Elo ratings from [eloratings.net](https://www.eloratings.net/)."
    )

    cols = st.columns(2)
    for idx, (path_key, path) in enumerate(UEFA_PLAYOFF_PATHS.items()):
        with cols[idx % 2]:
            st.markdown(f"### Path {path_key} → Group {path['winner_group']}")
            s1a, s1b = path["semifinal_1"]
            s2a, s2b = path["semifinal_2"]
            e1a, e1b = _resolve_elo(s1a), _resolve_elo(s1b)
            e2a, e2b = _resolve_elo(s2a), _resolve_elo(s2b)

            # Knockout: draws go to ET/pens; first-listed team hosts unless match is neutral
            _neutral_sf1   = path.get("neutral_sf1",   path.get("neutral", False))
            _neutral_sf2   = path.get("neutral_sf2",   path.get("neutral", False))
            _neutral_final = path.get("neutral_final", path.get("neutral", False))
            p1a = _elo_win_prob(e1a, e1b, 0.0 if _neutral_sf1 else _UEFA_HOME_ADV); p1b = 1.0 - p1a
            p2a = _elo_win_prob(e2a, e2b, 0.0 if _neutral_sf2 else _UEFA_HOME_ADV); p2b = 1.0 - p2a

            # Semi-final 1
            _sf1_prefix = "⚪" if _neutral_sf1 else "🏠"
            st.markdown(f"**Semi-final 1** *(March 26)*")
            st.markdown(
                f"{_sf1_prefix} {_flag(s1a)} **{s1a}** "
                f"<span style='color:#1a73e8'>{p1a*100:.0f}%</span> vs "
                f"<span style='color:#e53935'>{p1b*100:.0f}%</span> "
                f"**{s1b}** {_flag(s1b)}",
                unsafe_allow_html=True,
            )

            # Semi-final 2
            _sf2_prefix = "⚪" if _neutral_sf2 else "🏠"
            st.markdown(f"**Semi-final 2** *(March 26)*")
            st.markdown(
                f"{_sf2_prefix} {_flag(s2a)} **{s2a}** "
                f"<span style='color:#1a73e8'>{p2a*100:.0f}%</span> vs "
                f"<span style='color:#e53935'>{p2b*100:.0f}%</span> "
                f"**{s2b}** {_flag(s2b)}",
                unsafe_allow_html=True,
            )

            # Final: hosted by SF2 winner (they play at home); SF1 winner always plays away
            st.markdown(f"**Final** *(March 31)*")
            final_probs: dict[str, float] = {}
            for winner1, elo1, p1 in [(s1a, e1a, p1a), (s1b, e1b, p1b)]:
                for winner2, elo2, p2 in [(s2a, e2a, p2a), (s2b, e2b, p2b)]:
                    # winner2 (SF2 winner) hosts → negative fadv for winner1 (SF1 winner plays away)
                    _fadv = 0.0 if _neutral_final else -_UEFA_HOME_ADV
                    pf = _elo_win_prob(elo1, elo2, _fadv)
                    final_probs[winner1] = final_probs.get(winner1, 0) + p1 * p2 * pf
                    final_probs[winner2] = final_probs.get(winner2, 0) + p1 * p2 * (1 - pf)

            # Sort by probability
            fp_sorted = sorted(final_probs.items(), key=lambda x: -x[1])
            best = fp_sorted[0][0]
            rows_fp = []
            for team, prob in fp_sorted:
                rows_fp.append({"Team": f"{_flag(team)} {team}", "Win Path %": f"{prob*100:.1f}%"})
            df_fp = pd.DataFrame(rows_fp)
            st.dataframe(df_fp, hide_index=True, use_container_width=True)
            st.markdown(
                f"**Predicted qualifier:** {_flag(best)} **{best}** "
                f"→ joins Group {path['winner_group']}",
            )
            st.divider()


def _render_group_stage() -> None:
    st.markdown("## Group Stage Projections")
    st.caption(
        "Monte Carlo simulation (20,000 runs) using Elo ratings. "
        "Advance % = P(1st) + P(2nd) + 0.67 × P(3rd)."
    )

    group_keys = sorted(WC_GROUPS.keys())
    group_sel  = st.selectbox("Select Group", group_keys,
                              format_func=lambda g: f"Group {g}")

    teams = WC_GROUPS[group_sel]
    elos  = [_effective_elo(t) for t in teams]

    # Quick team overview
    st.markdown(f"### Group {group_sel}")
    team_cols = st.columns(4)
    for i, (t, elo) in enumerate(zip(teams, elos)):
        with team_cols[i]:
            st.metric(f"{_flag(t)} {t}", f"Elo {int(elo)}")

    st.markdown("---")

    with st.spinner("Running simulation…"):
        df = simulate_group(group_sel)

    st.markdown("#### Projected Group Standings")
    st.dataframe(_style_group_df(df), use_container_width=True)

    # Show all group matchups with odds
    st.markdown("#### Group Fixtures & Odds")
    matchups = [(0,1),(2,3),(0,2),(1,3),(0,3),(1,2)]
    md_labels = ["MD1","MD1","MD2","MD2","MD3","MD3"]
    prev_md = None
    for (i, j), md in zip(matchups, md_labels):
        if md != prev_md:
            st.markdown(f"**Matchday {md[-1]}**")
            prev_md = md
        ta, tb = teams[i], teams[j]
        ea, eb = _effective_elo(ta), _effective_elo(tb)
        pa, pd_, pb = _match_probs(ea, eb)
        st.markdown(
            f"{_flag(ta)} **{ta}** "
            f"<span style='color:#1a73e8'>{pa*100:.0f}%</span> · "
            f"<span style='color:#888'>{pd_*100:.0f}%</span> · "
            f"<span style='color:#e53935'>{pb*100:.0f}%</span> "
            f"**{tb}** {_flag(tb)}",
            unsafe_allow_html=True,
        )


def _render_knockout() -> None:
    st.markdown("## Tournament Winner Projections")
    st.caption(
        "Full Monte Carlo simulation (20,000 runs). "
        "Bracket seeding is simplified — actual FIFA bracket depends on group finish positions. "
        "These probabilities reflect each team's overall tournament strength."
    )

    with st.spinner("Running full tournament simulation…"):
        df = simulate_tournament()

    st.markdown("### All Teams — Tournament Outlook")
    top20 = df.head(20).copy()
    st.dataframe(_style_tournament_df(top20), use_container_width=True)

    st.markdown("#### Top 10 Tournament Favourites")
    top10 = df.head(10)
    max_win = float(top10["Win %"].max())
    for _, row in top10.iterrows():
        team_label = row["Team"]
        win_pct    = float(row["Win %"])
        final_pct  = float(row["Final %"])
        col1, col2, col3 = st.columns([3, 1, 4])
        with col1:
            st.markdown(f"**{team_label}** (Elo {row['Elo']})")
        with col2:
            st.markdown(f"**{win_pct:.1f}%**")
        with col3:
            bar_html = _pct_bar(win_pct, max_win)
            st.markdown(bar_html, unsafe_allow_html=True)
            st.caption(f"Final: {final_pct:.1f}%  SF: {float(row['SF %']):.1f}%")

    st.divider()
    st.markdown("### Full Table (all 48 teams)")
    st.dataframe(_style_tournament_df(df), use_container_width=True)


def _render_fifa_playoff() -> None:
    st.markdown("## FIFA Inter-Confederation Play-offs")
    st.markdown(
        "Six teams from five confederations compete for the final **two World Cup spots**. "
        "The two highest-ranked teams (DR Congo and Iraq) receive **byes** directly to the finals. "
        "**Semi-finals: March 26** — **Finals: March 31, 2026.** "
        "All matches played in Mexico (single-leg; extra time + penalties if tied). "
        "Predictions based on Elo ratings from [eloratings.net](https://www.eloratings.net/)."
    )

    cols = st.columns(2)
    for idx, (path_key, path) in enumerate(FIFA_IC_PLAYOFFS.items()):
        with cols[idx]:
            st.markdown(f"### Pathway {path_key} → Group {path['winner_group']}")
            bye_team     = path["bye_team"]
            sf_a, sf_b   = path["semifinal"]
            e_bye        = _resolve_elo(bye_team)
            e_sf_a       = _resolve_elo(sf_a)
            e_sf_b       = _resolve_elo(sf_b)

            # Knockout: draws go to ET/pens; neutral venue — no home advantage
            p_sf_a = _elo_win_prob(e_sf_a, e_sf_b); p_sf_b = 1.0 - p_sf_a

            # ── Semi-final ────────────────────────────────────────────────
            st.markdown(f"**Semi-final** *(March 26 · {path['semi_venue']})*")
            st.markdown(
                f"{_flag(sf_a)} **{sf_a}** "
                f"<span style='color:#1a73e8'>{p_sf_a*100:.0f}%</span> vs "
                f"<span style='color:#e53935'>{p_sf_b*100:.0f}%</span> "
                f"**{sf_b}** {_flag(sf_b)}",
                unsafe_allow_html=True,
            )
            st.caption("Neutral venue · extra time & penalties if level after 90 min")

            # ── Final ─────────────────────────────────────────────────────
            st.markdown(f"**Final** *(March 31 · {path['final_venue']})*")
            st.markdown(
                f"{_flag(bye_team)} **{bye_team}** *(bye — seeded)* "
                f"<span style='color:#888'>Elo {int(e_bye)}</span>",
                unsafe_allow_html=True,
            )
            st.markdown("vs. winner of semi-final above")

            # Weighted win probabilities (neutral; sums to 100%)
            final_probs: dict[str, float] = {}
            for sf_winner, e_sw, p_sw in [(sf_a, e_sf_a, p_sf_a), (sf_b, e_sf_b, p_sf_b)]:
                pf_bye = _elo_win_prob(e_bye, e_sw)
                final_probs[bye_team]   = final_probs.get(bye_team, 0)   + p_sw * pf_bye
                final_probs[sf_winner]  = final_probs.get(sf_winner, 0)  + p_sw * (1 - pf_bye)

            # ── Overall pathway win table ─────────────────────────────────
            st.markdown("**Overall pathway win probability:**")
            all_teams = [bye_team, sf_a, sf_b]
            conf_labels = {
                "DR Congo": "CAF", "Iraq": "AFC",
                "Jamaica": "CONCACAF", "Bolivia": "CONMEBOL",
                "Suriname": "CONCACAF", "New Caledonia": "OFC",
            }
            rows = []
            for t in sorted(all_teams, key=lambda x: -final_probs.get(x, 0)):
                prob = final_probs.get(t, 0)
                rows.append({
                    "Team":         f"{_flag(t)} {t}",
                    "Confederation": conf_labels.get(t, ""),
                    "Elo":          int(_resolve_elo(t)),
                    "Win %":        f"{prob*100:.1f}%",
                    "Role":         "Seeded (bye)" if t == bye_team else "Semi-final",
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)

            best = max(final_probs, key=final_probs.get)
            st.markdown(
                f"**Predicted qualifier:** {_flag(best)} **{best}** → joins Group {path['winner_group']}",
            )
            st.divider()


def _render_my_predictions() -> None:
    st.markdown("## My Predictions")
    st.caption(
        "Personal picks based on Elo projections, current form, and tournament experience."
    )

    st.markdown("### UEFA Play-off predicted qualifiers")
    po_preds = [
        ("A", "Italy",   "🇮🇹"),
        ("B", "Ukraine", "🇺🇦"),
        ("C", "Turkey",  "🇹🇷"),
        ("D", "Denmark", "🇩🇰"),
    ]
    for path_key, team, flag in po_preds:
        group = UEFA_PLAYOFF_PATHS[path_key]["winner_group"]
        st.markdown(f"- **Path {path_key}**: {flag} **{team}** → Group {group}")

    st.divider()

    st.markdown("### Predicted Group Winners & Runners-up")
    gw_data = {
        "A": ("Mexico",        "South Korea"),
        "B": ("Switzerland",   "Italy"),
        "C": ("Brazil",        "Morocco"),
        "D": ("United States", "Australia"),
        "E": ("Germany",       "Ecuador"),
        "F": ("Netherlands",   "Japan"),
        "G": ("Belgium",       "Egypt"),
        "H": ("Spain",         "Uruguay"),
        "I": ("France",        "Norway"),
        "J": ("Argentina",     "Austria"),
        "K": ("Portugal",      "Colombia"),
        "L": ("England",       "Croatia"),
    }
    rows = []
    for g, (w, ru) in gw_data.items():
        rows.append({
            "Group": f"Group {g}",
            "Winner":        f"{_flag(w)} {w}",
            "Runner-up":     f"{_flag(ru)} {ru}",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.divider()

    st.markdown("### Predicted Knockout Results")
    ko_data = [
        ("Round of 32",  "Brazil, Argentina, Spain, France, Germany, England, Netherlands, Portugal, "
                         "Belgium, Uruguay, United States, Colombia, Senegal, Japan, Croatia, Norway"),
        ("Round of 16",  "Brazil, Argentina, Spain, France, Germany, England, Netherlands, Portugal"),
        ("Quarter-finals","Brazil, Argentina, Spain, France"),
        ("Semi-finals",   "Argentina, Spain"),
        ("Winner 🏆",     "Argentina 🇦🇷"),
    ]
    for stage, teams_str in ko_data:
        st.markdown(f"**{stage}:** {teams_str}")

    st.divider()
    st.info(
        "💡 **Note:** These are personal projections made in March 2026, "
        "before the tournament begins. Group-stage upsets are expected — "
        "the 48-team format with 8 best third-place qualifiers increases volatility."
    )


# ---------------------------------------------------------------------------
# Manual Predictions tab
# ---------------------------------------------------------------------------

def _render_manual_predictions_wc() -> None:
    st.markdown("## 🔮 Manual Predictions")
    st.caption(
        "Enter predicted scores for group stage matches. "
        "Unset matches will be simulated using Elo ratings."
    )

    group_keys = sorted(WC_GROUPS.keys())
    group_sel  = st.selectbox(
        "Select Group", group_keys,
        format_func=lambda k: f"Group {k}",
        key="wc_manual_group_sel",
    )

    teams       = WC_GROUPS[group_sel]
    _MATCHUPS   = [(0,1),(2,3),(0,2),(1,3),(0,3),(1,2)]
    _MD_LABELS  = ["MD1","MD1","MD2","MD2","MD3","MD3"]
    match_pairs = [(teams[i], teams[j]) for i, j in _MATCHUPS]

    ver_key = f"wc_manual_ver_{group_sel}"
    sim_key = f"wc_manual_sim_{group_sel}"
    if ver_key not in st.session_state:
        st.session_state[ver_key] = 0

    match_df = pd.DataFrame([
        {"MD":   _MD_LABELS[k],
         "Home": f"{_flag(ta)} {ta}",
         "HG":   None,
         "AG":   None,
         "Away": f"{_flag(tb)} {tb}"}
        for k, (ta, tb) in enumerate(match_pairs)
    ])

    col_cfg = {
        "MD":   st.column_config.TextColumn("MD",   disabled=True, width="small"),
        "Home": st.column_config.TextColumn("Home", disabled=True),
        "HG":   st.column_config.NumberColumn("HG", min_value=0, max_value=20, step=1),
        "AG":   st.column_config.NumberColumn("AG", min_value=0, max_value=20, step=1),
        "Away": st.column_config.TextColumn("Away", disabled=True),
    }
    edited = st.data_editor(
        match_df,
        column_config=col_cfg,
        disabled=["MD", "Home", "Away"],
        hide_index=True,
        use_container_width=True,
        key=f"wc_pred_editor_{group_sel}_{st.session_state[ver_key]}",
    )

    # Extract filled predictions
    filled_mask = edited[["HG", "AG"]].notna().all(axis=1)
    fixed_results: dict = {}
    for idx in edited[filled_mask].index:
        ta, tb = match_pairs[idx]
        fixed_results[(ta, tb)] = (int(edited.at[idx, "HG"]), int(edited.at[idx, "AG"]))

    # Live standings from filled predictions
    if fixed_results:
        pts = {t: 0 for t in teams}; w = {t: 0 for t in teams}
        d   = {t: 0 for t in teams}; l = {t: 0 for t in teams}
        gf  = {t: 0 for t in teams}; ga = {t: 0 for t in teams}
        for (ta, tb), (g_a, g_b) in fixed_results.items():
            if g_a > g_b:    pts[ta] += 3; w[ta] += 1; l[tb] += 1
            elif g_a == g_b: pts[ta] += 1; pts[tb] += 1; d[ta] += 1; d[tb] += 1
            else:            pts[tb] += 3; w[tb] += 1; l[ta] += 1
            gf[ta] += g_a; ga[ta] += g_b
            gf[tb] += g_b; ga[tb] += g_a
        st_rows = sorted(
            [{"Team": f"{_flag(t)} {t}", "P": w[t]+d[t]+l[t],
              "W": w[t], "D": d[t], "L": l[t],
              "GF": gf[t], "GA": ga[t], "GD": gf[t]-ga[t], "Pts": pts[t]}
             for t in teams],
            key=lambda r: (r["Pts"], r["GD"], r["GF"]), reverse=True,
        )
        st.markdown("#### Predicted Group Standings")
        st.dataframe(pd.DataFrame(st_rows), hide_index=True, use_container_width=True)

    st.divider()

    n_sim   = 20_000
    pred_fp = (
        group_sel,
        tuple(sorted((ta, tb, g_a, g_b)
                     for (ta, tb), (g_a, g_b) in fixed_results.items())),
        n_sim,
    )

    col_run, col_clear = st.columns([3, 1])
    with col_run:
        if st.button(f"▶  Run {n_sim:,} simulations",
                     key=f"wc_run_{group_sel}", use_container_width=True):
            with st.spinner("Simulating…"):
                _df = simulate_group_manual(group_sel, fixed_results, n_sim)
            st.session_state[sim_key] = {"df": _df, "fp": pred_fp}
    with col_clear:
        if st.button("↺ Clear", key=f"wc_clear_{group_sel}", use_container_width=True):
            st.session_state[ver_key] = st.session_state.get(ver_key, 0) + 1
            st.session_state.pop(sim_key, None)
            st.rerun()

    cached = st.session_state.get(sim_key)
    if cached:
        if cached["fp"] != pred_fp:
            st.warning("⚠️ Predictions changed since last run — re-run to update.")
        st.markdown("#### Advancement Probabilities")
        st.dataframe(
            cached["df"].style.format({
                "1st %": "{:.1f}%", "2nd %": "{:.1f}%",
                "3rd %": "{:.1f}%", "4th %": "{:.1f}%",
                "Advance %": "{:.1f}%",
            }),
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_world_cup() -> None:
    st.markdown(
        "<h3 style='margin:0'>🌍 2026 FIFA World Cup"
        "<span style='font-weight:400;color:#555'> — USA · Canada · Mexico</span></h3>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"June 11 – July 26, 2026 · 48 teams · 12 groups · "
        f"Elo-based predictions (eloratings.net)"
    )
    st.divider()

    tab_po, tab_fifa, tab_groups, tab_ko, tab_manual, tab_picks = st.tabs([
        "🏆 UEFA Play-off",
        "🌍 FIFA Play-offs",
        "⚽ Group Stage",
        "🥊 Knockout",
        "🔮 Manual Predictions",
        "🎯 My Predictions",
    ])

    with tab_po:
        _render_uefa_playoff()

    with tab_fifa:
        _render_fifa_playoff()

    with tab_groups:
        _render_group_stage()

    with tab_ko:
        _render_knockout()

    with tab_manual:
        _render_manual_predictions_wc()

    with tab_picks:
        _render_my_predictions()


# Run page
render_world_cup()
