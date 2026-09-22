"""
deal_engine.py
--------------
Core logic for the IT Deal Finder tool — Serper-only version.

Requires only a SERPER_API_KEY. No Anthropic / Claude key needed.
"""

import re
from datetime import date, timedelta
from urllib.parse import urlparse

import requests
from dateutil import parser as dateparser

# ---------------------------------------------------------------------------
# 1. Date range handling
# ---------------------------------------------------------------------------

TENURE_OPTIONS = {
    "Past week": 7,
    "Past month": 30,
    "Past 3 months": 90,
    "Past 6 months": 182,
    "Past year": 365,
    "Past 2 years": 730,
}


def get_date_range(tenure_label: str, custom_start: date = None, custom_end: date = None):
    today = date.today()
    if tenure_label == "Custom range":
        if not custom_start or not custom_end:
            raise ValueError("Custom range selected but start/end date missing.")
        return custom_start, custom_end

    days = TENURE_OPTIONS.get(tenure_label)
    if days is None:
        raise ValueError(f"Unknown tenure option: {tenure_label}")
    return today - timedelta(days=days), today


def _tbs_for_tenure(start_date: date, end_date: date):
    days = (end_date - start_date).days
    if days <= 1:
        return "qdr:d"
    if days <= 7:
        return "qdr:w"
    if days <= 31:
        return "qdr:m"
    if days <= 365:
        return "qdr:y"
    return None


# ---------------------------------------------------------------------------
# 2. Search query construction
# ---------------------------------------------------------------------------

def build_search_queries(start_date: date, end_date: date, extra_keywords: str = ""):
    year_span = (
        f"{start_date.year}-{end_date.year}"
        if start_date.year != end_date.year
        else str(start_date.year)
    )
    base_terms = [
        "IT services acquisition OR merger announced",
        "technology company acquisition IT deal",
        "IT outsourcing contract signed OR awarded",
        "managed services deal OR contract announced",
        "cloud migration OR cloud services deal contract",
        "IT services deal OR digital transformation contract",
    ]
    queries = []
    for term in base_terms:
        q = f"{term} {year_span}"
        if extra_keywords.strip():
            q += f" {extra_keywords.strip()}"
        queries.append(q)
    return queries


# ---------------------------------------------------------------------------
# 3. Serper API call
# ---------------------------------------------------------------------------

SERPER_SEARCH_URL = "https://google.serper.dev/search"


def serper_search(api_key: str, query: str, num: int = 10, tbs=None) -> list:
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": min(max(num, 1), 100),
        "gl": "us",
        "hl": "en",
    }
    if tbs:
        payload["tbs"] = tbs

    try:
        resp = requests.post(SERPER_SEARCH_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 401:
            raise RuntimeError(
                "Serper rejected the API key (401 invalid x-api-key). "
                "Check that SERPER_API_KEY is set correctly in this terminal."
            )
        if resp.status_code == 403:
            raise RuntimeError(
                "Serper returned 403 — key may be out of credits or restricted."
            )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Serper API request failed: {e}") from e

    organic = data.get("organic") or []
    results = []
    for item in organic:
        results.append(
            {
                "title": item.get("title") or "",
                "link": item.get("link") or "",
                "snippet": item.get("snippet") or "",
                "date": item.get("date"),
            }
        )
    return results


# ---------------------------------------------------------------------------
# 4. Heuristic deal extraction from title + snippet
# ---------------------------------------------------------------------------

DEAL_SIGNAL_RE = re.compile(
    r"\b(acqui(?:re|res|red|sition)|merger|merges|buy(?:s|ing)|bought|"
    r"outsourc(?:e|es|ing)|contract\s+(?:award|sign|win)|"
    r"managed\s+services?|cloud\s+(?:deal|migration|contract)|"
    r"partnership|strategic\s+investment|takeover)\b",
    re.I,
)

VALUE_RE = re.compile(
    r"(?:US\s*)?[\$€£]\s*[\d,.]+(?:\s*(?:million|billion|m|bn|b))?"
    r"|\b[\d,.]+\s*(?:million|billion)\s*(?:USD|EUR|GBP|dollars?)?\b",
    re.I,
)

COMPANY_TOKEN = (
    r"[A-Z][A-Za-z0-9&.\-']+(?:\s+(?:Inc|Ltd|LLC|Corp|Corporation|"
    r"Group|Technologies|Systems|Solutions|Services|Software|Labs?)\.?)?"
)

ACQUIRE_PATTERNS = [
    re.compile(
        rf"(?P<buyer>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,3}})\s+"
        r"(?:to\s+)?(?:acquire|acquires|acquired|buy|buys|bought|purchase|purchases)\s+"
        rf"(?P<target>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,3}})",
        re.I,
    ),
    re.compile(
        rf"(?P<target>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,3}})\s+"
        r"(?:to\s+be\s+)?(?:acquired|bought|purchased)\s+by\s+"
        rf"(?P<buyer>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,3}})",
        re.I,
    ),
    re.compile(
        rf"(?P<buyer>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,2}})\s+"
        r"(?:and|&)\s+"
        rf"(?P<target>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,2}})\s+"
        r"(?:to\s+)?(?:merge|merger)",
        re.I,
    ),
]

CONTRACT_PATTERNS = [
    re.compile(
        rf"(?P<buyer>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,2}})\s+"
        r"(?:awards?|signs?|awarded|signed)\s+(?:an?\s+)?(?:IT\s+|managed\s+services?\s+|outsourcing\s+|cloud\s+)?"
        r"contract\s+(?:to|with)\s+"
        rf"(?P<vendor>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,2}})",
        re.I,
    ),
    re.compile(
        rf"(?P<vendor>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,2}})\s+"
        r"(?:wins?|won|secures?|secured)\s+(?:an?\s+)?(?:IT\s+|managed\s+services?\s+|outsourcing\s+|cloud\s+)?"
        r"contract\s+(?:from|with)\s+"
        rf"(?P<buyer>{COMPANY_TOKEN}(?:\s+{COMPANY_TOKEN}){{0,2}})",
        re.I,
    ),
]


def _guess_deal_type(text: str) -> str:
    t = text.lower()
    if re.search(r"\bmerg(?:e|er|es)\b", t):
        return "merger"
    if re.search(r"\bacqui(?:re|res|red|sition)\b|\bbuy(?:s|ing)\b|\bbought\b|\btakeover\b", t):
        return "acquisition"
    if re.search(r"\boutsourc", t):
        return "outsourcing contract"
    if re.search(r"\bmanaged\s+services?\b", t):
        return "managed services"
    if re.search(r"\bcloud\b", t):
        return "cloud deal"
    if re.search(r"\bpartnership\b|\bstrategic\s+alliance\b", t):
        return "partnership"
    if re.search(r"\bcontract\b", t):
        return "outsourcing contract"
    return "other"


def _extract_value(text: str):
    m = VALUE_RE.search(text)
    return m.group(0).strip() if m else None


def _parse_relative_or_absolute_date(raw, today=None):
    if not raw:
        return None
    today = today or date.today()
    raw = raw.strip()
    rel = re.match(
        r"^(\d+)\s+(hour|hours|day|days|week|weeks|month|months|year|years)\s+ago$",
        raw,
        re.I,
    )
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("hour"):
            return today
        if unit.startswith("day"):
            return today - timedelta(days=n)
        if unit.startswith("week"):
            return today - timedelta(weeks=n)
        if unit.startswith("month"):
            return today - timedelta(days=30 * n)
        if unit.startswith("year"):
            return today - timedelta(days=365 * n)
    try:
        return dateparser.parse(raw, fuzzy=True).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _source_name_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host or "unknown"
    except Exception:
        return "unknown"


def extract_deal_from_result(item: dict):
    title = (item.get("title") or "").strip()
    snippet = (item.get("snippet") or "").strip()
    link = (item.get("link") or "").strip()
    raw_date = item.get("date")

    if not link:
        return None

    combined = f"{title}. {snippet}"
    if not DEAL_SIGNAL_RE.search(combined):
        return None

    acquirer = None
    target = None

    for pat in ACQUIRE_PATTERNS:
        m = pat.search(combined)
        if m:
            acquirer = (m.group("buyer") or "").strip() or None
            target = (m.group("target") or "").strip() or None
            break

    if not acquirer and not target:
        for pat in CONTRACT_PATTERNS:
            m = pat.search(combined)
            if m:
                acquirer = (m.groupdict().get("buyer") or "").strip() or None
                target = (m.groupdict().get("vendor") or "").strip() or None
                break

    deal_type = _guess_deal_type(combined)
    deal_value = _extract_value(combined)
    parsed_date = _parse_relative_or_absolute_date(raw_date)
    announcement_date = parsed_date.isoformat() if parsed_date else None

    summary = title
    if snippet and snippet not in title:
        summary = f"{title} — {snippet[:180]}{'…' if len(snippet) > 180 else ''}"

    return {
        "acquirer_or_buyer": acquirer,
        "target_or_vendor": target,
        "deal_type": deal_type,
        "deal_value": deal_value,
        "announcement_date": announcement_date,
        "summary": summary[:500],
        "source_name": _source_name_from_url(link),
        "source_url": link,
    }


def search_and_extract(api_key: str, query: str, tbs=None, num: int = 10) -> list:
    results = serper_search(api_key, query, num=num, tbs=tbs)
    deals = []
    for item in results:
        deal = extract_deal_from_result(item)
        if deal:
            deals.append(deal)
    return deals


def run_all_queries(api_key: str, queries: list, tbs=None, progress_callback=None):
    all_deals = []
    total = len(queries)
    last_error = None
    for i, q in enumerate(queries, start=1):
        if progress_callback:
            progress_callback(i, total, q)
        try:
            deals = search_and_extract(api_key, q, tbs=tbs)
            all_deals.extend(deals)
        except RuntimeError as e:
            last_error = e
            continue
    if not all_deals and last_error:
        raise last_error
    return all_deals


# ---------------------------------------------------------------------------
# 5. Dedup + date filtering
# ---------------------------------------------------------------------------

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def dedupe_deals(deals: list):
    seen = set()
    unique = []
    for d in deals:
        key = (
            _norm(d.get("acquirer_or_buyer")),
            _norm(d.get("target_or_vendor")),
            _norm(d.get("deal_type")),
            d.get("source_url"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return unique


def filter_by_date(deals: list, start_date: date, end_date: date, keep_unknown_dates: bool = False):
    kept = []
    for d in deals:
        raw_date = d.get("announcement_date")
        if not raw_date:
            if keep_unknown_dates:
                kept.append(d)
            continue
        try:
            parsed = dateparser.parse(str(raw_date)).date()
        except (ValueError, TypeError):
            if keep_unknown_dates:
                kept.append(d)
            continue
        if start_date <= parsed <= end_date:
            kept.append(d)
    return kept


def get_deals(
    api_key: str,
    tenure_label: str,
    custom_start: date = None,
    custom_end: date = None,
    extra_keywords: str = "",
    keep_unknown_dates: bool = False,
    progress_callback=None,
):
    start_date, end_date = get_date_range(tenure_label, custom_start, custom_end)
    queries = build_search_queries(start_date, end_date, extra_keywords)
    tbs = _tbs_for_tenure(start_date, end_date)
    raw_deals = run_all_queries(
        api_key, queries, tbs=tbs, progress_callback=progress_callback
    )
    unique_deals = dedupe_deals(raw_deals)
    filtered = filter_by_date(
        unique_deals, start_date, end_date, keep_unknown_dates=keep_unknown_dates
    )
    return filtered, start_date, end_date