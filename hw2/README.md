# HW2 Multi-Agent RAG System Documentation

This folder contains the Homework 2 multi-agent system:
- Folder: `5381-activities/labs/hw2`
- Main system file: `hw2_multi_agent_rag_system.py`

## System Architecture

The system uses a **two-agent workflow** with tool calling and a lightweight retrieval step:

1. **Agent 1 (Research / Data Collection)**
   - Runs with `output="tools"` and calls three tools:
     - `get_vera_detention_trends`
     - `get_recent_ice_articles`
     - `get_census_demographics`
   - Returns structured tool outputs (JSON-like dicts), not prose.
   - If a model skips a required tool call, `_backfill_missing_tools_if_needed()` executes the missing tool(s) in Python to guarantee all three data sources are present.

2. **Evidence Packaging + Retrieval Step**
   - Tool outputs are bundled into `dataset_json`.
   - The system writes an evidence artifact to `data/retrieval_store/agent1_evidence_<timestamp>.json`.
   - `_retrieve_related_articles_from_evidence()` performs local retrieval over saved article evidence using keyword matching plus tool-derived signals (scope/relevance/intent flags).

3. **Agent 2 (Grounded Report Writer)**
   - Receives a strict JSON payload containing:
     - retrieved news matches
     - VERA detention statistics
     - Census demographics
   - Produces a neutral, structured public briefing.
   - Does **not** call tools and is instructed to copy numbers exactly from evidence fields.

## RAG Data Source

This project uses a hybrid evidence strategy:

- **Primary structured data source (local files):**
  - `data/texas_pt1.csv`, `data/texas_pt2.csv`, `data/new_york.csv`, `data/national.csv`
  - `data/facilities.csv`
  - Used by `get_vera_detention_trends()` with pandas aggregation.

- **Live API sources (external):**
  - NewsAPI (`get_recent_ice_articles`)
  - U.S. Census API ACS 1-year (`get_census_demographics`)

- **RAG search function:**
  - `_retrieve_related_articles_from_evidence(evidence_path, user_query, limit=5)`
  - Reads the saved Agent 1 evidence JSON and ranks candidate articles by:
    - query term hits
    - scope match
    - ICE relevance
    - detention/arrest intent match
    - recency and focus score
  - Returns a filtered/ranked list for Agent 2 grounding.

## Tool Functions

### `get_vera_detention_trends(state="national", metric="midnight_pop", days=30)`
- **Purpose:** Compute state/national detention trend metrics from local CSV data.
- **Parameters:**
  - `state` (string): US state name/abbrev or `national`
  - `metric` (string): `midnight_pop` or `daily_pop`
  - `days` (number): trailing window (`2..365`)
- **Returns:**
  - Success: `state`, `metric`, `days`, `as_of_date`, `latest_value`, `window_avg`, `window_change`, `year_over_year_*`, `facility_count`, `top_facilities`, `source_files`
  - Failure: structured `error` payload with hints and available files/states

### `get_recent_ice_articles(location, topic="", limit=5)`
- **Purpose:** Fetch recent ICE-related news from NewsAPI and filter for relevance.
- **Parameters:**
  - `location` (string, required): location scope (state/city/national)
  - `topic` (string): optional keyword refinement
  - `limit` (number): max output articles (`1..20`)
- **Returns:**
  - `articles` list with `headline`, `source`, `date`, `url`, `snippet`, `location_tags`, `article_excerpt`, and filtering signals (`scope_match`, `ice_relevance`, `intent_match`)
  - `filtering` metadata + `source` metadata
  - Structured `error` when API key/request fails

### `get_census_demographics(state)`
- **Purpose:** Fetch state-level demographic context from Census ACS 1-year API.
- **Parameters:**
  - `state` (string, required): US state name or abbreviation
- **Returns:**
  - `total_population`, `foreign_born_count/pct`, `non_citizen_count/pct`, `median_household_income_usd`, plus source provenance
  - Structured `error` for missing key, invalid state, national-only requests, or API failures

## Technical Details

- **Language/runtime:** Python 3
- **Core packages:** `pandas`, `requests`, `python-dotenv` (optional but supported), plus standard library
- **LLM orchestration:** `agent_run()` from `dsai/08_function_calling/functions.py`
- **Model serving:** Ollama (`http://localhost:11434` by default)
- **Config env vars:**
  - Required for full functionality:
    - `NEWSAPI_API_KEY`
    - `CENSUS_API_KEY`
  - Optional:
    - `MODEL` (default `llama3.1:8b`)
    - `PORT`, `OLLAMA_HOST`
    - `OLLAMA_HTTP_TIMEOUT`
    - `AGENT1_CHAIN_TIMEOUT_SEC`
    - `AGENT2_CHAIN_TIMEOUT_SEC`
    - `NEWS_EXCERPT_MAX_CHARS`
    - `NEWS_EXCERPT_ARTICLE_LIMIT`
    - `NEWS_EXCERPT_TIMEOUT_SEC`
    - `CENSUS_YEAR`
- **Important paths:**
  - `hw2_multi_agent_rag_system.py` (entry script)
  - `data/` (local VERA and facility files)
  - `data/retrieval_store/` (persisted Agent 1 evidence for retrieval)

## Usage Instructions

### 1) Install dependencies

From the repository root:

```bash
python -m pip install pandas requests python-dotenv
```

### 2) Start Ollama and pull a model

```bash
ollama serve
ollama pull llama3.1:8b
```

### 3) Configure API keys

Add these to your environment (or `.env` loaded by your project):

```bash
export NEWSAPI_API_KEY="your_newsapi_key"
export CENSUS_API_KEY="your_census_key"
```

If keys are missing, tools return structured errors (the script still runs, but with reduced evidence quality).

### 4) Verify data files

Ensure these files exist under `5381-activities/labs/hw2/data/`:
- `texas_pt1.csv`
- `texas_pt2.csv`
- `new_york.csv`
- `national.csv`
- `facilities.csv`

### 5) Run the system

```bash
cd 5381-activities/labs/hw2
python hw2_multi_agent_rag_system.py
```

### 6) What output to expect

The script prints:
- Agent 1 raw tool calls/results
- Combined `dataset_json`
- path to saved evidence JSON
- retrieved news matches from the evidence search step
- Agent 2 final grounded brief
