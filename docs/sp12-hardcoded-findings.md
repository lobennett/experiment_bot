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

