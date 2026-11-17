"""What the app remembers for one browser session. The sign-in token lives only in the
server-side session, never in the page address, and is dropped on sign-out or expiry."""

import streamlit as st

from ui.client import ApiClient, ApiError

STAFF_ROLES = {"employee", "executive"}  # the roles the API allows to run RFPs


def api() -> ApiClient:
    if "api" not in st.session_state:
        st.session_state.api = ApiClient()
    return st.session_state.api


def user() -> dict | None:
    return st.session_state.get("user")


def is_signed_in() -> bool:
    return user() is not None


def can_run_rfps() -> bool:
    current = user()
    return bool(current) and current["role"] in STAFF_ROLES


def sign_in(token: str) -> None:
    """Remember the token and who it belongs to. Raises ApiError if it does not work."""
    client = api()
    client.token = token
    try:
        st.session_state.user = client.me()
    except ApiError:
        client.token = None
        raise


def sign_out() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def handle_expiry(error: ApiError) -> None:
    """If the session ran out, go back to the sign-in page. Otherwise do nothing."""
    if error.expired:
        sign_out()
        st.rerun()
