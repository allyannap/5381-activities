"""Validate one ICE report against source context and emit structured results."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

import requests

from prompts import RUBRIC_SPEC, compute_overall_score


DEFAULT_PROVIDER = "openai"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.2:latest"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score one report against source context using the HW3 rubric."
    )
    parser.add_argument("--report-file", required=True, help="Path to report markdown/text file.")
    parser.add_argument(
        "--source-context-file",
        required=True,
        help="Path to source context file (ICE + Census extracts).",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "ollama"],
        default=DEFAULT_PROVIDER,
        help="Validator AI provider.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Validator model. Defaults to provider-specific value.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Validation temperature. Keep near zero for stable scoring.",
    )
    parser.add_argument("--prompt-id", default="", help="Optional prompt label (A/B/C).")
    parser.add_argument("--run-id", default="", help="Optional run identifier.")
    parser.add_argument(
        "--output-jsonl",
        default="",
        help="Optional path to append JSONL row output.",
    )
    parser.add_argument(
        "--output-csv",
        default="",
        help="Optional path to append CSV row output.",
    )
    parser.add_argument(
        "--openai-api-key",
        default=os.getenv("OPENAI_API_KEY", ""),
        help="OpenAI API key (default: OPENAI_API_KEY env var).",
    )
    parser.add_argument(
        "--ollama-host",
        default=DEFAULT_OLLAMA_HOST,
        help=f"Ollama host URL (default: {DEFAULT_OLLAMA_HOST}).",
    )
    return parser.parse_args()


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_validator_prompt(report_text: str, source_context: str) -> str:
    rubric_lines = []
    for metric_name, spec in RUBRIC_SPEC.items():
        rubric_lines.append(
            f"- {metric_name}: scale={spec['scale']}, min={spec['min']}, "
            f"max={spec['max']}, direction={spec['direction']}, "
            f"anchor={spec['scoring_anchor']}"
        )

    rubric_text = "\n".join(rubric_lines)
    return f"""You are a strict quality validator for county ICE summaries.

Score the report ONLY against the provided source context. Do not reward style over factuality.
If the report makes unsupported legal claims/recommendations, reflect that in legal_claim_risk and legal_claim_safety.
If required evidence is missing, do not infer outside facts.

Rubric metrics:
{rubric_text}

Return ONLY valid JSON with this exact schema:
{{
  "scores": {{
    "numeric_fidelity": 0.0,
    "legal_claim_risk": 0.0,
    "source_attribution_coverage": 0.0,
    "missingness_disclosure": 0,
    "public_utility_rating": 0.0,
    "legal_claim_safety": 0,
    "coverage_required_public_questions": 0.0
  }},
  "rationales": {{
    "numeric_fidelity": "...",
    "legal_claim_risk": "...",
    "source_attribution_coverage": "...",
    "missingness_disclosure": "...",
    "public_utility_rating": "...",
    "legal_claim_safety": "...",
    "coverage_required_public_questions": "..."
  }},
  "overall_rationale": "1-3 sentence holistic explanation"
}}

Source Context:
{source_context}

Report To Validate:
{report_text}
"""


def query_openai(prompt: str, model: str, temperature: float, api_key: str) -> str:
    if not api_key:
        raise ValueError("Missing OpenAI API key. Set OPENAI_API_KEY or pass --openai-api-key.")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict report validator. Return JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def query_ollama(prompt: str, model: str, temperature: float, host: str) -> str:
    base = host.rstrip("/")
    chat_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature},
    }
    response = requests.post(f"{base}/api/chat", json=chat_payload, timeout=90)
    if response.status_code == 404:
        # Older Ollama builds expose /api/generate but not /api/chat.
        generate_payload = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": temperature},
        }
        response = requests.post(f"{base}/api/generate", json=generate_payload, timeout=90)

    response.raise_for_status()
    data = response.json()
    if "message" in data and isinstance(data["message"], dict):
        return str(data["message"].get("content", ""))
    return str(data.get("response", ""))


def extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Validator response did not contain a JSON object.")
    return json.loads(match.group(0))


def coerce_score(metric_name: str, raw_value: Any) -> float:
    spec = RUBRIC_SPEC[metric_name]
    min_val = float(spec["min"])
    max_val = float(spec["max"])
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = min_val

    if metric_name in {"missingness_disclosure", "legal_claim_safety"}:
        value = 1.0 if value >= 0.5 else 0.0

    return max(min_val, min(max_val, value))


def parse_validator_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_scores = payload.get("scores", payload)
    raw_rationales = payload.get("rationales", {})

    scores: Dict[str, float] = {}
    rationales: Dict[str, str] = {}
    for metric_name in RUBRIC_SPEC:
        scores[metric_name] = coerce_score(metric_name, raw_scores.get(metric_name))
        rationale = raw_rationales.get(metric_name, payload.get(f"{metric_name}_rationale", ""))
        rationales[metric_name] = str(rationale).strip()

    overall_rationale = str(payload.get("overall_rationale", "")).strip()
    score_bundle = compute_overall_score(scores)
    return {
        "scores": scores,
        "normalized_scores": score_bundle["normalized_scores"],
        "overall_score": score_bundle["overall_score"],
        "overall_score_scale": score_bundle["overall_score_scale"],
        "gate_pass": score_bundle["gate_pass"],
        "rubric_pass": score_bundle["rubric_pass"],
        "rationales": rationales,
        "overall_rationale": overall_rationale,
        "validator_raw_payload": payload,
    }


def build_output_row(
    args: argparse.Namespace,
    report_text: str,
    source_context: str,
    parsed: Dict[str, Any],
    validator_model: str,
) -> Dict[str, Any]:
    timestamp_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    row: Dict[str, Any] = {
        "timestamp_utc": timestamp_utc,
        "prompt_id": args.prompt_id,
        "run_id": args.run_id,
        "provider": args.provider,
        "validator_model": validator_model,
        "validator_temperature": args.temperature,
        "report_file": args.report_file,
        "source_context_file": args.source_context_file,
        "report_sha256": sha256_text(report_text),
        "source_context_sha256": sha256_text(source_context),
        "overall_score": parsed["overall_score"],
        "overall_score_scale": parsed["overall_score_scale"],
        "gate_pass": parsed["gate_pass"],
        "rubric_pass": parsed["rubric_pass"],
        "overall_rationale": parsed["overall_rationale"],
    }

    for metric_name, value in parsed["scores"].items():
        row[metric_name] = value
    for metric_name, value in parsed["normalized_scores"].items():
        row[f"{metric_name}_normalized"] = value
    for metric_name, text in parsed["rationales"].items():
        row[f"{metric_name}_rationale"] = text

    row["validator_raw_payload_json"] = json.dumps(parsed["validator_raw_payload"], ensure_ascii=True)
    return row


def append_jsonl(path: str, row: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def append_csv(path: str, row: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_header = not target.exists() or target.stat().st_size == 0
    with target.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    args = parse_args()
    report_text = read_text(args.report_file)
    source_context = read_text(args.source_context_file)
    prompt = build_validator_prompt(report_text, source_context)

    validator_model = args.model or (
        DEFAULT_OPENAI_MODEL if args.provider == "openai" else DEFAULT_OLLAMA_MODEL
    )
    if args.provider == "openai":
        raw_response = query_openai(prompt, validator_model, args.temperature, args.openai_api_key)
    else:
        raw_response = query_ollama(prompt, validator_model, args.temperature, args.ollama_host)

    payload = extract_json_object(raw_response)
    parsed = parse_validator_payload(payload)
    row = build_output_row(args, report_text, source_context, parsed, validator_model)

    print(json.dumps(row, indent=2, ensure_ascii=True))

    if args.output_jsonl:
        append_jsonl(args.output_jsonl, row)
    if args.output_csv:
        append_csv(args.output_csv, row)


if __name__ == "__main__":
    main()
