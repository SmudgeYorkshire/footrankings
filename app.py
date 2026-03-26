"""
Entrypoint — handles authentication and page routing only.
All page content lives in football_rankings.py and admin.py.
"""

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import streamlit.components.v1 as components
from _auth import load_authenticator, get_role

st.set_page_config(
    page_title="Football Rankings – Statistics & Projections",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
/* Compact data tables */
[data-testid="stDataFrame"] { font-size: 13px; }

/* ── Mobile optimisations ───────────────────────────────────────────────── */
@media (max-width: 768px) {

    /* Hide Streamlit sidebar toggle padding / extra space */
    .block-container { padding: 0.5rem 0.75rem 2rem !important; }

    /* Make metric cards stack nicely */
    [data-testid="stMetric"] { min-width: 120px; }

    /* Make dataframes scroll horizontally instead of overflowing */
    [data-testid="stDataFrame"] { overflow-x: auto !important; font-size: 11px; }

    /* Full-width tables on mobile */
    [data-testid="stDataFrame"] > div { width: 100% !important; }

    /* Tabs: smaller font so all tabs fit on one line */
    [data-testid="stTabs"] button { font-size: 11px !important; padding: 4px 6px !important; }

    /* Sidebar narrower on mobile */
    [data-testid="stSidebar"] { min-width: 200px !important; }

    /* League header image smaller on mobile */
    [data-testid="stImage"] img { max-width: 48px !important; }

    /* Format tab group boxes — full width on mobile */
    .format-group-box { width: 100% !important; margin-bottom: 8px; }
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
authenticator, auth_config = load_authenticator()
authenticator.login(location="main")

status = st.session_state.get("authentication_status")
if status is False:
    st.error("Incorrect username or password.")
    st.stop()
if not status:
    st.stop()

username = st.session_state.get("username", "")
is_admin = get_role(auth_config, username) == "admin"

# ---------------------------------------------------------------------------
# Logout in sidebar (appears above the page navigation)
# ---------------------------------------------------------------------------
st.session_state["_authenticator"] = authenticator

# ---------------------------------------------------------------------------
# Global header
# ---------------------------------------------------------------------------
st.markdown(
    "<h2 style='margin:0'>⚽ Football Rankings "
    "<span style='font-weight:400; color:#555'>— Statistics &amp; Projections</span></h2>",
    unsafe_allow_html=True,
)
st.divider()

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
pages = [
    st.Page("football_rankings.py", title="European Leagues",       icon="⚽"),
    st.Page("european.py",          title="European Competitions",  icon="🏆"),
    st.Page("world_cup_page.py",    title="2026 World Cup",         icon="🌍"),
]
if is_admin:
    pages.append(st.Page("admin.py", title="Admin", icon="🔒"))

pg = st.navigation(pages)
pg.run()
