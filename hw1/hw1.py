"""
Homework 1: Expanded Census ACS API Query for ICE Dashboard Context

This script expands the original citizenship query (lab1.py) to include:
- Citizenship status (B05001) - original
- Age distribution (B01001) - aggregated age groups
- Race/ethnicity (B02001) - major categories
- Poverty status (B17001) - overall poverty
- Poverty by nativity (B05010) - foreign-born specific poverty rates
- Educational attainment (B15003) - key education levels

Makes multiple API calls and merges results by state FIPS code.
Exports comprehensive demographic dataset for ICE dashboard reporting.

Data source: U.S. Census Bureau ACS 5-Year (2024)
Documentation: https://www.census.gov/data/developers/data-sets/acs-5year.html
"""

import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

API_URL = "https://api.census.gov/data/2024/acs/acs5"
OUTPUT_DIR = Path(__file__).resolve().parent

# Load API key from .env (try lab2/.env, app/.env, hw1/.env, then parent)
env_paths = [
    OUTPUT_DIR.parent / "lab2" / ".env",  # Shiny app location
    OUTPUT_DIR.parent / "app" / ".env",   # Alternative app location
    OUTPUT_DIR / ".env",
    OUTPUT_DIR.parent / ".env",
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        break
else:
    load_dotenv(override=True)


def get_api_key() -> str:
    """Get and validate Census API key."""
    key = os.getenv("CENSUS_API_KEY")
    if not key or not key.strip() or "getenv" in key.lower():
        raise RuntimeError(
            "Set CENSUS_API_KEY in .env file. Get a key: https://api.census.gov/data/key_signup.html"
        )
    return key.strip()


def fetch_table(variables: tuple, table_name: str) -> pd.DataFrame:
    """
    Fetch a Census ACS table and return as DataFrame.
    
    Args:
        variables: Tuple of variable codes (e.g., ("NAME,", "B01001_001E,"))
        table_name: Descriptive name for error messages
    
    Returns:
        DataFrame with state-level data
    """
    params = {
        "get": variables,
        "for": "state:*",
        "key": get_api_key(),
    }
    
    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch {table_name}: {exc}")
    
    data = resp.json()
    if not data or len(data) < 2:
        raise RuntimeError(f"{table_name} returned no data.")
    
    header, *rows = data
    df = pd.DataFrame(rows, columns=header)
    
    # Convert numeric columns (all except NAME and state)
    for col in df.columns:
        if col not in ["NAME", "state"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    return df


def fetch_citizenship() -> pd.DataFrame:
    """Call 1: Citizenship status (B05001) - original query."""
    vars_citizenship = (
        "NAME," "B01001_001E," "B05001_002E," "B05001_003E," "B05001_004E,"
        "B05001_005E," "B05001_006E"
    )
    df = fetch_table(vars_citizenship, "Citizenship (B05001)")
    
    # Rename and derive basic metrics
    df["state_name"] = df["NAME"].astype(str).str.strip()
    df["total_population"] = df["B01001_001E"]
    df["non_citizen"] = df["B05001_006E"]
    df["naturalized"] = df["B05001_005E"]
    df["foreign_born"] = df["B05001_005E"] + df["B05001_006E"]
    
    total = df["total_population"].clip(lower=1)
    df["pct_non_citizen"] = (df["non_citizen"] / total * 100).round(2)
    df["pct_foreign_born"] = (df["foreign_born"] / total * 100).round(2)
    df["pct_naturalized"] = (df["naturalized"] / total * 100).round(2)
    
    return df[["state", "state_name", "total_population", "non_citizen", 
               "naturalized", "foreign_born", "pct_non_citizen", 
               "pct_foreign_born", "pct_naturalized"]].copy()


def fetch_age() -> pd.DataFrame:
    """
    Call 2: Age distribution (B01001) - aggregated age groups.
    
    Aggregates to: 18-34, 35-64, 65+
    """
    # B01001 structure: Total, then Male age groups (003-025), Female age groups (027-049)
    # We'll query key groups and aggregate:
    # Ages 18-34: Male 007-011 (18-19, 20, 21, 22-24, 25-29) + Female 031-035
    # Ages 35-64: Male 012-016 (30-34, 35-39, 40-44, 45-49, 50-54) + Female 036-040
    # Ages 65+: Male 017-025 (55-59, 60-61, 62-64, 65-66, 67-69, 70-74, 75-79, 80-84, 85+) + Female 041-049
    
    vars_age = (
        "NAME," "B01001_001E,"  # Total
        # Male: 18-34
        "B01001_007E," "B01001_008E," "B01001_009E," "B01001_010E," "B01001_011E,"
        # Male: 35-64
        "B01001_012E," "B01001_013E," "B01001_014E," "B01001_015E," "B01001_016E,"
        # Male: 65+
        "B01001_017E," "B01001_018E," "B01001_019E," "B01001_020E," "B01001_021E,"
        "B01001_022E," "B01001_023E," "B01001_024E," "B01001_025E,"
        # Female: 18-34
        "B01001_031E," "B01001_032E," "B01001_033E," "B01001_034E," "B01001_035E,"
        # Female: 35-64
        "B01001_036E," "B01001_037E," "B01001_038E," "B01001_039E," "B01001_040E,"
        # Female: 65+
        "B01001_041E," "B01001_042E," "B01001_043E," "B01001_044E," "B01001_045E,"
        "B01001_046E," "B01001_047E," "B01001_048E," "B01001_049E"
    )
    
    df = fetch_table(vars_age, "Age (B01001)")
    
    # Aggregate to age groups
    df["age_18_34"] = (
        df["B01001_007E"] + df["B01001_008E"] + df["B01001_009E"] + 
        df["B01001_010E"] + df["B01001_011E"] +
        df["B01001_031E"] + df["B01001_032E"] + df["B01001_033E"] + 
        df["B01001_034E"] + df["B01001_035E"]
    )
    
    df["age_35_64"] = (
        df["B01001_012E"] + df["B01001_013E"] + df["B01001_014E"] + 
        df["B01001_015E"] + df["B01001_016E"] +
        df["B01001_036E"] + df["B01001_037E"] + df["B01001_038E"] + 
        df["B01001_039E"] + df["B01001_040E"]
    )
    
    df["age_65_plus"] = (
        df["B01001_017E"] + df["B01001_018E"] + df["B01001_019E"] + 
        df["B01001_020E"] + df["B01001_021E"] + df["B01001_022E"] + 
        df["B01001_023E"] + df["B01001_024E"] + df["B01001_025E"] +
        df["B01001_041E"] + df["B01001_042E"] + df["B01001_043E"] + 
        df["B01001_044E"] + df["B01001_045E"] + df["B01001_046E"] + 
        df["B01001_047E"] + df["B01001_048E"] + df["B01001_049E"]
    )
    
    total = df["B01001_001E"].clip(lower=1)
    df["pct_age_18_34"] = (df["age_18_34"] / total * 100).round(2)
    df["pct_age_35_64"] = (df["age_35_64"] / total * 100).round(2)
    df["pct_age_65_plus"] = (df["age_65_plus"] / total * 100).round(2)
    
    return df[["state", "age_18_34", "age_35_64", "age_65_plus",
               "pct_age_18_34", "pct_age_35_64", "pct_age_65_plus"]].copy()


def fetch_race() -> pd.DataFrame:
    """Call 3: Race/ethnicity (B02001) - major categories."""
    vars_race = (
        "NAME," "B02001_001E," "B02001_002E," "B02001_003E," "B02001_004E,"
        "B02001_005E," "B02001_006E," "B02001_007E," "B02001_008E"
    )
    
    df = fetch_table(vars_race, "Race (B02001)")
    
    total = df["B02001_001E"].clip(lower=1)
    df["race_white"] = df["B02001_002E"]
    df["race_black"] = df["B02001_003E"]
    df["race_ai_an"] = df["B02001_004E"]  # American Indian/Alaska Native
    df["race_asian"] = df["B02001_005E"]
    df["race_nh_pi"] = df["B02001_006E"]  # Native Hawaiian/Pacific Islander
    df["race_other"] = df["B02001_007E"]
    df["race_two_or_more"] = df["B02001_008E"]
    
    df["pct_race_white"] = (df["race_white"] / total * 100).round(2)
    df["pct_race_black"] = (df["race_black"] / total * 100).round(2)
    df["pct_race_asian"] = (df["race_asian"] / total * 100).round(2)
    df["pct_race_other"] = (
        (df["race_ai_an"] + df["race_nh_pi"] + df["race_other"] + df["race_two_or_more"]) 
        / total * 100
    ).round(2)
    
    return df[["state", "race_white", "race_black", "race_asian", 
               "pct_race_white", "pct_race_black", "pct_race_asian", "pct_race_other"]].copy()


def fetch_poverty() -> pd.DataFrame:
    """Call 4: Poverty status (B17001) - overall poverty."""
    vars_poverty = (
        "NAME," "B17001_001E," "B17001_002E," "B17001_031E"
    )
    
    df = fetch_table(vars_poverty, "Poverty (B17001)")
    
    total = df["B17001_001E"].clip(lower=1)
    df["below_poverty"] = df["B17001_002E"]
    df["at_or_above_poverty"] = df["B17001_031E"]
    df["pct_below_poverty"] = (df["below_poverty"] / total * 100).round(2)
    
    return df[["state", "below_poverty", "at_or_above_poverty", "pct_below_poverty"]].copy()


def fetch_poverty_by_nativity() -> pd.DataFrame:
    """
    Call 5: Poverty by nativity (B05010) - foreign-born specific poverty rates.
    
    B05010 structure: Ratio of Income to Poverty Level by Nativity
    Key variables: Below 1.00 (poverty), 1.00-1.99, 2.00+
    """
    # B05010: Ratio of Income to Poverty Level by Nativity
    # Structure: Total, then Native (below 1.00, 1.00-1.99, 2.00+), then Foreign-born (below 1.00, 1.00-1.99, 2.00+)
    vars_pov_nativity = (
        "NAME," "B05010_001E,"  # Total
        "B05010_002E,"  # Native: Below 1.00
        "B05010_003E,"  # Native: 1.00-1.99
        "B05010_004E,"  # Native: 2.00+
        "B05010_005E,"  # Foreign-born: Below 1.00
        "B05010_006E,"  # Foreign-born: 1.00-1.99
        "B05010_007E"   # Foreign-born: 2.00+
    )
    
    df = fetch_table(vars_pov_nativity, "Poverty by Nativity (B05010)")
    
    # Foreign-born poverty
    fb_total = (df["B05010_005E"] + df["B05010_006E"] + df["B05010_007E"]).clip(lower=1)
    df["fb_below_poverty"] = df["B05010_005E"]
    df["pct_fb_below_poverty"] = (df["fb_below_poverty"] / fb_total * 100).round(2)
    
    # Native poverty for comparison
    native_total = (df["B05010_002E"] + df["B05010_003E"] + df["B05010_004E"]).clip(lower=1)
    df["native_below_poverty"] = df["B05010_002E"]
    df["pct_native_below_poverty"] = (df["native_below_poverty"] / native_total * 100).round(2)
    
    return df[["state", "fb_below_poverty", "pct_fb_below_poverty", 
               "native_below_poverty", "pct_native_below_poverty"]].copy()


def fetch_education() -> pd.DataFrame:
    """
    Call 6: Educational attainment (B15003) - key thresholds.
    
    Levels: Less than high school, High school, Some college/Associate's,
    Bachelor's, Master's, Professional, Doctorate
    """
    # B15003: Educational Attainment (25 years and over)
    # Structure: Total, then detailed levels (002-025)
    # Key: 002-016 (less than high school), 017 (high school), 018-021 (some college/associate's),
    #      022 (bachelor's), 023 (master's), 024 (professional), 025 (doctorate)
    vars_education = (
        "NAME," "B15003_001E,"  # Total 25+
        # Less than high school (002-016)
        "B15003_002E," "B15003_003E," "B15003_004E," "B15003_005E," "B15003_006E,"
        "B15003_007E," "B15003_008E," "B15003_009E," "B15003_010E," "B15003_011E,"
        "B15003_012E," "B15003_013E," "B15003_014E," "B15003_015E," "B15003_016E,"
        # High school (017)
        "B15003_017E,"
        # Some college/Associate's (018-021)
        "B15003_018E," "B15003_019E," "B15003_020E," "B15003_021E,"
        # Bachelor's (022)
        "B15003_022E,"
        # Master's (023)
        "B15003_023E,"
        # Professional (024)
        "B15003_024E,"
        # Doctorate (025)
        "B15003_025E"
    )
    
    df = fetch_table(vars_education, "Education (B15003)")
    
    total_25plus = df["B15003_001E"].clip(lower=1)
    
    # Aggregate education levels
    df["edu_less_than_hs"] = (
        df["B15003_002E"] + df["B15003_003E"] + df["B15003_004E"] + df["B15003_005E"] +
        df["B15003_006E"] + df["B15003_007E"] + df["B15003_008E"] + df["B15003_009E"] +
        df["B15003_010E"] + df["B15003_011E"] + df["B15003_012E"] + df["B15003_013E"] +
        df["B15003_014E"] + df["B15003_015E"] + df["B15003_016E"]
    )
    df["edu_high_school"] = df["B15003_017E"]
    df["edu_some_college"] = (
        df["B15003_018E"] + df["B15003_019E"] + df["B15003_020E"] + df["B15003_021E"]
    )
    df["edu_bachelors"] = df["B15003_022E"]
    df["edu_masters"] = df["B15003_023E"]
    df["edu_professional"] = df["B15003_024E"]
    df["edu_doctorate"] = df["B15003_025E"]
    df["edu_bachelors_plus"] = (
        df["edu_bachelors"] + df["edu_masters"] + df["edu_professional"] + df["edu_doctorate"]
    )
    
    # Percentages
    df["pct_edu_less_than_hs"] = (df["edu_less_than_hs"] / total_25plus * 100).round(2)
    df["pct_edu_high_school"] = (df["edu_high_school"] / total_25plus * 100).round(2)
    df["pct_edu_some_college"] = (df["edu_some_college"] / total_25plus * 100).round(2)
    df["pct_edu_bachelors"] = (df["edu_bachelors"] / total_25plus * 100).round(2)
    df["pct_edu_masters"] = (df["edu_masters"] / total_25plus * 100).round(2)
    df["pct_edu_professional"] = (df["edu_professional"] / total_25plus * 100).round(2)
    df["pct_edu_doctorate"] = (df["edu_doctorate"] / total_25plus * 100).round(2)
    df["pct_edu_bachelors_plus"] = (df["edu_bachelors_plus"] / total_25plus * 100).round(2)
    
    return df[["state", "edu_less_than_hs", "edu_high_school", "edu_some_college",
               "edu_bachelors", "edu_masters", "edu_professional", "edu_doctorate",
               "edu_bachelors_plus", "pct_edu_less_than_hs", "pct_edu_high_school",
               "pct_edu_some_college", "pct_edu_bachelors", "pct_edu_masters",
               "pct_edu_professional", "pct_edu_doctorate", "pct_edu_bachelors_plus"]].copy()


def main() -> None:
    """Fetch all tables, merge by state, and export CSV."""
    print("Fetching Census ACS data...")
    print("  Call 1: Citizenship status...")
    df_citizenship = fetch_citizenship()
    
    print("  Call 2: Age distribution...")
    df_age = fetch_age()
    
    print("  Call 3: Race/ethnicity...")
    df_race = fetch_race()
    
    print("  Call 4: Poverty status...")
    df_poverty = fetch_poverty()
    
    print("  Call 5: Poverty by nativity...")
    df_pov_nativity = fetch_poverty_by_nativity()
    
    print("  Call 6: Educational attainment...")
    df_education = fetch_education()
    
    print("\nMerging all datasets by state FIPS...")
    # Merge all on state FIPS code
    df_merged = df_citizenship.copy()
    for df in [df_age, df_race, df_poverty, df_pov_nativity, df_education]:
        df_merged = df_merged.merge(df, on="state", how="outer", validate="1:1")
    
    # Sort by state name for readability
    df_merged = df_merged.sort_values("state_name").reset_index(drop=True)
    
    # Export CSV
    output_path = OUTPUT_DIR / "citizenship_demographics_expanded.csv"
    df_merged.to_csv(output_path, index=False, encoding="utf-8")
    print(f"\n[SUCCESS] Wrote {output_path} ({len(df_merged)} rows, {len(df_merged.columns)} columns)")
    
    # Print summary
    print(f"\nDataset includes:")
    print(f"  - {len(df_merged)} states/territories")
    print(f"  - Citizenship: non-citizen, naturalized, foreign-born counts and rates")
    print(f"  - Age: 18-34, 35-64, 65+ counts and percentages")
    print(f"  - Race: White, Black, Asian, Other percentages")
    print(f"  - Poverty: Overall and foreign-born specific rates")
    print(f"  - Education: Key attainment levels (high school, bachelor's, master's, etc.)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
