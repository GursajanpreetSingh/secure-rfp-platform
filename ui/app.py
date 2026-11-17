"""Run with:  uv run streamlit run ui/app.py   (the API must be running too)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from ui import state, theme  # noqa: E402
from ui.views import home, login, rfp_dashboard, rfp_review  # noqa: E402

st.set_page_config(page_title="RFP AI Agent", page_icon="🛡️", layout="wide")
theme.apply()


def navigation(pages):
    try:
        return st.navigation(pages, position="hidden" if len(pages) == 1 else "sidebar")
    except TypeError:  # older Streamlit without the position option
        return st.navigation(pages)


if not state.is_signed_in():
    page = navigation([st.Page(login.render, title="Sign in", url_path="sign-in", default=True)])
else:
    with st.sidebar:
        theme.brand()
        current = state.user()
        st.caption(f"{current['full_name']}\n\n{current['email']}")
        if st.button("Sign out", use_container_width=True):
            state.sign_out()
            st.rerun()
    pages = {
        "home": st.Page(home.render, title="Home", icon="🏠", url_path="home", default=True),
    }
    if state.can_run_rfps():
        pages["dashboard"] = st.Page(
            rfp_dashboard.render, title="RFP dashboard", icon="📊", url_path="rfp"
        )
        pages["review"] = st.Page(
            rfp_review.render, title="Review answers", icon="✅", url_path="review"
        )
    st.session_state.pages = pages  # screens use this to move to another page
    page = navigation(list(pages.values()))

page.run()
