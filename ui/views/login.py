import streamlit as st

from ui import state, theme
from ui.client import ApiError


def _finish(action) -> None:
    try:
        state.sign_in(action())
    except ApiError as problem:
        st.error(problem.message)
        return
    st.rerun()


def render() -> None:
    left, middle, right = st.columns([1, 1.4, 1])
    with middle:
        theme.brand()
        st.write("")
        sign_in_tab, create_tab = st.tabs(["Sign in", "Create account"])

        with sign_in_tab:
            with st.form("sign_in"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                go = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if go:
                if not email.strip() or not password:
                    st.error("Enter your email and password.")
                else:
                    _finish(lambda: state.api().login(email.strip(), password))

        with create_tab:
            st.caption(
                "A new account can ask questions about public documents. "
                "Running RFPs is limited to staff accounts set up by an administrator."
            )
            with st.form("create_account"):
                name = st.text_input("Full name")
                new_email = st.text_input("Email", key="new_email")
                new_password = st.text_input("Password (12 to 128 characters)", type="password")
                again = st.text_input("Repeat password", type="password")
                create = st.form_submit_button(
                    "Create account", type="primary", use_container_width=True
                )
            if create:
                if new_password != again:
                    st.error("The two passwords do not match.")
                elif not name.strip() or not new_email.strip():
                    st.error("Enter your name and email.")
                else:
                    _finish(
                        lambda: state.api().register(new_email.strip(), new_password, name.strip())
                    )
