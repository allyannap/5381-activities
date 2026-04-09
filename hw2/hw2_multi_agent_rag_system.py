"""
HW2 — Multi-agent RAG tools

Single runnable script that demonstrates:
- Tool functions (one per source)
- Tool metadata (JSON schema) for function calling
- Two-agent chain with agent_run(): Agent 1 calls get_vera_detention_trends,
  get_recent_ice_articles, and get_census_demographics (output="tools"), then
  Agent 2 writes a grounded report from all three sources.

Environment variables (do not commit secrets):
- NEWSAPI_API_KEY: required for get_recent_ice_articles() to call NewsAPI
- CENSUS_API_KEY: required for get_census_demographics() to call the Census API

This script is intentionally runnable even without those keys: the tools will return
structured error payloads explaining what’s missing, while the VERA tool runs locally.

Numbers in CSVs are aggregated by Python (get_vera_detention_trends); the LLM does not
read the data folder. If Agent 1’s tool output JSON is correct but Agent 2’s report
wrong, that is usually paraphrase or hallucination in the second model call, not bad file IO.

Optional tuning (override with env vars if needed):
- OLLAMA_HTTP_TIMEOUT: seconds for each Ollama HTTP request (default 120)
- AGENT1_CHAIN_TIMEOUT_SEC: max seconds for Agent 1 to finish (default 120); on timeout the script exits with an error
- AGENT2_CHAIN_TIMEOUT_SEC: max seconds for Agent 2 (report) to finish (default 120); on timeout the script exits with an error
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd
import requests

try:
    from dotenv import load_dotenv

    _ACTIVITIES_ENV = Path(__file__).resolve().parents[2] / ".env"
    if _ACTIVITIES_ENV.exists():
        load_dotenv(_ACTIVITIES_ENV, override=False)
except ImportError:
    pass


# 0) CONFIG (mirrors dsai/08_function_calling patterns) #########################

# Select model of interest (same style as 04_multiple_agents_with_function_calling.py)
MODEL = os.getenv("MODEL", "llama3.1:8b")
#MODEL = os.getenv("MODEL", "smollm2:1.7b")

# Ollama connection (same style as dsai/08_function_calling/functions.py)
# NOTE: dsai/08_function_calling/functions.py hard-codes PORT/CHAT_URL at import time,
# so we patch the module after import to respect these env vars.
PORT = int(os.getenv("PORT", "11434"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", f"http://localhost:{PORT}")

# Ollama HTTP timeout (seconds) so hung requests fail instead of blocking indefinitely.
OLLAMA_HTTP_TIMEOUT = float(os.getenv("OLLAMA_HTTP_TIMEOUT", "120"))
# Max wall-clock time for Agent 1 (LLM + tool execution). If exceeded, exit with an error.
AGENT1_CHAIN_TIMEOUT_SEC = float(os.getenv("AGENT1_CHAIN_TIMEOUT_SEC", "120"))
# Max wall-clock time for Agent 2 (report, no tools). If exceeded, exit with an error.
AGENT2_CHAIN_TIMEOUT_SEC = float(os.getenv("AGENT2_CHAIN_TIMEOUT_SEC", "120"))
# Optional lightweight article excerpt fetch settings (best-effort; safe defaults).
NEWS_EXCERPT_MAX_CHARS = int(os.getenv("NEWS_EXCERPT_MAX_CHARS", "900"))
NEWS_EXCERPT_ARTICLE_LIMIT = int(os.getenv("NEWS_EXCERPT_ARTICLE_LIMIT", "3"))
NEWS_EXCERPT_TIMEOUT_SEC = float(os.getenv("NEWS_EXCERPT_TIMEOUT_SEC", "6"))


# 0.1) Import agent helpers ####################################################

ROOT = Path(__file__).resolve().parents[3]  # .../sysen5381
DSAI_FUNCTIONS_DIR = ROOT / "dsai" / "08_function_calling"
sys.path.append(str(DSAI_FUNCTIONS_DIR))

import functions as functions_module  # noqa: E402
from functions import agent_run  # noqa: E402

# Patch helper module endpoints to match env-configured Ollama host.
functions_module.PORT = PORT
functions_module.OLLAMA_HOST = OLLAMA_HOST
functions_module.CHAT_URL = f"{OLLAMA_HOST}/api/chat"

# Ensure every Ollama request has a finite timeout (functions.py uses requests.post without one).
_orig_requests_post = requests.post


def _requests_post_with_timeout(*args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("timeout", OLLAMA_HTTP_TIMEOUT)
    return _orig_requests_post(*args, **kwargs)


requests.post = _requests_post_with_timeout


# 1) UTILITIES ################################################################

_DATA_ROOT = Path(__file__).resolve().parent / "data"
DATA_DIR = _DATA_ROOT
EVIDENCE_STORE_DIR = DATA_DIR / "retrieval_store"


_USPS_TO_SLUG: Dict[str, str] = {
    "AL": "alabama",
    "AK": "alaska",
    "AZ": "arizona",
    "AR": "arkansas",
    "CA": "california",
    "CO": "colorado",
    "CT": "connecticut",
    "DE": "delaware",
    "FL": "florida",
    "GA": "georgia",
    "HI": "hawaii",
    "ID": "idaho",
    "IL": "illinois",
    "IN": "indiana",
    "IA": "iowa",
    "KS": "kansas",
    "KY": "kentucky",
    "LA": "louisiana",
    "ME": "maine",
    "MD": "maryland",
    "MA": "massachusetts",
    "MI": "michigan",
    "MN": "minnesota",
    "MS": "mississippi",
    "MO": "missouri",
    "MT": "montana",
    "NE": "nebraska",
    "NV": "nevada",
    "NH": "new_hampshire",
    "NJ": "new_jersey",
    "NM": "new_mexico",
    "NY": "new_york",
    "NC": "north_carolina",
    "ND": "north_dakota",
    "OH": "ohio",
    "OK": "oklahoma",
    "OR": "oregon",
    "PA": "pennsylvania",
    "RI": "rhode_island",
    "SC": "south_carolina",
    "SD": "south_dakota",
    "TN": "tennessee",
    "TX": "texas",
    "UT": "utah",
    "VT": "vermont",
    "VA": "virginia",
    "WA": "washington",
    "WV": "west_virginia",
    "WI": "wisconsin",
    "WY": "wyoming",
    "DC": "district_of_columbia",
}


_STATE_SLUG_TO_FIPS: Dict[str, str] = {
    "alabama": "01",
    "alaska": "02",
    "arizona": "04",
    "arkansas": "05",
    "california": "06",
    "colorado": "08",
    "connecticut": "09",
    "delaware": "10",
    "district_of_columbia": "11",
    "florida": "12",
    "georgia": "13",
    "hawaii": "15",
    "idaho": "16",
    "illinois": "17",
    "indiana": "18",
    "iowa": "19",
    "kansas": "20",
    "kentucky": "21",
    "louisiana": "22",
    "maine": "23",
    "maryland": "24",
    "massachusetts": "25",
    "michigan": "26",
    "minnesota": "27",
    "mississippi": "28",
    "missouri": "29",
    "montana": "30",
    "nebraska": "31",
    "nevada": "32",
    "new_hampshire": "33",
    "new_jersey": "34",
    "new_mexico": "35",
    "new_york": "36",
    "north_carolina": "37",
    "north_dakota": "38",
    "ohio": "39",
    "oklahoma": "40",
    "oregon": "41",
    "pennsylvania": "42",
    "rhode_island": "44",
    "south_carolina": "45",
    "south_dakota": "46",
    "tennessee": "47",
    "texas": "48",
    "utah": "49",
    "vermont": "50",
    "virginia": "51",
    "washington": "53",
    "west_virginia": "54",
    "wisconsin": "55",
    "wyoming": "56",
    "puerto_rico": "72",
}


def _clean_state_text(state: str) -> str:
    s = (state or "").strip()
    s = s.replace(".", "").replace(",", "").replace(";", "").replace(":", "")
    s = s.replace("/", " ")
    s = " ".join(s.split())
    return s


def _available_vera_state_slugs() -> List[str]:
    """
    Infer which state-level files exist under ./data/ (excluding facilities.csv).
    Treat texas_pt1/texas_pt2 as the single logical state 'texas'.
    """
    if not DATA_DIR.exists():
        return []
    names = {p.name for p in DATA_DIR.glob("*.csv")}
    names.discard("facilities.csv")

    slugs: set[str] = set()
    for n in names:
        if n.startswith("texas_pt") and n.endswith(".csv"):
            slugs.add("texas")
            continue
        if n.endswith(".csv"):
            slugs.add(n[:-4])
    return sorted(slugs)


def _normalize_state_to_slug(state: str) -> str:
    """
    Normalize user state phrasing to a slug matching local VERA filenames.
    Examples:
    - 'TX'/'Texas' -> 'texas' (maps to texas_pt1+texas_pt2)
    - 'NY'/'New York' -> 'new_york'
    - 'national'/'US' -> 'national'
    """
    raw = _clean_state_text(state)
    s = raw.lower()

    aliases = {
        "us": "national",
        "usa": "national",
        "united states": "national",
        "u s": "national",
        "national": "national",
        "all states": "national",
        "nationwide": "national",
        "nyc": "new_york",
        "new york state": "new_york",
    }
    if s in aliases:
        return aliases[s]

    # Two-letter USPS abbreviation
    if len(raw) == 2 and raw.isalpha():
        slug = _USPS_TO_SLUG.get(raw.upper())
        if slug:
            return slug

    return s.replace(" ", "_")


def _vera_state_files(state_slug: str) -> List[Path]:
    if state_slug == "texas":
        return [DATA_DIR / "texas_pt1.csv", DATA_DIR / "texas_pt2.csv"]
    return [DATA_DIR / f"{state_slug}.csv"]


def _read_facilities_metadata() -> pd.DataFrame:
    path = DATA_DIR / "facilities.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    if "detention_facility_code" in df.columns:
        df["detention_facility_code"] = df["detention_facility_code"].astype(str)
    return df


def _vera_two_pass_window(
    csv_paths: List[Path],
    days: int,
    usecols: List[str],
) -> Tuple[pd.Timestamp, pd.DataFrame]:
    """
    Two-pass read to avoid loading full state history into memory:
    pass 1 finds max(date), pass 2 collects only the last N days of rows.
    """
    max_dt: Optional[pd.Timestamp] = None
    for p in csv_paths:
        if not p.exists():
            continue
        for chunk in pd.read_csv(p, usecols=usecols, chunksize=200_000, parse_dates=["date"]):
            if chunk.empty:
                continue
            dt = chunk["date"].max()
            if pd.notna(dt) and (max_dt is None or dt > max_dt):
                max_dt = dt

    if max_dt is None:
        raise FileNotFoundError("No readable VERA CSV data found for requested state.")

    start_dt = (max_dt - pd.Timedelta(days=days - 1)).normalize()
    window_chunks: List[pd.DataFrame] = []
    for p in csv_paths:
        if not p.exists():
            continue
        for chunk in pd.read_csv(p, usecols=usecols, chunksize=200_000, parse_dates=["date"]):
            if chunk.empty:
                continue
            chunk = chunk[chunk["date"] >= start_dt]
            if not chunk.empty:
                window_chunks.append(chunk)

    window_df = pd.concat(window_chunks, ignore_index=True) if window_chunks else pd.DataFrame(columns=usecols)
    return max_dt.normalize(), window_df


def _statewide_total_near_date(
    csv_paths: List[Path],
    metric: str,
    target_date: pd.Timestamp,
    tolerance_days: int = 7,
) -> Tuple[Optional[float], Optional[pd.Timestamp], str]:
    """
    Compute state-wide total on target_date (or nearest within +/- tolerance_days).
    Returns (value, matched_date, method) where method in:
    - "exact_date"
    - "nearest_available"
    - "unavailable"
    """
    start = (target_date - pd.Timedelta(days=tolerance_days)).normalize()
    end = (target_date + pd.Timedelta(days=tolerance_days)).normalize()
    totals_by_date: Dict[pd.Timestamp, float] = {}

    for p in csv_paths:
        if not p.exists():
            continue
        for chunk in pd.read_csv(p, usecols=["date", metric], chunksize=200_000, parse_dates=["date"]):
            if chunk.empty:
                continue
            chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce").dt.normalize()
            chunk = chunk[(chunk["date"] >= start) & (chunk["date"] <= end)]
            if chunk.empty:
                continue
            chunk[metric] = pd.to_numeric(chunk[metric], errors="coerce").fillna(0.0)
            grouped = chunk.groupby("date", as_index=False)[metric].sum()
            for _, r in grouped.iterrows():
                d = pd.Timestamp(r["date"]).normalize()
                totals_by_date[d] = totals_by_date.get(d, 0.0) + float(r[metric])

    if not totals_by_date:
        return None, None, "unavailable"
    if target_date in totals_by_date:
        return float(totals_by_date[target_date]), target_date, "exact_date"

    nearest = sorted(
        totals_by_date.keys(),
        key=lambda d: (abs((d - target_date).days), d),
    )[0]
    return float(totals_by_date[nearest]), nearest, "nearest_available"


_SLUG_TO_USPS: Dict[str, str] = {v: k for k, v in _USPS_TO_SLUG.items()}


def _slug_to_place_title(slug: str) -> str:
    if slug == "national":
        return "United States"
    return " ".join(w.capitalize() for w in slug.split("_"))


def _derive_location_tags(location: str) -> List[str]:
    """
    Produce human-readable city/state-oriented tags from the query location string.
    NewsAPI does not return geographic metadata per article; tags reflect the *query scope*.
    """
    raw = (location or "").strip()
    tags: List[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        t = (tag or "").strip()
        if not t:
            return
        k = t.lower()
        if k not in seen:
            seen.add(k)
            tags.append(t)

    if not raw:
        add("national")
        add("United States")
        return tags

    slug_whole = _normalize_state_to_slug(raw)
    if slug_whole == "national":
        add("national")
        add("United States")
        return tags

    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) >= 2:
            city_guess, state_guess = parts[0], parts[-1]
            add(city_guess)
            st_slug = _normalize_state_to_slug(state_guess)
            if st_slug != "national":
                add(_slug_to_place_title(st_slug))
                usps = _SLUG_TO_USPS.get(st_slug)
                if usps:
                    add(usps)
        add(raw)
        return tags

    st_slug = slug_whole
    usps = _SLUG_TO_USPS.get(st_slug)
    if usps:
        add(_slug_to_place_title(st_slug))
        add(usps)
    else:
        # Likely a city or region name without a parseable state
        add(raw)

    return tags


def _infer_state_slug_from_question(user_question: str) -> str:
    """
    Best-effort geographic scope extraction for fallback tool backfilling.
    Returns a VERA-compatible slug (e.g., 'texas', 'new_york', or 'national').
    """
    q = (user_question or "").strip()
    q_lower = q.lower()
    if any(k in q_lower for k in ["national", "nationwide", "united states", "u.s.", "u.s", "usa"]):
        return "national"

    # Prefer explicit full state names in natural language.
    padded = f" {q_lower} "
    for slug in _USPS_TO_SLUG.values():
        name = slug.replace("_", " ")
        if f" {name} " in padded:
            return slug

    # Then look for explicit uppercase USPS tokens in the original text (e.g., TX, NY).
    for token in re.findall(r"\b[A-Z]{2}\b", q):
        slug = _USPS_TO_SLUG.get(token.upper())
        if slug:
            return slug

    return "national"


def _extract_text_excerpt_from_html(html: str, max_chars: int) -> str:
    """
    Convert HTML into a compact text excerpt for grounding.
    Heuristic-only: prefers article/main content, then strips scripts/styles/tags.
    """
    if not html:
        return ""

    # Try to prioritize article-like containers before full-body fallback.
    m = re.search(
        r"<article\b[^>]*>(.*?)</article>|<main\b[^>]*>(.*?)</main>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    source = m.group(1) if m and m.group(1) else (m.group(2) if m and m.group(2) else html)

    # Remove non-content noise.
    source = re.sub(r"<script\b[^>]*>.*?</script>", " ", source, flags=re.IGNORECASE | re.DOTALL)
    source = re.sub(r"<style\b[^>]*>.*?</style>", " ", source, flags=re.IGNORECASE | re.DOTALL)
    source = re.sub(r"<!--.*?-->", " ", source, flags=re.DOTALL)
    source = re.sub(r"<[^>]+>", " ", source)
    source = unescape(source)
    source = re.sub(r"\s+", " ", source).strip()
    if not source:
        return ""
    return source[:max_chars].rstrip()


def _fetch_article_excerpt(url: str, max_chars: int, timeout_sec: float) -> Dict[str, Any]:
    """
    Best-effort article text fetch for extra grounding.
    Returns excerpt + metadata; never raises.
    """
    if not url:
        return {"article_excerpt": "", "excerpt_status": "missing_url"}
    try:
        resp = requests.get(
            url,
            timeout=timeout_sec,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; lab6-multi-agent-tools/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        if resp.status_code != 200:
            return {
                "article_excerpt": "",
                "excerpt_status": "http_error",
                "excerpt_error": f"HTTP {resp.status_code}",
            }
        excerpt = _extract_text_excerpt_from_html(resp.text, max_chars=max_chars)
        if not excerpt:
            return {
                "article_excerpt": "",
                "excerpt_status": "empty_or_unreadable",
            }
        return {
            "article_excerpt": excerpt,
            "excerpt_status": "ok",
            "excerpt_char_count": len(excerpt),
        }
    except requests.exceptions.RequestException as e:
        return {
            "article_excerpt": "",
            "excerpt_status": "fetch_failed",
            "excerpt_error": str(e),
        }


def _is_article_scope_match(article: Dict[str, Any], location_tags: List[str]) -> bool:
    """
    Best-effort location relevance check for article rows.
    Marks an article as in-scope when state/city tags appear in title/snippet/excerpt/url.
    """
    if not location_tags:
        return True
    text = " ".join(
        [
            str(article.get("title", "")),
            str(article.get("headline", "")),
            str(article.get("description", "")),
            str(article.get("snippet", "")),
            str(article.get("article_excerpt", "")),
            str(article.get("url", "")),
        ]
    ).lower()
    if not text.strip():
        return False

    for tag in location_tags:
        t = (tag or "").strip().lower()
        if not t:
            continue
        # For short tokens like TX, require whole-word matches.
        if len(t) <= 3:
            if re.search(rf"\b{re.escape(t)}\b", text):
                return True
            continue
        if t in text:
            return True
    return False


def _is_ice_enforcement_article(article: Dict[str, Any]) -> bool:
    """
    Check whether article text is explicitly about ICE immigration enforcement/detention,
    not just unrelated topics that happen to contain short tokens like "TX".
    """
    text = " ".join(
        [
            str(article.get("title", "")),
            str(article.get("headline", "")),
            str(article.get("description", "")),
            str(article.get("snippet", "")),
            str(article.get("article_excerpt", "")),
        ]
    ).lower()
    if not text.strip():
        return False

    has_ice_term = bool(re.search(r"\bice\b", text)) or ("immigration and customs enforcement" in text)
    if not has_ice_term:
        return False

    enforcement_terms = [
        "detention",
        "detentions",
        "detainee",
        "deport",
        "removal",
        "immigration",
        "customs enforcement",
        "raid",
        "raids",
        "arrest",
        "arrests",
        "facility",
        "processing center",
        "ice officer",
    ]
    return any(term in text for term in enforcement_terms)


def _is_low_signal_source(article: Dict[str, Any]) -> bool:
    """
    Filter obviously low-signal sources that commonly duplicate sensational stories.
    This is intentionally conservative and easy to adjust.
    """
    source = str(article.get("source", "")).strip().lower()
    domain = str(article.get("domain", "")).strip().lower()
    low_signal = {
        "freerepublic.com",
        "www.freerepublic.com",
        "beforeitsnews.com",
        "www.beforeitsnews.com",
    }
    return source in low_signal or domain in low_signal


def _passes_detention_arrest_intent(article: Dict[str, Any]) -> bool:
    """
    Require explicit ICE + detention/arrest operations intent.
    Excludes personal-profile narratives unless they also include hard operational signals.
    """
    text = " ".join(
        [
            str(article.get("title", "")),
            str(article.get("headline", "")),
            str(article.get("description", "")),
            str(article.get("snippet", "")),
            str(article.get("article_excerpt", "")),
        ]
    ).lower()
    if not text.strip():
        return False

    has_ice = bool(re.search(r"\bice\b", text)) or ("immigration and customs enforcement" in text)
    if not has_ice:
        return False

    broad_terms = [
        "detention",
        "detentions",
        "detained",
        "detainee",
        "detainees",
        "arrest",
        "arrests",
        "arrested",
        "raid",
        "raids",
        "facility",
        "facilities",
        "processing center",
        "deport",
        "deportation",
        "removal",
        "custody",
        "operation",
        "enforcement",
    ]
    broad_hits = sum(1 for t in broad_terms if t in text)
    if broad_hits < 2:
        return False

    hard_operational_terms = [
        "arrest",
        "arrests",
        "arrested",
        "raid",
        "raids",
        "deport",
        "deportation",
        "removal",
        "operation",
        "enforcement operation",
    ]
    has_hard_operational = any(t in text for t in hard_operational_terms)

    profile_terms = [
        "niece",
        "nephew",
        "former lover",
        "ex-lover",
        "girlfriend",
        "boyfriend",
        "celebrity",
        "warlord",
    ]
    has_profile_framing = any(t in text for t in profile_terms)

    if has_profile_framing and not has_hard_operational:
        return False
    return True


def _canonical_title_key(title: str) -> str:
    """
    Normalize title text for duplicate/syndicated-story suppression.
    """
    t = re.sub(r"[^a-z0-9\s]", " ", (title or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    tokens = [tok for tok in t.split(" ") if tok and tok not in {"the", "a", "an", "and", "or", "to", "of", "in"}]
    return " ".join(tokens[:14])


def _dedupe_articles_by_title(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keep only one copy of near-identical syndicated headlines.
    Input should already be sorted by preference.
    """
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for a in articles:
        key = _canonical_title_key(str(a.get("title") or a.get("headline") or ""))
        if not key:
            key = str(a.get("url", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _article_focus_score(article: Dict[str, Any]) -> int:
    """
    Score article rows for public-brief usefulness.
    Higher scores emphasize detention/arrest operations and facility context,
    and de-emphasize one-off personal-profile/sensational stories.
    """
    text = " ".join(
        [
            str(article.get("title", "")),
            str(article.get("headline", "")),
            str(article.get("description", "")),
            str(article.get("snippet", "")),
            str(article.get("article_excerpt", "")),
        ]
    ).lower()
    if not text.strip():
        return 0

    score = 0
    if bool(article.get("scope_match")):
        score += 2
    if bool(article.get("ice_relevance")):
        score += 3
    if bool(article.get("intent_match")):
        score += 3
    if not bool(article.get("low_signal_source")):
        score += 1

    # Core signals for detention/arrest/system context.
    high_value_terms = [
        "detention",
        "detentions",
        "detention center",
        "processing center",
        "facility",
        "facilities",
        "jail",
        "custody",
        "arrest",
        "arrests",
        "raid",
        "raids",
        "operation",
        "enforcement",
        "deportation",
        "removal",
    ]
    for term in high_value_terms:
        if term in text:
            score += 1

    # Penalize personal-profile framing when not paired with strong operations context.
    low_value_profile_terms = [
        "niece",
        "nephew",
        "ex-lover",
        "former lover",
        "girlfriend",
        "boyfriend",
        "celebrity",
        "warlord",
    ]
    if any(term in text for term in low_value_profile_terms):
        score -= 2

    return score


def _published_at_sort_key(article: Dict[str, Any]) -> float:
    """
    Parse NewsAPI timestamps into an epoch sort key (newest first when descending).
    """
    raw = str(article.get("published_at") or article.get("date") or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# 2) TOOL FUNCTIONS ############################################################

def get_recent_ice_articles(location: str = "national", topic: str = "", limit: int = 5) -> Dict[str, Any]:
    """
    Tool 1: Fetch recent ICE-related news articles from NewsAPI.

    Returns a JSON object with an ``articles`` list; each item includes
    headline/title, source, date, url, snippet, description, and location_tags
    (state/city strings derived from the ``location`` argument), plus a best-effort
    ``article_excerpt`` pulled from the article URL for stronger grounding, and
    ``scope_match`` indicating whether the article text appears location-relevant.

    On failure: ``articles`` is empty and ``error`` describes the problem.
    """
    api_key = os.getenv("NEWSAPI_API_KEY", "").strip()
    if not api_key:
        return {
            "articles": [],
            "error": {
                "message": "Missing NEWSAPI_API_KEY. Set it in your environment (do not commit).",
                "env_keys_required": ["NEWSAPI_API_KEY"],
            },
            "source": {"provider": "NewsAPI", "endpoint": "https://newsapi.org/"},
        }

    loc = (location or "").strip() or "United States"
    # Commas in free-text locations can make NewsAPI return zero hits; keep tags from raw `location`.
    loc_for_query = " ".join(loc.replace(",", " ").split())
    # Query tuned for ICE detention/arrest and facility context.
    q = (
        f'("ICE" OR "Immigration and Customs Enforcement") AND ({loc_for_query}) AND '
        '(detention OR detentions OR "detention center" OR detainee OR arrest OR arrests OR '
        'raid OR raids OR deportation OR removal OR facility OR "processing center") '
        'NOT ("former lover" OR ex-lover OR niece OR nephew OR warlord OR celebrity)'
    )
    if topic and str(topic).strip():
        q += f" AND ({str(topic).strip()})"

    url = "https://newsapi.org/v2/everything"
    # Restrict to the past week for "recent reporting".
    from_day = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    page_size = int(max(1, min(int(limit), 20)))
    candidate_page_size = min(20, max(page_size * 3, 10))
    params: Dict[str, Any] = {
        "q": q,
        "pageSize": candidate_page_size,
        "sortBy": "publishedAt",
        "language": "en",
        "from": from_day,
    }
    headers = {"X-Api-Key": api_key, "Accept": "application/json"}
    location_tags = _derive_location_tags(location)

    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code != 200:
        return {
            "articles": [],
            "error": {"message": f"NewsAPI error: {resp.status_code}", "details": resp.text[:500]},
            "source": {"provider": "NewsAPI", "endpoint": url, "query": {k: v for k, v in params.items()}},
        }

    data = resp.json()
    if data.get("status") != "ok":
        return {
            "articles": [],
            "error": {
                "message": data.get("message") or "NewsAPI returned a non-ok status.",
                "code": data.get("code"),
            },
            "source": {"provider": "NewsAPI", "endpoint": url, "query": {k: v for k, v in params.items()}},
        }

    out: List[Dict[str, Any]] = []
    for a in (data.get("articles") or [])[:candidate_page_size]:
        title = (a.get("title") or "").strip()
        description = (a.get("description") or "").strip()
        content = (a.get("content") or "").strip()
        snippet = description or content
        published = (a.get("publishedAt") or "").strip()
        url_i = (a.get("url") or "").strip()
        do_excerpt = len(out) < max(0, NEWS_EXCERPT_ARTICLE_LIMIT)
        excerpt_obj = (
            _fetch_article_excerpt(url_i, max_chars=NEWS_EXCERPT_MAX_CHARS, timeout_sec=NEWS_EXCERPT_TIMEOUT_SEC)
            if do_excerpt
            else {"article_excerpt": "", "excerpt_status": "skipped"}
        )
        out.append(
            {
                "headline": title,
                "title": title,
                "source": ((a.get("source") or {}).get("name") or "").strip(),
                "date": published,
                "published_at": published,
                "url": url_i,
                "domain": (urlparse(url_i).netloc or "").lower(),
                "snippet": snippet,
                "description": description or snippet,
                "location_tags": list(location_tags),
                "article_excerpt": excerpt_obj.get("article_excerpt", ""),
                "excerpt_status": excerpt_obj.get("excerpt_status", "unknown"),
                "excerpt_char_count": excerpt_obj.get("excerpt_char_count", 0),
                "excerpt_error": excerpt_obj.get("excerpt_error"),
            }
        )
        out[-1]["scope_match"] = _is_article_scope_match(out[-1], location_tags)
        out[-1]["ice_relevance"] = _is_ice_enforcement_article(out[-1])
        out[-1]["intent_match"] = _passes_detention_arrest_intent(out[-1])
        out[-1]["low_signal_source"] = _is_low_signal_source(out[-1])

    scope_and_ice = [a for a in out if bool(a.get("scope_match")) and bool(a.get("ice_relevance"))]
    ice_only = [a for a in out if bool(a.get("ice_relevance"))]
    strict_scope_ice = [
        a
        for a in scope_and_ice
        if bool(a.get("intent_match")) and not bool(a.get("low_signal_source"))
    ]
    strict_scope_ice_ranked = sorted(
        strict_scope_ice,
        key=lambda a: (_article_focus_score(a), _published_at_sort_key(a)),
        reverse=True,
    )
    strict_scope_ice_dedup = _dedupe_articles_by_title(strict_scope_ice_ranked)

    strict_scope_with_low_signal = [a for a in scope_and_ice if bool(a.get("intent_match"))]
    strict_ice_only = [
        a
        for a in ice_only
        if bool(a.get("intent_match")) and not bool(a.get("low_signal_source"))
    ]
    strict_ice_only_with_low_signal = [a for a in ice_only if bool(a.get("intent_match"))]
    strict_scope_with_low_signal_ranked = sorted(
        strict_scope_with_low_signal,
        key=lambda a: (_article_focus_score(a), _published_at_sort_key(a)),
        reverse=True,
    )
    strict_scope_with_low_signal_dedup = _dedupe_articles_by_title(strict_scope_with_low_signal_ranked)
    strict_ice_only_ranked = sorted(
        strict_ice_only,
        key=lambda a: (_article_focus_score(a), _published_at_sort_key(a)),
        reverse=True,
    )
    strict_ice_only_dedup = _dedupe_articles_by_title(strict_ice_only_ranked)
    strict_ice_only_with_low_signal_ranked = sorted(
        strict_ice_only_with_low_signal,
        key=lambda a: (_article_focus_score(a), _published_at_sort_key(a)),
        reverse=True,
    )
    strict_ice_only_with_low_signal_dedup = _dedupe_articles_by_title(strict_ice_only_with_low_signal_ranked)

    # Prefer strict scope+intent first, then strict ICE intent without scope-match
    # when location tagging is too sparse/noisy in article text.
    # Keep strict intent gating to avoid weakly related profile stories.
    selected = (
        strict_scope_ice_dedup
        or strict_scope_with_low_signal_dedup
        or strict_ice_only_dedup
        or strict_ice_only_with_low_signal_dedup
    )

    return {
        "articles": selected[:page_size],
        "filtering": {
            "applied": True,
            "input_count": len(out),
            "scope_and_ice_count": len(scope_and_ice),
            "ice_only_count": len(ice_only),
            "strict_scope_ice_count": len(strict_scope_ice),
            "strict_scope_with_low_signal_count": len(strict_scope_with_low_signal),
            "strict_ice_only_count": len(strict_ice_only),
            "strict_ice_only_with_low_signal_count": len(strict_ice_only_with_low_signal),
            "low_signal_excluded_count": len(
                [a for a in scope_and_ice if bool(a.get("intent_match")) and bool(a.get("low_signal_source"))]
            ),
            "dedup_removed_count": max(0, len(strict_scope_ice_ranked) - len(strict_scope_ice_dedup)),
            "output_count": min(len(selected), page_size),
            "time_window_days": 7,
            "intent_gate": "requires_ice_plus_detention_or_arrest_operations",
        },
        "source": {
            "provider": "NewsAPI",
            "endpoint": url,
            "query": {k: v for k, v in params.items()},
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


def get_census_demographics(state: str = "national") -> Dict[str, Any]:
    """
    Tool 2: Fetch *state-level* demographics from the Census API (ACS 1-year).

    This is contextual (not detention composition). Return is JSON-friendly.
    """
    api_key = os.getenv("CENSUS_API_KEY", "").strip()
    if not api_key:
        return {
            "state": state,
            "error": {
                "message": "Missing CENSUS_API_KEY. Set it in your environment (do not commit).",
                "env_keys_required": ["CENSUS_API_KEY"],
            },
            "source": {"provider": "Census API", "dataset": "ACS 1-year", "endpoint": "https://api.census.gov/data.html"},
        }

    # Minimal, interpretable ACS fields:
    # - B01003_001E: total population
    # - B05002_013E: foreign born (total)
    # - B05001_006E: not a U.S. citizen (non-citizen)
    # - B19013_001E: median household income (USD)
    year = int(os.getenv("CENSUS_YEAR", "2023"))
    vars_ = ["B01003_001E", "B05002_013E", "B05001_006E", "B19013_001E", "NAME"]

    slug = _normalize_state_to_slug(state)
    if slug == "national":
        return {
            "state": state,
            "state_slug": slug,
            "error": {
                "message": "Census demographics tool is state-level only. Provide a specific US state.",
                "example_states": ["Texas", "TX", "New York", "NY"],
            },
            "source": {
                "provider": "Census API",
                "dataset": f"ACS 1-year {year}",
                "dataset_id": "acs/acs1",
                "variables": vars_,
            },
        }

    state_fips = _STATE_SLUG_TO_FIPS.get(slug)
    if not state_fips:
        return {
            "state": state,
            "state_slug": slug,
            "error": {
                "message": "Could not map input to a supported US state for Census lookup.",
                "hint": "Use a full US state name or 2-letter abbreviation (e.g., Texas/TX).",
            },
            "source": {
                "provider": "Census API",
                "dataset": f"ACS 1-year {year}",
                "dataset_id": "acs/acs1",
                "variables": vars_,
            },
        }

    url = f"https://api.census.gov/data/{year}/acs/acs1"
    params = {"get": ",".join(vars_), "for": f"state:{state_fips}", "key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        return {
            "state": state,
            "state_slug": slug,
            "error": {"message": "Census API request failed.", "details": str(exc)},
            "source": {"provider": "Census API", "endpoint": url, "query": params},
        }

    if resp.status_code != 200:
        return {
            "state": state,
            "state_slug": slug,
            "error": {"message": f"Census API error: {resp.status_code}", "details": resp.text[:500]},
            "source": {"provider": "Census API", "endpoint": url, "query": params},
        }

    try:
        rows = resp.json()
    except ValueError:
        return {
            "state": state,
            "state_slug": slug,
            "error": {"message": "Census API returned non-JSON response.", "details": resp.text[:500]},
            "source": {"provider": "Census API", "endpoint": url, "query": params},
        }

    if not isinstance(rows, list) or len(rows) < 2:
        return {
            "state": state,
            "state_slug": slug,
            "error": {"message": "Census API returned no state rows.", "details": rows},
            "source": {"provider": "Census API", "endpoint": url, "query": params},
        }

    header, values = rows[0], rows[1]
    row = dict(zip(header, values))

    def _to_float(value: Any) -> float:
        text = str(value).strip()
        if text in {"", "None", "null", "NaN", "-666666666"}:
            return float("nan")
        try:
            return float(text)
        except (TypeError, ValueError):
            return float("nan")

    total = _to_float(row.get("B01003_001E"))
    foreign_born = _to_float(row.get("B05002_013E"))
    non_citizen = _to_float(row.get("B05001_006E"))
    median_household_income = _to_float(row.get("B19013_001E"))

    def pct(n: float, d: float) -> Optional[float]:
        if d and d > 0 and n == n and d == d:
            return round((n / d) * 100.0, 2)
        return None

    return {
        "state": state,
        "state_slug": slug,
        "state_fips": state_fips,
        "state_name": row.get("NAME", state),
        "total_population": int(total) if total == total else None,
        "foreign_born_count": int(foreign_born) if foreign_born == foreign_born else None,
        "foreign_born_pct": pct(foreign_born, total),
        "non_citizen_count": int(non_citizen) if non_citizen == non_citizen else None,
        "non_citizen_pct": pct(non_citizen, total),
        "median_household_income_usd": (
            int(round(median_household_income)) if median_household_income == median_household_income else None
        ),
        "source": {
            "provider": "Census API",
            "dataset": f"ACS 1-year {year}",
            "dataset_id": "acs/acs1",
            "endpoint": url,
            "query": {"for": f"state:{state_fips}"},
            "variables": {
                "B01003_001E": "Total population",
                "B05002_013E": "Foreign born population",
                "B05001_006E": "Not a U.S. citizen (non-citizen)",
                "B19013_001E": "Median household income (USD)",
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


def get_vera_detention_trends(state: str = "national", metric: str = "midnight_pop", days: int = 30) -> Dict[str, Any]:
    """
    Tool 3: Summarize local VERA detention trends (state-level), computed from CSVs in ./data/.

    Output keys are stable for grounding:
    - state, metric, days
    - as_of_date, latest_value, window_avg, window_change
    - facility_count, top_facilities (joined with facilities.csv when possible)
    - source_files
    """
    state_slug = _normalize_state_to_slug(state)
    files = _vera_state_files(state_slug)
    missing = [str(p.relative_to(DATA_DIR)) for p in files if not p.exists()]
    if missing:
        available_slugs = _available_vera_state_slugs()
        return {
            "state": state,
            "state_slug": state_slug,
            "metric": metric,
            "days": int(days),
            "error": {
                "message": "Missing required local VERA CSV file(s) for this state.",
                "missing_files": missing,
                "available_state_slugs": available_slugs,
                "available_files": sorted([p.name for p in DATA_DIR.glob("*.csv")]),
                "hint": "Add the required CSV(s) under hw2/data/ or ask for a supported state.",
            },
            "source_files": [str(p) for p in files],
        }

    metric = (metric or "").strip()
    if metric not in {"daily_pop", "midnight_pop"}:
        return {
            "state": state,
            "metric": metric,
            "days": int(days),
            "error": {"message": "Unsupported metric. Use 'daily_pop' or 'midnight_pop'."},
            "source_files": [str(p) for p in files],
        }

    days = int(days)
    if days < 2 or days > 365:
        return {
            "state": state,
            "metric": metric,
            "days": days,
            "error": {"message": "days must be between 2 and 365."},
            "source_files": [str(p) for p in files],
        }

    # National file schema differs (already aggregated; no facility columns).
    if state_slug == "national":
        usecols = ["date", metric]
        as_of_date, window_df = _vera_two_pass_window(files, days=days, usecols=usecols)

        if window_df.empty:
            return {
                "state": state,
                "metric": metric,
                "days": days,
                "as_of_date": as_of_date.date().isoformat(),
                "latest_value": 0,
                "window_avg": 0.0,
                "window_change": 0,
                "facility_count": None,
                "top_facilities": [],
                "source_files": [str(p) for p in files],
            }

        window_df[metric] = pd.to_numeric(window_df[metric], errors="coerce").fillna(0.0)
        daily_totals = window_df.groupby("date", as_index=False)[metric].sum().sort_values("date")
        latest_total = float(daily_totals.iloc[-1][metric]) if not daily_totals.empty else 0.0
        first_total = float(daily_totals.iloc[0][metric]) if not daily_totals.empty else 0.0
        window_avg = float(daily_totals[metric].mean()) if not daily_totals.empty else 0.0
        yoy_target = (as_of_date - pd.DateOffset(years=1)).normalize()
        yoy_value, yoy_date, yoy_method = _statewide_total_near_date(files, metric, yoy_target, tolerance_days=7)
        yoy_change = (latest_total - yoy_value) if yoy_value is not None else None
        yoy_pct = ((yoy_change / yoy_value) * 100.0) if (yoy_value is not None and yoy_value != 0) else None

        return {
            "state": state,
            "metric": metric,
            "days": days,
            "as_of_date": as_of_date.date().isoformat(),
            "latest_value": int(round(latest_total)),
            "window_avg": round(window_avg, 2),
            "window_change": int(round(latest_total - first_total)),
            "year_ago_date": (yoy_date.date().isoformat() if yoy_date is not None else None),
            "year_ago_value": (int(round(yoy_value)) if yoy_value is not None else None),
            "year_over_year_change": (int(round(yoy_change)) if yoy_change is not None else None),
            "year_over_year_pct": (round(float(yoy_pct), 2) if yoy_pct is not None else None),
            "year_over_year_method": yoy_method,
            "facility_count": None,
            "top_facilities": [],
            "source_files": [str(p) for p in files],
        }

    usecols = ["detention_facility_code", "detention_facility_name", "state", "date", metric]
    as_of_date, window_df = _vera_two_pass_window(files, days=days, usecols=usecols)
    if window_df.empty:
        return {
            "state": state,
            "metric": metric,
            "days": days,
            "as_of_date": as_of_date.date().isoformat(),
            "latest_value": 0,
            "window_avg": 0.0,
            "window_change": 0,
            "facility_count": 0,
            "top_facilities": [],
            "source_files": [str(p) for p in files],
        }

    # Coerce numeric
    window_df[metric] = pd.to_numeric(window_df[metric], errors="coerce").fillna(0.0)

    # State-wide daily total time series
    daily_totals = window_df.groupby("date", as_index=False)[metric].sum().sort_values("date")
    latest_total = float(daily_totals.iloc[-1][metric]) if not daily_totals.empty else 0.0
    first_total = float(daily_totals.iloc[0][metric]) if not daily_totals.empty else 0.0
    window_avg = float(daily_totals[metric].mean()) if not daily_totals.empty else 0.0
    yoy_target = (as_of_date - pd.DateOffset(years=1)).normalize()
    yoy_value, yoy_date, yoy_method = _statewide_total_near_date(files, metric, yoy_target, tolerance_days=7)
    yoy_change = (latest_total - yoy_value) if yoy_value is not None else None
    yoy_pct = ((yoy_change / yoy_value) * 100.0) if (yoy_value is not None and yoy_value != 0) else None

    # Top facilities at as_of_date
    latest_rows = window_df[window_df["date"] == as_of_date].copy()
    fac_latest = (
        latest_rows.groupby(["detention_facility_code", "detention_facility_name"], as_index=False)[metric]
        .sum()
        .sort_values(metric, ascending=False)
    )

    facilities_meta = _read_facilities_metadata()
    if not facilities_meta.empty and "detention_facility_code" in facilities_meta.columns:
        meta_cols = [
            c
            for c in [
                "detention_facility_code",
                "detention_facility_name",
                "city",
                "county",
                "state",
                "type_grouped",
                "type_detailed",
            ]
            if c in facilities_meta.columns
        ]
        fac_latest = fac_latest.merge(
            facilities_meta[meta_cols],
            how="left",
            left_on="detention_facility_code",
            right_on="detention_facility_code",
            suffixes=("_csv", "_meta"),
        )

    top = []
    for _, r in fac_latest.head(5).iterrows():
        name_meta = r.get("detention_facility_name_meta")
        name_csv = r.get("detention_facility_name_csv")
        if name_meta is not None and not pd.isna(name_meta) and str(name_meta).strip():
            display_name = str(name_meta)
        elif name_csv is not None and not pd.isna(name_csv) and str(name_csv).strip():
            display_name = str(name_csv)
        else:
            display_name = str(r.get("detention_facility_name", "")) if r.get("detention_facility_name") is not None else ""

        top.append(
            {
                "facility_code": str(r.get("detention_facility_code", "")),
                "facility_name": display_name,
                "city": (None if pd.isna(r.get("city")) else str(r.get("city"))),
                "county": (None if pd.isna(r.get("county")) else str(r.get("county"))),
                "state": (None if pd.isna(r.get("state")) else str(r.get("state"))),
                "type_grouped": (None if pd.isna(r.get("type_grouped")) else str(r.get("type_grouped"))),
                "latest_metric_value": float(r.get(metric, 0.0)),
            }
        )

    facility_count = int((fac_latest[metric] > 0).sum()) if not fac_latest.empty else 0

    return {
        "state": state,
        "metric": metric,
        "days": days,
        "as_of_date": as_of_date.date().isoformat(),
        "latest_value": int(round(latest_total)),
        "window_avg": round(window_avg, 2),
        "window_change": int(round(latest_total - first_total)),
        "year_ago_date": (yoy_date.date().isoformat() if yoy_date is not None else None),
        "year_ago_value": (int(round(yoy_value)) if yoy_value is not None else None),
        "year_over_year_change": (int(round(yoy_change)) if yoy_change is not None else None),
        "year_over_year_pct": (round(float(yoy_pct), 2) if yoy_pct is not None else None),
        "year_over_year_method": yoy_method,
        "facility_count": facility_count,
        "top_facilities": top,
        "source_files": [str(p) for p in files],
    }


# 3) TOOL METADATA (function calling schemas) ##################################

tool_get_recent_ice_articles = {
    "type": "function",
    "function": {
        "name": "get_recent_ice_articles",
        "description": "Fetch recent ICE-related news articles for a location (state, city, or national). Returns JSON with an articles array; each item has headline, title, source, date, url, snippet, description, location_tags, best-effort article_excerpt text from the URL, scope_match (location relevance), and ice_relevance (ICE-enforcement relevance).",
        "parameters": {
            "type": "object",
            "required": ["location"],
            "properties": {
                "location": {"type": "string", "description": "State or city to focus on (e.g., 'Texas', 'New York', 'Houston')."},
                "topic": {"type": "string", "description": "Optional extra topic keywords (e.g., 'detention', 'raids'). Default empty."},
                "limit": {"type": "number", "description": "Max number of articles to return (1-20). Default 5."},
            },
        },
    },
}

tool_get_census_demographics = {
    "type": "function",
    "function": {
        "name": "get_census_demographics",
        "description": "Fetch state-level demographic context from the US Census API (ACS 1-year). Returns totals and foreign-born/non-citizen counts and percentages with variable provenance.",
        "parameters": {
            "type": "object",
            "required": ["state"],
            "properties": {
                "state": {"type": "string", "description": "US state name or abbreviation (e.g., 'Texas', 'TX', 'New York', 'NY')."},
            },
        },
    },
}

tool_get_vera_detention_trends = {
    "type": "function",
    "function": {
        "name": "get_vera_detention_trends",
        "description": "Summarize local VERA ICE detention trends for a state over the last N days. Returns latest total, trailing average, change, year-over-year same-date comparison, facility count, and top facilities.",
        "parameters": {
            "type": "object",
            "required": ["state"],
            "properties": {
                "state": {"type": "string", "description": "US state name/abbrev, or 'national' for national.csv. Example: 'Texas'/'TX', 'New York'/'NY'."},
                "metric": {"type": "string", "description": "Which metric to use: 'midnight_pop' (default) or 'daily_pop'."},
                "days": {"type": "number", "description": "Trailing window size in days (2-365). Default 30."},
            },
        },
    },
}


# 4) AGENT PROMPTS #############################################################

AGENT1_ROLE = """You are Agent 1: Research / Dataset Agent.
Your job is to gather evidence using the provided tools only—no narrative, no analysis.

Hard requirements (same assistant turn; issue parallel tool calls if the API allows):
1) Call get_vera_detention_trends exactly once.
   - Choose the most relevant US state from the user question.
   - If the question is national/unspecified, use state="national".
   - Defaults unless the user specifies otherwise: metric="midnight_pop", days=30.
   - If local VERA files are missing, still call the tool; preserve its structured error in the tool output.

2) Call get_recent_ice_articles exactly once.
   - Set location to the same geographic scope as the VERA call (e.g. "Texas" or "TX" for Texas, "New York" or "NY" for New York, "United States" or "national" when state is national).
   - Use topic="" unless the user clearly asks for a narrower topic; limit=5 unless they ask for more (max 20).

3) Call get_census_demographics exactly once.
   - Use the same state used for VERA.
   - If the question is national/unspecified, still call it with state="national" and preserve any structured tool error.

Do not reply with prose; only invoke these three tools.
"""

AGENT2_ROLE = """You are a public information reporting agent for an ICE activity dashboard.

Your job is to write a grounded regional briefing using only the structured evidence provided in the user message from three sources:
1) Retrieved ICE-related article matches (from a search step over Agent 1's evidence JSON)
2) VERA detention trends/context
3) Census demographic context

Use only the provided evidence. Do not use outside knowledge.
Do not call tools.
Do not make assumptions about people who were detained unless that information is explicitly stated in the retrieved evidence.
Do not claim causation between demographic characteristics and ICE activity.
Do not speculate about unreported events.
If a section has limited data or an error field, state that limitation clearly.
Numerical fidelity is strict: copy values exactly from JSON fields; do not swap metrics.

This is a location-based public brief. Keep claims careful and neutral:
- retrieved_news_matches = reported events (already query-matched by the retrieval step)
- get_vera_detention_trends = detention system context
- get_census_demographics = community context

Focus on what can be responsibly inferred from these sources:
- what has been reported in this location,
- what detention footprint/trend context exists,
- what broader community context surrounds this region.

Do NOT claim that regional demographics are the same as the demographics of detained individuals unless explicitly supported by evidence.
Do NOT present statewide detention totals as counts for a single facility.

Output format (use exactly these headings):

# {Location} ICE Reporting, Detention, and Community Context Brief

## Recent Reporting
- Summarize the most relevant recent ICE-related articles.
- Mention dates, locations, and themes when available.
- Use 2-5 retrieved stories when available and prefer scope-matched/local evidence.
- Prefer detention/arrest/enforcement-pattern coverage over one-off personal-profile stories when both are available.
- If no qualifying detention/arrest stories are present in the filtered evidence, state that clearly instead of filling with weakly related stories.
- Treat articles as in-location only when they are scope-matched in the provided evidence; otherwise label as out-of-scope context or omit.
- If retrieval metadata says out-of-scope items were included, add a one-line disclaimer.

## Detention Context
- Summarize the VERA detention information for the region.
- Include available metric/date/count/trend signals (for example: as_of_date, latest_value, window_avg, window_change, facility_count).
- Mention notable facility concentration or top facilities when available.
- Do not conflate fields: `window_change` is change within the selected trailing window; `year_over_year_change` compares latest_value to year_ago_value.

## Community Context
- Summarize Census demographic context for the region.
- Use only provided measures (for example: total_population, foreign_born_pct, non_citizen_pct, median_household_income_usd).

## What Stands Out
- Write 2-4 sentences synthesizing the three sources.
- Focus on supported patterns (reported events + detention context + community setting).
- If evidence is sparse or mixed, say so directly.

## Sources
- List article headlines and URLs from the provided evidence.
- Briefly note VERA and Census as supporting datasets used in this brief.
- For VERA, cite only provided `source_files`. For Census, cite only provided `source.endpoint`/dataset fields. Never invent or swap source URLs.

Tone: neutral, factual, and accessible for the public."""


# 5) CHAIN + HARNESS ###########################################################

def _location_string_for_newsapi(state_arg: str) -> str:
    """Map VERA-style state argument to a NewsAPI location string."""
    slug = _normalize_state_to_slug(state_arg)
    if slug == "national":
        return "United States"
    return _slug_to_place_title(slug)


def _backfill_missing_tools_if_needed(agent1_output: Any, user_question: str) -> Any:
    """
    Some models emit fewer tool calls than requested. Ensure Agent 1 output includes:
    - get_vera_detention_trends
    - get_recent_ice_articles
    - get_census_demographics

    This normalizes direct dict payloads into tool-call wrappers and backfills any
    missing tool outputs so downstream processing always has all three sources.
    """
    def _parse_args(raw_args: Any) -> Dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                loaded = json.loads(raw_args)
            except json.JSONDecodeError:
                return {}
            return loaded if isinstance(loaded, dict) else {}
        return {}

    guessed_slug = _infer_state_slug_from_question(user_question)
    guessed_state = _slug_to_place_title(guessed_slug) if guessed_slug != "national" else "national"
    guessed_loc = _location_string_for_newsapi(guessed_state)

    tool_calls: List[Dict[str, Any]] = []

    if isinstance(agent1_output, list):
        tool_calls = [tc for tc in agent1_output if isinstance(tc, dict)]
    if isinstance(agent1_output, dict):
        if isinstance(agent1_output.get("articles"), list):
            tool_calls = [
                {
                    "function": {
                        "name": "get_recent_ice_articles",
                        "arguments": json.dumps({"location": guessed_loc, "topic": "", "limit": 5}),
                    },
                    "output": agent1_output,
                },
            ]
        elif (
            "latest_value" in agent1_output
            or "metric" in agent1_output
            or ("error" in agent1_output and "state" in agent1_output)
        ):
            state_hint = str(agent1_output.get("state") or guessed_state or "national")
            tool_calls = [
                {
                    "function": {
                        "name": "get_vera_detention_trends",
                        "arguments": json.dumps(
                            {"state": state_hint, "metric": agent1_output.get("metric", "midnight_pop"), "days": 30}
                        ),
                    },
                    "output": agent1_output,
                },
            ]
        elif (
            "total_population" in agent1_output
            or "foreign_born_pct" in agent1_output
            or "non_citizen_pct" in agent1_output
            or ("state_fips" in agent1_output)
        ):
            state_hint = str(agent1_output.get("state") or guessed_state or "national")
            tool_calls = [
                {
                    "function": {
                        "name": "get_census_demographics",
                        "arguments": json.dumps({"state": state_hint}),
                    },
                    "output": agent1_output,
                }
            ]

    if not tool_calls:
        return agent1_output

    called = {(tc.get("function") or {}).get("name") for tc in tool_calls if isinstance(tc, dict)}

    state_hint = guessed_state
    for tc in tool_calls:
        fn = (tc.get("function") or {}).get("name")
        args = _parse_args((tc.get("function") or {}).get("arguments"))
        out = tc.get("output")
        if fn in {"get_vera_detention_trends", "get_census_demographics"}:
            state_hint = str(args.get("state") or (out.get("state") if isinstance(out, dict) else "") or state_hint)
            break
        if fn == "get_recent_ice_articles":
            state_hint = str(args.get("location") or state_hint)

    state_hint = state_hint or guessed_state
    news_location = _location_string_for_newsapi(state_hint)

    if "get_vera_detention_trends" not in called:
        tool_calls.append(
            {
                "function": {
                    "name": "get_vera_detention_trends",
                    "arguments": json.dumps({"state": state_hint, "metric": "midnight_pop", "days": 30}),
                },
                "output": get_vera_detention_trends(state=state_hint, metric="midnight_pop", days=30),
            }
        )
    if "get_recent_ice_articles" not in called:
        tool_calls.append(
            {
                "function": {
                    "name": "get_recent_ice_articles",
                    "arguments": json.dumps({"location": news_location, "topic": "", "limit": 5}),
                },
                "output": get_recent_ice_articles(location=news_location, topic="", limit=5),
            }
        )
    if "get_census_demographics" not in called:
        tool_calls.append(
            {
                "function": {
                    "name": "get_census_demographics",
                    "arguments": json.dumps({"state": state_hint}),
                },
                "output": get_census_demographics(state=state_hint),
            }
        )

    return tool_calls


def _bundle_tool_calls(tool_calls: Any, user_question: str) -> Dict[str, Any]:
    """
    functions.agent_run(..., output="tools") returns a list of tool_calls with outputs.
    Convert that into a single evidence JSON dataset for Agent 2.
    """
    tools_out: Dict[str, Any] = {}
    raw_agent1: Any = None

    # In practice (and in the dsai examples), agent_run(...) often returns the tool output
    # directly (e.g., a DataFrame or dict). Support both shapes:
    # - list[tool_call{function:{name,arguments}, output:...}]
    # - dict / str (direct tool output or plain text)
    if not isinstance(tool_calls, list):
        raw_agent1 = tool_calls
        if isinstance(tool_calls, dict):
            if isinstance(tool_calls.get("articles"), list):
                tools_out["get_recent_ice_articles"] = {"arguments": None, "output": tool_calls}
            elif (
                "total_population" in tool_calls
                or "foreign_born_pct" in tool_calls
                or "non_citizen_pct" in tool_calls
                or tool_calls.get("state_fips") is not None
            ):
                tools_out["get_census_demographics"] = {"arguments": None, "output": tool_calls}
            elif "latest_value" in tool_calls or "metric" in tool_calls or tool_calls.get("state") is not None:
                tools_out["get_vera_detention_trends"] = {"arguments": None, "output": tool_calls}
        tool_calls = []

    for tc in (tool_calls or []):
        if not isinstance(tc, dict):
            continue
        fn = (tc.get("function") or {}).get("name")
        if not fn:
            continue
        tools_out[fn] = {
            "arguments": (tc.get("function") or {}).get("arguments"),
            "output": tc.get("output"),
        }
    return {
        "question": user_question,
        "retrieved_at": datetime.utcnow().isoformat() + "Z",
        "agent1_raw": raw_agent1,
        "tools": tools_out,
    }


def _write_agent1_evidence_json(dataset: Dict[str, Any], user_question: str) -> Path:
    """
    Persist Agent 1 evidence for a deterministic retrieval step (Lab 2 style RAG).
    """
    EVIDENCE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_path = EVIDENCE_STORE_DIR / f"agent1_evidence_{stamp}.json"

    news_out = (((dataset.get("tools") or {}).get("get_recent_ice_articles") or {}).get("output")) or {}
    vera_out = (((dataset.get("tools") or {}).get("get_vera_detention_trends") or {}).get("output")) or {}
    census_out = (((dataset.get("tools") or {}).get("get_census_demographics") or {}).get("output")) or {}

    payload = {
        "question": user_question,
        "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "records": {
            "news_articles": (news_out.get("articles") if isinstance(news_out, dict) else []),
            "vera_detention": vera_out,
            "census_demographics": census_out,
        },
        "dataset_json": dataset,
    }

    with evidence_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return evidence_path


def _query_terms(text: str) -> List[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "what", "been",
        "have", "about", "lately", "would", "could", "should", "where", "when",
        "who", "how", "are", "was", "were", "has", "had", "ice",
    }
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in toks if len(t) >= 3 and t not in stop]


def _retrieve_related_articles_from_evidence(
    evidence_path: Path, user_query: str, limit: int = 5
) -> Dict[str, Any]:
    """
    Search the persisted Agent 1 evidence JSON for query-related article rows.
    """
    try:
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "query": user_query,
            "evidence_file": str(evidence_path),
            "articles": [],
            "error": {"message": "Could not read evidence JSON for retrieval.", "details": str(exc)},
        }

    records = (raw.get("records") or {})
    articles = records.get("news_articles") or []
    if not isinstance(articles, list):
        articles = []

    terms = _query_terms(user_query)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in articles:
        if not isinstance(row, dict):
            continue
        blob = " ".join(
            str(row.get(k, "") or "")
            for k in ("headline", "title", "snippet", "description", "article_excerpt", "source")
        )
        tags = row.get("location_tags")
        if isinstance(tags, list):
            blob += " " + " ".join(str(t) for t in tags)
        blob_l = blob.lower()

        term_hits = sum(1 for t in terms if t in blob_l)
        retrieval_score = float(term_hits) * 3.0
        if bool(row.get("scope_match")):
            retrieval_score += 2.0
        if bool(row.get("ice_relevance")):
            retrieval_score += 2.0
        if bool(row.get("intent_match")):
            retrieval_score += 2.0
        retrieval_score += float(_article_focus_score(row))

        enriched = dict(row)
        enriched["retrieval_score"] = round(retrieval_score, 3)
        scored.append((retrieval_score, enriched))

    scored.sort(key=lambda item: (item[0], _published_at_sort_key(item[1])), reverse=True)
    selected = [item[1] for item in scored[: max(1, min(int(limit), 20))]]
    out_of_scope_count = len([a for a in selected if not bool(a.get("scope_match"))])

    return {
        "query": user_query,
        "evidence_file": str(evidence_path),
        "total_articles_indexed": len(articles),
        "articles": selected,
        "retrieval": {
            "method": "keyword-match + tool-signals ranking",
            "query_terms": terms,
            "output_count": len(selected),
            "out_of_scope_context_included": bool(out_of_scope_count),
            "out_of_scope_context_count": out_of_scope_count,
        },
    }


def _vera_block_for_agent2(dataset: Dict[str, Any]) -> Any:
    """Prefer bundled tool output; fall back to agent1_raw when it is the VERA dict."""
    out = (((dataset.get("tools") or {}).get("get_vera_detention_trends") or {}).get("output"))
    if out is not None:
        return out
    raw = dataset.get("agent1_raw")
    if isinstance(raw, dict) and (
        "latest_value" in raw or "error" in raw or raw.get("metric") is not None
    ):
        return raw
    return {}


def _articles_block_for_agent2(evidence_json_path: Path, user_question: str) -> Any:
    """Retrieve query-related article rows from persisted Agent 1 evidence JSON."""
    return _retrieve_related_articles_from_evidence(
        evidence_path=evidence_json_path,
        user_query=user_question,
        limit=5,
    )


def _census_block_for_agent2(dataset: Dict[str, Any]) -> Any:
    """Census demographics output for Agent 2 grounding."""
    out = (((dataset.get("tools") or {}).get("get_census_demographics") or {}).get("output"))
    if out is not None:
        return out
    raw = dataset.get("agent1_raw")
    if isinstance(raw, dict) and (
        "total_population" in raw
        or "foreign_born_pct" in raw
        or "non_citizen_pct" in raw
        or raw.get("state_fips") is not None
    ):
        return raw
    return {}


def run_chain(user_question: str) -> Dict[str, Any]:
    """
    Two-agent chain:
    - Agent 1 calls get_vera_detention_trends, get_recent_ice_articles, and
      get_census_demographics (output="tools" so tool results are returned).
    - Persist Agent 1 evidence JSON, run retrieval over that JSON for query-related news,
      then Agent 2 consumes (retrieved articles + VERA + Census) for a grounded report.
    Timeouts: AGENT1_CHAIN_TIMEOUT_SEC, AGENT2_CHAIN_TIMEOUT_SEC.
    """
    def _agent1_call() -> Any:
        return agent_run(
            role=AGENT1_ROLE,
            task=user_question,
            model=MODEL,
            output="tools",
            tools=[tool_get_vera_detention_trends, tool_get_recent_ice_articles, tool_get_census_demographics],
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_agent1_call)
            agent1_output = fut.result(timeout=AGENT1_CHAIN_TIMEOUT_SEC)
    except FuturesTimeoutError:
        print(
            f"ERROR: Agent 1 did not finish within {int(AGENT1_CHAIN_TIMEOUT_SEC)} seconds. "
            "Check that Ollama is running, the model is loaded, and try a smaller/faster model or raise OLLAMA_HTTP_TIMEOUT.",
            file=sys.stderr,
        )
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(
            f"ERROR: Request to Ollama failed ({e}). If you are using a remote host, set OLLAMA_HOST and ensure the server is reachable.",
            file=sys.stderr,
        )
        sys.exit(1)

    agent1_output = _backfill_missing_tools_if_needed(agent1_output, user_question=user_question)
    dataset = _bundle_tool_calls(agent1_output, user_question=user_question)
    evidence_json_path = _write_agent1_evidence_json(dataset=dataset, user_question=user_question)
    retrieved_articles = _articles_block_for_agent2(
        evidence_json_path=evidence_json_path,
        user_question=user_question,
    )
    agent2_task = json.dumps(
        {
            "user_question": user_question,
            "evidence_json_file": str(evidence_json_path),
            "retrieved_news_matches": retrieved_articles,
            "vera_statistics_from_data_files": _vera_block_for_agent2(dataset),
            "census_demographics_by_state": _census_block_for_agent2(dataset),
        },
        indent=2,
        default=str,
    )

    def _agent2_call() -> str:
        return agent_run(
            role=AGENT2_ROLE,
            task=agent2_task,
            model=MODEL,
            output="text",
            tools=None,
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_agent2_call)
            agent2_report = fut.result(timeout=AGENT2_CHAIN_TIMEOUT_SEC)
    except FuturesTimeoutError:
        print(
            f"ERROR: Agent 2 did not finish within {int(AGENT2_CHAIN_TIMEOUT_SEC)} seconds. "
            "Try a faster model, increase AGENT2_CHAIN_TIMEOUT_SEC, or increase OLLAMA_HTTP_TIMEOUT.",
            file=sys.stderr,
        )
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(
            f"ERROR: Agent 2 request to Ollama failed ({e}).",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "agent1_tool_calls": agent1_output,
        "dataset_json": dataset,
        "agent1_evidence_json_file": str(evidence_json_path),
        "retrieved_news_matches": retrieved_articles,
        "agent2_report": agent2_report,
    }


if __name__ == "__main__":
    print("MODEL =", MODEL)
    print("PORT  =", PORT)
    print("OLLAMA_HOST =", OLLAMA_HOST)
    print()

    # Test harness (single prompt), mirroring dsai/08_function_calling/03_agents_with_function_calling.py
    messages = [
        {
            "role": "user",
            "content": "What has been happening with ICE detention in New York lately?",
        }
    ]
    user_question = messages[-1]["content"]

    print("=" * 88)
    print("TEST PROMPT:", user_question)
    print("-" * 88)
    result = run_chain(user_question)
    print("Agent 1 tool output (raw):")
    print(json.dumps(result["agent1_tool_calls"], indent=2, default=str)[:4000])
    print()
    print("Evidence dataset JSON (for grounding):")
    print(json.dumps(result["dataset_json"], indent=2, default=str)[:4000])
    print()
    print("Agent 1 evidence JSON file:")
    print(str(result.get("agent1_evidence_json_file")))
    print()
    print("Retrieved news matches (from evidence search):")
    print(json.dumps(result.get("retrieved_news_matches", {}), indent=2, default=str)[:4000])
    print()
    print("Agent 2 report:")
    print(str(result["agent2_report"])[:4000])
    print()
