"""Run with:  uv run streamlit run ui/app.py   (the API must be running too)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from ui import state, theme  # noqa: E402
from ui.views import (  # noqa: E402
    audit_log,
    home,
    login,
    qa_chat,
    qa_public,
    rfp_dashboard,
    rfp_review,
)

st.set_page_config(page_title="RFP AI Agent", page_icon="🛡️", layout="wide")
theme.apply()


def navigation(pages):
    try:
        return st.navigation(pages, position="hidden" if len(pages) == 1 else "sidebar")
    except TypeError:  # older Streamlit without the position option
        return st.navigation(pages)


if not state.is_signed_in():
    page = navigation(
        [
            st.Page(login.render, title="Sign in", url_path="sign-in", default=True),
            st.Page(qa_public.render, title="Public questions", icon="💬", url_path="public"),
        ]
    )
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
    pages["chat"] = st.Page(qa_chat.render, title="Question answering", icon="💬", url_path="chat")
    if state.can_run_rfps():
        pages["dashboard"] = st.Page(
            rfp_dashboard.render, title="RFP dashboard", icon="📊", url_path="rfp"
        )
        pages["review"] = st.Page(
            rfp_review.render, title="Review answers", icon="✅", url_path="review"
        )
    if current["role"] == "auditor":
        pages["audit"] = st.Page(audit_log.render, title="Audit log", icon="📜", url_path="audit")
    st.session_state.pages = pages  # screens use this to move to another page
    page = navigation(list(pages.values()))

page.run()
