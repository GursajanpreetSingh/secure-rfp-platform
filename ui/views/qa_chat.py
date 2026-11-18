import streamlit as st

from ui import qa_parts, state
from ui.client import ApiError


def _call(action, *args):
    try:
        return action(*args)
    except ApiError as problem:
        state.handle_expiry(problem)
        st.error(problem.message)
        return None


def _sidebar(current: str | None) -> None:
    st.markdown("**Your chats**")
    if st.button("➕ New chat", use_container_width=True, type="primary"):
        st.session_state.conversation_id = None
        st.rerun()
    chats = _call(state.api().conversations) or []
    if not chats:
        st.caption("No saved chats yet.")
    for chat in chats[:30]:
        open_col, delete_col = st.columns([5, 1])
        title = chat["title"] or "Untitled"
        if open_col.button(
            title[:40],
            key=f"open_{chat['id']}",
            use_container_width=True,
            disabled=chat["id"] == current,
        ):
            st.session_state.conversation_id = chat["id"]
            st.rerun()
        if delete_col.button("\U0001f5d1", key=f"del_{chat['id']}", help="Delete this chat"):
            _call(state.api().delete_conversation, chat["id"])
            if chat["id"] == current:
                st.session_state.conversation_id = None
            st.rerun()


def _history(conversation_id: str | None) -> None:
    if not conversation_id:
        qa_parts.empty_state(
            "Answers come only from documents you are allowed to see, and every answer "
            "shows where it came from."
        )
        return
    messages = _call(state.api().messages, conversation_id)
    if messages is None:
        st.session_state.conversation_id = None
        return
    for message in messages:
        if message["role"] == "user":
            qa_parts.render_user(message["content"])
        else:
            qa_parts.render_assistant(
                message["status"],
                message["content"],
                message["citations"],
                bool(message.get("redacted")),
            )


def render() -> None:
    st.title("Question answering")
    side, main = st.columns([1, 3])
    current = st.session_state.get("conversation_id")
    with side:
        _sidebar(current)
    with main:
        _history(current)
        question = qa_parts.next_question("Ask a question about your documents")
        if question:
            qa_parts.render_user(question)
            with st.spinner("Looking through your documents..."):
                reply = _call(state.api().ask, question, current)
            if reply is not None:
                st.session_state.conversation_id = reply["conversation_id"]
                st.rerun()
