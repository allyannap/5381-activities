"""
Lab 03: Query Census ACS citizenship API, clean/aggregate, and export CSV for AI.

Data source: U.S. Census Bureau ACS 5-Year (2024), table B05001.
Output: State-level citizenship demographics (counts and rates). Use for AI to
report on non-citizen and foreign-born population patterns by state.
Note: This is demographic population data, not ICE arrest/detention records.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

API_URL = "https://api.census.gov/data/2024/acs/acs5"
GET_VARS = (
    "NAME," "B01001_001E," "B05001_002E," "B05001_003E," "B05001_004E,"
    "B05001_005E," "B05001_006E"
)
OUTPUT_DIR = Path(__file__).resolve().parent

# Try .env in lab03, then in app (for CENSUS_API_KEY)
for env_path in [OUTPUT_DIR / ".env", OUTPUT_DIR.parent / "app" / ".env"]:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        break
else:
    load_dotenv(override=True)


def get_api_key() -> str:
    key = os.getenv("CENSUS_API_KEY")
    if not key or not key.strip() or "getenv" in key.lower():
        raise RuntimeError(
            "Set CENSUS_API_KEY in 5381-activities/app/.env or lab03/.env"
        )
    return key.strip()


def fetch_raw() -> pd.DataFrame:
    """Request Census API and return raw DataFrame (header + rows)."""
    params = {"get": GET_VARS, "for": "state:*", "key": get_api_key()}
    resp = requests.get(API_URL, params=params, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"Census API HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if not data or len(data) < 2:
        raise RuntimeError("Census API returned no data.")
    header, *rows = data
    return pd.DataFrame(rows, columns=header)


def clean_and_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Clean types, derive rates and rankings, filter to reporting columns."""
    # Numeric columns
    num_cols = ["B01001_001E", "B05001_002E", "B05001_003E", "B05001_004E", "B05001_005E", "B05001_006E"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    total = df["B01001_001E"].clip(lower=1)
    df["state_name"] = df["NAME"].astype(str).str.strip()
    df["total_population"] = df["B01001_001E"]
    df["non_citizen"] = df["B05001_006E"]
    df["naturalized"] = df["B05001_005E"]
    df["foreign_born"] = df["B05001_005E"] + df["B05001_006E"]

    df["pct_non_citizen"] = (df["non_citizen"] / total * 100).round(2)
    df["pct_foreign_born"] = (df["foreign_born"] / total * 100).round(2)
    df["pct_naturalized"] = (df["naturalized"] / total * 100).round(2)

    df["non_citizen_per_100k"] = (df["non_citizen"] / total * 100_000).round(1)
    df["foreign_born_per_100k"] = (df["foreign_born"] / total * 100_000).round(1)

    # Drop any row with missing key values so rankings are valid
    df = df.dropna(subset=["non_citizen", "total_population"]).copy()

    # Rankings (1 = highest)
    r1 = df["non_citizen"].rank(ascending=False, method="min")
    r2 = df["pct_non_citizen"].rank(ascending=False, method="min")
    r3 = df["foreign_born"].rank(ascending=False, method="min")
    df["rank_by_non_citizen_count"] = r1.where(r1.notna(), 0).astype(int)
    df["rank_by_pct_non_citizen"] = r2.where(r2.notna(), 0).astype(int)
    df["rank_by_foreign_born_count"] = r3.where(r3.notna(), 0).astype(int)

    # Reporting columns only (AI-friendly names)
    out = df[
        [
            "state_name", "state",
            "total_population", "non_citizen", "naturalized", "foreign_born",
            "pct_non_citizen", "pct_foreign_born", "pct_naturalized",
            "non_citizen_per_100k", "foreign_born_per_100k",
            "rank_by_non_citizen_count", "rank_by_pct_non_citizen", "rank_by_foreign_born_count",
        ]
    ].copy()
    out = out.rename(columns={"state": "state_fips"})
    return out.sort_values("rank_by_non_citizen_count").reset_index(drop=True)


def main() -> None:
    raw = fetch_raw()
    df = clean_and_aggregate(raw)

    # Main CSV for AI: one row per state, clear column names
    main_path = OUTPUT_DIR / "citizenship_by_state.csv"
    df.to_csv(main_path, index=False, encoding="utf-8")
    print(f"Wrote {main_path} ({len(df)} rows)")

    # Summary CSV: top/bottom states for quick AI patterns
    top_n = 15
    summary_rows = []
    for metric, label in [
        ("non_citizen", "non_citizen_count"),
        ("pct_non_citizen", "pct_non_citizen"),
        ("foreign_born", "foreign_born_count"),
    ]:
        top = df.nlargest(top_n, metric)[["state_name", metric]].copy()
        top["metric"] = label
        top["rank_type"] = "top"
        summary_rows.append(top)
        bot = df.nsmallest(top_n, metric)[["state_name", metric]].copy()
        bot["metric"] = label
        bot["rank_type"] = "bottom"
        summary_rows.append(bot)
    summary = pd.concat(summary_rows, ignore_index=True)
    summary_path = OUTPUT_DIR / "citizenship_rankings_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8")
    print(f"Wrote {summary_path}")

    # Data dictionary for AI
    dict_path = OUTPUT_DIR / "data_dictionary.csv"
    pd.DataFrame([
        {"column": "state_name", "description": "State or area name (e.g. California, District of Columbia)."},
        {"column": "state_fips", "description": "Census state FIPS code (2-digit string)."},
        {"column": "total_population", "description": "Total population estimate."},
        {"column": "non_citizen", "description": "Estimate of people who are not U.S. citizens."},
        {"column": "naturalized", "description": "Estimate of naturalized U.S. citizens."},
        {"column": "foreign_born", "description": "Approximate foreign-born (naturalized + non_citizen)."},
        {"column": "pct_non_citizen", "description": "Percent of total population that is non-citizen."},
        {"column": "pct_foreign_born", "description": "Percent of total population that is foreign-born."},
        {"column": "pct_naturalized", "description": "Percent of total population that is naturalized."},
        {"column": "non_citizen_per_100k", "description": "Non-citizens per 100,000 population."},
        {"column": "foreign_born_per_100k", "description": "Foreign-born per 100,000 population."},
        {"column": "rank_by_non_citizen_count", "description": "State rank by non-citizen count (1 = highest)."},
        {"column": "rank_by_pct_non_citizen", "description": "State rank by pct non-citizen (1 = highest)."},
        {"column": "rank_by_foreign_born_count", "description": "State rank by foreign-born count (1 = highest)."},
    ]).to_csv(dict_path, index=False, encoding="utf-8")
    print(f"Wrote {dict_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
