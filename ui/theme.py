import streamlit as st

_CSS = """
<style>
  .block-container { padding-top: 2rem; max-width: 1200px; }
  [data-testid="stSidebar"] { background: #0e1630; border-right: 1px solid #1c2748; }
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
  .brand { font-size: 1.25rem; font-weight: 700; letter-spacing: .2px; }
  .brand small { display: block; font-size: .72rem; font-weight: 400; color: #8f9ac2; }
  .chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .75rem;
          background: #1b2750; color: #aab6ff; border: 1px solid #2b3a74; }
  .muted { color: #8f9ac2; font-size: .9rem; }
  .kpi-label { color: #8f9ac2; font-size: .85rem; }
  .kpi-value { font-size: 2rem; font-weight: 700; line-height: 1.1; }
</style>
"""


def apply() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)  # fixed text written here, never user content


def brand() -> None:
    st.markdown(
        '<div class="brand">RFP AI Agent'
        "<small>Compliance, grounded in your own documents</small></div>",
        unsafe_allow_html=True,
    )
