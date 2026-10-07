"""
2027/28 UEFA European Competitions -- access list, connected live to each
domestic league's PREDICTED FINAL (2026/27) standings.

Nothing about the 2027/28 qualifying draw, League Phase pairings, or pot
seeding exists yet (UEFA won't draw any of that until mid-2027) -- a single
competition selector up top feeds three tabs. Projected Entries answers
"who would most likely qualify, and via which route, once the 2026/27
domestic seasons finish" (predicted final table, not the current one --
see _predicted_standings' own docstring for why), split into the real
Champions Path/League Path (or Main Path) sections each competition
actually used in its 2026/27 qualifying (confirmed against the 2026/27
Champions League, Europa League and Conference League Wikipedia
articles), not just a text column. Predicted
Qualifiers goes one step further and projects the qualifying rounds
themselves, including the real cross-competition cascade (Champions League
Champions Path losers drop into the Europa League; Europa League losers
drop into the Conference League, etc. -- see _BUCKETS below). Predicted
League Stage combines both into the full predicted 36-club field.

See european.py for the fully-live 2026/27 competitions (qualifying ties,
League Phase table, simulations) this page will grow into once the real
2027/28 draw exists.

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

from config import LEAGUES, DEFAULT_HOME_ADVANTAGE
from flags import flag_url
from api_football_fetcher import ApiFootballClient
from ratings_manager import load_ratings
from _split_season import compute_full_standings, ensure_full_roster
from entrants_2027_28 import ACCESS_LIST_2027_28, STAGE_ORDER_2027_28, QUALIFYING_DATES_2027_28
from club_coefficients_2027 import get_coeff_2027
from cup_predictions import resolve_predicted_cup_winner, fetch_cup_fixtures
from simulator import two_leg_advance_odds, simulate_season
from nations_league_simulator import _pair_playoff_pool, most_likely_group_order

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
# selected.
_ENTRIES_BY_COUNTRY: dict[str, list[tuple[str, dict]]] = {}
for _comp, _comp_entries in ACCESS_LIST_2027_28.items():
    for _e in _comp_entries:
        _ENTRIES_BY_COUNTRY.setdefault(_e["country"], []).append((_comp, _e))


_PREDICTION_N_SIM = 1_000  # see _predicted_standings' own docstring


@st.cache_data(ttl=60, show_spinner=False)
def _predicted_standings(league_id: int, season: int, league_name: str):
    """Every slot on this page resolves against the PREDICTED FINAL table,
    not the live current-season one -- this early in a season (a handful
    of matchweeks in), the current table is noisy (e.g. a promoted side's
    hot start can sit them above clubs who'll finish well clear of them by
    May; confirmed on real data, Leeds showing in a Champions League slot
    off a small-sample current position). Runs this site's own full-season
    Monte Carlo (the same simulate_season() the Predictions tab itself
    uses) and reduces it to the single most-likely finishing order via
    nations_league_simulator.most_likely_group_order -- the same
    "most-likely single draw" convention used everywhere else on this
    page. n_sim is deliberately much lower than the Predictions tab's own
    DEFAULT_N_SIMULATIONS (10,000): this page needs an ORDER, not precise
    probabilities, for up to ~50 countries at once, where the Predictions
    tab only ever runs one league at a time.

    Original standings rows (badges, etc.) are kept, just reordered and
    re-ranked (intRank) to the predicted finish."""
    client = ApiFootballClient(api_key=_API_KEY)
    roster = client.get_standings(league_id, season)
    played, remaining = client.get_fixtures(league_id, season)
    roster = ensure_full_roster(roster, played + remaining)
    cfg = LEAGUES.get(league_name, {})
    tiebreakers = cfg.get("tiebreakers")
    standings = compute_full_standings(roster, played, tiebreakers=tiebreakers) if roster else roster
    if not standings:
        return standings
    ratings_df = load_ratings(cfg.get("tsdb_id", league_id), standings)
    probs = simulate_season(
        standings, remaining, ratings_df, n_sim=_PREDICTION_N_SIM,
        home_advantage=cfg.get("home_advantage", DEFAULT_HOME_ADVANTAGE),
        tiebreakers=tiebreakers, played_fixtures=played,
    )
    if probs.empty:
        return standings
    order = most_likely_group_order(probs)
    by_team = {row["strTeam"]: row for row in standings}
    return [{**by_team[t], "intRank": i} for i, t in enumerate(order, start=1) if t in by_team]


@st.cache_data(ttl=60, show_spinner=False)
def _badge_lookup_for_country(country: str) -> dict[str, str]:
    """{team name: badge URL} for a country's own top-flight table --
    standings rows already carry this (see football_rankings.py's own
    badge_lookup), just scoped per-country here."""
    entries = _ENTRIES_BY_COUNTRY.get(country, [])
    league_name = next((e["league"] for _, e in entries if e["league"]), None)
    if not league_name:
        return {}
    cfg = LEAGUES.get(league_name)
    if not cfg or not _API_KEY:
        return {}
    try:
        standings = _predicted_standings(cfg["id"], cfg["af_season"], league_name)
    except Exception:
        return {}
    return {row["strTeam"]: row.get("strBadge", "") for row in (standings or []) if row.get("strBadge")}


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
    note = "predicted final position, may still change"
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
                standings = _predicted_standings(cfg["id"], cfg["af_season"], league_name)
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


def _number_rows(rows: list[dict]) -> list[dict]:
    """Prepend a "No." column (1..N in the rows' own current order) --
    every table on this page numbers its own rows this way, e.g. 1 to 36
    for the Predicted League Stage."""
    return [{"No.": i, **r} for i, r in enumerate(rows, start=1)]


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


def _club_row(occupant: str, note: str, country: str, label: str, route: str) -> dict:
    country_key = _country_key(country)
    coeff = get_coeff_2027(occupant, country_key) if occupant != "—" else None
    badge = _badge_lookup_for_country(country).get(occupant, "") if occupant != "—" else ""
    return {
        "Badge": badge,
        "Club": occupant,
        "Flag": flag_url(country_key),
        "Country": country,
        "Coefficient": coeff,
        "Label": label,
        "Route": route,
        "Note": note,
    }


_ENTRIES_COLUMN_CONFIG = {
    "No.": st.column_config.NumberColumn("No.", width="small"),
    "Badge": st.column_config.ImageColumn("", width="small"),
    "Club": st.column_config.TextColumn("Club", width="medium"),
    "Flag": st.column_config.ImageColumn("", width="small"),
    "Country": st.column_config.TextColumn("Country", width="small"),
    "Coefficient": st.column_config.NumberColumn("Coefficient", width="small", format="%.3f"),
    "Seeding": st.column_config.TextColumn("Seeding", width="small"),
    "Label": st.column_config.TextColumn("Label", width="small"),
    "Route": st.column_config.TextColumn("Route", width="small"),
    "Note": st.column_config.TextColumn("Note", width="large"),
}


# --- Real Champions/League/Main Path structure, confirmed against the
# 2026/27 UEFA Champions League, Europa League and Conference League
# Wikipedia articles ------------------------------------------------------
#
# Each bucket is one (competition, round, path) qualifying pool. "fresh"
# names the entrants_2027_28.py label whose access-list entries join this
# bucket fresh (None if this bucket has no direct access-list slots at
# all -- it's populated ENTIRELY by a cross-competition cascade, see
# "sources"). "sources" lists where else this bucket's starting pool comes
# from, as (other_bucket_id, "winners"|"losers") -- e.g. Europa League's
# Q3 Champions Path has no fresh entries of its own; its entire pool is
# the 12 losers of Champions League Q2's Champions Path.
#
# Confirmed real cascade, round by round:
#  - CL-Q1 (single bracket, no path split) losers all drop to Conference
#    League's Q2 Champions Path (a small number of these ties' losers
#    really drop to CO's Q3 Champions Path instead, for bracket-size
#    balancing -- not replicated here, a documented simplification).
#  - CL-Q2 Champions Path losers drop to EL-Q3 Champions Path; CL-Q2
#    League Path losers drop to EL-Q3 Main Path.
#  - CL-Q3 Champions Path losers drop to EL's Play-off round (EL-PO is a
#    single merged bracket, no path split); CL-Q3 League Path losers are
#    not carried further (eliminated from Europe).
#  - CL-PO (both paths) losers are not carried further.
#  - EL-Q2 losers drop to CO-Q3 League/Main Path. EL-Q3 Champions Path
#    losers drop to CO-PO Champions Path; EL-Q3 Main Path losers drop to
#    CO-PO League/Main Path. EL-Q1 losers drop to CO-Q2 League/Main Path.
#  - EL-PO and CO's Play-off round losers are not carried further --
#    whoever wins a Play-off round joins that competition's League Phase.
_BUCKETS: list[dict] = [
    {"id": "CL-Q1", "comp": "Champions League", "round": "First qualifying round", "path": None,
     "fresh": "CL-Q1", "sources": []},
    {"id": "CL-Q2-CP", "comp": "Champions League", "round": "Second qualifying round", "path": "Champions Path",
     "fresh": "CL-Q2", "sources": [("CL-Q1", "winners")]},
    {"id": "CL-Q2-LP", "comp": "Champions League", "round": "Second qualifying round", "path": "League Path",
     "fresh": "CL-Q2nc", "sources": []},
    {"id": "CL-Q3-CP", "comp": "Champions League", "round": "Third qualifying round", "path": "Champions Path",
     "fresh": None, "sources": [("CL-Q2-CP", "winners")]},
    {"id": "CL-Q3-LP", "comp": "Champions League", "round": "Third qualifying round", "path": "League Path",
     "fresh": "CL-Q3nc", "sources": [("CL-Q2-LP", "winners")]},
    {"id": "CL-PO-CP", "comp": "Champions League", "round": "Play-off round", "path": "Champions Path",
     "fresh": "CL-PO", "sources": [("CL-Q3-CP", "winners")]},
    {"id": "CL-PO-LP", "comp": "Champions League", "round": "Play-off round", "path": "League Path",
     "fresh": None, "sources": [("CL-Q3-LP", "winners")]},

    {"id": "EL-Q1", "comp": "Europa League", "round": "First qualifying round", "path": None,
     "fresh": "EL-Q1", "sources": []},
    {"id": "EL-Q2", "comp": "Europa League", "round": "Second qualifying round", "path": None,
     "fresh": "EL-Q2", "sources": [("EL-Q1", "winners")]},
    {"id": "EL-Q3-CP", "comp": "Europa League", "round": "Third qualifying round", "path": "Champions Path",
     "fresh": None, "sources": [("CL-Q2-CP", "losers")]},
    {"id": "EL-Q3-MP", "comp": "Europa League", "round": "Third qualifying round", "path": "Main Path",
     "fresh": "EL-Q3", "sources": [("EL-Q2", "winners"), ("CL-Q2-LP", "losers")]},
    {"id": "EL-PO", "comp": "Europa League", "round": "Play-off round", "path": None,
     "fresh": "EL-PO", "sources": [("EL-Q3-CP", "winners"), ("EL-Q3-MP", "winners"), ("CL-Q3-CP", "losers")]},

    {"id": "CO-Q1", "comp": "Conference League", "round": "First qualifying round", "path": None,
     "fresh": "CO-Q1", "sources": []},
    {"id": "CO-Q2-CP", "comp": "Conference League", "round": "Second qualifying round", "path": "Champions Path",
     "fresh": None, "sources": [("CL-Q1", "losers")]},
    {"id": "CO-Q2-MP", "comp": "Conference League", "round": "Second qualifying round", "path": "Main Path",
     "fresh": "CO-Q2", "sources": [("CO-Q1", "winners"), ("EL-Q1", "losers")]},
    {"id": "CO-Q3-CP", "comp": "Conference League", "round": "Third qualifying round", "path": "Champions Path",
     "fresh": None, "sources": [("CO-Q2-CP", "winners")]},
    {"id": "CO-Q3-MP", "comp": "Conference League", "round": "Third qualifying round", "path": "Main Path",
     "fresh": None, "sources": [("CO-Q2-MP", "winners"), ("EL-Q2", "losers")]},
    {"id": "CO-PO-CP", "comp": "Conference League", "round": "Play-off round", "path": "Champions Path",
     "fresh": None, "sources": [("CO-Q3-CP", "winners"), ("EL-Q3-CP", "losers")]},
    {"id": "CO-PO-MP", "comp": "Conference League", "round": "Play-off round", "path": "Main Path",
     "fresh": "CO-PO", "sources": [("CO-Q3-MP", "winners"), ("EL-Q3-MP", "losers")]},
]
_BUCKETS_BY_ID = {b["id"]: b for b in _BUCKETS}
_TERMINAL_BUCKETS = {
    "Champions League": ["CL-PO-CP", "CL-PO-LP"],
    "Europa League": ["EL-PO"],
    "Conference League": ["CO-PO-CP", "CO-PO-MP"],
}
# A team eliminated in a HIGHER competition's very last round doesn't drop
# into the next competition's qualifying -- it's already proven strong
# enough to go straight into that competition's own League Phase. Confirmed
# against the 2026/27 Europa League and Conference League Wikipedia
# articles' own League Phase distribution tables (which list these losers
# by name alongside the domestic-position/cup-winner direct entries, not
# under the Play-off round): Champions League Play-off round losers (both
# paths) AND Champions League Third Qualifying Round League Path losers
# (who never get a further qualifying tie at all) go straight into the
# Europa League's League Phase; Europa League Play-off round losers go
# straight into the Conference League's League Phase.
_EXTRA_LEAGUE_PHASE_SOURCES: dict[str, list[tuple[str, str]]] = {
    "Champions League": [],
    "Europa League": [("CL-PO-CP", "losers"), ("CL-PO-LP", "losers"), ("CL-Q3-LP", "losers")],
    "Conference League": [("EL-PO", "losers")],
}
_EXTRA_LEAGUE_PHASE_ROUTE = {
    "Europa League": "Transferred from Champions League",
    "Conference League": "Transferred from Europa League",
}


def _fresh_entries(comp: str, label: str) -> list[dict]:
    return [e for e in ACCESS_LIST_2027_28[comp] if e["label"] == label]


def _resolve_pool_clubs(entries: list[dict], comp: str) -> tuple[list[dict], list[str]]:
    """[{"team", "coeff", "country", "badge"}] for every entry that
    resolves to a real club, plus a list of one-line exclusion notes for
    entries that didn't (undetermined slots, e.g. Russia's suspended
    associations -- can't pair a non-existent club)."""
    clubs, excluded = [], []
    for e in entries:
        occ_note = _resolve_country_slots(e["country"]).get((comp, e["code"]))
        occupant, note = occ_note if occ_note else ("—", e.get("note") or "not yet determined")
        if occupant == "—":
            excluded.append(f"{e['country']} ({e['label']}): {note}")
            continue
        country_key = _country_key(e["country"])
        clubs.append({
            "team": occupant,
            "coeff": get_coeff_2027(occupant, country_key),
            "country": e["country"],
            "badge": _badge_lookup_for_country(e["country"]).get(occupant, ""),
        })
    return clubs, excluded


def _simulate_round(pool: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Seeded-vs-unseeded pairing (nations_league_simulator._pair_playoff_
    pool: strongest vs weakest, same "most likely single draw" convention
    used throughout this project) + two-legged win probability
    (simulator.two_leg_advance_odds, neutral home advantage since no real
    draw has set a leg order yet -- same convention project_league_a_
    finals uses for an unknown-venue match). Returns (tie rows for
    display, winning club dicts, losing club dicts) -- losers matter here
    since the real cascade carries them into a DIFFERENT competition's
    bucket (see _BUCKETS)."""
    if not pool:
        return [], [], []
    ranked = sorted(pool, key=lambda c: -c["coeff"])
    bye = None
    if len(ranked) % 2 == 1:
        bye = ranked[0]
        ranked = ranked[1:]
    by_name = {c["team"]: c for c in ranked}
    names = list(by_name.keys())

    ties, winners, losers = [], [], []
    for a, b in _pair_playoff_pool(names):
        ratings_df = pd.DataFrame({"team": [a, b], "opta_rating": [by_name[a]["coeff"], by_name[b]["coeff"]]})
        odds = two_leg_advance_odds(a, b, ratings_df, home_advantage=1.0)
        pct_a, pct_b = odds["team1_adv"] * 100, odds["team2_adv"] * 100
        winner, loser = (by_name[a], by_name[b]) if pct_a >= pct_b else (by_name[b], by_name[a])
        ties.append({
            "A Badge": by_name[a]["badge"], "Club A": a, "A %": round(pct_a, 1),
            "B Badge": by_name[b]["badge"], "Club B": b, "B %": round(pct_b, 1),
            "Predicted winner": winner["team"],
        })
        winners.append(winner)
        losers.append(loser)
    if bye is not None:
        ties.append({
            "A Badge": bye["badge"], "Club A": bye["team"], "A %": None,
            "B Badge": "", "Club B": "— (bye)", "B %": None,
            "Predicted winner": bye["team"],
        })
        winners.append(bye)
    return ties, winners, losers


@st.cache_data(ttl=60, show_spinner=False)
def _simulate_full_bracket() -> dict[str, dict]:
    """Every bucket's {"ties", "winners", "losers", "excluded"}, processed
    in round order (Q1 -> Q2 -> Q3 -> PO) across all 3 competitions at
    once -- the real cross-competition cascade means a later round's
    bucket can depend on an EARLIER round's bucket from a DIFFERENT
    competition (e.g. Conference League's Q2 Champions Path is entirely
    Champions League Q1 losers), so round order alone is a valid
    processing order; nothing ever depends on a same-round bucket."""
    results: dict[str, dict] = {}
    for round_name in STAGE_ORDER_2027_28:
        if round_name == "League Phase (direct)":
            continue
        for bucket in [b for b in _BUCKETS if b["round"] == round_name]:
            pool: list[dict] = []
            excluded: list[str] = []
            if bucket["fresh"]:
                fresh_clubs, fresh_excluded = _resolve_pool_clubs(_fresh_entries(bucket["comp"], bucket["fresh"]), bucket["comp"])
                pool.extend(fresh_clubs)
                excluded.extend(fresh_excluded)
            for src_id, kind in bucket["sources"]:
                pool.extend(results[src_id][kind])
            ties, winners, losers = _simulate_round(pool)
            results[bucket["id"]] = {"ties": ties, "winners": winners, "losers": losers, "excluded": excluded}
    return results


_TIES_COLUMN_CONFIG = {
    "No.": st.column_config.NumberColumn("No.", width="small"),
    "A Badge": st.column_config.ImageColumn("", width="small"),
    "Club A": st.column_config.TextColumn("Club A", width="medium"),
    "A %": st.column_config.NumberColumn("A %", width="small", format="%.1f%%"),
    "B Badge": st.column_config.ImageColumn("", width="small"),
    "Club B": st.column_config.TextColumn("Club B", width="medium"),
    "B %": st.column_config.NumberColumn("B %", width="small", format="%.1f%%"),
    "Predicted winner": st.column_config.TextColumn("Predicted winner", width="medium"),
}


st.title("🔮 European Competitions 2027/28")

comp_name = st.selectbox("Competition", list(ACCESS_LIST_2027_28.keys()), key="comp_select")
comp_entries = ACCESS_LIST_2027_28[comp_name]

with st.spinner("Projecting the qualifying rounds…"):
    bracket = _simulate_full_bracket()

entries_tab, qualifiers_tab, league_stage_tab = st.tabs(
    ["📋 Projected Entries", "🏁 Predicted Qualifiers", "🏆 Predicted League Stage"]
)

with entries_tab:
    st.caption(
        "UEFA's official 2027/28 access list (circular 54/2026), connected live to each "
        "country's PREDICTED FINAL 2026/27 league table (this site's own full-season "
        "simulation, not the current early-season table, which is noisy this far out). "
        "Every occupant below is provisional -- domestic seasons run until roughly "
        "May/June 2027, and nothing about the actual "
        "2027/28 qualifying draw exists yet. Each round is split into the real Champions "
        "Path / League Path (or Main Path) sections this competition actually used in its "
        "2026/27 qualifying, confirmed against that season's Wikipedia articles -- a path "
        "with no access-list slots of its own (its clubs come entirely from a higher "
        "competition's eliminations) shows a short note instead of an empty table; see the "
        "Predicted Qualifiers tab for that cascade. Coefficient is each club's live UEFA "
        "5-year club ranking ([kassiesa.net](https://kassiesa.net/uefa/data/method5/trank2027.html), "
        "still accumulating through 2026/27) -- a club with no individual European history "
        "inherits its country's floor value instead. Seeding splits each section's own clubs "
        "into the top/bottom half by that coefficient, matching how UEFA draws each round's "
        "pots. Rows sort Seeded, then Unseeded, then undetermined slots (e.g. Russia's "
        "suspended associations) last. A Cup Winner slot shows a predicted winner "
        "(highest-rated team not yet out of its domestic cup); if that club already holds a "
        "different slot via league position, the vacated continental slot passes to the next "
        "unclaimed league position instead of sitting empty."
    )

    n_direct = sum(1 for e in comp_entries if e["round"] == "League Phase (direct)")
    n_total = len(comp_entries)
    st.markdown(
        f"**{n_total} slots** in the 2027/28 access list -- **{n_direct} already go straight "
        f"to the 36-team League Phase**, the rest work through qualifying."
    )

    qd = QUALIFYING_DATES_2027_28[comp_name]
    comp_buckets = [b for b in _BUCKETS if b["comp"] == comp_name]

    for stage in STAGE_ORDER_2027_28:
        if stage == "League Phase (direct)":
            stage_entries = [e for e in comp_entries if e["round"] == stage]
            if not stage_entries:
                continue
            dates = qd.get("League Phase")
            date_str = f" — {dates['leg1']}" if dates else ""
            st.markdown(f"#### {stage}{date_str}")
            rows = [
                _club_row(*_resolve_country_slots(e["country"]).get((comp_name, e["code"]), ("—", e.get("note") or "not yet determined")),
                          e["country"], e["label"], e["route"])
                for e in stage_entries
            ]
            _seed_and_sort(rows)
            df = pd.DataFrame(_number_rows(rows))
            st.dataframe(df, column_config=_ENTRIES_COLUMN_CONFIG, use_container_width=True, hide_index=True,
                         height=len(df) * 35 + 38)
            continue

        stage_buckets = [b for b in comp_buckets if b["round"] == stage]
        if not stage_buckets:
            continue
        dates = qd.get({
            "First qualifying round": "First Qualifying Round",
            "Second qualifying round": "Second Qualifying Round",
            "Third qualifying round": "Third Qualifying Round",
            "Play-off round": "Play-off Round",
        }[stage])
        date_str = ""
        if dates:
            date_str = f" — {dates['leg1']}" + (f" / {dates['leg2']}" if dates.get("leg2") else "")

        for bucket in stage_buckets:
            path_label = f" — {bucket['path']}" if bucket["path"] else ""
            st.markdown(f"#### {stage}{path_label}{date_str}")
            if not bucket["fresh"]:
                st.caption(
                    "No access-list slots of its own -- this path's clubs come entirely from "
                    "a higher competition's eliminations. See the Predicted Qualifiers tab."
                )
                continue
            fresh = _fresh_entries(comp_name, bucket["fresh"])
            rows = [
                _club_row(*_resolve_country_slots(e["country"]).get((comp_name, e["code"]), ("—", e.get("note") or "not yet determined")),
                          e["country"], e["label"], e["route"])
                for e in fresh
            ]
            _seed_and_sort(rows)
            df = pd.DataFrame(_number_rows(rows))
            st.dataframe(df, column_config=_ENTRIES_COLUMN_CONFIG, use_container_width=True, hide_index=True,
                         height=len(df) * 35 + 38)

    st.divider()
    st.caption(
        "Not shown: UCL/UEL defending-titleholder byes, and the Conference League "
        "titleholder's promotion into the Europa League (all three depend on who wins "
        "the 2026/27 finals). England and Germany's 5th Champions League slot above "
        "assumes they again receive 2027/28's 2 \"European Performance Spot\" bonus "
        "places -- predicted, not yet confirmed by UEFA (awarded after 2026/27 ends, by "
        "aggregate club coefficient) -- see entrants_2027_28.py's own docstring for the "
        "full picture, including how Russia's ongoing suspension is handled. One real "
        "simplification in the cross-competition cascade: a small number of Champions "
        "League First Qualifying Round losers really drop into the Conference League's "
        "Third (not Second) Qualifying Round Champions Path, for bracket-size balancing -- "
        "all of them are shown dropping into the Second Qualifying Round here instead."
    )


with qualifiers_tab:
    st.caption(
        "Projects the qualifying rounds themselves, round by round, from today's most-likely "
        "occupant of every access-list slot (Projected Entries tab) -- not UEFA's actual random "
        "draw (which doesn't exist yet) or its same-association protection. Each round's own "
        "pool is split Seeded/Unseeded by live club coefficient and paired strongest vs weakest; "
        "win probability per two-legged tie comes from this site's own Poisson match model at a "
        "neutral venue (no real leg order is set yet). Champions Path, League Path and Main Path "
        "are kept separate exactly as far as the real 2026/27 qualifying kept them separate, "
        "including the real cross-competition cascade -- Champions League Champions/League Path "
        "losers drop into the Europa League; Europa League losers (including ex-Champions League "
        "clubs) drop into the Conference League. An odd pool gives its single strongest club a "
        "bye rather than inventing an opponent."
    )

    comp_buckets = [b for b in _BUCKETS if b["comp"] == comp_name]
    for stage in STAGE_ORDER_2027_28:
        stage_buckets = [b for b in comp_buckets if b["round"] == stage]
        for bucket in stage_buckets:
            result = bracket[bucket["id"]]
            path_label = f" — {bucket['path']}" if bucket["path"] else ""
            st.markdown(f"#### {stage}{path_label}")
            if result["excluded"]:
                st.caption("Excluded (no determined club): " + "; ".join(result["excluded"]))
            if not result["ties"]:
                st.caption("No clubs in this round's pool.")
                continue
            tie_df = pd.DataFrame(_number_rows(result["ties"]))
            st.dataframe(tie_df, column_config=_TIES_COLUMN_CONFIG, use_container_width=True, hide_index=True,
                         height=len(tie_df) * 35 + 38)

    st.divider()
    st.caption(
        "Play-off round winners join the League Phase (direct) clubs from the Projected "
        "Entries tab to complete the 36-team field -- see the Predicted League Stage tab."
    )


with league_stage_tab:
    st.caption(
        "The predicted 36-club League Phase: the League Phase (direct) entrants from the "
        "Projected Entries tab, the Play-off round's predicted winners from the Predicted "
        "Qualifiers tab (both Champions/League/Main Path brackets where the competition has "
        "one), and -- for Europa League and Conference League -- the clubs eliminated at the "
        "very last hurdle of the competition above, who go straight into this League Phase "
        "rather than drop into this competition's own qualifying (confirmed against the "
        "2026/27 Europa League and Conference League Wikipedia articles' own League Phase "
        "distribution). Sorted by live club coefficient, highest first -- the same ranking "
        "that would set the real League Phase's 4 pots, though the actual pot draw doesn't "
        "exist yet either."
    )

    direct_entries = [e for e in comp_entries if e["round"] == "League Phase (direct)"]
    direct_clubs, direct_excluded = _resolve_pool_clubs(direct_entries, comp_name)

    po_winners: list[dict] = []
    po_excluded: list[str] = []
    for bucket_id in _TERMINAL_BUCKETS[comp_name]:
        po_winners.extend(bracket[bucket_id]["winners"])
        po_excluded.extend(bracket[bucket_id]["excluded"])

    transferred: list[dict] = []
    for bucket_id, kind in _EXTRA_LEAGUE_PHASE_SOURCES[comp_name]:
        transferred.extend(bracket[bucket_id][kind])

    stage_rows = [
        {
            "Badge": c["badge"], "Club": c["team"], "Flag": flag_url(_country_key(c["country"])),
            "Country": c["country"], "Coefficient": c["coeff"], "Route": "Direct entry",
        }
        for c in direct_clubs
    ] + [
        {
            "Badge": c["badge"], "Club": c["team"], "Flag": flag_url(_country_key(c["country"])),
            "Country": c["country"], "Coefficient": c["coeff"], "Route": "Qualified via play-offs",
        }
        for c in po_winners
    ] + [
        {
            "Badge": c["badge"], "Club": c["team"], "Flag": flag_url(_country_key(c["country"])),
            "Country": c["country"], "Coefficient": c["coeff"], "Route": _EXTRA_LEAGUE_PHASE_ROUTE.get(comp_name, ""),
        }
        for c in transferred
    ]
    stage_rows.sort(key=lambda r: -r["Coefficient"])

    excluded = direct_excluded + po_excluded
    st.markdown(f"**{len(stage_rows)} of 36 slots** currently resolve to a predicted club.")
    if excluded:
        st.caption("Excluded (no determined club): " + "; ".join(excluded))

    stage_df = pd.DataFrame(_number_rows(stage_rows))
    st.dataframe(
        stage_df,
        column_config={
            "No.": st.column_config.NumberColumn("No.", width="small"),
            "Badge": st.column_config.ImageColumn("", width="small"),
            "Club": st.column_config.TextColumn("Club", width="medium"),
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Country": st.column_config.TextColumn("Country", width="small"),
            "Coefficient": st.column_config.NumberColumn("Coefficient", width="small", format="%.3f"),
            "Route": st.column_config.TextColumn("Route", width="medium"),
        },
        use_container_width=True, hide_index=True, height=len(stage_df) * 35 + 38,
    )

    st.divider()
    st.markdown("##### Clubs per country")
    country_counts: dict[str, int] = {}
    for r in stage_rows:
        country_counts[r["Country"]] = country_counts.get(r["Country"], 0) + 1
    count_rows = [
        {"Flag": flag_url(_country_key(country)), "Country": country, "Clubs": n}
        for country, n in sorted(country_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    count_df = pd.DataFrame(_number_rows(count_rows))
    st.dataframe(
        count_df,
        column_config={
            "No.": st.column_config.NumberColumn("No.", width="small"),
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Country": st.column_config.TextColumn("Country", width="medium"),
            "Clubs": st.column_config.NumberColumn("Clubs", width="small"),
        },
        use_container_width=True, hide_index=True, height=len(count_df) * 35 + 38,
    )
