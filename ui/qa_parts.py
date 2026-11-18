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
    if status == "no_answer":
        st.info(
            "I could not find this in the documents available to you.  \n"
            "Try naming the document or topic, or ask about one specific fact."
        )
        return
    if status == "error":
        st.warning("The assistant could not answer this time. Please try again.")
        return
    st.markdown(fmt.answer_markdown(text))  # every piece is escaped first
    if sources:
        st.caption(f"Based on {len(sources)} passage{'s' if len(sources) != 1 else ''}")
    show_sources(sources)
