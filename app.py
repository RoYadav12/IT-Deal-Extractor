"""
app.py
------
Streamlit UI for the IT Deal Finder (Serper-only version).

Run locally:      streamlit run app.py
Deploy:            push to GitHub, connect repo on Streamlit Community Cloud,
                    add SERPER_API_KEY under App settings -> Secrets.
"""

import io
import os
from datetime import date

import pandas as pd
import streamlit as st

from deal_engine import TENURE_OPTIONS, get_deals

st.set_page_config(page_title="IT Deal Finder", layout="wide")

st.title("IT Deal Finder")
st.caption(
    "Search recent IT-industry deals (M&A, outsourcing, managed services, cloud) "
    "across the web via Serper — not tied to a single company."
)

# ---------------------------------------------------------------------------
# Sidebar: filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")

    tenure_choices = list(TENURE_OPTIONS.keys()) + ["Custom range"]
    tenure_label = st.selectbox("Tenure", tenure_choices, index=1)

    custom_start, custom_end = None, None
    if tenure_label == "Custom range":
        col1, col2 = st.columns(2)
        with col1:
            custom_start = st.date_input("Start date", value=date.today())
        with col2:
            custom_end = st.date_input("End date", value=date.today())

    extra_keywords = st.text_input(
        "Optional keywords (industry, region, deal type)",
        placeholder="e.g. healthcare, Europe, cybersecurity",
    )

    keep_unknown = st.checkbox(
        "Include deals with no clear announcement date",
        value=False,
        help=(
            "Off by default so the tenure filter is meaningful. "
            "Turn on to see everything found, including undated items."
        ),
    )

    run_search = st.button("Search deals", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# API key handling — Serper only
# ---------------------------------------------------------------------------
# st.secrets raises StreamlitSecretNotFoundError when no secrets.toml exists.
# Always fall back to the environment variable.

api_key = ""
try:
    api_key = st.secrets.get("SERPER_API_KEY", "") or ""
except Exception:
    api_key = ""

if not api_key:
    api_key = os.environ.get("SERPER_API_KEY", "")

if not api_key:
    st.warning(
        "No **SERPER_API_KEY** found.\n\n"
        "In the terminal run:\n"
        "```\n"
        "export SERPER_API_KEY=\"your-key-here\"\n"
        "streamlit run app.py\n"
        "```\n\n"
        "Or create `.streamlit/secrets.toml` with:\n"
        "```\n"
        "SERPER_API_KEY = \"your-key-here\"\n"
        "```\n\n"
        "Get a free key at https://serper.dev"
    )

# ---------------------------------------------------------------------------
# Run search
# ---------------------------------------------------------------------------

if run_search:
    if not api_key:
        st.error("Cannot search without a Serper API key. Add SERPER_API_KEY first.")
    else:
        progress_bar = st.progress(0.0, text="Starting search...")

        def progress_callback(i, total, query):
            progress_bar.progress(
                i / total, text=f"Searching ({i}/{total}): {query[:60]}…"
            )

        with st.spinner("Searching the web via Serper and extracting deals..."):
            try:
                deals, start_date, end_date = get_deals(
                    api_key=api_key,
                    tenure_label=tenure_label,
                    custom_start=custom_start,
                    custom_end=custom_end,
                    extra_keywords=extra_keywords,
                    keep_unknown_dates=keep_unknown,
                    progress_callback=progress_callback,
                )
            except Exception as e:
                progress_bar.empty()
                st.error(f"Search failed: {e}")
                deals, start_date, end_date = [], None, None

        progress_bar.empty()
        if start_date is not None:
            st.session_state["deals"] = deals
            st.session_state["range_label"] = f"{start_date} to {end_date}"

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

deals = st.session_state.get("deals", [])

if deals:
    st.success(
        f"Found {len(deals)} deal(s) for range {st.session_state.get('range_label', '')}"
    )

    df = pd.DataFrame(deals)
    column_order = [
        "acquirer_or_buyer",
        "target_or_vendor",
        "deal_type",
        "deal_value",
        "announcement_date",
        "summary",
        "source_name",
        "source_url",
    ]
    df = df[[c for c in column_order if c in df.columns]]
    df = df.rename(
        columns={
            "acquirer_or_buyer": "Acquirer / Buyer",
            "target_or_vendor": "Target / Vendor",
            "deal_type": "Deal Type",
            "deal_value": "Deal Value",
            "announcement_date": "Announcement Date",
            "summary": "Summary",
            "source_name": "Source",
            "source_url": "Source URL",
        }
    )

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Excel export
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="IT Deals")
    buffer.seek(0)

    st.download_button(
        label="Download as Excel",
        data=buffer,
        file_name="it_deals.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
elif run_search:
    st.info(
        "No deals found for this range/keyword combination. "
        "Try widening the tenure, adding keywords, or enabling "
        "'Include deals with no clear announcement date'."
    )
else:
    st.info(
        "Choose a tenure (or custom range) in the sidebar, then click **Search deals**."
    )