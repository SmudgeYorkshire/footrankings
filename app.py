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
    page_title="Football Rankings – European Football Statistics & Projections",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
/* Compact data tables — reduces row height via font-size */
[data-testid="stDataFrame"] {
    font-size: 13px;
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
    "<span style='font-weight:400; color:#555'>— European Football Statistics &amp; Projections</span></h2>",
    unsafe_allow_html=True,
)
st.divider()

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
pages = [
    st.Page("football_rankings.py", title="European Leagues",       icon="⚽"),
    st.Page("european.py",          title="European Competitions",  icon="🏆"),
]
if is_admin:
    pages.append(st.Page("admin.py", title="Admin", icon="🔒"))

pg = st.navigation(pages)
pg.run()
