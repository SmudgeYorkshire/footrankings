"""
Live — public page.

Rich match detail (events, lineups, team & player statistics) pulled
directly from API-Football for a couple of hand-picked matches, as a demo
of the live data available on the site.

Not auto-refreshing yet — reload the page for the latest snapshot.
"""

import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

# Hand-picked matches to showcase the live data available via API-Football.
_TRACKED_MATCHES = [
    {"label": "Sparta Rotterdam vs Feyenoord", "api_football_fixture_id": 1552122},
    {"label": "Zorya Luhansk vs Kryvbas",      "api_football_fixture_id": 1565444},
]

st.markdown("<h3 style='margin:0'>🔴 Live</h3>", unsafe_allow_html=True)
st.caption("Live match data pulled directly from API-Football.")
st.divider()


def _fetch_api_football(fixture_id: int) -> dict:
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": _API_FOOTBALL_KEY},
            params={"id": fixture_id}, timeout=10,
        )
        resp = r.json().get("response") or []
        return resp[0] if resp else {}
    except Exception as e:
        return {"_error": str(e)}


def _player_stats_df(team_block: dict) -> pd.DataFrame:
    rows = []
    for p in team_block.get("players", []):
        info = p["player"]
        stat = (p.get("statistics") or [{}])[0]
        games = stat.get("games") or {}
        goals = stat.get("goals") or {}
        passes = stat.get("passes") or {}
        tackles = stat.get("tackles") or {}
        duels = stat.get("duels") or {}
        cards = stat.get("cards") or {}
        rows.append({
            "#": games.get("number"),
            "Player": info.get("name"),
            "Pos": games.get("position"),
            "Min": games.get("minutes"),
            "Rating": games.get("rating"),
            "Goals": goals.get("total"),
            "Assists": goals.get("assists"),
            "Shots": (stat.get("shots") or {}).get("total"),
            "Passes": passes.get("total"),
            "Pass Acc%": passes.get("accuracy"),
            "Tackles": tackles.get("total"),
            "Duels Won": duels.get("won"),
            "Y": cards.get("yellow"),
            "R": cards.get("red"),
        })
    return pd.DataFrame(rows)


for match in _TRACKED_MATCHES:
    st.markdown(f"### ⚽ {match['label']}")

    fx = _fetch_api_football(match["api_football_fixture_id"])
    if fx.get("_error"):
        st.error(f"Error: {fx['_error']}")
    elif not fx:
        st.warning("No data returned.")
    else:
        teams = fx["teams"]
        goals = fx["goals"]
        fixture = fx["fixture"]
        status = fixture["status"]
        home_name, away_name = teams["home"]["name"], teams["away"]["name"]

        st.metric(
            label=f"{home_name} vs {away_name}",
            value=f"{goals.get('home') or 0} - {goals.get('away') or 0}",
        )
        extra_suffix = f"+{status['extra']}" if status.get("extra") else ""
        st.write(f"**Status:** {status.get('long') or '—'}  "
                 f"({status.get('elapsed') or '?'}{extra_suffix}')")
        st.write(f"**League:** {fx['league']['name']} (round {fx['league'].get('round') or '—'})")
        venue = fixture.get("venue") or {}
        st.write(f"**Venue:** {venue.get('name') or '—'}, {venue.get('city') or '—'}")
        st.write(f"**Kickoff:** {fixture.get('date') or '—'}")
        st.write(f"**Referee:** {fixture.get('referee') or '—'}")

        score = fx.get("score", {})
        ht = score.get("halftime") or {}
        ft = score.get("fulltime") or {}
        st.write(f"**Half-time:** {ht.get('home')} - {ht.get('away')}  "
                 f"&nbsp;&nbsp; **Full-time:** {ft.get('home') if ft.get('home') is not None else '—'} - "
                 f"{ft.get('away') if ft.get('away') is not None else '—'}")

        # Events timeline
        events = fx.get("events") or []
        if events:
            st.markdown("**Events**")
            ev_rows = [{
                "Min": f"{e['time']['elapsed']}{'+' + str(e['time']['extra']) if e['time'].get('extra') else ''}",
                "Team": e["team"]["name"],
                "Player": (e.get("player") or {}).get("name"),
                "Type": e.get("type"),
                "Detail": e.get("detail"),
            } for e in events]
            st.dataframe(pd.DataFrame(ev_rows), hide_index=True, use_container_width=True)

        # Team statistics
        stats = fx.get("statistics") or []
        if stats and len(stats) == 2:
            st.markdown("**Match Statistics**")
            t0, t1 = stats[0], stats[1]
            types = [s["type"] for s in t0["statistics"]]
            stat_rows = []
            for i, t in enumerate(types):
                v0 = t0["statistics"][i]["value"]
                v1 = t1["statistics"][i]["value"]
                stat_rows.append({
                    t0["team"]["name"]: "—" if v0 is None else str(v0),
                    "Stat": t,
                    t1["team"]["name"]: "—" if v1 is None else str(v1),
                })
            df = pd.DataFrame(stat_rows)[[t0["team"]["name"], "Stat", t1["team"]["name"]]]
            st.dataframe(df, hide_index=True, use_container_width=True)

        # Lineups
        lineups = fx.get("lineups") or []
        if lineups:
            st.markdown("**Lineups**")
            for lu in lineups:
                with st.expander(f"{lu['team']['name']} — {lu['formation']} (coach: {(lu.get('coach') or {}).get('name') or '—'})"):
                    starters = ", ".join(
                        f"{p['player']['number']}. {p['player']['name']} ({p['player']['pos']})"
                        for p in lu.get("startXI", [])
                    )
                    subs = ", ".join(
                        f"{p['player']['number']}. {p['player']['name']} ({p['player']['pos']})"
                        for p in lu.get("substitutes", [])
                    )
                    st.write(f"**Starting XI:** {starters or '—'}")
                    st.write(f"**Substitutes:** {subs or '—'}")

        # Player statistics
        players = fx.get("players") or []
        if players:
            st.markdown("**Player Statistics**")
            for team_block in players:
                with st.expander(f"{team_block['team']['name']} — player stats"):
                    df = _player_stats_df(team_block)
                    st.dataframe(df, hide_index=True, use_container_width=True)

        with st.expander("Full raw response"):
            st.json(fx)

    st.divider()
