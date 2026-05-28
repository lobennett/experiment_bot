# Defensibility Sweep (audit roadmap #1–3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Spec-compliance reviewer per task; SKIP code-quality reviewer (per `feedback_skip_code_quality_reviewer`). Tasks are SEQUENTIAL (heavy executor.py + oracle.py contention) — one implementer at a time, each commits before the next.

**Goal:** Close the data-integrity, honesty, and anti-circularity gaps surfaced by the design audit (`docs/design-audit-2026-05.md`), without touching the sound scientific core (oracle determinism, two-tier anti-circularity, generic-mechanism effects, behavioral generative model — all KEEP-AS-IS per the audit).

**Scope:** Roadmap items #1 (completeness/data-integrity), #2 (coherence/honesty), #3 (anti-circularity on held-out). All low/medium risk. Distribution-family fix uses PATH A (wire Claude's choice through — restores the leverage-Claude tenet) per owner direction.

**Source of truth for each fix:** the verifier-refined `fix_recommendation` in the audit findings (ids cited per task).

**Project guardrails (do not violate):** G2 (generic mechanisms, no paradigm vocabulary in bot library), G4 (anti-circularity, hard-fail on broken state, norms never tuned to results), G5 (doc+code agree in the same pass). Never re-add gating ranges to norms files as a retrofit.

---

## Task 1: Wire RT distribution family end-to-end (PATH A)

**Findings:** domgen-001, humanlike-003, arch-002, claude-002 (all the same issue).

**Files:**
- Modify: `src/experiment_bot/taskcard/types.py` (`ParameterValue`)
- Modify: `src/experiment_bot/core/executor.py` (`_taskcard_to_config`, ~line 54)
- Modify: `src/experiment_bot/reasoner/validate.py` (per-family param-key check — optional but recommended)
- Modify: `docs/scope-of-validity.md` (L4 — say families ARE honored)
- Test: `tests/test_taskcard_types.py` + a sampler-path test

**Why:** Stage 2 asks Claude to pick `ex_gaussian`/`lognormal`/`shifted_wald` per the literature, but `ParameterValue.from_dict` (types.py:46-55) drops the `distribution` field, and `_taskcard_to_config` (executor.py:54) hardcodes `ex_gaussian`. The LogNormal/ShiftedWald samplers (distributions.py:35-122) are unreachable, and a non-ex-Gaussian choice would crash with `KeyError` on `tau`. This is broken leverage on the project's central tenet.

- [ ] **Step 1: Failing test** — in `tests/test_taskcard_types.py`, assert `ParameterValue.from_dict({"value": {...}, "distribution": "lognormal"}).distribution == "lognormal"` and that a dict with no `distribution` key defaults to `"ex_gaussian"`. Add a test that a `shifted_wald` TaskCard drives `_taskcard_to_config` → `ResponseSampler` and instantiates `ShiftedWaldSampler` (not a KeyError). Run; expect FAIL.
- [ ] **Step 2:** Add `distribution: str = "ex_gaussian"` field to `ParameterValue`; read via `d.get("distribution", "ex_gaussian")` in `from_dict`; emit in `to_dict`. (Backward-compatible with the 18 existing ex_gaussian cards.)
- [ ] **Step 3:** In `_taskcard_to_config` (executor.py:54), build `DistributionConfig(distribution=v.distribution, params={k: val for k, val in v.value.items() if k != "distribution"})`. (Guard: `v.value` should not contain `distribution`; it lives on the ParameterValue now.)
- [ ] **Step 4:** In `reasoner/validate.py`, when validating Stage 2 `response_distributions`, check the param-key set matches the declared family (ex_gaussian→{mu,sigma,tau}; lognormal→{mu,sigma}; shifted_wald→{drift_rate,boundary,shift_ms} — confirm exact keys against `distributions.py`). A mismatch fails loudly at Stage 2, not mid-session. (If the param-key sets are uncertain, read distributions.py to confirm before writing the check.)
- [ ] **Step 5:** Update `docs/scope-of-validity.md` L4 + the `distributions.py` docstring (lines ~42-44) to state all three families are selectable and honored end-to-end.
- [ ] **Step 6:** Run `uv run pytest -x -q`; commit.

```
feat(defense): wire RT distribution family end-to-end (honor Claude's choice)

ParameterValue gains a `distribution` field (default ex_gaussian, backward-
compatible); _taskcard_to_config uses it instead of hardcoding ex_gaussian;
Stage 2 validation checks param-keys match the declared family. Restores the
leverage-claude tenet (Claude picks the RT family from the literature and the
runtime honors it) and removes the latent KeyError crash on non-ex-Gaussian
choices. Audit: domgen-001/humanlike-003/arch-002/claude-002.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 2: Executor completeness instrumentation

**Findings:** robust-001 (PART 1), robust-002, robust-008.

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (`_trial_loop`, `run` metadata block)
- Modify: `src/experiment_bot/core/phase_detection.py` (`detect_phase`)
- Test: `tests/test_executor_adaptive_nav.py` or a new `tests/test_executor_completeness.py`

**Why:** G4's "hard-fail on broken state" is ONLY a `trial_count == 0` check (executor.py:563-573). Early-break branches (window_closed at ~757, max_misses at ~774) produce a NONZERO partial session that exits 0 and is scored as whole — the 61-vs-124 Stroop run is a real prior occurrence.

- [ ] **Step 1: Failing test** — construct an executor, drive `_trial_loop` to a max-misses break (mock page so stimulus never matches), assert `self._loop_exit_reason == "max_misses"` and that the run_metadata produced sets `incomplete=True`. A natural COMPLETE sets `incomplete=False`. Run; expect FAIL.
- [ ] **Step 2:** Add `self._loop_exit_reason = "complete"` default in `_trial_loop` init. Set the enum at each break: `"complete"` at the COMPLETE branch (~677), `"window_closed"` at the response-window-too-long break (~757), `"max_misses"` at the too-many-misses break (~774). If an adaptive-nav budget break exists, `"budget"`.
- [ ] **Step 3:** In `detect_phase` (phase_detection.py:29-31), on exception during predicate eval, do ONE short settle (e.g. `await asyncio.sleep(0.25)`) + single re-eval before falling back to COMPLETE. Distinguish the outcome: return/record whether COMPLETE came from the predicate being true vs a context-destroyed exception. Plumb a `context_destroyed` exit-reason into the trial loop when COMPLETE was exception-derived. (Keep it lightweight — do NOT add a stimulus-reappearance confirmation poll; the verifier marked that low-value.)
- [ ] **Step 4:** In the `run` finally/metadata block (~591-622), persist `metadata["loop_exit_reason"] = self._loop_exit_reason` and `metadata["incomplete"] = (self._loop_exit_reason != "complete")`. Also record into the `trial_loop` run_trace stage. Keep the existing `== 0` hard-fail unchanged. Do NOT hard-raise on early break.
- [ ] **Step 5 (robust-008):** If `self._adaptive_nav_uses > 0` AND `self._loop_exit_reason != "complete"`, ensure `incomplete=True` (already covered by step 4, but add a comment + a `suspect_adaptive_nav` boolean in run_metadata when adaptive nav ran and the loop did not complete naturally).
- [ ] **Step 6:** Run `uv run pytest -x -q`; commit.

```
feat(defense): trial-loop exit-reason enum + run_metadata.incomplete (G4)

_trial_loop records loop_exit_reason (complete/window_closed/max_misses/
budget/context_destroyed) at each break; detect_phase does one settle+re-eval
before treating an exception as COMPLETE and distinguishes context-destroyed
completion. run_metadata gains loop_exit_reason + incomplete so a nonzero
partial session is no longer indistinguishable from a whole one. Keeps the
==0 hard-fail; does NOT hard-raise on early break (held-out exploration).
Audit: robust-001(p1)/robust-002/robust-008.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 3: Executor JS-eval error counter + narrowed key excepts

**Findings:** robust-005.

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Test: same completeness test file

**Why:** ~18 broad `except Exception` blocks all commented "Page context may be torn down by navigation" but catching everything — a malformed Reasoner-emitted `response_key_js` silently resolves to None (treated as withhold) with only a WARNING. A real config bug is indistinguishable from a benign teardown race.

- [ ] **Step 1: Failing test** — mock `page.evaluate` for `response_key_js` to raise a non-Playwright `ValueError`; assert run_metadata's `js_eval_errors_by_source` records it under a `response_key_js` key with count ≥1. Run; expect FAIL.
- [ ] **Step 2:** Add `self._js_eval_errors: dict[str,int] = {}` init. For the HIGH-VALUE eval sites — `response_key_js` (executor.py:374-376, 388-390) and `response_window_js` (762-764) — catch `playwright.async_api.Error` as the benign teardown branch; for any OTHER exception, log at WARNING with a stable greppable tag (e.g. `[js_eval_error:response_key_js]`) and increment `self._js_eval_errors["response_key_js"]`. (Do NOT attempt to narrow all 18 sites — scope to these two highest-value ones; full narrowing is deferred to the architecture pass.)
- [ ] **Step 3:** Persist `metadata["js_eval_errors_by_source"] = dict(self._js_eval_errors)` in the metadata block.
- [ ] **Step 4:** Run `uv run pytest -x -q`; commit.

```
feat(defense): js-eval error counter + narrow response_key/window excepts

Narrows the two highest-value broad excepts (response_key_js, response_window_js)
to treat only Playwright teardown errors as benign; any other exception is
WARNING-logged with a greppable tag and counted into run_metadata
js_eval_errors_by_source, so a malformed Reasoner-emitted JS expression is
visible to the reviewer instead of silently degrading to chance keys.
Audit: robust-005.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 4: Error-injection honesty

**Findings:** robust-003.

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (`_pick_wrong_key` ~422-434, call site ~1176-1193)
- Test: completeness test file

**Why:** `_pick_wrong_key` returns the CORRECT key when no wrong key is available (single-real-key paradigm — a documented SP7/SP8 reality), but the trial is still LOGGED `intended_error=True`. The platform records a correct response; bot_log claims an error. This desyncs the two data sources and corrupts the bot_log-fallback `correct` derivation + PES trigger.

- [ ] **Step 1: Failing test** — call `_pick_wrong_key` with a key_map that has only one real key; assert it signals failure (returns `None` or a `(key, failed)` tuple — implementer picks one and is consistent). At the call site, when injection fails, `is_error` is forced False before logging so `intended_error`/`response_key`/`_recent_errors` all reflect the correct key actually pressed. Assert `run_metadata["error_injection"]["unrealizable_count"]` increments. Run; expect FAIL.
- [ ] **Step 2:** Change `_pick_wrong_key` to signal unrealizable (return `None`). At the call site (~1176): `wrong = self._pick_wrong_key(resolved_key); if wrong is None: is_error = False  # cannot inject; press correct key honestly` else use `wrong`. Increment `self._error_injection_unrealizable += 1` when None.
- [ ] **Step 3:** Persist `metadata["error_injection"] = {"unrealizable_count": self._error_injection_unrealizable}`.
- [ ] **Step 4:** Run `uv run pytest -x -q`; commit.

```
feat(defense): honest error-injection when no wrong key is available

_pick_wrong_key now signals unrealizable (returns None) instead of silently
returning the correct key while the trial is logged intended_error=True. The
call site forces is_error=False so bot_log matches the key actually pressed,
eliminating the log/behavior desync that corrupted bot_log-fallback accuracy +
the PES trigger. run_metadata.error_injection.unrealizable_count surfaces
single-real-key paradigms. Audit: robust-003.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 5: Oracle completeness exclusion + tri-state overall_pass + bot_log-fallback correctness guard

**Findings:** robust-001 (PART 2), defensibility-002, genbottle-005, humanlike-007, domgen-003, defensibility-004 (correctness-metric part).

**Files:**
- Modify: `src/experiment_bot/validation/oracle.py` (`validate_session_set`, `ValidationReport`)
- Modify: `src/experiment_bot/validation/cli.py` (tri-state print + report JSON)
- Test: `tests/test_*oracle*` (find the oracle test file; audit referenced `test_validation_oracle.py:110`)

**Why:** (a) the oracle has no completeness gate — it aggregates over whatever was captured; (b) `has_any_gate==False → overall=False` makes the all-descriptive working_memory class structurally unable to pass (a perfectly humanlike n-back reports FAIL); (c) on bot_log fallback, correctness-dependent metrics gate on the bot's self-graded `correct`.

- [ ] **Step 1: Failing tests** — (i) a session set where one session's `run_metadata.incomplete==True` → that session is EXCLUDED from aggregation and listed in `report.excluded_sessions` with reason; report exposes `n_used` vs `n_supplied`. (ii) an all-descriptive (all-null-range) norms file with descriptive data present → `overall_pass is None` (not False); a gated class with zero/empty data → still `False`. (iii) when the loader is the bot_log fallback, `post_error_slowing` (correctness-dependent) has `pass_ is None`. Run; expect FAIL.
- [ ] **Step 2 (completeness):** `validate_session_set` reads each `session_dir/run_metadata.json`; if `incomplete` is True, exclude that dir from `session_dirs` passed to metric compute, and append `{dir, reason: loop_exit_reason}` to a new `ValidationReport.excluded_sessions` list. Add `n_supplied` and `n_used` to the report. If ALL sessions are incomplete → `overall_pass=False` (hard "could not gate").
- [ ] **Step 3 (tri-state):** Change `ValidationReport.overall_pass` annotation to `bool | None`. At oracle.py:405-406: return `None` ONLY when `has_any_gate is False` AND at least one metric produced a non-None `bot_value` (descriptive data exists, nothing gates). Keep `False` when no metric produced any value (zero-trial/empty) — preserves the broken-state signal. Update the `summary` string accordingly.
- [ ] **Step 4 (bot_log correctness guard):** Thread a flag indicating the loader is `_default_bot_log_loader` (the CLI knows this — pass `trial_source` into `validate_session_set`, default `"platform_adapter"`). When `trial_source == "bot_log"`, set `pass_=None` for any metric whose compute reads `correct` (i.e. `post_error_slowing`) so the self-graded correctness can never gate. (Identify correctness-dependent metrics by inspecting METRIC_REGISTRY; the audit says only `post_error_slowing` reads `correct`. Verify.) Record `data_source` on the report.
- [ ] **Step 5 (cli):** In `validation/cli.py`, print `Overall pass: unscored (no gating metric — descriptive-only class)` when `overall_pass is None`; add `excluded_sessions`, `n_used`, `n_supplied`, `data_source` to the written report JSON.
- [ ] **Step 6:** Update the existing oracle test that asserts the old False behavior (audit cited `test_validation_oracle.py:110`); run `uv run pytest -x -q`; commit.

```
feat(defense): oracle excludes incomplete sessions; tri-state overall_pass; bot_log correctness guard

validate_session_set now (1) reads run_metadata.incomplete and EXCLUDES partial
sessions from aggregation, recording them in ValidationReport.excluded_sessions
with n_used vs n_supplied; (2) returns overall_pass=None (not False) for an
all-descriptive class with data present, so a humanlike working_memory/n-back
session is honestly "unscored" rather than structurally failed (keeps False for
zero-data); (3) marks correctness-dependent metrics (post_error_slowing) pass_=
None when scoring off the bot_log self-graded `correct`. CLI prints the tri-state
and records data_source. Audit: robust-001(p2)/defensibility-002/genbottle-005/
humanlike-007/domgen-003/defensibility-004.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 6: Validation-CLI anti-circularity gate + data-capture visibility

**Findings:** robust-004 (PART 1), platform-004, defensibility-004 (marker part).

**Files:**
- Modify: `src/experiment_bot/validation/cli.py`
- Modify: `src/experiment_bot/output/data_capture.py` (distinguish no-method vs exception)
- Modify: `src/experiment_bot/core/executor.py` (`_wait_for_completion` records data_capture status)
- Test: `tests/test_platform_adapters.py` or cli/data_capture test

**Why:** When no platform adapter is registered (the DEFAULT for any held-out paradigm), the CLI soft-warns (stderr only) and scores against bot_log — the bot grades its own homework on exactly the case that matters most. And `data_capture.capture` swallows ALL exceptions to None, so the authoritative export can be silently absent.

- [ ] **Step 1: Failing test** — invoke the validation CLI path (or its adapter-resolution helper) for an unregistered label WITHOUT `--allow-bot-log` → raises `click.ClickException` naming the circularity. WITH `--allow-bot-log` → proceeds, and the written report JSON has `"trial_source": "bot_log_self_graded"`. Run; expect FAIL.
- [ ] **Step 2:** In `validation/cli.py`, when `adapter_for_label(label)` is None: if `--allow-bot-log` not set, raise `click.ClickException` pointing at `platform_adapters.py` / TaskCard `data_capture`, explicitly naming the bot-grades-itself circularity. If set, proceed with the bot_log loader, pass `trial_source="bot_log"` to `validate_session_set`, and stamp the report JSON `"trial_source": "bot_log_self_graded"`.
- [ ] **Step 3:** Add the `--allow-bot-log` flag to the validate command (default False).
- [ ] **Step 4 (data_capture):** Make `ConfigDrivenCapture.capture` distinguish "no method configured" (return None, no error) from a swallowed exception (catch, log WARNING, set a failure flag). In `executor._wait_for_completion`, record `metadata["data_capture"] = {"written": bool(data), "method": <method>, "failed": <bool>}`.
- [ ] **Step 5:** Run `uv run pytest -x -q`; commit.

```
feat(defense): hard-gate missing platform adapter; surface data-capture status

A gating validation run with no registered platform adapter now HARD-FAILS with
a ClickException naming the bot-grades-its-own-homework circularity, unless
--allow-bot-log is passed (which stamps the report trial_source=
bot_log_self_graded so the bypass is recorded in the committed artifact, not a
transient stderr line). data_capture distinguishes no-method-configured from a
swallowed exception, and the executor records data_capture {written,method,
failed} so a silent capture failure is visible. Audit: robust-004(p1)/platform-004/defensibility-004.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 7: Provenance hashes + single model id + Stage-4 hardening + doc coherence

**Findings:** arch-007, claude-005 (hashes+model only — defer --model flag/caching), defensibility-006, + the doc fixes for defensibility-002/domgen-003 (working_memory §5) and L4 (distribution, done in Task 1) and scope circularity note.

**Files:**
- Modify: `src/experiment_bot/reasoner/cli.py` (`_wrap_for_taskcard` ~80-87)
- Modify: `src/experiment_bot/llm/protocol.py` (add `model` to the Protocol), `llm/cli_client.py`, `llm/api_client.py` (expose `model`), and a single `DEFAULT_MODEL` constant
- Modify: `src/experiment_bot/reasoner/stage4_doi_verify.py` (`.get()` + surface counts)
- Modify: `docs/scope-of-validity.md` (§5 working_memory; circularity note; model)
- Modify: `docs/heldout-nback-test.md` (correct the gating-range parenthetical)
- Test: `tests/test_reasoner_openalex.py` / stage4 test for malformed citation

**Why:** Provenance hashes ship empty and model id is a stale hardcoded `claude-opus-4-7` across 5 sites (harness runs opus-4-8) — `produced_by` can attribute a card to a model that never produced it, weakening the G4 paper trail. Stage 4 `.get()` crash on malformed citations. Docs advertise working_memory gates + a reproducibility claim that no longer hold.

- [ ] **Step 1: Failing tests** — (i) Stage 4 with a citation missing `doi`/`authors`/`year` does NOT raise KeyError (skips it, counts it). (ii) `_wrap_for_taskcard` produces non-empty `prompt_sha256` and `source_sha256`. (iii) a single `DEFAULT_MODEL` constant exists and `produced_by.model` is sourced from it / the live client, not a literal. Run; expect FAIL.
- [ ] **Step 2:** Add a `DEFAULT_MODEL` constant (one module, e.g. `llm/factory.py` or a small `llm/models.py`), sourced from an env var defaulting to the current model id (`claude-opus-4-8`). Point cli_client, api_client, reasoner/cli produced_by, and norms_extractor at it. Add a `model` property to the `LLMClient` Protocol and implement on both clients; `_wrap_for_taskcard` records the client's actual model.
- [ ] **Step 3:** In `_wrap_for_taskcard`, populate `prompt_sha256` (sha256 of the concatenated system+user prompt, or the system prompt if the user prompt isn't threaded here — implementer picks the most faithful available input) and `source_sha256` (sha256 of the SourceBundle). If the wrap path lacks access to these, thread them minimally from the pipeline.
- [ ] **Step 4:** In `stage4_doi_verify.py`, use `cit.get("doi")`, `cit.get("authors")`, `cit.get("year")` and skip/flag malformed citations rather than indexing; surface a `doi_verified` count in the ReasoningStep / provenance summary.
- [ ] **Step 5 (docs):** `docs/scope-of-validity.md` §5 — rewrite the working_memory bullet to state it currently declares ONLY descriptive-only metrics (no gating), remove the `n_back_accuracy_2back`/`capacity_k` claim, note they were trimmed (ref commit ecf07ea) pending a compute path. Add a circularity note (bot_log fallback is descriptive-only + requires `--allow-bot-log`). Correct the stale reproducibility claim (SP16 adaptive-nav sessions are not seed-reproducible). Fix `docs/heldout-nback-test.md` gating-range parenthetical. (The L4 distribution-family doc line was handled in Task 1.)
- [ ] **Step 6:** Run `uv run pytest -x -q`; commit.

```
feat(defense): real provenance hashes + single model id + Stage-4 hardening + doc coherence

produced_by now records real prompt_sha256/source_sha256 and the live client's
actual model via a single DEFAULT_MODEL constant + LLMClient.model property
(was stale hardcoded claude-opus-4-7 across 5 sites). Stage 4 uses .get() so a
malformed citation no longer crashes the pipeline, and surfaces doi_verified
counts. scope-of-validity §5 corrected to state working_memory has no gating
metrics (not the fictional n_back_accuracy/capacity_k), plus circularity +
reproducibility notes. Audit: arch-007/claude-005/defensibility-006/defensibility-002(doc).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Self-review

- **Coverage:** every finding in roadmap #1–3 maps to a task: completeness (T2,T5), js-eval (T3), error-injection (T4), distribution family (T1), working_memory tri-state (T5), anti-circularity gate (T6), provenance/model/stage4 (T7), docs (T1,T7). ✓
- **Sequencing:** T1→T2→T3→T4 (executor changes serialized), T5→T6 (oracle/cli serialized), T7 (reasoner/docs). Each commits before the next.
- **No scope creep:** deferred per audit — full except-narrowing (T3 does 2 sites only), `--model` flag + prompt caching (claude-005 enhancements), contract-drift cleanup (roadmap #4), god-class split (#8), navigation redesign (#7). Stated in each task.
- **Guardrails:** no norms-file gating ranges added; oracle stays Claude-free; generic mechanisms untouched; doc+code aligned per task (G5).

## Handoff

Execute via subagent-driven-development, spec-compliance reviewer per task, skip code-quality reviewer. After all 7 land + full suite green, run a dev-paradigm smoke (expfactory_stroop) to confirm no executor regression, then summarize for the owner.
