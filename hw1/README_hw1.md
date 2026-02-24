## Homework 1 – ICE & Demographics Tool Documentation

This document describes the data, technical details, and usage instructions for the Homework 1 toolchain: the Census/Vera data preparation scripts, the ICE & Demographics Shiny dashboard, and the AI reporting helper.

---

## Data Summary (Joined Dataset Columns)

The main dataset used by the dashboard and AI reporter is `census_vera_joined.csv`. It is a **state‑level** table created by combining expanded Census ACS data with Vera ICE detention facility counts. The table contains more fields than the dashboard directly shows; the variables below are the **primary columns surfaced in the app and/or used by the AI summaries.**

### Dataset overview

- **Unit of observation**: U.S. state (one row per state)
- **Key sources**:
  - U.S. Census Bureau ACS 5‑Year Estimates (demographics and nativity)
  - Vera Institute of Justice ICE detention facilities data
- **Typical record count**: 50 states + District of Columbia

### Key columns

| Column name              | Type      | Description                                                                 |
|--------------------------|-----------|-----------------------------------------------------------------------------|
| `state`                  | string    | State FIPS code (2‑digit string from Census).                              |
| `state_name`             | string    | Full state name (e.g., “California”).                                      |
| `state_abbr`             | string    | Two‑letter state abbreviation (e.g., “CA”).                                |
| `total_population`       | integer   | Total population estimate for the state.                                   |
| `non_citizen`            | integer   | Count of residents who are not U.S. citizens.                              |
| `pct_non_citizen`        | numeric   | Percent of residents who are non‑citizens.                                 |
| `foreign_born`           | integer   | Count of residents who are foreign‑born (regardless of citizenship).       |
| `pct_foreign_born`       | numeric   | Percent of residents who are foreign‑born.                                 |
| `ice_facility_count`     | integer   | Number of ICE detention facilities located in the state (from Vera).       |
| `pct_foreign_born`       | numeric   | Percent of residents who are foreign‑born.                                 |
| `pct_non_citizen`        | numeric   | Percent of residents who are non‑citizens.                                 |

Additional metrics (such as age structure, race/ethnicity breakdowns, poverty, and educational attainment) are included in `census_vera_joined.csv` but are not all directly visualized in the dashboard UI. They can be used for further analysis or extended visualizations if needed.

The AI reporter script (`ai_reporter_openai.py`) focuses especially on:

- `pct_foreign_born`
- `pct_non_citizen`
- `ice_facility_count`

These metrics are highlighted in the written narrative and bullet‑point takeaways.

---

## Technical Details

### Key scripts and files

- **`hw1.py`**  
  - Calls the Census ACS API (multiple tables) and builds an expanded state‑level demographics table.  
  - Produces intermediate CSV(s) with citizenship, age, race, poverty, and education metrics.

- **`join_census_vera.py`**  
  - Joins the expanded Census data to Vera ICE facility counts by state.  
  - Performs a **left join** from the Census demographics table to the Vera facilities table using `state_abbr` (Census) = `state` (Vera).  
  - Writes the main dataset used by both the dashboard and the AI reporter: `census_vera_joined.csv`.

- **`download_vera_national.py`**  
  - Downloads or prepares a national time‑series of ICE detention populations.  
  - Saves `data/national.csv`, used for the “National ICE detention trends” line chart.

- **`app.py`** (Shiny dashboard)  
  - Implements the **ICE & Demographics Dashboard** using Shiny for Python.  
  - Key components:
    - Left sidebar controls and filters.  
    - Choropleth map of the U.S. by state, with selectable metric:
      - `ice_facility_count`, `pct_foreign_born`, `pct_non_citizen`.  
    - Line chart of national ICE detention trends from `data/national.csv`.  
    - State comparison table with selected summary columns.  
    - **“Written Report and Analytic”** button that triggers an AI report.

- **`ai_reporter_openai.py`** (AI reporting helper)  
  - Loads `census_vera_joined.csv`.  
  - Builds a compact markdown summary of key metrics (top/bottom states, medians).  
  - Sends the summary to an OpenAI model and receives a narrative report.  
  - Saves formatted outputs:
    - `ice_report.txt` (plain text with title header)  
    - `ice_report.md` (markdown with the same content)  
    - `ice_report.docx` (Word document with headings and bullet lists)

> The dashboard reuses `build_summary_markdown()` and `call_openai()` from `ai_reporter_openai.py` so that the report can be generated directly from the UI based on the user’s selected states.

### APIs, credentials, and configuration

- **Census ACS API**
  - Base URL: `https://api.census.gov/data/2024/acs/acs5`  
  - Access: Requires a `CENSUS_API_KEY` defined in a `.env` file.  
  - Used by: `hw1.py` and related data‑prep helpers.

- **Vera ICE data**
  - Accessed via downloaded CSVs / helper scripts (`download_vera_national.py` and facility data files).  
  - No authentication required once the CSVs are present locally.

- **OpenAI API**
  - Used by: `ai_reporter_openai.py` and by the “Written Report and Analytic” button in `app.py`.  
  - Requires `OPENAI_API_KEY` in a `.env` file in the `hw1` directory.  
  - Model: `gpt-4.1-mini` (configured at the top of `ai_reporter_openai.py`).

### Packages used

- `pandas` – loading, merging, and transforming tabular data.  
- `requests` – making HTTP calls to external APIs (Census, if used directly in your scripts).  
- `python-dotenv` – loading environment variables from `.env` files (`CENSUS_API_KEY`, `OPENAI_API_KEY`).  
- `shiny` / `shiny.express` – building the interactive dashboard (`app.py`).  
- `shinywidgets` and `plotly` – interactive charts (choropleth map and line chart).  
- `openai` – communicating with the OpenAI Chat Completions API.  
- `python-docx` – writing the formatted Word document `ice_report.docx`.

### File structure (HW1 folder)

- `hw1.py` – Census ACS data expansion script.  
- `join_census_vera.py` – merges Census data with Vera facilities, creates `census_vera_joined.csv`.  
- `download_vera_national.py` – fetches / prepares `data/national.csv`.  
- `app.py` – Shiny dashboard entrypoint.  
- `ai_reporter_openai.py` – AI narrative report generator.  
- `census_vera_joined.csv` – main joined dataset for dashboard + AI.  
- `data/national.csv` – national ICE detention trend data.  
- `ice_report.txt`, `ice_report.md`, `ice_report.docx` – AI‑generated narrative outputs.  
- `.env` – local configuration (API keys; not committed to git).

---

## Usage Instructions

This section explains how to set up dependencies, configure keys, and run the software end‑to‑end.

### 1. Install dependencies

From the project root or from inside `5381-activities/hw1`, create a virtual environment (optional but recommended) and install the required packages:

```bash
cd 5381-activities/hw1
python -m venv venv
venv\Scripts\activate           # On Windows PowerShell

python -m pip install -r requirements.txt
```

If a `requirements.txt` file is not available, the core packages can be installed manually:

```bash
python -m pip install pandas requests python-dotenv shiny shinywidgets plotly openai python-docx
```

### 2. Configure API keys (`.env` file)

Create a file named `.env` in the `5381-activities/hw1` directory with at least the following keys:

```env
CENSUS_API_KEY=your_census_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

Guidance:

- Request a free Census API key at the Census developer site.  
- Create an OpenAI API key from your OpenAI account dashboard.  
- **Do not** commit `.env` to git; it should stay local on your machine.

### 3. Prepare the data

From the `hw1` folder:

```bash
# 1) Pull and expand Census ACS demographics
python hw1.py

# 2) Join expanded Census data with Vera facility counts
python join_census_vera.py

# 3) Download / prepare national Vera ICE detention trends
python download_vera_national.py
```

After these steps you should have:

- `citizenship_demographics_expanded.csv` (expanded Census demographics by state)  
- `census_vera_joined.csv` (main state‑level joined dataset)  
- `data/national.csv` (national ICE detention trend data)

### 4. Run the Shiny dashboard

Still in the `hw1` directory:

```bash
python -m shiny run --reload app.py
```

Then open the URL shown in the terminal (typically `http://127.0.0.1:8000`) in your browser.

In the app you can:

- Choose a metric for the U.S. map under **“Map shows”**.  
- Select one or more states in **“Compare states”**.  
- View the **State comparison** table and **National ICE detention trends** line chart.

### 5. Generate an AI report

There are two ways to generate a narrative report.

#### Option A – From the command line

From `hw1`:

```bash
python ai_reporter_openai.py
```

This uses the full `census_vera_joined.csv` dataset (all states) to build a summary and then calls OpenAI. When it finishes, you should see:

- `ice_report.txt`  
- `ice_report.md`  
- `ice_report.docx`

in the `hw1` folder.

#### Option B – From inside the dashboard

1. Start the app with `python -m shiny run --reload app.py`.  
2. Select one or more states under **“Compare states”** (for example, Florida and Pennsylvania).  
3. Click the **“Written Report and Analytic”** button in the sidebar.
4. The app will:
   - Filter `census_vera_joined.csv` to the selected states.  
   - Call OpenAI using that filtered summary.  
   - Save fresh versions of `ice_report.txt`, `ice_report.md`, and `ice_report.docx`.  
   - Show an **AI report status** message under the table confirming that the `.docx` was created, with a **“Return to dashboard”** button to clear the status.

### 6. Troubleshooting

- **Census API errors or missing data**
  - Re‑check `CENSUS_API_KEY` in `.env`.  
  - Ensure you have network connectivity when running `hw1.py` or other data‑prep scripts.

- **OpenAI quota / key errors**
  - Confirm `OPENAI_API_KEY` is set correctly in `.env`.  
  - If you see “insufficient_quota” or similar in the terminal, you may need to switch to a different OpenAI project or adjust billing.

- **Dashboard loads but charts are empty**
  - Verify that `census_vera_joined.csv` and `data/national.csv` exist in the `hw1` folder and `data/` subfolder respectively.  
  - Re‑run `join_census_vera.py` and `download_vera_national.py` if necessary.

- **AI report status does not appear**
  - Make sure at least one state is selected under **“Compare states”** before clicking the report button.  
  - Check the terminal where the Shiny app is running for any Python exceptions related to OpenAI.

---

## Quick Reference

| Component                  | Purpose                                               |
|---------------------------|-------------------------------------------------------|
| `hw1.py`                  | Fetch and expand Census ACS demographics.             |
| `join_census_vera.py`     | Join Census data with Vera ICE facility counts.       |
| `download_vera_national.py` | Download/prepare national ICE detention trends.     |
| `app.py`                  | Shiny dashboard (map, trends, state comparison, AI button). |
| `ai_reporter_openai.py`   | Generate narrative report and export `.txt/.md/.docx`. |
| `census_vera_joined.csv`  | Main state‑level dataset for dashboard + AI.          |
| `data/national.csv`       | National ICE detention time‑series.                   |
| `.env`                    | Stores `CENSUS_API_KEY` and `OPENAI_API_KEY` (local). |