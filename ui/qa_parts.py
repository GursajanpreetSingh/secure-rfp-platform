"""Pieces shared by the signed-in chat and the public Q&A page."""

import streamlit as st

from ui import format as fmt
from ui import htmlkit


def show_sources(sources: list[dict]) -> None:
    """The exact quotes, for anyone who wants to check an answer. Plain text only."""
    if not sources:
        return
    with st.expander(f"Quotes behind this answer ({len(sources)})"):
        for source in sources:
            st.caption(fmt.source_line(source))
            st.text(source.get("quote") or "")


def render_user(text: str) -> None:
    st.markdown(htmlkit.user_bubble(text), unsafe_allow_html=True)  # text is escaped inside


def render_assistant(status: str, text: str, sources: list[dict], redacted: bool = False) -> None:
    st.markdown(  # text is escaped inside
        htmlkit.assistant_message(status, text, sources, redacted), unsafe_allow_html=True
    )
    if status == "answered":
        show_sources(sources)


def empty_state(intro: str) -> None:
    """A welcome card with example questions. Returns nothing; a click stores the question."""
    st.markdown(
        '<div class="empty-hero"><div class="empty-title">Ask your documents</div>'
        f'<div class="empty-sub">{htmlkit.esc(intro)}</div></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(htmlkit.EXAMPLES))
    for index, (col, example) in enumerate(zip(cols, htmlkit.EXAMPLES, strict=True)):
        if col.button(example, key=f"example_{index}", use_container_width=True):
            st.session_state.pending_question = example
            st.rerun()


def next_question(prompt: str) -> str | None:
    """What was typed in the box, or an example that was just clicked."""
    typed = st.chat_input(prompt)
    return typed or st.session_state.pop("pending_question", None)
