# SP12 hardcoded-paradigm findings

This doc accumulates findings during the SP12 top-down walk. Each
section corresponds to a module; bullets within name a specific
hardcoded value, paradigm-specific assumption, or fragile coupling.
Findings inform whether the framework's generalizability claim
holds under scrutiny.

## Surviving scripts

(none — `audit_alignment.py` and `analyze_sessions.py` carry no
paradigm-specific values beyond the platform_adapters dispatch,
which is itself the generic mechanism for paradigm-awareness.)

## src/experiment_bot/cli.py

(no paradigm-specific values; CLI is paradigm-agnostic — `--label` routes
to whatever TaskCard exists for that label, and the rest of the CLI
contains no Stroop/stop_signal/jsPsych names.)

## src/experiment_bot/core/executor.py

Walked top-to-bottom under SP12 Task 4. Findings:

### Soft defaults / fallback literals (acceptable; configurable via TaskCard)

- **Default navigation-condition label** is the literal string
  `"navigation"` (executor.py:121). Used only when
  `runtime.navigation_stimulus_condition` is empty. This is a
  back-compat default; configurable.
- **Default attention-check conditions** are the literal strings
  `"attention_check"` and `"attention_check_response"`
  (executor.py:123–125). Used only when
  `runtime.attention_check.stimulus_conditions` is empty list.
  Back-compat default; configurable.
- **Default response key fallback** is `" "` (Space) in calibration
  when `_seen_response_keys` is empty (executor.py:~172). A reasonable
  ASCII default; paradigm-agnostic.
- **Sentinel strings** `"dynamic_mapping"` / `"dynamic"` appear in
  three places in `_resolve_response_key` and `_pick_wrong_key`
  (executor.py:393, 401, 436, 469). These are framework-level
  contract values written by the Reasoner to mean "fall through to
  the next resolution layer", not paradigm names.
- **Withhold sentinel set** (executor.py:344–348) is paradigm-agnostic
  ("", "none", "null", "withhold", "no_response", …) and tokenizes on
  non-word characters; documented to not match real Playwright key
  names.

### Default-on `is_correct` resolver fallback (potential silent failure)

- `_resolve_rt_distribution_key` (executor.py:505) falls back to
  `next(iter(dists))` when neither a `{condition}_correct/error`
  variant nor a direct match exists. For tasks whose condition labels
  don't appear in `response_distributions` at all, this silently
  samples from an arbitrary first distribution rather than raising.
  Not paradigm-specific, but worth surfacing — a malformed TaskCard
  can produce plausible-looking RTs from the wrong condition.

### Magic numbers / heuristics

- **Recent-errors deque maxlen=8** (executor.py:106). PES handler
  currently reads only index 0; the maxlen is reserved for "future
  multi-trial decay mechanism" per inline comment. Worth pruning
  if no current mechanism uses indices >0.
- **`_wait_for_response_window` timeout = 5.0 s** hard-coded
  (executor.py:1004). Other timing values flow through
  `runtime.timing.*`; this one bypasses config.
- **`is_visible(timeout=200)` and `click(timeout=500)`** in advance
  selector retry (executor.py:~714–715) are hard-coded ms.
- **Inter-fallback-key `asyncio.sleep(0.5)`** between exit-pager
  presses (executor.py:722) and between feedback-fallback keys
  (executor.py:1268) — hard-coded.
- **Stimulus-skip wait `asyncio.sleep(0.05)`** for non-trial stimuli
  (executor.py:745) — hard-coded.

### `response_window_js` contract is load-bearing

The executor relies on `runtime.timing.response_window_js` returning a
JS-evaluable expression for two distinct purposes:
1. **Gating stimulus detection** in `_trial_loop` (executor.py:660–683)
   to avoid re-detecting stale globals during fixation.
2. **Waiting for trial end** in `_wait_for_trial_end`
   (executor.py:808–837) to avoid double-firing.

When `response_window_js` is absent, `_wait_for_trial_end` falls back
to `_stimulus_detection_js(stim)`. This SP6 fallback is the only
guard against the over-firing failure mode. Worth documenting as a
TaskCard schema contract.

### `task_specific.trial_timing.max_response_time_ms` is read in two places

Executor reads `self._config.task_specific.get("trial_timing", {}).get(
"max_response_time_ms")` (executor.py:1099, 1141). This is the only
remaining read of an arbitrary `task_specific` substructure key by
the executor. It's framework-level (any speeded task could declare
this), not paradigm-specific, but the path is implicit rather than a
typed RuntimeConfig field. Candidate for promotion to
`runtime.timing.max_response_ms`.

### `_pick_wrong_key` requires ≥2 known keys

`_pick_wrong_key` returns `correct_key` (i.e., DOES NOT flip) when
only one real key exists in `_key_map` or `_seen_response_keys`
(executor.py:474–476). For paradigms with a single-key go response
(e.g., go/no-go where the only "go" key is Space), intended-error
trials silently behave as correct trials. Not necessarily wrong —
the design is to fail closed — but it's a hidden contract worth
documenting.

### Removed in SP12 Task 4 (architectural audit follow-up)

Two items the executor walk surfaced as architectural candidates have
been removed:

- **SP9a SessionAgent runtime LLM call.** The session-time LLM
  key-mapping resolver did not improve fidelity on any of the four
  paradigms it was evaluated against (CLAUDE.md SP9a entry: n-back
  smoke 68.1% vs SP8 72.1%, stroop x3 32.2% vs SP8 28.9%, stop_signal
  silently never fired due to schema mismatch). Net contribution to
  fidelity: zero. Removed: `_invoke_session_agent`,
  `_runtime_key_mapping` and `_session_agent_directive` instance
  fields, the priority-0 branch in `_resolve_response_key`, the
  `_KEY_ALIASES`/`_normalize_key` English-word normalization layer,
  the `session_agent=` constructor parameter and `_session_agent`
  storage, the `agent/` package (SessionAgent, page_probe,
  KeyMappingDirective), the `_build_session_agent` wiring in cli.py,
  and the `runtime.session_agent_enabled` config field. Tests
  removed: `tests/test_session_agent.py`,
  `tests/test_executor_session_agent_integration.py`, and the two
  `test_cli_*session_agent*` tests in `tests/test_cli.py`, plus the
  three `test_runtime_config_session_agent_enabled_*` tests in
  `tests/test_config.py`.

- **SP7 keypress diagnostic.** The per-trial page-keydown drain and
  the four diagnostic fields it appended to each trial entry
  (`resolved_key_pre_error`, `page_received_keys`, `keypress_received`,
  `keyup_received`) had zero production read consumers; the
  associated tests were self-referential. Removed:
  `_install_keydown_listener`, `_drain_keydown_log`, and
  `_log_trial_with_keypress_diag`; the call sites in `run()` and
  `_execute_trial`. Per-trial logging now goes straight through
  `writer.log_trial`. Tests removed:
  `tests/test_executor_keypress_diagnostic.py`.

## src/experiment_bot/core/config.py

Walked top-to-bottom under SP12 Task 5. Findings:

### Soft defaults / fallback literals (acceptable; configurable via TaskCard)

- **`AttentionCheckConfig.stimulus_conditions` default** is
  `["attention_check", "attention_check_response"]` (config.py:699–701).
  Back-compat default so legacy configs without this field still work;
  configurable.
- **`RuntimeConfig.navigation_stimulus_condition` default** is `""`;
  empty triggers the executor's legacy hardcoded `"navigation"` label
  (config.py:726). Back-compat default; configurable.
- **`RuntimeConfig.delivery_channel` default** is `"cdp"`
  (config.py:734). Framework-level — `"cdp"`, `"keyboard"`, `"none"`
  are bot-mechanic identifiers, not paradigm names.
- **`AdvanceBehaviorConfig.feedback_selectors` default** is `["button"]`
  (config.py:649). A generic HTML-element selector, not
  paradigm-specific; configurable.
- **`TimingConfig.viewport` default** is
  `{"width": 1280, "height": 800}` (config.py:624). A standard desktop
  size; paradigm-agnostic.

### Magic numbers in TimingConfig defaults

All TimingConfig timing defaults are bot-mechanic values, not
paradigm-specific — but several are unconfigured in current TaskCards
so they act as de facto framework constants:

- `poll_interval_ms = 20` (config.py:614)
- `max_no_stimulus_polls = 500` (config.py:615)
- `stuck_timeout_s = 10.0` (config.py:616)
- `completion_wait_ms = 5000` (config.py:617)
- `feedback_delay_ms = 2000` (config.py:618)
- `omission_wait_ms = 2000` (config.py:619)
- `rt_floor_ms = 150.0` (config.py:620) — minimum bot RT floor
- `rt_cap_fraction = 0.90` (config.py:621) — fraction of max RT cap
- `navigation_delay_ms = 1000` (config.py:626)
- `attention_check_delay_ms = 1500` (config.py:627)
- `completion_settle_ms = 2000` (config.py:628)
- `trial_end_timeout_s = 5.0` (config.py:629)
- `cdp_dwell_ms = 200.0` (config.py:631)
- `calibration_n_keys = 30` (config.py:739, RuntimeConfig) — number
  of calibration keypresses

### Practice-effect defaults are bot-library mechanic values

`PracticeEffectConfig` defaults (config.py:264–269):
- `asymptote_block = 3`
- `trials_per_block = 30`
- `decay_rate = 0.7`

These are the exponential-decay mechanism's defaults when enabled;
the Reasoner emits paradigm-specific values from literature when the
mechanism is on. Disabled-by-default contributes zero.

### BetweenSubjectJitter clip-range defaults

- `accuracy_clip_range = [0.60, 0.995]` (config.py:455)
- `omission_clip_range = [0.0, 0.04]` (config.py:456)

The inline comment notes these "reflect typical conflict/interrupt-
task ranges" and that "the Reasoner should override these per
paradigm class". This is a soft default tuned to dev paradigms;
configurable, but the default carries dev-paradigm assumptions. G3-
adjacent (defaults assume a paradigm class) — worth surfacing.

### PilotConfig defaults assume short-block paradigms

- `min_trials = 20` (config.py:469)
- `max_blocks = 3` (config.py:475) — "covers paradigms with a
  single-trial practice block followed by feedback"

Documented soft defaults; per-paradigm override expected.

### Deprecated dataclasses kept for back-compat

- **`ConditionRepetitionConfig`** (config.py:146–179): docstring
  declares it "Deprecated in SP11 Phase 2" in favor of
  `lag1_pair_modulation`. Fires a once-per-process stderr deprecation
  when `enabled=True`. Among current TaskCards, only
  `expfactory_flanker/2e7fe980.json` still has `enabled=True`; the
  other 10 have it disabled. Removing the dataclass would also
  remove the `condition_repetition` effect-registry entry and
  `apply_condition_repetition` handler — architectural decision.
- **`PinkNoiseConfig.hurst` legacy field**: handled via from_dict
  conversion (config.py:333–359). Fires once-per-process stderr
  deprecation; 6 of 11 current TaskCards still emit `hurst` (no card
  emits `alpha` directly). Removing the alias would require
  regenerating those 6 TaskCards.

### Removed in SP12 Task 5

- **`RuntimeConfig.calibration_run_pass`** — Task 3 removed the
  `--no-calibration` CLI flag that set it; the only remaining
  consumer was the test escape hatch
  `test_run_calibration_pass_skips_when_run_pass_false`. Per G5,
  field + executor branch + test removed; `_run_calibration_pass`
  now always runs when a deliverer is configured.
- **`RuntimeConfig.calibration_apply_to_sampler`** — Task 4 removed
  the executor branching that read it; the field was only consumed
  by config round-trip tests. Removed from the dataclass and tests.
  Result is now always installed on the sampler.

## src/experiment_bot/calibration/

Walked under SP12 Task 6. Findings:

### Removed (no remaining production consumers)

- **`drop_from_scope.py` + `test_drop_from_scope.py`** — Task 3 removed
  the CLI guard that read `task_specific.sp11_supported`. The
  `PilotVerdict` / `pilot_with_retry` / `mark_taskcard_unsupported` /
  `append_unsupported_note` machinery had zero remaining callers in
  src/, tests/, or scripts/. Net -152 LOC source + the dedicated test
  file.

- **`keyboard_deliverer.py` + `test_keyboard_deliverer.py`** — All 5
  production TaskCards set `runtime.delivery_channel = "cdp"`. Nothing
  in production sets `"keyboard"`. The `elif channel == "keyboard":`
  branch in `TaskExecutor._setup_keypress_deliverer` was dead code.
  Removed the branch + the deliverer file. The
  `RuntimeConfig.delivery_channel` field is preserved with `"cdp"` as
  the default and `"none"` as the legacy-flow escape hatch; passing
  any other value now logs `Unknown delivery_channel=` and falls
  through to `page.keyboard.press`.

- **`focus.py`** — Defined three paradigm-agnostic JS focus helpers
  (`JSPSYCH_DISPLAY_FOCUS_JS`, `BODY_FOCUS_JS`, `IFRAME_CONTENT_FOCUS_JS`)
  but no caller anywhere in src/, tests/, scripts/, or taskcards/
  imported them or passed their values via `listener_focus_js=`. The
  `CDPDeliverer` accepted `listener_focus_js: str | None = None` as a
  constructor kwarg that was always `None` in production. Removed
  the JS-string module, the constructor kwarg, the
  `_focus_listener_target` helper, and the two
  `test_deliver_at_trial_start_runs_focus*` tests in
  `test_cdp_deliverer.py`.

### Architectural candidates surfaced (no auto-removal)

- **`estimator.py` `regression` model branch.** Surveyed every
  `run_metadata.json` under `output/` (658 files). All of them report
  `model: too_few_events`; none report `fixed_offset`, `regression`,
  or `escalate`. The `regression` and `escalate` branches in
  `estimate_calibration` have never fired in a real production
  session. Possible reasons: every session pairs fewer than the
  estimator's 5-event minimum (suggests `_summarize_delivery_channels`
  or the gate-dismisser is dropping events upstream), OR the SD-based
  trigger thresholds need recalibration. Either way, `regression` is
  dormant code. Controller decision: keep (defensive), tighten the
  trigger thresholds, or remove the branch.

- **`KEY_TO_CDP_FIELDS` table coverage.** The dict in
  `cdp_deliverer.py:42-69` has 27 explicit entries. Across all
  current TaskCards the only static response-key values that resolve
  to this table are: `" "`, `"ArrowLeft"`, `"ArrowRight"`, `"Enter"`,
  and the single letters `b`, `g`, `r`, `y` (which fall through the
  alphabetic fallback, not the table). Unused-by-current-paradigms
  table entries: `,`, `.`, `/`, all digits 0-9, `Space` (string
  literal — the executor only ever passes `" "`), `ArrowUp`,
  `ArrowDown`, `Escape`, `Tab`, `Backspace`. Defensive value (a novel
  paradigm using `1234` for n-back or `,/.` for Stroop would hit the
  table). Controller decision: keep as-is (defensive coverage) vs
  prune to current paradigms.

### LOC delta

calibration/ before: 1588 LOC across 9 files.
calibration/ after: 1145 LOC across 7 files (drop_from_scope.py,
keyboard_deliverer.py, focus.py removed; cdp_deliverer.py trimmed by
the focus path).

## src/experiment_bot/output/writer.py

Walked under SP12 Task 7. Findings:

### Soft defaults / fallback literals (acceptable; configurable)

- **`DEFAULT_OUTPUT_DIR`** is `<repo>/output` (writer.py:13). Overridable
  via the `EXPERIMENT_BOT_OUTPUT_DIR` env var, which the SP11 Phase 7
  sweep wrapper uses to route per-arm sessions into per-arm subtrees.
  Framework-level; no paradigm-specific value.
- **Timestamp microsecond suffix** in `create_run` (writer.py:37):
  `"%Y-%m-%d_%H-%M-%S-%f"`. Inline comment notes the microsecond field
  exists to prevent concurrent-run directory collisions; framework-
  level, paradigm-agnostic.

### Method signature contract

- `save_task_data(data, filename)` — both args required at every call
  site (executor passes `f"experiment_data.{ext}"`, tests pass explicit
  CSV/TSV names). The legacy `filename: str = "task_data.csv"` default
  had zero readers across src/, tests/, and scripts/ — removed in this
  walk so the call signature reflects the actual contract.

### No paradigm-specific values

The writer has no paradigm-named strings, no Stroop/stop_signal/n-back
references, and no jsPsych-specific output knobs. File-name constants
(`bot_log.json`, `run_metadata.json`, `config.json`, `screenshots/`)
are framework-level contract values consumed by the validation oracle
and audit scripts via the platform_adapters dispatch.

### Removed in SP12 Task 7

- **`save_task_data` default `filename="task_data.csv"`.** No caller
  relied on the default — executor explicitly passes
  `f"experiment_data.{ext}"` and both `test_save_task_data_*` tests
  pass an explicit extension. Default removed; argument now required.

## src/experiment_bot/core/distributions.py

Walked under SP12 Task 8. Findings:

### Hardcoded family names (acceptable; data-driven dispatch)

- **`_build_sampler` family dispatch** (distributions.py:107-122) lists
  the three supported distribution families: `"ex_gaussian"`,
  `"lognormal"`, `"shifted_wald"`. Names appear as string literals
  because the TaskCard's `response_distributions.<cond>.distribution`
  string is the dispatch key. Unknown families raise a clear
  ValueError pointing the user at this file. Stage 2 prompt
  (`reasoner/prompts/stage2_behavioral.md`) documents the same three
  family names for the Reasoner. Adding a new family requires a new
  Sampler class + dispatch entry — that's by design (G2: small set
  of generic mechanisms).
- **No paradigm-specific condition labels.** All condition strings
  flow through the `distributions: dict[str, DistributionConfig]`
  constructor argument. The sampler treats condition names as opaque
  dict keys.
- **`condition_repetition` name check** at distributions.py:269.
  Hardcoded effect name in the temporal-effects loop is the
  registry key — same as how `_EXECUTOR_APPLIED_EFFECTS` references
  `post_event_slowing`. Both are documented contracts between the
  sampler and the effect registry, not paradigm vocabulary.

### Magic floor/ceiling values

- **`floor_ms: float = 150.0`** constructor default
  (distributions.py:163). Overridden per-paradigm by
  `config.runtime.timing.rt_floor_ms` (executor.py:93 passes it
  through). Default reflects the conventional "fast-guess" cutoff
  (Whelan 2008) documented in `prompts/system.md:140`. Per-paradigm
  override is encouraged for simple-RT and perceptual-threshold
  tasks. Framework-level default, paradigm-configurable.
- **`1e-6` divide-by-zero guard** in `ShiftedWaldSampler`
  (distributions.py:84, :92). Defensive lower bound on `drift_rate`
  to avoid `ZeroDivisionError`; tiny enough not to materially shift
  the mean. Framework-level numerical safety.
- **Pink noise buffer size `2048`** (distributions.py:187). Fixed-
  length precomputed FFT-synthesized 1/f^alpha noise series. Long
  sessions exceeding 2048 trials would wrap around — currently no
  paradigm in scope generates that many trials, but flagged as a
  potential silent-failure mode. Not paradigm-specific, but the
  ceiling is undocumented in the constructor signature.

### Architectural concern (report, don't remove)

- **`jitter_distributions` only handles `ex_gaussian`**
  (distributions.py:334). The `for dist in
  config.response_distributions.values(): if dist.distribution ==
  "ex_gaussian":` branch means lognormal and shifted-Wald
  distributions silently receive ZERO between-subject jitter on
  their parameters. Per-condition accuracy / omission jitter still
  applies (lines 345-358 are family-agnostic). If/when the
  Reasoner ever picks lognormal or shifted-Wald for a condition,
  that condition's RT distribution will not vary between
  simulated subjects. Surface this as a future SP item, not a
  walk-and-prune target — the asymmetric coverage was deliberate
  (only ex-Gaussian is exercised by current TaskCards), but the
  behavior is undocumented at the call site.
- **`LogNormalSampler.mu` and `ShiftedWaldSampler.shift_ms` have
  different units than `ExGaussianSampler.mu`.** The
  `getattr(sampler, "mu", 0.0)` defensive read at line 238
  populates `SamplerState.mu` from whichever sampler is active —
  for ex-Gaussian, `mu` is ms; for lognormal, `mu` is the
  log-space location parameter (dimensionless). Handlers that
  consume `state.mu` directly (none currently — only
  `apply_autocorrelation` does, gated by `state.expected_rt`)
  would get nonsense values for lognormal samplers. The
  `expected_rt` short-circuit hides this from current handlers
  but is fragile. Not a defect today; a latent contract gap.

### Sampler-family pruning candidates considered, none removed

- `LogNormalSampler` (distributions.py:35) — zero current TaskCards
  set `distribution = "lognormal"`. Kept because Stage 2 prompt
  documents it as an option for the Reasoner; it's part of the
  Reasoner's generic toolkit, not dead. Same logic as paradigm-
  agnostic effect handlers that no current paradigm enables.
- `ShiftedWaldSampler` (distributions.py:61) — same reasoning as
  `LogNormalSampler`. Zero current callers; documented Reasoner
  option for diffusion-style speeded decisions.

### `_EXECUTOR_APPLIED_EFFECTS` contract

- **`frozenset({"post_event_slowing"})`** at distributions.py:157.
  Kept and documented. Effects in this set are applied by the
  executor at the right point in the trial loop (after error
  detection), not by the sampler. The sampler skips them in its
  iteration to avoid double-invocation. This is a documented
  contract between `core/distributions.py` and `core/executor.py`.

### Comment edit (cosmetic)

- Line 327 comment originally read "preserves inter-condition
  differences like switch cost." The "switch cost" example is
  paradigm-specific phenomenon vocabulary; replaced with the
  generic "preserves inter-condition RT differences" to keep
  comments aligned with G2 (no paradigm vocabulary in bot library).
  No behavior change.

## src/experiment_bot/core/stimulus.py

Walked under SP12 Task 9. No paradigm names appear in the file; the
module dispatches on the TaskCard's `detection.method` string.

### Hardcoded method-name vocabulary (framework-level contract)

- `_check_rule` (stimulus.py:56–76) dispatches on four literal method
  strings: `"dom_query"`, `"js_eval"`, `"text_content"`,
  `"canvas_state"`. These are the Reasoner→Executor contract for
  stimulus-detection mechanics. Adding a fifth detection mechanism
  requires editing both this dispatch and `core/pilot.py:_check_rule`
  + `core/executor.py:_stimulus_detection_js` (and the Stage 2
  validator). The vocabulary is bot-mechanic, not paradigm-specific
  — generalizable, but the dispatch is duplicated in three places
  (see "Architectural" below).
- `"canvas_state"` and `"js_eval"` collapse to identical behavior in
  `_check_rule` (both: `await page.evaluate(rule.selector)` then
  `bool(result)`). The two branches are textually distinct but
  semantically identical. Probably intentional for Reasoner-facing
  semantic clarity ("canvas_state" tells the Reasoner this selector
  reads canvas pixel data; "js_eval" is generic). Not a defect.

### Dead-field carry: `_StimulusRule.alt_method`

- `_StimulusRule.alt_method` (stimulus.py:25) is populated in the
  constructor (stimulus.py:39) but never read by `_check_rule` or
  anywhere else in the bot library. The field tracks
  `DetectionConfig.alt_method` (config.py:41) which is similarly
  unread at runtime — it appears in TaskCard JSON, in fixtures, and
  in the Stage 2 schema, but no code consumes it. Either the
  Reasoner is meant to use it as a fallback method (intent visible in
  the field name) and the runtime fallback was never wired, or the
  field is vestigial schema. Report-don't-remove because the JSON
  schema is committed and TaskCards already serialize it.

### Architectural concerns (report, don't remove)

- **Three sites duplicate the detection-method dispatch.**
  `stimulus.py:_check_rule`, `pilot.py:_check_rule` (lines 214-221),
  and `executor.py:_stimulus_detection_js` (line 764+) each interpret
  the `detection.method` vocabulary independently. They agree today
  but a future Reasoner-side mechanism (e.g., `"shadow_dom"`,
  `"iframe_query"`) would need three matching edits. A small
  `core/detection_dispatch.py` (or method strategy table) would
  consolidate the contract.
- **Bare-`except` in `_check_rule`.** Line 73 catches all exceptions
  and logs at DEBUG. Sufficient for the documented "page context
  torn down by navigation" failure mode, but it also swallows JS
  syntax errors in the TaskCard's `detection.selector` — those
  manifest as "stimulus never matches" rather than a loud failure.
  The Stage 2 validator should catch malformed JS pre-flight; if it
  doesn't, this is a silent-failure surface.

## src/experiment_bot/core/phase_detection.py

Walked under SP12 Task 9. The module is paradigm-agnostic; all
phase predicates flow from `PhaseDetectionConfig` (TaskCard).

### Clear-cut removal applied

- The trailing `if config.test: return TaskPhase.TEST; return
  TaskPhase.TEST` (original lines 33-35) had identical return on
  both branches — dead code. Replaced with a single
  `return TaskPhase.TEST` plus a comment documenting that
  `config.test` is unused at runtime (TEST is always the
  fall-through default). Pytest green (675 passed).

### Hardcoded phase-name vocabulary (framework-level contract)

- The phase ordering tuple at lines 14-21 is the canonical
  evaluation order: `complete > loading > instructions >
  attention_check > feedback > practice`. Order matters because
  the first truthy predicate wins. Editing this order is a runtime
  semantics change. The names also match `TaskPhase` enum values
  (config.py:18-25) and the keys the Reasoner emits in
  `phase_detection.*` — three-way contract.

### Architectural concerns (report, don't remove)

- **`PhaseDetectionConfig.method` is unused at runtime.**
  Defaulted to `"js_eval"` (config.py:595), only surfaced by a
  `test_analyzer.py:161` roundtrip assertion. `detect_phase` always
  calls `page.evaluate` regardless. Either remove the field from
  the schema and roundtrip, or wire it through the dispatch (so the
  Reasoner can emit `"dom_query"` for paradigms whose phase markers
  are pure CSS selectors). Today it's a schema artifact only.
- **Context-destroyed → COMPLETE heuristic is paradigm-agnostic but
  fragile.** Line 29-31: any exception during `page.evaluate` is
  interpreted as "page navigated away → task complete." Correct for
  the dev paradigms (their completion flows always navigate), but
  an unrelated JS error in the Reasoner-emitted predicate would
  also silently report COMPLETE and terminate the trial loop. Same
  silent-failure shape as the `stimulus.py` bare-except.
- **`PhaseDetectionConfig.to_dict` omits empty strings**
  (config.py:608-609: `if v`). The empty default `test=""` would
  drop out of JSON, but the default is `test="true"`, so this
  doesn't lose data today. Worth noting that the dataclass
  defaults and the to_dict filter are coupled.

## 8. Instruction navigation: `navigation/navigator.py`

`InstructionNavigator.execute_all(page, navigation_config)` runs the
TaskCard's nav phases in order. Phases are:
- `click <selector>` — wait + click; raises on timeout (1.5s)
- `keypress <key>` — page.keyboard.press
- `wait <duration_ms>` — fixed sleep
- `sequence`, `repeat` — composite

Called once by `TaskExecutor.run` after page.goto. Re-invoked by the
trial loop's INSTRUCTIONS-phase branch (to advance any mid-experiment
instruction screens).

Entry point: `navigation/navigator.py:InstructionNavigator.execute_all`.

## src/experiment_bot/navigation/navigator.py

Walked top-to-bottom under SP12 Task 10. No paradigm names appear in
the file; the navigator dispatches on the TaskCard's
`navigation.phases[*].action` string.

### Hardcoded action-name vocabulary (framework-level contract)

- `execute_phase` (navigator.py:23–49) dispatches on five literal
  action strings: `"click"`, `"press"` / `"keypress"` (aliases),
  `"wait"`, `"sequence"`, `"repeat"`. These are the Reasoner→Executor
  contract for navigation mechanics. Unknown actions log
  `"Skipping unknown/meta action: ..."` and fall through (vs raise) —
  a soft contract that tolerates Reasoner-emitted meta-actions like
  documentation phases.
- The dual `"press"` / `"keypress"` accept-both is deliberate
  back-compat (Stage 1 prompt may emit either); no paradigm
  vocabulary in scope.

### Soft defaults / fallback literals (acceptable; configurable)

- **`reading_delay_range` constructor default** is `(3.0, 8.0)` seconds
  (navigator.py:16). `PilotRunner` overrides to `(1.0, 2.0)` for faster
  pilots (pilot.py:123). The executor uses the default. Framework-level
  human-pacing emulation; not paradigm-specific.
- **Click timeout `1500` ms** (navigator.py:63). Documented in the
  docstring as a deliberate fast-fail threshold (originally 10000 ms,
  caused ~170 s of phantom-button-clicking on expfactory_stop_signal
  and lost 35 of 180 trials — see SP2.5 entry in CLAUDE.md). Pinned by
  the `test_do_click_timeout_is_short_for_fast_fail` regression test.
  Framework-level; not paradigm-specific.

### Magic numbers / heuristics

- **`max_iterations = 20`** for the `repeat` action (navigator.py:39).
  Local literal (no config knob). The repeat loop exits early when the
  inner click raises (`PlaywrightError` re-raised from `_do_click`), so
  in practice the cap rarely fires. The test docstring
  (`tests/test_navigator.py:73`) claims "default 50" — doc rot; the
  actual cap is 20. Behaviorally inert in dev paradigms because the
  break-on-exception path dominates.

### Clear-cut removal applied

- **Unused exception-bound variable `e`** in `_do_click`
  (navigator.py:65): `except PlaywrightError as e:` → `except
  PlaywrightError:`. The variable was never referenced in the body
  (only the bare `raise` re-raised the current exception). No behavior
  change. Pytest green (675 passed).

### Architectural concerns (report, don't remove)

- **Action-vocabulary dispatch duplicates the `NavigationPhase`
  schema.** `execute_phase`'s five `elif phase.action == ...` branches
  encode the same vocabulary that `core/config.py:NavigationPhase`
  (and the Stage 2 schema) already declares. A future
  Reasoner-side mechanism (e.g., `"focus"`, `"scroll"`) would need
  edits in both places + the Stage 2 validator. A small dispatch
  table (or strategy registry) would consolidate the contract; same
  shape as the `stimulus.py` / `pilot.py` / `executor.py` triple-site
  detection-method dispatch flagged in Task 9.
- **Bare `Exception` catch in `_exec_pre_js`** (navigator.py:80).
  Catches all exceptions and logs at DEBUG. Sufficient for the
  documented "page context torn down by navigation" failure mode, but
  also swallows JS syntax errors in Reasoner-emitted `pre_js` strings.
  Same silent-failure shape as `stimulus.py:_check_rule` (Task 9) and
  `phase_detection.py` context-destroyed → COMPLETE (Task 9).
- **`repeat` swallows all sub-step exceptions to break out**
  (navigator.py:45–47). A non-Playwright bug inside a `sequence` step
  (e.g., a TypeError in a future composite action) would silently end
  the loop with no log line. The bare `except Exception:` is a
  deliberate "any failure → done" semantic for the dev paradigm
  pattern (click Next until it disappears), but it shares the
  silent-failure shape with the items above.

## src/experiment_bot/navigation/stuck.py

Walked under SP12 Task 10. Pure utility module — paradigm-agnostic, no
hardcoded values beyond the constructor default.

### Soft default

- **`timeout_seconds = 10.0`** constructor default (stuck.py:12).
  Overridden in the only production call site by
  `config.runtime.timing.stuck_timeout_s` (executor.py:522).
  Framework-level pacing; not paradigm-specific.

### Architectural candidate (report, don't remove)

- **Single production call site.** `StuckDetector` is imported and
  instantiated only in `core/executor.py:_trial_loop` (the test file
  `tests/test_stuck.py` is the only other consumer). The class is a
  21-line wrapper around `time.monotonic()` + a timeout. Per Task 10
  protocol, a single-call-site utility is a candidate for inlining
  back into the caller (the entire class is three operations:
  `__init__`, `heartbeat()`, and the `is_stuck` property — `_trial_loop`
  could track `last_heartbeat` directly with no loss of clarity).
  Decision deferred — the standalone module is cleanly tested in
  isolation and the call-site cost is one import; inlining is a
  cosmetic refactor with no fidelity impact.
