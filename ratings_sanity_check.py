"""
Standing data-integrity check for the persistent Odds-Implied rating
pipeline (ratings/club_odds_implied_ratings.csv, ratings/club_odds_
processed_fixtures.csv, club_power_rankings_1000.csv).

Built 2026-11-05 after two real, silent bugs were found and fixed this
same session -- both only caught because a human happened to notice an
implausible number on screen:

  - A ledger-duplication bug (the daily automated workflow and a manual
    trigger both started from the same stale ledger, so the same real
    fixture's odds got fit into a club's rating up to 3x over) inflated
    n_updates for 639 clubs, 441 of them wrongly shown at full confidence.
  - An orphaned-state-key bug (club_outright_odds_calibration.py keying
    a nudge by a competition field's own display name instead of the
    ratings CSV's canonical "team" column) made 34 clubs' outright-odds
    corrections silently dead on arrival.

Four checks below, each a precise, near-zero-false-positive invariant
derived directly from one of those two bugs (not a fuzzy "rating moved
too much" heuristic, which would need separate tuning and risk noisy
false alarms). Report-only, by deliberate choice -- see run_checks()'s
own docstring for why this never blocks a commit.

Usage: py ratings_sanity_check.py
"""

import csv
from pathlib import Path

import pandas as pd

from config import LEAGUES, LEAGUES_TIER2, EUROPEAN_COMPETITIONS
import club_odds_ratings as cor

POWER_RANKINGS_PATH = "club_power_rankings_1000.csv"
_MAX_LISTED = 20  # cap how many individual issues of one kind get printed


def _check_ledger_duplicates() -> list[str]:
    """Should be structurally impossible now (club_odds_ratings._append_
    ledger's own write-time dedup guard, added this session) -- any hit
    here means that guard itself has a problem, the single highest-
    confidence signal this whole script can raise."""
    if not cor.LEDGER_PATH.exists():
        return []
    with open(cor.LEDGER_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    counts: dict[tuple, int] = {}
    for r in rows:
        key = (r["league"], r["home_team"], r["away_team"], r["commence_time"])
        counts[key] = counts.get(key, 0) + 1
    dupes = sorted(((k, c) for k, c in counts.items() if c > 1), key=lambda kc: -kc[1])

    issues = [
        f"LEDGER DUPLICATE: {key[1]} vs {key[2]} ({key[0]}, {key[3]}) appears {count}x "
        f"in {cor.LEDGER_PATH}"
        for key, count in dupes[:_MAX_LISTED]
    ]
    if len(dupes) > _MAX_LISTED:
        issues.append(f"... and {len(dupes) - _MAX_LISTED} more duplicate ledger keys")
    return issues


def _true_n_updates_by_key() -> dict[tuple[str, str], int]:
    """{(league_id, team): count of distinct real-world fixtures in the
    ledger that should have contributed to that team's n_updates} --
    same resolution this session's one-time correction used: domestic
    via LEAGUES/LEAGUES_TIER2's own id, European via club_odds_ratings.
    _load_tracked_ratings_with_source()'s _home_league_id column (the
    exact lookup main() itself builds for European observations)."""
    if not cor.LEDGER_PATH.exists():
        return {}
    with open(cor.LEDGER_PATH, encoding="utf-8") as f:
        distinct_keys = {
            (r["league"], r["home_team"], r["away_team"], r["commence_time"])
            for r in csv.DictReader(f)
        }

    combined = cor._load_tracked_ratings_with_source()
    home_league_lookup = dict(zip(combined["team"], combined["_home_league_id"]))

    true_counts: dict[tuple[str, str], int] = {}
    for league, home, away, _commence_time in distinct_keys:
        if league in EUROPEAN_COMPETITIONS:
            for t in (home, away):
                lid = home_league_lookup.get(t)
                if lid:
                    true_counts[(lid, t)] = true_counts.get((lid, t), 0) + 1
        else:
            cfg = LEAGUES.get(league) or LEAGUES_TIER2.get(league)
            if not cfg:
                continue
            lid = str(cfg.get("tsdb_id", cfg["id"]))
            true_counts[(lid, home)] = true_counts.get((lid, home), 0) + 1
            true_counts[(lid, away)] = true_counts.get((lid, away), 0) + 1
    return true_counts


def _check_n_updates_accuracy() -> list[str]:
    """The exact check that would have caught the real ledger-duplication
    bug directly. Separately calls out the specific, most-damaging
    symptom -- a club wrongly shown at full confidence (n_updates >=
    N_FULL_CONFIDENCE) when the ledger only truly supports fewer than
    that -- since that's the case that silently changes a live
    prediction's blend, not just a cosmetic evidence-count number."""
    state = cor._load_state()
    true_counts = _true_n_updates_by_key()

    tier_flips = []
    other_mismatches = []
    for key, entry in state.items():
        true_n = true_counts.get(key, 0)
        if entry["n_updates"] == true_n:
            continue
        if entry["n_updates"] >= cor.N_FULL_CONFIDENCE and true_n < cor.N_FULL_CONFIDENCE:
            tier_flips.append((key, entry["n_updates"], true_n))
        else:
            other_mismatches.append((key, entry["n_updates"], true_n))
    tier_flips.sort(key=lambda item: -(item[1] - item[2]))

    issues = [
        f"CONFIDENCE-TIER FLIP: {team} ({lid}) shows n_updates={cur} (treated as full "
        f"confidence) but the ledger only supports {true_n} distinct match(es) "
        f"(N_FULL_CONFIDENCE={cor.N_FULL_CONFIDENCE})"
        for (lid, team), cur, true_n in tier_flips[:_MAX_LISTED]
    ]
    if len(tier_flips) > _MAX_LISTED:
        issues.append(f"... and {len(tier_flips) - _MAX_LISTED} more confidence-tier-flipped clubs")
    if other_mismatches:
        issues.append(
            f"{len(other_mismatches)} other club(s) have an n_updates value that doesn't "
            f"match the ledger's true distinct-fixture count (doesn't change their confidence tier)"
        )
    return issues


def _check_orphaned_keys() -> list[str]:
    """Flags any (league_id, team) in the persistent state whose team
    doesn't match the "team" or "alias" column of that league's own
    ratings/{id}.csv -- the exact signature of the field-name-vs-
    canonical-name bug club_outright_odds_calibration.py had. Skips
    "EURO:{comp}" fallback keys entirely -- a deliberate, already-known
    bucket for a club whose league couldn't be resolved at all, not an
    orphan in this bug's sense."""
    all_cfgs = {**LEAGUES, **LEAGUES_TIER2}
    id_to_cfg = {str(cfg.get("tsdb_id", cfg["id"])): cfg for cfg in all_cfgs.values()}
    roster_cache: dict[str, set[str] | None] = {}

    def _roster_for(lid: str) -> set[str] | None:
        if lid not in roster_cache:
            cfg = id_to_cfg.get(lid)
            csv_path = Path("ratings") / f"{lid}.csv"
            if cfg is None or not csv_path.exists():
                roster_cache[lid] = None
            else:
                df = pd.read_csv(csv_path, dtype=str)
                names = set(df.get("team", pd.Series(dtype=str)).dropna())
                if "alias" in df.columns:
                    names |= set(df["alias"].dropna())
                roster_cache[lid] = names
        return roster_cache[lid]

    orphans = []
    for (lid, team), _entry in cor._load_state().items():
        if lid.startswith("EURO:"):
            continue
        names = _roster_for(lid)
        if names is None:
            continue  # unknown league_id -- can't verify either way, not a false orphan claim
        if team not in names:
            orphans.append((lid, team))

    issues = [
        f"ORPHANED STATE KEY: ({lid}, {team!r}) doesn't match any 'team'/'alias' in "
        f"ratings/{lid}.csv -- its own rating/nudge may never be read by a live prediction"
        for lid, team in orphans[:_MAX_LISTED]
    ]
    if len(orphans) > _MAX_LISTED:
        issues.append(f"... and {len(orphans) - _MAX_LISTED} more orphaned state keys")
    return issues


def _check_display_freshness() -> list[str]:
    """Backstop behind this session's two auto-rebuild fixes (the daily
    workflow step, and club_outright_odds_calibration.py's own call at
    the end of main()) -- in case a future script writes to the
    persistent state without triggering either. Scoped to LEAGUES (top-
    flight) only: club_power_rankings_1000.csv's own tracked_league-label
    matching (build_club_power_rankings.py) is only built against that
    set, not LEAGUES_TIER2 or European-only entries."""
    path = Path(POWER_RANKINGS_PATH)
    if not path.exists():
        return [f"{POWER_RANKINGS_PATH} does not exist -- run build_club_power_rankings.py"]

    df = pd.read_csv(path)
    label_to_league_id = {
        f"{cfg['flag']} {name}": str(cfg.get("tsdb_id", cfg["id"])) for name, cfg in LEAGUES.items()
    }
    df["_league_id"] = df["tracked_league"].map(label_to_league_id)
    state = cor._load_state()

    stale = []
    for _, row in df.dropna(subset=["_league_id", "odds_implied_rating"]).iterrows():
        key = (row["_league_id"], row["team"])
        entry = state.get(key)
        if entry is None:
            continue
        if abs(float(row["odds_implied_rating"]) - entry["rating"]) > 0.02 or int(row["odds_n_updates"]) != entry["n_updates"]:
            stale.append((key, row["odds_implied_rating"], entry["rating"], row["odds_n_updates"], entry["n_updates"]))

    issues = [
        f"STALE DISPLAY: {team} ({lid}) shows odds_implied_rating={csv_r}/n={csv_n} in "
        f"{POWER_RANKINGS_PATH} but the live state has {live_r}/n={live_n} -- rerun "
        f"build_club_power_rankings.py"
        for (lid, team), csv_r, live_r, csv_n, live_n in stale[:_MAX_LISTED]
    ]
    if len(stale) > _MAX_LISTED:
        issues.append(f"... and {len(stale) - _MAX_LISTED} more stale display rows")
    return issues


def run_checks() -> list[str]:
    """Report-only by deliberate choice (same convention daily_snapshot.
    py's own swing-detector already uses) -- a false positive here can
    never block a legitimate day's ratings update from publishing. Every
    check is a precise, near-zero-false-positive invariant derived
    directly from a real bug found this session, not a tunable
    heuristic, so a genuine hit is worth trusting; still, blocking a
    commit on a bug in THIS script would be worse than the problem it's
    meant to catch."""
    issues: list[str] = []
    issues += _check_ledger_duplicates()
    issues += _check_n_updates_accuracy()
    issues += _check_orphaned_keys()
    issues += _check_display_freshness()
    return issues


def main() -> None:
    issues = run_checks()
    if not issues:
        print(
            "Ratings pipeline sanity check: all clear -- no ledger duplicates, "
            "n_updates matches the ledger for every club, no orphaned state keys, "
            "club_power_rankings_1000.csv is fresh."
        )
        return
    print(
        f"Ratings pipeline sanity check: {len(issues)} issue(s) found. "
        f"Report-only -- none of these block today's commit, but worth a look:"
    )
    for issue in issues:
        print(f"  - {issue}")


if __name__ == "__main__":
    main()
