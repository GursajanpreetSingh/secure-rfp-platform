import streamlit as st

_CSS = """
<style>
  .block-container { padding-top: 2rem; max-width: 1200px; }
  [data-testid="stSidebar"] { background: #eceefa !important; border-right: 1px solid #d9dcf0; }
  [data-testid="stSidebar"] * { color: #1b2140 !important; }
  [data-testid="stSidebar"] [aria-current="page"], [data-testid="stSidebar"] a:hover {
    background: #dfe2fb !important; border-radius: 8px; }
  [data-testid="stSidebar"] .brand small { color: #5b6490 !important; }
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
  .brand { font-size: 1.25rem; font-weight: 700; letter-spacing: .2px; }
  .brand small { display: block; font-size: .72rem; font-weight: 400; color: #5b6490; }
  .chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .75rem;
          background: #e4e6ff; color: #3730a3; border: 1px solid #c7ccf5; }
  .muted { color: #5b6490; font-size: .9rem; }
  .kpi-label { color: #5b6490; font-size: .85rem; }
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