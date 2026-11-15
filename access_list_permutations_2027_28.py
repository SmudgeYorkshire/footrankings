"""
2027/28 UEFA access-list PERMUTATIONS.

entrants_2027_28.ACCESS_LIST_2027_28 is the pure DEFAULT access list --
every country's nominal 2027/28 entry exactly as UEFA's own circular
(54/2026, enclosure 2) and kassiesa.net's mirrored PDF
(https://kassiesa.net/uefa/files/2027-28-uefa-access-list.pdf) show it,
Russia included with its own undisturbed nominal slots.

A PERMUTATION is a real-world departure from that default -- Russia's
ongoing UEFA suspension redistributing its slots, a predicted European
Performance Spot recipient, a confirmed titleholder-replacement cascade,
etc. -- tracked here as a discrete, independently toggleable transform,
rather than hand-edited into the default list. apply_permutations()
always starts from a fresh deep copy of ACCESS_LIST_2027_28 and layers
each ACTIVE permutation's own transformation on top, in order, so the
default is always trivially recoverable: a permutation turning off, or
turning out not to apply after all, is just removing its id from
ACTIVE_PERMUTATIONS -- never a hand-revert of the base data.

Every downstream consumer of the access list (european_2027_28.py,
build_league_status.py -> league_status.py, cup_cascade.py) should go
through this module's resolvers (apply_permutations /
european_status_zones / cup_winner_status), not entrants_2027_28's own,
so turning a permutation on/off here automatically propagates everywhere
the access list is used.

Per explicit instruction (2026-10-12): started with ACTIVE_PERMUTATIONS
empty (the pure default, Russia included normally) until the resulting
Status column had been checked across every league. That check passed
clean 2026-11-14 (only the 5 already-documented contested-play-off
exceptions in league_status.py differed, none of them new) -- per
explicit instruction the same day, "russia_suspension" is now ACTIVE
below.
"""

import copy
import csv
import os

from entrants_2027_28 import ACCESS_LIST_2027_28, label_to_status, _POSITION_CODE

_ROUND_NAME = {
    "Q1": "First qualifying round", "Q2": "Second qualifying round",
    "Q3": "Third qualifying round", "PO": "Play-off round", "LS": "League Phase (direct)",
}


def _round_for_label(label: str) -> str:
    base = label[:-2] if label.endswith("nc") else label
    _, rnd = base.split("-", 1)
    return _ROUND_NAME[rnd]


# ---------------------------------------------------------------------------
# Permutation: Russia's ongoing UEFA suspension (Executive Committee,
# 28 February 2022, still in force). Real-world effect: the slot
# immediately above each of Russia's own cascade points is promoted up one
# round to absorb the vacancy Russia can't fill. Russia's own entries stay
# in the list (so its nominal entitlement is still visible) but get a note
# explaining no Russian club will actually occupy them.
# ---------------------------------------------------------------------------
_RUSSIA_PROMOTIONS: dict[tuple[str, str, str], str] = {
    ("Champions League", "Ukraine", "CH"): "CL-Q2",
    ("Europa League", "Switzerland", "CW"): "EL-Q2",
    ("Conference League", "Latvia", "CW"): "CO-Q2",
    ("Conference League", "Faroe Isl.", "CW"): "CO-Q2",
    ("Conference League", "Malta", "CW"): "CO-Q2",
    ("Conference League", "Estonia", "CW"): "CO-Q2",
    ("Conference League", "Albania", "CW"): "CO-Q2",
    ("Conference League", "Liechtenstein", "CW"): "CO-Q2",
}
_RUSSIA_NOTE = (
    "Suspended from UEFA competitions until further notice (Executive "
    "Committee, 28 Feb 2022) -- slot redistributed, no Russian club will "
    "actually occupy it"
)


def _apply_russia_suspension(access_list: dict) -> None:
    for comp, entries in access_list.items():
        for e in entries:
            if e["country"] == "Russia":
                e["note"] = _RUSSIA_NOTE
                continue
            new_label = _RUSSIA_PROMOTIONS.get((comp, e["country"], e["code"]))
            if new_label:
                old_label = e["label"]
                e["label"] = new_label
                e["round"] = _round_for_label(new_label)
                e["note"] = f"Promoted {old_label} -> {new_label}"


# ---------------------------------------------------------------------------
# Permutation: UCL Titleholder bye. Real-world effect (confirmed by the
# user from their own primary source, 2026-11-15): when the 2026/27 UCL
# titleholder doesn't requalify for 2027/28 through its own domestic
# route, UEFA fills its guaranteed League Phase slot from the Champions
# Path club with the single highest UEFA club coefficient. Unlike
# russia_suspension (a fixed, hardcoded set of moves -- Russia's
# suspension never changes which slots it affects), WHICH club benefits
# at each step is resolved dynamically from live data (each country's own
# live predicted champion + its live UEFA coefficient), the same way
# every other occupant on this site is resolved rather than hardcoded.
#
# That live resolution needs a full live standings simulation per country
# (exactly the same expensive per-country computation
# european_2027_28.py's own Projected Entries tab needs -- see
# european_predictions_core.py's own docstring for why it's precomputed
# once a day rather than live on each page load), so it can't run inside
# this module's own apply_permutations() at european_2027_28.py's import
# time the way russia_suspension's static dict lookup can. Instead,
# build_european_2027_28_predictions.py (the same daily job that
# precomputes european_2027_28.py's standings) resolves this cascade once
# a day and writes its result to _TITLEHOLDER_BYE_CSV; this module just
# reads that small, already-resolved file back in -- same
# "precompute once, read fast" split as every other live number on this
# site that's too expensive to recompute per request.
#
# A SEPARATE confirmed consequence (2 Conference League QR2 Champions
# Path clubs get a bye to QR3 Champions Path, a structural effect of the
# shrunken CL-Q1 Champions Path pool once 2 of its clubs move up to
# CL-Q2) is NOT applied as an access-list mutation here -- which 2
# specific clubs get it depends on the real UEFA draw, not anything this
# site's live data can resolve, so it's recorded only as a description
# note below for the Permutation Info tab, never as a club assignment.
# ---------------------------------------------------------------------------
_TITLEHOLDER_BYE_CSV = "european_2027_28_ucl_titleholder_bye.csv"


def _load_titleholder_bye_movements() -> dict[tuple[str, str, str], dict]:
    """{(competition, country, code): {new_label, club, coefficient}} from
    build_european_2027_28_predictions.py's own daily output. Returns {}
    (a harmless no-op -- the permutation just doesn't move anything yet)
    if that file doesn't exist, same bootstrapping-before-first-daily-run
    tolerance every other precomputed page on this site already has."""
    if not os.path.exists(_TITLEHOLDER_BYE_CSV):
        return {}
    movements: dict[tuple[str, str, str], dict] = {}
    with open(_TITLEHOLDER_BYE_CSV, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["competition"], row["country"], row["code"])
            movements[key] = {
                "new_label": row["new_label"], "club": row["club"],
                "coefficient": float(row["coefficient"]),
            }
    return movements


_TITLEHOLDER_BYE_MOVEMENTS = _load_titleholder_bye_movements()


def _apply_ucl_titleholder_bye(access_list: dict) -> None:
    for comp, entries in access_list.items():
        for e in entries:
            move = _TITLEHOLDER_BYE_MOVEMENTS.get((comp, e["country"], e["code"]))
            if not move:
                continue
            old_label = e["label"]
            e["label"] = move["new_label"]
            e["round"] = _round_for_label(move["new_label"])
            e["note"] = (
                f"UCL Titleholder bye: highest Champions Path coefficient in this round "
                f"({move['club']}, {move['coefficient']:.3f}) -- promoted {old_label} -> {move['new_label']}"
            )


def ucl_titleholder_bye_movements() -> list[dict]:
    """One row per real-world slot movement ucl_titleholder_bye causes --
    competition, country, code, route, old/new label, the resolved club,
    and its coefficient -- read straight off the untouched default list
    plus the daily-resolved movements file. Used by european_2027_28.py's
    Permutation Info tab, same contract as russia_suspension_movements()."""
    rows = []
    for (comp, country, code), move in _TITLEHOLDER_BYE_MOVEMENTS.items():
        entry = next(
            (e for e in ACCESS_LIST_2027_28[comp] if e["country"] == country and e["code"] == code), None,
        )
        if entry is None:
            continue
        rows.append({
            "competition": comp, "country": country, "code": code, "route": entry["route"],
            "old_label": entry["label"], "new_label": move["new_label"],
            "club": move["club"], "coefficient": move["coefficient"],
        })
    return rows


# ---------------------------------------------------------------------------
# Permutation: Europa League Titleholder bye. Confirmed by the user from
# their own primary source, 2026-11-15, as a SEPARATE real-world event
# from ucl_titleholder_bye above (a different titleholder -- the 2026/27
# Europa League champion -- not requalifying, not the Champions League
# one). Two independent parts:
#
# 1. A dynamic Champions League cascade, drawing from a WIDER pool than
#    ucl_titleholder_bye's own: the single highest-coefficient club
#    across EVERY Champions League qualifying entry, Champions Path AND
#    League Path alike (confirmed live: Portugal's League Path N3 entry,
#    Sporting CP, outranks every Champions Path entry on live
#    coefficients -- a real club this site's own model can beat the
#    user's own illustrative example with, since this is resolved live
#    each day, not hardcoded). Promotes one level toward the League
#    Phase within League Path's own chain (QR2nc -> QR3nc -> LS); a club
#    reaching CL-Q3nc backfills from the top-2 REMAINING League Path
#    CL-Q2nc entries (two-legged, same "pair" convention as
#    ucl_titleholder_bye's own QR1 step). Resolved daily by
#    build_european_2027_28_predictions.py's _build_uel_titleholder_bye
#    (same "precompute once, read fast" split as ucl_titleholder_bye --
#    see that permutation's own comment block above for why), excluding
#    whichever countries ucl_titleholder_bye already claimed that same
#    run.
# 2. Four FIXED (non-coefficient) Europa League promotions -- Austria,
#    Scotland, Sweden and Croatia's cup-winner entries start from UEL-Q2
#    instead of UEL-Q1. Unlike part 1, this never changes which countries
#    it affects, so it's a static dict, exactly like
#    _RUSSIA_PROMOTIONS -- no live data needed.
#
# A SEPARATE, already-automatic consequence of part 2 (fewer Europa
# League QR1 losers cascading down to Conference League QR2, more QR2
# losers cascading to QR3, since 4 clubs no longer play EL-Q1 but do
# enlarge the EL-Q2 pool instead) needs NO special handling anywhere --
# european_2027_28.py's own _simulate_full_bracket already re-derives
# that cascade purely from each entry's (now-changed) label, exactly the
# same way russia_suspension's own promotions already do.
# ---------------------------------------------------------------------------
_UEL_TITLEHOLDER_BYE_CSV = "european_2027_28_uel_titleholder_bye.csv"

_UEL_FIXED_PROMOTIONS: dict[tuple[str, str, str], str] = {
    ("Europa League", "Austria", "CW"): "EL-Q2",
    ("Europa League", "Scotland", "CW"): "EL-Q2",
    ("Europa League", "Sweden", "CW"): "EL-Q2",
    ("Europa League", "Croatia", "CW"): "EL-Q2",
}


def _load_uel_titleholder_bye_movements() -> dict[tuple[str, str, str], dict]:
    """{(competition, country, code): {new_label, club, coefficient}} --
    the dynamic Champions League side only (part 1 above) -- from
    build_european_2027_28_predictions.py's own daily output. Returns {}
    if that file doesn't exist yet, same bootstrapping tolerance as
    _load_titleholder_bye_movements."""
    if not os.path.exists(_UEL_TITLEHOLDER_BYE_CSV):
        return {}
    movements: dict[tuple[str, str, str], dict] = {}
    with open(_UEL_TITLEHOLDER_BYE_CSV, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["competition"], row["country"], row["code"])
            movements[key] = {
                "new_label": row["new_label"], "club": row["club"],
                "coefficient": float(row["coefficient"]),
            }
    return movements


_UEL_TITLEHOLDER_BYE_MOVEMENTS = _load_uel_titleholder_bye_movements()


def _apply_uel_titleholder_bye(access_list: dict) -> None:
    for comp, entries in access_list.items():
        for e in entries:
            move = _UEL_TITLEHOLDER_BYE_MOVEMENTS.get((comp, e["country"], e["code"]))
            if move:
                old_label = e["label"]
                e["label"] = move["new_label"]
                e["round"] = _round_for_label(move["new_label"])
                e["note"] = (
                    f"Europa League Titleholder bye: highest Champions League qualifying "
                    f"coefficient ({move['club']}, {move['coefficient']:.3f}) -- "
                    f"promoted {old_label} -> {move['new_label']}"
                )
                continue
            new_label = _UEL_FIXED_PROMOTIONS.get((comp, e["country"], e["code"]))
            if new_label:
                old_label = e["label"]
                e["label"] = new_label
                e["round"] = _round_for_label(new_label)
                e["note"] = f"Europa League Titleholder bye: promoted {old_label} -> {new_label}"


def uel_titleholder_bye_movements() -> list[dict]:
    """One row per real-world slot movement uel_titleholder_bye causes --
    both the dynamic Champions League side and the 4 fixed Europa League
    promotions -- competition, country, code, route, old/new label, and
    (for the dynamic rows only) the resolved club + coefficient. Used by
    european_2027_28.py's Permutation Info tab, same contract as
    russia_suspension_movements()/ucl_titleholder_bye_movements()."""
    rows = []
    for (comp, country, code), move in _UEL_TITLEHOLDER_BYE_MOVEMENTS.items():
        entry = next(
            (e for e in ACCESS_LIST_2027_28[comp] if e["country"] == country and e["code"] == code), None,
        )
        if entry is None:
            continue
        rows.append({
            "competition": comp, "country": country, "code": code, "route": entry["route"],
            "old_label": entry["label"], "new_label": move["new_label"],
            "club": move["club"], "coefficient": move["coefficient"],
        })
    for (comp, country, code), new_label in _UEL_FIXED_PROMOTIONS.items():
        entry = next(
            (e for e in ACCESS_LIST_2027_28[comp] if e["country"] == country and e["code"] == code), None,
        )
        if entry is None:
            continue
        rows.append({
            "competition": comp, "country": country, "code": code, "route": entry["route"],
            "old_label": entry["label"], "new_label": new_label,
            "club": None, "coefficient": None,
        })
    return rows


PERMUTATIONS: dict[str, dict] = {
    "russia_suspension": {
        "name": "Russia's UEFA suspension",
        "description": (
            "Russia remains suspended from UEFA competitions (Executive Committee, "
            "28 Feb 2022). Its slots are redistributed: Ukraine's champion CL-Q1 -> "
            "CL-Q2, Switzerland's cup winner EL-Q1 -> EL-Q2, and the cup winners of "
            "Latvia, Faroe Islands, Malta, Estonia, Albania and Liechtenstein "
            "CO-Q1 -> CO-Q2."
        ),
        "apply": _apply_russia_suspension,
    },
    "ucl_titleholder_bye": {
        "name": "UCL Titleholder bye",
        "description": (
            "If the 2026/27 Champions League titleholder doesn't requalify for 2027/28 "
            "through its own domestic route, UEFA fills its guaranteed League Phase slot "
            "from the Champions Path club with the single highest UEFA club coefficient. "
            "Resolved dynamically each day from live predicted champions + live "
            "coefficients (build_european_2027_28_predictions.py), not hardcoded: the "
            "highest-coefficient Champions Path club in the Play-off round moves PO -> "
            "League Phase (direct); the highest-remaining Champions Path club in the "
            "Second qualifying round then fills that vacancy, QR2 -> PO; the top-2 "
            "remaining Champions Path clubs in the First qualifying round (a pair, since "
            "QR1 ties are two-legged) fill the QR2 vacancy, QR1 -> QR2. Separately, this "
            "also creates a bye for 2 Conference League Second qualifying round (Champions "
            "Path) clubs straight to the Third qualifying round -- a structural consequence "
            "of the shrunken CL-Q1 Champions Path pool, not shown as a specific club move "
            "here since which 2 clubs get it depends on the real UEFA draw."
        ),
        "apply": _apply_ucl_titleholder_bye,
    },
    "uel_titleholder_bye": {
        "name": "Europa League Titleholder bye",
        "description": (
            "If the 2026/27 Europa League titleholder doesn't requalify for 2027/28 through "
            "its own domestic route, a SEPARATE event from the Champions League titleholder "
            "above: the single highest-coefficient club across EVERY Champions League "
            "qualifying entry (Champions Path AND League Path alike) is promoted one level "
            "toward the League Phase within its own path's chain -- resolved dynamically "
            "each day the same way as UCL Titleholder bye, excluding whichever club that "
            "permutation already claimed. When the promoted club is League Path's QR3 "
            "entry, the vacancy is backfilled by the top-2 remaining League Path QR2 "
            "entries (a pair, same two-legged convention). Separately, 4 fixed promotions "
            "(not by coefficient): Austria, Scotland, Sweden and Croatia's cup winners "
            "start from Europa League QR2 instead of QR1 -- which automatically shrinks "
            "how many QR1 losers cascade down to Conference League QR2 and grows how many "
            "QR2 losers cascade to QR3, with no extra handling needed."
        ),
        "apply": _apply_uel_titleholder_bye,
    },
}

# "russia_suspension" went live 2026-11-14 (see module docstring) --
# Russia remains suspended from UEFA competitions with no resolution in
# sight, so its slots are redistributed everywhere on the site.
# "ucl_titleholder_bye" went live 2026-11-15, confirmed by the user from
# their own primary source as a fixed UEFA rule -- see that permutation's
# own comment block above for why it's resolved from a daily-precomputed
# file rather than live data, and is a harmless no-op (moves nothing)
# until that file's first real run. "uel_titleholder_bye" went live the
# same day, a separate confirmed rule covering a different titleholder --
# see its own comment block above. Further permutations get added to
# PERMUTATIONS (and here) one at a time, each deliberately confirmed
# before going active -- see this module's own docstring for the full
# process.
ACTIVE_PERMUTATIONS: list[str] = ["russia_suspension", "ucl_titleholder_bye", "uel_titleholder_bye"]


def apply_permutations(active: list[str] | None = None) -> dict:
    """A deep copy of ACCESS_LIST_2027_28 with each active permutation's
    transformation layered on top, in order. The default list itself is
    NEVER mutated -- re-running this (with a different `active` list, or
    None to use the module's current ACTIVE_PERMUTATIONS) always starts
    fresh from the untouched default."""
    ids = ACTIVE_PERMUTATIONS if active is None else active
    access_list = copy.deepcopy(ACCESS_LIST_2027_28)
    for pid in ids:
        perm = PERMUTATIONS.get(pid)
        if perm:
            perm["apply"](access_list)
    return access_list


def _access_by_country(active: list[str] | None = None) -> dict[str, dict[str, str]]:
    """{country: {code: label}} flattened across all three competitions,
    from the permutation-applied list. Not cached (unlike entrants_2027_28's
    own version) since which permutations are active can change at
    runtime and this is cheap -- the access list is small, static data."""
    by_country: dict[str, dict[str, str]] = {}
    for entries in apply_permutations(active).values():
        for e in entries:
            by_country.setdefault(e["country"], {})[e["code"]] = e["label"]
    return by_country


def european_status_zones(country: str, active: list[str] | None = None) -> dict[int, str]:
    """Same contract as entrants_2027_28.european_status_zones, resolved
    against the permutation-applied list instead of the raw default."""
    access = _access_by_country(active).get(country, {})
    return {
        pos: label_to_status(access[code])
        for pos, code in _POSITION_CODE.items() if code in access
    }


def cup_winner_status(country: str, active: list[str] | None = None) -> str | None:
    """Same contract as entrants_2027_28.cup_winner_status, resolved
    against the permutation-applied list instead of the raw default."""
    label = _access_by_country(active).get(country, {}).get("CW")
    return label_to_status(label) if label else None


def russia_suspension_movements() -> list[dict]:
    """One row per real-world slot movement russia_suspension causes (NOT
    Russia's own 4 vacated slots -- see russia_vacated_slots for those):
    competition, country, code, route, and the label it moves from/to,
    read straight off the untouched default list. Used by
    european_2027_28.py's Permutation Info tab to show exactly which
    countries' slots shift, each resolved there against its own live
    predicted occupant (this module has no live-prediction access of its
    own)."""
    rows = []
    for (comp, country, code), new_label in _RUSSIA_PROMOTIONS.items():
        entry = next(e for e in ACCESS_LIST_2027_28[comp] if e["country"] == country and e["code"] == code)
        rows.append({
            "competition": comp, "country": country, "code": code, "route": entry["route"],
            "old_label": entry["label"], "new_label": new_label,
        })
    return rows


def russia_vacated_slots() -> list[dict]:
    """Russia's own 4 entries in the default list -- what russia_suspension
    removes (no club will ever actually occupy these, see _RUSSIA_NOTE)."""
    return [
        {"competition": comp, "code": e["code"], "route": e["route"], "label": e["label"]}
        for comp, entries in ACCESS_LIST_2027_28.items()
        for e in entries if e["country"] == "Russia"
    ]
