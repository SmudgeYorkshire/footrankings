"""
2026-27 UEFA Nations League — group stage projections and League A's
predicted knockout bracket.

Groups are the real UEFA draw (see nations_league_data.py); ratings are
eloratings.net's current national-team Elo, scraped by
scrape_elo_ratings.py into ratings/nations_league_elo.csv. Real fixtures/
results come from API-Football (nations_league_fixtures.py) -- once a
match is played it locks in and only what's left to play gets simulated,
the same "real results + simulate the rest" approach used across the
rest of this site (see european.py's League Stage Predictions).
"""

import random
from datetime import datetime

import streamlit as st
import pandas as pd

from flags import flag_url
from nations_league_data import (
    NL_GROUPS, NL_FLAG_ALIASES, LEAGUE_OUTCOME_RULES, LEAGUE_LEAVE_LABELS, NL_TIEBREAKERS, NL_TIEBREAK_RULES,
    position_status_labels,
)
from nations_league_simulator import (
    load_nl_ratings, simulate_group, simulate_league_a_knockouts, simulate_league_outcomes,
    cross_group_ranking, group_fixture_odds, group_expected_points, project_qf_entries,
    project_playoff_entries, project_2028_composition, league_a_relegation_pool_split,
    most_likely_group_order, group_position_bounds, league_label_certainty,
    apply_cross_league_playoff_correction,
)
from nations_league_fixtures import group_fixtures
from _split_season import compute_full_standings

st.title("🌍 2026/27 UEFA Nations League")


def _flag(team: str) -> str:
    return flag_url(NL_FLAG_ALIASES.get(team, team))


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# "X" (mathematically eliminated) / "✓" (mathematically clinched) replace
# the usual "%.1f%%" text wherever group_position_bounds/league_label_
# certainty have proven one or the other -- both are reserved for real
# certainty (see those functions' own docstrings for exactly what they
# will and won't assert), never just a simulated probability that
# happens to round to 0.0% or 100.0%.
#
# These cells are encoded as a NUMBER (the real percentage, or a sentinel
# far outside the real 0-100 range), not a pre-formatted "X"/"73.2%"
# string -- an earlier version used plain text (via st.column_config.
# TextColumn) so our own row order could put clinched/eliminated rows at
# the right end, but that broke the column's own built-in click-to-sort
# header: Streamlit compares TextColumn values lexicographically, so
# "6.0%" sorts ahead of "46.1%" (same bug a plain numeric column would
# have if formatted as text first). Keeping the column genuinely numeric
# and only overriding its DISPLAY via a pandas Styler .format() callable
# (same pattern football_rankings.py's render_prob_table already uses)
# means both our own default order and the reader's own click-to-sort
# compare real numbers throughout, never text.
_CLINCHED_SENTINEL = 1_000.0
_ELIMINATED_SENTINEL = -1_000.0


def _cert_value(value: float, certain: bool | None) -> float:
    if certain is True:
        return _CLINCHED_SENTINEL
    if certain is False:
        return _ELIMINATED_SENTINEL
    return value


def _cert_cell_format(v: float) -> str:
    if v == _CLINCHED_SENTINEL:
        return "✓"
    if v == _ELIMINATED_SENTINEL:
        return "X"
    return f"{v:.1f}%"


def _format_date(date_str: str) -> str:
    """'2026-09-25' -> 'Friday, 25 September' -- no year, since every
    fixture on this page is within the 2026-27 season."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    return f"{dt.strftime('%A')}, {dt.day} {dt.strftime('%B')}"


ratings_df = load_nl_ratings()
if ratings_df.empty:
    st.warning(
        "No Elo ratings found yet — run `scrape_elo_ratings.py` to fetch them from eloratings.net."
    )
    st.stop()


def _render_table(standings: list[dict], height: int, league_name: str) -> None:
    status_by_pos = position_status_labels(league_name, len(standings))
    rows = []
    for row in sorted(standings, key=lambda r: int(r.get("intRank", 99))):
        gd = int(row.get("intGoalDifference", 0))
        rank = int(row.get("intRank", 0))
        rows.append({
            "Rank": rank,
            "Flag": _flag(row["strTeam"]),
            "Team": row["strTeam"],
            "P": int(row.get("intPlayed", 0)),
            "W": int(row.get("intWin", 0)),
            "D": int(row.get("intDraw", 0)),
            "L": int(row.get("intLoss", 0)),
            "GF": int(row.get("intGoalsFor", 0)),
            "GA": int(row.get("intGoalsAgainst", 0)),
            "GD": f"+{gd}" if gd > 0 else str(gd),
            "Pts": int(row.get("intPoints", 0)),
            "Status": status_by_pos.get(rank, ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.set_properties(subset=["Team"], **{"font-weight": "bold"}),
        column_config={
            "Rank": st.column_config.NumberColumn("#", width="small"),
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Team": st.column_config.TextColumn("Team", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="large"),
        },
        use_container_width=True, hide_index=True, height=height,
    )


def _render_fixtures(played: list[dict], remaining: list[dict], height: int) -> None:
    if not played and not remaining:
        st.info("No fixtures found for this group yet.")
        return
    rows = []
    for f in sorted(played + remaining, key=lambda f: (f.get("dateEvent", ""), f.get("strTime", ""))):
        decided = f in played
        score = f"{f.get('intHomeScore', '')}–{f.get('intAwayScore', '')}" if decided else "—"
        rows.append({
            "Date": _format_date(f.get("dateEvent", "")),
            "HB": _flag(f.get("strHomeTeam", "")),
            "Home": f.get("strHomeTeam", ""),
            "Score": score,
            "Away": f.get("strAwayTeam", ""),
            "AB": _flag(f.get("strAwayTeam", "")),
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.set_properties(subset=["Home", "Away"], **{"font-weight": "bold"}),
        column_config={
            "HB": st.column_config.ImageColumn("", width="small"),
            "AB": st.column_config.ImageColumn("", width="small"),
        },
        use_container_width=True, hide_index=True, height=height,
    )


def _render_match_odds(teams: list[str], played: list[dict], remaining: list[dict], height: int) -> None:
    """Home/Draw/Away win chance for every fixture in the group, played or
    not -- the Poisson model doesn't need a result to have an opinion, so
    this shows the same pre-match read for already-decided games too
    rather than only the ones still to come."""
    fixtures = sorted(played + remaining, key=lambda f: (f.get("dateEvent", ""), f.get("strTime", "")))
    if not fixtures:
        st.info("No fixtures found for this group yet.")
        return
    odds_list = group_fixture_odds(teams, fixtures, ratings_df)
    rows = []
    for f, odds in zip(fixtures, odds_list):
        rows.append({
            "Date": _format_date(f.get("dateEvent", "")),
            "HB": _flag(f.get("strHomeTeam", "")),
            "Home": f.get("strHomeTeam", ""),
            "Home %": round(odds["home_win"] * 100, 1),
            "Draw %": round(odds["draw"] * 100, 1),
            "Away %": round(odds["away_win"] * 100, 1),
            "Away": f.get("strAwayTeam", ""),
            "AB": _flag(f.get("strAwayTeam", "")),
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.set_properties(subset=["Home", "Away"], **{"font-weight": "bold"}),
        column_config={
            "HB": st.column_config.ImageColumn("", width="small"),
            "AB": st.column_config.ImageColumn("", width="small"),
            "Home %": st.column_config.NumberColumn("Home %", format="%.1f%%", width="small"),
            "Draw %": st.column_config.NumberColumn("Draw %", format="%.1f%%", width="small"),
            "Away %": st.column_config.NumberColumn("Away %", format="%.1f%%", width="small"),
        },
        use_container_width=True, hide_index=True, height=height,
    )


def _render_predictions(
    teams: list[str], probs: pd.DataFrame, exp_pts: dict[str, float],
    bounds: dict[str, tuple[int, int]] | None = None,
) -> None:
    n_teams = len(teams)
    pos_cols = [_ordinal(pos) for pos in range(1, n_teams + 1)]
    rows = []
    for team in probs.index:
        row = {"Flag": _flag(team), "Team": team}
        best, worst = bounds.get(team, (1, n_teams)) if bounds else (1, n_teams)
        for pos in range(1, n_teams + 1):
            # Full precision, not rounded -- rounding before sorting can
            # tie two teams who both display e.g. "0.0%" but have
            # different real chances, leaving their relative order
            # arbitrary. Only _cert_cell_format rounds, for display.
            value = probs.loc[team, str(pos)] * 100
            certain = True if best == worst == pos else (False if not (best <= pos <= worst) else None)
            row[_ordinal(pos)] = _cert_value(value, certain)
        row["xPTS"] = round(exp_pts.get(team, 0.0), 1)
        rows.append(row)
    # Rows default-sort by 1st-place chance -- a team clinched 1st goes to
    # the top, one eliminated from 1st to the bottom (see _cert_value's
    # sentinels), everyone else by their real chance in between. Ties in
    # 1st-place chance cascade to 2nd, then 3rd, etc. (the full row of
    # position columns, left to right) instead of leaving tied teams in
    # arbitrary order.
    rows.sort(key=lambda r: tuple(r[c] for c in pos_cols), reverse=True)
    display_df = pd.DataFrame(rows)
    styled = display_df.style.format(_cert_cell_format, subset=pos_cols)

    col_cfg = {
        "Flag": st.column_config.ImageColumn("", width="small"),
        "Team": st.column_config.TextColumn("Team", width="medium"),
    }
    for pos_col in pos_cols:
        col_cfg[pos_col] = st.column_config.NumberColumn(pos_col, width="small")
    col_cfg["xPTS"] = st.column_config.NumberColumn(
        "xPTS", width="small", help="Expected points", format="%.1f",
    )

    st.dataframe(
        styled, column_config=col_cfg, use_container_width=True,
        hide_index=True, height=len(display_df) * 35 + 38,
    )


# Both play-off pools' win/lose columns (see nations_league_simulator.
# _PLAYOFF_POOLS) are display-renamed to the same generic "Winner in
# Play-offs"/"Loser in Play-offs" text -- table position (next to their
# own pool's re-derived aggregate) tells them apart, not distinct
# wording. Internal DataFrame column names stay the raw simulator labels
# (so probs_df/LEAGUE_LEAVE_LABELS need no parallel renaming); only each
# column's st.column_config label is overridden, which is what lets two
# different columns both display as "Winner in Play-offs" without a
# dict-key collision. Each tuple is (win_col, lose_col, aggregate label
# re-derived as their sum and inserted ahead of both -- pool-entry chance
# first, then how it resolved).
_PLAYOFF_SPLITS = [
    ("Promoted in Play-offs", "Relegated in Play-offs", "Relegation Play-off"),
    ("Won Promotion Play-offs", "Lost Promotion Play-offs", "Promotion Play-offs"),
]
_WIN_DISPLAY = "Winner in Play-offs"
_LOSE_DISPLAY = "Loser in Play-offs"

# A league's terminal "arrived here" column should read as the TOTAL
# chance of ending up there next edition, not just its direct route --
# whichever OTHER raw label also leads to the exact same destination
# (winning or losing the relevant play-off) gets folded into that
# column's displayed value. "Relegation to League B" (League A): the
# bottom two (cross-group ranked) 4th-place teams go down directly, but
# so do the top two 4th-place/bottom two 3rd-place teams who then LOSE
# their relegation play-off. "Promotion" (League B/C): 1st place is
# promoted directly, but so is 2nd place if it WINS its promotion
# play-off -- League D has no such column so this is a no-op there.
_COMBINE_EXTRA = {
    "Relegation to League B": "Relegated in Play-offs",
    "Promotion": "Won Promotion Play-offs",
}

# Display-only rename for the direct-promotion column so it names its
# actual destination league instead of the generic "Promotion" -- the
# underlying rule label (and Status column text) is untouched.
_PROMOTION_DISPLAY_BY_LEAGUE = {
    "League B": "Promotion to League A",
    "League C": "Promotion to League B",
    "League D": "Promotion to League C",
}

# League B has no direct-relegation rule at all (see LEAGUE_OUTCOME_
# RULES) -- every 4th-place team enters the relegation play-off pool, so
# losing it is the ONLY way down. That's already shown as "Loser in
# Play-offs", but a reader shouldn't have to infer the real-world
# destination from a generic play-off label -- this adds an explicitly-
# named alias column (same value, right after "Stay in {league}") for
# whichever league needs it. League A/C don't: League A already has its
# own real "Relegation to League B" bucket (see _COMBINE_EXTRA above),
# and League C has no relegation path at all.
_EXTRA_ALIAS_COLUMN = {
    "League B": ("Relegation to League C", "Relegated in Play-offs"),
}


# Reverse of nations_league_simulator._PLAYOFF_POOLS -- lets the
# aggregate "pool entry chance" column below look up whether a team has
# mathematically CLINCHED reaching that pool (league_label_certainty sets
# this on the raw, pre-split label, never on the win/lose columns
# themselves -- see that function's own docstring for why).
_RAW_POOL_LABEL = {
    ("Promoted in Play-offs", "Relegated in Play-offs"): "Relegation Play-offs",
    ("Won Promotion Play-offs", "Lost Promotion Play-offs"): "Promotion Play-offs",
}


def _render_outcome_predictions(
    teams: list[str], probs_df: pd.DataFrame, league_name: str,
    certainty: dict[str, dict[str, bool]] | None = None,
) -> None:
    """One column per outcome-bucket label in probs_df (Quarterfinals,
    Promotion, Winner/Loser in Play-offs, ...) plus a "Stay in {league}"
    column: 1 minus whichever of those labels actually mean leaving the
    league next edition (see LEAGUE_LEAVE_LABELS) -- e.g. for League A
    that's just the two ways down (a lost relegation play-off or direct
    relegation), since reaching the Quarterfinals or winning a play-off
    both keep a team in League A. The Stay column is omitted entirely
    when every raw column already means leaving (League D: every position
    is a direct "Promotion", so it would always read 0%).

    certainty (from league_label_certainty): wherever it's proven a cell
    mathematically impossible or already clinched, that cell shows "X" or
    "✓" instead of the usual percentage -- see _cert_value."""
    leave_labels = LEAGUE_LEAVE_LABELS.get(league_name, set(probs_df.columns))
    bucket_cols = list(probs_df.columns)
    show_stay = not (set(bucket_cols) <= leave_labels)
    stay_label = f"Stay in {league_name}"
    cols = (bucket_cols[:1] + [stay_label] + bucket_cols[1:]) if show_stay else list(bucket_cols)

    extra_alias = _EXTRA_ALIAS_COLUMN.get(league_name)
    if extra_alias and show_stay and extra_alias[1] in bucket_cols:
        alias_name, alias_source = extra_alias
        cols.insert(cols.index(stay_label) + 1, alias_name)
    else:
        extra_alias = None

    active_splits = [s for s in _PLAYOFF_SPLITS if s[0] in cols and s[1] in cols]
    for win_col, lose_col, agg_col in active_splits:
        cols.insert(cols.index(win_col), agg_col)

    rows = []
    for t in teams:
        row = {"Flag": _flag(t), "Team": t}
        cert = (certainty or {}).get(t, {})
        raw = {c: float(probs_df.loc[t, c]) if t in probs_df.index else 0.0 for c in probs_df.columns}
        # Full precision throughout (not rounded) -- rounding before
        # sorting can tie two teams who both display e.g. "0.0%" but have
        # different real chances, leaving their order arbitrary. Only
        # _cert_cell_format rounds, for display.
        for c, v in raw.items():
            extra_label = _COMBINE_EXTRA.get(c, "")
            extra = raw.get(extra_label, 0.0)
            value = (v + extra) * 100
            own_cert, extra_cert = cert.get(c), cert.get(extra_label) if extra_label else None
            combined = True if (own_cert or extra_cert) else (
                False if own_cert is False and (not extra_label or extra_cert is False) else None
            )
            row[c] = _cert_value(value, combined)
        for win_col, lose_col, agg_col in active_splits:
            value = (raw[win_col] + raw[lose_col]) * 100
            pool_label = _RAW_POOL_LABEL.get((win_col, lose_col))
            pool_cert = cert.get(pool_label) if pool_label else None
            if pool_cert is None and cert.get(win_col) is False and cert.get(lose_col) is False:
                pool_cert = False
            row[agg_col] = _cert_value(value, pool_cert)
        if show_stay:
            leave_prob = sum(v for c, v in raw.items() if c in leave_labels)
            value = max(0.0, 1.0 - leave_prob) * 100
            stay_cert = True if all(cert.get(c) is False for c in leave_labels) else None
            row[stay_label] = _cert_value(value, stay_cert)
        if extra_alias:
            value = raw[extra_alias[1]] * 100
            row[extra_alias[0]] = _cert_value(value, cert.get(extra_alias[1]))
        rows.append(row)
    # Rows default-sort by cols[0] -- the league's headline qualifying
    # outcome (Quarterfinals/Promotion) -- clinched teams first, real
    # chances descending, eliminated last (see _cert_value's sentinels).
    # Ties cascade through the rest of the row's own columns, left to
    # right, instead of leaving tied teams in arbitrary order.
    rows.sort(key=lambda r: tuple(r[c] for c in cols), reverse=True)
    df = pd.DataFrame(rows)[["Flag", "Team"] + cols]
    styled = df.style.format(_cert_cell_format, subset=cols)

    promo_display = _PROMOTION_DISPLAY_BY_LEAGUE.get(league_name)
    display_overrides = {win: _WIN_DISPLAY for win, _, _ in active_splits}
    display_overrides.update({lose: _LOSE_DISPLAY for _, lose, _ in active_splits})
    if promo_display and "Promotion" in cols:
        display_overrides["Promotion"] = promo_display

    col_cfg = {
        "Flag": st.column_config.ImageColumn("", width="small"),
        "Team": st.column_config.TextColumn("Team", width="medium"),
    }
    for c in cols:
        col_cfg[c] = st.column_config.NumberColumn(display_overrides.get(c, c))
    st.dataframe(styled, column_config=col_cfg, use_container_width=True, hide_index=True, height=len(df) * 35 + 38)


def _blank_third_fourth_reps(groups: dict[str, list[str]], position: int) -> list[dict]:
    """Placeholder rows for a "ranked" pool before the group stage has
    settled anything -- no real team can be named yet, so each group gets
    a generic "Nth-placed team of X" label and dashes for every stat,
    matching how the top-level Promotion & Relegation tab's bracket
    tables show a pool rather than a guessed name."""
    ord_ = _ordinal(position)
    return [
        {"group": gname, "Team": f"{ord_}-placed team of {gname}",
         "Pld": "-", "W": "-", "D": "-", "L": "-", "GF": "-", "GA": "-", "GD": "-", "Pts": "-", "xPts": "-"}
        for gname in groups
    ]


def _current_third_fourth_reps(standings_by_group: dict[str, list[dict]], position: int) -> list[dict]:
    """Real teams currently sitting at `position` in each group, cross-
    ranked by their actual Pld/W/D/L/GF/GA/GD/Pts so far."""
    reps = cross_group_ranking(standings_by_group, position)
    rows = []
    for r in reps:
        gd = int(r.get("intGoalDifference", 0))
        rows.append({
            "group": r["group"], "Flag": _flag(r["strTeam"]), "Team": r["strTeam"],
            "Pld": int(r.get("intPlayed", 0)), "W": int(r.get("intWin", 0)), "D": int(r.get("intDraw", 0)),
            "L": int(r.get("intLoss", 0)), "GF": int(r.get("intGoalsFor", 0)), "GA": int(r.get("intGoalsAgainst", 0)),
            "GD": f"+{gd}" if gd > 0 else str(gd), "Pts": int(r.get("intPoints", 0)),
        })
    return rows


def _predicted_third_fourth_reps(
    standings_by_group: dict[str, list[dict]], group_probs: dict[str, pd.DataFrame],
    group_exp_pts: dict[str, dict[str, float]], position: int,
) -> list[dict]:
    """Whichever team is MOST LIKELY (per simulate_group's own position
    probabilities) to finish at `position` in each group, cross-ranked by
    projected final points (xPts = current Pts + expected points from
    whatever's left to play) then current GD/GF as a tiebreak -- real
    final GD/GF isn't knowable ahead of the remaining fixtures actually
    being played, so this reuses each team's record so far rather than
    inventing a projected one."""
    pos_col = str(position)
    reps = []
    for gname, standings in standings_by_group.items():
        team = group_probs[gname][pos_col].idxmax()
        row = next((r for r in standings if r["strTeam"] == team), {})
        gd = int(row.get("intGoalDifference", 0))
        gf = int(row.get("intGoalsFor", 0))
        xpts = round(group_exp_pts[gname].get(team, 0.0), 1)
        reps.append({
            "group": gname, "Flag": _flag(team), "Team": team,
            "Pld": int(row.get("intPlayed", 0)), "W": int(row.get("intWin", 0)), "D": int(row.get("intDraw", 0)),
            "L": int(row.get("intLoss", 0)), "GF": gf, "GA": int(row.get("intGoalsAgainst", 0)),
            "GD": f"+{gd}" if gd > 0 else str(gd), "xPts": xpts, "_sort": (xpts, gd, gf),
        })
    reps.sort(key=lambda r: r["_sort"], reverse=True)
    for r in reps:
        del r["_sort"]
    return reps


def _render_ranking_table(reps: list[dict], rule: tuple, pts_key: str = "Pts", blank: bool = False) -> None:
    """Renders one cross-group ranking table (see _blank/_current/
    _predicted_third_fourth_reps) with a Qualification column derived
    from `rule`'s n_top/label_top/n_bottom/label_bottom -- same shape as
    LEAGUE_OUTCOME_RULES' "ranked" rules. `blank` skips the qualification
    guess entirely (nothing's decided yet) and skips the pink highlight."""
    _, position, n_top, label_top, n_bottom, label_bottom = rule
    n = len(reps)
    quals = [None] * n
    if not blank:
        for i in range(min(n_top, n)):
            quals[i] = label_top
        for i in range(max(0, n - n_bottom), n):
            quals[i] = label_bottom
    rows = []
    for i, r in enumerate(reps):
        row = {"Pos": i + 1, "Grp": r["group"]}
        if "Flag" in r:
            row["Flag"] = r["Flag"]
        row["Team"] = r["Team"]
        for k in ("Pld", "W", "D", "L", "GF", "GA", "GD"):
            row[k] = r.get(k, "-")
        row[pts_key] = r.get(pts_key, "-")
        row["Qualification"] = "-" if blank else (quals[i] or "Safe")
        rows.append(row)
    df = pd.DataFrame(rows)
    col_cfg = {"Team": st.column_config.TextColumn("Team", width="medium")}
    if "Flag" in df.columns:
        col_cfg["Flag"] = st.column_config.ImageColumn("", width="small")
    if pts_key == "xPts" and not blank:
        col_cfg["xPts"] = st.column_config.NumberColumn("xPts", format="%.1f")

    if blank:
        st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True, height=len(df) * 35 + 38)
        return

    def _row_style(row):
        pink = row["Qualification"] != "Safe"
        return [f"background-color: {'#fbdcdc' if pink else ''}" for _ in row]

    styled = df.style.apply(_row_style, axis=1).set_properties(subset=["Team"], **{"font-weight": "bold"})
    st.dataframe(styled, column_config=col_cfg, use_container_width=True, hide_index=True, height=len(df) * 35 + 38)


def _group_states_from(groups: dict[str, list[str]], standings_by_group: dict[str, list[dict]],
                        remaining_by_group: dict[str, list[dict]]) -> dict[str, dict]:
    return {
        gname: {
            "teams": teams,
            "base_stats": {
                r["strTeam"]: {"pts": r["intPoints"], "gd": r["intGoalDifference"], "gf": r["intGoalsFor"]}
                for r in standings_by_group[gname]
            },
            "remaining": remaining_by_group[gname],
        }
        for gname, teams in groups.items()
    }


def _manual_predictions_tab(group_key: str, teams: list[str], roster: list[dict],
                             played: list[dict], remaining: list[dict], league_name: str) -> None:
    ver_key = f"nl_manual_ver_{group_key}"
    sim_key = f"nl_manual_sim_{group_key}"
    if ver_key not in st.session_state:
        st.session_state[ver_key] = 0

    if not remaining:
        st.info("All fixtures in this group have been played.")
        return

    fix_rows = []
    for f in remaining:
        fix_rows.append({
            "Date": _format_date(f.get("dateEvent", "")),
            "HB": _flag(f.get("strHomeTeam", "")),
            "Home": f.get("strHomeTeam", ""),
            "HG": pd.NA, "AG": pd.NA,
            "Away": f.get("strAwayTeam", ""),
            "AB": _flag(f.get("strAwayTeam", "")),
        })
    fix_df = pd.DataFrame(fix_rows)
    fix_df["HG"] = fix_df["HG"].astype(pd.Int64Dtype())
    fix_df["AG"] = fix_df["AG"].astype(pd.Int64Dtype())

    editor_key = f"nl_editor_{group_key}_{st.session_state[ver_key]}"
    height = len(remaining) * 35 + 38

    hdr_col, btn_col, _ = st.columns([2, 1, 3], vertical_alignment="center")
    metric_ph = hdr_col.empty()
    clear_ph = btn_col.empty()
    edited_df = st.data_editor(
        fix_df,
        column_config={
            "HB": st.column_config.ImageColumn("", width="small"),
            "Home": st.column_config.TextColumn("Home", width="medium"),
            "HG": st.column_config.NumberColumn("HG", min_value=0, max_value=20, step=1, width="small"),
            "AG": st.column_config.NumberColumn("AG", min_value=0, max_value=20, step=1, width="small"),
            "Away": st.column_config.TextColumn("Away", width="medium"),
            "AB": st.column_config.ImageColumn("", width="small"),
        },
        disabled=["Date", "HB", "Home", "Away", "AB"],
        use_container_width=True, hide_index=True, height=height, key=editor_key,
    )

    filled_mask = edited_df[["HG", "AG"]].notna().all(axis=1)
    metric_ph.markdown(f"### Predicted: {int(filled_mask.sum())} / {len(remaining)}")
    if clear_ph.button("🗑 Clear", use_container_width=True, key=f"nl_clear_{group_key}"):
        st.session_state[ver_key] += 1
        st.session_state.pop(sim_key, None)
        st.rerun()

    fix_by_pair = {(f["strHomeTeam"], f["strAwayTeam"]): f for f in remaining}
    predicted_as_played = []
    for _, row in edited_df[filled_mask].iterrows():
        pair = (row["Home"], row["Away"])
        if pair in fix_by_pair:
            entry = dict(fix_by_pair[pair])
            entry["intHomeScore"] = int(row["HG"])
            entry["intAwayScore"] = int(row["AG"])
            entry["strStatus"] = "FT"
            predicted_as_played.append(entry)

    predicted_pairs = {(f["strHomeTeam"], f["strAwayTeam"]) for f in predicted_as_played}
    unpredicted = [f for f in remaining
                   if (f["strHomeTeam"], f["strAwayTeam"]) not in predicted_pairs]
    updated_standings = compute_full_standings(roster, played + predicted_as_played, tiebreakers=NL_TIEBREAKERS)

    # Stashed every rerun (not just after "Run simulations") so League A's
    # cross-group Relegation Pool tab can pick up whatever's currently
    # entered here, even before this group's own simulation has been run.
    st.session_state[f"nl_manual_state_{group_key}"] = {
        "standings": updated_standings, "remaining": unpredicted,
    }

    st.divider()
    st.markdown("### Updated standings")
    _render_table(updated_standings, height=len(teams) * 35 + 38, league_name=league_name)

    fingerprint = (
        tuple(sorted((f["strHomeTeam"], f["strAwayTeam"], f["intHomeScore"], f["intAwayScore"])
                     for f in predicted_as_played)),
    )
    st.divider()
    st.markdown("### Projected final standings")
    cached = st.session_state.get(sim_key)
    if st.button("▶  Run simulations with predictions", type="primary",
                 use_container_width=True, key=f"nl_run_{group_key}"):
        with st.spinner("Simulating…"):
            probs, exp_pts = simulate_group(
                teams, ratings_df, n_sim=10_000,
                standings=updated_standings, remaining_fixtures=unpredicted,
                played_fixtures=played + predicted_as_played,
            )
        st.session_state[sim_key] = {"probs": probs, "exp_pts": exp_pts, "fingerprint": fingerprint}
        cached = st.session_state[sim_key]

    if cached:
        if cached["fingerprint"] != fingerprint:
            st.warning("⚠ Predictions changed since last run — press ▶ to update.")
        manual_state = {"G": {
            "teams": teams,
            "base_stats": {r["strTeam"]: {"pts": r["intPoints"]} for r in updated_standings},
            "remaining": unpredicted,
        }}
        _render_predictions(teams, cached["probs"], cached["exp_pts"], group_position_bounds(manual_state))
    else:
        st.info("Enter predictions above then press **▶ Run simulations**.")


league_names = list(NL_GROUPS.keys())
top_tabs = st.tabs(
    league_names + ["🔀 Promotion & Relegation", "🏆 Knockouts", "📜 Rules", "🔮 2028/29 Projections"]
)
league_tabs = top_tabs[:len(league_names)]
promo_releg_tab = top_tabs[-4]
knockout_chances_tab = top_tabs[-3]
rules_tab = top_tabs[-2]
projections_2028_tab = top_tabs[-1]

all_group_probs: dict[str, dict[str, pd.DataFrame]] = {}
all_outcome_probs: dict[str, pd.DataFrame] = {}
all_group_standings: dict[str, dict[str, list[dict]]] = {}
all_group_remaining: dict[str, dict[str, list[dict]]] = {}
all_group_played: dict[str, dict[str, list[dict]]] = {}
all_group_roster: dict[str, dict[str, list[dict]]] = {}
all_group_states: dict[str, dict[str, dict]] = {}
all_group_position_probs: dict[str, dict[str, pd.DataFrame]] = {}
all_league_seed: dict[str, int] = {}
all_league_certainty: dict[str, dict[str, dict[str, bool]]] = {}
all_league_bounds: dict[str, dict[str, tuple[int, int]]] = {}

# Simulate every league's own group stage FIRST, before rendering any of
# them, so the play-off win/lose correction below can see every league's
# pool-entry chances at once -- simulate_league_outcomes only ever sees
# one league's own roster at a time, so a team's real cross-league
# play-off opponent (e.g. a League C runner-up facing a League B
# relegation-pool team) isn't knowable until BOTH sides' simulations have
# run. group_fixtures() is cached, so fetching each group's data here and
# again inside the render loop below is cheap, not a double real pull.
with st.spinner("Simulating every league's group stage…"):
    for league_name in league_names:
        groups = NL_GROUPS[league_name]
        rules = LEAGUE_OUTCOME_RULES[league_name]
        # Shared across every simulate_league_outcomes() call for this
        # league this render pass (the main call here and the "Chances
        # of finishing 3rd or 4th" detail-table call further down) so
        # they're the same underlying replicates, just binned into
        # differently labelled buckets -- not two independently-random
        # simulations that could report slightly different numbers for
        # the same thing.
        league_seed = random.randint(0, 2**31 - 1)
        all_league_seed[league_name] = league_seed

        league_group_standings: dict[str, list[dict]] = {}
        league_group_remaining: dict[str, list[dict]] = {}
        league_group_played: dict[str, list[dict]] = {}
        league_group_roster: dict[str, list[dict]] = {}
        for group_name, teams in groups.items():
            played, remaining = group_fixtures(teams)
            roster = [{"strTeam": t} for t in teams]
            real_standings = compute_full_standings(roster, played, tiebreakers=NL_TIEBREAKERS)
            league_group_standings[group_name] = real_standings
            league_group_remaining[group_name] = remaining
            league_group_played[group_name] = played
            league_group_roster[group_name] = roster
        all_group_standings[league_name] = league_group_standings
        all_group_remaining[league_name] = league_group_remaining
        all_group_played[league_name] = league_group_played
        all_group_roster[league_name] = league_group_roster

        league_group_states = _group_states_from(groups, league_group_standings, league_group_remaining)
        all_group_states[league_name] = league_group_states
        outcome_probs, group_position_probs = simulate_league_outcomes(
            league_group_states, rules, ratings_df, n_sim=10_000, seed=league_seed,
        )
        all_outcome_probs[league_name] = outcome_probs
        all_group_position_probs[league_name] = group_position_probs
        all_league_bounds[league_name] = group_position_bounds(league_group_states)
        all_league_certainty[league_name] = league_label_certainty(league_group_states, rules)

    # Now that every league's pool-entry chances exist, replace each
    # play-off pool's Won/Lost split with the cross-league-aware win rate
    # (see apply_cross_league_playoff_correction's own docstring for why
    # simulate_league_outcomes' own internal split can't get this right
    # on its own). Mutates all_outcome_probs' DataFrames in place.
    apply_cross_league_playoff_correction(
        all_outcome_probs["League A"], "Relegation Play-offs",
        all_outcome_probs["League B"], "Promotion Play-offs",
        ratings_df,
    )
    apply_cross_league_playoff_correction(
        all_outcome_probs["League B"], "Relegation Play-offs",
        all_outcome_probs["League C"], "Promotion Play-offs",
        ratings_df,
    )

for league_tab, league_name in zip(league_tabs, league_names):
    with league_tab:
        groups = NL_GROUPS[league_name]
        rules = LEAGUE_OUTCOME_RULES[league_name]
        ranked_rules = [r for r in rules if r[0] == "ranked"]
        all_league_teams = [t for g in groups.values() for t in g]
        league_seed = all_league_seed[league_name]
        league_group_standings = all_group_standings[league_name]
        league_group_remaining = all_group_remaining[league_name]
        league_group_played = all_group_played[league_name]
        league_group_roster = all_group_roster[league_name]
        league_group_states = all_group_states[league_name]
        outcome_probs = all_outcome_probs[league_name]
        group_position_probs = all_group_position_probs[league_name]
        league_bounds = all_league_bounds[league_name]
        league_certainty = all_league_certainty[league_name]

        tab_labels = (
            list(groups.keys())
            + (["🥉 3rd/4th"] if ranked_rules else [])
            + ["📈 Predictions"]
        )
        all_tabs = st.tabs(tab_labels)
        group_tabs = all_tabs[:len(groups)]
        next_idx = len(groups)
        third_fourth_tab = None
        if ranked_rules:
            third_fourth_tab = all_tabs[next_idx]
            next_idx += 1
        pred_tab = all_tabs[next_idx]

        league_group_probs: dict[str, pd.DataFrame] = {}
        league_group_exp_pts: dict[str, dict[str, float]] = {}

        for group_tab, (group_name, teams) in zip(group_tabs, groups.items()):
            with group_tab:
                played = league_group_played[group_name]
                remaining = league_group_remaining[group_name]
                roster = league_group_roster[group_name]
                real_standings = league_group_standings[group_name]

                sub_table, sub_pred, sub_manual = st.tabs(
                    ["📅 Table & Fixtures", "🎯 Predictions", "🔮 Manual Predictions"]
                )

                with sub_table:
                    st.markdown("#### Table")
                    _render_table(real_standings, height=len(teams) * 35 + 38, league_name=league_name)
                    st.markdown("#### Fixtures")
                    _render_fixtures(played, remaining, height=len(played + remaining) * 35 + 38)
                    st.markdown("#### Match Outcome Chances")
                    _render_match_odds(teams, played, remaining, height=len(played + remaining) * 35 + 38)

                with sub_pred:
                    probs = group_position_probs[group_name]
                    exp_pts = group_expected_points(
                        teams, ratings_df, standings=real_standings, remaining_fixtures=remaining,
                    )
                    league_group_probs[group_name] = probs
                    league_group_exp_pts[group_name] = exp_pts
                    _render_predictions(teams, probs, exp_pts, league_bounds)
                    st.markdown("#### Group stage outcome chances")
                    _render_outcome_predictions(teams, outcome_probs, league_name, league_certainty)

                with sub_manual:
                    _manual_predictions_tab(f"{league_name}_{group_name}", teams, roster, played, remaining, league_name)

        all_group_probs[league_name] = league_group_probs

        if third_fourth_tab is not None:
            with third_fourth_tab:
                st.markdown("#### Ranking of 3rd/4th-placed teams")
                st.caption(
                    "These positions' fate depends on ranking against the other groups' teams finishing "
                    "the same position, not just this group -- see the top-level Promotion & Relegation "
                    "tab for how the resulting play-off pool plays out."
                )
                for rule in ranked_rules:
                    position = rule[1]
                    st.markdown(f"##### Ranking of {_ordinal(position)}-placed teams")
                    t_blank, t_current, t_predicted = st.tabs(
                        ["Blank", "Current standings", "Predicted standings"]
                    )
                    with t_blank:
                        _render_ranking_table(
                            _blank_third_fourth_reps(groups, position), rule, pts_key="Pts", blank=True,
                        )
                    with t_current:
                        _render_ranking_table(
                            _current_third_fourth_reps(league_group_standings, position), rule, pts_key="Pts",
                        )
                    with t_predicted:
                        _render_ranking_table(
                            _predicted_third_fourth_reps(
                                league_group_standings, league_group_probs, league_group_exp_pts, position,
                            ),
                            rule, pts_key="xPts",
                        )
                    st.divider()

                st.markdown("##### Chances of finishing 3rd or 4th")
                # Re-labelled copies of ranked_rules for this one table only: the
                # real LEAGUE_OUTCOME_RULES give the two paths into the pool the
                # SAME "Relegation Play-offs" label on purpose (see
                # nations_league_simulator.simulate_league_outcomes), but this
                # breakdown is specifically about telling those two paths apart.
                detail_rules = []
                for r in ranked_rules:
                    _, position, n_top, label_top, n_bottom, label_bottom = r
                    ord_ = _ordinal(position)
                    if position == 3:
                        top_text = f"Best two {ord_}-place - Stay in {league_name}"
                        bottom_text = f"Worst two {ord_}-place - {label_bottom}"
                    elif position == 4:
                        top_text = f"Best two {ord_}-place - {label_top}"
                        bottom_text = f"Worst two {ord_}-place - Relegated to League B"
                    else:
                        top_text = f"{ord_} place, {label_top}"
                        bottom_text = f"{ord_} place, {label_bottom}"
                    detail_rules.append(("ranked", position, n_top, top_text, n_bottom, bottom_text))
                with st.spinner("Simulating…"):
                    detail_probs, _ = simulate_league_outcomes(
                        _group_states_from(groups, league_group_standings, league_group_remaining),
                        detail_rules, ratings_df, n_sim=10_000, seed=league_seed,
                    )
                detail_certainty = league_label_certainty(league_group_states, detail_rules)
                detail_cert_cols = list(detail_probs.columns)
                detail_rows = []
                for t in all_league_teams:
                    row = {"Flag": _flag(t), "Team": t}
                    cert = detail_certainty.get(t, {})
                    for col in detail_cert_cols:
                        value = float(detail_probs.loc[t, col]) * 100
                        row[col] = _cert_value(value, cert.get(col))
                    detail_rows.append(row)
                detail_rows.sort(key=lambda r: tuple(r[c] for c in detail_cert_cols), reverse=True)
                detail_df = pd.DataFrame(detail_rows)
                detail_styled = detail_df.style.format(_cert_cell_format, subset=detail_cert_cols)
                detail_col_cfg = {
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                }
                for col in detail_cert_cols:
                    detail_col_cfg[col] = st.column_config.NumberColumn(col)
                st.dataframe(
                    detail_styled, column_config=detail_col_cfg, use_container_width=True,
                    hide_index=True, height=len(detail_df) * 35 + 38,
                )

        with pred_tab:
            st.markdown("#### Group Stage Outcome Predictions")
            st.caption(
                f"Every {league_name} nation's chance of landing in each group-stage outcome, jointly "
                "simulating all groups together so a cross-group-ranked outcome is correctly correlated "
                "rather than computed from independent per-group marginals."
            )
            _render_outcome_predictions(all_league_teams, outcome_probs, league_name, league_certainty)

with knockout_chances_tab:
    st.markdown("#### Knockouts")

    st.markdown("##### Quarter-finals format")
    st.caption(
        "The draw for the quarter-finals is held after the league phase, pairing each League A "
        "group winner with a runner-up from a different group. Legs played 25–27 Mar and 28–30 Mar 2027."
    )
    qf_format_df = pd.DataFrame(
        [{"Team 1": "Group runner-up", "Agg.": "", "Team 2": "Group winner",
          "1st leg": "25–27 Mar", "2nd leg": "28–30 Mar"}
         for _ in range(4)]
    )
    st.dataframe(qf_format_df, hide_index=True, use_container_width=True, height=len(qf_format_df) * 35 + 38)

    st.divider()
    st.markdown("##### Projected Quarterfinals Entries")
    st.caption(
        "The team most likely to finish 1st and 2nd in each League A group -- i.e. if exactly these "
        "eight nations are the ones who show up, each one's chance to prevail in the Quarterfinals, "
        "averaged over every valid winner-vs-different-group-runner-up draw."
    )
    qf_entries = project_qf_entries(all_group_probs["League A"], ratings_df)
    qf_entries_df = pd.DataFrame([
        {
            "Flag": _flag(r["team"]),
            "Team": r["team"],
            "Group": r["group"],
            "Role": r["role"],
            "Chance to prevail": r["prevail_pct"],
        }
        for _, r in qf_entries.iterrows()
    ])
    st.dataframe(
        qf_entries_df,
        column_config={
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Team": st.column_config.TextColumn("Team", width="medium"),
            "Group": st.column_config.TextColumn("Group", width="small"),
            "Role": st.column_config.TextColumn("Role", width="small"),
            "Chance to prevail": st.column_config.NumberColumn("Chance to prevail", format="%.1f%%", width="small"),
        },
        use_container_width=True, hide_index=True, height=len(qf_entries_df) * 35 + 38,
    )

    st.divider()
    st.markdown("##### Predictions")
    st.caption(
        "Winners will face Runners-up in the Quarterfinals, determined by a draw, and it will "
        "be an open draw for the Semifinals without seeding."
    )
    with st.spinner("Simulating the quarter-finals and Finals Four…"):
        ko = simulate_league_a_knockouts(all_group_probs["League A"], ratings_df, n_sim=10_000)

    a_certainty = all_league_certainty.get("League A", {})
    ko_cert_cols = ["Quarterfinals", "Semifinals", "Finals", "Winner"]
    ko_rows = []
    for team, r in ko.iterrows():
        qf_cert = a_certainty.get(team, {}).get("Quarterfinals")
        # Semifinals/Finals/Winner are knockout-contingent (an actual draw
        # and matches still to come), so they never get a "✓" from group-
        # stage math alone -- but a team eliminated from the Quarterfinals
        # is just as surely eliminated from everything past it, so "X"
        # cascades down from the same qf_cert fact.
        downstream_cert = False if qf_cert is False else None
        # Full precision throughout (not rounded) -- only _cert_cell_
        # format rounds, for display. Rows sort by Quarterfinals first
        # (clinched top, eliminated bottom, real chances descending), then
        # cascade through Semifinals/Finals/Winner as tiebreakers so two
        # teams level on Quarterfinals chance (or both eliminated) still
        # land in a sensible order instead of an arbitrary one.
        ko_rows.append({
            "Flag": _flag(team),
            "Team": team,
            "Quarterfinals": _cert_value(r["reached_qf"] * 100, qf_cert),
            "Semifinals": _cert_value(r["reached_finals_four"] * 100, downstream_cert),
            "Finals": _cert_value(r["reached_final"] * 100, downstream_cert),
            "Winner": _cert_value(r["won_competition"] * 100, downstream_cert),
        })
    ko_rows.sort(key=lambda r: tuple(r[c] for c in ko_cert_cols), reverse=True)
    ko_df = pd.DataFrame(ko_rows)
    ko_styled = ko_df.style.format(_cert_cell_format, subset=ko_cert_cols)
    ko_col_cfg = {
        "Flag": st.column_config.ImageColumn("", width="small"),
        "Team": st.column_config.TextColumn("Team", width="medium"),
        "Quarterfinals": st.column_config.NumberColumn("Quarterfinals", width="small"),
        "Semifinals": st.column_config.NumberColumn("Semifinals", width="small"),
        "Finals": st.column_config.NumberColumn("Finals", width="small"),
        "Winner": st.column_config.NumberColumn("Winner", width="small"),
    }
    st.dataframe(
        ko_styled, column_config=ko_col_cfg, use_container_width=True,
        hide_index=True, height=len(ko_df) * 35 + 38,
    )

with promo_releg_tab:
    st.markdown("#### Promotion & Relegation")
    st.caption(
        "UEFA's own promotion/relegation play-off bracket for March 2027. Exact pairings aren't drawn "
        "until after the group stage, so these show which pool each side is drawn from rather than "
        "real nations — see "
        "[Wikipedia](https://en.wikipedia.org/wiki/2026%E2%80%9327_UEFA_Nations_League#Promotion_and_relegation_play-offs)."
    )

    def _bracket_table(team2_label: str, team1_label: str) -> None:
        df = pd.DataFrame(
            [{"Team 1": team1_label, "Agg.": "", "Team 2": team2_label, "1st leg": "25–27 Mar", "2nd leg": "28–30 Mar"}
             for _ in range(4)]
        )
        st.dataframe(df, hide_index=True, use_container_width=True, height=len(df) * 35 + 38)

    st.markdown("##### League A vs League B")
    _bracket_table("League A third place/fourth place", "League B runner-up")

    st.markdown("##### League B vs League C")
    _bracket_table("League B fourth place", "League C runner-up")

    a_teams = [t for g in NL_GROUPS["League A"].values() for t in g]
    b_teams = [t for g in NL_GROUPS["League B"].values() for t in g]
    c_teams = [t for g in NL_GROUPS["League C"].values() for t in g]
    a_probs = all_outcome_probs["League A"]
    b_probs = all_outcome_probs["League B"]
    c_probs = all_outcome_probs["League C"]
    a_releg_pool_chance = a_probs["Promoted in Play-offs"] + a_probs["Relegated in Play-offs"]
    b_releg_pool_chance = b_probs["Promoted in Play-offs"] + b_probs["Relegated in Play-offs"]
    b_promo_pool_chance = b_probs["Won Promotion Play-offs"] + b_probs["Lost Promotion Play-offs"]
    c_promo_pool_chance = c_probs["Won Promotion Play-offs"] + c_probs["Lost Promotion Play-offs"]

    st.divider()
    st.markdown("##### Projected Promotion/Relegation Entries")
    st.caption(
        "The four teams most likely to land in each side of a pool -- i.e. if exactly these eight "
        "nations are the ones who show up, each one's chance to prevail in its two-legged tie, "
        "averaged over every way UEFA's open draw could pair the two pools."
    )

    # Each pool's 4 entrants must come from exactly one representative per
    # group (never a league-wide marginal probability's raw top-4, which
    # can double-book a team into two different pools at once -- see
    # project_playoff_entries' docstring) -- League A's is a genuine
    # cross-group ranking (league_a_relegation_pool_split), League B/C's
    # are single "direct rule" positions so each group's own most-likely
    # team at that position (most_likely_group_order) is exactly right.
    a_split = league_a_relegation_pool_split(all_group_probs["League A"], a_probs)
    a_playoff_pool = a_split["playoff_third"] + a_split["playoff_fourth"]
    b_order = {g: most_likely_group_order(p) for g, p in all_group_probs["League B"].items()}
    c_order = {g: most_likely_group_order(p) for g, p in all_group_probs["League C"].items()}
    b_runner_up_pool = [order[1] for order in b_order.values()]
    b_fourth_pool = [order[3] for order in b_order.values()]
    c_runner_up_pool = [order[1] for order in c_order.values()]

    def _projected_entries_table(higher_teams, higher_label, lower_teams, lower_label):
        entries = project_playoff_entries(higher_teams, higher_label, lower_teams, lower_label, ratings_df)
        df = pd.DataFrame([
            {
                "Flag": _flag(r["team"]), "Team": r["team"], "Pool": r["pool"],
                "Chance to prevail": r["prevail_pct"],
            }
            for _, r in entries.iterrows()
        ])
        st.dataframe(
            df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Pool": st.column_config.TextColumn("Pool", width="medium"),
                "Chance to prevail": st.column_config.NumberColumn("Chance to prevail", format="%.1f%%", width="small"),
            },
            use_container_width=True, hide_index=True, height=len(df) * 35 + 38,
        )

    st.markdown("###### League A vs League B")
    _projected_entries_table(
        a_playoff_pool, "League A third place/fourth place",
        b_runner_up_pool, "League B runner-up",
    )

    st.markdown("###### League B vs League C")
    _projected_entries_table(
        b_fourth_pool, "League B fourth place",
        c_runner_up_pool, "League C runner-up",
    )

    st.divider()
    st.markdown("##### Chances of reaching each play-off pool")

    def _role_chances(title: str, teams: list[str], chances: pd.Series, cert: dict[str, bool] | None = None) -> None:
        with st.expander(title):
            rows = []
            for t in teams:
                # Full precision, not rounded -- rounding first can tie
                # two teams who both display "0.0%" but have different
                # real chances. Only _cert_cell_format rounds, for display.
                value = float(chances.get(t, 0.0)) * 100
                certain = (cert or {}).get(t)
                rows.append({
                    "Flag": _flag(t), "Team": t,
                    "Chance": _cert_value(value, certain),
                })
            rows.sort(key=lambda r: r["Chance"], reverse=True)
            df = pd.DataFrame(rows)
            styled = df.style.format(_cert_cell_format, subset=["Chance"])
            st.dataframe(
                styled,
                column_config={
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "Chance": st.column_config.NumberColumn("Chance"),
                },
                use_container_width=True, hide_index=True, height=len(df) * 35 + 38,
            )

    a_cert = {t: c.get("Relegation Play-offs") for t, c in all_league_certainty.get("League A", {}).items()}
    b_cert = all_league_certainty.get("League B", {})
    c_cert = all_league_certainty.get("League C", {})
    _role_chances("League A third place/fourth place", a_teams, a_releg_pool_chance, a_cert)
    _role_chances("League B runner-up", b_teams, b_promo_pool_chance,
                  {t: c.get("Promotion Play-offs") for t, c in b_cert.items()})
    _role_chances("League B fourth place", b_teams, b_releg_pool_chance,
                  {t: c.get("Relegation Play-offs") for t, c in b_cert.items()})
    _role_chances("League C runner-up", c_teams, c_promo_pool_chance,
                  {t: c.get("Promotion Play-offs") for t, c in c_cert.items()})

with rules_tab:
    st.markdown("#### Tiebreaking Rules")
    st.caption(
        "UEFA's official criteria for ranking teams level on points within a group, from "
        "[Wikipedia](https://en.wikipedia.org/wiki/2026%E2%80%9327_UEFA_Nations_League#Tiebreakers). "
        "Criteria 1-3 use only the matches played among the tied teams; if a 3+-way tie survives all "
        "three, criterion 4 restarts 1-3 among just whichever teams are still tied. Criteria 5-9 fall "
        "back to each team's record across the whole group. Every group table, simulation and "
        "Manual Predictions projection on this page uses this exact order."
    )
    for i, (desc, implemented) in enumerate(NL_TIEBREAK_RULES, start=1):
        if implemented:
            st.markdown(f"{i}. {desc}")
        else:
            st.markdown(f"{i}. {desc} — *not applied here, see note below*")
    st.info(
        "Criteria 10 and 11 aren't applied: disciplinary points would need card-by-card data this "
        "site doesn't fetch for any competition, and the UEFA Nations League access list isn't a "
        "football result at all. Both are extremely unlikely to ever matter in practice — reaching "
        "them needs five or more criteria to all tie exactly — so group tables/simulations here use "
        "criteria 1-9 in full."
    )
    st.markdown("#### Cross-Group Ranking (Ranking of Nth-placed teams)")
    st.caption(
        "League A's 3rd/4th-placed teams (the only ones still cross-group ranked — see the "
        "Promotion & Relegation tab) are from different groups and have never played each other, so "
        "criteria 1-4 (head-to-head) never apply — ranking starts straight at criterion 5 (overall "
        "goal difference), then goals scored, away goals scored, wins, and away wins, in that order."
    )

with projections_2028_tab:
    st.markdown("#### 2028/29 UEFA Nations League Projections")
    st.caption(
        "UEFA is folding League D and moving to a three-league, 18-team shape (League A/B/C) for "
        "2028/29 — see UEFA's own "
        "[transition rules PDF](https://editorial.uefa.com/resources/02a9-21985b7e3370-3f0fda209606-1000/promotion_and_relegation_unl_website.pdf). "
        "This projects each nation's 2028/29 league and rank from the single most-likely outcome of "
        "every slot in the 2026/27 edition — group finishes, the Nations League Finals itself, both "
        "play-off pools' likeliest winners, and League D's teams, which all move to League C "
        "regardless of position. Ranking order and wording follow UEFA's own "
        "[criteria for final overall ranking](https://en.wikipedia.org/wiki/2026%E2%80%9327_UEFA_Nations_League#Overall_ranking), "
        "using each team's projected points as the tiebreaker within a bucket. It's a point estimate, "
        "not a probability (contrast the Knockouts/Promotion & Relegation tabs' own \"chance to "
        "prevail\" figures, which still carry real uncertainty) — treat it as today's single "
        "most-likely scenario, not a forecast with error bars."
    )

    with st.spinner("Projecting the 2028/29 league composition…"):
        composition = project_2028_composition(
            all_group_probs, NL_GROUPS, ratings_df, all_group_standings, all_group_remaining,
            league_a_outcome_probs=all_outcome_probs["League A"],
        )

    for league in ["League A", "League B", "League C"]:
        league_rows = composition[composition["league"] == league].reset_index(drop=True)
        st.markdown(f"##### {league} ({len(league_rows)} teams)")
        df = pd.DataFrame([
            {"Rank": r["rank"], "Flag": _flag(r["team"]), "Team": r["team"], "Source": r["source"]}
            for _, r in league_rows.iterrows()
        ])
        st.dataframe(
            df,
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", width="small"),
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="medium"),
                "Source": st.column_config.TextColumn("How they got there", width="large"),
            },
            use_container_width=True, hide_index=True, height=len(df) * 35 + 38,
        )
