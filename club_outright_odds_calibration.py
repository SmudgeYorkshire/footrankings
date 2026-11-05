"""
Periodic, MANUALLY-run nudge: compares this site's own simulated "win the
whole thing" probability (for the European competitions) or "win the
title" probability (for domestic leagues) -- run ONCE under CURRENT
ratings -- against manual_outright_odds.py's real, de-vigged outright
market odds, and applies a single PERSISTENT nudge per priced club to
club_odds_ratings.py's own state (ratings/club_odds_implied_ratings.csv).

Same shape nl_odds_calibration.py's own apply_outright_adjustments()
already uses for Nations League: run the full competition/season
simulation once (not inside a fitting loop -- a many-thousand-sim Monte
Carlo is far too slow to re-run every gradient step), read off the
model's own win probability, compare to the market's, apply one direct
nudge. Unlike the match-level fit in club_odds_ratings.py's own main(),
this isn't ledger-tracked or idempotent -- re-running with the SAME
(unrefreshed) manual_outright_odds.py data applies the same nudge again,
compounding it. Same accepted limitation nl_odds_calibration.py's own
OBSERVATIONS-based workflow already has; the intended usage is "refresh
manual_outright_odds.py, then run this," not blind re-runs.

Only touches clubs actually priced in manual_outright_odds.OUTRIGHT_ODDS
-- every other club's persistent rating is completely untouched. The
de-vig is computed across only the entered observations for that
competition/league (manual_outright_odds.devig_outright), so priced clubs
are compared against EACH OTHER's share of that probability mass, not
against the full field.

n_updates is deliberately NOT incremented by this nudge -- it's a
different evidence class than a real match-level observation, and
build_club_power_rankings.N_FULL_CONFIDENCE's own confidence formula is
calibrated against match-level counts specifically. This only moves
`rating`.

Not part of the daily automated workflow -- running a full 30,000-sim
simulation per priced competition/league is too slow for that, and the
input data (manual_outright_odds.py) only changes when manually refreshed
anyway. Run this manually, right after refreshing that file.

Usage: py club_outright_odds_calibration.py
"""

import os
import sys
from pathlib import Path

# Windows' console defaults to cp1252, which can't encode every character
# a club name might contain (confirmed live 2026-11-05: a Turkish club
# name crashed this script's own progress printing partway through a run
# -- after the League Phase simulation had already run but BEFORE main()'s
# single _save_state(state) call at the very end, so the exception lost
# every nudge computed in that run, not just the one that failed to
# print). Guarded since sys.stdout isn't guaranteed to be a reconfigurable
# TextIOWrapper in every environment this could run in.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from config import LEAGUES, LEAGUES_TIER2, EUROPEAN_COMPETITIONS, get_current_season
from coefficients_baseline import COUNTRY_NAME_FIXUP
from update_ratings_from_opta import fuzzy_token_match
from api_football_fetcher import ApiFootballClient
from club_coefficients import get_coeff
from club_odds_ratings import (
    _load_state, _save_state, blend_with_live_rating,
    RATING_SANITY_MIN, RATING_SANITY_MAX,
)
from league_phase_simulator import simulate_competition_winner
from simulator import simulate_season, build_live_odds_lambda_overrides
from qualifying_projection import (
    _project_league_phase_field, _load_combined_ratings, _resolve_field_ratings,
    real_league_phase_results, resolve_to_team,
)
from league_phase_fixtures import is_opponent_list_complete, derive_fixtures
from ratings_manager import load_ratings, load_club_rating_adjustments
from manual_outright_odds import OUTRIGHT_ODDS, devig_outright

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")

# Provisional -- see module docstring. ~20x nl_odds_calibration.py's own
# match-vs-outright learning-rate ratio (300/15), applied to this site's
# own match-level LEARNING_RATE=1.2 (club_odds_ratings.py).
OUTRIGHT_LEARNING_RATE = 24.0

# Mirrors european.py's own _LEAGUE_PHASE_POTS -- duplicated rather than
# imported, since european.py is a Streamlit PAGE (importing it would run
# its top-level UI setup code outside a real Streamlit session).
_LEAGUE_PHASE_POTS = {"Champions League": (4, 2), "Europa League": (4, 2), "Conference League": (6, 1)}

N_SIM = 30_000


def apply_outright_nudge(
    state: dict, key: tuple[str, str], raw_rating: float, alias: str,
    model_prob: float, market_prob: float,
) -> float:
    """Applies one persistent, capped nudge to state[key] (seeding from
    the club's current persisted rating if it has one, else raw_rating --
    same "seed from current, fall back to raw" pattern _fit_persistent
    already uses). Returns the delta actually applied (post-clamp), for
    logging. Does NOT touch n_updates -- see module docstring."""
    current = state.get(key)
    current_rating = current["rating"] if current else raw_rating
    error = market_prob - model_prob
    new_rating = max(RATING_SANITY_MIN, min(RATING_SANITY_MAX, current_rating + OUTRIGHT_LEARNING_RATE * error))
    state[key] = {
        "alias": current["alias"] if current else (alias or ""),
        "rating": new_rating,
        "seed": current["seed"] if current else raw_rating,
        "n_updates": current["n_updates"] if current else 0,
        "last_updated": current["last_updated"] if current else "",
    }
    return new_rating - current_rating


def _resolve_field_league_ids(field: list[dict]) -> dict[str, tuple[str, str]]:
    """{field_team: (league_id, canonical_team)} for just THIS field's
    clubs, resolved per club by (team, country) and checked against BOTH
    the "team" and "alias" columns of each country-matching league's
    ratings CSV. canonical_team is that CSV's own "team" column value --
    the exact name ratings_manager.load_ratings()/club_odds_ratings.
    blend_with_live_rating() key the live persistent state by -- which is
    NOT always the same string as field_team (see below).

    NOT a flat bare-team-name dict keyed only by the "team" column (an
    earlier version of this used club_odds_ratings._load_tracked_
    ratings_with_source()'s own such dict directly) -- confirmed live
    2026-11-04 that this has TWO real failure modes: (1) a same-named
    club in a DIFFERENT country silently wins the dict collision (e.g.
    England's vs Belarus's "Arsenal" -- an outright nudge meant for
    English Arsenal landed on Belarusian Arsenal Dzerzhinsk instead,
    moving an unrelated minor club's rating), and (2) a club whose field
    name is the ratings CSV's ALIAS rather than its "team" column (e.g.
    field's "Olympiacos" vs ratings/4336.csv's team="Olympiakos Piraeus",
    alias="Olympiacos" -- the exact same root cause as the real-results
    name-resolution bug fixed earlier this session) isn't found at all
    and silently falls back to the generic "EURO:{comp_name}" bucket
    instead of its real, already-accumulating domestic entry. Checking
    both columns, scoped to the field club's own (hand-verified or
    already-disambiguated, see qualifying_projection._project_league_
    phase_field's own docstring) country, fixes both at once.

    A THIRD failure mode, caught live 2026-11-05 (confirmed by comparing
    this file's own git history for ratings/club_odds_implied_ratings.csv
    across commits): returning only league_id (not also the canonical
    name) let the caller key its nudge by field_team whenever that
    differed from the CSV's own "team" column -- e.g. field's "Bayern
    Munich"/"Inter Milan"/"Atlético Madrid" vs the CSV's own "Bayern
    München"/"Inter"/"Atlético de Madrid". The league_id resolved
    correctly either way, but the nudge landed on a brand new, never-
    read orphan state entry instead of the real one -- confirmed live:
    34 clubs' entire 2026-11-04 outright-odds correction silently had
    zero effect on any live prediction. Returning canonical_team too
    lets the caller key its nudge the same way the rest of the site
    reads this state, closing that gap."""
    result: dict[str, tuple[str, str]] = {}
    all_cfgs = list(LEAGUES.items()) + list(LEAGUES_TIER2.items())
    for f in field:
        team, country = f["team"], f["country"]
        if team in result:
            continue
        for _league_name, cfg in all_cfgs:
            cfg_country = COUNTRY_NAME_FIXUP.get(cfg.get("country", ""), cfg.get("country", ""))
            if cfg_country != country:
                continue
            league_id = str(cfg.get("tsdb_id", cfg["id"]))
            csv_path = Path("ratings") / f"{league_id}.csv"
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path, dtype=str)
            if "team" not in df.columns:
                continue
            names = set(df["team"].dropna())
            alias_to_team = {}
            if "alias" in df.columns:
                for _, row in df.iterrows():
                    alias = str(row.get("alias", "")).strip()
                    if alias:
                        alias_to_team[alias] = row["team"]
                names |= set(alias_to_team)
            if team in names:
                canonical = alias_to_team.get(team, team)
                result[team] = (league_id, canonical)
                break
            # Fuzzy tier (e.g. field's "Inter Milan" vs ratings' team=
            # "Internazionale"/alias="Inter", or "Atlético Madrid" vs
            # team="Atlético de Madrid"/alias="Atletico Madrid" -- none
            # an exact match, but a safe token-subset relationship).
            # Only run within this ONE country's own small roster, the
            # same scale fuzzy_token_match's own docstring already
            # documents as safe.
            fuzzy_match = fuzzy_token_match(team, names)
            if fuzzy_match:
                canonical = alias_to_team.get(fuzzy_match, fuzzy_match)
                result[team] = (league_id, canonical)
                break
    return result


def calibrate_european_competition(comp_name: str, state: dict) -> None:
    outright = OUTRIGHT_ODDS.get(comp_name)
    if not outright or not outright.get("odds"):
        return

    ratings_df = _load_combined_ratings()
    field = _project_league_phase_field(comp_name, ratings_df)
    if len(field) < 36:
        print(f"[{comp_name}] only {len(field)}/36 League Phase clubs known yet -- skipping")
        return

    # _resolve_field_ratings already returns each club's live CURRENT rating
    # (Opta + daily nudge + the persistent Odds-Implied confidence-weighted
    # blend, via _load_ratings_by_country -- see club_odds_ratings.
    # blend_with_live_rating) -- no separate override needed here. Used to
    # hand-roll a full (unweighted) override with state[...]["rating"]
    # before that blend existed; after 2026-11-05's live-blend rollout it
    # would have overridden the correct confidence-weighted number with an
    # all-or-nothing one, undoing exactly the thing that blend was built to
    # do -- removed instead of layering a second blend on top, which would
    # double-apply the weighting and distort it.
    field_ratings_df = _resolve_field_ratings(field)
    home_league_lookup = _resolve_field_league_ids(field)
    raw_lookup = dict(zip(field_ratings_df["team"], field_ratings_df["opta_rating"]))
    alias_lookup = dict(zip(field_ratings_df["team"], field_ratings_df["alias"].fillna("")))

    cfg = EUROPEAN_COMPETITIONS[comp_name]
    home_advantage = cfg["home_advantage"]
    n_pots, opp_per_pot = _LEAGUE_PHASE_POTS[comp_name]
    club_coeff = {f["team"]: get_coeff(f["team"], f["country"]) for f in field}
    field_teams = [f["team"] for f in field]

    real_schedule_ready = is_opponent_list_complete(comp_name, field_teams)
    real_schedule = derive_fixtures(comp_name) if real_schedule_ready else None
    real_results = {}
    if real_schedule_ready:
        real_results, unresolved = real_league_phase_results(comp_name, _API_KEY, field_teams)
        if unresolved:
            print(f"[{comp_name}] WARNING: {len(unresolved)} real result(s) unresolved: {unresolved}")

    _live_odds_overrides = (
        build_live_odds_lambda_overrides(
            real_schedule, field_ratings_df, home_advantage, comp_name,
            exclude=set(real_results.keys()) if real_results else None,
        ) if real_schedule else {}
    )
    print(f"[{comp_name}] running {N_SIM:,}-sim League Phase simulation...")
    result = simulate_competition_winner(
        field=field, club_coeff=club_coeff, ratings_df=field_ratings_df,
        n_pots=n_pots, opponents_per_pot=opp_per_pot, n_sim=N_SIM,
        home_advantage=home_advantage, comp_name=comp_name,
        schedule=real_schedule, real_results=real_results,
        live_odds_lambda_overrides=_live_odds_overrides,
    )

    devigged = devig_outright(outright["odds"])
    for raw_name, market_prob in devigged.items():
        matched = resolve_to_team(raw_name, field_teams)
        if matched is None or matched not in result.index:
            print(f"[{comp_name}] WARNING: couldn't match outright entry {raw_name!r} to a field club")
            continue
        lid, canonical_team = home_league_lookup.get(matched, (f"EURO:{comp_name}", matched))
        model_prob = float(result.loc[matched, "won_competition"])
        delta = apply_outright_nudge(
            state, (lid, canonical_team), raw_lookup.get(matched, 75.0), alias_lookup.get(matched, ""),
            model_prob, market_prob,
        )
        sign = "+" if delta >= 0 else ""
        print(f"  {matched:25s} model={model_prob*100:6.2f}%  market={market_prob*100:6.2f}%  {sign}{delta:.2f}")


def calibrate_domestic_league(league_name: str, state: dict) -> None:
    outright = OUTRIGHT_ODDS.get(league_name)
    if not outright or not outright.get("odds"):
        return

    cfg = LEAGUES.get(league_name) or LEAGUES_TIER2.get(league_name)
    if not cfg:
        print(f"[{league_name}] not a tracked league -- skipping")
        return
    if cfg.get("split_round"):
        print(f"[{league_name}] split-season league, title logic not supported here -- skipping")
        return

    af_id = cfg["id"]
    ratings_id = cfg.get("tsdb_id", cfg["id"])
    league_id = str(ratings_id)
    season = cfg.get("af_season") or get_current_season(cfg["season_type"])
    home_advantage = cfg.get("home_advantage", 1.20)

    client = ApiFootballClient(api_key=_API_KEY)
    standings = client.get_standings(af_id, season)
    if not standings:
        print(f"[{league_name}] no standings available -- skipping")
        return
    played, remaining = client.get_fixtures(af_id, season)

    # apply_adjustments=False -- need the pre-blend raw+nudge base below to
    # hand to blend_with_live_rating ourselves, using the in-memory `state`
    # (not apply_adjustments=True's own fresh disk read, which would miss
    # any nudge main() already applied to a European competition earlier
    # in THIS run -- e.g. a club priced in both a European outright market
    # and its own domestic title odds).
    ratings_df = load_ratings(ratings_id, standings, apply_adjustments=False)
    alias_lookup = dict(zip(ratings_df["team"], ratings_df["alias"].fillna("")))
    adjustments = load_club_rating_adjustments()

    def _current_rating(team: str, raw: float) -> float:
        base = raw + adjustments.get(team, adjustments.get(alias_lookup.get(team, ""), 0.0))
        return blend_with_live_rating(league_id, team, base, state)

    ratings_df = ratings_df.copy()
    ratings_df["opta_rating"] = ratings_df.apply(lambda r: _current_rating(r["team"], r["opta_rating"]), axis=1)
    raw_lookup = dict(zip(ratings_df["team"], ratings_df["opta_rating"]))
    field_teams = list(ratings_df["team"])

    _live_odds_overrides = build_live_odds_lambda_overrides(remaining, ratings_df, home_advantage, league_name)
    print(f"[{league_name}] running {N_SIM:,}-sim season simulation...")
    result = simulate_season(
        standings=standings, remaining_fixtures=remaining, ratings=ratings_df,
        n_sim=N_SIM, home_advantage=home_advantage, tiebreakers=cfg.get("tiebreakers"),
        played_fixtures=played, live_odds_lambda_overrides=_live_odds_overrides,
    )
    if result.empty or "1" not in result.columns:
        print(f"[{league_name}] simulation returned no usable result -- skipping")
        return

    devigged = devig_outright(outright["odds"])
    for raw_name, market_prob in devigged.items():
        matched = resolve_to_team(raw_name, field_teams)
        if matched is None or matched not in result.index:
            print(f"[{league_name}] WARNING: couldn't match outright entry {raw_name!r} to the table")
            continue
        model_prob = float(result.loc[matched, "1"])
        delta = apply_outright_nudge(
            state, (league_id, matched), raw_lookup.get(matched, 75.0), alias_lookup.get(matched, ""),
            model_prob, market_prob,
        )
        sign = "+" if delta >= 0 else ""
        print(f"  {matched:25s} model={model_prob*100:6.2f}%  market={market_prob*100:6.2f}%  {sign}{delta:.2f}")


def main() -> None:
    state = _load_state()
    for comp_name in EUROPEAN_COMPETITIONS:
        calibrate_european_competition(comp_name, state)
    for league_name in list(LEAGUES) + list(LEAGUES_TIER2):
        calibrate_domestic_league(league_name, state)
    _save_state(state)
    print("Done -- ratings/club_odds_implied_ratings.csv updated for every priced club above.")

    # Every live prediction page (domestic and European) reads this run's
    # state change immediately -- ratings_manager.load_ratings() and
    # qualifying_projection's own field-ratings loaders call club_odds_
    # ratings.blend_with_live_rating() fresh each time, no caching of the
    # state file itself. club_power_rankings_1000.csv is the one exception:
    # a static, pre-built display artifact (the Club Power Rankings page,
    # cup_predictions.py's cup-winner strength lookup) that only reflects
    # whatever it was last built against -- confirmed live 2026-11-05 as a
    # real, confusing gap (Man City's corrected rating showed up instantly
    # in the Champions League/domestic predictions but not there) until
    # rebuilt by hand. Rebuilding it automatically here, every run, closes
    # that gap for good instead of relying on someone remembering to run
    # build_club_power_rankings.py separately afterward.
    from build_club_power_rankings import main as rebuild_power_rankings
    print("\nRebuilding club_power_rankings_1000.csv so the Club Power Rankings "
          "page reflects today's nudge too...")
    rebuild_power_rankings()

    # Same standing data-integrity check the daily automated workflow runs
    # (report-only -- see ratings_sanity_check.run_checks's own docstring
    # for why) -- a manual nudge run writes to the exact same persistent
    # state, so it deserves the exact same safety net.
    from ratings_sanity_check import main as sanity_check
    print()
    sanity_check()


if __name__ == "__main__":
    main()
