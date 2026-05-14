"""Analyze HW3 experiment results with one-way ANOVA on overall_score."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from scipy.stats import f_oneway


DEFAULT_RESULTS_CSV = "outputs/experiment_results.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute descriptive stats + one-way ANOVA for prompt experiment results."
    )
    parser.add_argument(
        "--results-csv",
        default=DEFAULT_RESULTS_CSV,
        help=f"Path to experiment results CSV (default: {DEFAULT_RESULTS_CSV}).",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Significance threshold (default: 0.05).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.results_csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"Results CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required_cols = {"prompt_id", "overall_score"}
    missing_cols = sorted(required_cols - set(df.columns))
    if missing_cols:
        raise ValueError(f"Missing required columns in results CSV: {missing_cols}")

    df = df.dropna(subset=["prompt_id", "overall_score"]).copy()
    df["prompt_id"] = df["prompt_id"].astype(str).str.strip().str.upper()
    df["overall_score"] = pd.to_numeric(df["overall_score"], errors="coerce")
    df = df.dropna(subset=["overall_score"])

    grouped = {
        prompt_id: group["overall_score"].to_numpy()
        for prompt_id, group in df.groupby("prompt_id", sort=True)
    }
    if len(grouped) < 2:
        raise ValueError("Need at least 2 prompt groups to run ANOVA.")

    print("Descriptive statistics by prompt:")
    print(
        df.groupby("prompt_id")["overall_score"]
        .agg(["count", "mean", "std", "min", "max"])
        .round(3)
    )
    print()

    samples = [grouped[prompt_id] for prompt_id in sorted(grouped)]
    f_stat, p_value = f_oneway(*samples)

    print("One-way ANOVA on overall_score")
    print("H0: Mean overall_score is equal across prompt groups.")
    print("H1: At least one prompt mean differs.")
    print(f"F-statistic: {f_stat:.6f}")
    print(f"p-value: {p_value:.6f}")
    print(f"alpha: {args.alpha:.3f}")
    significant = p_value < args.alpha
    print(f"Decision: {'Reject H0' if significant else 'Fail to reject H0'}")
    print()

    print("Post-hoc tests intentionally omitted. This analysis reports ANOVA only.")


if __name__ == "__main__":
    main()
