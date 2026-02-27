# Lab 03 — Census citizenship data for AI reporting

## What this is

This folder contains **processed U.S. Census ACS 5-Year (2024) citizenship data** by state, formatted for AI consumption. The pipeline:

1. **Queries** the same API used in the previous lab (`my_good_query.py` / app): Census Bureau ACS 5-year, table B05001 (citizenship).
2. **Cleans and aggregates**: numeric types, derived rates (%, per 100k), and state rankings by non-citizen count, % non-citizen, and foreign-born count.
3. **Exports CSV** with clear column names and a data dictionary.

## Important note on data meaning

- **This data is citizenship and nativity demographics by state** (total population, non-citizen, naturalized, foreign-born counts and rates). It is **not** ICE arrest, detention, or enforcement data.
- For **ICE arrests/detentions**, you would need other sources (e.g. TRAC, FOIA releases). This dataset can still support **context** for AI reporting: e.g. which states have the largest or highest-share non-citizen and foreign-born populations, and how they rank.

## Files

| File | Purpose |
|------|--------|
| `fetch_and_process_census.py` | Script: fetch API → clean → aggregate → write CSVs. |
| `citizenship_by_state.csv` | One row per state: counts, rates, rankings. **Main file for AI.** |
| `citizenship_rankings_summary.csv` | Top/bottom 15 states by non-citizen count, % non-citizen, and foreign-born count. |
| `data_dictionary.csv` | Column names and short descriptions for AI. |

## How to run

From this folder (or with `PYTHONPATH` set so `lab03` is on the path):

```bash
python fetch_and_process_census.py
```

Requires:

- `CENSUS_API_KEY` in `5381-activities/app/.env` or `lab03/.env`
- `requests`, `pandas`, `python-dotenv`

## Using the data for AI

- **Primary input**: `citizenship_by_state.csv`. UTF-8, header row, one row per state. Use for state-level trends and rankings.
- **Quick patterns**: `citizenship_rankings_summary.csv` gives top/bottom states by three metrics for summary sentences.
- **Column meanings**: `data_dictionary.csv` lists each column and a one-line description.

Example prompts for an AI:

- “Summarize which states have the highest non-citizen population (count and share) and how they rank.”
- “Describe patterns in foreign-born and non-citizen population by state using the provided CSV.”
- “Which states are in the top 10 by non-citizen share and by non-citizen count? How do they differ?”
