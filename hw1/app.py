from pathlib import Path

import pandas as pd
from shiny.express import input, render, ui
from shinywidgets import render_plotly


ROOT = Path(__file__).resolve().parent
JOINED_CSV = ROOT / "census_vera_joined.csv"
NATIONAL_CSV = ROOT / "data" / "national.csv"


def _load_state_data() -> pd.DataFrame:
    """
    Load the Census + Vera joined state-level dataset.
    """
    df = pd.read_csv(JOINED_CSV, dtype={"state": str})
    # Basic sanity: ensure state_abbr exists
    if "state_abbr" not in df.columns:
        raise RuntimeError("Expected 'state_abbr' column in census_vera_joined.csv.")
    return df


def _load_national_data() -> pd.DataFrame:
    """
    Load Vera national ICE detention trends from local CSV.

    The file should be created by running download_vera_national.py once.
    """
    if not NATIONAL_CSV.exists():
        raise RuntimeError(
            f"National trends file not found at {NATIONAL_CSV}. "
            "Run download_vera_national.py in the hw1 folder to fetch it."
        )
    df = pd.read_csv(NATIONAL_CSV, parse_dates=["date"])
    return df


# ---------------------------------------------------------------------------
# UI (dark, map + time series)
# ---------------------------------------------------------------------------

ui.page_opts(
    title="ICE & Demographics Dashboard",
    fillable=True,
)

# Simple dark theme tweaks
ui.tags.style(
    """
    body {
        background-color: #050508;
        color: #f5f5f5;
    }
    .sidebar, .card, .bslib-card {
        background-color: #111118;
        color: #f5f5f5;
    }
    .form-label {
        color: #f5f5f5;
    }
    """
)

with ui.sidebar(open="desktop"):
    ui.h3("Controls")

    ui.input_select(
        "map_metric",
        "Map shows",
        choices={
            "ice_facility_count": "Detention activity (facility count)",
            "pct_foreign_born": "% foreign-born",
            "pct_non_citizen": "% non-citizen",
        },
        selected="ice_facility_count",
    )

    ui.hr()
    ui.markdown(
        "States in brighter red have **higher values** for the selected metric. "
        "National trends show ICE detention populations over time."
    )


with ui.layout_columns():
    with ui.card():
        ui.card_header("Heat map – detention & demographics")

        @render_plotly
        def map_choropleth():
            import plotly.express as px

            df = _load_state_data()
            metric = input.map_metric()

            # Replace NaNs for plotting
            df_plot = df.copy()
            df_plot[metric] = pd.to_numeric(df_plot[metric], errors="coerce").fillna(0)

            titles = {
                "ice_facility_count": "ICE facilities (count)",
                "pct_foreign_born": "% foreign-born",
                "pct_non_citizen": "% non-citizen",
            }
            color_title = titles.get(metric, metric)

            fig = px.choropleth(
                df_plot,
                locations="state_abbr",
                locationmode="USA-states",
                color=metric,
                scope="usa",
                color_continuous_scale=[
                    "#330000",
                    "#7f0000",
                    "#ff0000",
                    "#ff8c00",
                ],
                hover_name="state_name",
                labels={metric: color_title},
            )
            fig.update_layout(
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor="#050508",
                plot_bgcolor="#050508",
                coloraxis_colorbar_title=color_title,
            )
            return fig

    with ui.card():
        ui.card_header("National ICE detention trends")

        @render_plotly
        def national_trends():
            import plotly.graph_objects as go

            df = _load_national_data()

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["date"],
                    y=df["midnight_pop"],
                    mode="lines",
                    name="Midnight population",
                    line=dict(color="#ff4d4d", width=2),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["date"],
                    y=df["daily_pop"],
                    mode="lines",
                    name="24-hour population",
                    line=dict(color="#ffa64d", width=1.8),
                )
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#050508",
                plot_bgcolor="#050508",
                margin=dict(l=40, r=20, t=40, b=40),
                xaxis_title="Date",
                yaxis_title="People in ICE detention",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            return fig
# Shiny Express apps do not need an explicit `App(...)` object.
# Running `python -m shiny run --reload app.py` will discover the UI defined above.

