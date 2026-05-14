"""Run the HW3 prompt experiment and save master validation results."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, List

import requests

from prompts import (
    EXPERIMENT_SAMPLE_SIZE_PER_PROMPT,
    GENERATOR_MAX_TOKENS,
    GENERATOR_MODEL,
    GENERATOR_TEMPERATURE,
    GENERATOR_TOP_P,
    PROMPT_IDS,
    build_report_prompt,
)
from validate_reports import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OPENAI_MODEL,
    append_csv,
    append_jsonl,
    build_output_row,
    build_validator_prompt,
    extract_json_object,
    parse_validator_payload,
    query_ollama,
    query_openai,
)


DEFAULT_REPORTS_DIR = "outputs/generated_reports"
DEFAULT_RESULTS_CSV = "outputs/experiment_results.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate+validate repeated ICE reports for Prompt A/B/C and save a master CSV."
        )
    )
    parser.add_argument(
        "--source-context-file",
        required=True,
        help="Path to source context text file (ICE + Census extracts).",
    )
    parser.add_argument(
        "--prompt-ids",
        default=",".join(PROMPT_IDS),
        help="Comma-separated prompt IDs to run (default: A,B,C).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=EXPERIMENT_SAMPLE_SIZE_PER_PROMPT,
        help=f"Runs per prompt (default: {EXPERIMENT_SAMPLE_SIZE_PER_PROMPT}).",
    )

    # Report generation config (fixed across prompts during experiment).
    parser.add_argument(
        "--generator-provider",
        choices=["openai", "ollama"],
        default="openai",
        help="Report generator provider.",
    )
    parser.add_argument(
        "--generator-model",
        default=GENERATOR_MODEL,
        help=f"Report generator model (default: {GENERATOR_MODEL}).",
    )
    parser.add_argument(
        "--generator-temperature",
        type=float,
        default=GENERATOR_TEMPERATURE,
        help=f"Report generation temperature (default: {GENERATOR_TEMPERATURE}).",
    )
    parser.add_argument(
        "--generator-top-p",
        type=float,
        default=GENERATOR_TOP_P,
        help=f"Report generation top_p (default: {GENERATOR_TOP_P}).",
    )
    parser.add_argument(
        "--generator-max-tokens",
        type=int,
        default=GENERATOR_MAX_TOKENS,
        help=f"Report generation max tokens (default: {GENERATOR_MAX_TOKENS}).",
    )

    # Validator config.
    parser.add_argument(
        "--validator-provider",
        choices=["openai", "ollama"],
        default="openai",
        help="Validator provider.",
    )
    parser.add_argument(
        "--validator-model",
        default="",
        help="Validator model (defaults to provider-specific model if omitted).",
    )
    parser.add_argument(
        "--validator-temperature",
        type=float,
        default=0.0,
        help="Validation temperature. Keep near zero for stable scoring.",
    )

    # Shared provider auth/network config.
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

    # Output controls.
    parser.add_argument(
        "--reports-dir",
        default=DEFAULT_REPORTS_DIR,
        help=f"Directory for generated report files (default: {DEFAULT_REPORTS_DIR}).",
    )
    parser.add_argument(
        "--output-csv",
        default=DEFAULT_RESULTS_CSV,
        help=f"Master results CSV path (default: {DEFAULT_RESULTS_CSV}).",
    )
    parser.add_argument(
        "--output-jsonl",
        default="",
        help="Optional JSONL output path for row-level reproducibility.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing outputs instead of starting a fresh file.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional delay between runs to reduce provider rate pressure.",
    )
    parser.add_argument(
        "--max-total-seconds",
        type=float,
        default=0.0,
        help=(
            "Optional wall-clock time budget in seconds for the whole run. "
            "When exceeded, the script stops early and keeps completed rows."
        ),
    )
    return parser.parse_args()


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def parse_prompt_ids(raw_prompt_ids: str) -> List[str]:
    prompt_ids = [p.strip().upper() for p in raw_prompt_ids.split(",") if p.strip()]
    invalid = [p for p in prompt_ids if p not in PROMPT_IDS]
    if invalid:
        allowed = ", ".join(PROMPT_IDS)
        raise ValueError(f"Invalid prompt IDs {invalid}. Allowed values: {allowed}.")
    if not prompt_ids:
        raise ValueError("No prompt IDs provided after parsing --prompt-ids.")
    return prompt_ids


def maybe_reset_output(path: str, append: bool) -> None:
    if append:
        return
    output = Path(path)
    if output.exists():
        output.unlink()


def query_openai_report(
    prompt: str,
    model: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    api_key: str,
) -> str:
    if not api_key:
        raise ValueError("Missing OpenAI API key. Set OPENAI_API_KEY or pass --openai-api-key.")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write concise, factual county reports. "
                        "Use only provided context and follow user instructions exactly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def query_ollama_report(
    prompt: str,
    model: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    host: str,
) -> str:
    base = host.rstrip("/")
    chat_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": max_tokens,
        },
    }
    response = requests.post(f"{base}/api/chat", json=chat_payload, timeout=90)
    if response.status_code == 404:
        # Older Ollama builds expose /api/generate but not /api/chat.
        generate_payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            },
        }
        response = requests.post(f"{base}/api/generate", json=generate_payload, timeout=90)

    response.raise_for_status()
    data = response.json()
    if "message" in data and isinstance(data["message"], dict):
        return str(data["message"].get("content", "")).strip()
    return str(data.get("response", "")).strip()


def generate_report_text(
    provider: str,
    model: str,
    prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    openai_api_key: str,
    ollama_host: str,
) -> str:
    if provider == "openai":
        return query_openai_report(
            prompt=prompt,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            api_key=openai_api_key,
        )
    return query_ollama_report(
        prompt=prompt,
        model=model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        host=ollama_host,
    )


def validate_report_text(
    provider: str,
    model: str,
    temperature: float,
    report_text: str,
    source_context: str,
    openai_api_key: str,
    ollama_host: str,
) -> dict:
    validator_prompt = build_validator_prompt(report_text, source_context)
    if provider == "openai":
        raw_response = query_openai(validator_prompt, model, temperature, openai_api_key)
    else:
        raw_response = query_ollama(validator_prompt, model, temperature, ollama_host)
    payload = extract_json_object(raw_response)
    return parse_validator_payload(payload)


def save_report_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def iter_runs(prompt_ids: Iterable[str], sample_size: int) -> Iterable[tuple[str, int]]:
    for prompt_id in prompt_ids:
        for run_idx in range(1, sample_size + 1):
            yield prompt_id, run_idx


def main() -> None:
    args = parse_args()
    prompt_ids = parse_prompt_ids(args.prompt_ids)
    if args.sample_size < 1:
        raise ValueError("--sample-size must be >= 1.")

    source_context = read_text(args.source_context_file)
    reports_dir = Path(args.reports_dir)
    output_csv = args.output_csv
    output_jsonl = args.output_jsonl

    validator_model = args.validator_model or (
        DEFAULT_OPENAI_MODEL if args.validator_provider == "openai" else DEFAULT_OLLAMA_MODEL
    )

    maybe_reset_output(output_csv, args.append)
    if output_jsonl:
        maybe_reset_output(output_jsonl, args.append)

    total_runs = len(prompt_ids) * args.sample_size
    start_ts = time.time()
    print(
        f"Starting experiment: prompts={prompt_ids}, sample_size={args.sample_size}, total_runs={total_runs}"
    )
    print(
        "Generation controls: "
        f"provider={args.generator_provider}, model={args.generator_model}, "
        f"temperature={args.generator_temperature}, top_p={args.generator_top_p}, "
        f"max_tokens={args.generator_max_tokens}"
    )
    print(
        "Validator controls: "
        f"provider={args.validator_provider}, model={validator_model}, "
        f"temperature={args.validator_temperature}"
    )

    for sequence_idx, (prompt_id, run_idx) in enumerate(
        iter_runs(prompt_ids, args.sample_size), start=1
    ):
        elapsed = time.time() - start_ts
        if args.max_total_seconds > 0 and elapsed >= args.max_total_seconds:
            print(
                "Time budget reached before next run. "
                f"elapsed_seconds={elapsed:.1f}, max_total_seconds={args.max_total_seconds:.1f}"
            )
            break

        run_id = f"{prompt_id}-{run_idx:03d}"
        report_prompt = build_report_prompt(prompt_id=prompt_id, source_context=source_context)

        report_text = generate_report_text(
            provider=args.generator_provider,
            model=args.generator_model,
            prompt=report_prompt,
            temperature=args.generator_temperature,
            top_p=args.generator_top_p,
            max_tokens=args.generator_max_tokens,
            openai_api_key=args.openai_api_key,
            ollama_host=args.ollama_host,
        )

        report_path = reports_dir / f"prompt_{prompt_id}" / f"run_{run_idx:03d}.md"
        save_report_text(report_path, report_text)

        parsed_validation = validate_report_text(
            provider=args.validator_provider,
            model=validator_model,
            temperature=args.validator_temperature,
            report_text=report_text,
            source_context=source_context,
            openai_api_key=args.openai_api_key,
            ollama_host=args.ollama_host,
        )

        row_args = SimpleNamespace(
            prompt_id=prompt_id,
            run_id=run_id,
            provider=args.validator_provider,
            temperature=args.validator_temperature,
            report_file=str(report_path),
            source_context_file=args.source_context_file,
        )
        row = build_output_row(
            args=row_args,
            report_text=report_text,
            source_context=source_context,
            parsed=parsed_validation,
            validator_model=validator_model,
        )
        row["generator_provider"] = args.generator_provider
        row["generator_model"] = args.generator_model
        row["generator_temperature"] = args.generator_temperature
        row["generator_top_p"] = args.generator_top_p
        row["generator_max_tokens"] = args.generator_max_tokens
        row["report_generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        row["run_sequence"] = sequence_idx

        append_csv(output_csv, row)
        if output_jsonl:
            append_jsonl(output_jsonl, row)

        print(
            f"[{sequence_idx}/{total_runs}] prompt={prompt_id} run={run_idx:03d} "
            f"overall_score={row['overall_score']} rubric_pass={row['rubric_pass']}"
        )
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    print(f"Experiment complete. Master CSV written to: {output_csv}")
    if output_jsonl:
        print(f"JSONL rows written to: {output_jsonl}")


if __name__ == "__main__":
    main()
