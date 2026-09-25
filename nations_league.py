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
    cross_group_ranking, group_fixture_odds,
)
from nations_league_fixtures import group_fixtures
from _split_season import compute_full_standings

st.title("🌍 2026/27 UEFA Nations League")


def _flag(team: str) -> str:
    return flag_url(NL_FLAG_ALIASES.get(team, team))


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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


def _render_predictions(teams: list[str], probs: pd.DataFrame, exp_pts: dict[str, float]) -> None:
    n_teams = len(teams)
    rows = []
    for team in probs.index:
        row = {"Flag": _flag(team), "Team": team}
        for pos in range(1, n_teams + 1):
            row[_ordinal(pos)] = round(probs.loc[team, str(pos)] * 100, 1)
        row["xPTS"] = round(exp_pts.get(team, 0.0), 1)
        rows.append(row)
    display_df = pd.DataFrame(rows)

    col_cfg = {
        "Flag": st.column_config.ImageColumn("", width="small"),
        "Team": st.column_config.TextColumn("Team", width="medium"),
    }
    for pos in range(1, n_teams + 1):
        col_cfg[_ordinal(pos)] = st.column_config.NumberColumn(_ordinal(pos), format="%.1f%%", width="small")
    col_cfg["xPTS"] = st.column_config.NumberColumn("xPTS", width="small", help="Expected points")

    st.dataframe(
        display_df, column_config=col_cfg, use_container_width=True,
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

# A league's final "Relegation to League X" column should read as the
# TOTAL chance of ending up there next edition, not just the direct-
# relegation route -- League A's bottom two (cross-group ranked) 4th-
# place teams go down directly, but the bottom two 3rd-place teams *and*
# the top two 4th-place teams who then LOSE their relegation play-off end
# up in exactly the same place, so that raw column's displayed value adds
# in whichever play-off-loss label also leads there.
_COMBINE_WITH_PLAYOFF_LOSS = {"Relegation to League B": "Relegated in Play-offs"}

# Display-only rename for the direct-promotion column so it names its
# actual destination league instead of the generic "Promotion" -- the
# underlying rule label (and Status column text) is untouched.
_PROMOTION_DISPLAY_BY_LEAGUE = {
    "League B": "Promotion to League A",
    "League C": "Promotion to League B",
    "League D": "Promotion to League C",
}


def _render_outcome_predictions(teams: list[str], probs_df: pd.DataFrame, league_name: str) -> None:
    """One column per outcome-bucket label in probs_df (Quarterfinals,
    Promotion, Winner/Loser in Play-offs, ...) plus a "Stay in {league}"
    column: 1 minus whichever of those labels actually mean leaving the
    league next edition (see LEAGUE_LEAVE_LABELS) -- e.g. for League A
    that's just the two ways down (a lost relegation play-off or direct
    relegation), since reaching the Quarterfinals or winning a play-off
    both keep a team in League A. The Stay column is omitted entirely
    when every raw column already means leaving (League D: every position
    is a direct "Promotion", so it would always read 0%)."""
    leave_labels = LEAGUE_LEAVE_LABELS.get(league_name, set(probs_df.columns))
    bucket_cols = list(probs_df.columns)
    show_stay = not (set(bucket_cols) <= leave_labels)
    stay_label = f"Stay in {league_name}"
    cols = (bucket_cols[:1] + [stay_label] + bucket_cols[1:]) if show_stay else list(bucket_cols)

    active_splits = [s for s in _PLAYOFF_SPLITS if s[0] in cols and s[1] in cols]
    for win_col, lose_col, agg_col in active_splits:
        cols.insert(cols.index(win_col), agg_col)

    rows = []
    for t in teams:
        row = {"Flag": _flag(t), "Team": t}
        raw = {c: float(probs_df.loc[t, c]) if t in probs_df.index else 0.0 for c in probs_df.columns}
        for c, v in raw.items():
            extra = raw.get(_COMBINE_WITH_PLAYOFF_LOSS.get(c, ""), 0.0)
            row[c] = round((v + extra) * 100, 1)
        for win_col, lose_col, agg_col in active_splits:
            row[agg_col] = round((raw[win_col] + raw[lose_col]) * 100, 1)
        if show_stay:
            leave_prob = sum(v for c, v in raw.items() if c in leave_labels)
            row[stay_label] = round(max(0.0, 1.0 - leave_prob) * 100, 1)
        rows.append(row)
    df = pd.DataFrame(rows)[["Flag", "Team"] + cols]

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
        col_cfg[c] = st.column_config.NumberColumn(display_overrides.get(c, c), format="%.1f%%")
    st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True, height=len(df) * 35 + 38)


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
        _render_predictions(teams, cached["probs"], cached["exp_pts"])
    else:
        st.info("Enter predictions above then press **▶ Run simulations**.")


league_names = list(NL_GROUPS.keys())
top_tabs = st.tabs(league_names + ["🔀 Promotion & Relegation", "🏆 Knockout Chances", "📜 Rules"])
league_tabs = top_tabs[:len(league_names)]
promo_releg_tab = top_tabs[-3]
knockout_chances_tab = top_tabs[-2]
rules_tab = top_tabs[-1]

all_group_probs: dict[str, dict[str, pd.DataFrame]] = {}
all_outcome_probs: dict[str, pd.DataFrame] = {}

for league_tab, league_name in zip(league_tabs, league_names):
    with league_tab:
        groups = NL_GROUPS[league_name]
        rules = LEAGUE_OUTCOME_RULES[league_name]
        ranked_rules = [r for r in rules if r[0] == "ranked"]
        all_league_teams = [t for g in groups.values() for t in g]

        # Pre-fetch every group's real current data once -- needed both
        # for each group's own tabs below and for the league-wide outcome
        # simulation, which has to see every group's state at once so a
        # cross-group-ranked rule (e.g. League A's 3rd/4th-place pools)
        # is correlated correctly rather than computed from independent
        # per-group marginals.
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

        with st.spinner("Simulating group-stage outcomes…"):
            outcome_probs = simulate_league_outcomes(
                _group_states_from(groups, league_group_standings, league_group_remaining),
                rules, ratings_df, n_sim=8_000,
            )
        all_outcome_probs[league_name] = outcome_probs

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
                    probs, exp_pts = simulate_group(
                        teams, ratings_df, n_sim=10_000,
                        standings=real_standings, remaining_fixtures=remaining, played_fixtures=played,
                    )
                    league_group_probs[group_name] = probs
                    league_group_exp_pts[group_name] = exp_pts
                    _render_predictions(teams, probs, exp_pts)
                    st.markdown("#### Group stage outcome chances")
                    _render_outcome_predictions(teams, outcome_probs, league_name)

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
                    top_text = f"{ord_} place, stays in {league_name}" if position == 3 else f"{ord_} place, {label_top}"
                    bottom_text = f"{ord_} place, {label_bottom}"
                    detail_rules.append(("ranked", position, n_top, top_text, n_bottom, bottom_text))
                with st.spinner("Simulating…"):
                    detail_probs = simulate_league_outcomes(
                        _group_states_from(groups, league_group_standings, league_group_remaining),
                        detail_rules, ratings_df, n_sim=8_000,
                    )
                detail_rows = []
                for t in all_league_teams:
                    row = {"Flag": _flag(t), "Team": t}
                    for col in detail_probs.columns:
                        row[col] = round(float(detail_probs.loc[t, col]) * 100, 1)
                    detail_rows.append(row)
                detail_df = pd.DataFrame(detail_rows)
                detail_col_cfg = {
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                }
                for col in detail_probs.columns:
                    detail_col_cfg[col] = st.column_config.NumberColumn(col, format="%.1f%%")
                st.dataframe(
                    detail_df, column_config=detail_col_cfg, use_container_width=True,
                    hide_index=True, height=len(detail_df) * 35 + 38,
                )

        with pred_tab:
            st.markdown("#### Group Stage Outcome Predictions")
            st.caption(
                f"Every {league_name} nation's chance of landing in each group-stage outcome, jointly "
                "simulating all groups together so a cross-group-ranked outcome is correctly correlated "
                "rather than computed from independent per-group marginals."
            )
            _render_outcome_predictions(all_league_teams, outcome_probs, league_name)

with knockout_chances_tab:
    st.markdown("#### Knockout Chances")
    st.caption(
        "Winners will face Runners-up in the Quarterfinals, determined by a draw, and it will "
        "be an open draw for the Semifinals without seeding."
    )
    with st.spinner("Simulating the quarter-finals and Finals Four…"):
        ko = simulate_league_a_knockouts(all_group_probs["League A"], ratings_df, n_sim=8_000)

    ko_rows = []
    for team, r in ko.iterrows():
        ko_rows.append({
            "Flag": _flag(team),
            "Team": team,
            "Quarterfinals": round(r["reached_qf"] * 100, 1),
            "Semifinals": round(r["reached_finals_four"] * 100, 1),
            "Winner": round(r["won_competition"] * 100, 1),
        })
    ko_df = pd.DataFrame(ko_rows)
    ko_col_cfg = {
        "Flag": st.column_config.ImageColumn("", width="small"),
        "Team": st.column_config.TextColumn("Team", width="medium"),
        "Quarterfinals": st.column_config.NumberColumn("Quarterfinals", format="%.1f%%", width="small"),
        "Semifinals": st.column_config.NumberColumn("Semifinals", format="%.1f%%", width="small"),
        "Winner": st.column_config.NumberColumn("Winner", format="%.1f%%", width="small"),
    }
    st.dataframe(
        ko_df, column_config=ko_col_cfg, use_container_width=True,
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

    st.divider()
    st.markdown("##### Chances of reaching each play-off pool")

    def _role_chances(title: str, teams: list[str], chances: pd.Series) -> None:
        with st.expander(title):
            rows = [
                {"Flag": _flag(t), "Team": t, "Chance": round(float(chances.get(t, 0.0)) * 100, 1)}
                for t in teams
            ]
            rows.sort(key=lambda r: -r["Chance"])
            df = pd.DataFrame(rows)
            st.dataframe(
                df,
                column_config={
                    "Flag": st.column_config.ImageColumn("", width="small"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "Chance": st.column_config.NumberColumn("Chance", format="%.1f%%"),
                },
                use_container_width=True, hide_index=True, height=len(df) * 35 + 38,
            )

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

    _role_chances("League A third place/fourth place", a_teams, a_releg_pool_chance)
    _role_chances("League B runner-up", b_teams, b_promo_pool_chance)
    _role_chances("League B fourth place", b_teams, b_releg_pool_chance)
    _role_chances("League C runner-up", c_teams, c_promo_pool_chance)

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
