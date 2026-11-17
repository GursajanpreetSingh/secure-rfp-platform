import pandas as pd
import streamlit as st

from ui import format as fmt
from ui import state
from ui.client import ApiError


def _call(action, *args):
    """Run an API call. Show a plain message on failure and return None."""
    try:
        return action(*args)
    except ApiError as problem:
        state.handle_expiry(problem)
        st.error(problem.message)
        return None


def _kpi(column, label: str, value: str) -> None:
    with column:
        with st.container(border=True):
            st.markdown(f'<div class="kpi-label">{label}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="kpi-value">{value}</div>', unsafe_allow_html=True)


def _overview() -> None:
    data = _call(state.api().overview)
    if data is None:
        return
    rate = data["compliance_rate"]
    cols = st.columns(4)
    _kpi(cols[0], "RFP runs", str(data["runs_total"]))
    _kpi(cols[1], "Answers", str(data["answers_total"]))
    _kpi(cols[2], "Waiting for review", str(data["pending_review"]))
    _kpi(cols[3], "Compliant", "-" if rate is None else f"{rate}%")

    rows = fmt.chart_rows(data["status_counts"])
    with st.container(border=True):
        st.subheader("Answers by status")
        if rows:
            frame = pd.DataFrame({"Answers": list(rows.values())}, index=list(rows.keys()))
            st.bar_chart(frame, horizontal=True)
        else:
            st.caption("No answers yet. Upload an RFP to get started.")
        st.caption(
            "Reviewed answers count with the status the reviewer chose. Rejected ones are left out."
        )


def _upload() -> None:
    with st.container(border=True):
        st.subheader("New RFP")
        if not state.can_run_rfps():
            st.info("Your account type cannot run RFPs.")
            return
        uploaded = st.file_uploader("PDF, DOCX or TXT, up to 10 MB", type=fmt.UPLOAD_TYPES)
        if uploaded is None:
            return
        data = uploaded.getvalue()
        problem = fmt.upload_problem(uploaded.name, len(data))
        if problem:
            st.error(problem)
            return
        if st.button("Start analysis", type="primary"):
            with st.spinner("Reading the file..."):
                run = _call(state.api().upload_run, uploaded.name, data)
            if run is not None:
                st.session_state.selected_run = run["id"]
                st.success("Started. Progress appears below.")
                st.rerun()


def _run_card(run: dict, answered: int | None) -> None:
    with st.container(border=True):
        left, middle, right = st.columns([3, 2, 1])
        with left:
            st.markdown(f"**{fmt.md_escape(run['rfp_name'])}**")
            st.caption(f"Started {fmt.short_time(run['created_at'])}")
        with middle:
            if run["state"] == "running":
                done = answered or 0
                st.progress(
                    fmt.progress_fraction(done, run["requirement_count"]),
                    text=f"{done} of {run['requirement_count']} requirements",
                )
            elif run["state"] == "completed":
                st.caption(f"Finished. {run['requirement_count']} requirements.")
            else:
                st.caption("Failed. Nothing was exported.")
        with right:
            if run["state"] == "completed" and st.button(
                "Review", key=f"open_{run['id']}", use_container_width=True
            ):
                st.session_state.selected_run = run["id"]
                st.switch_page(st.session_state.pages["review"])
        for warning in run.get("warnings") or []:
            st.caption(f"Note: {fmt.md_escape(warning)}")


def _runs_body() -> None:
    runs = _call(state.api().list_runs)
    if runs is None:
        return
    runs = fmt.newest_first(runs)
    if not runs:
        st.caption("No runs yet.")
        return
    before = st.session_state.get("had_running", False)
    running = fmt.any_running(runs)
    st.session_state.had_running = running
    if before != running:
        st.rerun()  # a run started or finished: redraw the numbers and the refresh timer
    for run in runs[:10]:
        answered = None
        if run["state"] == "running":
            detail = _call(state.api().run_detail, run["id"])
            answered = detail["answered"] if detail else 0
        _run_card(run, answered)


def _runs() -> None:
    st.subheader("Your runs")
    interval = 3 if st.session_state.get("had_running") else None
    st.fragment(run_every=interval)(_runs_body)()


def _activity() -> None:
    with st.expander("Recent activity"):
        rows = _call(state.api().activity, 15)
        if not rows:
            st.caption("Nothing yet.")
            return
        table = [
            {
                "When": fmt.short_time(row["occurred_at"]),
                "Action": row["action"],
                "Decision": row["decision"],
                "Item": row["resource_type"] or "",
            }
            for row in rows
        ]
        st.dataframe(table, hide_index=True, use_container_width=True)


def render() -> None:
    st.title("RFP dashboard")
    if not state.can_run_rfps():
        st.info("Your account type cannot run RFPs. Ask an administrator for staff access.")
        return
    left, right = st.columns([3, 2])
    with left:
        _overview()
    with right:
        _upload()
    _runs()
    _activity()
