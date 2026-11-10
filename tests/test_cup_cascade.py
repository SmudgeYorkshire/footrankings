"""
Tests for cup_cascade._cascade_insert's pass_through behavior -- added
2026-11-10 for Denmark, whose Championship Round 4th place plays a
separate play-off for its OWN UECL - QR2 entitlement, independent of 3rd
place's own direct UECL - QR2 spot. Without pass_through, the shared
"stop at any seeded playoff position" rule (added after real bugs in
Bulgaria 2026-10-19 and Wales 2026-10-20, where a cascade otherwise
double-counted a SINGLE shared slot) incorrectly also blocks Denmark's
case, where the two UECL - QR2 spots are genuinely different allocations.
pass_through is an explicit per-league opt-in (frozenset of positions),
not a global behavior change -- these tests also confirm the default
(empty pass_through) still reproduces the original Bulgaria/Wales-style
stop-dead behavior unchanged.
"""

import cup_cascade as cc

RANKED = ["A", "B", "C", "D", "E", "F"]


def test_without_pass_through_cascade_stops_at_seeded_playoff_position():
    """Bulgaria/Wales-style: a single shared slot. The vacated tier must
    NOT skip past the seeded position to land further down."""
    zones = {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1"}
    overrides = {3: "UECL - QR1"}  # pre-seeded, as resolve_live_overrides does
    claimed = {3}
    placed = cc._cascade_insert(RANKED, zones, overrides, claimed, "UECL - QR1", (1, 2))
    assert placed is False
    assert overrides == {3: "UECL - QR1"}


def test_with_pass_through_cascade_reaches_the_next_open_position():
    """Denmark-style: two genuinely independent slots. The vacated tier
    must skip past the seeded, pass_through-marked position and land on
    the next real candidate."""
    zones = {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1"}
    overrides = {3: "UECL - QR1"}
    claimed = {3}
    placed = cc._cascade_insert(
        RANKED, zones, overrides, claimed, "UECL - QR1", (1, 2),
        pass_through=frozenset({3}),
    )
    assert placed is True
    assert overrides == {3: "UECL - QR1", 4: "UECL - QR1"}


def test_pass_through_position_keeps_its_own_seeded_label_untouched():
    """The pass_through position's own display label (from
    resolve_live_overrides' upfront seeding) is never overwritten by the
    cascade scanning past it."""
    zones = {1: "UCL - QR1", 2: "UECL - QR2", 3: "UECL - QR1"}
    overrides = {3: "UECL - QR1"}
    claimed = {3}
    cc._cascade_insert(
        RANKED, zones, overrides, claimed, "UECL - QR1", (1, 2),
        pass_through=frozenset({3}),
    )
    assert overrides[3] == "UECL - QR1"
