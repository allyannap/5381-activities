from pathlib import Path
import pandas as pd
from shiny.express import input, render, ui
from shiny import reactive
from shinywidgets import render_plotly

ROOT = Path(__file__).resolve().parent
JOINED_CSV = ROOT / "census_vera_joined.csv"
NATIONAL_CSV = ROOT / "data" / "national.csv"


def _load_state_data() -> pd.DataFrame:
    df = pd.read_csv(JOINED_CSV, dtype={"state": str})
    if "state_abbr" not in df.columns:
        raise RuntimeError("Expected 'state_abbr' column in census_vera_joined.csv.")
    return df


def _load_national_data() -> pd.DataFrame:
    if not NATIONAL_CSV.exists():
        raise RuntimeError(
            f"National trends file not found at {NATIONAL_CSV}. "
            "Run download_vera_national.py in the hw1 folder to fetch it."
        )
    return pd.read_csv(NATIONAL_CSV, parse_dates=["date"])


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
ui.page_opts(title=None, fillable=True)
ui.tags.head(ui.tags.title("ICE & Demographics Dashboard"))

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
ui.tags.style(
        """
        /* ---------- LET PAGE BE NORMAL (no forced clipping) ---------- */
    html, body { overflow: auto; }

    /* ---------- COMPACT SIDEBAR (so button is visible) ---------- */
    .sidebar {
        padding: 10px 10px !important;
        overflow-y: auto;              /* sidebar can scroll if needed */
        font-size: 0.92rem !important; /* overall smaller text */
    }

    /* Make headings smaller + consistent */
    .sidebar h3, .sidebar h4 {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        margin: 0 0 6px 0 !important;
    }

    /* Reduce label + input spacing */
    .sidebar .form-label {
        margin: 0 0 4px 0 !important;
        font-size: 0.92rem !important;
    }

    .sidebar .shiny-input-container {
        margin-bottom: 10px !important;
    }

    /* Reduce HR spacing */
    .sidebar hr {
        margin: 10px 0 !important;
    }

    /* Make multi-select shorter */
    .sidebar select[multiple] {
        height: 115px !important;  /* key: shorter list */
    }

    /* Smaller button */
        .report-btn-wrap { margin-top: 10px !important; }
        .report-btn-wrap .btn {
        padding: 8px 10px !important;
        font-size: 0.90rem !important;
    }

    /* Header (more compact) */
    #ice-dashboard-header {
        flex: 0 0 auto;
        width: 100%;
        box-sizing: border-box;
        padding: 6px 12px;  /* smaller */
        display: flex;
        justify-content: center;
        align-items: center;
        background: #ffffff;
        border-bottom: 1px solid rgba(0,0,0,0.12);
    }
    #ice-dashboard-header .ice-title {
        margin: 0;
        font-size: 1.2rem;  /* smaller */
        font-weight: 700;
        line-height: 1.1;
        text-align: center;
        white-space: nowrap;
    }

    /* cards/sidebar light styling */
    .sidebar, .card, .bslib-card {
        background-color: #ffffff;
        color: #1a1a1a;
        border: 1px solid #e0e0e0;
    }

    /* Card compact padding */
    .card-header, .bslib-card .card-header { padding: 6px 10px !important; }
    .card-body, .bslib-card .card-body { padding: 8px 10px !important; }

    /* Main area fit viewport */
    .main-content-wrap, #ice-main-container {
        height: 100%;
        min-height: 0;
        display: flex;
        flex-direction: column;
        overflow: hidden !important;
    }

    .viz-row { flex: 0 0 auto !important; min-height: 0 !important; min-width: 0; }

    /* Table area should not scroll */
    .state-comparison-wrap {
        flex: 0 0 auto !important;
        min-height: 0 !important;
        overflow: hidden !important;
        min-width: 0;
    }

    .viz-card .card-body { min-height: 0 !important; }

    /* Dataframe: prevent internal scrollbars */
    .shiny-data-grid, .shiny-data-grid * { overflow: hidden !important; }

    .sidebar .keyword { color: #ff8c00; font-weight: bold; }
    .report-btn-wrap { margin-top: 1.5rem; }
    .report-btn-wrap .btn { width: 100%; }
    """
)

with ui.div(id="app-shell"):
    # Header (top)
    ui.tags.div(
        {"id": "ice-dashboard-header"},
        ui.tags.span("ICE & Demographics Dashboard", class_="ice-title"),
    )

    # Content (sidebar + main)
    with ui.layout_sidebar(fillable=True):
        with ui.sidebar(open="desktop", id="sidebar"):
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
            ui.h4("Filters")
            ui.input_select(
                "state_select",
                "Compare states",
                multiple=True,
                choices=[],
            )

        ui.div(
            {"class": "report-btn-wrap"},
            ui.input_action_button(
                "report_btn",
                "Written Report and Analytic",
                class_="btn btn-secondary",
            ),
        )

        # Populate state choices
        @reactive.effect
        def _populate_state_select():
            try:
                df = _load_state_data()
            except RuntimeError:
                return
            names = sorted(df["state_name"].astype(str).unique())
            ui.update_select("state_select", choices={n: n for n in names})

        # ✅ MAIN AREA
        with ui.div(class_="main-content-wrap"):
            with ui.div(class_="main_container", id="ice-main-container"):

                with ui.div(class_="viz-row"):
                    with ui.layout_columns(col_widths=(6, 6), row_heights="1fr"):

                        with ui.card(class_="viz-card"):
                            ui.card_header("ICE detention activity by state")

                            @render_plotly
                            def map_choropleth():
                                import plotly.express as px

                                df = _load_state_data()
                                metric = input.map_metric()

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
                                    color_continuous_scale=["#330000", "#7f0000", "#ff0000", "#ff8c00"],
                                    hover_name="state_name",
                                    labels={metric: color_title},
                                )
                                fig.update_layout(
                                    template="plotly_white",
                                    height=210,
                                    margin=dict(l=0, r=0, t=20, b=0),
                                    paper_bgcolor="#ffffff",
                                    plot_bgcolor="#ffffff",
                                    font=dict(size=12),
                                    coloraxis_colorbar=dict(
                                        title=dict(text=color_title, font=dict(size=13)),
                                        tickfont=dict(size=11),
                                        thickness=16,
                                        len=0.75,
                                        x=1.02,
                                        xanchor="left",
                                    ),
                                )

                                fig.update_geos(
                                    scope="usa",
                                    fitbounds="locations",
                                    projection_type="albers usa",
                                    showlakes=False,
                                    bgcolor="rgba(0,0,0,0)",
                                )

                                return fig

                        with ui.card(class_="viz-card"):
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
                                        line=dict(color="#ff4d4d", width=2.5),
                                    )
                                )
                                fig.add_trace(
                                    go.Scatter(
                                        x=df["date"],
                                        y=df["daily_pop"],
                                        mode="lines",
                                        name="24-hour population",
                                        line=dict(color="#ffa64d", width=2.2),
                                    )
                                )
                                fig.update_layout(
                                    template="plotly_white",
                                    height=210,  # <-- reduced
                                    paper_bgcolor="#ffffff",
                                    plot_bgcolor="#ffffff",
                                    margin=dict(l=50, r=20, t=40, b=40),
                                    xaxis=dict(title=dict(text="Date", font=dict(size=14)), tickfont=dict(size=12)),
                                    yaxis=dict(
                                        title=dict(text="People in ICE detention", font=dict(size=14)),
                                        tickfont=dict(size=12),
                                    ),
                                    legend=dict(
                                        orientation="h",
                                        yanchor="bottom",
                                        y=1.02,
                                        xanchor="right",
                                        x=1,
                                        font=dict(size=12),
                                    ),
                                )
                                return fig

                with ui.div(class_="state-comparison-wrap"):
                    with ui.card():
                        ui.card_header("State comparison")

                        @render.data_frame
                        def comparison_table():
                            df = _load_state_data()
                            states = input.state_select()

                            cols = [
                                "state_name",
                                "ice_facility_count",
                                "total_population",
                                "non_citizen",
                                "pct_non_citizen",
                                "foreign_born",
                                "pct_foreign_born",
                            ]

                            rename_map = {
                                "state_name": "State",
                                "ice_facility_count": "ICE facilities (count)",
                                "total_population": "Total population",
                                "non_citizen": "Non-citizen",
                                "pct_non_citizen": "% non-citizen",
                                "foreign_born": "Foreign-born",
                                "pct_foreign_born": "% foreign-born",
                            }

                            if not states:
                                return df[cols].head(6).rename(columns=rename_map)

                            subset = df[df["state_name"].astype(str).isin(states)]
                            out = subset[[c for c in cols if c in subset.columns]].copy()
                            return out.rename(columns=rename_map).head(6)

                # 🔎 Optional: short on-screen AI report triggered by the button
                @render.ui
                def report_output():
                    return ui.div()

                @reactive.effect
                def _run_report_on_click():
                    from pathlib import Path

                    # Only react on actual button clicks (ignore initial 0)
                    if input.report_btn() is None or input.report_btn() < 1:
                        return

                    txt_path = Path(__file__).resolve().parent / "ice_report.txt"
                    if not txt_path.exists():
                        report_output.set_ui(
                            ui.p(
                                "Run `ai_reporter_ollama.py` first to generate the AI report "
                                "files (ice_report.txt / .md / .docx)."
                            )
                        )
                        return

                    snippet = txt_path.read_text(encoding="utf-8").strip()
                    # Keep the dashboard view compact – only show first ~400 words.
                    words = snippet.split()
                    if len(words) > 400:
                        snippet = " ".join(words[:400]) + " ..."

                    report_output.set_ui(
                        ui.card(
                            ui.card_header("Written Report and Analytics"),
                            ui.pre(snippet),
                        )
                    )