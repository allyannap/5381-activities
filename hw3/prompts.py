"""Prompt and rubric constants for HW3 ICE report validation."""

from __future__ import annotations

from typing import Dict, Any


PROMPT_IDS = ("A", "B", "C")

# Controlled generation constants: these should stay fixed across A/B/C runs.
GENERATOR_MODEL = "gpt-4o-mini"
GENERATOR_TEMPERATURE = 0.2
GENERATOR_TOP_P = 1.0
GENERATOR_MAX_TOKENS = 900
EXPERIMENT_SAMPLE_SIZE_PER_PROMPT = 30

FIXED_REPORT_TASK = (
    "Write a county-level ICE public-information report using only the provided source context."
)

FIXED_SOURCE_SCOPE = (
    "Use only the ICE + Census source context included below. "
    "Do not invent, infer, or import facts from outside this context."
)

FIXED_OUTPUT_FORMAT = (
    "Output plain Markdown with short section headers and concise paragraphs. "
    "Do not output JSON or code blocks."
)

COMMON_REPORT_REQUIREMENTS = [
    "Stay factual and data-bound.",
    "If a metric is unavailable, explicitly mark it as missing/unknown.",
    "Avoid legal advice, legal conclusions, or policy prescriptions.",
    "Keep tone neutral and public-facing.",
]

PROMPT_TEMPLATE_A = """\
Prompt A (Baseline Summary):
Task: {task}

Rules:
- {source_scope}
- {output_format}
- {requirement_1}
- {requirement_2}
- {requirement_3}
- {requirement_4}

Write a straightforward narrative summary of the county ICE context from the source data.
Cover key totals, rates, and notable caveats when present.

Source Context:
{source_context}
"""

PROMPT_TEMPLATE_B = """\
Prompt B (Reporter-Style Constraints):
Task: {task}

Rules:
- {source_scope}
- {output_format}
- {requirement_1}
- {requirement_2}
- {requirement_3}
- {requirement_4}

Reporter constraints:
- Include counts and rates (when both are available).
- Distinguish observed values from interpretation.
- Include at least one caveat about uncertainty or data limits.
- Keep each section compact and avoid policy recommendations.

Source Context:
{source_context}
"""

PROMPT_TEMPLATE_C = """\
Prompt C (Strict Validator-Aware Framing):
Task: {task}

Rules:
- {source_scope}
- {output_format}
- {requirement_1}
- {requirement_2}
- {requirement_3}
- {requirement_4}

Strict constraints:
- For each major claim, provide an inline source reference label in parentheses
  (example labels: ICE Table 1, Census Table A).
- Do not make legal conclusions unless the legal basis is explicitly present in source context.
- Disclose missingness, uncertainty, and denominator limitations.
- Ensure required public questions are covered: counts, rates, disparities, and caveats.

Source Context:
{source_context}
"""

PROMPT_TEMPLATES: Dict[str, str] = {
    "A": PROMPT_TEMPLATE_A,
    "B": PROMPT_TEMPLATE_B,
    "C": PROMPT_TEMPLATE_C,
}


def get_controlled_experiment_constants() -> Dict[str, Any]:
    """Return non-prompt settings that must stay fixed during A/B/C comparisons."""
    return {
        "prompt_ids": PROMPT_IDS,
        "model": GENERATOR_MODEL,
        "temperature": GENERATOR_TEMPERATURE,
        "top_p": GENERATOR_TOP_P,
        "max_tokens": GENERATOR_MAX_TOKENS,
        "sample_size_per_prompt": EXPERIMENT_SAMPLE_SIZE_PER_PROMPT,
        "task": FIXED_REPORT_TASK,
        "source_scope": FIXED_SOURCE_SCOPE,
        "output_format": FIXED_OUTPUT_FORMAT,
        "common_requirements": COMMON_REPORT_REQUIREMENTS,
    }


def build_report_prompt(prompt_id: str, source_context: str) -> str:
    """Build one report-generation prompt (A/B/C) with fixed shared controls."""
    normalized_id = str(prompt_id).strip().upper()
    if normalized_id not in PROMPT_TEMPLATES:
        allowed = ", ".join(PROMPT_IDS)
        raise ValueError(f"Unknown prompt_id '{prompt_id}'. Expected one of: {allowed}.")

    template = PROMPT_TEMPLATES[normalized_id]
    return template.format(
        task=FIXED_REPORT_TASK,
        source_scope=FIXED_SOURCE_SCOPE,
        output_format=FIXED_OUTPUT_FORMAT,
        requirement_1=COMMON_REPORT_REQUIREMENTS[0],
        requirement_2=COMMON_REPORT_REQUIREMENTS[1],
        requirement_3=COMMON_REPORT_REQUIREMENTS[2],
        requirement_4=COMMON_REPORT_REQUIREMENTS[3],
        source_context=(source_context or "").strip(),
    )


RUBRIC_SPEC: Dict[str, Dict[str, Any]] = {
    "numeric_fidelity": {
        "display_name": "Numeric Fidelity",
        "scale": "0-1",
        "min": 0.0,
        "max": 1.0,
        "direction": "higher_is_better",
        "benchmark": ">= 0.90",
        "weight": 0.25,
        "description": (
            "Share of numeric claims (counts/rates/trends) that are correct given source data."
        ),
        "scoring_anchor": "1.0 means no detected numeric error; 0.0 means severe numeric mismatch.",
    },
    "legal_claim_risk": {
        "display_name": "Legal Claim Risk",
        "scale": "0-2",
        "min": 0.0,
        "max": 2.0,
        "direction": "lower_is_better",
        "benchmark": "<= 0.50",
        "weight": 0.15,
        "description": (
            "Risk level from unsupported legal conclusions, legal advice, or certainty beyond evidence."
        ),
        "scoring_anchor": "0 = no risk, 1 = moderate risk language, 2 = high legal-risk claims.",
    },
    "source_attribution_coverage": {
        "display_name": "Source Attribution Coverage",
        "scale": "0-1",
        "min": 0.0,
        "max": 1.0,
        "direction": "higher_is_better",
        "benchmark": ">= 0.80",
        "weight": 0.20,
        "description": (
            "Proportion of material claims that are explicitly tied to named data sources or tables."
        ),
        "scoring_anchor": "1.0 means all major claims are source-linked; 0.0 means no attribution.",
    },
    "missingness_disclosure": {
        "display_name": "Missingness Disclosure",
        "scale": "0 or 1",
        "min": 0.0,
        "max": 1.0,
        "direction": "higher_is_better",
        "benchmark": "== 1",
        "weight": 0.10,
        "description": (
            "Whether data gaps, uncertainty, and unavailable values are explicitly disclosed."
        ),
        "scoring_anchor": "1 = disclosure present and clear; 0 = missingness not disclosed.",
    },
    "public_utility_rating": {
        "display_name": "Public Utility Rating",
        "scale": "0-2",
        "min": 0.0,
        "max": 2.0,
        "direction": "higher_is_better",
        "benchmark": ">= 1.00",
        "weight": 0.10,
        "description": (
            "How actionable and understandable the summary is for public-facing decision support."
        ),
        "scoring_anchor": "0 = not useful, 1 = moderately useful, 2 = clearly useful and interpretable.",
    },
    "legal_claim_safety": {
        "display_name": "Legal-Claim Safety",
        "scale": "0 or 1",
        "min": 0.0,
        "max": 1.0,
        "direction": "higher_is_better",
        "benchmark": "== 1",
        "weight": 0.10,
        "description": (
            "Binary safety gate: avoids legal recommendations and unsupported legal determinations."
        ),
        "scoring_anchor": "1 = safe; 0 = unsafe legal framing present.",
    },
    "coverage_required_public_questions": {
        "display_name": "Coverage of Required Public Questions",
        "scale": "0-2",
        "min": 0.0,
        "max": 2.0,
        "direction": "higher_is_better",
        "benchmark": ">= 1.50",
        "weight": 0.10,
        "description": (
            "Coverage of required public questions (counts/rates/disparities/caveats) in the summary."
        ),
        "scoring_anchor": "0 = poor coverage, 1 = partial coverage, 2 = full required coverage.",
    },
}

OVERALL_SCORE_FORMULA = (
    "overall_score_0_to_100 = 100 * sum(weight_i * normalized_metric_i)"
)

RUBRIC_NOTES = {
    "normalization": (
        "Each dimension is normalized to [0,1]. "
        "For higher-is-better metrics: (value - min) / (max - min). "
        "For lower-is-better metrics (Legal Claim Risk): 1 - ((value - min) / (max - min))."
    ),
    "weight_sum_check": "All weights must sum to 1.0.",
    "benchmark_rule": (
        "A report is rubric-pass when overall_score >= 80 and all binary safety checks are met."
    ),
}


def normalize_metric(metric_name: str, value: float) -> float:
    """Normalize one rubric metric into the [0,1] range with direction-aware handling."""
    spec = RUBRIC_SPEC[metric_name]
    lo = float(spec["min"])
    hi = float(spec["max"])
    if hi == lo:
        return 0.0

    clipped = max(lo, min(hi, float(value)))
    scaled = (clipped - lo) / (hi - lo)
    if spec["direction"] == "lower_is_better":
        scaled = 1.0 - scaled
    return max(0.0, min(1.0, scaled))


def compute_overall_score(scores: Dict[str, float]) -> Dict[str, Any]:
    """Return weighted overall score and normalized component scores."""
    weight_sum = sum(float(v["weight"]) for v in RUBRIC_SPEC.values())
    if round(weight_sum, 6) != 1.0:
        raise ValueError(f"RUBRIC_SPEC weights must sum to 1.0. Found {weight_sum}.")

    normalized = {}
    weighted_sum = 0.0
    for metric_name, spec in RUBRIC_SPEC.items():
        raw_value = float(scores[metric_name])
        norm_value = normalize_metric(metric_name, raw_value)
        normalized[metric_name] = norm_value
        weighted_sum += float(spec["weight"]) * norm_value

    overall_score = round(100.0 * weighted_sum, 2)
    gate_pass = bool(scores["legal_claim_safety"] == 1 and scores["missingness_disclosure"] == 1)
    rubric_pass = overall_score >= 80.0 and gate_pass

    return {
        "overall_score": overall_score,
        "overall_score_scale": "0-100",
        "normalized_scores": normalized,
        "gate_pass": gate_pass,
        "rubric_pass": rubric_pass,
    }
