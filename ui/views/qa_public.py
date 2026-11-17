import streamlit as st

from ui import qa_parts, state
from ui.client import ApiError


def render() -> None:
    st.title("Public questions")
    st.info(
        "No account needed. You can ask about public documents only. "
        "Nothing you type here is saved."
    )
    # Only this page's own memory of the questions, kept in the browser session. It is not stored.
    turns = st.session_state.setdefault("public_turns", [])
    for turn in turns:
        with st.chat_message("user"):
            st.text(turn["question"])
        with st.chat_message("assistant"):
            qa_parts.show_answer(turn["status"], turn["text"], turn["sources"])
    question = st.chat_input("Ask a question about public documents")
    if not question:
        return
    with st.chat_message("user"):
        st.text(question)
    with st.chat_message("assistant"):
        with st.spinner("Looking..."):
            try:
                reply = state.api().ask_public(question)
            except ApiError as problem:
                st.error(problem.message)
                return
    turns.append(
        {
            "question": question,
            "status": reply["status"],
            "text": reply["text"],
            "sources": reply["sources"],
        }
    )
    st.rerun()
