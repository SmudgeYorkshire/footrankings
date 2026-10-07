"""
2027/28 UEFA European Competitions -- access list, connected live to each
domestic league's CURRENT (2026/27) standings.

Nothing about the 2027/28 qualifying draw, League Phase pairings, or pot
seeding exists yet (UEFA won't draw any of that until mid-2027) -- the
Projected Entries tab answers "who would currently qualify, and via which
route, if the 2026/27 domestic seasons ended today." The Predicted
Qualifiers tab goes one step further and projects the qualifying rounds
themselves (own pool-chaining/pairing/win-probability model -- see its own
section below). See european.py for the fully-live 2026/27 competitions
(qualifying ties, League Phase table, simulations) this page will grow
into once the real 2027/28 draw exists.

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
from ratings_manager import load_ratings
from _split_season import compute_full_standings, ensure_full_roster
from entrants_2027_28 import ACCESS_LIST_2027_28, STAGE_ORDER_2027_28, QUALIFYING_DATES_2027_28
from club_coefficients_2027 import get_coeff_2027
from cup_predictions import resolve_predicted_cup_winner, fetch_cup_fixtures
from simulator import two_leg_advance_odds
from nations_league_simulator import _pair_playoff_pool

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")

# entrants_2027_28.py's country spelling matches config.LEAGUES' own (so a
# row's "league" field can look standings up directly) -- flags.py alone
# spells a handful of these differently, so only the flag lookup needs this.
_FLAG_ALIAS = {
    "Turkey": "Türkiye", "Czech Rep.": "Czechia", "Bosnia": "Bosnia-Herzegovina",
    "Faroe Isl.": "Faroe Islands", "N. Macedonia": "North Macedonia", "N. Ireland": "Northern Ireland",
}

_POSITION_OF_CODE = {"CH": 1, "N2": 2, "N3": 3, "N4": 4, "N5": 5, "N6": 6, "N7": 7}

# Every entry across all 3 competitions, grouped by country -- built once so
# the Cup Winner cascade (see _resolve_country_slots) can see a country's
# FULL slot list regardless of which single competition is currently
# selected in either tab's own selectbox.
_ENTRIES_BY_COUNTRY: dict[str, list[tuple[str, dict]]] = {}
for _comp, _comp_entries in ACCESS_LIST_2027_28.items():
    for _e in _comp_entries:
        _ENTRIES_BY_COUNTRY.setdefault(_e["country"], []).append((_comp, _e))


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


def _position_occupant(entry: dict, standings: list[dict] | None) -> tuple[str, str]:
    """(team, note) for a league-table-position slot (CH, N2..N7) --
    unique table positions, never collide with each other or with CW."""
    own_note = entry.get("note")
    if own_note and own_note.startswith("Suspended"):
        return "—", own_note
    if entry["league"] is None:
        return "—", own_note or "no tracked league"
    if standings is None:
        return "—", own_note or ("no API key configured" if not _API_KEY else "live fetch failed")
    pos = _POSITION_OF_CODE.get(entry["code"])
    if not standings or pos is None or pos > len(standings):
        return "—", own_note or "not yet determined"
    note = "current position, may still change"
    if own_note:
        note = f"{own_note} — {note}"
    return standings[pos - 1].get("strTeam", "—"), note


@st.cache_data(ttl=60, show_spinner=False)
def _predict_cup_winner(country: str) -> tuple[str | None, str]:
    """(predicted winner team name, note) for this country's main domestic
    cup -- the same point-estimate engine (resolve_predicted_cup_winner:
    highest-Opta-rated team not yet eliminated from its cup) that powers
    football_rankings.py's live Cup Details tab."""
    entries = _ENTRIES_BY_COUNTRY.get(country, [])
    league_name = next((e["league"] for _, e in entries if e["league"]), None)
    if league_name is None:
        return None, "no tracked league"
    if not _API_KEY:
        return None, "no API key configured"
    cfg = LEAGUES.get(league_name)
    cup_id = cfg.get("cup_id") if cfg else None
    if not cfg or not cup_id:
        return None, "no cup data available for this country"
    try:
        league_season = cfg.get("af_season") or cfg["af_season"]
        season = cfg.get("cup_af_seasons", {}).get(cup_id, league_season)
        played, remaining = fetch_cup_fixtures(cup_id, season, _API_KEY)
        ratings_df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [])
        pred_row, _pred_status, _skipped = resolve_predicted_cup_winner(ratings_df, played, remaining)
    except Exception:
        return None, "live cup fetch failed"
    alias = str(pred_row.get("alias", "")).strip()
    name = alias if alias else pred_row["team"]
    return name, "predicted cup winner — domestic cup still in progress"


@st.cache_data(ttl=60, show_spinner=False)
def _resolve_country_slots(country: str) -> dict[tuple[str, str], tuple[str, str]]:
    """{(competition, code): (occupant, note)} for every slot this country
    has across all three competitions.

    Every country has exactly one Cup Winner (CW) slot total (confirmed
    against entrants_2027_28.py), so the only possible collision is "the
    predicted cup winner already holds a different, league-position slot
    for this same country" -- never CW-vs-CW. When that happens, the real
    rule is that the vacated continental slot cascades down to the next
    domestic-table team not already claimed (walking from position 8
    onward -- positions 1-7 are already fully accounted for by the
    position-based slots resolved first below), rather than sit empty.
    """
    entries = _ENTRIES_BY_COUNTRY.get(country, [])
    if not entries:
        return {}
    league_name = next((e["league"] for _, e in entries if e["league"]), None)
    standings = None
    if league_name:
        cfg = LEAGUES.get(league_name)
        if cfg and _API_KEY:
            try:
                standings = _current_standings(cfg["id"], cfg["af_season"], league_name)
            except Exception:
                standings = None

    result: dict[tuple[str, str], tuple[str, str]] = {}
    claimed: set[str] = set()
    cw_slot: tuple[str, dict] | None = None
    for comp, e in entries:
        if e["code"] == "CW":
            cw_slot = (comp, e)
            continue
        occ, note = _position_occupant(e, standings)
        result[(comp, e["code"])] = (occ, note)
        if occ != "—":
            claimed.add(occ)

    if cw_slot:
        comp, e = cw_slot
        own_note = e.get("note")
        if own_note and own_note.startswith("Suspended"):
            result[(comp, "CW")] = ("—", own_note)
        elif e["league"] is None:
            result[(comp, "CW")] = ("—", own_note or "no tracked league")
        else:
            pred_name, pred_note = _predict_cup_winner(country)
            if pred_name is None:
                result[(comp, "CW")] = ("—", own_note or pred_note)
            elif pred_name not in claimed:
                note = f"{own_note} — {pred_note}" if own_note else pred_note
                result[(comp, "CW")] = (pred_name, note)
            else:
                fallback = None
                if standings:
                    for row in standings[len(_POSITION_OF_CODE):]:
                        team = row.get("strTeam", "")
                        if team and team not in claimed:
                            fallback = (team, row.get("intRank"))
                            break
                if fallback:
                    team, rank = fallback
                    note = (
                        f"Cup winner {pred_name} already qualified via league position — "
                        f"slot passes to {rank}-placed {team}"
                    )
                else:
                    team = "—"
                    note = (
                        f"Cup winner {pred_name} already qualified via league position — "
                        f"no further unclaimed league position available"
                    )
                if own_note:
                    note = f"{own_note} — {note}"
                result[(comp, "CW")] = (team, note)
    return result


def _country_key(country: str) -> str:
    return _FLAG_ALIAS.get(country, country)


_SEED_RANK = {"Seeded": 0, "Unseeded": 1, "—": 2}


def _seed_and_sort(table_rows: list[dict]) -> None:
    """In-place: assign Seeded/Unseeded (top/bottom half of this table's
    own pool by coefficient -- matching how UEFA draws each round's pots)
    and sort Seeded above Unseeded above undetermined ("—", e.g. Russia),
    each group by coefficient (or country name for the undetermined
    group, which has none)."""
    ranked = sorted((r for r in table_rows if r["Coefficient"] is not None), key=lambda r: -r["Coefficient"])
    cutoff = -(-len(ranked) // 2)
    for i, r in enumerate(ranked):
        r["Seeding"] = "Seeded" if i < cutoff else "Unseeded"
    for r in table_rows:
        r.setdefault("Seeding", "—")
    table_rows.sort(key=lambda r: (_SEED_RANK[r["Seeding"]], -(r["Coefficient"] or 0), r["Country"]))


st.title("🔮 European Competitions 2027/28")

entries_tab, qualifiers_tab = st.tabs(["📋 Projected Entries", "🏁 Predicted Qualifiers"])

with entries_tab:
    st.caption(
        "UEFA's official 2027/28 access list (circular 54/2026), connected live to each "
        "country's CURRENT 2026/27 league table. Every occupant below is provisional -- "
        "domestic seasons run until roughly May/June 2027, and nothing about the actual "
        "2027/28 qualifying draw exists yet. Coefficient is each club's live UEFA 5-year "
        "club ranking ([kassiesa.net](https://kassiesa.net/uefa/data/method5/trank2027.html), "
        "still accumulating through 2026/27) -- a club with no individual European history "
        "inherits its country's floor value instead. Seeding splits each stage's own clubs "
        "into the top/bottom half by that coefficient, matching how UEFA draws each round's "
        "pots -- not the actual qualifying bracket or League Phase's 4-pot structure, which "
        "don't exist yet either. Rows sort Seeded, then Unseeded, then undetermined slots "
        "(e.g. Russia's suspended associations) last. A Cup Winner slot shows a predicted "
        "winner (highest-rated team not yet out of its domestic cup); if that club already "
        "holds a different slot via league position, the vacated continental slot passes to "
        "the next unclaimed league position instead of sitting empty."
    )

    comp_name = st.selectbox("Competition", list(ACCESS_LIST_2027_28.keys()), key="entries_comp")
    comp_entries = ACCESS_LIST_2027_28[comp_name]

    n_direct = sum(1 for e in comp_entries if e["round"] == "League Phase (direct)")
    n_total = len(comp_entries)
    st.markdown(
        f"**{n_total} slots** in the 2027/28 access list -- **{n_direct} already go straight "
        f"to the 36-team League Phase**, the rest work through qualifying."
    )

    qd = QUALIFYING_DATES_2027_28[comp_name]

    groups: dict[str, list[dict]] = {}
    for e in comp_entries:
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
        for e in rows:
            occ_note = _resolve_country_slots(e["country"]).get((comp_name, e["code"]))
            occupant, note = occ_note if occ_note else ("—", e.get("note") or "not yet determined")
            country_key = _country_key(e["country"])
            coeff = get_coeff_2027(occupant, country_key) if occupant != "—" else None
            table_rows.append({
                "Flag": flag_url(country_key),
                "Club": occupant,
                "Country": e["country"],
                "Coefficient": coeff,
                "Label": e["label"],
                "Path": e["path"],
                "Route": e["route"],
                "Note": note,
            })

        _seed_and_sort(table_rows)

        df = pd.DataFrame(table_rows)
        st.dataframe(
            df,
            column_config={
                "Flag": st.column_config.ImageColumn("", width="small"),
                "Club": st.column_config.TextColumn("Club", width="medium"),
                "Country": st.column_config.TextColumn("Country", width="small"),
                "Coefficient": st.column_config.NumberColumn("Coefficient", width="small", format="%.3f"),
                "Seeding": st.column_config.TextColumn("Seeding", width="small"),
                "Label": st.column_config.TextColumn("Label", width="small"),
                "Path": st.column_config.TextColumn("Path", width="small"),
                "Route": st.column_config.TextColumn("Route", width="small"),
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


# --- Predicted Qualifiers ---------------------------------------------
#
# UEFA's real qualifying bracket runs Champions Path and League Path
# separately through most rounds with mid-bracket reseeding rules complex
# enough that no public source (nor entrants_2027_28.py's own data model,
# which only tracks each slot's FIRST entry round) cleanly specifies who
# reshuffles where. This approximates the real structure as closely as the
# data supports: Champions Path and League Path are kept as separate
# pools through each round, merging only at the Play-off round (where
# entrants_2027_28.py's own labels stop distinguishing them -- there is no
# separate "CL-PO-nc"). Europa League and Conference League have no path
# split in this data at all (no "nc" labels), so they stay single-chain.
#
# Confirmed against the 2026/27 UEFA Champions League qualifying structure
# (Wikipedia): Champions Path runs Q1->Q2->Q3->PO even though
# entrants_2027_28.py has no fresh "CL-Q3" entries (Q3 is a pure
# continuation round for that path -- its Q2 survivors still play a real
# tie before Play-offs); League Path runs Q2nc->Q3nc->PO. Europa League
# runs Q1->Q2->Q3->PO (one path, no "nc" labels); Conference League runs
# Q1->Q2->PO (one path, no Q3 at all -- confirmed no CO-Q3 label exists).
_QUALIFYING_ROUNDS = ["First qualifying round", "Second qualifying round", "Third qualifying round", "Play-off round"]

_PATH_SEQUENCES: dict[str, dict[str, list[str]]] = {
    "Champions League": {
        "main": ["First qualifying round", "Second qualifying round", "Third qualifying round", "Play-off round"],
        "nc":   ["Second qualifying round", "Third qualifying round", "Play-off round"],
    },
    "Europa League": {
        "main": ["First qualifying round", "Second qualifying round", "Third qualifying round", "Play-off round"],
    },
    "Conference League": {
        "main": ["First qualifying round", "Second qualifying round", "Play-off round"],
    },
}


def _fresh_pool_entries(comp: str, round_name: str, path: str | None) -> list[dict]:
    """Fresh (newly-joining) access-list entries for this competition and
    round, filtered to the given path ("main"/"nc") -- or every path at
    once when path is None (the Play-off round's merge point, where
    entrants_2027_28.py's own labels no longer distinguish them)."""
    out = []
    for e in ACCESS_LIST_2027_28[comp]:
        if e["round"] != round_name:
            continue
        if path is not None:
            suffix = "nc" if e["label"].endswith("nc") else "main"
            if suffix != path:
                continue
        out.append(e)
    return out


def _resolve_pool_clubs(entries: list[dict], comp: str) -> tuple[list[dict], list[str]]:
    """[{"team", "coeff", "country"}] for every entry that resolves to a
    real club, plus a list of one-line exclusion notes for entries that
    didn't (undetermined slots, e.g. Russia's suspended associations --
    can't pair a non-existent club)."""
    clubs, excluded = [], []
    for e in entries:
        occ_note = _resolve_country_slots(e["country"]).get((comp, e["code"]))
        occupant, note = occ_note if occ_note else ("—", e.get("note") or "not yet determined")
        if occupant == "—":
            excluded.append(f"{e['country']} ({e['label']}): {note}")
            continue
        country_key = _country_key(e["country"])
        clubs.append({"team": occupant, "coeff": get_coeff_2027(occupant, country_key), "country": e["country"]})
    return clubs, excluded


def _simulate_round(pool: list[dict]) -> tuple[list[dict], list[dict]]:
    """Seeded-vs-unseeded pairing (nations_league_simulator._pair_playoff_
    pool: strongest vs weakest, same "most likely single draw" convention
    used throughout this project) + two-legged win probability
    (simulator.two_leg_advance_odds, neutral home advantage since no real
    draw has set a leg order yet -- same convention project_league_a_
    finals uses for an unknown-venue match). Returns (tie rows for
    display, winning club dicts to carry into the next round)."""
    if not pool:
        return [], []
    ranked = sorted(pool, key=lambda c: -c["coeff"])
    bye = None
    if len(ranked) % 2 == 1:
        bye = ranked[0]
        ranked = ranked[1:]
    by_name = {c["team"]: c for c in ranked}
    names = list(by_name.keys())

    ties, winners = [], []
    for a, b in _pair_playoff_pool(names):
        ratings_df = pd.DataFrame({"team": [a, b], "opta_rating": [by_name[a]["coeff"], by_name[b]["coeff"]]})
        odds = two_leg_advance_odds(a, b, ratings_df, home_advantage=1.0)
        pct_a, pct_b = odds["team1_adv"] * 100, odds["team2_adv"] * 100
        winner = by_name[a] if pct_a >= pct_b else by_name[b]
        ties.append({
            "Club A": a, "A %": round(pct_a, 1),
            "Club B": b, "B %": round(pct_b, 1),
            "Predicted winner": winner["team"],
        })
        winners.append(winner)
    if bye is not None:
        ties.append({
            "Club A": bye["team"], "A %": None,
            "Club B": "— (bye)", "B %": None,
            "Predicted winner": bye["team"],
        })
        winners.append(bye)
    return ties, winners


def _simulate_competition_bracket(comp: str) -> list[dict]:
    """[{"round", "path" (or None for the PO merge), "ties", "excluded"}]
    in bracket order, chaining each path's own winners round to round per
    _PATH_SEQUENCES, merging all paths into one pool at the Play-off
    round."""
    paths = list(_PATH_SEQUENCES[comp].keys())
    pool_by_path: dict[str, list[dict]] = {p: [] for p in paths}
    output = []

    for round_name in _QUALIFYING_ROUNDS:
        active_paths = [p for p in paths if round_name in _PATH_SEQUENCES[comp][p]]
        if not active_paths:
            continue
        if round_name == "Play-off round":
            pool, excluded = [], []
            for p in paths:
                pool.extend(pool_by_path[p])
            fresh, fresh_excluded = _resolve_pool_clubs(_fresh_pool_entries(comp, round_name, None), comp)
            pool.extend(fresh)
            excluded.extend(fresh_excluded)
            ties, _winners = _simulate_round(pool)
            output.append({"round": round_name, "path": None, "ties": ties, "excluded": excluded})
        else:
            for p in active_paths:
                fresh, excluded = _resolve_pool_clubs(_fresh_pool_entries(comp, round_name, p), comp)
                pool = pool_by_path[p] + fresh
                ties, winners = _simulate_round(pool)
                output.append({"round": round_name, "path": p, "ties": ties, "excluded": excluded})
                pool_by_path[p] = winners
    return output


with qualifiers_tab:
    st.caption(
        "Projects the qualifying rounds themselves, round by round, from today's most-likely "
        "occupant of every access-list slot (Projected Entries tab) -- not UEFA's actual random "
        "draw (which doesn't exist yet) or its same-association protection. Each round's own "
        "pool is split Seeded/Unseeded by live club coefficient (same split as Projected "
        "Entries) and paired strongest vs weakest; win probability per two-legged tie comes "
        "from this site's own Poisson match model at a neutral venue (no real leg order is set "
        "yet). Champions Path and League Path are kept separate through each round, merging "
        "only at the Play-off round, matching how entrants_2027_28.py's own data stops "
        "distinguishing them there. An odd pool gives its single strongest club a bye rather "
        "than inventing an opponent."
    )

    qual_comp = st.selectbox("Competition", list(ACCESS_LIST_2027_28.keys()), key="qualifiers_comp")

    with st.spinner("Projecting the qualifying rounds…"):
        bracket = _simulate_competition_bracket(qual_comp)

    _PATH_LABEL = {"main": " — Champions Path" if qual_comp == "Champions League" else "", "nc": " — League Path", None: ""}

    for stage_round in bracket:
        path_label = _PATH_LABEL.get(stage_round["path"], "")
        st.markdown(f"#### {stage_round['round']}{path_label}")
        if stage_round["excluded"]:
            st.caption("Excluded (no determined club): " + "; ".join(stage_round["excluded"]))
        if not stage_round["ties"]:
            st.caption("No clubs in this round's pool.")
            continue
        tie_df = pd.DataFrame(stage_round["ties"])
        st.dataframe(
            tie_df,
            column_config={
                "Club A": st.column_config.TextColumn("Club A", width="medium"),
                "A %": st.column_config.NumberColumn("A %", width="small", format="%.1f%%"),
                "Club B": st.column_config.TextColumn("Club B", width="medium"),
                "B %": st.column_config.NumberColumn("B %", width="small", format="%.1f%%"),
                "Predicted winner": st.column_config.TextColumn("Predicted winner", width="medium"),
            },
            use_container_width=True, hide_index=True, height=len(tie_df) * 35 + 38,
        )

    st.divider()
    st.caption(
        "Play-off round winners above would join the League Phase (direct) clubs already "
        "shown on the Projected Entries tab, completing the 36-team field."
    )
