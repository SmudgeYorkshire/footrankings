"""
Shared finish-probability table renderer.

Extracted from football_rankings.py (2026-10-12) so european.py can reuse
it for the new European-competition League Phase position table --
football_rankings.py itself can't be imported directly, same reason
cup_predictions.py was split out earlier: it's a Streamlit page script with
top-level rendering code (a bare main_content() call at module scope,
plus sidebar code at import time) that runs immediately on import, not a
pure library module. football_rankings.py and football_rankings_tier2.py
both now import render_prob_table from here instead of defining their own
copy (admin.py's own render_prob_table/_green_col are a separate, simpler,
intentionally-unrelated implementation -- not migrated here).
"""

import pandas as pd
import streamlit as st

from simulator import cert_value, cert_cell_format, CLINCHED_SENTINEL, ELIMINATED_SENTINEL


def _green_col(s: pd.Series) -> list[str]:
    """Return CSS background-color styles interpolated white→dark-green per
    column. A cell holding render_prob_table's clinched/eliminated sentinel
    (see simulator.cert_value) gets its own fixed style instead of being
    folded into the gradient -- at ±1000 it would otherwise either blow out
    vmax (washing out every real percentage in the column) or, for the
    eliminated sentinel, go negative and break the t=v/vmax ratio entirely."""
    normal = s[(s > ELIMINATED_SENTINEL / 2) & (s < CLINCHED_SENTINEL / 2)]
    vmax = normal.max() if len(normal) else 0
    styles = []
    for v in s:
        if v >= CLINCHED_SENTINEL / 2:
            styles.append("background-color: #1b5e20; color: white; font-weight: bold")
            continue
        if v <= ELIMINATED_SENTINEL / 2:
            styles.append("background-color: #f0f0f0; color: #999")
            continue
        if vmax == 0:
            styles.append("")
            continue
        t = v / vmax
        r = int(255 * (1 - t))
        g = int(255 - t * 155)   # 255 → 100
        b = int(255 * (1 - t))
        text = "white" if t > 0.65 else "black"
        styles.append(f"background-color: rgb({r},{g},{b}); color: {text}")
    return styles


def _euro_style_cell(val):
    s = str(val).upper()
    if "UCL"  in s: return "color: #1a73e8; font-weight: bold"
    if "UEL"  in s: return "color: #f9ab00; font-weight: bold"
    if "UECL" in s: return "color: #34a853; font-weight: bold"
    return ""


def _status_style_pred(val):
    """Colour + bold for status labels in the predicted-standings Status column."""
    s = str(val).lower().rstrip()
    if "relega"           in s: return "color: #ea4335; font-weight: bold"
    if "champions league" in s: return "color: #1a73e8; font-weight: bold"
    if "europa league"    in s: return "color: #f9ab00; font-weight: bold"
    if "uecl play-offs"   in s: return "color: #34a853; font-weight: bold"
    if "conference"       in s: return "color: #34a853; font-weight: bold"
    if "final four"       in s: return "color: #2e7d32; font-weight: bold"
    if "championship"     in s: return "color: #2e7d32; font-weight: bold"
    if "play-off"         in s: return "color: #2e7d32; font-weight: bold"
    if "play out"         in s: return "color: #f9ab00; font-weight: bold"
    if "middle"           in s: return "color: #f9ab00; font-weight: bold"
    return ""


def _status_for_pos(pos: int, status_map: dict) -> str:
    """Return the status label for a given position from a {pos: label} dict."""
    return (status_map or {}).get(pos, "")


def render_prob_table(probs: pd.DataFrame, badge_lookup: dict = None,
                      expected_pts: dict = None, european_spots: dict = None,
                      title: str = "Season finish probabilities", zones: dict = None,
                      status_map: dict = None, team_overrides: dict = None,
                      bounds: dict = None, title_emoji: bool = False):
    """Color-coded finish-probability table, sorted by expected finishing
    position (Σ position × probability, ascending) -- the single-number
    summary of each team's whole distribution, consistent with what this
    table actually shows. xPts (season points expectation) is a related
    but distinct stat -- still displayed as its own column when supplied,
    but no longer the sort key, since it can disagree with the position
    probabilities sitting right next to it (e.g. a team with a fatter
    title-chance tail outranking a steadier, slightly-higher-xPts rival).

    status_map: unified {pos: label} dict from league_status.py (preferred).
    european_spots / zones: legacy params, used only if status_map is not provided.
    team_overrides: {team_name: label} — fixed status for specific teams
        regardless of position. Genuinely team-specific, static cases only
        (config.py's own team_status_overrides fallback); the live
        cup-winner cascade (cup_cascade.resolve_live_overrides) is keyed by
        POSITION instead and merged straight into status_map/zones by its
        caller, not passed here -- a team-keyed lookup would keep showing a
        stale label wherever that team is NOW displayed even after they've
        moved well away from the position the cascade actually concerns
        (confirmed live 2026-10-13: a team dropping out of contention kept
        its old European-zone tag at its new, much lower row).
    bounds: {team: (best_reachable, worst_reachable)} from simulator.position_bounds
        -- when given, any cell mathematically proven impossible/guaranteed
        (see that function's own docstring) shows "X"/"✓" instead of the raw
        percentage. Only pass this for a table whose underlying "current
        points" are real or a self-consistent hypothesis -- never for a
        table seeded from a PROJECTED starting position (e.g. a pre-split
        group projected forward to the real split round), since that would
        assert certainty about a number that's itself still a guess.
    title_emoji: when True (and bounds is given), a clinched 1st place shows
        "🏆" instead of the plain "✓" every other clinched cell gets. Only
        pass True when position 1 in THIS table really is the outright
        champion -- not a sub-group's own 1st (Middle Group, Relegation
        Round) and not a League Phase's 1st (the knockout stage still
        decides the actual winner from there).
    """
    # Resolve unified status map
    _smap = status_map if status_map is not None else (european_spots or {})

    pos_nums = pd.Series({c: int(c) for c in probs.columns})
    expected_rank = probs.mul(pos_nums, axis=1).sum(axis=1)
    probs = probs.loc[expected_rank.sort_values(ascending=True).index]
    df = (probs * 100).round(1)
    badge_lookup = badge_lookup or {}
    teams = list(probs.index)
    df.insert(0, "Team", teams)
    df.insert(0, "Badge", [badge_lookup.get(t, "") for t in teams])
    if expected_pts:
        df["xPts"] = [round(expected_pts.get(t, 0), 1) for t in teams]
    df.index = range(1, len(df) + 1)
    df.index.name = "Pos"
    if _smap or team_overrides:
        df["Status"] = [
            (team_overrides or {}).get(t) or _status_for_pos(pos, _smap)
            for pos, t in zip(df.index, df["Team"])
        ]
    non_pos = {"Badge", "Team", "xPts", "Status"}
    pos_cols = [c for c in df.columns if c not in non_pos]
    if bounds:
        for t in df.index:
            team = df.loc[t, "Team"]
            best, worst = bounds.get(team, (1, len(pos_cols)))
            for pos_str in pos_cols:
                pos = int(pos_str)
                certain = True if best == worst == pos else (False if not (best <= pos <= worst) else None)
                if certain is not None:
                    df.loc[t, pos_str] = cert_value(df.loc[t, pos_str], certain, is_title=title_emoji and pos == 1)
    styled = (
        df.style
        .apply(_green_col, axis=0, subset=pos_cols)
        .format(cert_cell_format, subset=pos_cols)
        .set_properties(subset=["Team"], **{"font-weight": "bold"})
    )
    if expected_pts:
        styled = styled.format("{:.1f}", subset=["xPts"])
    if "Status" in df.columns:
        styled = (styled
                  .map(_euro_style_cell,  subset=["Status"])
                  .map(_status_style_pred, subset=["Status"]))
    col_cfg = {
        "Badge":  st.column_config.ImageColumn("", width="small"),
        "Team":   st.column_config.TextColumn("Team"),
        "xPts":   st.column_config.NumberColumn("xPts", format="%.1f", width="small"),
        "Status": st.column_config.TextColumn("Status", width=110),
    }
    st.markdown(f"#### {title}")
    st.dataframe(styled, column_config=col_cfg, width="content",
                 height=len(probs) * 35 + 42)
