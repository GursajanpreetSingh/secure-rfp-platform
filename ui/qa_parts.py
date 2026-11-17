"""Pieces shared by the signed-in chat and the public Q&A page."""

import streamlit as st

from ui import format as fmt


def show_sources(sources: list[dict]) -> None:
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)})"):
        for source in sources:
            st.caption(fmt.source_line(source))
            st.text(source.get("quote") or "")  # plain text: never markdown or HTML


def show_answer(status: str, text: str, sources: list[dict]) -> None:
    st.text(text)
    if status == "no_answer":
        st.caption("Nothing in the documents you can see answers this.")
    elif status == "error":
        st.caption("The assistant could not answer this time. Please try again.")
    show_sources(sources)
