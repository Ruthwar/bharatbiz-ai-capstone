import re
from decimal import Decimal
from html import escape

import streamlit as st

COLORS = {
    "ink": "#172033",
    "muted": "#64748b",
    "line": "#e2e8f0",
    "canvas": "#f5f7fb",
    "accent": "#1d4ed8",
    "success": "#0f766e",
    "warning": "#b45309",
    "danger": "#b91c1c",
}


def format_rupees(value) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    whole, _, fraction = f"{abs(amount):.2f}".partition(".")
    if len(whole) > 3:
        tail = whole[-3:]
        head = whole[:-3]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}.{fraction}"


def quote_html(text: str) -> str:
    escaped = escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bb-ink: #172033;
            --bb-muted: #64748b;
            --bb-line: #e2e8f0;
            --bb-canvas: #f5f7fb;
            --bb-accent: #1d4ed8;
            --bb-success: #0f766e;
            --bb-warning: #b45309;
            --bb-danger: #b91c1c;
        }
        .stApp, [data-testid="stAppViewContainer"] {
            background: var(--bb-canvas);
            color: var(--bb-ink);
            font-family: "Segoe UI", Inter, Arial, sans-serif;
        }
        [data-testid="stHeader"] { background: transparent; }
        #MainMenu, footer { visibility: hidden; }
        [data-testid="stMainBlockContainer"] {
            max-width: 1500px;
            padding: 1.8rem 2.2rem 3rem;
        }
        [data-testid="stSidebar"] {
            background: #111c33;
            border-right: 1px solid #263550;
        }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.4rem; }
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] label { color: #dbe5f5; }
        [data-testid="stSidebar"] [role="radiogroup"] { gap: 0.35rem; }
        [data-testid="stSidebar"] [role="radiogroup"] > label {
            width: 100%;
            padding: 0.7rem 0.8rem;
            border-radius: 8px;
            border: 1px solid transparent;
            transition: background 120ms ease;
        }
        [data-testid="stSidebar"] [role="radiogroup"] > label:hover { background: #1a2945; }
        [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
            background: #203456;
            border-color: #38547f;
        }
        [data-testid="stSidebar"] [role="radiogroup"] > label > div:first-child { display: none; }
        [data-testid="stSidebar"] hr { border-color: #2a3a57; }
        [data-testid="stSidebar"] .stCaption { color: #91a3bf; }
        h1, h2, h3, h4 { color: var(--bb-ink); letter-spacing: -0.02em; }
        p, label, .stMarkdown { font-size: 0.94rem; }
        .stCaption, .stCaption p { color: var(--bb-muted); }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff;
            border: 1px solid var(--bb-line) !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.025);
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.bb-dark-card) {
            background: #16233c;
            border-color: #16233c !important;
        }
        .stButton button, .stFormSubmitButton button {
            border-radius: 8px;
            border: 1px solid #cbd5e1;
            font-weight: 600;
            min-height: 2.45rem;
            box-shadow: none;
        }
        .stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {
            background: var(--bb-accent);
            border-color: var(--bb-accent);
        }
        .stButton button:hover { border-color: #94a3b8; }
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 1.4rem;
            border-bottom: 1px solid var(--bb-line);
        }
        [data-testid="stTabs"] [data-baseweb="tab"] {
            height: 2.8rem;
            padding: 0 0.1rem;
            color: var(--bb-muted);
            font-weight: 600;
        }
        [data-testid="stTabs"] [aria-selected="true"] { color: var(--bb-accent); }
        [data-testid="stDataFrame"] { border: 1px solid var(--bb-line); border-radius: 9px; overflow: hidden; }
        [data-testid="stAlert"] { border-radius: 9px; }
        [data-testid="stChatMessage"] {
            background: #ffffff;
            border: 1px solid var(--bb-line);
            border-radius: 10px;
            padding: 0.4rem 0.7rem;
        }
        .bb-brand { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
        .bb-brand-mark {
            width: 38px; height: 38px; border-radius: 9px; background: #2f6fed;
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 750; letter-spacing: -0.04em;
        }
        .bb-brand-name { color: #ffffff; font-size: 1.08rem; font-weight: 700; line-height: 1.2; }
        .bb-brand-sub { color: #91a3bf; font-size: 0.75rem; margin-top: 0.2rem; }
        .bb-side-label {
            color: #8094b3; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em;
            text-transform: uppercase; margin: 1.1rem 0 0.55rem;
        }
        .bb-side-status {
            background: #182844; border: 1px solid #2b4166; border-radius: 9px;
            padding: 0.75rem; color: #c8d6ea; font-size: 0.79rem; line-height: 1.55;
        }
        .bb-side-status strong { color: #ffffff; }
        .bb-page-head {
            display: flex; justify-content: space-between; align-items: flex-start;
            gap: 1rem; margin-bottom: 1.35rem;
        }
        .bb-eyebrow {
            color: var(--bb-accent); font-size: 0.7rem; font-weight: 750;
            letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.35rem;
        }
        .bb-page-title { font-size: 1.75rem; line-height: 1.2; font-weight: 720; letter-spacing: -0.035em; }
        .bb-page-desc { color: var(--bb-muted); margin-top: 0.45rem; max-width: 760px; line-height: 1.5; }
        .bb-page-meta {
            color: var(--bb-muted); background: #ffffff; border: 1px solid var(--bb-line);
            border-radius: 8px; padding: 0.55rem 0.75rem; font-size: 0.77rem; white-space: nowrap;
        }
        .bb-kpi {
            background: #ffffff; border: 1px solid var(--bb-line); border-radius: 11px;
            padding: 1rem 1.05rem; min-height: 112px; box-shadow: 0 1px 2px rgba(15,23,42,0.025);
        }
        .bb-kpi-label { color: var(--bb-muted); font-size: 0.74rem; font-weight: 650; text-transform: uppercase; letter-spacing: 0.045em; }
        .bb-kpi-value { color: var(--bb-ink); font-size: 1.55rem; font-weight: 720; letter-spacing: -0.035em; margin: 0.5rem 0 0.3rem; }
        .bb-kpi-note { color: var(--bb-muted); font-size: 0.76rem; line-height: 1.35; }
        .bb-kpi-accent { border-top: 3px solid var(--bb-accent); }
        .bb-kpi-warning { border-top: 3px solid #d97706; }
        .bb-kpi-success { border-top: 3px solid var(--bb-success); }
        .bb-section-head { margin: 0.15rem 0 0.8rem; }
        .bb-section-title { font-size: 1rem; font-weight: 700; letter-spacing: -0.015em; }
        .bb-section-sub { color: var(--bb-muted); font-size: 0.78rem; margin-top: 0.25rem; }
        .bb-badge {
            display: inline-block; border-radius: 999px; padding: 0.2rem 0.55rem;
            font-size: 0.69rem; font-weight: 700; letter-spacing: 0.02em;
            background: #eef2ff; color: #3730a3; border: 1px solid #dbe3ff;
        }
        .bb-badge-success { background: #ecfdf5; color: #047857; border-color: #d1fae5; }
        .bb-badge-warning { background: #fffbeb; color: #b45309; border-color: #fde7b2; }
        .bb-badge-danger { background: #fef2f2; color: #b91c1c; border-color: #fecaca; }
        .bb-badge-neutral { background: #f1f5f9; color: #475569; border-color: #e2e8f0; }
        .bb-recommendation {
            background: #f0f5ff; border: 1px solid #d7e4ff; border-left: 4px solid var(--bb-accent);
            border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 1rem;
        }
        .bb-recommendation-label { color: var(--bb-accent); font-size: 0.7rem; font-weight: 750; text-transform: uppercase; letter-spacing: 0.08em; }
        .bb-recommendation-text { font-size: 1rem; line-height: 1.55; font-weight: 600; margin-top: 0.45rem; }
        .bb-quote {
            color: #334155; background: #f8fafc; border-left: 3px solid #94a3b8;
            padding: 0.75rem 0.9rem; border-radius: 0 7px 7px 0; line-height: 1.55; margin: 0.65rem 0;
        }
        .bb-list { margin: 0; padding: 0; list-style: none; }
        .bb-list li { padding: 0.7rem 0; border-bottom: 1px solid #edf1f6; line-height: 1.45; }
        .bb-list li:last-child { border-bottom: 0; }
        .bb-list-title { font-weight: 650; font-size: 0.88rem; }
        .bb-list-meta { color: var(--bb-muted); font-size: 0.75rem; margin-top: 0.25rem; }
        .bb-meter { height: 9px; background: #e8edf4; border-radius: 999px; overflow: hidden; margin: 0.9rem 0 0.55rem; }
        .bb-meter-fill { height: 100%; background: var(--bb-success); border-radius: 999px; }
        .bb-meter-legend { display: flex; justify-content: space-between; color: var(--bb-muted); font-size: 0.74rem; }
        .bb-flow { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
        .bb-flow-step { background: #f8fafc; border: 1px solid var(--bb-line); border-radius: 7px; padding: 0.5rem 0.65rem; font-size: 0.75rem; font-weight: 650; }
        .bb-flow-arrow { color: #94a3b8; font-size: 0.8rem; }
        .bb-empty { text-align: center; padding: 2.5rem 1rem; color: var(--bb-muted); }
        .bb-empty-title { color: var(--bb-ink); font-weight: 700; font-size: 1.05rem; margin-bottom: 0.35rem; }
        .bb-code { font-family: Consolas, monospace; font-size: 0.78rem; color: #475569; }
        @media (max-width: 900px) {
            [data-testid="stMainBlockContainer"] { padding: 1.2rem 1rem 2rem; }
            .bb-page-head { display: block; }
            .bb-page-meta { display: inline-block; margin-top: 0.8rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, description: str, meta: str = "") -> None:
    meta_html = f'<div class="bb-page-meta">{escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
        <div class="bb-page-head">
            <div>
                <div class="bb-eyebrow">{escape(eyebrow)}</div>
                <div class="bb-page-title">{escape(title)}</div>
                <div class="bb-page-desc">{escape(description)}</div>
            </div>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, subtitle: str = "") -> None:
    subtitle_html = f'<div class="bb-section-sub">{escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f'<div class="bb-section-head"><div class="bb-section-title">{escape(title)}</div>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, note: str = "", tone: str = "") -> None:
    tone_class = f" bb-kpi-{tone}" if tone else ""
    note_html = f'<div class="bb-kpi-note">{escape(note)}</div>' if note else ""
    st.markdown(
        f"""
        <div class="bb-kpi{tone_class}">
            <div class="bb-kpi-label">{escape(label)}</div>
            <div class="bb-kpi-value">{escape(value)}</div>
            {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, tone: str = "neutral") -> str:
    return f'<span class="bb-badge bb-badge-{escape(tone)}">{escape(text)}</span>'


def empty_state(title: str, text: str) -> None:
    st.markdown(
        f'<div class="bb-empty"><div class="bb-empty-title">{escape(title)}</div><div>{escape(text)}</div></div>',
        unsafe_allow_html=True,
    )
