# How to test this lab with Ollama

You can use **local Ollama** (no API key) or **Ollama Cloud** (API key in `.env`). The lab example scripts are in `dsai/03_query_ai/`: `02_ollama.py` (local) and `03_ollama_cloud.py` (cloud).

---

## Option A: Local Ollama (easiest to try)

### 1. Install and run Ollama

- Install: [ollama.com](https://ollama.com) (download and install).
- In a terminal, pull a model and keep the server running:
  ```bash
  ollama run llama3.2
  ```
  Or: `ollama run gemma3:latest`. First run downloads the model. You can close the chat and Ollama will still be running in the background, or leave it open.

- Check it’s running: open [http://localhost:11434](http://localhost:11434) in a browser, or run:
  ```bash
  ollama list
  ```

### 2. Run the lab pipeline and AI report

From `5381-activities/lab03`:

```bash
# 1) Get processed data (if you haven’t already)
python fetch_and_process_census.py

# 2) Generate report using local Ollama
python run_ollama_report.py
```

`run_ollama_report.py` loads the top 15 states from `citizenship_by_state.csv`, builds a prompt, and calls **local Ollama** at `http://localhost:11434/api/generate` (same idea as `02_ollama.py`). The script prints the AI’s short report.

- If you use a different model:
  ```bash
  python run_ollama_report.py --model gemma3:latest
  ```

---

## Option B: Ollama Cloud

- Get an API key from [Ollama](https://ollama.com) and put it in `.env`:
  ```env
  OLLAMA_API_KEY=your_key_here
  ```
- From `lab03`:
  ```bash
  python run_ollama_report.py --cloud
  ```
  This uses the **chat** API at `https://ollama.com/api/chat` with your key (same pattern as `03_ollama_cloud.py`).

---

## Matching the lab tasks

| Lab task | What to do |
|----------|------------|
| **Task 1 – Data pipeline** | Already done: `fetch_and_process_census.py` queries the API, cleans/aggregates, and writes CSV. |
| **Task 2 – Design prompt** | The prompt is in `run_ollama_report.py` (`build_prompt`). It asks for 2–3 paragraphs, trends/patterns, specific numbers, no ICE/enforcement. |
| **Task 3 – Iterate** | Run `run_ollama_report.py` multiple times. Edit `build_prompt()` in the script to change length (“2–3 sentences” vs “2–3 paragraphs”), format (“bullet points” vs “paragraphs”), or focus; run again until the output is what you want. |

---

## Quick sanity check (no CSV)

To confirm Ollama works before using the Census data, run the course example:

```bash
cd dsai/03_query_ai
python 02_ollama.py
```

You should see a short reply from the model. Then use `run_ollama_report.py` in `lab03` to test with your processed data.
