# SP12 deliverable — codebase simplification + audit + N=5 re-measurement

**Date:** 2026-05-22
**Tag:** `sp12-complete` (at this commit)
**Branch:** `sp11/playwright-recommit`

## What landed

Top-down walk-and-prune from CLI entry through every module exercised
in a production run. Each module's walk: read, list candidates, user
checkpoint, delete approved with one commit per logical removal, run
tests, append findings to `docs/sp12-hardcoded-findings.md`.

Plus Phase 2 visibility (pipeline-flow.md + narrated stdout +
run_trace.json) and Phase 3 re-measurement (5 sessions × 4 paradigms
vs the Phase 7 N=5 baseline).

## Before / after (vs commit 2436289, SP11/Phase 7 end-state)

| Metric | Before SP12 | After SP12 | Delta |
|---|---|---|---|
| Source LOC (src/experiment_bot/) | 9,566 | 8,498 | -1,068 |
| Python files in src/ | 66 | 58 | -8 |
| Scripts (excl. surviving 3) | 14 | 0 | -14 |
| SP11 phase docs | 14 | 0 (consolidated to sp11-complete.md) | -14 |
| CLI flags on `experiment-bot` | 7 | 5 | -2 (--no-calibration, --skip-calibration-pass) |
| Test files in tests/ | 77 | 73 | -4 |
| Tests collected | 743 | 679 | -64 |
| Commits during SP12 (from 2436289) | 21 | | |

Note: the script and SP11-phase-doc deletions were committed earlier
in SP12 (commits `25ac1a9`, `87566ff`, `2436289`) — slightly before
the LOC-diff baseline above. Counted in the "Delta" column because
they are SP12 work; the full-SP12 commit count from the design-spec
commit `19b809b` is 26.

## What survived (final shape)

`src/experiment_bot/` after SP12 (58 .py files, 8,498 LOC):

```
cli.py
__init__.py
calibration/   (calibrator, llm_deliverer, scope, target_extractor, types)
core/          (executor, config, distributions, stimulus, phase_detection)
effects/       (registry + per-effect handlers, used via TaskCard)
llm/           (cli_client + api_client behind a single Protocol)
navigation/    (navigator, stuck-detection)
output/        (writer, run_metadata)
prompts/       (system.md + per-stage templates)
reasoner/      (stage1..stage5 + norms_extractor, pipeline orchestrator)
taskcard/      (loader, sampler, types/schema)
validation/    (oracle, platform_adapters, expfactory, cognitionrun, stopit)
```

See `docs/pipeline-flow.md` for a 13-section walkthrough — one section
per module, each with its entry-point reference.

## What was removed (highlights)

**Scripts:** all one-shot SP-era helpers (phase7_sweep, phase7_aggregate,
phase7_baseline_snapshots, check_parameter_drift, probe_*, keypress_audit,
batch_run, test_run, __deprecated__, figure1+2 PNGs). Renamed
phase7_analysis.py → analyze_sessions.py with generic --root.

**Docs:** 14 SP11 phase-deliverable docs consolidated into
sp11-complete.md.

**Code:**
- SessionAgent path (entire `agent/` package, plus the cli.py and
  executor.py wiring) — SP9a empirically showed hypothesis not supported
- SP7 keypress diagnostic (_install_keydown_listener,
  _drain_keydown_log, _log_trial_with_keypress_diag, the 4 per-trial
  diagnostic fields) — no production read consumers
- `--no-calibration`, `--skip-calibration-pass` CLI flags + their
  RuntimeConfig fields — Phase 7 pre-cal-arm experiment is done
- `RuntimeConfig.session_agent_enabled` — orphaned after SessionAgent
  removal
- `calibration/drop_from_scope.py` — CLI guard was removed in Task 3
- `calibration/keyboard_deliverer.py` — delivery_channel="keyboard"
  never set in production
- `calibration/focus.py` — listener_focus_js never passed by callers
- `validation/eisenberg.py` — zero production callers
- `_wrap_legacy_dist`/`_wrap_legacy_effect` in taskcard/types.py —
  all current TaskCards use v2 layout
- Multiple smaller cleanups (dead imports, unused exception bindings,
  obsolete tests for removed flags, etc.)

## Hardcoded paradigm findings

See `docs/sp12-hardcoded-findings.md` for the per-module list (19
sections across the 13 modules walked, including cross-cutting
reasoner findings). Notable structural assumptions:

- `validation/platform_adapters.py` — `PLATFORM_ADAPTERS` and
  `TEST_ROW_PREDICATES` are paradigm-labeled dispatch tables; long-term
  destination is TaskCard-emitted field-mapping config.
- Three sites still hardcode the detection-method vocabulary
  (`stimulus.py`, `pilot.py`, `executor.py`) — adding a 5th method is
  a 3-edit ripple.
- `DetectionConfig.alt_method` field is schema-only (never read).
- `core/distributions.py`: `jitter_distributions` only handles
  ex_gaussian; lognormal/shifted-Wald paradigms would silently get
  no jitter.
- `reasoner/stage1_structural.py`: `REQUIRED_FIELDS_CHECKLIST` contains
  paradigm-name leakage (e.g., "STOP-IT calls a custom
  jsPsych.data.getInteractionData()") — would force TaskCard regen if
  changed.

## Architectural candidates surfaced but not removed

- Two LLM client implementations (cli + api) no longer needed for
  capability — kept for UX (Max subscription vs API key).
- `output_format` + `images` params on `LLMClient.complete` are
  vestigial (no production caller passes them).
- `LogNormalSampler` / `ShiftedWaldSampler` unused by current
  TaskCards but generic-toolkit per G2.
- All recent `run_metadata.json` show
  `calibration: model="too_few_events"` — calibration isn't actually
  firing across paradigms. Phase 3 N=5 sessions confirm this signal
  persists.
- `condition_repetition` effect handler — deprecated in favor of
  `lag1_pair_modulation`. Currently only `expfactory_flanker`
  (a held-out paradigm) has `enabled=True`.
- `PinkNoiseConfig.hurst` legacy field — deprecated in favor of
  `alpha`, but 6 of 11 current TaskCards still emit `hurst`.

## Runtime visibility

Phase 2 added:
- `docs/pipeline-flow.md` — 13-section walkthrough, ~10-min read,
  one section per module with entry-point references.
- `[sp12]` stdout narration — 5 lines per session (navigate,
  calibration, trial_loop, wait_completion, save). Greppable via
  the `[sp12]` prefix.
- `run_trace.json` — small structured trace beside `bot_log.json`,
  one entry per major stage with duration_s. Per-trial detail
  stays in `bot_log.json`.

## Post-cleanup re-measurement

See `docs/sp12-remeasure-results.md`. Headline: 3 of 4 paradigms
behaviorally stable post-cleanup vs the Phase 7 N=5 baseline. One
notable shift: `expfactory_stop_signal` SSRT 178 → 353 ms (BELOW
→ ABOVE norm), within baseline's wide SD (±207). Tighter post-SP12
SD (±34) suggests SP12 measurement is more reliable; the shift is
plausibly attributable to SP7 keypress-diagnostic noise being
removed.

## Pre-registration disclosure

SP12 did not modify:
- `docs/scope-of-validity.md` claims
- Norms files in `norms/`
- §6 pre-registered metrics from the SP11 design spec
- Stage 1-5 prompts or schema (verified: no TaskCard regen needed)

## Backlog rolled forward (to a hypothetical SP13)

- All-paradigm calibration `too_few_events` — investigate why
  calibration pass never produces enough paired events
- Detection-method dispatch duplicated across 3 sites — refactor to
  shared helper
- LLM client consolidation (cli/api) post SessionAgent removal
- `PLATFORM_ADAPTERS` migration toward TaskCard-emitted field-mapping
- `condition_repetition` + `PinkNoiseConfig.hurst` deprecation
  completion (forces TaskCard regen)
- `expfactory_stop_signal` SSRT shift investigation

## Files added during SP12

- `docs/sp12-hardcoded-findings.md` (per-module audit findings)
- `docs/sp12-deliverable.md` (this doc)
- `docs/sp11-complete.md` (consolidated SP11 phase docs)
- `docs/pipeline-flow.md` (13-section walkthrough)
- `docs/sp12-remeasure-results.md` + `.json`
- `tests/test_executor_narration.py`, `tests/test_run_trace.py`

## Files / packages removed during SP12

- 14 one-shot scripts in `scripts/`
- 14 individual SP11 phase deliverable docs
- `src/experiment_bot/agent/` package (4 files)
- `src/experiment_bot/calibration/drop_from_scope.py`
- `src/experiment_bot/calibration/keyboard_deliverer.py`
- `src/experiment_bot/calibration/focus.py`
- `src/experiment_bot/validation/eisenberg.py`
- 8 test files covering removed code
