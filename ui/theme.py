import streamlit as st

_CSS = """
<style>
  /* page: soft lavender gradient, tighter spacing */
  .stApp {
    background:
      radial-gradient(circle at 8% 0%, #e3e6ff 0, transparent 38%),
      radial-gradient(circle at 95% 8%, #f1e7ff 0, transparent 34%),
      linear-gradient(180deg, #f1f3ff 0%, #f8f9ff 50%, #ffffff 100%);
    background-attachment: fixed;
  }
  html, body, .stApp { font-family: "Segoe UI", "Inter", system-ui, sans-serif; }
  header[data-testid="stHeader"] { background: transparent; }
  #MainMenu, footer { visibility: hidden; }
  .block-container { padding-top: 1.4rem; padding-bottom: 2.5rem; max-width: 1150px; }
  div[data-testid="stVerticalBlock"] { gap: .7rem; }
  h1 { color: #2a2f6b; font-weight: 800; letter-spacing: -.3px; padding: 0 0 .2rem 0; }
  h2, h3 { color: #2a2f6b; padding-top: .3rem; }

  /* sidebar */
  [data-testid="stSidebar"] { background: #eceefa !important; border-right: 1px solid #d9dcf0; }
  [data-testid="stSidebar"] * { color: #1b2140 !important; }
  [data-testid="stSidebar"] [aria-current="page"], [data-testid="stSidebar"] a:hover {
    background: #dfe2fb !important; border-radius: 10px; }
  [data-testid="stSidebar"] .brand small { color: #5b6490 !important; }

  /* cards made with st.container(border=True) */
  div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px; background: rgba(255,255,255,.78);
    box-shadow: 0 6px 22px rgba(79,70,229,.07); }

  /* buttons and inputs */
  .stButton > button, .stDownloadButton > button { border-radius: 12px; font-weight: 600; }
  button[kind="primary"], button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #6366f1, #7c3aed); color: #fff; border: 0; }
  button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
    filter: brightness(1.07); }
  div[data-testid="stChatInput"] {
    border-radius: 16px; box-shadow: 0 6px 22px rgba(79,70,229,.10); }

  /* brand, chips, numbers */
  .brand { font-size: 1.25rem; font-weight: 700; letter-spacing: .2px; }
  .brand small { display: block; font-size: .72rem; font-weight: 400; color: #5b6490; }
  .chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .75rem;
          background: #e4e6ff; color: #3730a3; border: 1px solid #c7ccf5; }
  .muted { color: #5b6490; font-size: .9rem; }
  .kpi-label { color: #5b6490; font-size: .85rem; }
  .kpi-value { font-size: 2rem; font-weight: 700; line-height: 1.1; }

  /* chat */
  .msg-user { display: flex; justify-content: flex-end; align-items: flex-end; gap: .6rem;
              margin: .7rem 0 .3rem 0; }
  .bubble-user { background: linear-gradient(135deg, #6366f1, #7c3aed); color: #fff;
                 padding: .65rem 1rem; border-radius: 18px 18px 4px 18px; max-width: 72%;
                 box-shadow: 0 6px 16px rgba(99,102,241,.28); line-height: 1.45; }
  .msg-ai { display: flex; align-items: flex-start; gap: .6rem; margin: .4rem 0 .7rem 0; }
  .avatar { width: 34px; height: 34px; border-radius: 50%; display: flex; flex: none;
            align-items: center; justify-content: center; font-size: 1.05rem; }
  .avatar-user { background: #e0e3ff; }
  .avatar-ai { background: #fff; border: 1px solid #dfe3f8;
               box-shadow: 0 3px 10px rgba(79,70,229,.12); }
  .card-answer { background: #fff; border: 1px solid #e3e6f6; border-left: 5px solid #6366f1;
                 border-radius: 6px 16px 16px 16px; padding: .85rem 1.1rem; max-width: 84%;
                 box-shadow: 0 8px 24px rgba(79,70,229,.09); color: #2b3157; }
  .card-answer.notice-info { border-left-color: #38bdf8; background: #f5fbff; }
  .card-answer.notice-warn { border-left-color: #f59e0b; background: #fffaf0; }
  .ans-head { font-weight: 700; font-size: 1.05rem; color: #1b2140; line-height: 1.4; }
  .ans-para { margin-top: .4rem; line-height: 1.5; }
  .ans-list { margin: .5rem 0 0 1.1rem; padding: 0; line-height: 1.55; }
  .ans-list li { margin: .15rem 0; }
  .chips { margin-top: .75rem; display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
  .based { font-size: .75rem; color: #5b6490; margin-right: .2rem; }
  .src-chip { background: #eef0ff; color: #3730a3; border: 1px solid #d5d9fb;
              border-radius: 999px; padding: 2px 10px; font-size: .75rem; cursor: help; }
  .empty-hero { text-align: center; padding: 1.6rem 1rem; background: rgba(255,255,255,.7);
                border: 1px dashed #cfd4f7; border-radius: 18px; margin-bottom: .4rem; }
  .empty-title { font-size: 1.25rem; font-weight: 700; color: #2a2f6b; }
  .empty-sub { color: #5b6490; margin-top: .3rem; }
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
