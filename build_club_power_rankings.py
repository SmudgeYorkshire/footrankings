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
"Complete Rankings" tab already does it (match team/alias from every
league's own ratings CSV, normalized fallback) -- reused via
_tracked_league_map(), factored out of opta_rankings.py's inline version
so both pages stay in sync automatically.

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


def tracked_league_map() -> dict[str, tuple[str, str]]:
    """{normalized name: (label, canonical_team)} built from every tracked
    league's own ratings CSV (team AND alias columns) -- the same source
    opta_rankings.py's Complete Rankings tab already cross-references,
    factored out here so both pages tag "tracked" the same way with one
    source of truth. Mapping to (label, canonical_team) rather than just the
    label means one resolution step also gives the exact key
    club_rating_adjustments.csv uses for that club, rather than resolving
    "tracked league" and "which adjustment applies" separately.

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
    untagged here rather than risk that kind of collision.
    """
    exact: dict[str, tuple[str, str]] = {}
    for league_name, cfg in LEAGUES.items():
        label = f"{cfg['flag']} {league_name}"
        csv_path = Path("ratings") / f"{cfg.get('tsdb_id', cfg['id'])}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str)
        for _, row in df.iterrows():
            canonical = row["team"]
            for col in ("team", "alias"):
                name = str(row.get(col, "")).strip()
                if name and name.lower() != "nan":
                    exact.setdefault(_normalize(name), (label, canonical))
    return exact


def main() -> None:
    if not Path(GLOBAL_RANKINGS_PATH).exists():
        print(f"{GLOBAL_RANKINGS_PATH} not found -- run scrape_opta_power_rankings.py first.", file=sys.stderr)
        sys.exit(1)

    global_df = pd.read_csv(GLOBAL_RANKINGS_PATH)
    global_df["rating"] = pd.to_numeric(global_df["rating"], errors="coerce")
    global_df = global_df.dropna(subset=["rating"])

    adjustments = load_club_rating_adjustments()
    tracked_exact = tracked_league_map()

    global_df["tracked_league"] = ""
    global_df["_canonical_team"] = ""

    resolved = global_df["team"].map(lambda t: tracked_exact.get(_normalize(t)))
    found = resolved.notna()
    global_df.loc[found, "tracked_league"] = resolved[found].map(lambda r: r[0])
    global_df.loc[found, "_canonical_team"] = resolved[found].map(lambda r: r[1])

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
