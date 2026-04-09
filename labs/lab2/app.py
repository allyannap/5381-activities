from shiny import App, reactive
from shiny.express import input, render, ui
from shinywidgets import render_plotly

import os
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from pathlib import Path
from dotenv import load_dotenv


# --------------------------------------------------------------------------------------
# Configuration and helpers
# --------------------------------------------------------------------------------------

API_URL = "https://api.census.gov/data/2024/acs/acs5"

# Citizenship table (B05001) variables
CITIZEN_VARS = [
    "NAME",
    "B01001_001E",  # Total population
    "B05001_002E",  # U.S. citizen, born in the United States
    "B05001_003E",  # U.S. citizen, born in Puerto Rico or U.S. Island Areas
    "B05001_004E",  # U.S. citizen, born abroad of American parent(s)
    "B05001_005E",  # Naturalized U.S. citizen
    "B05001_006E"  # Not a U.S. citizen
]

# Map from state FIPS -> postal abbreviation (for Plotly USA choropleth)
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
    "56": "WY", "72": "PR"
}


def _get_api_key() -> str | None:
    """
    Load the Census API key from the app directory's .env file.
    Returns None if not set or if the value looks like a placeholder.
    """
    # Always load .env from the same folder as this app (so it works no matter where you run from)
    app_dir = Path(__file__).resolve().parent
    env_path = app_dir / ".env"
    # override=True ensures we use the .env file value even if env var already exists
    load_dotenv(env_path, override=True)
    
    raw = os.getenv("CENSUS_API_KEY")
    if not raw:
        return None
    key = raw.strip()
    # Reject placeholder or invalid values that would cause "Invalid Key"
    if not key or "getenv" in key.lower() or key.startswith("REPLACE") or len(key) < 10:
        return None
    return key


def fetch_citizenship_data() -> pd.DataFrame:
    """
    Query ACS 5-year citizenship table for all states.

    Returns a tidy DataFrame with counts and derived rates.
    Raises RuntimeError with a friendly message on failure.
    """
    CENSUS_API_KEY = _get_api_key()
    if not CENSUS_API_KEY:
        raise RuntimeError(
            "Census API key not found. In the app folder, open .env and set "
            "CENSUS_API_KEY=your_key (no quotes). Get a key: https://api.census.gov/data/key_signup.html"
        )

    # Match EXACT format from my_good_query.py: tuple of comma-terminated strings
    get_params = (
        "NAME,"            # State name 
        "B01001_001E,"     # Total population
        "B05001_002E,"     # U.S. citizen, born in the United States
        "B05001_003E,"     # U.S. citizen, born in Puerto Rico or U.S. Island Areas
        "B05001_004E,"     # U.S. citizen, born abroad of American parent(s)
        "B05001_005E,"     # Naturalized U.S. citizen
        "B05001_006E"      # Not a U.S. citizen
    )
    params = {
        "get": get_params,
        "for": "state:*",
        "key": CENSUS_API_KEY
    }

    try:
        resp = requests.get(API_URL, params=params, timeout=20)
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error while calling Census API: {exc}") from exc

    if resp.status_code != 200:
        # The Census API sometimes returns an HTML error page or text body.
        # Include a short snippet to help with debugging, but avoid dumping everything.
        snippet = resp.text[:200].replace("\n", " ").strip()
        raise RuntimeError(
            "Census API request failed. "
            f"HTTP status {resp.status_code}. "
            "This usually means the API key is invalid, expired, or the service is down. "
            f"Response snippet: {snippet!r}"
        )

    try:
        data = resp.json()
    except ValueError:
        # Non‑JSON response (often an HTML or plain‑text error page)
        snippet = resp.text[:200].replace("\n", " ").strip()
        raise RuntimeError(
            "Census API returned invalid JSON instead of data. "
            "This often indicates a problem with the API key or request parameters. "
            f"Response snippet: {snippet!r}"
        )
    if not data or len(data) < 2:
        raise RuntimeError("Census API returned no data for this query.")

    header, *rows = data
    # Census returns 8 columns: NAME, B01001_001E, ..., B05001_006E, state
    df = pd.DataFrame(rows, columns=header)

    # Convert numeric columns
    num_cols = [
        "B01001_001E",
        "B05001_002E",
        "B05001_003E",
        "B05001_004E",
        "B05001_005E",
        "B05001_006E"
    ]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["total_pop"] = df["B01001_001E"]
    # Approximate foreign-born as naturalized + non-citizen
    df["foreign_born"] = df["B05001_005E"] + df["B05001_006E"]
    df["non_citizen"] = df["B05001_006E"]
    df["naturalized"] = df["B05001_005E"]

    # Rates (% of total population). Avoid division by zero.
    df["pct_foreign_born"] = (df["foreign_born"] / df["total_pop"] * 100).round(2)
    df["pct_non_citizen"] = (df["non_citizen"] / df["total_pop"] * 100).round(2)
    df["pct_naturalized"] = (df["naturalized"] / df["total_pop"] * 100).round(2)

    # Per 100k metrics
    factor = 100_000
    df["foreign_born_per_100k"] = (df["foreign_born"] / df["total_pop"] * factor).round(1)
    df["non_citizen_per_100k"] = (df["non_citizen"] / df["total_pop"] * factor).round(1)
    df["naturalized_per_100k"] = (df["naturalized"] / df["total_pop"] * factor).round(1)

    # Add state abbreviation for mapping
    df["state_abbr"] = df["state"].map(STATE_FIPS_TO_ABBR)

    return df


# --------------------------------------------------------------------------------------
# Reactive state
# --------------------------------------------------------------------------------------

@reactive.calc
def census_data() -> pd.DataFrame:
    """
    Reactive wrapper around the Census query.
    Re-runs when the user clicks the 'Run query' button.
    """
    # Depend on the button to make this reactive
    _ = input.run_query()
    return fetch_citizenship_data()


@reactive.calc
def selected_states() -> list[str]:
    # multi-select returns a tuple of selected values (or None); normalize to list of strings
    value = input.state_select()
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(s) for s in value]
    return [str(value)]


# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------

ui.page_opts(
    title="US Citizenship Dashboard",
    fillable=True,
)

with ui.sidebar(open="desktop"):
    ui.h3("Controls")

    ui.input_action_button("run_query", "Run Census query")

    ui.input_select(
        "metric",
        "Ranking metric",
        choices={
            "pct_foreign_born": "% foreign-born",
            "pct_non_citizen": "% non-citizen",
            "pct_naturalized": "% naturalized",
        },
        selected="pct_foreign_born"
    )

    ui.input_radio_buttons(
        "value_mode",
        "View",
        choices={
            "rate": "Rate (share of population)",
            "count": "Count",
        },
        selected="rate",
    )

    ui.input_select(
        "state_select",
        "Compare states",
        multiple=True,
        choices=[]  # populated reactively below
    )

    ui.hr()
    ui.markdown(
        "Data source: ACS 5-year (2024), citizenship table B05001 "
        "(foreign-born approximated as naturalized + non-citizen)."
    )


with ui.layout_columns():
    with ui.card():
        ui.card_header("State rankings")

        @render.data_frame
        def rankings():
            df = census_data().copy()
            metric = input.metric()
            mode = input.value_mode()

            if mode == "count":
                col = {
                    "pct_foreign_born": "foreign_born",
                    "pct_non_citizen": "non_citizen",
                    "pct_naturalized": "naturalized"
                }[metric]
                display_col = col
            else:
                display_col = metric

            df = df.sort_values(display_col, ascending=False)
            top = df[
                [
                    "NAME",
                    "total_pop",
                    "foreign_born",
                    "non_citizen",
                    "naturalized",
                    "pct_foreign_born",
                    "pct_non_citizen",
                    "pct_naturalized"
                ]
            ]
            top = top.rename(
                columns={
                    "NAME": "State",
                    "total_pop": "Total pop",
                    "foreign_born": "Foreign-born",
                    "non_citizen": "Non-citizen",
                    "naturalized": "Naturalized",
                    "pct_foreign_born": "% foreign-born",
                    "pct_non_citizen": "% non-citizen",
                    "pct_naturalized": "% naturalized"
                }
            )
            return top

    with ui.card():
        ui.card_header("Map view")

        @render_plotly
        def map_view():
            import plotly.express as px

            df = census_data()
            metric = input.metric()

            title = {
                "pct_foreign_born": "% foreign-born",
                "pct_non_citizen": "% non-citizen",
                "pct_naturalized": "% naturalized"
            }[metric]

            fig = px.choropleth(
                df,
                locations="state_abbr",
                locationmode="USA-states",
                color=metric,
                scope="usa",
                color_continuous_scale="Blues",
                hover_name="NAME",
                labels={metric: title}
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=40, b=0),
                coloraxis_colorbar_title=title
            )
            return fig


with ui.card():
    ui.card_header("State comparison")

    @render.data_frame
    def comparison_table():
        df = census_data()
        states = selected_states()
        if states:
            # Compare as strings so selection from dropdown matches df["NAME"]
            df = df[df["NAME"].astype(str).isin(states)]

        subset = df[
            [
                "NAME",
                "total_pop",
                "foreign_born",
                "non_citizen",
                "naturalized",
                "pct_foreign_born",
                "pct_non_citizen",
                "pct_naturalized",
                "foreign_born_per_100k",
                "non_citizen_per_100k",
                "naturalized_per_100k"
            ]
        ]

        subset = subset.rename(
            columns={
                "NAME": "State",
                "total_pop": "Total pop",
                "foreign_born": "Foreign-born",
                "non_citizen": "Non-citizen",
                "naturalized": "Naturalized",
                "pct_foreign_born": "% foreign-born",
                "pct_non_citizen": "% non-citizen",
                "pct_naturalized": "% naturalized",
                "foreign_born_per_100k": "Foreign-born per 100k",
                "non_citizen_per_100k": "Non-citizen per 100k",
                "naturalized_per_100k": "Naturalized per 100k"
            }
        )
        return subset


# --------------------------------------------------------------------------------------
# Reactive updates for UI controls and error handling
# --------------------------------------------------------------------------------------

@render.ui
def error_message():
    """
    Display a friendly error message if the Census query fails.
    """
    try:
        # Trigger data loading without using the result
        _ = census_data()
    except RuntimeError as exc:
        return ui.div(
            {"class": "alert alert-warning"},
            ui.strong("Problem loading Census data: "),
            str(exc)
        )
    return ui.div()


@reactive.effect
def _populate_state_choices():
    """
    Populate the state multi-select choices once data is available.
    Use state name as both value and label so selection matches df["NAME"].
    """
    try:
        df = census_data()
    except RuntimeError:
        return

    names = sorted(df["NAME"].astype(str).unique())
    # Dict ensures selected value is the state name string (matches df["NAME"])
    choices = {name: name for name in names}
    ui.update_select("state_select", choices=choices)
