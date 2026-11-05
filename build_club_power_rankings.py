"""
Builds the Club Power Ranking -- every club Opta rates worldwide
(opta_power_rankings.csv, ~14,200 teams), not just the 54 tracked
top-flight leagues, so 2nd tiers and other countries can be folded in
later with no change to this pipeline.

Separate from (not a replacement for) the per-league opta_rating used for
match simulation: this is a derived, display-focused artifact. For the
subset of clubs in a tracked league that also got an odds-driven adjustment
today (club_rating_calibration.py), that adjustment is applied on top of
the raw Opta rating before rescaling -- the same number ratings_manager.
load_ratings() used to hand the simulator unmodified; as of 2026-11-05 the
simulator additionally blends in the persistent Odds-Implied rating on
top of this (see combined_elo below), so opta_elo is now this pipeline's
pre-blend baseline rather than an exact mirror of the simulator's input.

Three ratings are computed per club, all on one shared Elo-style number
line (see ELO_FLOOR/ELO_CEILING):
  - opta_elo: today's raw Opta rating + the existing small live nudge
    (club_rating_calibration.py) -- the simulator's own pre-odds-blend
    baseline, not the final number it predicts with (see above).
  - odds_elo: club_odds_ratings.py's persistent, full-history odds-implied
    rating, for clubs with any odds-market coverage (blank otherwise --
    deliberately NOT backfilled to Opta's number when coverage is absent).
  - combined_elo: a confidence-weighted blend of the two (full weight on
    the odds signal once a club has ~N_FULL_CONFIDENCE real odds-implied
    observations, falling back toward pure Opta as that evidence thins
    out or disappears) -- this same confidence-weighted blend (via
    club_odds_ratings.blend_with_live_rating, sharing this module's own
    N_FULL_CONFIDENCE) was wired into the actual live prediction path
    2026-11-05, in ratings_manager.load_ratings() and qualifying_
    projection.py -- opta_elo above (pure Opta + daily nudge, no odds
    blend) is now a display-only BASELINE for comparison, not "the same
    number the simulator uses" it was before that change.
Rescale (for all three) is linear min-max over the full global pool so the
single best club worldwide lands on ELO_CEILING and the single worst on
ELO_FLOOR (not a per-tier or per-country rescale -- deliberately one
global scale, since the whole point is a single ranking spanning every
club Opta covers).

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

Writes club_power_rankings_1000.csv (rank, team, tracked_league,
opta_rating_raw, adjustment, odds_implied_rating, odds_n_updates,
opta_elo, odds_elo, combined_elo, combined_confidence, badge_url).

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
from club_odds_ratings import N_FULL_CONFIDENCE, RATINGS_OUT_PATH as ODDS_IMPLIED_PATH

GLOBAL_RANKINGS_PATH = "opta_power_rankings.csv"
OUT_PATH = "club_power_rankings_1000.csv"
_MAX_RATING_GAP = 5.0  # see resolve_tracked_leagues' own docstring for why

# Standard-looking Elo number line instead of the old 0-1000 scale -- the
# single best club worldwide today lands on ELO_CEILING, the single worst
# on ELO_FLOOR, same linear min-max idea as the old rating_1000, just
# different endpoints. Anchors are a deliberate stylistic choice, not a
# literal match to clubelo.com's own empirical range (real clubelo/World
# Football Elo peaks run roughly 2100-2150 at most, e.g. peak Pep
# Barcelona, peak Argentina) -- chosen instead to land in a band that
# reads the way chess's familiar 2200-2400 ("National Master" to just
# under "International Master") does for a casual audience: a number
# that clearly signals "the best," without implying we've reproduced
# clubelo's specific methodology (sequential win/draw/loss Elo updates
# with a K-factor) -- we haven't; see club_odds_ratings.py's module
# docstring for why this site's rating model stays the existing Poisson/
# attack-defense fit instead.
ELO_FLOOR = 1200.0
ELO_CEILING = 2400.0


def _combined_rating(
    adjusted_rating: pd.Series, league_raw_rating: pd.Series, odds_delta: pd.Series, confidence: pd.Series,
) -> pd.Series:
    """Straight linear interpolation between adjusted_rating (Opta +
    today's small live nudge -- Opta Elo's own basis) and the odds-implied
    rating's global-scale equivalent (league_raw_rating + odds_delta,
    i.e. odds_implied_rating re-expressed on this global scale -- see
    odds_elo's own computation, which rescales this exact same quantity):
    `adjusted_rating * (1 - confidence) + odds_equivalent * confidence`.

    NOT "adjusted_rating + odds_delta * confidence" (the original, buggy
    version of this): that double-counts the live nudge at high
    confidence, since adjusted_rating already includes it and odds_delta
    is computed against the UNADJUSTED raw rating -- confirmed 2026-11-04
    via club_combined_rating_validation.py (live=92.5, odds=95.0 -> the
    old formula gave 97.5 at full confidence instead of 95.0). Straight
    interpolation correctly reduces to adjusted_rating at confidence=0 and
    exactly the odds-implied rating at confidence=1, with no double-
    counting in between.

    Wherever odds_delta is NaN (no odds coverage for that club),
    `confidence` is already guaranteed 0 by the caller (odds_n_updates
    defaults to 0 there too) -- the `.fillna(adjusted_rating)` below only
    exists so that guaranteed-zero-weight term doesn't poison the result
    with NaN; its actual value is never used."""
    odds_equivalent = (league_raw_rating + odds_delta).fillna(adjusted_rating)
    return adjusted_rating * (1.0 - confidence) + odds_equivalent * confidence


def _to_elo(values: pd.Series, lo: float, hi: float) -> pd.Series:
    """Linear rescale onto [ELO_FLOOR, ELO_CEILING]. NaN stays NaN -- a
    club with no odds coverage should show a blank Odds Elo, not a
    misleading number. `lo`/`hi` are always the SAME two anchors (the
    global Opta pool's own adjusted_rating min/max) for every metric this
    is applied to, so Opta/Odds/Combined Elo stay comparable on one
    number line instead of each being independently min-maxed against
    its own, differently-sized population."""
    return (ELO_FLOOR + (values - lo) / (hi - lo) * (ELO_CEILING - ELO_FLOOR)).round(0)


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

    # club_odds_ratings.py's persistent, full-history odds-implied rating --
    # read-only, display-only comparison column. Keyed by (league_id, team),
    # NOT bare team name: that file deliberately disambiguates same-named
    # clubs across different leagues (e.g. England's "Arsenal" vs Belarus's
    # "Arsenal" -- a real collision found 2026-11-04), so the lookup here
    # must too, or it would silently show one club's number under the
    # other's row depending on which happened to sort last. tracked_league
    # (just resolved above) already pins each global_df row to one specific
    # LEAGUES entry, so the exact same league_id club_odds_ratings.py itself
    # used is directly recoverable here -- no guessing needed. NOT folded
    # into adjusted_rating/rating_1000 below -- this is Phase 1 (build +
    # validate standalone, see club_odds_rating_validation.py), not a
    # replacement for the live Opta+adjustment number yet.
    _label_to_league_id = {
        f"{cfg['flag']} {name}": str(cfg.get("tsdb_id", cfg["id"])) for name, cfg in LEAGUES.items()
    }
    global_df["_league_id"] = global_df["tracked_league"].map(_label_to_league_id)

    # club_odds_ratings.py's rating is seeded from, and stays on the same
    # units as, each club's OWN per-league ratings/{id}.csv opta_rating
    # (that league's own best team = 100) -- NOT this file's global
    # opta_power_rankings.csv "rating" (the single best club WORLDWIDE =
    # 100, a different number for every club outside the very top of the
    # global pool). Blending odds_implied_rating straight into the global
    # scale would wrongly inflate a weak league's own top team just
    # because it sits near 100 on ITS OWN league's scale. Instead, odds_
    # implied_rating is converted to a DELTA against that same per-league
    # baseline (odds_delta = odds_implied_rating - own_league_raw_rating)
    # -- exactly the same "delta from the per-league Opta number" shape
    # `adjustment` (club_rating_calibration.py's own nudge) already is --
    # and that delta is what gets added onto the GLOBAL rating below, so
    # everything stays in one consistent unit.
    _known_rating_by_key: dict[tuple[str, str], float] = {
        (_label_to_league_id.get(label, ""), canonical): known_rating
        for label, canonical, known_rating, _names in tracked_league_map()
        if known_rating is not None
    }
    global_df["_league_raw_rating"] = global_df.apply(
        lambda r: _known_rating_by_key.get((r["_league_id"], r["_canonical_team"])) if r["_canonical_team"] else None,
        axis=1,
    )

    odds_meta: dict[tuple[str, str], tuple[float, int]] = {}
    if ODDS_IMPLIED_PATH.exists():
        odf = pd.read_csv(ODDS_IMPLIED_PATH, dtype=str)
        odf["opta_rating"] = pd.to_numeric(odf["opta_rating"], errors="coerce")
        odf["n_updates"] = pd.to_numeric(odf["n_updates"], errors="coerce").fillna(0).astype(int)
        odds_meta = {
            (lid, t): (r, n) for lid, t, r, n in zip(odf["league_id"], odf["team"], odf["opta_rating"], odf["n_updates"])
        }
    global_df["odds_implied_rating"] = global_df.apply(
        lambda r: odds_meta.get((r["_league_id"], r["_canonical_team"]), (None, 0))[0] if r["_canonical_team"] else None,
        axis=1,
    )
    global_df["odds_n_updates"] = global_df.apply(
        lambda r: odds_meta.get((r["_league_id"], r["_canonical_team"]), (None, 0))[1] if r["_canonical_team"] else 0,
        axis=1,
    )
    global_df["odds_delta"] = global_df["odds_implied_rating"] - global_df["_league_raw_rating"]

    global_df["opta_rating_raw"] = global_df["rating"]
    global_df["adjusted_rating"] = global_df["opta_rating_raw"] + global_df["adjustment"]

    # Co-equal-input blend (the "Combined Strength Ranking"): confidence-
    # weighted by how much real odds-implied evidence THIS club has
    # (club_odds_ratings.py's own n_updates), per the user's own chosen
    # design -- a club with deep odds coverage trusts the odds signal as
    # much as Opta; a club with little/none falls back toward pure Opta
    # (+ today's existing small live nudge), exactly the "Opta Rankings
    # are good for clubs/leagues where Odds Rankings lack information"
    # fallback this was built for. NOT wired into any live prediction
    # path yet -- this stays a display-only column here (like odds_
    # implied_rating already was) until a future phase decides to feed
    # it into ratings_manager.load_ratings() for actual match simulation.
    global_df["combined_confidence"] = (global_df["odds_n_updates"] / N_FULL_CONFIDENCE).clip(upper=1.0)
    global_df["combined_rating"] = _combined_rating(
        global_df["adjusted_rating"], global_df["_league_raw_rating"],
        global_df["odds_delta"], global_df["combined_confidence"],
    )

    # Elo-scale display rescale -- see ELO_FLOOR/ELO_CEILING's own comment.
    # lo/hi are always derived from the GLOBAL Opta pool's adjusted_rating
    # (the one metric with full coverage), reused for all three so Opta/
    # Odds/Combined Elo are directly comparable on one number line.
    lo, hi = global_df["adjusted_rating"].min(), global_df["adjusted_rating"].max()
    global_df["opta_elo"] = _to_elo(global_df["adjusted_rating"], lo, hi)
    global_df["odds_elo"] = _to_elo(
        global_df["_league_raw_rating"] + global_df["odds_delta"], lo, hi,
    )  # NaN where odds_delta is NaN (no coverage) -- deliberately left blank, not backfilled to Opta's number
    global_df["combined_elo"] = _to_elo(global_df["combined_rating"], lo, hi)

    out = global_df.sort_values("combined_elo", ascending=False).reset_index(drop=True)
    out = out.drop(columns=["rank", "_canonical_team"])  # supersede Opta's raw rank with our post-blend one
    out.insert(0, "rank", out.index + 1)
    out = out[["rank", "team", "tracked_league", "opta_rating_raw", "adjustment",
               "odds_implied_rating", "odds_n_updates", "opta_elo", "odds_elo", "combined_elo",
               "combined_confidence", "badge_url"]]
    out.to_csv(OUT_PATH, index=False)

    n_adjusted = (out["adjustment"] != 0.0).sum()
    n_odds = out["odds_implied_rating"].notna().sum()
    print(f"Wrote {len(out)} clubs to {OUT_PATH} ({n_adjusted} with a live odds adjustment, "
          f"{n_odds} with an odds-implied rating)")
    summary = out.head(10).to_string(index=False)
    print(summary.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))


if __name__ == "__main__":
    main()
