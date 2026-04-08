# Lab 6 — Multi-agent tools (VERA detention trends)

## Goal

Demonstrate **function calling** plus a **two-agent chain** using `agent_run()` from `dsai/08_function_calling/functions.py` (same pattern as `03_agents_with_function_calling.py` / `04_multiple_agents_with_function_calling.py`).

- **Agent 1 (research / dataset)**: Uses the LLM to call **`get_vera_detention_trends`** exactly once with arguments inferred from the user question (state, optional `metric` / `days`). The LLM does **not** read CSV files; Python/pandas does inside the tool.
- **Agent 2 (reporting)**: Receives a slim JSON payload with **`vera_statistics_from_data_files`** (the tool’s return value) and writes a **short public-facing report**: key statewide statistics, and **one** facility—the site with the **largest** `latest_metric_value` among rows in **`top_facilities`** (compare all rows; list order is not rank). The prompt stresses copying numbers from the JSON to reduce hallucination.

The runnable script is **`lab6_multi_agent_tools.py`**. It also defines **NewsAPI** and **Census** tool functions and schemas for later expansion; the **end-to-end chain** in `run_chain()` currently wires **only the VERA tool** for Agent 1.

## Data (local VERA extracts)

Place CSVs under **`lab6_multi_agent_tools/data/`**:

- **Texas**: `texas_pt1.csv` and `texas_pt2.csv` (concatenated by the tool).
- **Other states**: e.g. `new_york.csv`, `national.csv` as needed.
- **`facilities.csv`**: metadata for facility names/locations when building `top_facilities`.

The tool returns JSON with fields such as `state`, `metric`, `days`, `as_of_date`, `latest_value`, `window_avg`, `window_change`, `facility_count`, `top_facilities`, and `source_files`.

**Interpretation note:** `window_change` is the difference between the **first and last day** of the requested window in the extract—not a separate “previous month.” `latest_value` is **statewide**; facility counts are only under `top_facilities[].latest_metric_value`. The “highest” facility named in the report is the maximum **among listed** `top_facilities` (the tool returns a capped list), not necessarily every facility in the state unless you extend the tool.

## How to run

1. Start **Ollama** and pull the model (default in script is **`llama3.1:8b`**):

   ```bash
   ollama serve
   ollama pull llama3.1:8b
   ```

2. From the repo (or this folder):

   ```bash
   python lab6_multi_agent_tools.py
   ```

3. Optional environment variables:

   - **`MODEL`**: Ollama tag (default `llama3.1:8b`).
   - **`PORT`**, **`OLLAMA_HOST`**: Ollama endpoint (default `http://localhost:11434`).
   - **`OLLAMA_HTTP_TIMEOUT`**: Per-request timeout in seconds (default `25`).
   - **`AGENT1_CHAIN_TIMEOUT_SEC`**, **`AGENT2_CHAIN_TIMEOUT_SEC`**: Max wall time per agent step (default `30` each). On timeout the process exits with an error message.
   - **`NEWSAPI_API_KEY`**, **`CENSUS_API_KEY`**: Only needed if you call the News/Census tools directly; not required for the VERA-only chain.

The harness uses a single **`messages`** list with one user prompt (mirror of the course script style). Output includes **Agent 1 raw tool result**, the full **evidence `dataset_json`**, and **Agent 2 report**.

## Grounding and accuracy

Numbers in the report should match **`vera_statistics_from_data_files`**. If Agent 1’s printed JSON is correct but Agent 2 drifts, that is usually **language model error**, not bad file I/O. Compare the report digit-by-digit to the **Agent 1 tool output** on the same run.

## Relation to other labs and Homework 2

- **Lab 1 / prompt design**: Agent roles (research vs. reporting) and separation of concerns.
- **Lab 2 / RAG**: Article retrieval from SQLite is a natural **additional** evidence source; this folder’s **current** demo emphasizes **structured numeric** evidence from **local VERA CSVs** via a tool.
- **Homework 2**: You can document this script as the **tools + multi-agent** slice: tool schema, `agent_run` chaining, screenshots of Agent 1 output and Agent 2 report, plus setup (Ollama, data files, env vars).

## What “done” looks like for this checkpoint

- `get_vera_detention_trends` runs against local data and returns stable JSON.
- Agent 1 invokes that tool via function calling; Agent 2 writes a concise report from **`vera_statistics_from_data_files`** with accurate statewide figures and the **single highest-count** facility from `top_facilities`, plus provenance from `source_files` (basenames).
