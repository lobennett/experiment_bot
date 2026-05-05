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
        Reasoner (5 existing stages, prompt updates)
                          │
                          ▼
                    TaskCard (literature-grounded:
                     - paradigm_classes tags on task
                     - temporal_effects keyed by registered
                       effect-type names
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
        │  Reads bot output + Eisenberg 2019 data:    │
        │   - KS / Anderson-Darling on RT dists       │
        │   - Ex-Gaussian parameter recovery          │
        │   - Population SD across bot vs human       │
        │   - Lag-1 autocorrelation match             │
        │   - Post-error slowing match                │
        │   - CSE magnitude (when applicable)         │
        │   - SSRT (when applicable)                  │
        │  Reports pass/fail per pillar per task.     │
        └─────────────────────────────────────────────┘
```

### Two strict rules

- **Asymmetric data flow.** Human reference data is read ONLY by the validation oracle. The Reasoner never sees it. The bot's parameters come from Claude's literature reasoning + DOI-verified citations (the SP1 mechanism).
- **Failures route to prompts, not to data.** If the bot's output mismatches human, the fix is in `prompts/system.md` or in providing better literature pointers — not in feeding the bot human data.

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

**Module:** `src/experiment_bot/validation/oracle.py` — function `validate_session_set(taskcard, session_dirs, human_reference_path) -> ValidationReport` that runs all applicable metrics and reports per-pillar pass/fail.

### Universal metrics (run on every task)

| Metric | Computation | Pass criterion |
|---|---|---|
| **RT distribution match** | KS test on per-condition correct-trial RT, bot vs human, two-sample | p > 0.01 (two-sided) |
| **Ex-Gaussian parameter recovery** | Fit ex-Gaussian to bot session and to human subject; Cohen's d on each parameter (mu, sigma, tau) across the population | abs(d) < 0.5 for all parameters |
| **Population SD match** | SD across N=15 bot sessions of each parameter, vs SD across human subjects | ratio in [0.5, 2.0] |
| **Lag-1 autocorrelation match** | Pearson r at lag-1 within block, mean across runs vs across subjects | abs(r_bot − r_human) < 0.10 |
| **Post-error slowing match** | mean(RT_{t+1} \| error_t) − mean(RT_{t+1} \| correct_t), per run vs per subject | abs(bot − human) / human_SE < 2 |

### Paradigm-specific metrics

| Metric | Active when | Pass criterion |
|---|---|---|
| **CSE magnitude** | `congruency_sequence` enabled | abs(bot_CSE − human_CSE) / human_cross_subject_SE < 2 (same 2-SE rule as PES) |
| **SSRT recovery** | `runtime.trial_interrupt.detection_condition` populated | bot's SSRT (integration method) within ±50ms of human mean |

### Report format

```python
@dataclass
class ValidationReport:
    task_label: str
    pillar_results: dict[str, PillarResult]
    overall_pass: bool
    summary: str

@dataclass
class PillarResult:
    pillar: str          # "rt_distribution" | "sequential" | "individual_differences"
    metrics: dict[str, MetricResult]
    pass_: bool
```

Output: one `validation/{label}_{taskcard_hash}_{timestamp}.json` per run plus a summary CSV with one row per (paradigm, metric).

CLI entry point: `experiment-bot-validate --label <label>` reads latest TaskCard for the label, finds session output directories under `output/`, finds human reference data per paradigm class, runs the oracle.

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
- `tests/test_validation_oracle.py` — oracle on synthetic bot+human inputs with known statistical properties; verifies pass/fail correctness for each metric. ~10 tests.

### Integration tests

- `tests/test_reasoner_paradigm_filter.py` — Reasoner filters effects by paradigm class. Mock LLM returning `paradigm_classes=["conflict"]` should get CSE in the eligible-effects list; `["interrupt"]` should not. ~3 tests.

### Live tests (gated, RUN_LIVE_LLM=1)

- One end-to-end Reasoner regen on `expfactory_stroop` and verification that the resulting TaskCard has `congruency_sequence` enabled.
- One executor smoke against a CSE-enabled TaskCard verifying CSE structure appears in `bot_log.json`.

### Validation oracle live runs

After SP2 lands the registry, executor changes, and Reasoner prompts, regenerate the 4 dev TaskCards. Then run a fresh batch (15 sessions × 4 paradigms = 60 sessions). Then run `experiment-bot-validate` against each. Report per-pillar pass/fail. **THIS is the SP2 success measurement.**

If a pillar fails on a paradigm: the fix is in the prompt or in providing better literature pointers — NOT in the data. Iterate prompt → regenerate → re-validate.

## Success criterion

SP2 is "done" when, on all 4 dev paradigms:

- ✅ RT distribution KS test p > 0.01 per condition
- ✅ Ex-Gaussian parameter recovery abs(d) < 0.5
- ✅ Population SD ratio in [0.5, 2.0]
- ✅ Lag-1 autocorrelation match within 0.10
- ✅ Post-error slowing match within 2 SE
- ✅ CSE magnitude within 2 cross-subject SE of human mean (3 conflict paradigms only)
- ✅ SSRT within ±50ms of human mean (2 stop-signal paradigms only)

If any pillar fails on any paradigm, SP2 is incomplete — iterate prompts and regen until passing.

**Failure mode protection:** if iterating the prompt cannot produce passing values, this is itself a finding. Document in a `docs/sp2-findings.md` what didn't converge and why. May indicate that the literature-only approach has limits for that paradigm — a real result for the paper.

## Out of scope (deferred)

- New paradigm-specific effects beyond CSE (switch cost, list length, n-back lure, etc.) — registered when SP5 brings new paradigms. Schema is ready; just no implementations or validators yet.
- Auto-iteration of prompts (some kind of optimization loop). Manual prompt iteration is sufficient for v1.
- Non-RT metrics like response confidence or reaction-time-by-position curves.
- Calibration via local data files (explicitly forbidden by the design's asymmetric-data-flow rule).
- HPC / Slurm execution (SP3).
- Per-session forensic trace logs and audit reports (SP6).

## Estimated effort

~2–3 weeks for the framework + CSE + oracle + Reasoner prompt updates + initial validation pass. Add 1–2 weeks if multiple iteration rounds are needed to pass all pillars. Plan for 4 weeks total to ship SP2 to "validation-pass" state.

## Risks

- **CSE handler implementation correctness.** The 2-back interaction is subtle; an off-by-one in trial-pair tracking could produce a mathematically-valid-but-wrong CSE. Mitigation: extensive unit tests on synthetic trial sequences with known expected RT modulations.
- **Human data limitations.** The Eisenberg 2019 trial-level CSV covers stop_signal and stroop. STOP-IT and cognition.run paradigms differ in trial counts, instructions, etc. — direct comparison may be noisy. Mitigation: oracle accepts a `paradigm_class` mapping that points STOP-IT to the same human reference as stop_signal_RDoC.
- **Pillar-pass thresholds may be too strict.** KS p > 0.01 on N=15 bot × 100 trials = 1500 RTs is a high-power test that may reject even moderate effect sizes. Mitigation: thresholds documented in spec; if all paradigms fail KS but pass effect-size-based metrics, re-evaluate the threshold rather than the bot.
- **Literature-only between_subject_sd may be wrong.** Claude's reasoning about between-subject variation may diverge from Eisenberg's empirical SD. Mitigation: this is the whole experiment — if it diverges, that's a paper finding. Don't paper over with calibration.
- **Effect-registry refactor risk.** Re-expressing 6 existing effects as registry entries is a structural change to ResponseSampler. Mitigation: regression test that bot output before/after the refactor produces statistically equivalent traces (run 10 sessions of each task on a frozen seed, compare per-trial RT and accuracy log).
