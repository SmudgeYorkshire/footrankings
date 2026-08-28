"""
Projects the UEFA European Competitions' Play-off round outcomes and the
resulting 36-club League Phase fields, shared by european.py (the
Qualifying Predictions tab) and country_ranking_simulator.py (which needs
the same field projection to simulate League Phase + Knockout points).

Split out from european.py so this reusable logic can be imported without
pulling in that file's top-level page-rendering code (which runs
immediately on import) -- see coefficients_live.py for the same pattern
applied to the Coefficients page.
"""

import os
import unicodedata

import streamlit as st
import pandas as pd
from pathlib import Path

from config import EUROPEAN_COMPETITIONS, LEAGUES
from api_football_fetcher import ApiFootballClient
from simulator import two_leg_advance_odds
from qualifying_bracket import PLAYOFF_BRACKET, CONFIRMED_LEAGUE_PHASE
from coefficients_live import _load_club_country_map

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_CURRENT_EURO_SEASON = "2026-2027"  # only the current season is tracked

_PLAYOFF_ROUND_NAMES = frozenset({"Play-offs", "Playoff round"})

# Since the 2024-27 reformed "Swiss model" format, a club eliminated in
# one competition's Play-off round doesn't drop out of Europe -- it's
# parachuted straight into the NEXT competition down's League Phase (not
# its qualifying). Champions League Play-off losers -> Europa League
# League Phase; Europa League Play-off losers -> Conference League League
# Phase. _project_league_phase_field below folds these in for EL/ECL.
_CASCADE_FROM = {"Europa League": "Champions League", "Conference League": "Europa League"}


@st.cache_data(ttl=60, show_spinner=False)
def _load_combined_ratings() -> pd.DataFrame:
    """Merge all domestic league ratings CSVs into one DataFrame.

    Short TTL (matches the sitewide live-data convention) rather than the
    1h this used to have — this only reads local CSVs (cheap, no API
    quota at stake), and a long TTL meant Qualifying Predictions odds
    could keep using a rating for up to an hour after admin.py saved a
    new one.
    """
    rows = []
    for league_cfg in LEAGUES.values():
        csv_path = Path("ratings") / f"{league_cfg.get('tsdb_id', league_cfg['id'])}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, dtype=str)
            if "team" in df.columns and "opta_rating" in df.columns:
                if "alias" not in df.columns:
                    df["alias"] = ""
                df["alias"] = df["alias"].fillna("")
                df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
                rows.append(df[["team", "alias", "opta_rating"]].dropna(subset=["opta_rating"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["team", "alias", "opta_rating"])


def _normalize_club_name(s: str) -> str:
    """Accent/case-insensitive form for fuzzy club-name matching."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


@st.cache_data(ttl=60, show_spinner=False)
def _load_ratings_by_country() -> dict[str, pd.DataFrame]:
    """{country: DataFrame[team, alias, opta_rating]}, scoped per country
    rather than one global name-keyed table. A flat global lookup (as
    _load_combined_ratings gives) collides whenever two clubs in different
    countries share a literal name -- e.g. English Arsenal vs a Belarusian
    club also named "Arsenal" -- silently overwriting one with the other's
    rating. Scoping by country (known for every League Phase field entry)
    avoids that entirely."""
    by_country: dict[str, list[pd.DataFrame]] = {}
    for league_cfg in LEAGUES.values():
        country = league_cfg.get("country", "")
        csv_path = Path("ratings") / f"{league_cfg.get('tsdb_id', league_cfg['id'])}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str)
        if "team" not in df.columns or "opta_rating" not in df.columns:
            continue
        if "alias" not in df.columns:
            df["alias"] = ""
        df["alias"] = df["alias"].fillna("")
        df["opta_rating"] = pd.to_numeric(df["opta_rating"], errors="coerce")
        by_country.setdefault(country, []).append(
            df[["team", "alias", "opta_rating"]].dropna(subset=["opta_rating"])
        )
    return {c: pd.concat(dfs, ignore_index=True) for c, dfs in by_country.items()}


def _resolve_field_ratings(field: list[dict]) -> pd.DataFrame:
    """One opta_rating per League Phase field club, matched only within
    that club's own country's ratings CSV(s) -- collision-proof (see
    _load_ratings_by_country) and tolerant of naming drift between
    qualifying_bracket.py's display names and the ratings/alias columns
    (e.g. "Inter Milan" vs the CSV's "Internazionale"/"Inter") via a
    normalized, then substring, fallback match. Any club that still can't
    be resolved gets the mean rating of the clubs that could -- a safer
    default than the mean of a random cross-section of every domestic
    league (including part-time minnows), which is what falling through
    to the flat global lookup would otherwise silently produce."""
    by_country = _load_ratings_by_country()
    resolved: list[dict] = []
    unresolved: list[dict] = []
    for f in field:
        team, country = f["team"], f["country"]
        df = by_country.get(country)
        rating = None
        if df is not None and not df.empty:
            exact = df[(df["team"] == team) | (df["alias"] == team)]
            if not exact.empty:
                rating = float(exact.iloc[0]["opta_rating"])
            else:
                norm_team = _normalize_club_name(team)
                norm_team_series = df["team"].map(_normalize_club_name)
                norm_alias_series = df["alias"].map(_normalize_club_name)
                exact_norm = df[(norm_team_series == norm_team) | (norm_alias_series == norm_team)]
                if not exact_norm.empty:
                    rating = float(exact_norm.iloc[0]["opta_rating"])
                else:
                    contains = df[
                        norm_team_series.apply(lambda n: n in norm_team or norm_team in n)
                        | norm_alias_series.apply(lambda n: bool(n) and (n in norm_team or norm_team in n))
                    ]
                    if not contains.empty:
                        rating = float(contains.iloc[0]["opta_rating"])
        row = {"team": team, "alias": "", "opta_rating": rating}
        (resolved if rating is not None else unresolved).append(row)
    if unresolved and resolved:
        fallback = sum(r["opta_rating"] for r in resolved) / len(resolved)
        for row in unresolved:
            row["opta_rating"] = fallback
    return pd.DataFrame(resolved + unresolved)


def _leg_aggregate_winner(
    t1: str, t2: str, l1h: int, l1a: int, l2h: int, l2a: int,
    l1_pen: tuple[int, int] | None = None, l2_pen: tuple[int, int] | None = None,
) -> str | None:
    """Two-leg aggregate winner (t1 was leg1's home team, t2 leg1's away
    team; leg2 has them swapped). If level on aggregate, falls back to
    whichever leg's penalty shootout is recorded -- l1_pen/l2_pen are that
    leg's own (home_pens, away_pens), so l1_pen's home side is t1 and
    l2_pen's home side is t2. None only if level on aggregate with no
    penalty data available."""
    agg_t1 = l1h + l2a
    agg_t2 = l1a + l2h
    if agg_t1 > agg_t2:
        return t1
    if agg_t2 > agg_t1:
        return t2
    if l2_pen is not None and l2_pen[0] != l2_pen[1]:
        return t2 if l2_pen[0] > l2_pen[1] else t1
    if l1_pen is not None and l1_pen[0] != l1_pen[1]:
        return t1 if l1_pen[0] > l1_pen[1] else t2
    return None


def _leg_penalty_score(leg: dict) -> tuple[int, int] | None:
    ph, pa = leg.get("intPenaltyHome"), leg.get("intPenaltyAway")
    if ph is None or pa is None:
        return None
    return (int(ph), int(pa))


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_comp_fixtures(comp_name: str, key: str):
    """played, remaining fixtures for any of the 3 competitions, by name."""
    cid = EUROPEAN_COMPETITIONS[comp_name]["id"]
    client = ApiFootballClient(api_key=key)
    return client.get_fixtures(cid, _CURRENT_EURO_SEASON)


def _resolve_bracket_side(side: tuple, ratings_df: pd.DataFrame) -> dict:
    """Resolve one side of a projected Play-off tie.

    Returns {"label": str|None, "status": "confirmed"|"predicted"|"tbd",
             "pct": float|None}.
    """
    if side[0] == "team":
        return {"label": side[1], "status": "confirmed", "pct": None}

    _, comp, name_set, which = side
    played, remaining = _fetch_comp_fixtures(comp, _API_KEY)
    qr3_played    = [f for f in played    if f.get("strRound") == "3rd Qualifying Round"]
    qr3_remaining = [f for f in remaining if f.get("strRound") == "3rd Qualifying Round"]
    played_ids = {f.get("idEvent") for f in qr3_played}
    all_qr3 = qr3_played + qr3_remaining

    tie_map: dict[frozenset, list[dict]] = {}
    for f in all_qr3:
        pair = frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")})
        tie_map.setdefault(pair, []).append(f)

    match_legs = tie_map.get(frozenset(name_set))
    if match_legs is None:
        for pair, legs in tie_map.items():
            if pair & name_set:
                match_legs = legs
                break
    if match_legs is None:
        return {"label": None, "status": "tbd", "pct": None}

    legs = sorted(match_legs, key=lambda x: x.get("dateEvent", ""))
    leg1 = legs[0]
    leg2 = legs[1] if len(legs) > 1 else None
    t1 = leg1.get("strHomeTeam", "")
    t2 = leg1.get("strAwayTeam", "")
    l1_played = leg1.get("idEvent") in played_ids
    l2_played = leg2 is not None and leg2.get("idEvent") in played_ids

    if l1_played and l2_played:
        winner = _leg_aggregate_winner(
            t1, t2,
            int(leg1["intHomeScore"] or 0), int(leg1["intAwayScore"] or 0),
            int(leg2["intHomeScore"] or 0), int(leg2["intAwayScore"] or 0),
            l1_pen=_leg_penalty_score(leg1), l2_pen=_leg_penalty_score(leg2),
        )
        loser  = t2 if winner == t1 else (t1 if winner == t2 else None)
        chosen = winner if which == "winner" else loser
        return {"label": chosen or "TBD (penalties)", "status": "confirmed", "pct": None}

    leg1_score = None
    if l1_played:
        leg1_score = (int(leg1.get("intHomeScore") or 0), int(leg1.get("intAwayScore") or 0))
    odds = two_leg_advance_odds(t1, t2, ratings_df, leg1_score=leg1_score)
    t1_pct, t2_pct = odds["team1_adv"], odds["team2_adv"]
    if which == "winner":
        chosen, pct = (t1, t1_pct) if t1_pct >= t2_pct else (t2, t2_pct)
    else:
        chosen, pct = (t2, t2_pct) if t1_pct >= t2_pct else (t1, t1_pct)
    return {"label": chosen, "status": "predicted", "pct": pct}


def _resolve_playoff_tie_odds(team_a: str, team_b: str, comp_name: str, ratings_df: pd.DataFrame) -> dict | None:
    """Once both sides of a projected Play-off tie are confirmed real
    clubs, find their actual scheduled Play-off fixture(s) and compute
    THIS tie's own two-leg advance odds -- not the probability of having
    reached the slot (that's _resolve_bracket_side's job), but the
    probability of winning the Play-off tie itself. Incorporates leg 1's
    real result once it's played. Returns None if no such fixture exists
    yet (e.g. one side is still only a prediction, so there's nothing
    scheduled to look up)."""
    played, remaining = _fetch_comp_fixtures(comp_name, _API_KEY)
    po_played    = [f for f in played    if f.get("strRound") in _PLAYOFF_ROUND_NAMES]
    po_remaining = [f for f in remaining if f.get("strRound") in _PLAYOFF_ROUND_NAMES]
    played_ids = {f.get("idEvent") for f in po_played}
    all_po = po_played + po_remaining

    # Team names sometimes drift slightly between rounds in the provider's
    # own data (e.g. "LASK" earlier vs "Lask Linz" here, "AEK Athens" vs
    # "AEK Athens FC") -- try an exact pair match first, then fall back to
    # any fixture sharing at least one of the two names, same pattern
    # _resolve_bracket_side already uses for this.
    tie_map: dict[frozenset, list[dict]] = {}
    for f in all_po:
        tie_map.setdefault(frozenset({f.get("strHomeTeam", ""), f.get("strAwayTeam", "")}), []).append(f)

    pair = frozenset({team_a, team_b})
    legs = tie_map.get(pair)
    if legs is None:
        for fpair, flegs in tie_map.items():
            if fpair & pair:
                legs = flegs
                break
    if legs is None:
        return None
    legs = sorted(legs, key=lambda x: x.get("dateEvent", ""))
    leg1 = legs[0]
    leg2 = legs[1] if len(legs) > 1 else None
    t1, t2 = leg1.get("strHomeTeam", ""), leg1.get("strAwayTeam", "")
    l1_played = leg1.get("idEvent") in played_ids
    l2_played = leg2 is not None and leg2.get("idEvent") in played_ids

    if l1_played and l2_played:
        winner = _leg_aggregate_winner(
            t1, t2,
            int(leg1["intHomeScore"] or 0), int(leg1["intAwayScore"] or 0),
            int(leg2["intHomeScore"] or 0), int(leg2["intAwayScore"] or 0),
            l1_pen=_leg_penalty_score(leg1), l2_pen=_leg_penalty_score(leg2),
        )
        return {"status": "decided", "team1": t1, "team2": t2, "winner": winner}

    leg1_score = None
    if l1_played:
        leg1_score = (int(leg1.get("intHomeScore") or 0), int(leg1.get("intAwayScore") or 0))
    odds = two_leg_advance_odds(t1, t2, ratings_df, leg1_score=leg1_score)
    return {
        "status": "predicted", "team1": t1, "team2": t2,
        "team1_adv": odds["team1_adv"], "team2_adv": odds["team2_adv"],
        "leg1_played": l1_played, "leg1_score": leg1_score,
    }


def _resolve_bracket_tie(
    side_a: tuple, side_b: tuple, comp_name: str, ratings_df: pd.DataFrame,
) -> tuple[str | None, str | None]:
    """(winner, loser) for one Play-off bracket pairing -- the tie's real
    advance odds when both sides are confirmed teams (using the favoured
    side immediately, without waiting for a leg to be played), falling
    back to each slot's own reaching-this-slot favourite otherwise."""
    ra = _resolve_bracket_side(side_a, ratings_df)
    rb = _resolve_bracket_side(side_b, ratings_df)
    winner = loser = None
    if ra["status"] == "confirmed" and rb["status"] == "confirmed" and ra["label"] and rb["label"]:
        tie = _resolve_playoff_tie_odds(ra["label"], rb["label"], comp_name, ratings_df)
        if tie:
            if tie["status"] == "decided":
                winner = tie["winner"]
                loser = tie["team2"] if winner == tie["team1"] else tie["team1"]
            elif tie["team1_adv"] >= tie["team2_adv"]:
                winner, loser = tie["team1"], tie["team2"]
            else:
                winner, loser = tie["team2"], tie["team1"]
    if winner is None:
        a_pct, b_pct = ra.get("pct") or 0.0, rb.get("pct") or 0.0
        if a_pct >= b_pct:
            winner, loser = ra["label"], rb["label"]
        else:
            winner, loser = rb["label"], ra["label"]
        winner = winner or ra["label"] or rb["label"]
    return winner, loser


def _project_league_phase_field(comp_name: str, ratings_df: pd.DataFrame) -> list[dict]:
    """Confirmed direct League Phase entrants + this competition's own
    Play-off winners + (for Europa/Conference League) the Play-off losers
    parachuted down from the competition above. Returns
    [{"team", "country"}, ...] -- fewer than 36 entries means some data
    (confirmed entrant lists, Play-off bracket pairings) isn't available
    yet for this competition."""
    club_country = _load_club_country_map()
    field: list[dict] = []
    seen: set[str] = set()

    def _add(team: str | None) -> None:
        if team and team not in seen:
            field.append({"team": team, "country": club_country.get(team, "Unknown")})
            seen.add(team)

    for team, country, _flag in CONFIRMED_LEAGUE_PHASE.get(comp_name, []):
        if team not in seen:
            field.append({"team": team, "country": country})
            seen.add(team)

    for side_a, side_b in PLAYOFF_BRACKET.get(comp_name, []):
        winner, _loser = _resolve_bracket_tie(side_a, side_b, comp_name, ratings_df)
        _add(winner)

    upstream = _CASCADE_FROM.get(comp_name)
    if upstream:
        for side_a, side_b in PLAYOFF_BRACKET.get(upstream, []):
            _winner, loser = _resolve_bracket_tie(side_a, side_b, upstream, ratings_df)
            _add(loser)

    return field
