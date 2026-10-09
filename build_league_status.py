"""
Regenerates league_status.py's European-spot labels from
entrants_2027_28.ACCESS_LIST_2027_28 -- the single source of truth
connecting this season's Status column to the real 2027/28 UEFA access
list (see league_status.py's own docstring, and the explicit instruction
this connection was built for, 2026-10-09).

Run this after ANY change to ACCESS_LIST_2027_28 (adding/removing/
re-routing a country's slot) to keep league_status.py in sync -- it
won't happen on its own, since league_status.py is a plain static dict
(kept that way deliberately: football_rankings.py reads it in dozens of
places, and a lazily-computed version would be a much bigger, riskier
change for no behavioral benefit over "run this script").

This only touches EUROPEAN-SPOT positions (anything whose label contains
UCL/UEL/UECL). Relegation/promotion positions and split leagues' "regular"
phase group-assignment placeholders ("Championship Group" etc.) are left
completely untouched -- they have nothing to do with the access list and
are hand-kept directly in league_status.py.

Usage: py build_league_status.py
    Prints a diff of what would change (nothing is ever written
    automatically -- paste the new per-league blocks into league_status.py
    by hand, same as any other hand-reviewed data file on this site, and
    rerun the full pytest suite + a couple of live spot-checks before
    treating it as done).
"""

from config import LEAGUES
from league_status import LEAGUE_STATUS
from entrants_2027_28 import european_status_zones

SPOT_KW = ("ucl", "uel", "uecl")


def _is_spot(label: str) -> bool:
    return any(kw in str(label).lower() for kw in SPOT_KW)


def _zone_for(abs_pos: int, n_champ: int | None, n_mid: int) -> tuple[str, int]:
    """Which phase + within-phase position an OVERALL league position falls
    into for a split league (champ = top n_champ, then mid, then relg);
    "regular" directly for a non-split league."""
    if n_champ:
        if abs_pos <= n_champ:
            return "champ", abs_pos
        elif abs_pos <= n_champ + n_mid:
            return "mid", abs_pos - n_champ
        else:
            return "relg", abs_pos - n_champ - n_mid
    return "regular", abs_pos


def computed_spots(league_name: str) -> dict[str, dict[int, str]]:
    """{phase: {position: label}} -- just the European-spot positions for
    one league, derived fresh from the access list."""
    cfg = LEAGUES[league_name]
    n_champ, n_mid = cfg.get("n_champ"), cfg.get("n_mid") or 0
    out: dict[str, dict[int, str]] = {}
    if league_name == "Albanian Superliga":
        return out  # Final Four zone isn't position-derived the same way
    for abs_pos, label in european_status_zones(cfg.get("country")).items():
        phase, rel_pos = _zone_for(abs_pos, n_champ, n_mid)
        out.setdefault(phase, {})[rel_pos] = label
    return out


def current_spots(league_name: str) -> dict[str, dict[int, str]]:
    ls = LEAGUE_STATUS.get(league_name, {})
    return {
        phase: {p: l for p, l in d.items() if _is_spot(l)}
        for phase, d in ls.items() if phase in ("regular", "champ", "mid", "relg")
    }


def main() -> None:
    changed = 0
    for league_name in LEAGUE_STATUS:
        new, old = computed_spots(league_name), current_spots(league_name)
        new_full = {p: new.get(p, {}) for p in set(new) | set(old)}
        old_full = {p: old.get(p, {}) for p in set(new) | set(old)}
        if new_full != old_full:
            changed += 1
            print(f"=== {league_name} ===")
            for phase in ("regular", "champ", "mid", "relg"):
                o, n = old.get(phase, {}), new.get(phase, {})
                if o or n:
                    print(f"  {phase}: OLD={o}")
                    print(f"  {phase}: NEW={n}")
            print()
    if changed:
        print(f"{changed} league(s) differ from ACCESS_LIST_2027_28 -- "
              "update league_status.py by hand, then rerun this script to confirm 0 remain.")
    else:
        print("league_status.py already matches ACCESS_LIST_2027_28 -- nothing to do.")


if __name__ == "__main__":
    main()
