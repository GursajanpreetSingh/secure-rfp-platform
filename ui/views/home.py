import streamlit as st

from ui import state


def render() -> None:
    current = state.user()
    st.title(f"Welcome, {current['full_name'].split()[0]}")
    st.markdown(
        f'<span class="chip">{current["role"]}</span>', unsafe_allow_html=True
    )  # role names come from a fixed list on the server
    st.write("What would you like to do?")

    rfp, qa = st.columns(2)
    with rfp:
        with st.container(border=True):
            st.subheader("RFP compliance")
            st.write(
                "Upload an RFP, see how well your own documents meet each requirement, "
                "review the answers and export the result."
            )
            if state.can_run_rfps():
                if st.button("Open the RFP dashboard", type="primary"):
                    st.switch_page(st.session_state.pages["dashboard"])
            else:
                st.info("Your account type cannot run RFPs. Ask an administrator for staff access.")
    with qa:
        with st.container(border=True):
            st.subheader("Question answering")
            st.write(
                "Ask questions about the documents you are allowed to see. "
                "Your chats are saved, and every answer shows its sources."
            )
            if st.button("Open the chat", type="primary", key="open_chat"):
                st.switch_page(st.session_state.pages["chat"])
