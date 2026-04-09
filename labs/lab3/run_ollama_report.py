"""
Lab 03: Use Ollama to generate a reporting summary from processed Census data.

Prereqs:
  - Processed data: run fetch_and_process_census.py first (creates citizenship_by_state.csv).
  - Local Ollama: install from https://ollama.com, then run: ollama run <model>
  - Python: requests, pandas

Usage:
  python run_ollama_report.py              # default: local Ollama, top-15 summary
  python run_ollama_report.py --cloud     # use Ollama Cloud (needs OLLAMA_API_KEY in .env)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# Load .env from lab03 or app
for p in [Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent / "app" / ".env"]:
    if p.exists():
        load_dotenv(p, override=True)
        break

LAB03 = Path(__file__).resolve().parent
CSV_PATH = LAB03 / "citizenship_by_state.csv"

# Local Ollama: use /api/chat (current Ollama versions); fallback to /api/generate for older
OLLAMA_LOCAL_HOST = "http://localhost:11434"
OLLAMA_LOCAL_CHAT_URL = f"{OLLAMA_LOCAL_HOST}/api/chat"
OLLAMA_LOCAL_GENERATE_URL = f"{OLLAMA_LOCAL_HOST}/api/generate"
OLLAMA_CLOUD_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL_LOCAL = "llama3.2"   # change to gemma3:latest or whatever you have
DEFAULT_MODEL_CLOUD = "gpt-oss:20b-cloud"


def load_data_summary(max_rows: int = 15) -> str:
    """Load CSV and return a short text summary for the prompt (to save tokens)."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Run fetch_and_process_census.py first to create {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    # Top states by non-citizen count
    top = df.nlargest(max_rows, "non_citizen")[
        ["state_name", "total_population", "non_citizen", "pct_non_citizen", "foreign_born", "pct_foreign_born"]
    ]
    lines = [
        "State, Total population, Non-citizen count, % non-citizen, Foreign-born count, % foreign-born",
        *[f"{row['state_name']}, {row['total_population']:.0f}, {row['non_citizen']:.0f}, {row['pct_non_citizen']}, {row['foreign_born']:.0f}, {row['pct_foreign_born']}" for _, row in top.iterrows()],
    ]
    return "\n".join(lines)


def build_prompt(data_summary: str) -> str:
    return f"""You are a data analyst. Below are the top 15 U.S. states by non-citizen population (Census ACS 5-year citizenship data).

Data (state, total population, non-citizen count, % non-citizen, foreign-born count, % foreign-born):
{data_summary}

Instructions:
- In 3–4 short bullet points, summarize trends and patterns: which states have the most non-citizens (by count and by share), U.S. citizens, and how foreign-born population compares. Report largest by shares, rather than count.
- Also report shares of different citizenship statuses for states (largest, smallest, other useful trends and patterns to inform further analyses).
- Use specific numbers from the data.
- Write in clear, neutral language suitable for a brief report. Keep it concise, and intuitive and easy to understand and interpret."""


def query_local(prompt: str, model: str = DEFAULT_MODEL_LOCAL) -> str:
    """Call local Ollama /api/generate (same pattern as 02_ollama.py)."""
    body = {"model": model, "prompt": prompt, "stream": False}
    try:
        r = requests.post(OLLAMA_LOCAL_URL, json=body, timeout=120)
        r.raise_for_status()
        return r.json()["response"]
    except requests.exceptions.ConnectionError:
        raise SystemExit(
            "Could not connect to Ollama. Is it running? Start with: ollama run " + model
        )


def query_cloud(prompt: str, model: str = DEFAULT_MODEL_CLOUD) -> str:
    """Call Ollama Cloud /api/chat (same pattern as 03_ollama_cloud.py)."""
    import os
    key = os.getenv("OLLAMA_API_KEY")
    if not key:
        raise SystemExit("OLLAMA_API_KEY not set in .env for Ollama Cloud.")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(OLLAMA_CLOUD_URL, headers=headers, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]


def main():
    parser = argparse.ArgumentParser(description="Generate AI report from Census data via Ollama")
    parser.add_argument("--cloud", action="store_true", help="Use Ollama Cloud (requires OLLAMA_API_KEY)")
    parser.add_argument("--model", default=None, help="Model name (default: llama3.2 local, gpt-oss:20b-cloud cloud)")
    parser.add_argument("--rows", type=int, default=15, help="Number of top states to include (default 15)")
    args = parser.parse_args()

    print("Loading data summary...")
    data_summary = load_data_summary(max_rows=args.rows)
    prompt = build_prompt(data_summary)

    if args.cloud:
        model = args.model or DEFAULT_MODEL_CLOUD
        print(f"Calling Ollama Cloud ({model})...")
        out = query_cloud(prompt, model=model)
    else:
        model = args.model or DEFAULT_MODEL_LOCAL
        print(f"Calling local Ollama ({model})...")
        out = query_local(prompt, model=model)

    print("\n--- AI report ---\n")
    print(out)
    print("\n--- end ---\n")


if __name__ == "__main__":
    main()
