"""
One-off (but re-runnable, e.g. after a future hyperparameter change)
rebuild of club_odds_ratings.py's persistent state -- ratings/club_odds_
implied_ratings.csv and ratings/club_odds_processed_fixtures.csv -- from
scratch, under whatever LEARNING_RATE/L2_SHRINKAGE/EPOCHS/
MIN_BOOKMAKERS_FOR_FULL_WEIGHT values club_odds_ratings.py currently ships
(e.g. the 2026-11-05 club_odds_hyperparameter_sweep.py-validated change).
Changing those constants only affects FUTURE fits; it does nothing to the
ratings already baked into the state file from the OLD values, so a real
hyperparameter change needs this to actually take effect on live ratings.

Does NOT reimplement _fit_persistent's own replay logic (unlike club_odds_
hyperparameter_sweep.py's validation-only _replay_fit, which deliberately
starts every team from a clean raw-Opta seed every candidate and is scoped
to the 21 football-data.co.uk leagues it can score against). This instead
wipes the two state files and calls club_odds_ratings.main() once per
real distinct historical kickoff date, in order -- the actual production
entry point, covering every tracked domestic league/tier AND the European
competitions' own cross-league resolution exactly as main() already
handles it, with zero separate reimplementation.

Critically, this reproduces the REAL daily batch granularity (a handful of
newly-eligible fixtures per league per call), not one giant batch. A
single wipe-and-call-main-once-for-today pass was explicitly rejected:
calling main() fresh against an empty ledger would hand EVERY historical
fixture to _fit_persistent in ONE call per league -- exactly the failure
mode club_odds_ratings.py's own module docstring documents and rejected
(a ~5,000-observation joint batch scored 0.6635 against the held-out
benchmark, far worse than daily-granularity replay, because _fit_
persistent's model snapshot is only recomputed once per EPOCH, letting
errors compound against a stale snapshot before the model catches up).
Calling main() once per distinct real kickoff date instead keeps every
individual _fit_persistent call at the same small batch size the daily
cron itself produces.

Stops at TODAY (inclusive of every kickoff strictly before today) --
exactly where the real, currently-committed ledger already stands.
Fixtures captured in advance for a kickoff that, in reality, hasn't
happened yet are deliberately left pending, same as the real pipeline
would leave them.

Does NOT touch the separate outright-odds nudge (club_outright_odds_
calibration.py) -- that's a distinct correction layered on top of this
match-level fit, not reproducible by replaying match-level observations,
and must be re-applied (once, against the fresh base this script
produces) in a separate run after this one.

Usage: py club_odds_rebuild_history.py [--as-of YYYY-MM-DD]
"""

import argparse
import sys
from datetime import date, timedelta

# Windows' console defaults to cp1252, which can't encode every character a
# club name might contain -- club_outright_odds_calibration.py already hit
# and guarded against this exact crash (a Turkish club name, mid-run); same
# guard here, since main()'s own per-call summary print walks every
# touched team's name across all ~106 tracked leagues/competitions, not
# just the handful club_outright_odds_calibration.py prints.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import club_odds_ratings as cor


def rebuild(as_of_date: str) -> None:
    as_of = date.fromisoformat(as_of_date)

    all_obs = cor._load_all_tracked_observations()
    dates = sorted({
        o["commence_time"][:10] for o in all_obs
        if o.get("commence_time") and date.fromisoformat(o["commence_time"][:10]) < as_of
    })
    if not dates:
        print("No historical observations found before", as_of_date)
        return

    print(f"Wiping state: {cor.RATINGS_OUT_PATH}, {cor.LEDGER_PATH}")
    if cor.RATINGS_OUT_PATH.exists():
        cor.RATINGS_OUT_PATH.unlink()
    if cor.LEDGER_PATH.exists():
        cor.LEDGER_PATH.unlink()

    print(f"Replaying {len(dates)} distinct kickoff dates from {dates[0]} to {dates[-1]} "
          f"(as_of={as_of_date}), one main() call per date...")
    for i, d in enumerate(dates, 1):
        call_date = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
        print(f"[{i}/{len(dates)}] {d} (main(--date {call_date}))")
        cor.main(call_date)

    print("\nRebuild complete.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args()
    rebuild(args.as_of)


if __name__ == "__main__":
    main()
