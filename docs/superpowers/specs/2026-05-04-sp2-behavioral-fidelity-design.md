# SP2 — Behavioral Fidelity Expansion: Design

**Date:** 2026-05-04
**Author:** Logan Bennett (via Claude Opus 4.7)
**Status:** Approved
**Predecessor:** `2026-04-23-taskcard-reasoner-design.md` (SP1), `2026-05-04-sp1.5-stage1-prompt-gaps-design.md` (SP1.5)

## Goal

Extend the bot's behavioral repertoire so that, on each of the 4 development paradigms, its output is statistically indistinguishable from human data on three pillars: full RT distribution shape, canonical sequential effects, and population-level individual differences. Build the extension as a generalized effect-type registry that future paradigms (SP5) can plug into without rewriting the executor.

## Background

SP1 established a peer-reviewable TaskCard format and 5-stage Reasoner that produces literature-grounded behavioral parameters. SP1.5 closed the Stage 1 gaps and accumulated a reasoning chain. The bot now produces parameter values traceable to specific papers — but its output's *match to human data* has been measured only on means (the analysis notebook compares mean RT and accuracy per condition). The paper claim requires distributional match plus canonical sequential effects (CSE on conflict tasks; PES on tasks with errors) plus realistic population-level variability.

The current `temporal_effects` schema has six fixed entries. None covers the congruency-sequence effect (CSE / Gratton 1992) — a 2-back interaction where the conflict effect is reduced after an incongruent trial. Without CSE, the bot's data on conflict paradigms looks "humanlike on means" but conspicuously missing on a canonical published interaction. A skeptical reviewer running standard sequential-effects analysis would flag this immediately.

The 4 development paradigms include 3 conflict tasks (expfactory_stroop, stopit_stroop-equivalent, cognitionrun_stroop) and 2 stop-signal interrupt tasks (expfactory_stop_signal, stopit_stop_signal). Future paradigms (SP5) will introduce task-switching, n-back, and others — each with its own canonical sequential effect (switch cost, list-length effect, etc.). SP2 must produce a framework where adding a new effect type does not require rewriting the executor or the validation logic.

A key design constraint: the bot's parameters come from Claude's literature reasoning, not from local human reference data. Human data is read only by the validation oracle, never by the Reasoner. This asymmetric data flow preserves the paper's causal chain ("literature → bot → matches independent data") and prevents the bot from being calibrated to the test set.

## Architecture

```
        Reasoner (5 existing stages + new norms extractor)
                          │
                          ├─────────────────────┐
                          ▼                     ▼
                    TaskCard           norms/{paradigm}.json
                    (parameters)       (per-metric published ranges
                     - paradigm_classes tags on task    + DOI citations
                     - temporal_effects keyed by         from meta-analyses
                       registered effect-type names      and review articles)
                     - between_subject_sd from Claude's
                       reading of inter-subject variability
                       norms in cited papers)
                          │
                          ▼
                    Performer (15 sessions × 4 paradigms)
                          │
                          ▼
        ┌─────────────────────────────────────────────┐
        │  SP2 Validation oracle (NEW; separate)      │
        │  Reads bot output + norms/{paradigm}.json:  │
        │   - bot RT distribution vs published range  │
        │   - bot ex-Gaussian params vs published     │
        │     mu/sigma/tau ranges                     │
        │   - bot population SD vs published SD range │
        │   - bot lag-1 autocorr vs published range   │
        │   - bot PES vs published range              │
        │   - bot CSE magnitude vs Egner 2007 range   │
        │   - bot SSRT vs Verbruggen 2019 range       │
        │  Optionally: side-by-side comparison vs     │
        │  Eisenberg 2019 (descriptive only).         │
        │  Reports pass/fail per pillar per task.     │
        └─────────────────────────────────────────────┘
```

### Four strict rules

- **Asymmetric data flow on subject-level data.** Raw subject-level human reference data (e.g., Eisenberg 2019 trial-level CSVs) is read ONLY by the validation oracle, never by the Reasoner. The bot's parameters come from Claude's literature reasoning + DOI-verified citations (the SP1 mechanism).
- **Validation against published canonical norms, not against any single dataset.** The oracle's pass/fail criterion is "bot's metric falls within published-literature ranges per the canonical reviews/meta-analyses cited in `norms/{paradigm}.json`." Specific datasets like Eisenberg 2019 are shown side-by-side for context but do not gate pass/fail. This protects against the failure mode where a single dataset is flawed, unrepresentative, or contested.
- **Norms extraction citation discipline.** The Reasoner stage that extracts norms is prompted to cite **meta-analyses and review articles**, not the same primary sources used for parameter-setting. This avoids circularity (bot trivially matching norms because both came from the same citation pool). When meta-analyses don't exist for a metric, the norms extractor reports "no canonical range available" — that metric becomes descriptive-only for the affected paradigm.
- **Failures route to prompts, not to data.** If the bot's output mismatches the published range, the fix is in `prompts/system.md` or in providing better literature pointers — not in feeding the bot human data, and not in widening the published-range thresholds.

## Generalized effect framework

Two classes of temporal effects, schema-distinguished:

| Class | Examples | Applicability |
|---|---|---|
| **Paradigm-universal** | autocorrelation, fatigue_drift, post_error_slowing, pink_noise | All speeded-choice paradigms |
| **Paradigm-specific** | CSE (conflict only), switch_cost (task-switching only), list_length effect (memory only), stop_signal_dependence (interrupt only) | Restricted to specific paradigm families |

The TaskCard schema's `temporal_effects` becomes a registry-keyed map. Each entry is keyed by an effect-type name and validated against an effect-type registry.

### Effect-type registry

Lives in `src/experiment_bot/effects/registry.py`:

```python
EFFECT_REGISTRY = {
    # Paradigm-universal (already exist; just formalized as registry entries)
    "autocorrelation": EffectType(
        params={"phi": float},
        applicable_paradigms=ALL,
        handler=apply_autocorrelation,
        validation_metric=lag1_autocorr_match,
    ),
    "fatigue_drift": EffectType(...),
    "post_error_slowing": EffectType(...),
    "pink_noise": EffectType(...),
    "condition_repetition": EffectType(...),
    "post_interrupt_slowing": EffectType(...),

    # Paradigm-specific (SP2 adds CSE as the first; framework supports more)
    "congruency_sequence": EffectType(
        params={"sequence_facilitation_ms": float, "sequence_cost_ms": float},
        applicable_paradigms={"conflict"},
        handler=apply_cse,
        validation_metric=cse_magnitude_match,
    ),
}
```

### Reasoner-side generalization

Stage 1 (or a Reasoner-side classifier) tags each task with one or more paradigm classes in `TaskCard.task.paradigm_classes`: e.g., `["conflict"]` for Stroop/Flanker/Simon, `["interrupt"]` for stop-signal, `["task_switching"]` for cued switching, `["memory"]` for n-back. The list is open-ended; Claude proposes paradigm classes; the registry filters which paradigm-specific effects are eligible. Universal effects always apply.

Stage 2's prompt enumerates ONLY (universal effects + effects whose `applicable_paradigms` intersects the task's paradigm classes). Claude picks which to enable and parameterizes from literature. This prevents offering CSE on stop-signal tasks or stop_signal_dependence on Stroop.

### Executor-side generalization

`ResponseSampler` no longer hardcodes 6 effect handlers. It iterates the TaskCard's `temporal_effects` keys, looks each up in the registry, and applies the handler in order. New effect types added to the registry get applied automatically. Handler-application order is registry-defined (autocorrelation first, then fatigue, then sequential effects, etc.).

### Validation oracle generalization

The oracle iterates effects in the TaskCard, looks up `validation_metric` in the registry, and runs whichever validators apply. Universal metrics (RT KS, ex-Gaussian recovery, population SD) run on every task. Paradigm-specific metrics (CSE magnitude, SSRT, etc.) run only when the relevant effect is enabled in the TaskCard.

### SP2 v1 scope

Ships:
- The registry mechanism + 6 existing effects re-expressed as registry entries (no behavioral change for these — pure refactor).
- ONE new paradigm-specific effect: `congruency_sequence` (CSE), with handler + validation metric.
- Reasoner prompt updates to use the registry filter and to populate `paradigm_classes`.
- Validation oracle that runs all applicable metrics.

Does NOT ship:
- `switch_cost`, `list_length`, `stop_signal_dependence`, etc. — registered as schema placeholders only when a development paradigm exists to validate against (none today besides conflict + interrupt). These come in SP5 alongside their paradigms.

## Validation oracle

**Module:** `src/experiment_bot/validation/oracle.py` — function `validate_session_set(taskcard, session_dirs, norms_path, eisenberg_path=None) -> ValidationReport` that scores bot output against published norms (`norms_path`) and optionally shows side-by-side descriptive comparison to Eisenberg 2019 (`eisenberg_path`).

### Norms file schema (`norms/{paradigm_class}.json`)

```jsonc
{
  "paradigm_class": "conflict",
  "produced_by": {                  // same shape as TaskCard.produced_by
    "model": "claude-opus-4-7",
    "extraction_prompt_sha256": "...",
    "timestamp": "2026-05-04T..."
  },
  "metrics": {
    "rt_distribution": {
      "mu_range": [430, 580],
      "sigma_range": [40, 90],
      "tau_range": [50, 130],
      "citations": [
        {"doi": "10.1016/j.cognition.2008.07.011", "quote": "...", "doi_verified": true}
      ]
    },
    "between_subject_sd": {
      "mu_sd_range": [30, 80],
      "sigma_sd_range": [8, 20],
      "tau_sd_range": [15, 35],
      "citations": [...]
    },
    "lag1_autocorr": {
      "range": [0.05, 0.25],
      "citations": [...]
    },
    "post_error_slowing": {
      "range_ms": [10, 60],
      "citations": [{"doi": "10.1037/h0042782", "authors": "Rabbitt", ...}]
    },
    "cse_magnitude": {           // paradigm-specific; only present in conflict norms
      "range_ms": [15, 55],
      "citations": [{"doi": "10.1016/j.tics.2007.08.005", "authors": "Egner", ...}]
    }
  }
}
```

When a metric has no canonical published range (e.g., a niche paradigm with no meta-analysis), the entry is `{"range": null, "no_canonical_range_reason": "<text>"}` and the oracle reports descriptively for that metric only.

### Pass criteria (against published ranges)

| Metric | Pass criterion |
|---|---|
| **RT distribution mu** | bot's mu in `mu_range` for the paradigm |
| **RT distribution sigma** | bot's sigma in `sigma_range` |
| **RT distribution tau** | bot's tau in `tau_range` |
| **Population SD on mu** | SD across N=15 bot sessions in `mu_sd_range` |
| **Population SD on sigma** | SD across N=15 bot sessions in `sigma_sd_range` |
| **Population SD on tau** | SD across N=15 bot sessions in `tau_sd_range` |
| **Lag-1 autocorrelation** | bot's mean lag-1 r in published `range` |
| **Post-error slowing** | bot's mean PES in published `range_ms` |
| **CSE magnitude** | bot's mean CSE in published `range_ms` (conflict paradigms only) |
| **SSRT** | bot's SSRT (integration method) in published `range_ms` (interrupt paradigms only) |

Each pass criterion is a simple range check, not a statistical test. The published range already encodes the cross-study variability that subsumes both random-sampling noise and methodological differences.

### Optional side-by-side with a specific dataset

If `eisenberg_path` is provided, the oracle ALSO computes the bot's metric vs Eisenberg 2019's value and reports the comparison **descriptively only**. Output looks like:

```
mu (Stroop congruent)
  bot:        542 ms
  published:  [430, 580]   ✅ in range
  Eisenberg:  537 ms       (descriptive only; bot − Eisenberg = +5 ms)
```

This satisfies a reviewer who asks "how does the bot compare to a specific real dataset" without gating on that dataset.

### Norms extractor (new Reasoner sub-module)

A standalone extractor at `src/experiment_bot/reasoner/norms_extractor.py`. Function: `extract_norms(paradigm_class: str, llm_client) -> dict`. Prompted to cite ONLY meta-analyses and review articles. Optionally seeded with a list of known seminal papers per paradigm (Egner 2007 for CSE, Verbruggen 2019 for SSRT, Whelan 2008 for RT distributions, etc.). Output validated against the norms file schema before saving.

CLI entry point: `experiment-bot-extract-norms --paradigm-class conflict` — produces `norms/conflict.json`. Run once per paradigm class; norms files are committed to the repo and treated as project-level artifacts (not per-TaskCard).

### Report format

```python
@dataclass
class ValidationReport:
    task_label: str
    pillar_results: dict[str, PillarResult]
    overall_pass: bool       # all gating metrics in published range
    summary: str

@dataclass
class PillarResult:
    pillar: str          # "rt_distribution" | "sequential" | "individual_differences"
    metrics: dict[str, MetricResult]
    pass_: bool

@dataclass
class MetricResult:
    name: str
    bot_value: float
    published_range: tuple[float, float] | None    # None when no canonical range
    pass_: bool | None                              # None for descriptive-only metrics
    eisenberg_value: float | None                   # optional; descriptive
    citations: list[Citation]
```

Output: one `validation/{label}_{taskcard_hash}_{timestamp}.json` per run plus a summary CSV with one row per (paradigm, metric).

CLI entry point: `experiment-bot-validate --label <label>` reads latest TaskCard for the label, finds session output directories under `output/`, loads `norms/{paradigm_class}.json`, optionally loads Eisenberg data if present, runs the oracle.

## Prompt changes

**`prompts/system.md` additions (one new section, "Sequential and temporal effects"):**

- Document the universal effects (already in current prompt) — light cleanup only.
- Document the paradigm-class concept: Claude tags `task.paradigm_classes` (open-ended list of strings like `"conflict"`, `"interrupt"`, `"task_switching"`, `"memory"`, `"speeded_choice"`).
- Document `congruency_sequence` as the canonical example of a paradigm-specific effect, with params (`sequence_facilitation_ms`, `sequence_cost_ms`), references (Gratton 1992; Egner 2007 for review), and triggering condition ("populate this only when the paradigm has a manipulable congruency dimension AND the task has multiple consecutive trials of varying congruency").
- Standalone instruction: "When setting `between_subject_sd`, reason from published RT-norms literature (Whelan 2008, ex-Gaussian fits in healthy adults typically show population SD of mu ~50ms, sigma ~10ms, tau ~20ms — but these are paradigm-specific; cite the paper your values come from)."

**Stage 2 user-message builder addition:** the registry-filtered list of effects applicable to this task's paradigm classes, with example parameter values from canonical papers.

## Testing

### Unit tests (no live LLM)

- `tests/test_effect_registry.py` — registry construction, lookup, paradigm filtering. ~6 tests.
- `tests/test_effect_handlers.py` — each effect handler in isolation, including the new CSE handler. CSE-specific: pre/post sequences of (cong, incong) trials produce correct facilitation_ms / cost_ms RT modulation. ~8 tests.
- `tests/test_validation_oracle.py` — oracle on synthetic bot input + handcrafted norms files with known ranges; verifies pass/fail logic for each metric, including the descriptive-only path when `range` is null. ~10 tests.
- `tests/test_norms_extractor.py` — norms extractor with mocked LLM responses producing valid norms-file shapes; schema validation; circularity-prevention prompt content check. ~5 tests.

### Integration tests

- `tests/test_reasoner_paradigm_filter.py` — Reasoner filters effects by paradigm class. Mock LLM returning `paradigm_classes=["conflict"]` should get CSE in the eligible-effects list; `["interrupt"]` should not. ~3 tests.

### Live tests (gated, RUN_LIVE_LLM=1)

- One end-to-end Reasoner regen on `expfactory_stroop` and verification that the resulting TaskCard has `congruency_sequence` enabled and `paradigm_classes` includes `"conflict"`.
- One end-to-end norms extraction for paradigm class `"conflict"` and verification that the resulting `norms/conflict.json` has DOI-verified citations from meta-analyses or reviews.
- One executor smoke against a CSE-enabled TaskCard verifying CSE structure appears in `bot_log.json`.

### Validation oracle live runs

After SP2 lands the registry, executor changes, Reasoner prompts, AND `norms/{conflict, interrupt}.json` are extracted, regenerate the 4 dev TaskCards. Then run a fresh batch (15 sessions × 4 paradigms = 60 sessions). Then run `experiment-bot-validate` against each. Report per-pillar pass/fail. **THIS is the SP2 success measurement.**

If a metric falls outside its published range on a paradigm: the fix is in the prompt or in providing better literature pointers to the Reasoner — NOT in widening the norms range, and NOT in feeding the bot human data. Iterate prompt → regenerate → re-validate.

## Success criterion

SP2 is "done" when, on all 4 dev paradigms, the bot's mean output for every gating metric falls within the published canonical range as recorded in `norms/{paradigm_class}.json`:

- ✅ ex-Gaussian mu, sigma, tau in published ranges (per condition)
- ✅ Population SD on mu, sigma, tau in published cross-subject SD ranges
- ✅ Lag-1 autocorrelation in published range
- ✅ Post-error slowing in published range
- ✅ CSE magnitude in published range from canonical reviews (3 conflict paradigms only)
- ✅ SSRT in published range from Verbruggen et al. consensus (2 stop-signal paradigms only)

Side-by-side comparison to Eisenberg 2019 is reported but does NOT gate.

If any gating metric falls outside its published range on any paradigm, SP2 is incomplete — iterate prompts and regen until in range.

**Metrics with no canonical range** (e.g., niche derived metric with no meta-analysis) are descriptive-only — they appear in the report but don't gate pass/fail.

**Failure mode protection:** if iterating the prompt cannot produce values within published ranges, this is itself a paper finding. Document in `docs/sp2-findings.md` what didn't converge and why. The literature-only approach has documented limits for that paradigm — a real result.

## Out of scope (deferred)

- New paradigm-specific effects beyond CSE (switch cost, list length, n-back lure, etc.) — registered when SP5 brings new paradigms. Schema is ready; just no implementations or validators yet.
- Auto-iteration of prompts (some kind of optimization loop). Manual prompt iteration is sufficient for v1.
- Non-RT metrics like response confidence or reaction-time-by-position curves.
- Bot reading raw subject-level human reference data (explicitly forbidden by the asymmetric-data-flow rule).
- Validation against any specific dataset as a gating criterion (Eisenberg 2019 is descriptive-only). The gating mechanism is published canonical norms.
- Norms files for paradigm classes the dev set doesn't include (task-switching, memory, etc.) — extracted in SP5 alongside their paradigms.
- HPC / Slurm execution (SP3).
- Per-session forensic trace logs and audit reports (SP6).

## Estimated effort

~2–3 weeks for the framework + CSE + oracle + Reasoner prompt updates + initial validation pass. Add 1–2 weeks if multiple iteration rounds are needed to pass all pillars. Plan for 4 weeks total to ship SP2 to "validation-pass" state.

## Risks

- **CSE handler implementation correctness.** The 2-back interaction is subtle; an off-by-one in trial-pair tracking could produce a mathematically-valid-but-wrong CSE. Mitigation: extensive unit tests on synthetic trial sequences with known expected RT modulations.
- **Norms extraction circularity.** If the Reasoner pulls norms from the same papers it cites for parameter-setting, the bot trivially matches by construction. Mitigation: norms-extractor prompt explicitly requires meta-analyses and review articles (e.g., Egner 2007 for CSE; Verbruggen 2019 for SSRT). Manual review of the first norms files per paradigm is recommended before relying on them as gates.
- **Norms files may have no canonical range for some metrics.** Some metrics (e.g., a derived measure with no published meta-analysis) genuinely have no defensible canonical range. Mitigation: norms file schema explicitly supports `{"range": null, "no_canonical_range_reason": "..."}` for these — they become descriptive-only and don't gate.
- **Published ranges may be too wide to be discriminating.** A range like "Stroop congruent mu in [400, 600]" is broad enough that many implementations pass, including ones that don't behave very humanlike on shape or sequential effects. Mitigation: combination of universal metrics (RT distribution + ex-Gaussian + sequential effects + population SD) jointly constrains the bot more tightly than any single metric. The point is not to "pass narrowly" but to be in the published mainstream on all metrics simultaneously.
- **Effect-registry refactor risk.** Re-expressing 6 existing effects as registry entries is a structural change to ResponseSampler. Mitigation: regression test that bot output before/after the refactor produces statistically equivalent traces (run 10 sessions of each task on a frozen seed, compare per-trial RT and accuracy log).
- **Eisenberg 2019 differs from canonical norms.** This is now a feature, not a bug — the bot is validated against published norms; Eisenberg shows up descriptively as "for context, here is one specific real-world dataset." If Eisenberg falls outside the published range, that's interesting independent of the bot.
