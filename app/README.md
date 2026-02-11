# US Citizenship Dashboard — Documentation

## 📋 Overview

The **US Citizenship Dashboard** is a Shiny for Python app that uses the U.S. Census Bureau’s ACS 5‑Year Estimates (2024) to help you explore citizenship and nativity patterns across all U.S. states, DC, and Puerto Rico. It turns the `my_good_query.py` Census API call into an interactive reporter-style dashboard for casual users.

- **Data source:** U.S. Census Bureau – ACS 5‑Year (Citizenship table B05001)  
- **Geography:** All U.S. states, District of Columbia, and Puerto Rico  
- **Metrics:** Foreign‑born, non‑citizen, and naturalized counts and rates  
- **Use case:** Quick rankings, map exploration, and state‑to‑state comparisons  

---

## 🔧 App Structure & Features

### Main features

- **On‑demand Census query:** Click “Run Census query” to fetch fresh ACS 5‑year citizenship data.  
- **State rankings:** Sortable table of states ranked by **% foreign‑born**, **% non‑citizen**, or **% naturalized**, with both counts and rates.  
- **Map view:** Choropleth map of states colored by the selected metric (e.g., **% non‑citizen**) with hover tooltips.  
- **State comparison:** Side‑by‑side comparison table for selected states, including per‑100k metrics.  
- **Error handling:** Friendly messages when the API key is missing or the Census API fails.  

### Data used

| Code | Description |
|------|-------------|
| `B01001_001E` | Total population |
| `B05001_005E` | Naturalized U.S. citizen |
| `B05001_006E` | Not a U.S. citizen |

The app **approximates foreign‑born** as:  
`foreign_born = B05001_005E (naturalized) + B05001_006E (non‑citizen)`.

---

## 📦 Installation

From the `5381-activities/app` folder, install the Python dependencies:

```bash
pip install -r requirements.txt
```

You also need a **Census API key** (free) from the Census developer portal.

---

## 🚀 Running the App

1. **Set up your `.env` file** (see next section).  
2. Open a terminal in `5381-activities/app`.  
3. Run the Shiny app:

```bash
python -m shiny run --reload app.py
```

4. Open the URL shown in the terminal (usually `http://127.0.0.1:8000/`) in your browser.

When the app loads, click **“Run Census query”** in the sidebar to fetch and display data.

---

## 🔑 API Key Configuration

The app expects your Census API key in a local `.env` file (not committed to version control).

In `5381-activities/app`, create a `.env` file with:

```env
CENSUS_API_KEY=your_census_api_key_here
```

If the key is missing or invalid, the app shows a **yellow warning banner** with a clear explanation instead of crashing.

---

## 📊 UI & Interactions

### Sidebar controls

- **Run Census query:** Triggers the ACS API call and refreshes all views.  
- **Ranking metric:** Choose:
  - `% foreign-born`
  - `% non-citizen`
  - `% naturalized`
- **View:** Toggle between:
  - **Rate (share of population)**  
  - **Count (absolute number of people)**  
- **Compare states:** Multi‑select dropdown to focus comparison on 2–3 states of interest.

### State rankings

- Shows a sortable table with:
  - State name  
  - Total population  
  - Foreign‑born, non‑citizen, and naturalized counts  
  - Corresponding percentages  
- The selected metric is used to rank states from highest to lowest.

### Map view (choropleth)

- Uses **Plotly** to show a USA choropleth map by state.  
- Colors each state by the selected metric (`% foreign-born`, `% non-citizen`, or `% naturalized`).  
- Hovering displays:
  - State name  
  - Value of the current metric  

### State comparison table

- Filters to selected states (or shows all if none selected).  
- Columns include:
  - Total population  
  - Foreign‑born, non‑citizen, naturalized counts  
  - Percentages for each  
  - Per‑100k metrics:
    - Foreign‑born per 100k  
    - Non‑citizen per 100k  
    - Naturalized per 100k  

---

## 🧠 App Logic (High‑Level)

```mermaid
flowchart LR
    A[User clicks 'Run Census query'] --> B[Fetch ACS B05001 data<br/>for all states]
    B --> C[Build pandas DataFrame]
    C --> D[Compute foreign-born,<br/>non-citizen, naturalized<br/>counts and rates]
    D --> E[Rankings table]
    D --> F[Map view (Plotly choropleth)]
    D --> G[State comparison table]
    D --> H[Populate 'Compare states' choices]
    B --> I[Error handler]
    I --> J[Show friendly warning<br/>if API key / request fails]
```

The app uses **reactive calculations** so that changing inputs (metric, view, selected states) updates only the necessary outputs.

---

## 🧪 Testing Checklist

- **Install:** `pip install -r requirements.txt` completes without errors.  
- **Run:** `python -m shiny run --reload app.py` starts the server.  
- **API:** Clicking **“Run Census query”** loads data without error when the API key is valid.  
- **UI:** Rankings table, map, and comparison table all render in the browser.  
- **Errors:** Removing or breaking `CENSUS_API_KEY` shows a clear warning instead of a crash.  

---

## ✅ Summary

| Item | Detail |
|------|--------|
| **App** | US Citizenship Dashboard (Shiny for Python) |
| **Data** | ACS 5‑Year (2024), citizenship table B05001 |
| **Geography** | All U.S. states, DC, Puerto Rico |
| **Key metrics** | Foreign‑born, non‑citizen, naturalized (counts, rates, per‑100k) |
| **Main views** | Rankings table, choropleth map, state comparison |

