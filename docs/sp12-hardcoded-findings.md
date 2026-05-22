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

## src/experiment_bot/llm/

Walked under SP12 Task 12. Five files, ~150 LOC total. Paradigm-
agnostic LLM client abstraction; no paradigm vocabulary, no hardcoded
norms/magnitudes. The only consumer chain after SessionAgent removal
(Task 4) is the offline Reasoner pipeline.

### src/experiment_bot/llm/__init__.py

Empty (0 bytes). Re-exports nothing. Consumers always import from the
submodule (e.g. `from experiment_bot.llm.protocol import LLMResponse`).
Leave as-is.

### src/experiment_bot/llm/protocol.py

- **`LLMResponse` dataclass** (text + `stop_reason`); `stop_reason`
  default `"end_turn"` is an Anthropic-protocol literal, not a
  paradigm-specific tunable.
- **`LLMClient` Protocol** with one method `complete(system, user,
  max_tokens=16384, output_format="text", images=None)`. The
  `max_tokens=16384` default is a model-capability ceiling, not a
  fidelity parameter. The `images: list[bytes] | None` slot is now
  dead in production (no Reasoner stage passes images; SessionAgent
  removal in Task 4 was the only image-passing caller). Kept in the
  protocol for parity with the SDK; no call sites left to migrate.
- No hardcoded paradigm values. Consumed broadly by reasoner stages
  1, 2, 3, 5, 6, parse_retry, norms_extractor, pipeline.

### src/experiment_bot/llm/cli_client.py

- **`claude_binary="claude"`** constructor default — paradigm-agnostic
  binary name on PATH.
- **`model="claude-opus-4-7"`** constructor default — framework-wide
  model selection, surfaced through `build_default_client(model=...)`
  override.
- **`timeout_s=1200.0`** constructor default (20-minute LLM call
  ceiling) — bot-mechanic, paradigm-agnostic.
- **`--output-format json`** hardcoded CLI arg (line 50). The CLI's
  JSON envelope is parsed; this is the binary's own format flag, not
  the per-call `output_format="text"/"json"` parameter (which is
  silently ignored on the CLI path).
- **Multimodal warn-and-degrade** (lines 36–42). When images are
  passed, logs a warning and proceeds text-only. Post-SessionAgent-
  removal, this branch is dead code in production but cheap to keep.
- **Usage-limit error sniffing** (line 70) keys on the strings
  `"usage limit"` / `"quota"` in stderr. CLI-binary contract, not a
  paradigm value.
- Sole instantiation: `factory.py:_build_cli_client` (+ tests).

### src/experiment_bot/llm/api_client.py

- **`model="claude-opus-4-7"`** constructor default — same framework
  default as the CLI client. Matched override path via factory.
- **`media_type="image/png"`** hardcoded (line 31). Reasonable for
  the only historical caller (SessionAgent screenshots, now removed).
  No paradigm coupling; PNG is the Playwright screenshot default.
- **`output_format` parameter is documented as informational only on
  the API path** (lines 22–23) — the API enforces JSON via prompt
  text, not a request flag. Matches CLI's silent-ignore behavior.
- Sole instantiation: `factory.py:_build_api_client` (+ tests).

### src/experiment_bot/llm/factory.py

- **`EXPERIMENT_BOT_LLM_CLIENT`** env var with values `"cli"` /
  `"api"` selects the implementation explicitly. Default branch
  prefers CLI if `claude` is on PATH, else API if
  `ANTHROPIC_API_KEY` is set, else raises. Clean two-step resolution.
- **`build_default_client(model: str | None = None)`** is the lone
  public entry. Used by:
  - `reasoner/cli.py:55` (Reasoner TaskCard generation)
  - `reasoner/norms_cli.py:24` (norms extractor)
- No hardcoded paradigm values; the only literals are env-var names
  and the protocol-default model id (overridable).

### Architectural candidate (report, don't remove)

- **Two client implementations, one remaining consumer surface
  (Reasoner, offline).** Prior to Task 4, SessionAgent was the only
  caller that needed multimodal (screenshots) and explicitly required
  the API path. With SessionAgent gone, every remaining caller is
  text-only, so the API client's distinguishing capability
  (multimodal image input) is no longer exercised in production. The
  two-implementation pattern still has a real UX rationale — CLI uses
  the user's Max subscription via `claude login`, API uses
  `ANTHROPIC_API_KEY` — and the `images=None` branch in both clients
  is cheap, so neither is a clear-cut removal. Decision deferred:
  consolidating to a single client (either) would simplify the
  abstraction by ~40 LOC but trade off the no-API-key UX. Logged as
  an architectural call, no auto-apply.
- **`output_format` parameter on `LLMClient.complete`** is now
  silently ignored on both implementations (CLI uses
  `--output-format json` unconditionally; API enforces JSON via
  prompt text). Could be dropped from the Protocol with a sweep
  through reasoner call sites, but the change touches every stage and
  has zero fidelity impact. Architectural call, deferred.
- **`images` parameter on `LLMClient.complete`** is no longer passed
  by any production call site (Task 4 removed SessionAgent, the only
  caller). Same disposition as `output_format`: removal is safe but
  touches the protocol and both implementations for cosmetic gain.
  Deferred.

## src/experiment_bot/taskcard/

(no paradigm-specific values; the module is purely structural — JSON
load/save, dataclass shaping, hashing, between-subject jitter draw.
Paradigm semantics live entirely in the TaskCard payload itself.)

### `__init__.py`

- Empty file (0 bytes). No re-exports, no public-API surface declared
  at package level. Architectural note, not a finding.

### `loader.py`

- `load_by_hash(base_dir, label, hash_prefix)` was dead code — only
  referenced by its own test (`test_load_by_hash`). No production
  call site, not exported from `__init__.py`. **Auto-removed**
  alongside its test in this walk.
- `load_latest` resolves "most recent" by `file.stat().st_mtime`. This
  is correct for the current single-writer pipeline (Stage 6 saves
  once per regeneration) but would silently pick the wrong card if
  `touch`-style operations bumped mtime without re-saving content.
  Not a hardcoded-paradigm issue; logging the assumption here.

### `types.py`

- `_wrap_legacy_dist` / `_wrap_legacy_effect` adapt v1 (`{"params":
  {...}, "distribution": ..., "unit": ...}`) TaskCard payloads to the
  v2 `ParameterValue` shape on load. Grep across the committed
  `taskcards/` tree shows zero v1 payloads remain. These wrappers are
  dead-on-arrival for any current TaskCard but live behind a defensive
  `"value" in v` branch and have no paradigm coupling. Architectural
  item — removal is safe, but the safety net is also cheap. Deferred.
- `Citation.doi_verified_at` is typed `str | None` and serialized via
  `asdict`; no ISO-8601 invariant is enforced at the dataclass layer.
  Stage 4's openalex verifier writes this value. Not paradigm-specific.

### `sampling.py`

- `sample_session_params` clips draws to `literature_range` per
  sub-parameter when present. The clip is paradigm-agnostic (operates
  on whatever keys appear in `value`), and the SD-zero branch returns
  the mean unchanged. No hardcoded paradigm vocabulary.

### `hashing.py`

- `taskcard_sha256` zeroes `produced_by.taskcard_sha256` before
  hashing so the hash is content-addressed and self-verifying. Uses
  `sort_keys=True` and `separators=(",", ":")` for canonical form.
  No paradigm coupling.

## src/experiment_bot/taskcard/

### types.py
- `_wrap_legacy_dist` / `_wrap_legacy_effect` REMOVED — all current TaskCards use v2 layout (`value` key present); the legacy v1 wrappers (with hardcoded `sensitivity="unknown"` fallback) had zero live callers.
- `between_subject_jitter` field type is `Any` (dict | BetweenSubjectJitterConfig) with a duck-typed `to_dict` check in `TaskCard.to_dict`. Fragile contract — should be normalized to a single type in a follow-up SP.

### loader.py
- Paradigm-agnostic. `load_latest` picks newest by mtime, not by SHA — adequate but means an older card with a newer mtime would shadow a newer one.

### sampling.py
- Paradigm-agnostic. Single function used by `cli.py`.
- Silent fallback: missing `between_subject_sd` → `spread = 0` (deterministic draw), no warning.

### hashing.py
- Paradigm-agnostic. Canonicalizes via `sort_keys + (",", ":")` separators.

## src/experiment_bot/reasoner/ (SP12 Task 14)

Walked the 5-stage offline pipeline (1872 LOC across 14 .py files + 4
stage prompt .md files). Constraint: must not touch `prompts/system.md`,
`prompts/schema.json`, or any `reasoner/prompts/stage*.md` — those force
TaskCard regen. Removed only `validate_stage1_output` dead import from
`stage6_pilot.py` (pyflakes-confirmed; only true unused import in dir).
Suite green: 674 passed, 3 skipped.

### `pipeline.py`
- Hardcodes `Path("taskcards")` as default `_taskcards_dir` (line 43)
  — same default in `cli.py`, so functionally redundant but not
  paradigm-specific.
- Resume scan iterates explicitly `(5, 4, 3, 2, 1)` — adding a future
  stage requires editing this tuple.
- Paradigm-agnostic; no hardcoded paradigm names.

### `cli.py`
- Hardcodes `"claude-opus-4-7"` and `"1.0.0"` scraper version as
  fallback `produced_by` metadata in `_wrap_for_taskcard` (lines 78-85).
  Falls back only when partial lacks `schema_version` (legacy path);
  current Stage 1 emits this, so dead in practice — but provenance
  could lie if it ever fires.
- Paradigm-agnostic.

### `normalize.py`
- Pure key-alias mapping. Canonical aliases are LLM-output coercions
  (`detect`→`detection`, `type`→`method`, `selector`→`target`,
  `duration`→`duration_ms`). No paradigm names.
- `_normalize_performance` injects `accuracy = {"default": 0.95}` when
  the LLM omits accuracy entirely (line 41). The 0.95 is a hardcoded
  bot-side default; documented as "interrupt tasks measuring inhibition
  rate" but the value itself is not citation-backed. **Soft finding:**
  consider sourcing from norms or surfacing as warning.
- `_normalize_stimulus` falls through to `id = "unknown_stimulus"`
  when no ID-like key exists (line 62). Silent — Stage 1 validation
  doesn't check IDs for uniqueness either.

### `stage1_structural.py`
- **REQUIRED_FIELDS_CHECKLIST (lines 20-61)** is appended to the
  user prompt in `_build_stage1_prompt`. Contains paradigm/platform
  examples: "STOP-IT calls a custom `jsPsych.data.getInteractionData()`"
  (line 40). This is paradigm-name leakage in prompt content.
  **NOT REMOVED** — modifying it changes Stage 1 outputs (TaskCard
  regen). Flag for SP-prompt-cleanup pass.
- Hardcoded source-text truncation: `description_text[:5000]`,
  `content[:60000]` (lines 81-83). Tuned for jsPsych task sizes; could
  decay for very large paradigm sources. No fallback warning.
- `_extract_json` is the canonical JSON extractor for all stages
  (re-exported via parse_retry); historical reason but stage2 still
  imports it directly from here (`stage2_behavioral.py` line 7).
  Cleaner home would be a `_json.py` module.
- `max_retries=3` for validation loop is hardcoded.

### `stage2_behavioral.py`
- `STAGE2_MAX_REFINEMENTS = 3` hardcoded.
- `_SLOT_RULES` list (lines 31-38) defines slot-extraction depth
  per top-level path. `between_subject_jitter` collapses to whole
  slot; `temporal_effects` / `performance` / `task_specific` /
  `response_distributions` collapse to depth-2. **Adding a new
  slot-bearing top-level key requires editing this list** — a
  future paradigm with a different top-level structure would silently
  fall through to the depth-1 default.
- `_render_slot_refinement_prompt` builds a multi-section refinement
  prompt inline (lines 92-115). Includes the docstring-anchored
  reference to the "Concrete shape examples" section of `system.md`
  — coupled to system prompt structure.
- Paradigm-agnostic; mechanism vocabulary read from `EFFECT_REGISTRY`
  at runtime.

### `stage3_citations.py`
- `path.split("/", 2)` (line 47) — section-key separator is hardcoded
  `/`. Same convention as enumeration. Dispatch on `section` name is
  a static if/elif chain over the three known sections.
- Paradigm-agnostic.

### `stage4_doi_verify.py`
- `_iter_citations` walks the same three sections by hardcoded names
  (`response_distributions`, `temporal_effects`,
  `between_subject_jitter`). Identical pattern to stage3 / stage5
  dispatch — three copies of the section list across the reasoner.
- Paradigm-agnostic.

### `stage5_sensitivity.py`
- Same hardcoded section list as stages 3/4 (lines 30-35).
- Path-parts dispatch (2 vs 3 segments) is hardcoded; malformed
  paths silently skipped.
- Paradigm-agnostic.

### `stage6_pilot.py`
- **REFINEMENT_PROMPT (lines 39-85)** is a paradigm-agnostic prompt
  template, but it does name the specific structural fields that
  pilot evidence can refine: stimuli, navigation,
  runtime.advance_behavior, runtime.phase_detection,
  runtime.data_capture, task_specific. Coupled to the TaskCard
  shape.
- `_partial_to_pilot_config` builds a TaskConfig that imports 8
  dataclasses from `core.config` — strongest tight coupling in the
  reasoner directory.
- Splice list (`stimuli`, `navigation`, `runtime`, ...) at line 180
  duplicates the structural-fields list in `_partial_to_pilot_config`
  and again in `_save_refinement_diff` (line 229). 3 hardcoded
  copies of the same list — divergence risk.
- Hardcoded source truncations: `[:5000]`, `[:30000]` (lines 154-156)
  diverge from Stage 1's `[:5000]`, `[:60000]`. Stage 6 sees less
  source context than Stage 1 did; intentional? Undocumented.
- Removed unused `validate_stage1_output` import (pyflakes-clean).

### `validate.py`
- `validate_stage2_schema` reads `EFFECT_REGISTRY` at function-call
  time (line 83) — late binding intentional so dynamic
  `register_effect` calls work.
- Hardcoded list of validated top-level keys: `temporal_effects`,
  `between_subject_jitter`, `performance.accuracy`,
  `performance.omission_rate`, `task_specific.key_map`. Adding a new
  validation target requires editing this function.
- Comment block (lines 78-81) names removed paradigm vocabulary
  (`congruency_sequence`, `post_error_slowing`) as historical
  context; safe — comment only, not in any prompt.
- `validate_stage1_output` hardcodes the executor's contract:
  advance_keys vs feedback_selectors, data_capture.method enum.
  Tightly coupled to executor's expectations.

### `parse_retry.py`
- `max_retries=3` default hardcoded.
- Defers import of `_extract_json` to avoid a circular dependency
  with `stage1_structural.py` (comment lines 69-74). **Architectural
  smell:** `_extract_json` should live in `parse_retry.py` (or a
  shared `_json.py`); other stages import it from stage1 only by
  historical accident.

### `openalex.py`
- Hardcoded URL template `OPENALEX_URL` (line 7) and HTTP timeout
  `10.0`s. Both reasonable defaults; configurable via env var would
  be nicer.
- Surname-matching tokenization is heuristic: tokens with length > 2
  and capitalized first letter (lines 41-45). Will mis-tokenize
  hyphenated names, single-syllable surnames ≤ 2 chars (e.g., "Yu"),
  and non-Western name orders.
- SP9b string-vs-list normalization (lines 39-40) is paradigm-
  agnostic.

### `norms_extractor.py`
- `_RANGE_KEYS` (lines 25-29) hardcodes the set of acceptable range
  keys: `range`, `range_ms`, `mu_range`, `sigma_range`, `tau_range`,
  `mu_sd_range`, `sigma_sd_range`, `tau_sd_range`. Adding a new
  range-bearing key (e.g., `gamma_range` for a future distribution)
  requires editing.
- Validator allows EITHER concrete range OR explicit-null with
  reason — paradigm-agnostic policy.

### `norms_cli.py`
- Lightweight click wrapper. Single hardcoded default `norms` dir.

## Cross-cutting reasoner findings

1. **Three copies of the section-list dispatch.** `stage3`, `stage4`,
   `stage5` each hardcode `response_distributions` /
   `temporal_effects` / `between_subject_jitter`. If a future Stage
   adds a fourth top-level numeric section (e.g.,
   `within_subject_jitter`), all three must be updated in lockstep.
   Candidate for a shared `SECTIONS_WITH_PARAMS` constant.
2. **`_extract_json` belongs in `parse_retry.py`.** Its current
   home in `stage1_structural.py` is historical; the circular-import
   workaround in `parse_retry.py` is the symptom.
3. **`REQUIRED_FIELDS_CHECKLIST` paradigm leakage.** Lives in
   `stage1_structural.py` but is prompt content. STOP-IT named
   directly. Cleanup requires a Stage 1 TaskCard regen pass —
   defer to a future SP.
4. **Hardcoded source truncation budgets diverge.** Stage 1 uses
   60k chars per file; Stage 6 refinement uses 30k. No documented
   reason. May silently shrink the LLM's view between attempts.
5. **`_normalize_performance` default `accuracy = 0.95`.** Soft
   default with no citation hook. For tasks that legitimately omit
   accuracy, this number ends up in the TaskCard and propagates
   through the executor. Worth a logged warning or
   norms-file lookup.
6. **Pipeline resume tuple `(5, 4, 3, 2, 1)`.** Adding stage 7+ is
   a 2-line edit, but the order is also embedded in the chained
   `start_after < N` conditions in `run()`.

## src/experiment_bot/effects/ (SP12 Task 15)

Walked the four files. No auto-removals applied — every symbol is
imported by oracle.py, scripts/analyze_sessions.py, or tests/.

### Things that look removable but aren't

1. **`apply_condition_repetition` handler.** Every committed
   TaskCard sets `temporal_effects.condition_repetition.enabled =
   False`; the runtime delta is always 0. But the mechanism is
   under an explicit SP11 Phase 2 deprecation arc
   (`core/config.py:_emit_condition_repetition_deprecation`), with
   tests gating the warning behavior and the registry wiring still
   live. Per G2, the mechanism vocabulary entry is retained until
   Phase 5 removal; the Reasoner could re-enable it on a future
   paradigm by setting `enabled: true` and supplying non-zero
   `facilitation_ms`/`cost_ms`. Keep.

2. **`SamplerState.mu`/`sigma`/`tau` fields.** Doc says they are
   "kept for back-compat with handlers/tests that reference
   ex-Gaussian parameters directly" and `apply_autocorrelation`
   falls back to `state.mu + state.tau` when `expected_rt` is 0.
   Several tests construct `SamplerState` without setting
   `expected_rt` and rely on this fallback. Removal would break
   them. Keep until those tests migrate.

### Architectural items (reported, not removed)

1. **`registry.py` does post-hoc wiring of handlers and
   config_classes at import time** (lines 178–211). Each registry
   entry is built with `handler=None` / `validation_metric=None`
   then mutated after the dataclass is constructed. The comment
   says "filled in by Task A2" — that task is long-done.
   Refactoring this to declare handler/config_class/validation_metric
   inline at the `EffectType(...)` call site would remove the
   two-phase init and the `# noqa: E402` imports, but requires
   resolving the `effects ↔ core.config` circular-import shape
   (handlers references SamplerState; config references handlers
   indirectly via validation). Defer until the circular shape is
   investigated holistically.

2. **`apply_post_event_slowing.decay_weights` is documented but
   not implemented.** The handler's docstring (lines 222–228)
   describes per-position decay weights consulted "only [for]
   error-event triggers"; the body never reads
   `decay_weights`. Either prune the docstring claim or wire it
   up. Affects SP2-E3 fidelity follow-ups already tracked in
   `docs/sp2-validation-followups.md`.

3. **`effects/__init__.py` is empty.** All consumers import from
   submodules directly (`from experiment_bot.effects.handlers
   import ...`, `from experiment_bot.effects.registry import
   EFFECT_REGISTRY`). Empty `__init__.py` is fine — no re-export
   layer to maintain. Noting only because the next sibling
   walk-throughs may want to keep this pattern consistent.

4. **`fit_ex_gaussian` hardcodes the [150ms, 5000ms] outlier
   filter and bounds `(50, 5000)` / `(1, 1000)` / `(1, 2000)`.**
   These are physiologically motivated and documented in the
   docstring. Worth flagging because the bot's library should
   ideally read RT plausibility bounds from a single source
   (currently also referenced in `distributions.py` and in the
   norms files). Candidate for a `RT_PLAUSIBILITY_RANGE_MS`
   constant. Defer.

5. **`cse_magnitude` lives in `effects/validation_metrics.py`
   despite being explicitly paradigm-conventional language.**
   The docstring is clear that the name is retained because the
   conflict literature standardizes it — the implementation is a
   thin wrapper around `lag1_pair_contrast`. This is a deliberate
   exception under the G2 carve-out for metric NAMES (vs.
   mechanism names). No change.

## src/experiment_bot/validation/

Walked top-to-bottom under SP12 Task 16. Files reviewed:
`oracle.py`, `platform_adapters.py`, `cli.py`, `__init__.py`, and
the now-removed `eisenberg.py`.

### Removed (dead code)

- **`validation/eisenberg.py`** — `load_eisenberg_summary(...)` had
  no callers in `src/`, `scripts/`, or `tests/`. The function read
  trial-level CSVs into ex-Gaussian fits for "descriptive-only"
  side-by-side comparison; that comparison path was never wired
  into the oracle or CLI in the final SP2 implementation (the
  spec/plan mentioned it but the wiring was dropped). PARADIGM_CLASS
  filenames (`stroop_eisenberg.csv`, `stop_signal_eisenberg.csv`)
  also hardcoded `conflict` / `interrupt` → dev-paradigm names, which
  would have been a G1 generalizability violation if it had been
  exercised. Removed.

### Architectural items (reported, not removed)

1. **`platform_adapters.PLATFORM_ADAPTERS` carries hardcoded
   paradigm labels** (`stop_signal_rdoc`, `stroop_rdoc`,
   `flanker_rdoc`, `n_back_rdoc`, `stop_signal_kywch_jspsych`,
   `stop_signal_task_(stop-it,_jspsych_port)`,
   `stroop_online_(cognition.run)`, plus URL-label aliases
   `expfactory_stroop`, etc.). The module docstring already
   acknowledges this: "Long-term, these adapters belong in the
   TaskCard (the Reasoner could emit field-mapping config during
   Stage 1+ from source-code analysis). For now, they live in code
   with one dispatch entry per dev paradigm." This is the canonical
   G1 generalizability soft-spot — adding a new paradigm requires a
   code edit here, not just a TaskCard. Tracked; not removed
   because no replacement TaskCard schema exists yet.

2. **`TEST_ROW_PREDICATES` mirrors `PLATFORM_ADAPTERS` label list
   1:1.** Same paradigm-labeled dispatch shape, same generalizability
   concern, same long-term destination (TaskCard-emitted filter
   config). Both registries should migrate together; until then the
   parallel structure is fine.

3. **`read_cognitionrun_stroop` silently treats every keyed
   response as `correct=True`** (platform_adapters.py:268,
   "Without the runtime key→colour map, treat any keyed response
   as a successful response and let the oracle's RT-distribution
   metrics ignore correctness for this paradigm"). This is
   documented but breaks the oracle's correctness-based metric
   contract for this label. Acceptable for the population-level
   RT/CSE/PES metrics currently gated; risky if a future norms file
   adds accuracy gates. Worth flagging in scope-of-validity.

4. **`read_expfactory_n_back` canonicalizes condition labels
   inline** (`f"{cond}_{delay}back"` on line 185). The
   normalization is paradigm-specific (n-back's `(condition, delay)`
   pair → `<condition>_<delay>back`). It lives in the adapter
   because the platform export emits the two fields separately;
   the TaskCard expects them concatenated. Acceptable — adapters
   are explicitly the place for per-paradigm field-mapping — but
   the in-band string templating could move to a more declarative
   pattern when this registry migrates to TaskCard config.

5. **`oracle.METRIC_REGISTRY` includes `cse_magnitude` as a
   built-in entry** (oracle.py:291–295). Per the SP12 effects walk
   finding #5, the metric NAME is acceptable as conflict-paradigm
   conventional language; the underlying compute (`_compute_cse`)
   is the generic `cse_magnitude` wrapper that itself dispatches
   to `lag1_pair_contrast`. CLAUDE.md / "When editing the
   validation oracle" explicitly carves this out. No change.

6. **`_default_bot_log_loader` fallback path is deprecated but
   retained** (oracle.py:76–112). Used only when no adapter is
   registered for a label; CLI emits a WARNING in that case. G4
   ("Authoritative data sources") says the oracle reads the
   platform export, not `bot_log.json`. The fallback violates that
   in spirit but is gated behind an explicit warning and only
   fires when adapters are missing. Keep as a back-compat safety
   net; the warning is the durable user-facing signal.

7. **`cli.py:_load_lag1_contrast_labels` infers (high, low) from
   `modulation_table` sign conventions** ("prev == curr and delta
   < 0" → high; the other label is low). This is paradigm-agnostic
   in implementation but depends on the Reasoner emitting tables
   that follow the documented sign convention. A malformed table
   returns None silently, and the dependent metric NaNs out — fail-
   open by design. The convention is documented in the docstring.
   Acceptable.

8. **`validation/__init__.py` is empty.** Consumers import from
   submodules directly. Consistent with `effects/__init__.py`
   (finding #3 above). No re-export layer to maintain.

