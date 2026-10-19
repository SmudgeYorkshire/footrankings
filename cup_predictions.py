"""
Shared domestic-cup status/prediction helpers.

Split out from football_rankings.py (where these were originally built for
its live Cup Details tab) so european_2027_28.py can reuse the exact same
predicted-cup-winner logic for its Cup Winner access-list slots, without
importing football_rankings.py itself (a Streamlit page script whose whole
body runs on import -- see european_2027_28.py's own _current_standings
docstring for why that's avoided elsewhere on this page already).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from api_football_fetcher import ApiFootballClient
from simulator import fixture_odds
from qualifying_projection import _fuzzy_key

_STRENGTH_RANKING_PATH = "club_power_rankings_1000.csv"


@st.cache_data(ttl=3_600, show_spinner=False)
def _load_strength_ranking() -> dict[str, list[tuple[float, float]]]:
    """{team name: [(opta_rating_raw, rating_1000), ...]} from this site's
    own Club Power Ranking (build_club_power_rankings.py's output) -- the
    ranking cup-winner predictions are made from (2026-10-19), replacing
    the raw per-league opta_rating. That column is calibrated for the
    Poisson goals model (match simulation still uses it via fixture_odds
    below, unaffected by this), not as a general "how strong is this
    club" ranking, and could run above its nominal 0-100 ceiling for a
    club with a large odds-driven adjustment applied on top -- confirmed
    live 2026-10-19 (Arsenal showing "Opta 103.8").

    Restricted to tracked_league rows only (the ones
    build_club_power_rankings.resolve_tracked_leagues already matched to
    one of our actual tracked clubs) -- every caller here passes a
    ratings_df scoped to one tracked league, so untracked global-scrape
    noise can only ever cause wrong matches, never right ones. Even
    within that tracked subset, the SAME team name still legitimately
    recurs across different countries (confirmed live 2026-10-19: 3
    different tracked clubs are all literally named "Arsenal" -- England,
    Belarus, Montenegro), which is why this returns every candidate
    instead of collapsing them -- _strength_score picks the one whose own
    opta_rating_raw is closest to the specific row's opta_rating, the
    same anchor-to-known-rating disambiguation
    resolve_tracked_leagues itself already uses, rather than risking a
    flat dict silently keeping an arbitrary (likely unrelated) one.
    Falls back to an empty dict (every lookup then treated as unranked/
    lowest priority, rather than crashing) if the file hasn't been built yet."""
    if not Path(_STRENGTH_RANKING_PATH).exists():
        return {}
    df = pd.read_csv(_STRENGTH_RANKING_PATH)
    df = df[df["tracked_league"].notna() & (df["tracked_league"] != "")]
    out: dict[str, list[tuple[float, float]]] = {}
    for _, r in df.iterrows():
        out.setdefault(r["team"], []).append((r["opta_rating_raw"], r["rating_1000"]))
    return out


@st.cache_data(ttl=3_600, show_spinner=False)
def _load_strength_ranking_fuzzy() -> dict[str, list[tuple[float, float]]]:
    """Same shape and source as _load_strength_ranking, but keyed by
    _fuzzy_key (accent-folded, filler-token-dropped, e.g. "FC"/"AS"/"FK")
    instead of the exact team name -- a fallback tier for the several
    tracked clubs confirmed missing BOTH an exact name/alias match and an
    opta_scrape_alias (2026-10-19: Viktoria Plzeň vs the scrape's "Plzeň",
    Omonia Nicosia vs "Omonia", Bodø / Glimt vs "Bodø/Glimt", Crvena
    Zvezda vs "Crvena zvezda", FC Košice vs "Košice") -- the same class of
    name variance _fuzzy_key already exists to absorb elsewhere on the
    site (european.py's badge lookups, qualifying_projection's own
    fixture-team resolution), reused here rather than reinvented."""
    if not Path(_STRENGTH_RANKING_PATH).exists():
        return {}
    df = pd.read_csv(_STRENGTH_RANKING_PATH)
    df = df[df["tracked_league"].notna() & (df["tracked_league"] != "")]
    out: dict[str, list[tuple[float, float]]] = {}
    for _, r in df.iterrows():
        out.setdefault(_fuzzy_key(r["team"]), []).append((r["opta_rating_raw"], r["rating_1000"]))
    return out


def _strength_score(row, strength_map: dict[str, list[tuple[float, float]]]) -> float:
    """This club's Club Power Ranking score -- among same-named candidates,
    picks the one whose own opta_rating_raw is closest to this row's own
    opta_rating (see _load_strength_ranking's docstring for why a flat
    name match alone isn't safe). -1.0 for a club genuinely missing from
    the tracked subset, so it sorts last rather than winning a tie-break
    it has no real claim to.

    Checks row["opta_scrape_alias"] (when present) ALONGSIDE
    _team_name_set's team/alias -- confirmed as a real gap 2026-10-19:
    several clubs' global Opta Power Rankings scrape name doesn't match
    either their "team" or their API-Football "alias" at all (Bayern
    München/alias "Bayern Munich" vs the scrape's "FC Bayern"; Bayer
    Leverkusen vs "Bayer 04"; RB Leipzig vs "Leipzig"; ...), so without
    this they silently fell back to -1.0 (unranked) and lost every
    predicted-cup-winner tie-break to a weaker club whose name happened
    to match exactly -- confirmed live, Germany's DFB Pokal predicting
    Stuttgart over Bayern Munich."""
    own_opta = row.get("opta_rating")
    names = _team_name_set(row)
    _scrape_alias = str(row.get("opta_scrape_alias", "") or "").strip()
    if _scrape_alias:
        names = names | {_scrape_alias}
    best = None
    best_gap = None
    for name in names:
        for opta_raw, rating_1000 in strength_map.get(name, []):
            gap = abs(opta_raw - own_opta) if pd.notna(own_opta) else 0.0
            if best_gap is None or gap < best_gap:
                best_gap, best = gap, rating_1000
    if best is not None:
        return best
    # No exact team/alias/scrape_alias match -- last-resort fuzzy fallback
    # (accent-fold + filler-token-drop) before giving up. Confirmed as a
    # real remaining gap 2026-10-19 even after the scrape_alias fix above:
    # a handful of clubs have no opta_scrape_alias set at all AND their
    # team/alias spelling doesn't exactly match the scrape's either
    # (Viktoria Plzeň vs "Plzeň", Crvena Zvezda vs "Crvena zvezda", ...).
    fuzzy_map = _load_strength_ranking_fuzzy()
    for name in names:
        for opta_raw, rating_1000 in fuzzy_map.get(_fuzzy_key(name), []):
            gap = abs(opta_raw - own_opta) if pd.notna(own_opta) else 0.0
            if best_gap is None or gap < best_gap:
                best_gap, best = gap, rating_1000
    return best if best is not None else -1.0


def _cup_campaign_status(team_names: set[str], played: list[dict], remaining: list[dict]) -> dict:
    """One team's progress through a single cup season, derived purely from
    its own fixtures (played + remaining already fetched for the whole
    competition). Returns a dict with a "state" of:
      - "not_entered"  — no fixture at all yet (their round hasn't been
        drawn/published by the provider yet, common for top-flight sides
        that enter a cup many rounds after it starts)
      - "active"       — has an upcoming fixture
      - "awaiting_draw"— won/advanced their last match but the next round
        isn't drawn yet
      - "eliminated"   — lost (normal time, or on penalties) their last match
    "entry_round"/"entry_date" (when available) is their earliest fixture
    this season, i.e. the phase they entered the competition at.
    """
    def _involves(f):
        return f.get("strHomeTeam") in team_names or f.get("strAwayTeam") in team_names

    team_played = sorted((f for f in played if _involves(f)), key=lambda f: f.get("dateEvent", ""))
    team_remaining = sorted((f for f in remaining if _involves(f)), key=lambda f: f.get("dateEvent", ""))
    if not team_played and not team_remaining:
        return {"state": "not_entered"}

    entry_fx = sorted(team_played + team_remaining, key=lambda f: f.get("dateEvent", ""))[0]
    entry_round, entry_date = entry_fx.get("strRound", ""), entry_fx.get("dateEvent", "")

    if team_remaining:
        nxt = team_remaining[0]
        is_home = nxt.get("strHomeTeam") in team_names
        opponent = nxt.get("strAwayTeam") if is_home else nxt.get("strHomeTeam")
        return {
            "state": "active", "entry_round": entry_round, "entry_date": entry_date,
            "next_round": nxt.get("strRound", ""), "next_date": nxt.get("dateEvent", ""),
            "opponent": opponent, "is_home": is_home,
        }

    last = team_played[-1]
    is_home = last.get("strHomeTeam") in team_names
    hs, as_ = last.get("intHomeScore"), last.get("intAwayScore")
    team_score, opp_score = (hs, as_) if is_home else (as_, hs)
    lost = False
    if team_score is not None and opp_score is not None:
        if team_score < opp_score:
            lost = True
        elif team_score == opp_score:
            # Two-legged aggregate ties aren't reconstructed here (that would
            # need pairing up both legs) -- a single-match loss on penalties
            # is treated as elimination, which covers single-match knockout
            # rounds (the common case for the rounds this feature targets).
            ph, pa = last.get("intPenaltyHome"), last.get("intPenaltyAway")
            if ph is not None and pa is not None:
                team_pens, opp_pens = (ph, pa) if is_home else (pa, ph)
                lost = team_pens < opp_pens
    opponent = last.get("strAwayTeam") if is_home else last.get("strHomeTeam")
    if lost:
        return {
            "state": "eliminated", "entry_round": entry_round, "entry_date": entry_date,
            "round": last.get("strRound", ""), "date": last.get("dateEvent", ""),
            "opponent": opponent, "score": f"{hs}–{as_}",
        }
    return {
        "state": "awaiting_draw", "entry_round": entry_round, "entry_date": entry_date,
        "last_round": last.get("strRound", ""), "last_date": last.get("dateEvent", ""),
    }


def _team_name_set(row) -> set[str]:
    return {n for n in (str(row.get("team", "")).strip(), str(row.get("alias", "")).strip()) if n}


def resolve_predicted_cup_winner(ratings_df: pd.DataFrame, played: list[dict], remaining: list[dict],
                                  home_advantage: float = 1.0, neutral_final: bool = False,
                                  excluded_teams: set[str] | None = None):
    """Highest-ranked (by this site's own Club Power Ranking, not the raw
    per-league Opta rating -- see _load_strength_ranking/_strength_score)
    team in this league that hasn't already been knocked out of this
    season's cup AND isn't the underdog in its own next scheduled tie,
    plus any team ranked HIGHER than that predicted winner which has
    already been eliminated -- a genuine upset worth flagging, unlike an
    eliminated team that was never favoured over the winner in the first
    place. Returns
    (predicted_row, predicted_status, [(skipped_row, skipped_status), ...]),
    the third element sorted highest-ranked first.

    A team with a known upcoming fixture gets its actual prevail
    probability for that specific tie (home advantage + opponent
    strength, via the project's own Poisson model -- same one the
    Predictions tabs use, still based on opta_rating since that's the
    model it's calibrated for) attached to its status dict as
    "prevail_pct"; among non-eliminated teams, anyone currently an
    underdog in their own tie (prevail_pct < 0.5) is ranked below every
    team that isn't, with Club Power Ranking breaking ties within each
    group. A draw is split 50/50 toward either side advancing (most of
    these rounds are one-legged, decided by extra time/penalties if level
    -- a reasonable simplification rather than modelling penalty
    shoot-outs). A team with no scheduled fixture yet (next round not
    drawn) gets prevail_pct=None and is treated as not ruled out -- "keep
    it general" until there's something concrete to weight against.

    neutral_final: this cup's Final is played at a neutral venue (e.g. the
    FAI Cup, confirmed 2026-10-20), so whichever side the provider happens
    to list as "home" for that specific tie gets no home-advantage boost.

    excluded_teams: team/alias names to leave out of consideration entirely
    (not even as a "higher-rated, already eliminated" upset note) -- e.g. a
    club suspended from this season's cup for disciplinary/administrative
    reasons (North Macedonia: Shkendija, confirmed 2026-10-20) rather than
    having actually lost a tie."""
    strength_map = _load_strength_ranking()
    ranked = ratings_df.copy()
    if excluded_teams:
        ranked = ranked[~ranked.apply(lambda r: bool(_team_name_set(r) & excluded_teams), axis=1)]
    ranked["_strength"] = ranked.apply(lambda r: _strength_score(r, strength_map), axis=1)
    ranked = ranked.sort_values("_strength", ascending=False)
    skipped = []
    candidates = []
    for _, row in ranked.iterrows():
        status = _cup_campaign_status(_team_name_set(row), played, remaining)
        if status["state"] == "eliminated":
            skipped.append((row, status))
            continue
        candidates.append((row, status))

    if not candidates:
        # Everyone we track has been eliminated -- fall back to the top-rated
        # team anyway rather than showing nothing. They're the highest-rated
        # team full stop, so nothing else we track can be "higher-rated and
        # eliminated" relative to them -- the skipped list is necessarily empty.
        row = ranked.iloc[0]
        status = _cup_campaign_status(_team_name_set(row), played, remaining)
        return row, status, []

    _attach_prevail_pct(candidates, ratings_df, home_advantage, neutral_final=neutral_final)

    def _sort_key(item):
        _row, status = item
        p = status.get("prevail_pct")
        favoured = p is None or p >= 0.5
        return (0 if favoured else 1, -_strength_score(_row, strength_map))

    candidates.sort(key=_sort_key)
    predicted_row, predicted_status = candidates[0]
    # skipped was built by iterating every tracked team in rating order and
    # collecting every eliminated one along the way -- not just the ones
    # actually better-rated than wherever the predicted winner ended up
    # (which, since it also weighs each team's own next-tie prevail
    # chance, isn't always simply "the #1 team"). Confirmed as a real bug
    # 2026-10-13: a League Cup predicted-winner line was flagging 7 clubs
    # all rated BELOW the predicted winner as "higher-rated, already
    # eliminated" -- not an upset at all, just noise, since none of them
    # were ever better-rated than the team predicted to win.
    predicted_strength = _strength_score(predicted_row, strength_map)
    higher_rated_skipped = [
        (row, status) for row, status in skipped
        if _strength_score(row, strength_map) > predicted_strength
    ]
    return predicted_row, predicted_status, higher_rated_skipped


def _attach_prevail_pct(candidates: list[tuple], ratings_df: pd.DataFrame, home_advantage: float,
                         neutral_final: bool = False) -> None:
    """Mutates each status dict in `candidates` ([(row, status), ...]) with
    a "prevail_pct" key -- this team's probability of advancing past its
    *next known* tie, or None when no fixture is scheduled yet.

    neutral_final: zero out the home-advantage boost for a tie whose own
    "next_round" is literally "Final" -- the provider's home/away
    designation for a neutral-venue final doesn't reflect a real home
    ground, so neither side should get the usual boost."""
    fixtures, slots = [], []
    home_advantage_overrides: dict[tuple[str, str], float] = {}
    for i, (row, status) in enumerate(candidates):
        if status["state"] != "active":
            status["prevail_pct"] = None
            continue
        is_home = status["is_home"]
        home_team = row["team"] if is_home else status["opponent"]
        away_team = status["opponent"] if is_home else row["team"]
        fixtures.append({"strHomeTeam": home_team, "strAwayTeam": away_team})
        slots.append((i, is_home))
        if neutral_final and (status.get("next_round") or "").strip().lower() == "final":
            home_advantage_overrides[(home_team, away_team)] = 1.0

    if not fixtures:
        return
    odds = fixture_odds(fixtures, ratings_df, home_advantage=home_advantage,
                         home_advantage_overrides=home_advantage_overrides or None)
    for (i, is_home), o in zip(slots, odds):
        p = o["home_win"] + 0.5 * o["draw"] if is_home else o["away_win"] + 0.5 * o["draw"]
        candidates[i][1]["prevail_pct"] = p


@st.cache_data(ttl=3_600, show_spinner=False)
def fetch_cup_fixtures(cup_id, season, key):
    """Every fixture (played + remaining) for a cup's current season."""
    return ApiFootballClient(api_key=key).get_fixtures(cup_id, season)
