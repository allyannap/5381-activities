"""
Join Census demographics (hw1) with Vera ICE detention data by state.

- Adds state_abbr to Census (FIPS -> 2-letter code).
- Aggregates Vera facilities.csv to state level (facility count).
- Left-joins: Census (left) on state_abbr = Vera state.
- Output: census_vera_joined.csv (one row per Census state with ICE metrics).
"""

import pandas as pd
import requests
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent
CENSUS_CSV = OUTPUT_DIR / "citizenship_demographics_expanded.csv"
VERA_FACILITIES_URL = "https://raw.githubusercontent.com/vera-institute/ice-detention-trends/main/metadata/facilities.csv"
JOINED_CSV = OUTPUT_DIR / "census_vera_joined.csv"

# FIPS (2-digit string) -> 2-letter state abbreviation (Census + Vera use this on Vera side)
STATE_FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "72": "PR",
}


def load_census_with_state_abbr() -> pd.DataFrame:
    """Load Census CSV and add state_abbr from FIPS."""
    df = pd.read_csv(CENSUS_CSV, dtype={"state": str})
    # Ensure state is 2-digit string for mapping (e.g. 1 -> "01")
    df["state"] = df["state"].astype(str).str.zfill(2)
    df["state_abbr"] = df["state"].map(STATE_FIPS_TO_ABBR)
    return df


def load_vera_state_metrics() -> pd.DataFrame:
    """Fetch Vera facilities.csv and aggregate to state level (facility count)."""
    r = requests.get(VERA_FACILITIES_URL, timeout=30)
    r.raise_for_status()
    facilities = pd.read_csv(pd.io.common.BytesIO(r.content), dtype={"state": str})
    # Aggregate by state: facility count
    vera = (
        facilities.groupby("state", as_index=False)
        .agg(ice_facility_count=("detention_facility_code", "nunique"))
    )
    return vera


def main() -> None:
    census = load_census_with_state_abbr()
    vera = load_vera_state_metrics()

    # Left-join: Census (left) on state_abbr = Vera state
    joined = census.merge(
        vera,
        left_on="state_abbr",
        right_on="state",
        how="left",
        suffixes=("", "_vera"),
    )
    # Drop the Vera "state" column (duplicate of state_abbr); keep Census "state" (FIPS)
    if "state_vera" in joined.columns:
        joined = joined.drop(columns=["state_vera"])
    # Pandas may name the right key "state" so we have state (FIPS) and state from Vera
    if "state" in joined.columns and joined.columns.duplicated().any():
        joined = joined.loc[:, ~joined.columns.duplicated()]
    # Reorder: state, state_abbr, then rest
    lead = ["state", "state_abbr"] if "state_abbr" in joined.columns else ["state"]
    rest = [c for c in joined.columns if c not in lead]
    joined = joined[lead + rest]

    joined.to_csv(JOINED_CSV, index=False, encoding="utf-8")
    print(f"Wrote {JOINED_CSV} ({len(joined)} rows)")
    print(f"States with ICE facilities: {joined['ice_facility_count'].notna().sum()}")


if __name__ == "__main__":
    main()
