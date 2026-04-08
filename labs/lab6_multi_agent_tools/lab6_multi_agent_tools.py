"""
Lab 6 — Multi-agent tools

Single runnable script that demonstrates:
- Tool functions (one per source)
- Tool metadata (JSON schema) for function calling
- Two-agent chain with agent_run(): Agent 1 (tools) -> Agent 2 (grounded report)

Environment variables (do not commit secrets):
- NEWSAPI_API_KEY: required for get_recent_ice_articles() to call NewsAPI
- CENSUS_API_KEY: required for get_census_demographics() to call the Census API

This script is intentionally runnable even without those keys: the tools will return
structured error payloads explaining what’s missing, while the VERA tool runs locally.

Numbers in CSVs are aggregated by Python (get_vera_detention_trends); the LLM does not
read the data folder. If Agent 1’s tool output JSON is correct but Agent 2’s report
wrong, that is usually paraphrase or hallucination in the second model call, not bad file IO.

Optional tuning (defaults keep total runtime predictable):
- OLLAMA_HTTP_TIMEOUT: seconds for each Ollama HTTP request (default 25)
- AGENT1_CHAIN_TIMEOUT_SEC: max seconds for Agent 1 to finish (default 30); on timeout the script exits with an error
- AGENT2_CHAIN_TIMEOUT_SEC: max seconds for Agent 2 (report) to finish (default 30); on timeout the script exits with an error
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests


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
OLLAMA_HTTP_TIMEOUT = float(os.getenv("OLLAMA_HTTP_TIMEOUT", "25"))
# Max wall-clock time for Agent 1 (LLM + tool execution). If exceeded, exit with an error.
AGENT1_CHAIN_TIMEOUT_SEC = float(os.getenv("AGENT1_CHAIN_TIMEOUT_SEC", "30"))
# Max wall-clock time for Agent 2 (report, no tools). If exceeded, exit with an error.
AGENT2_CHAIN_TIMEOUT_SEC = float(os.getenv("AGENT2_CHAIN_TIMEOUT_SEC", "30"))


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


# 2) TOOL FUNCTIONS ############################################################

def get_recent_ice_articles(location: str = "national", topic: str = "", limit: int = 5) -> Dict[str, Any]:
    """
    Tool 1: Fetch recent ICE-related news articles from NewsAPI.

    Returns JSON:
    - { "articles": [...], "source": {...} }
    - or { "articles": [], "error": {...}, "source": {...} }
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

    q_parts = [p for p in ["ICE immigration detention", location, topic] if p and p.strip()]
    q = " ".join(q_parts)

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": q,
        "pageSize": int(max(1, min(int(limit), 20))),
        "sortBy": "publishedAt",
        "language": "en",
    }
    headers = {"X-Api-Key": api_key, "Accept": "application/json"}

    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code != 200:
        return {
            "articles": [],
            "error": {"message": f"NewsAPI error: {resp.status_code}", "details": resp.text[:500]},
            "source": {"provider": "NewsAPI", "endpoint": url, "query": params},
        }

    data = resp.json()
    out: List[Dict[str, Any]] = []
    for a in (data.get("articles") or [])[: params["pageSize"]]:
        out.append(
            {
                "title": a.get("title", "") or "",
                "source": (a.get("source") or {}).get("name", "") or "",
                "published_at": a.get("publishedAt", "") or "",
                "url": a.get("url", "") or "",
                "snippet": a.get("description", "") or a.get("content", "") or "",
                "location_tags": [location],
            }
        )

    return {
        "articles": out,
        "source": {"provider": "NewsAPI", "endpoint": url, "query": params, "retrieved_at": datetime.utcnow().isoformat() + "Z"},
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
    year = int(os.getenv("CENSUS_YEAR", "2023"))
    vars_ = ["B01003_001E", "B05002_013E", "B05001_006E", "NAME"]

    # State FIPS mapping for the states included in local VERA examples
    # (extend as needed for other states)
    fips = {
        "new_york": "36",
        "texas": "48",
    }
    slug = _normalize_state_to_slug(state)
    state_fips = fips.get(slug)
    if not state_fips:
        return {
            "state": state,
            "error": {
                "message": "State FIPS mapping not configured in this lab script for the given state.",
                "supported_states": sorted([k for k in fips.keys()]),
            },
            "source": {"provider": "Census API", "dataset": f"acs/acs1?year={year}", "variables": vars_},
        }

    url = f"https://api.census.gov/data/{year}/acs/acs1"
    params = {"get": ",".join(vars_), "for": f"state:{state_fips}", "key": api_key}
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        return {
            "state": state,
            "error": {"message": f"Census API error: {resp.status_code}", "details": resp.text[:500]},
            "source": {"provider": "Census API", "endpoint": url, "query": params},
        }

    rows = resp.json()
    header, values = rows[0], rows[1]
    row = dict(zip(header, values))

    total = float(row.get("B01003_001E", "nan"))
    foreign_born = float(row.get("B05002_013E", "nan"))
    non_citizen = float(row.get("B05001_006E", "nan"))

    def pct(n: float, d: float) -> Optional[float]:
        if d and d > 0 and n == n and d == d:
            return round((n / d) * 100.0, 2)
        return None

    return {
        "state": state,
        "state_name": row.get("NAME", state),
        "total_population": int(total) if total == total else None,
        "foreign_born_count": int(foreign_born) if foreign_born == foreign_born else None,
        "foreign_born_pct": pct(foreign_born, total),
        "non_citizen_count": int(non_citizen) if non_citizen == non_citizen else None,
        "non_citizen_pct": pct(non_citizen, total),
        "source": {
            "provider": "Census API",
            "dataset": f"ACS 1-year {year}",
            "endpoint": url,
            "variables": {
                "B01003_001E": "Total population",
                "B05002_013E": "Foreign born population",
                "B05001_006E": "Not a U.S. citizen (non-citizen)",
            },
            "retrieved_at": datetime.utcnow().isoformat() + "Z",
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
                "hint": "Add the required CSV(s) under lab6_multi_agent_tools/data/ or ask for a supported state.",
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

        return {
            "state": state,
            "metric": metric,
            "days": days,
            "as_of_date": as_of_date.date().isoformat(),
            "latest_value": int(round(latest_total)),
            "window_avg": round(window_avg, 2),
            "window_change": int(round(latest_total - first_total)),
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
        "facility_count": facility_count,
        "top_facilities": top,
        "source_files": [str(p) for p in files],
    }


# 3) TOOL METADATA (function calling schemas) ##################################

tool_get_recent_ice_articles = {
    "type": "function",
    "function": {
        "name": "get_recent_ice_articles",
        "description": "Fetch recent ICE-related news articles for a given location (state/city) and optional topic. Returns JSON list of articles with title/source/date/url/snippet.",
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
        "description": "Summarize local VERA ICE detention trends for a state over the last N days. Returns latest total, trailing average, change, facility count, and top facilities.",
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
Your job is to gather evidence using the provided tool, not to write a narrative.

Hard requirements:
- You MUST call the tool get_vera_detention_trends exactly once.
- Choose the most relevant US state from the user question.
  - If the question is national/unspecified, use state="national".
- Use reasonable defaults unless the user requests otherwise:
  - metric="midnight_pop"
  - days=30
- If the requested state's VERA CSVs are not present locally, still call the tool.
  It will return a structured error payload that you must preserve.

After the tool call, output only the single word: TOOLS_CALLED
"""

AGENT2_ROLE = """You are Agent 2. Write a short report-style summary for the public. Do not call tools.

The user message JSON includes "vera_statistics_from_data_files": the object computed from the lab VERA CSVs. Treat it as the only source of truth for every number.

Accuracy (non-negotiable):
- Copy each statistic from the JSON only. Do not estimate, round differently, invent numbers, or add percentages.
- latest_value is statewide; facility counts come only from top_facilities[].latest_metric_value. Do not assign the statewide total to one facility.
- Use the fields that are actually present (e.g., state, metric, days, as_of_date, latest_value, window_avg, window_change, facility_count when available). If a field is missing, say it is not in the extract rather than guessing.

Content:
- Report the key statewide figures in clear prose: what the metric means in plain terms (e.g., people in detention at midnight for midnight_pop), the as-of date, the latest totals and averages over the window, and what window_change indicates for the state total over that window.
- If top_facilities is present and non-empty, name exactly one site: the row with the largest latest_metric_value (compare every row; list order does not mean rank). Give facility_name, city, and state, and that row’s latest_metric_value exactly as in the JSON. Do not name any other facility or discuss lowest-detention sites.
- Optionally note facility_count only if it appears in the JSON, as the count of facilities with nonzero values in the extract—not as an enforcement or policy claim.
- Close with one sentence on data origin using source_files (file basenames only, not full paths).

If the object contains an "error" field, write a brief factual notice from that message only.

Tone: neutral, readable. Format: readable dates (March 10, 2026), comma thousands for large integers, plain paragraphs, no Markdown."""


# 5) CHAIN + HARNESS ###########################################################

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


def _vera_block_for_agent2(dataset: Dict[str, Any]) -> Any:
    """Prefer bundled tool output; fall back to agent1_raw when it is the tool dict."""
    out = (((dataset.get("tools") or {}).get("get_vera_detention_trends") or {}).get("output"))
    if out is not None:
        return out
    raw = dataset.get("agent1_raw")
    if isinstance(raw, dict):
        return raw
    return {}


def run_chain(user_question: str) -> Dict[str, Any]:
    """
    Two-agent chain (VERA-only for now):
    - Agent 1 (LLM) chooses tool arguments; `get_vera_detention_trends` reads CSVs under
      lab6_multi_agent_tools/data/ via pandas and returns numeric JSON. The LLM does not
      read the filesystem directly.
    - Agent 2 (LLM) turns that JSON into a report; errors in numbers are model behavior,
      not CSV parsing, if Agent 1’s printed tool output already matches the files.
    Timeouts: AGENT1_CHAIN_TIMEOUT_SEC, AGENT2_CHAIN_TIMEOUT_SEC.
    """
    def _agent1_call() -> Any:
        return agent_run(
            role=AGENT1_ROLE,
            task=user_question,
            model=MODEL,
            output="text",
            tools=[tool_get_vera_detention_trends],
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

    dataset = _bundle_tool_calls(agent1_output, user_question=user_question)
    agent2_task = json.dumps(
        {
            "user_question": user_question,
            "vera_statistics_from_data_files": _vera_block_for_agent2(dataset),
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
            "content": "What has been happening with ICE detention in Texas lately?",
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
    print("Agent 2 report:")
    print(str(result["agent2_report"])[:4000])
    print()
