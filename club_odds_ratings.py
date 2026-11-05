"""
Persistent, full-history odds-implied club rating -- Phase 1 of moving the
club odds pipeline from club_rating_calibration.py's small, capped,
14-day-window "nudge to Opta" toward something closer to a genuinely
independent, accumulating rating built from this site's complete real-
market-odds history.

club_rating_calibration.py's adjustment is REFIT FROM SCRATCH every run
against only the trailing 14 days, pulled back toward 0 each epoch, and
hard-capped at +/-10 points -- deliberately a small, mean-reverting nudge
to Opta, not a competing signal. This module instead:

  - Reads EVERY odds_coverage/daily_odds/*.json file that exists, not a
    windowed subset -- that directory already keeps everything forever
    (nothing prunes it), so "full history" was mostly a data-USE problem,
    not a data-retention one.
  - PERSISTS and ACCUMULATES: each run loads the rating this module wrote
    last time and nudges it further, it does not reset to a baseline+delta
    split. club_rating_calibration.py itself already documents exactly
    this pattern working well for the Nations League
    (nl_odds_calibration.py's fit_match_adjustments(), which loads
    current_adj and carries it forward) -- including a real, non-obvious
    bug that system already hit and fixed: shrinking the WHOLE persisted
    dict every run silently erases any team not freshly observed that
    specific run (400 epochs of 2% shrinkage =~ 99.97% decay in ONE run).
    The fix there, reused here: every regularizing step only ever touches
    teams THIS run's observations actually mention.
  - Has no tight absolute cap -- the whole point is to let this rating
    diverge from Opta as far as real market evidence supports, not to
    keep it anchored nearby. A loose [RATING_SANITY_MIN, RATING_SANITY_MAX]
    clamp exists only as a safety rail against a runaway bug, not as a
    design choice about how far odds should be allowed to move a club.

Each real-world fixture is applied EXACTLY ONCE, at its freshest pre-
kickoff capture, via a ledger (ratings/club_odds_processed_fixtures.csv)
keyed on (league, home_team, away_team, commence_time) -- unlike the
14-day window's dedup key, this includes commence_time, because the same
two clubs will legitimately meet more than once over a full season/
multi-season history and a (league, home, away)-only key would wrongly
conflate separate meetings. A fixture only becomes eligible once its
kickoff date is strictly in the past (see main()) -- fetch_daily_odds.py
only looks forward, so once a date has passed there's no way a future
pull could still improve on whatever capture of it we already have;
applying it any earlier risks locking in a stale "3 days out" price that
a closer-to-kickoff capture would have refined.

Wired into every live prediction (domestic and European) as of 2026-11-05
via blend_with_live_rating() below, confidence-weighted against Opta +
club_rating_calibration.py's daily nudge -- see that function's own
docstring. See club_odds_rating_validation.py for how this rating gets
checked, standalone, against real market data.

Writes:
  ratings/club_odds_implied_ratings.csv
    (league_id, team, alias, opta_rating, seed_rating, n_updates, last_updated)
    -- reuses the "opta_rating" column name on purpose (same trick
    scrape_elo_ratings.py already uses for Nations League Elo) so
    simulator.fixture_odds / _opta_to_attack_defense / simulate_season
    etc. can all consume a (league_id, team) slice of this file with zero
    changes, as just another ratings CSV, once a future phase wants to.
  ratings/club_odds_processed_fixtures.csv -- the ledger described above.

State is keyed by (league_id, team), NOT bare team name -- confirmed as a
real, live collision risk 2026-11-04 while testing this module: England's
"Arsenal" (ratings/4328.csv) and Belarus's "Arsenal" (canonical name in
ratings/4622.csv, alias "Arsenal Dzerzhinsk") are two completely unrelated
clubs that happen to share the exact same canonical team-name string (3
such collisions exist across all tracked leagues today: also Moldova/
Montenegro's "Iskra" and Montenegro/Slovenia's "Rudar"). A flat team-name
key would silently blend their entire odds-implied histories together
forever once both happened to have an observation in the same run --
exactly the collision class ratings_by_country()/resolve_tracked_leagues()
elsewhere in this codebase already guard against, but club_rating_
calibration.py's OWN flat club_rating_adjustments.csv output does NOT
(confirmed the same day: its final cross-league merge in main() is keyed
by bare team name too) -- that's a real, separate, pre-existing bug in
the ALREADY-LIVE production nudge system, flagged for its own follow-up
rather than fixed here, since this module's job is building the new
system, not auditing the old one. It matters far more here regardless:
club_rating_calibration.py's damage from a collision is bounded (+/-10 cap,
shrunk toward 0, refit from scratch each run) and doesn't compound: this
module's rating persists and accumulates forever, so the same collision
left unscoped would corrupt both clubs' history a little more every time
either one got a fresh observation, indefinitely.

Usage:
    py club_odds_ratings.py [--date YYYY-MM-DD]
A historical-odds bootstrap from football-data.co.uk (to deepen these 21
leagues' thin real-evidence counts with a decade-plus of free closing-odds
history) was tried and REJECTED on 2026-11-04, after real validation
testing -- documented here, not removed from history, so this isn't
re-attempted the same way without re-learning why it failed:

  - It targeted the wrong leagues: football-data.co.uk's ~21 covered
    leagues turned out to be exactly the ones API-Football's real-time
    odds coverage is already strongest for -- after just 5 weeks of the
    real daily pipeline, every current-roster team in e.g. Spanish La
    Liga, the Russian Premier League and the Danish Superliga already
    had >=1 real observation. The leagues that actually have near-zero
    coverage are the ~85 OTHER tracked leagues/tiers, which football-
    data.co.uk doesn't cover at all.
  - More fundamentally, _fit_persistent's LEARNING_RATE/EPOCHS/
    L2_SHRINKAGE were tuned (even if only provisionally) against the
    DAILY pipeline's own batch sizes -- a handful of new observations per
    call. Feeding it a much bigger batch broke that assumption and made
    things WORSE, not better, confirmed at two different granularities
    against club_odds_rating_validation.py's held-out benchmark: a
    season-sized sequential replay (~380 obs/call, 13 calls) pushed the
    21-league aggregate Brier from 0.6139 to 0.6156 and reversed EPL's
    own earlier win (0.6137 -> 0.6175); a single ~5,000-observation joint
    batch was far worse still (0.6635) -- every team's adj correction
    accumulates once per observation touching it within a SINGLE epoch's
    fixed model snapshot (the "precompute attack/defense once per epoch"
    optimization in _fit_persistent), so a team involved in hundreds of
    matches overshoots massively before the model ever updates to
    reflect any of it, in a way a ~20-40-observation daily/windowed call
    never triggers. A future attempt at this would need either a much
    smaller per-call chunk size (closer to the daily pipeline's own
    scale, e.g. monthly rather than seasonal or whole-window) or an
    explicitly batch-size-normalized learning rate -- not attempted here.
"""

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from config import LEAGUES, LEAGUES_TIER2, EUROPEAN_COMPETITIONS
from ratings_manager import load_ratings
from simulator import fixture_odds, _opta_to_attack_defense
from club_rating_calibration import _resolve_observations

DAILY_ODDS_DIR = Path("odds_coverage") / "daily_odds"
RATINGS_OUT_PATH = Path("ratings") / "club_odds_implied_ratings.csv"
LEDGER_PATH = Path("ratings") / "club_odds_processed_fixtures.csv"

# Validated 2026-11-05 by club_odds_hyperparameter_sweep.py: one-at-a-time
# sweeps against the same held-out pre-2026-10-01 football-data.co.uk
# Brier benchmark club_odds_rating_validation.py / club_combined_rating_
# validation.py use, replaying the full real fixture history day-by-day
# (same granularity main() itself runs at) across all 21 football-data.co.uk-
# covered leagues. The original values (copied from club_rating_calibration.py
# for continuity, never independently validated) scored 0.6157 combined
# n-weighted Brier; a first pass found LEARNING_RATE and L2_SHRINKAGE both
# consistently better at more extreme values across all 21 leagues (not
# cherry-picked) and EPOCHS better lower, landing a combined 0.6116; a
# second, finer pass around that neighborhood plateaued at 0.6113-0.6114,
# confirming these three values capture the real gain rather than chasing
# noise. MIN_BOOKMAKERS_FOR_FULL_WEIGHT (below) swept flat -- no change.
LEARNING_RATE = 0.6
L2_SHRINKAGE = 0.10
EPOCHS = 10

# bookmaker_count-based confidence weighting -- how reliable THIS match's
# own market price is, not how many fixtures a team happens to have in the
# current run's batch (club_rating_calibration.py's MIN_OBS_FOR_FULL_WEIGHT
# means something different here: since the ledger guarantees each real
# fixture is only ever processed once, a team caught up to real-time will
# typically have just 1 new fixture per run regardless of how long and
# well-corroborated its history is, so counting THIS run's observations
# would wrongly downweight a team with a deep history forever).
MIN_BOOKMAKERS_FOR_FULL_WEIGHT = 5

# Safety rail only -- see module docstring.
RATING_SANITY_MIN = 0.0
RATING_SANITY_MAX = 150.0

# How much real odds-implied evidence (n_updates below) a club needs
# before the live blend below trusts it as much as Opta. Swept 2026-11-04
# against club_combined_rating_validation.py's held-out Brier benchmark
# (21 leagues, 10,416 held-out matches): every N from 2-20 beat the pure
# live-nudge baseline, with a fairly flat curve across N=2-10 and N=6
# coming out marginally best. Owned here (not build_club_power_
# rankings.py, which only DISPLAYS a rating computed with this same
# number) so the display and the live blend below can never drift onto
# different thresholds.
N_FULL_CONFIDENCE = 6

# One-line rollback: flip to False to make blend_with_live_rating() below
# always return the input unchanged (pure Opta + today's small daily
# nudge, exactly today's pre-2026-11-05 behavior), with no other code
# change needed, if the live odds blend ever needs to be pulled quickly.
USE_LIVE_ODDS_BLEND = True


def blend_with_live_rating(
    league_id: str, team: str, base_rating: float, state: dict | None = None,
) -> float:
    """The actual LIVE prediction rating for one club: `base_rating`
    (today's existing Opta + small daily nudge, from ratings_manager.
    load_ratings()'s apply_adjustments=True path) confidence-weighted-
    blended with this club's persistent Odds-Implied rating -- the exact
    same formula build_club_power_rankings._combined_rating() already
    uses for the (until 2026-11-05) display-only Combined Elo column, now
    also the real prediction input, not just a display number. Reduces to
    `base_rating` unchanged for a club with no state entry (zero
    confidence) -- "Opta covers the gaps" for a club club_odds_ratings.py
    hasn't accumulated any real odds history for yet, no special-casing
    needed -- and to the pure persisted Odds-Implied rating once a club
    clears N_FULL_CONFIDENCE real observations.

    CALLERS: only ever call this from the apply_adjustments=True path.
    NEVER from apply_adjustments=False (the raw baseline every fitting/
    calibration script in this codebase relies on, including this
    module's OWN main()/_fit_persistent) -- letting this leak into the
    raw path would make club_odds_ratings.py fit its own persistent
    rating against an input that already includes itself, compounding
    indefinitely. See ratings_manager.load_ratings()'s own docstring for
    the same warning about the existing daily nudge; this is the same
    risk, one layer further out.

    `state`: pass an already-loaded `_load_state()` dict to avoid
    re-reading ratings/club_odds_implied_ratings.csv from disk on every
    single call (callers iterating many teams/leagues in one page render
    should load it once and pass it through); defaults to a fresh
    `_load_state()` call if not given."""
    if not USE_LIVE_ODDS_BLEND:
        return base_rating
    state = state if state is not None else _load_state()
    entry = state.get((league_id, team))
    if not entry:
        return base_rating
    confidence = min(1.0, entry["n_updates"] / N_FULL_CONFIDENCE)
    return base_rating * (1.0 - confidence) + entry["rating"] * confidence


def _load_all_tracked_observations() -> list[dict]:
    """Every api_football, tracked observation across EVERY odds_coverage/
    daily_odds/*.json file (no trailing-window limit), deduped to the
    freshest (latest-dated file) capture of each real-world fixture --
    club_rating_calibration._load_windowed_observations's exact
    "freshest capture wins" rule, just applied over the complete
    available history instead of a bounded window. Filenames sort
    chronologically (YYYY-MM-DD.json), so a plain sorted() walk is enough
    to guarantee later files overwrite earlier ones for the same key."""
    by_fixture: dict[tuple, dict] = {}
    for path in sorted(DAILY_ODDS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            day_obs = json.load(f)
        for o in day_obs:
            if o.get("source") != "api_football" or not o.get("tracked"):
                continue
            if not o.get("commence_time"):
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
    """Re-reads the ledger fresh right before writing (not just the
    `ledger` set main() loaded at the very start of its own run) and
    skips any key already on disk -- confirmed live 2026-11-05 that this
    file had accumulated ~2,000 duplicate rows (41% of its own size),
    one real fixture's correction applied up to 3x over, from something
    re-running this script without the ledger it started from reflecting
    an earlier run's not-yet-landed commit (closest confirmed trigger:
    the daily workflow commits twice a day, not once, despite a single
    daily cron entry -- root cause not pinned down further; this is the
    defense against whatever it turns out to be). This alone doesn't
    stop a concurrent run's gradient fit from double-counting an
    observation in memory before either process writes -- only a
    write-time guard here, re-checking disk state as close to the
    actual write as this module can get, can't fully close a true race
    between two processes that both started before either committed --
    but it does stop the ledger FILE itself from re-accumulating
    duplicate rows on every subsequent appearance of the same key,
    which is what actually matters for n_updates staying correct on any
    run after the first.
    """
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
    """A pandas cell read back as NaN (float) is truthy in Python --
    `v or ""` doesn't catch it, so a round-tripped blank field would
    otherwise be written back out as the literal text "nan"."""
    return "" if pd.isna(v) else str(v)


def _load_state() -> dict[tuple[str, str], dict]:
    """{(league_id, team): {alias, rating, seed, n_updates, last_updated}}."""
    if not RATINGS_OUT_PATH.exists():
        return {}
    df = pd.read_csv(RATINGS_OUT_PATH, dtype=str)
    state: dict[tuple[str, str], dict] = {}
    for _, r in df.iterrows():
        state[(r["league_id"], r["team"])] = {
            "alias": _clean_str(r.get("alias")),
            "rating": float(r["opta_rating"]),
            "seed": float(r["seed_rating"]),
            "n_updates": int(r["n_updates"]),
            "last_updated": _clean_str(r.get("last_updated")),
        }
    return state


def _save_state(state: dict[tuple[str, str], dict]) -> None:
    RATINGS_OUT_PATH.parent.mkdir(exist_ok=True)
    rows = sorted(
        (
            {
                "league_id": lid,
                "team": t,
                "alias": v["alias"],
                "opta_rating": round(v["rating"], 2),
                "seed_rating": round(v["seed"], 2),
                "n_updates": v["n_updates"],
                "last_updated": v["last_updated"],
            }
            for (lid, t), v in state.items()
        ),
        key=lambda r: -r["opta_rating"],
    )
    with open(RATINGS_OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["league_id", "team", "alias", "opta_rating", "seed_rating", "n_updates", "last_updated"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _load_tracked_ratings_with_source() -> pd.DataFrame:
    """Same combined cross-league roster _load_tracked_ratings_combined()
    builds, with an extra `_home_league_id` column per row -- needed to
    resolve a European-competition fixture's team back to the SAME
    (league_id, team) key its own domestic-league evidence already uses
    (so both sources accumulate into one persistent entry, not two), and
    to pick the right one of two different leagues' clubs that happen to
    share an exact name string (see module docstring). Where a name
    collides across leagues, dict construction below keeps whichever
    league comes later in LEAGUES/LEAGUES_TIER2's own iteration order --
    the same residual, already-accepted risk class _load_tracked_ratings_
    combined() itself documents; genuinely rare (3 cases total across all
    tracked leagues as of 2026-11-04) and not worth a heavier fix for a
    cross-league competition fixture specifically."""
    frames = []
    for cfg in list(LEAGUES.values()) + list(LEAGUES_TIER2.values()):
        league_id = str(cfg.get("tsdb_id", cfg["id"]))
        df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [], apply_adjustments=False)
        if df.empty:
            continue
        df = df.copy()
        df["_home_league_id"] = league_id
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["team", "alias", "opta_rating", "_home_league_id"]
    )


def _fit_persistent(
    ratings_df: pd.DataFrame, home_advantage: float, resolved: list[dict],
    current_ratings: dict[str, float], epochs: int = EPOCHS,
) -> dict[str, float]:
    """club_rating_calibration._fit_observations, adapted for a PERSISTENT
    absolute rating instead of a reset-to-zero delta from raw Opta.

    The per-call correction (`adj`) is still shrunk toward 0 each epoch --
    same regularization idea as the original, just now anchoring THIS
    call's correction close to zero (i.e. close to wherever the rating
    already sits) rather than anchoring the rating itself close to Opta.
    It gets added onto whatever's already in `current_ratings`, falling
    back to that row's raw opta_rating for a team with no persisted value
    yet -- which is exactly what "being seeded for the first time right
    here" should do, with no special-casing needed.

    `ratings_df` must be the FULL league/competition roster (not just the
    touched teams) -- fixture_odds()'s attack/defense conversion is
    sensitive to the whole pool's mean rating, same reason club_rating_
    calibration.py's own `working` always carries the complete roster too.

    Returns the final ABSOLUTE rating (not a delta) for every team with
    >=1 observation in `resolved`, loosely sanity-clamped -- see
    RATING_SANITY_MIN/MAX's own docstring note in the module header."""
    if not resolved:
        return {}

    raw_lookup = dict(zip(ratings_df["team"], ratings_df["opta_rating"]))

    def _weight(o: dict) -> float:
        return min(1.0, o.get("bookmaker_count", 0) / MIN_BOOKMAKERS_FOR_FULL_WEIGHT)

    touched = {t for o in resolved for t in (o["home_team"], o["away_team"])}
    adj: dict[str, float] = {t: 0.0 for t in touched}
    for _ in range(epochs):
        working = ratings_df.copy()
        working["opta_rating"] = working.apply(
            lambda r: current_ratings.get(r["team"], r["opta_rating"]) + adj.get(r["team"], 0.0), axis=1,
        )
        # Precomputed ONCE per epoch, not once per observation: fixture_odds()
        # would otherwise redo this exact attack/defense conversion over the
        # WHOLE roster on every single call (it only skips it when "attack"
        # is already a column) -- for a league with dozens of observations
        # in one batch (a full historical backfill especially), that's
        # avoidable O(observations) repeated roster-wide work per epoch.
        working = _opta_to_attack_defense(working)
        for o in resolved:
            model = fixture_odds(
                [{"strHomeTeam": o["home_team"], "strAwayTeam": o["away_team"]}],
                working, home_advantage=home_advantage,
            )[0]
            err_home = o["home_prob"] - model["home_win"]
            err_away = o["away_prob"] - model["away_win"]
            w = _weight(o)
            adj[o["home_team"]] += LEARNING_RATE * w * err_home
            adj[o["away_team"]] += LEARNING_RATE * w * err_away
        for t in touched:
            adj[t] *= (1.0 - L2_SHRINKAGE)

    return {
        t: max(RATING_SANITY_MIN, min(RATING_SANITY_MAX, round(current_ratings.get(t, raw_lookup[t]) + adj[t], 2)))
        for t in touched
    }



def main(as_of_date: str) -> None:
    as_of = date.fromisoformat(as_of_date)
    all_obs = _load_all_tracked_observations()
    ledger = _load_ledger()

    # Group by league and drop only "still pending kickoff" observations
    # here -- that needs just commence_time, no team-name resolution.
    # fetch_daily_odds.py only ever looks forward, so once a kickoff date
    # is in the past no future pull could still refine our capture of it;
    # applying it any earlier risks locking in a stale early-week price
    # over whatever closer-to-kickoff capture would otherwise still arrive.
    #
    # The ledger-already-processed check deliberately does NOT happen here,
    # against these observations' own RAW odds-feed team names -- it
    # happens below, AFTER _resolve_observations, against the RESOLVED
    # (canonical) names. _append_ledger always writes canonical names (see
    # `resolved` below), so comparing a raw name here would never match a
    # canonically-keyed ledger entry for any team whose raw odds-feed name
    # needs alias resolution (e.g. "Coleraine FC" in the odds feed vs this
    # site's own canonical "Coleraine") -- that fixture would look
    # perpetually unprocessed and get refit on every future run forever.
    # Confirmed live 2026-11-05 while rebuilding full history under new
    # hyperparameters: several clubs' n_updates were inflated far past
    # their real match count purely from this, exposed hard by a tight
    # day-by-day replay loop but present (and silently worsening) in real
    # daily production too, for any team needing alias resolution.
    obs_by_league: dict[str, list[dict]] = {}
    pending = 0
    for o in all_obs:
        try:
            kickoff_date = datetime.fromisoformat(o["commence_time"]).date()
        except ValueError:
            continue
        if kickoff_date >= as_of:
            pending += 1
            continue
        obs_by_league.setdefault(o["league"], []).append(o)

    if not obs_by_league:
        print(f"No newly-kicked-off fixtures ready to incorporate as of {as_of_date} "
              f"({pending} captured but still pending kickoff).")
        return

    state = _load_state()

    newly_applied_keys: list[tuple] = []
    touched_this_run: dict[tuple[str, str], dict] = {}
    combined_with_source = None
    home_league_lookup: dict[str, str] = {}

    for league_name, obs in obs_by_league.items():
        if league_name in EUROPEAN_COMPETITIONS:
            if combined_with_source is None:
                combined_with_source = _load_tracked_ratings_with_source()
                home_league_lookup = dict(zip(combined_with_source["team"], combined_with_source["_home_league_id"]))
            raw_ratings_df = combined_with_source
            home_advantage = EUROPEAN_COMPETITIONS.get(league_name, {}).get("home_advantage", 1.20)
            team_league_id = home_league_lookup  # per-team lookup, home/away may differ
        else:
            cfg = LEAGUES.get(league_name) or LEAGUES_TIER2.get(league_name)
            if not cfg:
                continue
            league_id = str(cfg.get("tsdb_id", cfg["id"]))
            raw_ratings_df = load_ratings(cfg.get("tsdb_id", cfg["id"]), [], apply_adjustments=False)
            home_advantage = cfg.get("home_advantage", 1.20)
            team_league_id = {t: league_id for t in raw_ratings_df["team"]}  # every team here shares one league_id

        resolved_all = _resolve_observations(league_name, raw_ratings_df, obs)
        # Ledger membership check, now against RESOLVED (canonical) names
        # -- see the comment above obs_by_league's own construction.
        resolved = [
            o for o in resolved_all
            if (o["league"], o["home_team"], o["away_team"], o["commence_time"]) not in ledger
        ]
        if not resolved:
            continue

        touched = {t for o in resolved for t in (o["home_team"], o["away_team"])}
        # This league/competition's own (league_id, team)-scoped slice of
        # the persisted state -- see module docstring: a European-
        # competition batch can span many different home leagues at once,
        # so this is built per team, not per batch.
        current_ratings = {
            t: state[(team_league_id[t], t)]["rating"]
            for t in touched
            if t in team_league_id and (team_league_id[t], t) in state
        }

        updates = _fit_persistent(raw_ratings_df, home_advantage, resolved, current_ratings)
        if not updates:
            continue

        raw_lookup = dict(zip(raw_ratings_df["team"], raw_ratings_df["opta_rating"]))
        alias_lookup = dict(zip(raw_ratings_df["team"], raw_ratings_df["alias"].fillna("")))
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
            lid = team_league_id.get(t, f"EURO:{league_name}")  # unresolvable-to-any-domestic-roster fallback
            key = (lid, t)
            if key not in touched_this_run:
                prev = state.get(key)
                touched_this_run[key] = {
                    "alias": alias_lookup.get(t) or (prev["alias"] if prev else ""),
                    "seed": prev["seed"] if prev else float(raw_lookup.get(t, new_rating)),
                    "n_updates": prev["n_updates"] if prev else 0,
                    "last_updated": prev["last_updated"] if prev else "",
                }
            entry = touched_this_run[key]
            entry["rating"] = new_rating
            entry["n_updates"] += n_obs_by_team.get(t, 0)
            entry["last_updated"] = max(entry["last_updated"], last_date_by_team.get(t, ""))

        for o in resolved:
            newly_applied_keys.append((o["league"], o["home_team"], o["away_team"], o["commence_time"]))

    if not touched_this_run:
        print("No observations resolved to a tracked team this run.")
        return

    for key, entry in touched_this_run.items():
        state[key] = entry
    _save_state(state)
    _append_ledger(newly_applied_keys)

    print(f"Incorporated {len(newly_applied_keys)} newly-kicked-off fixtures, updating "
          f"{len(touched_this_run)} teams' persistent odds-implied rating ({pending} fixtures "
          f"still pending kickoff, left for a future run). {len(state)} (league, team) entries tracked in total.")
    top = sorted(touched_this_run.items(), key=lambda kv: -abs(kv[1]["rating"] - kv[1]["seed"]))[:20]
    for (lid, t), entry in top:
        drift = entry["rating"] - entry["seed"]
        sign = "+" if drift >= 0 else ""
        print(f"  [{lid}] {t:25s} {entry['rating']:6.2f}  (seed {entry['seed']:6.2f}, {sign}{drift:.2f}, n={entry['n_updates']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    main(args.date)
