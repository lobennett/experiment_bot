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

### Comma-separated SessionAgent key aliases hard-code English

`_KEY_ALIASES` (executor.py:325–334) maps English-word names ("comma",
"period", "left") to Playwright keys. This is a runtime-LLM
normalization layer; it's only consulted on `_runtime_key_mapping`
hits (i.e., when SessionAgent fires). Not paradigm-specific, but
ties one piece of the framework to one human language.

### `_pick_wrong_key` requires ≥2 known keys

`_pick_wrong_key` returns `correct_key` (i.e., DOES NOT flip) when
only one real key exists in `_key_map` or `_seen_response_keys`
(executor.py:474–476). For paradigms with a single-key go response
(e.g., go/no-go where the only "go" key is Space), intended-error
trials silently behave as correct trials. Not necessarily wrong —
the design is to fail closed — but it's a hidden contract worth
documenting.
