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

Usage: py build_european_2027_28_predictions.py
"""

import os
import sys

import pandas as pd

from config import LEAGUES
from entrants_2027_28 import ACCESS_LIST_2027_28 as DEFAULT_ACCESS_LIST_2027_28
from access_list_permutations_2027_28 import apply_permutations
from club_coefficients_2027 import get_coeff_2027
from european_predictions_core import predicted_standings_and_probs, predict_cup_winner

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")

STANDINGS_OUT = "european_2027_28_predicted_standings.csv"
PROBS_OUT = "european_2027_28_position_probs.csv"
CUP_WINNERS_OUT = "european_2027_28_predicted_cup_winners.csv"
TITLEHOLDER_BYE_OUT = "european_2027_28_ucl_titleholder_bye.csv"

# One CH entry per round currently sits in each of these Champions-Path
# labels (see _build_titleholder_bye) -- QR1 moves as a PAIR since UEFA's
# qualifying rounds are two-legged ties, so two QR1 clubs always advance
# together to fill one QR2 vacancy.
_CASCADE_TOP_N = {"CL-PO": 1, "CL-Q2": 1, "CL-Q1": 2}


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
    country, code, old_label, new_label, club, coefficient)."""
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

    pd.DataFrame(standings_rows).to_csv(STANDINGS_OUT, index=False)
    pd.DataFrame(probs_rows).to_csv(PROBS_OUT, index=False)
    pd.DataFrame(cup_rows).to_csv(CUP_WINNERS_OUT, index=False)
    print(f"Wrote {len(standings_rows)} standings rows across {len(standings_by_league)} leagues to {STANDINGS_OUT}")
    print(f"Wrote {len(probs_rows)} position-probability rows to {PROBS_OUT}")
    print(f"Wrote {len(cup_rows)} predicted cup winners to {CUP_WINNERS_OUT}")

    try:
        _build_titleholder_bye(standings_by_league)
    except Exception as exc:
        # Never let a flaky live coefficient/fixture fetch (a DIFFERENT,
        # unrelated API-Football endpoint from the league standings above)
        # throw away the standings/probs/cup-winner CSVs already written
        # successfully above -- same "report, don't fail the whole daily
        # run" resilience as ratings_sanity_check.py.
        print(f"UCL Titleholder bye cascade FAILED ({exc}) -- standings/probs/cup files above are still valid.", file=sys.stderr)


if __name__ == "__main__":
    main()
