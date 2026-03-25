# Lab 5 — Custom RAG query (SQLite)

This folder implements the **Create Your Own RAG AI Query** lab (see the course materials under `dsai/07_rag/LAB_custom_rag_query.md`): a SQLite-backed retrieval step plus an Ollama chat call that summarizes retrieved rows.

## Contents

| File | Purpose |
|------|---------|
| `create_db.py` | Creates `ice_news.db` and tables `articles`, `state_metrics`. |
| `seed_data.py` | Inserts sample articles and state metrics (run after `create_db.py`). |
| `rag_query.py` | Search function, retrieval preview tables, and multi-query RAG workflow. |

## Prerequisites

- Python 3 with `pandas` and `requests` (`pip install pandas requests`).
- [Ollama](https://ollama.com/) running locally; pull the model named in `rag_query.py` (e.g. `ollama pull smollm2:1.7b`).

## Setup

From this directory:

```bash
python create_db.py
python seed_data.py
```

## Run the RAG script

```bash
python rag_query.py
```

Ensure `ice_news.db` exists in the same folder as `rag_query.py`. The script prints a quick search test, then runs several RAG queries (each with a retrieval preview table and a generated summary).

