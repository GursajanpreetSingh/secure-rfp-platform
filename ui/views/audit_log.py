import json

import streamlit as st

from ui import format as fmt
from ui import state
from ui.client import ApiError


def render() -> None:
    st.title("Audit log")
    st.caption("The most recent recorded events. The log can only be added to, never edited.")
    size = st.select_slider("How many", options=[25, 50, 100], value=50)
    try:
        rows = state.api().activity(size)
    except ApiError as problem:
        state.handle_expiry(problem)
        st.error(problem.message)
        return
    if not rows:
        st.caption("Nothing recorded yet.")
        return
    table = [
        {
            "When": fmt.short_time(row["occurred_at"]),
            "Who": row.get("user_email") or "",
            "Action": row["action"],
            "Decision": row["decision"],
            "Item": row.get("resource_type") or "",
            "Detail": json.dumps(row.get("detail") or {}, sort_keys=True)[:200],
        }
        for row in rows
    ]
    st.dataframe(table, hide_index=True, use_container_width=True)  # cells are plain text
