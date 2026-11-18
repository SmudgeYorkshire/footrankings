"""
Persistent, full-history odds-implied NATIONAL TEAM rating -- the nation-
level analog of club_odds_ratings.py, reusing that module's proven
mechanics (persist-and-accumulate across runs, not refit-from-scratch;
a ledger applying each real fixture exactly once; only shrink teams a
run's own observations actually touch) against a different, simpler
underlying fit.

Reads the SAME odds_coverage/daily_odds/*.json files club_odds_ratings.py
and club_rating_calibration.py already read -- fetch_daily_odds.py's own
daily pull is unscoped (every odds-covered fixture API-Football has that
day, not just tracked club leagues), so real national-team odds (UEFA/
CONCACAF Nations League, AFCON qualifiers, FIFA Asean Cup, SAFF
Championship, Gulf Cup of Nations, senior "Friendlies") were already
sitting there unused, tagged tracked=False, the same situation UCL/UEL/
UECL odds were in before club_rating_calibration.py started reading
them. See INTERNATIONAL_COMPETITIONS below for exactly which league
names count, and why most of this file's own filtering happens there
rather than on the existing "tracked" flag (that flag means "one of our
54 tracked CLUB leagues", not relevant here).

Two real differences from club_odds_ratings.py, both simplifications:
  - Fitting math: classic Elo win-expectancy (1/(1+10**(-diff/400)), +100
    home-advantage points) instead of the club pipeline's Poisson/
    attack-defense goal model. There's no single
    "league scope" to anchor a goal model against here (this pool spans
    World Cup/continental qualifiers and friendlies between arbitrary
    pairs); classic Elo is this codebase's own already-proven approach
    for exactly this kind of cross-country fit.
  - State key: bare team name, not (league_id, team) -- country names
    have no realistic homonym-collision risk the way club names do
    ("Arsenal", "Olympiakos", ...), so the compound key club_odds_
    ratings.py needs isn't necessary here.

Seeded from ratings/nation_elo_global.csv (scrape_nation_elo_ratings.py's
own output -- every team eloratings.net rates) for any team with no
persisted value yet, same "being seeded for the first time right here"
idea _fit_persistent already uses for clubs (raw Opta there, raw
eloratings.net Elo here).

This feeds build_nation_power_rankings.py / nation_power_rankings.py
("Nation Strength Rankings"), same bootstrapping order club_power_
rankings.py itself followed (display first; live-wiring was a separate,
later phase). As of 2026-11-18, nations_league_simulator.py's own
load_nl_ratings() reads that same combined_rating directly -- the old,
bespoke Nations League Elo/odds pipeline this file's own docstring used
to describe here (a manual-only scrape + calibration workflow) has been
retired entirely.

Usage:
    py nation_odds_ratings.py [--date YYYY-MM-DD]
"""

import argparse
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from update_ratings_from_opta import _normalize, fuzzy_token_match

DAILY_ODDS_DIR = Path("odds_coverage") / "daily_odds"
GLOBAL_ELO_PATH = Path("ratings") / "nation_elo_global.csv"
RATINGS_OUT_PATH = Path("ratings") / "nation_odds_implied_ratings.csv"
LEDGER_PATH = Path("ratings") / "nation_odds_processed_fixtures.csv"

# Genuine senior men's national-team competitions only -- confirmed
# against real league-name strings already sitting in odds_coverage/
# daily_odds/*.json (a full scan of every stored file, 2026-11-15).
# Deliberately excludes (by omission, all confirmed present in that same
# scan): "Friendlies Clubs"/"Friendlies Women" (this site's existing
# Nations League coverage is men's senior internationals only, matched
# here), every CAF/CONMEBOL/AFC CLUB competition that happens to share a
# confederation-style name with a national-team one (CAF Champions
# League/Confederation Cup, CONMEBOL Libertadores/Sudamericana, AFC
# Champions League, every Women's club competition), and every U17/U19/
# U20/U21/U23 qualifier or league (youth, not senior). Grow this the same
# organic, bug-driven way club_odds_ratings.py's own alias dicts grew --
# by checking real odds_coverage data for a league name that should
# count but doesn't yet, not by guessing an unconfirmed string.
INTERNATIONAL_COMPETITIONS: set[str] = {
    "UEFA Nations League",
    "CONCACAF Nations League",
    "Africa Cup of Nations - Qualification",
    "Friendlies",
    "FIFA Asean Cup",
    "SAFF Championship",
    "Gulf Cup of Nations",
}

HOME_ADVANTAGE_ELO_PTS = 100.0  # classic national-team Elo convention

# Starting points, copied from club_odds_ratings.py's own already-
# validated values (see that module's own docstring for how they were
# swept) -- not yet independently re-tuned for this different fitting
# model/competition pool. Revisit with an analogous held-out validation
# pass if this rating's own accuracy is ever checked the way club_odds_
# rating_validation.py checks the club one.
LEARNING_RATE = 0.6
L2_SHRINKAGE = 0.10
EPOCHS = 10
MIN_BOOKMAKERS_FOR_FULL_WEIGHT = 5

# Safety rail only (see club_odds_ratings.py's own module docstring for
# why this is a runaway-bug backstop, not a design choice about how far
# odds should be allowed to move a team) -- wide margin either side of
# eloratings.net's own real current range (369-2290, confirmed live).
RATING_SANITY_MIN = 100.0
RATING_SANITY_MAX = 2500.0

# How much real odds-implied evidence (n_updates) a team needs before a
# display blend trusts it as much as the raw Elo baseline -- same idea
# and same starting value as club_odds_ratings.N_FULL_CONFIDENCE (not
# independently re-swept for this pool yet).
N_FULL_CONFIDENCE = 6


def _elo_expectancy(rating_diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-rating_diff / 400.0))


def _load_global_elo() -> pd.DataFrame:
    if not GLOBAL_ELO_PATH.exists():
        return pd.DataFrame(columns=["team", "alias", "elo_rating", "elo_rank"])
    return pd.read_csv(GLOBAL_ELO_PATH)


# API-Football's own odds-feed spelling, only where it differs from
# eloratings.net's (the global roster's own canonical name) and the
# normalized/fuzzy tiers below can't bridge it on their own (an acronym
# or a genuinely different short name, not just accents/casing). Grown
# the same organic way as every other alias dict in this codebase --
# confirmed against real odds_coverage data, 2026-11-15.
_ODDS_NAME_ALIASES: dict[str, str] = {
    "Türkiye": "Turkey",
    "Czech Republic": "Czechia",
    "FYR Macedonia": "North Macedonia",
    "USA": "United States",
    "Chinese Taipei": "Taiwan",
    "St. Kitts and Nevis": "Saint Kitts and Nevis",
    "St. Lucia": "Saint Lucia",
    "St. Vincent / Grenadines": "Saint Vincent and the Grenadines",
}


def _resolve_team(name: str, roster: pd.DataFrame) -> str | None:
    """Match an odds provider's team name against the global Elo roster's
    own "team"/"alias" column -- same three-tier convention (exact,
    normalized, fuzzy token-subset) update_ratings_from_opta._resolve_team
    -style matching already uses elsewhere in this codebase, just against
    ~244 countries instead of one league's ~18-20 clubs. Country names
    carry far less homonym-collision risk than club names do, so the
    looser tiers are safe here too. _ODDS_NAME_ALIASES is checked first,
    for a mismatch too different for either tier to bridge on its own."""
    name = _ODDS_NAME_ALIASES.get(name, name)
    for _, row in roster.iterrows():
        if name == row["team"] or name == row.get("alias", ""):
            return row["team"]
    norm_name = _normalize(name)
    for _, row in roster.iterrows():
        if norm_name == _normalize(row["team"]) or norm_name == _normalize(str(row.get("alias", ""))):
            return row["team"]
    for _, row in roster.iterrows():
        if fuzzy_token_match(name, (row["team"], str(row.get("alias", "")))):
            return row["team"]
    return None


def _resolve_observations(roster: pd.DataFrame, observations: list[dict]) -> list[dict]:
    resolved = []
    unresolved = set()
    for o in observations:
        home = _resolve_team(o["home_team"], roster)
        away = _resolve_team(o["away_team"], roster)
        if home and away:
            resolved.append({**o, "home_team": home, "away_team": away})
        else:
            unresolved.add((o["home_team"], o["away_team"]))
    for h, a in unresolved:
        print(f"  WARNING: couldn't resolve '{h}' vs '{a}' to a known national team", file=sys.stderr)
    return resolved


def _is_youth_team(name: str) -> bool:
    """True for a trailing age-group suffix (U17/U19/U20/U21/U23...) --
    confirmed live 2026-11-15 that API-Football tags youth internationals
    under the SAME plain "Friendlies" league name as senior ones (no
    separate "Friendlies U21"-style league string to filter on), so this
    needs its own check rather than relying on INTERNATIONAL_COMPETITIONS
    alone. Senior/youth is the only split checked -- women's internationals
    use their own distinctly-named leagues already excluded there."""
    tokens = name.split()
    return bool(tokens) and tokens[-1].upper().lstrip("U").isdigit() and tokens[-1].upper().startswith("U")


def _load_all_international_observations() -> list[dict]:
    """Every api_football observation, across EVERY odds_coverage/
    daily_odds/*.json file (full history, no window), whose league name
    is in INTERNATIONAL_COMPETITIONS and whose teams are senior (not
    youth, see _is_youth_team) -- deduped to the freshest (latest-dated
    file) capture of each real-world fixture, same "filenames sort
    chronologically so later files simply overwrite" rule club_odds_
    ratings._load_all_tracked_observations() uses."""
    by_fixture: dict[tuple, dict] = {}
    for path in sorted(DAILY_ODDS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            day_obs = json.load(f)
        for o in day_obs:
            if o.get("source") != "api_football" or o.get("league") not in INTERNATIONAL_COMPETITIONS:
                continue
            if not o.get("commence_time"):
                continue
            if _is_youth_team(o.get("home_team", "")) or _is_youth_team(o.get("away_team", "")):
                continue
            key = (o.get("league"), o.get("home_team"), o.get("away_team"), o["commence_time"])
            by_fixture[key] = o
    return list(by_fixture.values())


def _load_ledger() -> set[tuple]:
    if not LEDGER_PATH.exists():
        return set()
    with open(LEDGER_PATH, encoding="utf-8") as f:
        return {
            (r["league"], r["home_team"], r["away_team"], r["commence_time"])
            for r in csv.DictReader(f)
        }


def _append_ledger(keys: list[tuple]) -> None:
    """Re-reads the ledger fresh right before writing and skips any key
    already on disk -- same write-time dedup guard club_odds_ratings.py's
    own _append_ledger uses, for the same reason (a real, confirmed
    duplicate-row bug there, see that function's own docstring)."""
    on_disk = _load_ledger()
    new_keys = [k for k in keys if k not in on_disk]
    if not new_keys:
        return
    LEDGER_PATH.parent.mkdir(exist_ok=True)
    is_new = not LEDGER_PATH.exists()
    with open(LEDGER_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["league", "home_team", "away_team", "commence_time"])
        writer.writerows(new_keys)


def _clean_str(v) -> str:
    return "" if pd.isna(v) else str(v)


def _load_state() -> dict[str, dict]:
    """{team: {rating, seed, n_updates, last_updated}}."""
    if not RATINGS_OUT_PATH.exists():
        return {}
    df = pd.read_csv(RATINGS_OUT_PATH, dtype=str)
    state: dict[str, dict] = {}
    for _, r in df.iterrows():
        state[r["team"]] = {
            "rating": float(r["odds_rating"]),
            "seed": float(r["seed_rating"]),
            "n_updates": int(r["n_updates"]),
            "last_updated": _clean_str(r.get("last_updated")),
        }
    return state


def _save_state(state: dict[str, dict]) -> None:
    RATINGS_OUT_PATH.parent.mkdir(exist_ok=True)
    rows = sorted(
        (
            {
                "team": t,
                "odds_rating": round(v["rating"], 2),
                "seed_rating": round(v["seed"], 2),
                "n_updates": v["n_updates"],
                "last_updated": v["last_updated"],
            }
            for t, v in state.items()
        ),
        key=lambda r: -r["odds_rating"],
    )
    with open(RATINGS_OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "odds_rating", "seed_rating", "n_updates", "last_updated"])
        writer.writeheader()
        writer.writerows(rows)


def blend_nation_rating(team: str, base_rating: float, state: dict | None = None) -> float:
    """Display-only confidence blend -- identical formula to club_odds_
    ratings.blend_with_live_rating(), NOT currently called from any live
    prediction path (see module docstring)."""
    state = state if state is not None else _load_state()
    entry = state.get(team)
    if not entry:
        return base_rating
    confidence = min(1.0, entry["n_updates"] / N_FULL_CONFIDENCE)
    return base_rating * (1.0 - confidence) + entry["rating"] * confidence


def _fit_persistent(resolved: list[dict], current_ratings: dict[str, float], epochs: int = EPOCHS) -> dict[str, float]:
    """club_odds_ratings._fit_persistent, adapted to classic Elo win-
    expectancy instead of a Poisson goal model -- see module docstring
    for why. Draw is stripped out of each observation's de-vigged 1X2
    probability first (home_prob/(home_prob+away_prob)), since classic
    Elo expectancy has no draw concept to compare against directly.

    Returns the final ABSOLUTE rating for every team with >=1 observation
    in `resolved`, loosely sanity-clamped -- not every team in
    current_ratings (a team with zero observations this run is left out
    entirely, so the caller's persistent merge leaves its last fitted
    value untouched rather than overwriting it)."""
    if not resolved:
        return {}

    touched = {t for o in resolved for t in (o["home_team"], o["away_team"])}
    adj: dict[str, float] = {t: 0.0 for t in touched}

    def _weight(o: dict) -> float:
        return min(1.0, o.get("bookmaker_count", 0) / MIN_BOOKMAKERS_FOR_FULL_WEIGHT)

    for _ in range(epochs):
        for o in resolved:
            home, away = o["home_team"], o["away_team"]
            rating_home = current_ratings.get(home, 0.0) + adj.get(home, 0.0)
            rating_away = current_ratings.get(away, 0.0) + adj.get(away, 0.0)
            diff = rating_home - rating_away + HOME_ADVANTAGE_ELO_PTS
            model_home = _elo_expectancy(diff)
            target_home = o["home_prob"] / (o["home_prob"] + o["away_prob"])
            err = target_home - model_home
            w = _weight(o)
            adj[home] += LEARNING_RATE * w * err
            adj[away] -= LEARNING_RATE * w * err
        for t in touched:
            adj[t] *= (1.0 - L2_SHRINKAGE)

    return {
        t: max(RATING_SANITY_MIN, min(RATING_SANITY_MAX, round(current_ratings.get(t, 0.0) + adj[t], 2)))
        for t in touched
    }


def main(as_of_date: str) -> None:
    as_of = date.fromisoformat(as_of_date)
    roster = _load_global_elo()
    if roster.empty:
        print(
            f"No {GLOBAL_ELO_PATH} found -- run scrape_nation_elo_ratings.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    seed_lookup = dict(zip(roster["team"], roster["elo_rating"]))

    all_obs = _load_all_international_observations()
    ledger = _load_ledger()

    pending = 0
    resolvable: list[dict] = []
    for o in all_obs:
        try:
            kickoff_date = datetime.fromisoformat(o["commence_time"]).date()
        except ValueError:
            continue
        if kickoff_date >= as_of:
            pending += 1
            continue
        resolvable.append(o)

    resolved_all = _resolve_observations(roster, resolvable)
    # Ledger check against RESOLVED (canonical) names -- a raw odds-feed
    # name needing alias resolution would never match a canonically-keyed
    # ledger entry otherwise, the same real bug class club_odds_ratings.py
    # confirmed and fixed for clubs (see that module's own main() comment).
    resolved = [
        o for o in resolved_all
        if (o["league"], o["home_team"], o["away_team"], o["commence_time"]) not in ledger
    ]
    if not resolved:
        print(f"No newly-kicked-off international fixtures ready to incorporate as of {as_of_date} "
              f"({pending} captured but still pending kickoff).")
        return

    state = _load_state()
    touched = {t for o in resolved for t in (o["home_team"], o["away_team"])}
    # A team with no persisted entry yet starts the fit from its real
    # eloratings.net seed, never from 0.0 -- confirmed live 2026-11-15 as
    # a genuinely catastrophic bug: every team's diff against a 0.0
    # baseline saturates _elo_expectancy in the very first epoch,
    # collapsing every single rating straight to RATING_SANITY_MIN.
    current_ratings = {t: state[t]["rating"] if t in state else seed_lookup.get(t, 0.0) for t in touched}

    updates = _fit_persistent(resolved, current_ratings)
    if not updates:
        print("No observations resolved to a known national team this run.")
        return

    n_obs_by_team: dict[str, int] = {}
    last_date_by_team: dict[str, str] = {}
    for o in resolved:
        for side in ("home_team", "away_team"):
            t = o[side]
            n_obs_by_team[t] = n_obs_by_team.get(t, 0) + 1
            ct_date = o["commence_time"][:10]
            if ct_date > last_date_by_team.get(t, ""):
                last_date_by_team[t] = ct_date

    for t, new_rating in updates.items():
        prev = state.get(t)
        entry = {
            "rating": new_rating,
            "seed": prev["seed"] if prev else float(seed_lookup.get(t, new_rating)),
            "n_updates": (prev["n_updates"] if prev else 0) + n_obs_by_team.get(t, 0),
            "last_updated": max(prev["last_updated"] if prev else "", last_date_by_team.get(t, "")),
        }
        state[t] = entry

    _save_state(state)
    _append_ledger([(o["league"], o["home_team"], o["away_team"], o["commence_time"]) for o in resolved])

    print(f"Incorporated {len(resolved)} newly-kicked-off international fixtures, updating "
          f"{len(updates)} teams' persistent odds-implied rating ({pending} fixtures still pending "
          f"kickoff, left for a future run). {len(state)} teams tracked in total.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    main(args.date)
