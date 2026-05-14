# HW3 ICE Summary Validation Rubric

This rubric defines the final scoring scales, benchmarks, and overall score formula for ICE county summary validation.

## Dimensions, Scales, and Benchmarks

| Dimension | Scale | Benchmark | Direction | Weight |
|---|---|---|---|---|
| Numeric Fidelity | 0-1 | >= 0.90 | Higher is better | 0.25 |
| Legal Claim Risk | 0-2 | <= 0.50 | Lower is better | 0.15 |
| Source Attribution Coverage | 0-1 | >= 0.80 | Higher is better | 0.20 |
| Missingness Disclosure | 0 or 1 | == 1 | Higher is better | 0.10 |
| Public Utility Rating | 0-2 | >= 1.00 | Higher is better | 0.10 |
| Legal-Claim Safety | 0 or 1 | == 1 | Higher is better | 0.10 |
| Coverage of Required Public Questions | 0-2 | >= 1.50 | Higher is better | 0.10 |

Weight sum check: `0.25 + 0.15 + 0.20 + 0.10 + 0.10 + 0.10 + 0.10 = 1.00`.

## Scoring Interpretation Anchors

- Numeric Fidelity: `1.0` means no numeric mismatch; `0.0` means severe mismatch.
- Legal Claim Risk: `0` no legal-risk language; `1` moderate risk; `2` high risk.
- Source Attribution Coverage: `1.0` all major claims mapped to source; `0.0` no mapping.
- Missingness Disclosure: `1` discloses data gaps/unknowns; `0` does not disclose.
- Public Utility Rating: `0` low utility, `1` moderate utility, `2` high utility for public decisions.
- Legal-Claim Safety: `1` safe framing; `0` unsafe legal recommendation/claim present.
- Coverage of Required Public Questions: `0` poor coverage, `1` partial, `2` full coverage.

## Overall Score Formula

Per-metric normalization:

- Higher-is-better metric: `normalized_i = (raw_i - min_i) / (max_i - min_i)`
- Lower-is-better metric (Legal Claim Risk): `normalized_i = 1 - (raw_i - min_i) / (max_i - min_i)`
- Clip normalized values to `[0, 1]`

Weighted formula:

`overall_score_0_to_100 = 100 * SUM(weight_i * normalized_i)`

## Pass Rule

Rubric pass requires all of:

1. `overall_score >= 80`
2. `legal_claim_safety == 1`
3. `missingness_disclosure == 1`
