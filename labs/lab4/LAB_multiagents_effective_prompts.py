# LAB_multiagents_effective_prompts.py
# Design Effective Prompts for Multi-Agent Systems
# Lab: LAB_prompt_design.md (dsai/06_agents/)
#
# Use this template to:
# - Define 2–3 agents with clear roles and system prompts
# - Chain agents so each output becomes the next agent's input
# - Test and iterate on prompt design
#
# Reference: 02_using_ollama.py, 03_agents.py, 04_rules.py, 04_rules.yaml, functions.py

# =============================================================================
# 0. SETUP
# =============================================================================

import argparse
import csv
import io
import re
import sys
import time
from pathlib import Path
import requests

# Ensure we use the course agent helpers from dsai/06_agents, not pip "functions"
THIS_FILE = Path(__file__).resolve()
DSAI_AGENTS = None
for parent in THIS_FILE.parents:
    candidate = parent / "dsai" / "06_agents"
    if candidate.exists():
        DSAI_AGENTS = candidate
        break
if DSAI_AGENTS is None:
    raise FileNotFoundError(
        f"Could not locate dsai/06_agents from {THIS_FILE}. "
        "Expected a folder named dsai/06_agents in an ancestor directory."
    )
sys.path.insert(0, str(DSAI_AGENTS))

from functions import agent_run
# Optional for data pipelines (e.g. fetch → analyze → report):
# from functions import agent_run, get_shortages, df_as_text

# Optional: use rules from dsai/06_agents/04_rules.yaml (or your own YAML)
# import yaml
# with open(DSAI_AGENTS / "04_rules.yaml", "r") as f:
#     rules = yaml.safe_load(f)
# def format_rules_for_prompt(ruleset):
#     return f"{ruleset['name']}\n{ruleset['description']}\n\n{ruleset['guidance']}"

# =============================================================================
# 1. CONFIGURATION
# =============================================================================

MODEL = "smollm2:1.7b"  # Better quality for strict prompt format
FAST_MODEL = "smollm2:135m"  # Faster local model for strict timeout runs
DEFAULT_AGENT_TIMEOUT = 90
FAST_AGENT_TIMEOUT = 20
DEFAULT_AGENT1_SOURCE_CSV = "ice_structured.csv"
DEFAULT_NUM_PREDICT = 220
FAST_NUM_PREDICT = 60
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MAX_FORMAT_ATTEMPTS = 2


def install_request_timeout(timeout_seconds: int, num_predict: int | None = None) -> None:
    """
    Set defaults for requests.post calls used by agent_run:
    - hard timeout
    - Ollama chat generation caps for faster completion
    """
    original_post = requests.post

    def post_with_timeout(*args, **kwargs):
        kwargs.setdefault("timeout", timeout_seconds)
        url = args[0] if args else kwargs.get("url", "")
        if isinstance(url, str) and url.endswith("/api/chat"):
            payload = kwargs.get("json")
            if isinstance(payload, dict):
                payload.setdefault("keep_alive", "20m")
                options = payload.get("options")
                if not isinstance(options, dict):
                    options = {}
                if num_predict is not None:
                    options.setdefault("num_predict", int(num_predict))
                options.setdefault("temperature", 0.2)
                payload["options"] = options
                kwargs["json"] = payload
        return original_post(*args, **kwargs)

    requests.post = post_with_timeout


def warmup_model(model: str, timeout_seconds: int) -> None:
    """Preload the Ollama model to reduce first-call latency."""
    try:
        requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with: OK"}],
                "stream": False,
                "keep_alive": "20m",
                "options": {"num_predict": 5, "temperature": 0.0},
            },
            timeout=min(timeout_seconds, 10),
        )
    except requests.exceptions.RequestException:
        # Warmup is best-effort; workflow continues without failing.
        pass


def read_csv_text(path: Path, max_rows: int) -> str:
    """Return a compact ranked CSV view for Agent 1 input."""
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"CSV is empty: {path}")

    def _safe_int(text: str) -> int:
        try:
            return int(float(str(text).strip()))
        except Exception:
            return 0

    key_cols = [
        "report_date",
        "state",
        "county_or_city",
        "facility_name",
        "demographic_group",
        "citizenship_group",
        "detention_count",
        "percent_change",
    ]
    normalized = [{col: r.get(col, "NA") for col in key_cols} for r in rows]
    ranked = sorted(normalized, key=lambda r: _safe_int(r.get("detention_count", "0")), reverse=True)
    limited = ranked[:max_rows]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=key_cols, lineterminator="\n")
    writer.writeheader()
    writer.writerows(limited)
    return buffer.getvalue().strip()


def _has_required_parts(text: str, part_numbers: list[int]) -> bool:
    """Return True when all required Part N headers are present."""
    lowered = (text or "").lower()
    for n in part_numbers:
        # Accept both "Part N:" and "Part N"
        if not re.search(rf"\bpart\s*{n}\b", lowered):
            return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 2-agent ICE workflow from local structured data."
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=5,
        help="Maximum CSV rows sent to Agent 1 (default: 5).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use a faster local model for shorter runs.",
    )
    parser.add_argument(
        "--agent-timeout",
        type=int,
        default=DEFAULT_AGENT_TIMEOUT,
        help=f"Per-agent timeout in seconds (default: {DEFAULT_AGENT_TIMEOUT}).",
    )
    parser.add_argument(
        "--agent1-source-csv",
        default=str(Path(__file__).resolve().parent / DEFAULT_AGENT1_SOURCE_CSV),
        help="Base CSV used by Agent 1 reporter (default: ice_structured.csv).",
    )
    return parser.parse_args()

# =============================================================================
# 2. TASK 1: DESIGN YOUR MULTI-AGENT SYSTEM
# =============================================================================
#
# Goal:
# Build a 2-agent workflow for an ICE activity dashboard that helps users
# understand where detention activity is concentrated, where recent ICE-related
# trends are increasing, and which areas may need closer attention.
#
# Workflow Overview:
# The system takes in ICE-related data from public or regularly updated sources,
# processes it into a clean structured dataset, creates dashboard-ready summaries
# and visualizations, and then produces a clear written interpretation for users.
#
# Agent 1 Data Reporter
# Primary function:
# - Read the cleaned ICE-related data
# - Write a plain-language summary of the most important findings 
 #   - such as:
 #  demographic and citizenship breakdowns, 
 # hotspots of ICE activity nationwide by location and date, 
 # recent time trends, 
 # map-ready regional summaries, 
 # and showing top 5 locations by ICE activity, 
 # and other important information.
# - Highlight where activity is concentrated, whether trends are rising,
#   and which groups or regions appear most affected if supported by the data
#
# Input:
# - Cleaned data table and key metrics from Agent 1
#
# Output:
# - A short report in accessible language
# - 3–5 key takeaways for dashboard users
# - A concise summary of hotspots, trends, and disparities

#
## Agent 2: Risk Analyst & Community Advisor
# Primary function:
# - Read the findings from Agent 1
# - Produce a general preparedness and community-awareness brief
# - Suggest lawful, non-speculative actions families and communities can take
# - Ground advice in trusted rights/preparedness resources and broad historical lessons
#   about preparedness, documentation, legal support, and collective response
#
# Input:
# - Agent 1 summary of findings
#
# Output:
# - A short community preparedness brief
# - A "What your community can can do now" section (specific for that state or county)
# - A "Know your rights and preparedness" section, depending on the citizenship of the individual or demographic community in question.
# - A short note on historical lessons such as documentation, coalition-building,
#   mutual aid, and access to trusted legal support


#   Flow: Agent 1 → Agent 2
# =============================================================================

# =============================================================================
# 3. TASK 2: SYSTEM PROMPTS FOR EACH AGENT
# =============================================================================
#
# Define the agent's role clearly, output format, and any constraints.
# Ref: 02_using_ollama.py (system prompts), 04_rules.yaml (structured rules)
# =============================================================================

# --- Agent 1: Reporter role ---
ROLE_1 = """
You are a data reporter for an ICE activity dashboard.

You receive a structured table selected from local ice_structured.csv data.
Your job is to produce a short, evidence-based summary for community users.

You must:
- identify the 2-3 most important findings only
- use exact places, numbers, and dates from the input
- describe change over time only when exact comparison dates are available
- identify the most affected locations, demographic groups, or citizenship groups only if supported by the data
- state clearly when the data is limited

Your output must be exactly three parts:

Part 1: Summary
- 3 sentences maximum

Part 2: Key Takeaways
- exactly 3 bullet points
- each bullet must include at least one number, one location or group, and one date or date range when available

Part 3: Structured Findings
- Hotspots: 1-2 sentences
- Trends Over Time: 1-2 sentences
- Groups Most Affected: 1-2 sentences

Constraints:
- do not use filler, slogans, or generic phrases
- do not say "recent", "currently", "some communities", "certain groups", or similar vague wording without a specific number, place, or date
- do not speculate about motives, causes, or future actions
- keep the full response under 300 words
"""

# --- Agent 2: Analyst/advisor role ---
ROLE_2 = """
You are a risk analyst and community preparedness advisor for an ICE activity dashboard.

You receive a short findings summary from Agent 1.
Your job is to translate those findings into concise, lawful, evidence-based community guidance.

You must:
- connect each recommendation to a finding from Agent 1
- provide only general preparedness guidance, not individualized legal advice
- prioritize practical steps such as family preparedness planning, document organization, emergency contacts, rights education, and trusted nonprofit legal resources
- mention uncertainty when the underlying data is limited
- keep the tone calm, direct, and useful

Preferred output structure is four parts:

Part 1: Community Preparedness Summary
- 2 sentences maximum

Part 2: What Your Community Can Do Now
- 3-4 bullet points
- each bullet must be practical and specific

Part 3: Know Your Rights and Preparedness
- 2-3 bullet points
- general only, not individualized legal advice

Part 4: Historical Lessons
- 2 sentences maximum
- focus on broad lessons such as documentation, mutual aid, coalition-building, and rights education

Constraints:
- do not use vague motivational language
- do not make unsupported claims
- do not instruct users to evade law enforcement
- do not provide individualized legal advice
- keep the full response under 350 words
"""

# =============================================================================
# 4. TASK 3: RUN WORKFLOW AND ITERATE
# =============================================================================
#
# Run the chain. Check each agent's output; refine ROLE_* and TASK_* above
# if outputs are vague or format is wrong. Document what worked and what you changed.
# =============================================================================


if __name__ == "__main__":
    args = parse_args()
    agent1_source_csv = Path(args.agent1_source_csv).resolve()
    max_rows = max(3, args.max_rows)

    # Keep a lower bound but allow larger timeouts for slower local setups.
    agent_timeout = max(5, args.agent_timeout)
    if args.fast:
        agent_timeout = min(agent_timeout, FAST_AGENT_TIMEOUT)
        max_rows = min(max_rows, 6)
        print(f"Fast preset enabled: agent_timeout={agent_timeout}s")
    num_predict = FAST_NUM_PREDICT if args.fast else DEFAULT_NUM_PREDICT
    model_for_run = FAST_MODEL if args.fast else MODEL
    install_request_timeout(agent_timeout, num_predict=num_predict)
    warmup_model(model_for_run, agent_timeout)
    print(f"Agent timeout enabled: {agent_timeout}s per LLM call")
    print(f"Model selected: {model_for_run}")
    if not agent1_source_csv.exists():
        raise FileNotFoundError(
            f"Missing CSV input: {agent1_source_csv}. "
            "Please keep your synthetic ice_structured.csv in the lab4 folder."
        )
    print(f"Using CSV input: {agent1_source_csv}")
    selected_csv = read_csv_text(agent1_source_csv, max_rows=max_rows)

    print("Agent 1 running...")

    TASK_1 = f"""
You are Agent 1, the reporter.
Use only this table from local synthetic CSV source ({agent1_source_csv}):

{selected_csv}

Follow ROLE_1 exactly.
Do not copy raw CSV rows verbatim.
Return ONLY in this exact template:
Part 1: Summary
<text>

Part 2: Key Takeaways
- <bullet 1>
- <bullet 2>
- <bullet 3>

Part 3: Structured Findings
- Hotspots: <text>
- Trends Over Time: <text>
- Groups Most Affected: <text>
"""

    t1 = time.monotonic()
    role_1 = ROLE_1
    result1 = ""
    for attempt in range(MAX_FORMAT_ATTEMPTS):
        try:
            if attempt == 0:
                result1 = agent_run(role=role_1, task=TASK_1, model=model_for_run, output="text")
            else:
                task_1_rewrite = f"""
Rewrite the following Agent 1 draft so it strictly follows ROLE_1.
You must include Part 1, Part 2, and Part 3.
Do not copy CSV rows verbatim.
Return ONLY in this exact template:
Part 1: Summary
<text>

Part 2: Key Takeaways
- <bullet 1>
- <bullet 2>
- <bullet 3>

Part 3: Structured Findings
- Hotspots: <text>
- Trends Over Time: <text>
- Groups Most Affected: <text>

Draft:
{result1}
"""
                result1 = agent_run(role=role_1, task=task_1_rewrite, model=model_for_run, output="text")
        except requests.exceptions.RequestException as exc:
            print(f"Agent 1 timeout/error after {agent_timeout}s ({type(exc).__name__}).")
            print("Try: --fast --max-rows 5 --agent-timeout 60")
            raise

        if _has_required_parts(result1, [1, 2, 3]):
            break
    else:
        raise RuntimeError("Agent 1 output missing required sections: Part 1, Part 2, Part 3.")
    t1_elapsed = time.monotonic() - t1

    print("\n===== AGENT 1 OUTPUT =====\n")
    print(result1)
    print(f"Agent 1 elapsed: {t1_elapsed:.1f}s")
    print("\n==========================\n")

    # Agent 2 = analyst/advisor (LLM), consuming Agent 1 report.
    TASK_2 = f"""
Here is the findings summary from Agent 1 (reporter):

{result1}

Using only these findings, create a concise community preparedness brief.

Instructions:
- make recommendations only if they are appropriate to the findings
- if Agent 1 gives limited geographic or demographic detail, keep the advice general
- connect guidance to the reported hotspots, affected groups, or trend findings when possible
- avoid filler and avoid repeating the findings summary word-for-word
- if the data is limited, explicitly say so

Follow ROLE_2 exactly.
Do not repeat Agent 1 text verbatim.
Write fresh recommendations derived from the findings.
Return ONLY in this exact template:
Part 1: Community Preparedness Summary
Part 2: What Your Community Can Do Now
Part 3: Know Your Rights and Preparedness
Part 4: Historical Lessons
If needed, you may omit one section, but include at least Part 1 and Part 2.
"""

    print("Agent 2 running...")
    t2 = time.monotonic()
    role_2 = ROLE_2
    result2 = ""
    for attempt in range(MAX_FORMAT_ATTEMPTS):
        try:
            if attempt == 0:
                result2 = agent_run(role=role_2, task=TASK_2, model=model_for_run, output="text")
            else:
                task_2_rewrite = f"""
Rewrite the following Agent 2 draft so it strictly follows ROLE_2.
You must include Part 1, Part 2, Part 3, and Part 4.
Do not repeat Agent 1 text verbatim.
Write fresh recommendations derived from the findings.
Return ONLY in this exact template:
Part 1: Community Preparedness Summary
Part 2: What Your Community Can Do Now
Part 3: Know Your Rights and Preparedness
Part 4: Historical Lessons
If needed, you may omit one section, but include at least Part 1 and Part 2.

Draft:
{result2}
"""
                result2 = agent_run(role=role_2, task=task_2_rewrite, model=model_for_run, output="text")
        except requests.exceptions.RequestException as exc:
            print(f"Agent 2 timeout/error after {agent_timeout}s ({type(exc).__name__}).")
            print("Try: --fast --max-rows 5 --agent-timeout 60")
            raise

        if _has_required_parts(result2, [1, 2]):
            break
    else:
        print(
            "Warning: Agent 2 output format still partial after retries. Continuing with best available output."
        )
    t2_elapsed = time.monotonic() - t2

    print("\n===== AGENT 2 OUTPUT =====\n")
    print(result2)
    print(f"\nAgent 2 elapsed: {t2_elapsed:.1f}s")
    print("\n==========================\n")

    print("=== WORKFLOW COMPLETE ===")
    print("Refine ROLE_1/ROLE_2 and TASK_1/TASK_2 as needed, then re-run to iterate.")