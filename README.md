A Streamlit tool that searches the web for **recent IT-industry deals** —
mergers, acquisitions, outsourcing contracts, managed services deals, cloud
deals — from **any company**, not just one you name.

This version uses **only the Serper API** (Google Search results as JSON).  
No Anthropic / Claude API key is required.

You pick a time window (past week up to past 2 years, or a custom range),
the app runs several Serper searches, extracts structured deal data from
titles and snippets, shows results in a table, and lets you download Excel.

---

## What's in this folder

| File | Purpose |
|---|---|
| `app.py` | Streamlit web app (UI) |
| `deal_engine.py` | Date ranges, Serper search, heuristic deal extraction, dedupe & date filter |
| `requirements.txt` | Python packages |
| `README.md` | This guide |

---

## Step 1 — Get a Serper API key

1. Go to https://serper.dev
2. Sign up (free tier includes a large number of searches).
3. Copy your API key from the dashboard.

---

## Step 2 — Run locally

```bash
pip install -r requirements.txt
export SERPER_API_KEY="paste-your-key-here"
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

---

## Step 3 — Deploy on Streamlit Community Cloud (optional)

1. Push this folder to a GitHub repo.
2. Go to https://share.streamlit.io → **Create app** → pick the repo, main file `app.py`.
3. Under **Advanced settings → Secrets** add:

   ```
   SERPER_API_KEY = "paste-your-key-here"
   ```

4. Deploy. You’ll get a permanent URL.

---

## How to use

1. In the sidebar, pick a **Tenure** (or Custom range + start/end dates).
2. Optionally add keywords (e.g. `healthcare`, `Europe`, `cybersecurity`).
3. Click **Search deals**.
4. Review the table (Acquirer/Buyer, Target/Vendor, Deal Type, Value, Date, Summary, Source, URL).
5. **Download as Excel** if needed.

---

## How extraction works (no LLM)

- Serper returns organic Google results (title, link, snippet, date).
- The engine keeps only results that mention deal signals (acquire, merger, outsourcing contract, managed services, cloud deal, etc.).
- Regex patterns try to pull buyer/target (or vendor) and deal value from title + snippet.
- Deal type is inferred from keywords.
- Dates are parsed from Serper’s `date` field when present (including “2 days ago”-style relative dates).
- Results are deduplicated and filtered to your selected date range.

**Limits:** Without an LLM, party names and values are best-effort from the snippet. Some rows may have null Acquirer/Target if the headline is vague. Always use the Source URL to verify.

---

## Notes

- Each “Search deals” click runs **6 Serper queries** (different deal angles). Watch your Serper credit usage.
- To change coverage, edit `base_terms` in `deal_engine.py`.
- Tick **Include deals with no clear announcement date** if you want undated hits as well.