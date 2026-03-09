"""
Shared authentication utilities.

Loads auth.yaml, creates the streamlit-authenticator instance, and
provides helpers for role checking used across all pages.
"""

import yaml
import streamlit as st
import streamlit_authenticator as stauth

AUTH_YAML = "auth.yaml"


def load_authenticator():
    """Load auth config and return (authenticator, config_dict).

    Tries auth.yaml on disk first (local dev).
    Falls back to st.secrets["AUTH_YAML_CONTENT"] (Streamlit Cloud).
    """
    try:
        with open(AUTH_YAML, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raw = st.secrets["AUTH_YAML_CONTENT"]
        config = yaml.safe_load(raw)

    auth = stauth.Authenticate(
        credentials=config["credentials"],
        cookie_name=config["cookie"]["name"],
        cookie_key=config["cookie"]["key"],
        cookie_expiry_days=config["cookie"]["expiry_days"],
    )
    return auth, config


def get_role(config: dict, username: str) -> str:
    """Return the role ('admin' or 'user') for the given username."""
    return config["credentials"]["usernames"].get(username, {}).get("role", "user")


def require_login(authenticator, location: str = "main"):
    """
    Render login form and stop execution if the user is not authenticated.
    Returns (username, role_is_admin) when authenticated.
    """
    authenticator.login(location=location)
    status = st.session_state.get("authentication_status")
    username = st.session_state.get("username", "")

    if status is False:
        st.error("Incorrect username or password.")
        st.stop()
    if not status:
        st.stop()

    return username
