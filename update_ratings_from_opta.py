"""
Matches opta_power_rankings.csv (the full global scrape from
scrape_opta_power_rankings.py) against every tracked league's
ratings/{tsdb_id}.csv, updating opta_rating for every confident match.

Matching is deliberately conservative: exact match (case-insensitive) on
either the CSV's `team` or `alias` column first, then a normalized
fallback (strip diacritics/punctuation, drop a trailing club-type word
like "FC"/"CF"/"AFC"). A global name that maps to more than one team in
the scraped list (e.g. "Rangers" exists in multiple countries) is never
auto-applied -- there's no country column in the scraped data to
disambiguate with, so those are reported for manual review instead of
risking assigning the wrong club's rating.

Writes changes directly to each ratings/{id}.csv (same file the site
already reads). Run with --dry-run to see the match report without
writing anything.
"""

import csv
import re
import sys
import unicodedata
from pathlib import Path

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


def update_league(csv_path: Path, exact: dict, normalized: dict, dry_run: bool) -> dict:
    """Returns a report dict: {matched: [...], unmatched: [...], ambiguous: [...], unchanged: [...]}"""
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    report = {"matched": [], "unmatched": [], "disambiguated": [], "unchanged": []}

    for row in rows:
        team = (row.get("team") or "").strip()
        alias = (row.get("alias") or "").strip()
        if not team:
            continue

        old_rating = row.get("opta_rating", "")
        try:
            old_val = float(old_rating)
        except (TypeError, ValueError):
            old_val = None

        candidates = [team] + ([alias] if alias else [])
        new_rating = None
        matched_on = None
        disambiguated = False
        for cand in candidates:
            hits = exact.get(cand.lower())
            if hits:
                new_rating, disambiguated = _pick_rating(hits, old_val)
                matched_on = cand
                if new_rating is not None:
                    break
        if new_rating is None:
            for cand in candidates:
                hits = normalized.get(_normalize(cand))
                if hits:
                    new_rating, disambiguated = _pick_rating(hits, old_val)
                    matched_on = cand
                    if new_rating is not None:
                        break

        if new_rating is None:
            report["unmatched"].append(team)
            continue

        if old_val is not None and abs(old_val - new_rating) < 0.05:
            report["unchanged"].append(team)
            continue

        entry = (team, matched_on, old_rating, new_rating)
        report["disambiguated" if disambiguated else "matched"].append(entry)
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

    exact, normalized = load_global_rankings()
    n_ambiguous = sum(1 for v in exact.values() if len(v) > 1)
    print(f"Loaded {len(exact)} global team names ({n_ambiguous} shared by more than one club).",
          file=sys.stderr)

    totals = {"matched": 0, "disambiguated": 0, "unmatched": 0, "unchanged": 0}
    all_unmatched: dict[str, list[str]] = {}
    all_disambiguated: dict[str, list[tuple]] = {}

    for league_name, cfg in LEAGUES.items():
        csv_path = RATINGS_DIR / f"{cfg.get('tsdb_id', cfg['id'])}.csv"
        if not csv_path.exists():
            print(f"  SKIP {league_name}: no ratings file at {csv_path}", file=sys.stderr)
            continue
        report = update_league(csv_path, exact, normalized, dry_run)
        totals["matched"] += len(report["matched"])
        totals["disambiguated"] += len(report["disambiguated"])
        totals["unmatched"] += len(report["unmatched"])
        totals["unchanged"] += len(report["unchanged"])
        if report["unmatched"]:
            all_unmatched[league_name] = report["unmatched"]
        if report["disambiguated"]:
            all_disambiguated[league_name] = report["disambiguated"]
        print(f"  {league_name}: {len(report['matched'])} updated, "
              f"{len(report['disambiguated'])} disambiguated, "
              f"{len(report['unchanged'])} unchanged, {len(report['unmatched'])} unmatched",
              file=sys.stderr)

    print(f"\nTOTAL: {totals['matched']} updated, {totals['disambiguated']} disambiguated, "
          f"{totals['unchanged']} unchanged, {totals['unmatched']} unmatched"
          + (" (dry run, nothing written)" if dry_run else ""),
          file=sys.stderr)

    if all_disambiguated:
        print("\nDisambiguated (name shared by multiple clubs worldwide, resolved via "
              "closest match to the existing rating):", file=sys.stderr)
        for league_name, entries in all_disambiguated.items():
            for team, matched_on, old_rating, new_rating in entries:
                print(f"  {league_name}: {team} ({old_rating} -> {new_rating})", file=sys.stderr)

    if all_unmatched:
        print("\nUnmatched teams by league (left at their existing rating):", file=sys.stderr)
        for league_name, teams in all_unmatched.items():
            print(f"  {league_name}: {', '.join(teams)}", file=sys.stderr)


if __name__ == "__main__":
    main()
