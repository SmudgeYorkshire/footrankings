"""
Matches opta_power_rankings.csv (the full global scrape from
scrape_opta_power_rankings.py) against every tracked league's
ratings/{tsdb_id}.csv, updating opta_rating for every confident match.

The actual club <-> scrape-row matching is build_club_power_rankings.py's
resolve_tracked_leagues() -- the same bipartite, closest-rating-wins
resolver the Club Power Rankings and Opta Rankings pages use, so this
script can no longer disagree with what those pages show. Before this was
unified, this script ran its own simpler, independent-per-club version
(exact/normalized name match, _pick_rating's closest-rating tiebreak) that
had no way to stop two different tracked clubs independently claiming the
same scrape row -- real nickname collisions this site tracks on both
sides (several different clubs legitimately called "Dinamo", "CSKA",
"Radnik", ...) went unmatched every single day because each club's own
lookup refused once it saw the other's candidate too. _normalize,
fuzzy_token_match, load_global_rankings and _pick_rating stay here
unchanged -- other modules (club_rating_calibration.py, nl_odds_
calibration_auto.py, qualifying_projection.py, bootstrap_tier2_ratings.py)
import them directly for unrelated matching tasks.

Writes changes directly to each ratings/{id}.csv (same file the site
already reads). Run with --dry-run to see the match report without
writing anything.
"""

import csv
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

from config import LEAGUES

RANKINGS_PATH = "opta_power_rankings.csv"
RATINGS_DIR = Path("ratings")

_CLUB_SUFFIXES = re.compile(
    r"\b(fc|cf|afc|sc|ac|cd|ud|sd|ca|sk|fk|bk|if|aif|ik|se|nk|hnk|ks|ss|us|as|rc)\b\.?",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = _CLUB_SUFFIXES.sub("", name)
    name = re.sub(r"[^a-z0-9]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def fuzzy_token_match(name: str, candidates) -> str | None:
    """Loosest tier of name matching, shared by club_rating_calibration.py
    and build_club_power_rankings.py: true when `name`'s normalized token
    set is a subset of a candidate's (or vice versa) -- catches spelling
    variants exact/normalized matching misses, e.g. "Inter Milan" ~ alias
    "Inter", "FC Bayern" ~ "Bayern Munich", "Atalanta BC" ~ "Atalanta".
    `candidates` is any iterable of strings; returns the first match or
    None. Only safe to use against a small, known-relevant candidate pool
    (a single league's ~20 teams, not the full 14,200-club global list) --
    single-token names risk over-matching in a large, unrelated pool."""
    name_tokens = set(_normalize(name).split())
    if not name_tokens:
        return None
    for candidate in candidates:
        if not candidate:
            continue
        cand_tokens = set(_normalize(candidate).split())
        if cand_tokens and (cand_tokens <= name_tokens or name_tokens <= cand_tokens):
            return candidate
    return None


def load_global_rankings() -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Returns (exact_lookup, normalized_lookup): name -> every rating it
    maps to in the scraped data (usually one; a handful of common club
    names -- Arsenal, Rangers, Barcelona -- exist in several countries).
    Callers resolve multi-value entries via _pick_rating rather than
    guessing blindly."""
    exact: dict[str, list[float]] = {}
    normalized: dict[str, list[float]] = {}
    with open(RANKINGS_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            team = row["team"].strip()
            rating = float(row["rating"])
            exact.setdefault(team.lower(), []).append(rating)
            normalized.setdefault(_normalize(team), []).append(rating)
    return exact, normalized


def _pick_rating(candidates: list[float], old_rating: float | None) -> tuple[float | None, bool]:
    """Resolve a (possibly multi-club) list of ratings for one name to a
    single value. Returns (rating, was_disambiguated).

    Same club name existing in several countries (Arsenal: 100.0 plus
    three unrelated lower-division clubs at 64.6/62.3/51.8) is common
    enough in world football that dropping every collision would lose
    several of our biggest tracked clubs. Since we already have a prior
    Opta rating for the team, the candidate closest to it is used --
    correct as long as the real update is smaller than the gap to the
    next-nearest homonym, which every case observed in practice satisfies
    by a wide margin (tens of rating points). Refuses to guess when there
    is no prior rating to anchor to, or the two closest candidates are
    within 5 points of each other (genuinely ambiguous)."""
    if len(candidates) == 1:
        return candidates[0], False
    if old_rating is None:
        return None, False
    ranked = sorted(candidates, key=lambda r: abs(r - old_rating))
    if len(ranked) > 1 and abs(ranked[0] - old_rating) >= abs(ranked[1] - old_rating) - 5:
        return None, False
    return ranked[0], True


def update_league(csv_path: Path, rating_by_team: dict[str, float], dry_run: bool) -> dict:
    """Returns a report dict: {matched: [...], unmatched: [...], unchanged: [...]}.

    rating_by_team: {this league's own ratings-CSV "team" value: new
    rating}, already fully resolved by resolve_tracked_leagues() -- at
    most one scrape row per club, so no further disambiguation happens
    here; this function only decides whether to WRITE that resolved
    value (skipping a no-op update within 0.05)."""
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    report = {"matched": [], "unmatched": [], "unchanged": []}

    for row in rows:
        team = (row.get("team") or "").strip()
        if not team:
            continue

        old_rating = row.get("opta_rating", "")
        try:
            old_val = float(old_rating)
        except (TypeError, ValueError):
            old_val = None

        new_rating = rating_by_team.get(team)
        if new_rating is None:
            report["unmatched"].append(team)
            continue

        if old_val is not None and abs(old_val - new_rating) < 0.05:
            report["unchanged"].append(team)
            continue

        report["matched"].append((team, old_rating, new_rating))
        if not dry_run:
            row["opta_rating"] = f"{new_rating:.1f}"

    if not dry_run and report["matched"]:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return report


def main():
    dry_run = "--dry-run" in sys.argv
    if not Path(RANKINGS_PATH).exists():
        print(f"{RANKINGS_PATH} not found -- run scrape_opta_power_rankings.py first.", file=sys.stderr)
        sys.exit(1)

    from build_club_power_rankings import resolve_tracked_leagues

    global_df = pd.read_csv(RANKINGS_PATH)
    global_df["rating"] = pd.to_numeric(global_df["rating"], errors="coerce")
    tracked_league, canonical_team = resolve_tracked_leagues(global_df)

    # {(league label, canonical team name): resolved rating} -- one entry
    # per tracked club resolve_tracked_leagues actually matched.
    rating_by_label_team: dict[tuple[str, str], float] = {}
    for idx in global_df.index:
        label, canonical = tracked_league.at[idx], canonical_team.at[idx]
        if label and canonical:
            rating_by_label_team[(label, canonical)] = global_df.at[idx, "rating"]
    print(f"Resolved {len(rating_by_label_team)} tracked clubs against the global scrape.", file=sys.stderr)

    totals = {"matched": 0, "unmatched": 0, "unchanged": 0}
    all_unmatched: dict[str, list[str]] = {}
    all_matched: dict[str, list[tuple]] = {}

    for league_name, cfg in LEAGUES.items():
        csv_path = RATINGS_DIR / f"{cfg.get('tsdb_id', cfg['id'])}.csv"
        if not csv_path.exists():
            print(f"  SKIP {league_name}: no ratings file at {csv_path}", file=sys.stderr)
            continue
        label = f"{cfg['flag']} {league_name}"
        rating_by_team = {c: r for (lbl, c), r in rating_by_label_team.items() if lbl == label}
        report = update_league(csv_path, rating_by_team, dry_run)
        totals["matched"] += len(report["matched"])
        totals["unmatched"] += len(report["unmatched"])
        totals["unchanged"] += len(report["unchanged"])
        if report["unmatched"]:
            all_unmatched[league_name] = report["unmatched"]
        if report["matched"]:
            all_matched[league_name] = report["matched"]
        print(f"  {league_name}: {len(report['matched'])} updated, "
              f"{len(report['unchanged'])} unchanged, {len(report['unmatched'])} unmatched",
              file=sys.stderr)

    print(f"\nTOTAL: {totals['matched']} updated, {totals['unchanged']} unchanged, "
          f"{totals['unmatched']} unmatched"
          + (" (dry run, nothing written)" if dry_run else ""),
          file=sys.stderr)

    if all_matched:
        print("\nUpdated ratings:", file=sys.stderr)
        for league_name, entries in all_matched.items():
            for team, old_rating, new_rating in entries:
                print(f"  {league_name}: {team} ({old_rating} -> {new_rating})", file=sys.stderr)

    if all_unmatched:
        print("\nUnmatched teams by league (left at their existing rating):", file=sys.stderr)
        for league_name, teams in all_unmatched.items():
            print(f"  {league_name}: {', '.join(teams)}", file=sys.stderr)


if __name__ == "__main__":
    main()
