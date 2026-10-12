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

Per explicit instruction (2026-10-12): start with ACTIVE_PERMUTATIONS
empty (the pure default, Russia included normally) until the resulting
Status column has been checked across every league; only then re-enable
"russia_suspension" (and any others that should be live) below.
"""

import copy

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
                e["note"] = f"Promoted {old_label} -> {new_label}: Russia ban vacates a slot above it"


# ---------------------------------------------------------------------------
# Permutation: predicted European Performance Spot recipients. Awarded
# AFTER 2026/27 ends to whichever 2 associations have the best aggregate
# CLUB coefficient that season -- not fixed in the access-list circular
# itself, so this is a live, speculative best guess. Manually curated for
# now (see entrants_2027_28.py's own note on titleholder confirmations --
# same "keep it manual until it's worth automating" approach); the
# Coefficients page's own "Race for an extra Champions League spot" and
# "Predicted Race..." tables (also surfaced in european_2027_28.py's
# Permutation Info tab) are the live data to check before editing this.
# ---------------------------------------------------------------------------
_EPS_PREDICTED_RECIPIENTS: list[tuple[str, str]] = [
    ("England", "English Premier League"),
    ("Germany", "German Bundesliga"),
]


def _apply_eps_prediction(access_list: dict) -> None:
    for country, league in _EPS_PREDICTED_RECIPIENTS:
        access_list["Champions League"].append({
            "country": country, "league": league, "code": "N5", "route": "League 5th",
            "label": "CL-LS", "path": "Direct", "round": "League Phase (direct)",
            "note": "Predicted EPS recipient, not yet confirmed by UEFA -- this slot only exists if that holds",
        })


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
    "eps_prediction": {
        "name": "Predicted European Performance Spot recipients",
        "description": (
            "England and Germany are predicted (not yet confirmed by UEFA) to "
            "receive 2027/28's 2 European Performance Spot bonus places, awarded "
            "after 2026/27 ends to whichever 2 associations have the best "
            "aggregate club coefficient that season. Modelled as a 5th direct "
            "League Phase slot for each."
        ),
        "apply": _apply_eps_prediction,
    },
}

# Per explicit instruction (2026-10-12): start empty (the pure default
# access list, Russia included normally) until the Status column has been
# checked across every league -- then re-enable "russia_suspension" here
# (and "eps_prediction", if still accurate) once confirmed.
ACTIVE_PERMUTATIONS: list[str] = []


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
