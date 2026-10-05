"""
Builds the new, standalone 0-1000 Club Power Ranking -- every club Opta
rates worldwide (opta_power_rankings.csv, ~14,200 teams), not just the 54
tracked top-flight leagues, so 2nd tiers and other countries can be folded
in later with no change to this pipeline.

Separate from (not a replacement for) the per-league opta_rating used for
match simulation: this is a derived, display-focused artifact. For the
subset of clubs in a tracked league that also got an odds-driven adjustment
today (club_rating_calibration.py), that adjustment is applied on top of
the raw Opta rating before rescaling -- same number ratings_manager.
load_ratings() hands to the simulator, just rescaled for this global view.

Rescale is linear min-max over the full global pool so the single best club
= 1000 and the single worst = 0 (not a per-tier or per-country rescale --
deliberately one global scale, since the whole point is a single ranking
spanning every club Opta covers).

Tracked-league membership is tagged the same way opta_rankings.py's
"Complete Rankings" tab does it -- both import resolve_tracked_leagues()
from here, so there's one shared implementation, not two copies that can
drift apart.

Matching is name-based (team/alias from every league's own ratings CSV,
normalized fallback) but a normalized name alone is NOT assumed unique:
plenty of club names recur across countries by coincidence (Arsenal,
Rangers, Inter, Racing, Nacional, ...), and the global scrape has no
country column to disambiguate with directly. When a tracked club's
normalized name matches more than one row in the global scrape,
resolve_tracked_leagues() claims only the row whose rating is closest to
that club's own known opta_rating (same disambiguation
update_ratings_from_opta.py's _pick_rating already uses, and for the same
reason: the real update from one day to the next is reliably smaller than
the gap to an unrelated homonym club). Earlier versions of this matching
tagged EVERY row sharing a name, which double- (sometimes 8x-) counted
big clubs like Arsenal/Inter/Juventus/Rangers under the global scrape's
unrelated homonyms in other countries.

Writes club_power_rankings_1000.csv (rank, team, country_or_league,
opta_rating_raw, adjustment, rating_1000, badge_url).

Usage: py build_club_power_rankings.py
"""

import csv
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from config import LEAGUES
from ratings_manager import load_club_rating_adjustments
from update_ratings_from_opta import _normalize

GLOBAL_RANKINGS_PATH = "opta_power_rankings.csv"
OUT_PATH = "club_power_rankings_1000.csv"
_MAX_RATING_GAP = 5.0  # see resolve_tracked_leagues' own docstring for why


def tracked_league_map() -> list[tuple[str, str, float | None, set[str]]]:
    """[(label, canonical_team, known_rating, {normalized names...}), ...]
    one entry PER TRACKED CLUB (not per name) -- every distinct normalized
    form that club could appear under in the global scrape (from its
    team/alias/opta_scrape_alias columns) is collected into one set, so a
    club whose team name and alias normalize differently is still resolved
    as a single club with several possible candidate rows, not as two
    independent entries that could each separately claim a different row.
    Confirmed on real data why that distinction matters: Ukraine's ratings
    CSV has team="Karpaty Lviv", alias="Karpaty" -- an earlier, per-name
    version of this map let "Karpaty Lviv" claim the real Karpaty Lviv row
    (75.0) under one key AND an unrelated "Karpaty"-named homonym (49.2)
    under the other, and whichever got written last silently overwrote the
    club's own correct rating with the wrong club's.

    known_rating is that club's own current opta_rating (ratings/{id}.csv)
    -- the anchor resolve_tracked_leagues() disambiguates against whenever
    more than one candidate row is in play, for this club or for others
    competing for the same row.

    Deliberately exact/normalized matching only -- no fuzzy (token-subset)
    fallback here. That fallback is safe in club_rating_calibration.py
    because it only ever runs against one league's ~20-team roster; tried
    against this page's ~1,500 tracked names combined, it produced a real
    false positive (the global scrape's "Villa" -- a different, unrelated
    club ranked 10th globally -- matched ratings' "Aston Villa" on the
    single generic token "villa", even though the real Aston Villa already
    had its own correct entry elsewhere in the same global list). A few
    clubs whose global-scrape spelling doesn't exactly match (e.g. "FC
    Bayern" vs. ratings' "Bayern München"/alias "Bayern Munich") just go
    untagged here rather than risk that kind of collision -- unless that
    club has a confirmed opta_scrape_alias (see below).

    A 3rd optional column, opta_scrape_alias, is also checked alongside
    team/alias. It exists because `alias` is already overloaded site-wide
    as "whatever a DIFFERENT external provider (API-Football) calls this
    club" (see admin.py's own column header, "API-Football Name (if
    different)") -- overwriting it with Opta's own shortened scrape
    spelling risks breaking that unrelated matching path. opta_scrape_
    alias is reserved specifically for "what this exact global Opta
    Power Rankings scrape calls this club" and is cross-checked by hand
    (name AND rating both verified) before being added, not inferred
    automatically -- see update_ratings_from_opta.py, which reads the
    same column for its own daily opta_rating sync.
    """
    clubs: list[tuple[str, str, float | None, set[str]]] = []
    for league_name, cfg in LEAGUES.items():
        label = f"{cfg['flag']} {league_name}"
        csv_path = Path("ratings") / f"{cfg.get('tsdb_id', cfg['id'])}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str)
        for _, row in df.iterrows():
            canonical = row["team"]
            try:
                known_rating = float(row.get("opta_rating", ""))
            except (TypeError, ValueError):
                known_rating = None
            names: set[str] = set()
            for col in ("team", "alias", "opta_scrape_alias"):
                name = str(row.get(col, "")).strip()
                if name and name.lower() != "nan":
                    names.add(_normalize(name))
            if names:
                clubs.append((label, canonical, known_rating, names))
    return clubs


def resolve_tracked_leagues(global_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(tracked_league, canonical_team) Series aligned to global_df's index.

    Each tracked club claims AT MOST ONE row in global_df, and each row
    goes to AT MOST ONE tracked club -- whether several clubs share one
    normalized name (a real-world homonym in another country, e.g. one of
    the many clubs worldwide simply called "Inter" or "Racing"; or several
    tracked clubs legitimately sharing one short alias, "Dinamo", "Sparta",
    ...) or one club has several candidate rows of its own (its team name
    and its alias normalize differently, and each happens to also match a
    DIFFERENT scrape row). Resolved as a single global greedy closest-
    rating assignment across every (club, candidate row) pair at once --
    not grouped by name first -- so a club's own best-fitting row always
    wins over its own weaker options, not just over other clubs': every
    pair gets a |rating - known_rating| score, pairs are taken smallest-
    gap-first, and a club or row already claimed is skipped. Same anchor-
    to-known-rating idea update_ratings_from_opta.py's _pick_rating uses
    for a single name's candidates, generalized to the whole tracked set
    at once. A club with no known_rating, or whose every candidate row has
    no numeric rating, is left untagged rather than guessed at. Any pair
    whose rating gap exceeds _MAX_RATING_GAP is never taken at all, even
    as the least-bad option left once closer pairs have claimed their
    rows -- a club forced onto a clearly-wrong leftover row would be worse
    than staying untagged (confirmed on real data: without this cap,
    Dinamo Makhachkala's own close match got claimed first by a different
    Dinamo-aliased club tied at the same gap, leaving Makhachkala to
    wrongly grab an unrelated row 12+ points off)."""
    clubs = tracked_league_map()
    norm_series = global_df["team"].map(_normalize)

    indices_by_norm: dict[str, list] = {}
    for idx, norm in norm_series.items():
        indices_by_norm.setdefault(norm, []).append(idx)

    tracked_league = pd.Series("", index=global_df.index, dtype=object)
    canonical_team = pd.Series("", index=global_df.index, dtype=object)

    pairs = []  # (|diff|, club_idx, row_idx)
    for ci, (_, _, known_rating, names) in enumerate(clubs):
        if known_rating is None:
            continue
        candidate_rows: set = set()
        for name in names:
            candidate_rows.update(indices_by_norm.get(name, []))
        for gi in candidate_rows:
            rating = global_df.at[gi, "rating"]
            if pd.notna(rating):
                diff = abs(rating - known_rating)
                if diff <= _MAX_RATING_GAP:
                    pairs.append((diff, ci, gi))
    pairs.sort(key=lambda p: p[0])

    used_clubs: set[int] = set()
    used_rows: set = set()
    for _diff, ci, gi in pairs:
        if ci in used_clubs or gi in used_rows:
            continue
        used_clubs.add(ci)
        used_rows.add(gi)
        label, canonical, _, _ = clubs[ci]
        tracked_league.at[gi] = label
        canonical_team.at[gi] = canonical

    return tracked_league, canonical_team


def main() -> None:
    if not Path(GLOBAL_RANKINGS_PATH).exists():
        print(f"{GLOBAL_RANKINGS_PATH} not found -- run scrape_opta_power_rankings.py first.", file=sys.stderr)
        sys.exit(1)

    global_df = pd.read_csv(GLOBAL_RANKINGS_PATH)
    global_df["rating"] = pd.to_numeric(global_df["rating"], errors="coerce")
    global_df = global_df.dropna(subset=["rating"])

    adjustments = load_club_rating_adjustments()
    global_df["tracked_league"], global_df["_canonical_team"] = resolve_tracked_leagues(global_df)

    # One resolution feeds both the league tag above and the adjustment
    # lookup here, by design -- see tracked_league_map()'s docstring for why.
    global_df["adjustment"] = global_df["_canonical_team"].map(lambda t: adjustments.get(t, 0.0) if t else 0.0)

    global_df["opta_rating_raw"] = global_df["rating"]
    global_df["adjusted_rating"] = global_df["opta_rating_raw"] + global_df["adjustment"]

    lo, hi = global_df["adjusted_rating"].min(), global_df["adjusted_rating"].max()
    global_df["rating_1000"] = ((global_df["adjusted_rating"] - lo) / (hi - lo) * 1000).round(1)

    out = global_df.sort_values("rating_1000", ascending=False).reset_index(drop=True)
    out = out.drop(columns=["rank", "_canonical_team"])  # supersede Opta's raw rank with our post-adjustment one
    out.insert(0, "rank", out.index + 1)
    out = out[["rank", "team", "tracked_league", "opta_rating_raw", "adjustment",
               "rating_1000", "badge_url"]]
    out.to_csv(OUT_PATH, index=False)

    n_adjusted = (out["adjustment"] != 0.0).sum()
    print(f"Wrote {len(out)} clubs to {OUT_PATH} ({n_adjusted} with a live odds adjustment)")
    summary = out.head(10).to_string(index=False)
    print(summary.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))


if __name__ == "__main__":
    main()
