# SP2 — Behavioral Fidelity Expansion: Findings

## Norms extraction outcome (2026-05-04)

The Reasoner-extracted canonical norms (per the meta-analysis-only constraint) reveal that **most behavioral metrics lack systematic cross-study reviews**. The LLM, faithfully following the circularity-protection instruction to cite only meta-analyses and review articles, marked the following metrics as NULL with explicit reason:

| Paradigm class | Metric | Reason |
|---|---|---|
| conflict | between_subject_sd | No meta-analysis aggregates between-subject SDs of ex-Gaussian parameters for conflict-task RT |
| conflict | lag1_autocorr | No meta-analysis reports canonical lag-1 RT autocorrelation; existing data is in primary studies of sequential dependencies |
| interrupt | rt_distribution | No SST-specific ex-Gaussian meta-analysis; methodological treatments (e.g., BEESTS/Matzke 2013) describe estimation but don't pool population ranges |
| interrupt | between_subject_sd | Same gap as conflict |
| interrupt | lag1_autocorr | Same gap as conflict |

Concrete ranges WERE found for:

| Paradigm class | Metric | Range | Source |
|---|---|---|---|
| conflict | rt_distribution.mu | [400, 550] ms | Matzke & Wagenmakers 2009; Whelan 2008 |
| conflict | rt_distribution.sigma | [25, 60] ms | (same) |
| conflict | rt_distribution.tau | [70, 160] ms | (same) |
| conflict | post_error_slowing | [10, 50] ms | Danielmeier & Ullsperger 2011 review |
| conflict | cse_magnitude | [-45, -10] ms | Egner 2007 review |
| interrupt | post_error_slowing | [10, 50] ms | (same) |
| interrupt | ssrt | [180, 280] ms | Verbruggen et al. 2019 consensus |

## Implication for SP2 success criterion

The design's stated criterion — "all three pillars hit on 4 dev paradigms" — is not measurable as written for the metrics with no canonical range. SP2 adopts the design's documented fallback: **NULL-range metrics are descriptive-only**. Pass/fail gates only on metrics with concrete published ranges.

**Adjusted SP2 success criterion (2026-05-04):**

A paradigm "passes" when all gateable metrics for its class fall within their published ranges:

- **conflict-class paradigms** (3 dev tasks: expfactory_stroop, stopit_stop_signal, cognitionrun_stroop):
  - rt_distribution mu, sigma, tau in published ranges
  - post_error_slowing in published range
  - cse_magnitude in published range
  - between_subject_sd: descriptive-only
  - lag1_autocorr: descriptive-only

- **interrupt-class paradigms** (1 dev task: expfactory_stop_signal — STOP-IT also has interrupt class):
  - post_error_slowing in published range
  - ssrt in published range
  - rt_distribution: descriptive-only
  - between_subject_sd: descriptive-only
  - lag1_autocorr: descriptive-only

This is a strictly weaker criterion than the original design but is the strongest defensible criterion under literature-grounded discipline. The descriptive-only metrics still get reported in every validation run and can be inspected by reviewers; we simply don't claim canonical pass/fail on them.

## Why this matters for the paper

Reviewers will value the discipline shown here: rather than over-claim gateable status on metrics where the literature doesn't support it, we explicitly mark them as ungateable and report values descriptively. A reviewer can read the report and form their own opinion on whether the bot's between-subject SD looks reasonable, without us asserting it does.
