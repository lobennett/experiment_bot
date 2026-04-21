# Code Review, Analysis Audit, and Batch Run — Design

**Date:** 2026-04-21
**Author:** Logan Bennett (via Claude Opus 4.7)
**Status:** Approved

## Goal

Perform a task-agnosticism and quality review of the `experiment-bot` codebase, audit the analysis notebook for per-platform dataframe handling bugs and alignment with field-standard metric definitions, and then launch 15 instances of each of the 4 validated tasks to produce the full validation dataset.

## Background

`experiment-bot` advertises a zero-shot, task-agnostic, platform-agnostic design: a single Claude API call ingests an experiment's HTML/JS source and produces a `TaskConfig` that drives a generic Playwright executor. The claim is that no task-specific code exists in the Python layer. `docs/how-it-works.md` is the canonical description of that claim.

Two pieces of evidence suggest the claim deserves verification:

- `src/experiment_bot/core/executor.py:318` hardcodes `match.condition == "navigation"`, and `executor.py:326` hardcodes `("attention_check", "attention_check_response")`. These are covert contracts between the executor and Claude's output.
- Several dataclass defaults in `core/config.py` are non-zero (`rt_floor_ms=150`, `rt_cap_fraction=0.90`, `advance_keys=[" "]`, `feedback_fallback_keys=["Enter"]`). `how-it-works.md` claims "all defaults are off or zero."

The analysis notebook (`scripts/analysis.ipynb`) is explicitly per-platform and should NOT be task-agnostic — each platform emits different column names, different exclusion conventions, and in some cases different metric definitions. The review standard for the notebook is therefore bug-correctness and alignment with field conventions, not agnosticism.

## Phase 0 — Bootstrap

**Prerequisites produced:** model upgrade committed, fresh `.env` in place, 1 `experiment_data.*` file per task available as reference for Phase 1 and Phase 2.

1. Change `src/experiment_bot/core/analyzer.py:68` from `model: str = "claude-opus-4-6"` to `model: str = "claude-opus-4-7"`. Commit message: `chore: upgrade Claude model to Opus 4.7`.
2. **User action:** copy `.env.example` to `.env` and populate `ANTHROPIC_API_KEY` from the Team MAX account. Claude cannot proceed past this point until confirmed.
3. Run `uv run experiment-bot <url> --label <label> --regenerate-config --headless` once per task (4 total). This:
   - exercises the new model on a fresh pilot validation loop for each experiment
   - writes 4 fresh `cache/{label}/config.json` files
   - produces `output/{task}/{timestamp}/experiment_data.*` files that serve as reference data for Phase 1 review and Phase 2 notebook audit

## Phase 1 — Code review and fixes

**Scope:** `src/experiment_bot/core/` (analyzer, cache, config, distributions, executor, phase_detection, pilot, scraper, stimulus), `src/experiment_bot/prompts/` (system.md, schema.json), `src/experiment_bot/navigation/`, and the pilot validation loop in `core/pilot.py` and its invocation in `cli.py`. Analysis scripts are explicitly excluded from the agnosticism review — they are per-platform by design.

**Agnosticism rubric:**

1. **Hardcoded condition strings.** `executor.py:318` (`"navigation"`) and `executor.py:326` (`"attention_check"`, `"attention_check_response"`) create a covert schema contract. Either remove the special cases and let them flow through standard stimulus handling, or surface the required condition names in `schema.json` + `system.md` so Claude reliably emits them.
2. **Hardcoded framework assumptions.** The system prompt advertises jsPsych / PsyToolkit / lab.js / Gorilla / custom HTML. Audit for jsPsych-only examples, selectors, or heuristics that would fail on the other platforms. Examples in the prompt should be platform-spanning.
3. **Behavioral defaults leaking into Python.** Audit every dataclass default in `config.py`. Non-zero timing values, non-empty key lists, or any field that influences behavior without being Claude-authored is a candidate for surfacing to the schema or justifying as structural.
4. **Schema/prompt coverage.** For each field the executor reads, confirm the schema requires Claude to populate it. Any Python fallback path is a platform-agnosticism crack.
5. **Pilot loop bias.** Does `pilot.py` assume stimulus counts, condition labels, block structures, or DOM selectors that would fail on a novel paradigm (flanker, n-back, task-switching)?
6. **Scraper coverage.** Does `scraper.py` correctly handle inline scripts, iframes, dynamic imports, and the non-jsPsych platforms? The 30KB-per-file cap matters for large task bundles — confirm it does not truncate critical trial definitions.
7. **Condition-name contracts.** `failure_rt_key`, `detection_condition`, and the `{condition}_correct` / `{condition}_error` resolution path in `executor._resolve_rt_distribution_key` all depend on Claude emitting specific string conventions. Confirm these are documented in `system.md`.

**Quality rubric (lighter pass):**

8. Dead code, unused parameters, unreachable branches.
9. Bare `except Exception: pass` around `page.evaluate()` calls in `executor.py`. Each should be narrowed or justified with a comment.
10. Test coverage for the agnosticism contract vs. only the 4 validated happy paths.

**Deliverable:** written review at `docs/superpowers/specs/2026-04-21-code-review-findings.md` with findings grouped by severity (Critical / Significant / Minor / Nit), plus inline fixes committed. Each Critical finding must be fixed before Phase 3. Significant findings fixed unless they require a design decision — flagged for user in that case.

## Phase 2 — Analysis notebook audit

**Scope:** `scripts/analysis.ipynb`.

**Standard:** per-platform correctness and alignment with field-standard metric definitions. Divergences from field standard are reported; the user supplies canonical references; Claude re-checks and fixes.

**Check list:**

1. **Exclusion filtering.** Human data: "all three exclusion columns equal 'Include'" is applied consistently. Bot data: no exclusion columns expected — confirm no bot rows are accidentally dropped.
2. **Per-platform column mapping.** For each of the 4 platforms, verify the correct columns are read for correctness, RT, condition, trial_type. Numeric columns cast to numeric before arithmetic.
3. **Trial-phase filtering.** Test trials only, practice/attention-check/feedback excluded. A recent commit (`ee27ee7`) already fixed a Figure 2 filtering bug — confirm the current filter is complete.
4. **Stop Signal SSRT (integration method).** `SSRT = nth_percentile(go_rt_distribution, p(respond|stop)) − mean(SSD)`. Compare against Verbruggen et al. 2019 consensus recommendations, including go-omission RT treatment.
5. **Go vs stop metrics.** `go_accuracy` excludes stop trials; `go_omission_rate` is fraction of go trials with no response; `mean_stop_failure_RT` restricted to stop trials with responses.
6. **Stroop metrics.** `congruent_rt` / `incongruent_rt` on correct trials only; accuracy on all responded test trials.
7. **Sequential effects (Figure 2).** Lag-1 autocorrelation and post-error slowing computed on consecutive valid-RT pairs only. No cross-block leakage. No practice-trial contamination. Confirm the `mean go RT > 2000 ms` exclusion is applied after RT cleaning, not before.
8. **Bot-CSV export schema.** `data/bot/stop_signal.csv` and `data/bot/stroop.csv` must match `data/human/*.csv` column-for-column.
9. **Execution.** Run the notebook end-to-end against the 4 Phase-0 smoke outputs. Fix any runtime errors.

**Iteration.** After findings are presented, the user shares canonical references (e.g., Verbruggen 2019 for SSRT, Rabbitt 1966 / Dutilh 2012 for post-error slowing) for any metric where the bot's numbers diverge from expectation. Claude re-checks, fixes, re-runs, reports.

**Deliverable:** findings appended to the same `2026-04-21-code-review-findings.md` document under an "Analysis notebook" section, plus inline fixes committed.

## Phase 3 — Batch run

**Command:** `bash scripts/batch_run.sh --count 15 --headless --regenerate`

- 4 tasks × 15 runs = 60 total, sequential, ~3s stagger between runs.
- `--regenerate` on first-of-each-task re-invokes Claude with any prompt/schema fixes from Phase 1. Remaining 14 runs per task reuse the fresh cache.
- Launched in the background so progress is visible; Claude reports on completion.
- After completion, user can re-run the notebook to see metrics on the full 60-run dataset.

**Exit criteria:**

- All 60 invocations returned.
- Failure count ≤ 6 (10%).
- Post-batch notebook re-run produces `data/bot/stop_signal.csv` and `data/bot/stroop.csv` with expected row counts (15 rows per platform per task where applicable).

If the failure rate exceeds 10%, stop and investigate before declaring the batch complete.

## Out of scope

- Agnosticism review of the analysis scripts themselves (they are intentionally per-platform).
- Performance optimizations beyond those incidentally required to make the pipeline correct.
- Adding new tasks or platforms to the validated set.
- Refactoring unrelated to agnosticism or analysis correctness.
- UI/visualization changes to the notebook beyond what Phase 2 bugs require.

## Risks

- **Smoke runs use pre-review code.** Phase 0 generates reference output before Phase 1 fixes land. If a Phase 1 fix changes output schema (unlikely — the review targets agnosticism, not output format), the smoke runs would need to be re-generated before Phase 2. Flagged at time of fix if this occurs.
- **Claude API quota.** Phase 0 (4 regenerations) + Phase 3 (4 regenerations) = 8 Claude calls on Opus 4.7. Should be well within Team MAX quota but worth noting.
- **Wall-clock time.** Phase 3 is sequential by user preference; 60 runs at multi-minute each will take several hours. Batch is long-running and should be kicked off in a background process.
- **Pilot loop failures.** If the new Opus 4.7 model produces configs that fail pilot validation, Phase 0 may stall. The pilot loop allows up to 2 refinements; beyond that, cached configs may be unvalidated, producing bad Phase 0 smoke data.
