import streamlit as st

from ui import qa_parts, state
from ui.client import ApiError


def render() -> None:
    st.title("Public questions")
    st.info(
        "No account needed. You can ask about public documents only. "
        "Nothing you type here is saved."
    )
    # Only this tab's own memory of the questions, kept in the browser session. It is not stored.
    turns = st.session_state.setdefault("public_turns", [])
    if not turns:
        qa_parts.empty_state("Ask about our public documents. Nothing you type is saved.")
    for turn in turns:
        qa_parts.render_user(turn["question"])
        qa_parts.render_assistant(turn["status"], turn["text"], turn["sources"])
    question = qa_parts.next_question("Ask a question about public documents")
    if not question:
        return
    qa_parts.render_user(question)
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
