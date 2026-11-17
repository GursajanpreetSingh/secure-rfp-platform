import streamlit as st

from ui import format as fmt
from ui import state
from ui.client import ApiError


def _call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ApiError as problem:
        state.handle_expiry(problem)
        st.error(problem.message)
        return None


def _pick_run() -> dict | None:
    runs = _call(state.api().list_runs)
    if runs is None:
        return None
    done = [run for run in fmt.newest_first(runs) if run["state"] == "completed"]
    if not done:
        st.info("No finished runs yet. Start one on the dashboard.")
        return None
    ids = [run["id"] for run in done]
    chosen = st.session_state.get("selected_run")
    index = ids.index(chosen) if chosen in ids else 0
    names = {run["id"]: f"{run['rfp_name']}  ({fmt.short_time(run['created_at'])})" for run in done}
    run_id = st.selectbox("RFP run", ids, index=index, format_func=names.get)
    st.session_state.selected_run = run_id
    return next(run for run in done if run["id"] == run_id)


def _export(run_id: str, summary: dict) -> None:
    with st.container(border=True):
        pending = summary["pending"]
        if pending:
            st.caption(
                f"{pending} answers are still waiting for review. Export opens when none are."
            )
        else:
            st.caption("Every answer has been reviewed. The export is ready.")
        if st.button("Prepare CSV export", disabled=bool(pending)):
            download = _call(state.api().export_csv, run_id)
            if download is not None:
                st.download_button(
                    "Download compliance matrix",
                    data=download.data,
                    file_name=download.filename,
                    mime="text/csv",
                )


def _citations(result: dict) -> None:
    if not result["citations"]:
        st.caption("No supporting passage was cited.")
        return
    for cite in result["citations"]:
        where = cite.get("title") or "Document"
        if cite.get("section"):
            where += f", {cite['section']}"
        if cite.get("page"):
            where += f", page {cite['page']}"
        st.caption(f"{cite.get('ref', '')}  {where}")
        st.text(cite.get("quote") or "")  # st.text never interprets markdown or HTML


def _review_form(run_id: str, result: dict) -> None:
    key = f"{run_id}_{result['requirement_id']}"
    actions = fmt.allowed_actions(result)
    with st.form(f"review_{key}"):
        action = st.radio(
            "Decision",
            actions,
            format_func={
                "approve": "Approve the answer",
                "edit": "Use another status",
                "reject": "Reject the answer",
            }.get,
            horizontal=True,
        )
        chosen = st.selectbox(
            "Status (only when using another status)",
            list(fmt.STATUS_ORDER[:4]),
            format_func=lambda s: fmt.status_text(s),
        )
        note = st.text_area("Note (required to edit or reject, at least 10 characters)")
        go = st.form_submit_button("Save review", type="primary")
    if not go:
        return
    final = chosen if action == "edit" else None
    problem = fmt.review_problem(action, final, note)
    if problem:
        st.error(problem)
        return
    saved = _call(
        state.api().review, run_id, result["requirement_id"], action, final, note.strip() or None
    )
    if saved is not None:
        st.rerun()


def _result_card(run_id: str, result: dict) -> None:
    shown = (
        fmt.status_text(fmt.shown_status(result))
        if result["review_state"] != "rejected"
        else "Rejected"
    )
    title = (
        f"{fmt.md_escape(result['requirement_id'])}  ·  {shown}  ·  "
        f"{fmt.REVIEW_LABEL[result['review_state']]}"
    )
    with st.expander(title):
        st.markdown("**Requirement**")
        st.text(result["requirement_text"])
        st.markdown(f"**System answer:** {fmt.status_text(result['ai_status'])}")
        if result.get("downgraded_from"):
            st.caption(
                "The system lowered this answer because the quoted evidence did not hold up."
            )
        st.text(result["ai_rationale"])
        _citations(result)
        if result["review_state"] != "pending":
            st.markdown(f"**Reviewed:** {fmt.REVIEW_LABEL[result['review_state']]}")
            if result.get("reviewer_note"):
                st.text(result["reviewer_note"])
            st.caption("You can review again to change this.")
        _review_form(run_id, result)


def render() -> None:
    st.title("Review answers")
    if not state.can_run_rfps():
        st.info("Your account type cannot run RFPs.")
        return
    run = _pick_run()
    if run is None:
        return
    detail = _call(state.api().run_detail, run["id"])
    results = _call(state.api().results, run["id"])
    if detail is None or results is None:
        return
    summary = detail["summary"]
    cols = st.columns(4)
    cols[0].metric("Requirements", summary["total"])
    cols[1].metric("Waiting", summary["pending"])
    cols[2].metric(
        "Approved or edited",
        summary["review_state"]["approved"] + summary["review_state"]["edited"],
    )
    cols[3].metric("Rejected", summary["review_state"]["rejected"])
    _export(run["id"], summary)

    left, right = st.columns(2)
    review_filter = left.selectbox(
        "Show",
        [None, *fmt.REVIEW_LABEL],
        format_func=lambda s: "All" if s is None else fmt.REVIEW_LABEL[s],
    )
    status_filter = right.selectbox(
        "Status",
        [None, *fmt.STATUS_ORDER],
        format_func=lambda s: "Any" if s is None else fmt.status_text(s),
    )
    shown = fmt.filter_results(results, review_filter, status_filter)
    st.caption(f"{len(shown)} of {len(results)} answers")
    for result in shown:
        _result_card(run["id"], result)
