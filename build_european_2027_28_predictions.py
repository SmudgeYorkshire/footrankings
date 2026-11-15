"""
Daily precompute for european_2027_28.py's three most expensive per-
country computations (predicted final standings, the finishing-position
probability matrix, and the predicted domestic cup winner), plus the
dynamically-resolved "UCL Titleholder bye" cascade (see
access_list_permutations_2027_28.py's own "ucl_titleholder_bye"
permutation, which reads this script's own output).

Why: european_2027_28.py used to run simulate_season() (and a cup-winner
sub-simulation) LIVE, for every one of the ~50 countries in the 2027/28
UEFA access list, on EVERY page load -- confirmed to take several
minutes to load (2026-11-15), same root cause already fixed for the Club
and Nation Strength Rankings pages via a daily precompute + CSV read
(build_club_power_rankings.py / build_nation_power_rankings.py). This
script is that same fix for this page: run it once a day (see
.github/workflows/daily_odds_and_ratings.yml), write the results to
disk, and european_2027_28.py just reads them back.

Writes:
  european_2027_28_predicted_standings.csv   -- league_name, intRank, strTeam, strBadge
  european_2027_28_position_probs.csv        -- league_name, strTeam, position, probability
  european_2027_28_predicted_cup_winners.csv -- league_name, team, note
  european_2027_28_ucl_titleholder_bye.csv   -- see _build_titleholder_bye's own docstring
  european_2027_28_uel_titleholder_bye.csv   -- see _build_uel_titleholder_bye's own docstring
  european_2027_28_uecl_titleholder_bye.csv  -- see _build_uecl_titleholder_bye's own docstring

Usage: py build_european_2027_28_predictions.py
"""

import os
import sys

import pandas as pd

from config import LEAGUES
from entrants_2027_28 import ACCESS_LIST_2027_28 as DEFAULT_ACCESS_LIST_2027_28
from access_list_permutations_2027_28 import apply_permutations, _UEL_FIXED_PROMOTIONS
from club_coefficients_2027 import get_coeff_2027
from european_predictions_core import predicted_standings_and_probs, predict_cup_winner

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")

STANDINGS_OUT = "european_2027_28_predicted_standings.csv"
PROBS_OUT = "european_2027_28_position_probs.csv"
CUP_WINNERS_OUT = "european_2027_28_predicted_cup_winners.csv"
TITLEHOLDER_BYE_OUT = "european_2027_28_ucl_titleholder_bye.csv"
UEL_TITLEHOLDER_BYE_OUT = "european_2027_28_uel_titleholder_bye.csv"
UECL_TITLEHOLDER_BYE_OUT = "european_2027_28_uecl_titleholder_bye.csv"

# One CH entry per round currently sits in each of these Champions-Path
# labels (see _build_titleholder_bye) -- QR1 moves as a PAIR since UEFA's
# qualifying rounds are two-legged ties, so two QR1 clubs always advance
# together to fill one QR2 vacancy.
_CASCADE_TOP_N = {"CL-PO": 1, "CL-Q2": 1, "CL-Q1": 2}

# Every Champions League qualifying ("fresh entry") label, Champions Path
# and League Path alike -- see _build_uel_titleholder_bye's own docstring
# for why the Europa League Titleholder bye's own "high CH Q" comparison
# spans both, unlike ucl_titleholder_bye's Champions-Path-only pool.
_CL_QUALIFYING_PATH = {
    "CL-PO": "Champions Path", "CL-Q2": "Champions Path", "CL-Q1": "Champions Path",
    "CL-Q3nc": "League Path", "CL-Q2nc": "League Path",
}
_CL_PROMOTE_TO = {
    "CL-PO": "CL-LS", "CL-Q2": "CL-PO", "CL-Q1": "CL-Q2",
    "CL-Q3nc": "CL-LS", "CL-Q2nc": "CL-Q3nc",
}
_POSITION_OF_CODE = {"CH": 1, "N2": 2, "N3": 3, "N4": 4, "N5": 5, "N6": 6, "N7": 7}

# Europa League's own qualifying ("fresh entry") rounds, ordered low->high
# -- see _build_uecl_titleholder_bye's own docstring.
_EL_QUALIFYING_ORDER = ["EL-Q1", "EL-Q2", "EL-Q3", "EL-PO"]


def _all_tracked_leagues() -> list[str]:
    """Every distinct league_name any access-list entry points at, across
    all 3 competitions -- unaffected by which permutations are active (a
    permutation only ever changes an entry's label/round/note, never its
    country->league mapping), so the pure default list is enough here."""
    names = set()
    for entries in DEFAULT_ACCESS_LIST_2027_28.values():
        for e in entries:
            if e["league"]:
                names.add(e["league"])
    return sorted(names)


def _build_titleholder_bye(standings_by_league: dict[str, list[dict]]) -> None:
    """Resolve the "UCL Titleholder bye" cascade: when the 2026/27 UCL
    titleholder doesn't requalify for 2027/28 through its own domestic
    route, UEFA fills its guaranteed League Phase slot from the Champions
    Path club with the single highest UEFA club coefficient -- confirmed
    by the user as a fixed rule from their own primary source (not
    something this site derives independently), applied here by resolving
    WHICH club that is dynamically each run (live coefficients + each
    country's own live predicted champion), the same way every other
    occupant on this page is resolved, rather than hardcoding specific
    club names.

    Per that same confirmed rule: the Champions Path PO entrant with the
    highest coefficient is promoted PO -> League Phase (direct); the QR2
    entrant with the highest REMAINING coefficient (excluding whichever
    country just moved) then fills the vacated PO slot; the top-2
    REMAINING QR1 entrants (a pair, since QR1 ties are two-legged) fill
    the vacated QR2 slot. Resolved against the russia_suspension-applied
    list (Ukraine already promoted CL-Q1 -> CL-Q2, Russia's own entry
    excluded -- it has no club to resolve), so this cascade always layers
    on top of that one, never instead of it.

    A SEPARATE confirmed consequence (2 Conference League QR2 Champions
    Path clubs get a bye to QR3 Champions Path) is a structural effect of
    the shrunken CL-Q1 Champions Path pool, not a coefficient-rankable
    choice -- which 2 specific clubs get it depends on the real UEFA
    draw, not anything this site's live data can resolve, so it's
    recorded here only as a note for the Permutation Info tab to display,
    never as a specific club assignment.

    Writes TITLEHOLDER_BYE_OUT: one row per club that moves (competition,
    country, code, old_label, new_label, club, coefficient). Also returns
    that same list of movements, so _build_uel_titleholder_bye (a
    separate, independently-triggered titleholder event) can exclude
    whichever countries this one already claimed from its own pool."""
    access_list = apply_permutations(active=["russia_suspension"])
    pool: dict[str, list[dict]] = {label: [] for label in _CASCADE_TOP_N}
    for e in access_list["Champions League"]:
        if e["code"] != "CH" or e["path"] != "Champions Path":
            continue
        if e["label"] not in pool or e["country"] == "Russia":
            continue
        standings = standings_by_league.get(e["league"] or "")
        if not standings:
            continue
        champion = standings[0].get("strTeam", "")
        if not champion:
            continue
        try:
            coeff = get_coeff_2027(champion, e["country"])
        except Exception as exc:
            print(f"  coefficient lookup failed for {champion} ({e['country']}): {exc}", file=sys.stderr)
            continue
        pool[e["label"]].append({
            "country": e["country"], "code": e["code"], "route": e["route"],
            "club": champion, "coefficient": coeff,
        })

    _LABEL_ORDER = ["CL-PO", "CL-Q2", "CL-Q1"]
    _NEW_LABEL = {"CL-PO": "CL-LS", "CL-Q2": "CL-PO", "CL-Q1": "CL-Q2"}
    movements = []
    claimed_countries: set[str] = set()
    for label in _LABEL_ORDER:
        candidates = [c for c in pool[label] if c["country"] not in claimed_countries]
        candidates.sort(key=lambda c: -(c["coefficient"] or 0))
        top_n = _CASCADE_TOP_N[label]
        for c in candidates[:top_n]:
            movements.append({
                "competition": "Champions League", "country": c["country"], "code": c["code"],
                "old_label": label, "new_label": _NEW_LABEL[label],
                "club": c["club"], "coefficient": c["coefficient"],
            })
            claimed_countries.add(c["country"])

    pd.DataFrame(movements).to_csv(TITLEHOLDER_BYE_OUT, index=False)
    print(f"Wrote {len(movements)} UCL Titleholder bye movements to {TITLEHOLDER_BYE_OUT}")
    for m in movements:
        print(f"  {m['country']} ({m['club']}, coeff {m['coefficient']:.3f}): {m['old_label']} -> {m['new_label']}")
    return movements


def _build_uel_titleholder_bye(standings_by_league: dict[str, list[dict]], claimed_countries: set[str]) -> None:
    """Resolve the Champions League side of the "Europa League Titleholder
    bye" cascade (the fixed, non-coefficient Europa League QR1 -> QR2
    moves are hardcoded directly in access_list_permutations_2027_28.py
    instead -- they don't need live data).

    Confirmed by the user from their own primary source as a SEPARATE,
    independently-triggered real-world event from ucl_titleholder_bye
    (a different titleholder -- the 2026/27 Europa League champion --
    not requalifying, not the Champions League one), drawing from a
    WIDER candidate pool: the single highest-coefficient club across
    EVERY Champions League qualifying entry, Champions Path AND League
    Path alike (unlike ucl_titleholder_bye's Champions-Path-only pool) --
    confirmed live, 2026-11-15: Portugal's League Path N3 entry (Sporting
    CP) outranks every Champions Path entry on live coefficients, despite
    sitting at only CL-Q3nc, not even that path's own top round.
    claimed_countries (ucl_titleholder_bye's own already-resolved
    countries, passed in from the same run) are excluded here -- a club
    that event already promoted can't also be promoted by this one.

    That overall-highest club promotes one level toward the League Phase
    within its OWN path's chain (League Path: QR2nc -> QR3nc -> LS;
    Champions Path promotions are ucl_titleholder_bye's own exclusive
    domain, so if the overall highest (after exclusion) is still a
    Champions Path club, this step is skipped entirely -- rather than
    inventing a second, untested Champions-Path cascade under the wrong
    permutation's name). When the promoted club comes specifically from
    League Path's CL-Q3nc, the vacancy is backfilled by the top-2
    REMAINING League Path CL-Q2nc entries (confirmed by the user's own
    real example: Czech Rep./Denmark's N2 entries, Sparta Praha and
    Midtjylland) -- League Path has no lower rung after CL-Q2nc, so a
    club promoted FROM CL-Q2nc itself needs no further backfill.

    A SEPARATE, already-automatic consequence (fewer Europa League QR1
    losers cascading to Conference League QR2, more QR2 losers cascading
    to QR3, once the 4 fixed EL-Q1 -> EL-Q2 moves shrink/grow those pools)
    needs no special handling here -- european_2027_28.py's own
    _simulate_full_bracket already re-derives that cascade purely from
    each entry's (now-changed) label, exactly as russia_suspension's own
    promotions already do.

    Writes UEL_TITLEHOLDER_BYE_OUT: one row per Champions League club
    that moves (competition, country, code, old_label, new_label, club,
    coefficient) -- empty if the overall highest (after exclusion) is a
    Champions Path club, so there's nothing for this permutation to do
    this run."""
    access_list = apply_permutations(active=["russia_suspension"])
    pool = []
    for e in access_list["Champions League"]:
        if e["label"] not in _CL_QUALIFYING_PATH or e["country"] in ("Russia", *claimed_countries):
            continue
        standings = standings_by_league.get(e["league"] or "")
        if not standings:
            continue
        pos = _POSITION_OF_CODE.get(e["code"])
        if pos is None or pos > len(standings):
            continue
        club = standings[pos - 1].get("strTeam", "")
        if not club:
            continue
        try:
            coeff = get_coeff_2027(club, e["country"])
        except Exception as exc:
            print(f"  coefficient lookup failed for {club} ({e['country']}): {exc}", file=sys.stderr)
            continue
        pool.append({
            "country": e["country"], "code": e["code"], "route": e["route"], "label": e["label"],
            "path": _CL_QUALIFYING_PATH[e["label"]], "club": club, "coefficient": coeff,
        })

    movements = []
    if pool:
        pool.sort(key=lambda c: -(c["coefficient"] or 0))
        top = pool[0]
        if top["path"] == "League Path":
            movements.append({
                "competition": "Champions League", "country": top["country"], "code": top["code"],
                "old_label": top["label"], "new_label": _CL_PROMOTE_TO[top["label"]],
                "club": top["club"], "coefficient": top["coefficient"],
            })
            if top["label"] == "CL-Q3nc":
                remaining = [c for c in pool if c["label"] == "CL-Q2nc" and c["country"] != top["country"]]
                remaining.sort(key=lambda c: -(c["coefficient"] or 0))
                for c in remaining[:2]:
                    movements.append({
                        "competition": "Champions League", "country": c["country"], "code": c["code"],
                        "old_label": c["label"], "new_label": _CL_PROMOTE_TO[c["label"]],
                        "club": c["club"], "coefficient": c["coefficient"],
                    })
        else:
            print(
                f"  Europa League Titleholder bye: overall-highest unclaimed CL qualifying "
                f"coefficient ({top['club']}, {top['country']}) is a Champions Path club -- "
                f"skipping (that path's cascade belongs to ucl_titleholder_bye only).",
                file=sys.stderr,
            )

    pd.DataFrame(movements).to_csv(UEL_TITLEHOLDER_BYE_OUT, index=False)
    print(f"Wrote {len(movements)} Europa League Titleholder bye (CL side) movements to {UEL_TITLEHOLDER_BYE_OUT}")
    for m in movements:
        print(f"  {m['country']} ({m['club']}, coeff {m['coefficient']:.3f}): {m['old_label']} -> {m['new_label']}")
    return movements


def _apply_movements_locally(access_list: dict, movements: list[dict]) -> None:
    """Mutate access_list in place, relabelling every entry a movements
    list (country, code, new_label) names -- same effect as a
    permutation's own apply function, but using THIS RUN's own in-memory
    movements rather than access_list_permutations_2027_28's module-level
    dicts, which only refresh on the NEXT import, not mid-run (today's
    just-written CSVs wouldn't be picked up by apply_permutations() again
    within this same script execution). Needed so
    _build_uecl_titleholder_bye sees the Europa League access list
    exactly as it'll really look once ucl_titleholder_bye and
    uel_titleholder_bye have both already been layered on top -- e.g.
    Austria/Scotland/Sweden/Croatia's cup winners must already be out of
    EL-Q1 (promoted to EL-Q2 by uel_titleholder_bye's own fixed rule)
    before this cascade compares who's left in EL-Q1."""
    by_key = {(m["country"], m["code"]): m["new_label"] for m in movements}
    for entries in access_list.values():
        for e in entries:
            new_label = by_key.get((e["country"], e["code"]))
            if new_label:
                e["label"] = new_label


def _build_uecl_titleholder_bye(
    standings_by_league: dict[str, list[dict]],
    ucl_bye_movements: list[dict], uel_bye_movements: list[dict],
    cup_winner_by_league: dict[str, str] | None = None,
) -> None:
    """Resolve the "Conference League Titleholder bye" cascade: a THIRD
    separate, independently-triggered titleholder event (the 2026/27
    Conference League champion not requalifying), confirmed by the user
    from their own primary source.

    Pool: every Europa League qualifying entry (EL-Q1/Q2/Q3/PO, every
    position code, not just CW/CH -- unlike the Champions League
    cascades, EL's own fresh entries are a mix of cup winners and
    various league positions depending on the country). The single
    highest-coefficient club across that WHOLE pool promotes directly to
    EL-LS (League Phase direct), regardless of which of the 4 rounds it
    started in -- confirmed live, 2026-11-15: Turkey's own EL-Q2 entry
    (N3, Fenerbahce in the user's own real example) outranks even
    Turkey's OWN higher-round EL-PO entry (its cup winner), so this is a
    genuine open comparison across all 4 rounds, not just "whoever's
    already in PO".

    The vacancy is backfilled by the single highest-REMAINING candidate
    in the round immediately below the departed one (EL-Q1 < EL-Q2 <
    EL-Q3 < EL-PO) -- confirmed by the user's own example: Fenerbahce
    departs EL-Q2, so Slovakia's EL-Q1 entry (Slovan Bratislava) -- the
    highest-coefficient club left in EL-Q1 -- backfills EL-Q2. Only ONE
    club backfills here (not a two-legged pair like Champions League's
    own QR1 step) -- EL's qualifying rounds aren't paired the same way.

    Resolved against the FULLY cascaded list (russia_suspension +
    ucl_titleholder_bye + uel_titleholder_bye all already layered on,
    via _apply_movements_locally since those permutations' own module-
    level dicts won't reflect this same run's just-written files yet --
    see that helper's own docstring) -- in particular, Austria/Scotland/
    Sweden/Croatia must already be out of EL-Q1 before this cascade's own
    EL-Q1 comparison runs.

    A FOURTH, FIXED (non-coefficient) and CROSS-COMPETITION promotion --
    Moldova's Conference League cup-winner entry (CO-Q2) moves into
    Europa League's own EL-Q1, filling the vacancy Slovan Bratislava's
    own promotion leaves there -- is hardcoded as _UECL_FIXED_PROMOTIONS
    in access_list_permutations_2027_28.py instead of computed here (no
    live data needed), since unlike every other fixed promotion so far
    it needs to actually MOVE the entry between competitions, not just
    relabel it in place.

    Unlike the Champions League cascades (CH/N2-N4 only -- always a
    league position), Europa League's own fresh entries are heavily
    CW-coded (domestic cup winners -- Austria, Czech Rep., Turkey's
    EL-PO entry, Slovakia's EL-Q1 entry, etc.), which _POSITION_OF_CODE
    has no rank for (confirmed as a real bug while building this: every
    CW entry was silently skipped, since `pos = _POSITION_OF_CODE.get
    ("CW")` is None). cup_winner_by_league (league_name -> predicted
    cup-winning club, the exact same data this run already wrote to
    CUP_WINNERS_OUT) resolves those instead of a league standings
    position.

    Writes UECL_TITLEHOLDER_BYE_OUT: one row per Europa League club that
    moves (competition, country, code, old_label, new_label, club,
    coefficient)."""
    cup_winner_by_league = cup_winner_by_league or {}
    access_list = apply_permutations(active=["russia_suspension"])
    _apply_movements_locally(access_list, ucl_bye_movements)
    _apply_movements_locally(access_list, uel_bye_movements)
    for (comp, country, code), new_label in _UEL_FIXED_PROMOTIONS.items():
        for e in access_list.get(comp, []):
            if e["country"] == country and e["code"] == code:
                e["label"] = new_label

    pool = []
    for e in access_list["Europa League"]:
        if e["label"] not in _EL_QUALIFYING_ORDER or e["country"] == "Russia":
            continue
        if e["code"] == "CW":
            club = cup_winner_by_league.get(e["league"] or "", "")
        else:
            standings = standings_by_league.get(e["league"] or "")
            if not standings:
                continue
            pos = _POSITION_OF_CODE.get(e["code"])
            if pos is None or pos > len(standings):
                continue
            club = standings[pos - 1].get("strTeam", "")
        if not club:
            continue
        try:
            coeff = get_coeff_2027(club, e["country"])
        except Exception as exc:
            print(f"  coefficient lookup failed for {club} ({e['country']}): {exc}", file=sys.stderr)
            continue
        pool.append({
            "country": e["country"], "code": e["code"], "route": e["route"],
            "label": e["label"], "club": club, "coefficient": coeff,
        })

    movements = []
    if pool:
        pool.sort(key=lambda c: -(c["coefficient"] or 0))
        top = pool[0]
        movements.append({
            "competition": "Europa League", "country": top["country"], "code": top["code"],
            "old_label": top["label"], "new_label": "EL-LS",
            "club": top["club"], "coefficient": top["coefficient"],
        })
        idx = _EL_QUALIFYING_ORDER.index(top["label"])
        if idx > 0:
            lower_label = _EL_QUALIFYING_ORDER[idx - 1]
            remaining = [c for c in pool if c["label"] == lower_label and c["country"] != top["country"]]
            remaining.sort(key=lambda c: -(c["coefficient"] or 0))
            if remaining:
                c = remaining[0]
                movements.append({
                    "competition": "Europa League", "country": c["country"], "code": c["code"],
                    "old_label": lower_label, "new_label": top["label"],
                    "club": c["club"], "coefficient": c["coefficient"],
                })

    pd.DataFrame(movements).to_csv(UECL_TITLEHOLDER_BYE_OUT, index=False)
    print(f"Wrote {len(movements)} Conference League Titleholder bye (EL side) movements to {UECL_TITLEHOLDER_BYE_OUT}")
    for m in movements:
        print(f"  {m['country']} ({m['club']}, coeff {m['coefficient']:.3f}): {m['old_label']} -> {m['new_label']}")
    return movements


def main() -> None:
    if not _API_KEY:
        print("API_FOOTBALL_KEY not set -- nothing to compute.", file=sys.stderr)
        sys.exit(1)

    standings_rows = []
    probs_rows = []
    cup_rows = []
    standings_by_league: dict[str, list[dict]] = {}

    for league_name in _all_tracked_leagues():
        cfg = LEAGUES.get(league_name)
        if not cfg:
            continue
        try:
            standings, probs = predicted_standings_and_probs(cfg["id"], cfg["af_season"], league_name, _API_KEY)
        except Exception as exc:
            print(f"  {league_name}: FAILED ({exc})", file=sys.stderr)
            continue
        if standings:
            standings_by_league[league_name] = standings
            for row in standings:
                standings_rows.append({
                    "league_name": league_name,
                    "intRank": row.get("intRank"),
                    "strTeam": row.get("strTeam", ""),
                    "strBadge": row.get("strBadge", ""),
                })
        if probs is not None and not probs.empty:
            for team in probs.index:
                for pos in probs.columns:
                    probs_rows.append({
                        "league_name": league_name, "strTeam": team,
                        "position": pos, "probability": float(probs.loc[team, pos]),
                    })
        if cfg.get("cup_id"):
            name, note = predict_cup_winner(league_name, _API_KEY)
            if name:
                cup_rows.append({"league_name": league_name, "team": name, "note": note})

    cup_winner_by_league = {r["league_name"]: r["team"] for r in cup_rows}

    pd.DataFrame(standings_rows).to_csv(STANDINGS_OUT, index=False)
    pd.DataFrame(probs_rows).to_csv(PROBS_OUT, index=False)
    pd.DataFrame(cup_rows).to_csv(CUP_WINNERS_OUT, index=False)
    print(f"Wrote {len(standings_rows)} standings rows across {len(standings_by_league)} leagues to {STANDINGS_OUT}")
    print(f"Wrote {len(probs_rows)} position-probability rows to {PROBS_OUT}")
    print(f"Wrote {len(cup_rows)} predicted cup winners to {CUP_WINNERS_OUT}")

    ucl_bye_claimed: set[str] = set()
    ucl_bye_movements: list[dict] = []
    try:
        ucl_bye_movements = _build_titleholder_bye(standings_by_league)
        ucl_bye_claimed = {m["country"] for m in ucl_bye_movements}
    except Exception as exc:
        # Never let a flaky live coefficient/fixture fetch (a DIFFERENT,
        # unrelated API-Football endpoint from the league standings above)
        # throw away the standings/probs/cup-winner CSVs already written
        # successfully above -- same "report, don't fail the whole daily
        # run" resilience as ratings_sanity_check.py.
        print(f"UCL Titleholder bye cascade FAILED ({exc}) -- standings/probs/cup files above are still valid.", file=sys.stderr)

    uel_bye_movements: list[dict] = []
    try:
        uel_bye_movements = _build_uel_titleholder_bye(standings_by_league, ucl_bye_claimed)
    except Exception as exc:
        print(f"Europa League Titleholder bye cascade FAILED ({exc}) -- other files above are still valid.", file=sys.stderr)

    try:
        _build_uecl_titleholder_bye(standings_by_league, ucl_bye_movements, uel_bye_movements, cup_winner_by_league)
    except Exception as exc:
        print(f"Conference League Titleholder bye cascade FAILED ({exc}) -- other files above are still valid.", file=sys.stderr)


if __name__ == "__main__":
    main()
