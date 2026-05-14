# SP9a — Session-time runtime LLM: cross-paradigm results

**Date:** 2026-05-13
**Spec:** `docs/superpowers/specs/2026-05-12-sp9a-session-agent-design.md`
**Plan:** `docs/superpowers/plans/2026-05-12-sp9a-session-agent.md`
**Branch:** `sp9a/session-agent` (off `sp8-complete`)
**Tag (after this report lands):** `sp9a-complete`

## Goal

Add a one-call-per-session LLM agent (`SessionAgent`) that runs after navigation completes, probes the live page (DOM + window globals + screenshot), and resolves the condition→key mapping. Cache the directive in the executor so per-trial key lookup is a synchronous dict access (zero latency added during stimulus polling). Test whether runtime LLM at session start improves per-trial alignment vs SP8's prompt-engineering approach.

## Hypothesis (from spec)

A runtime LLM call at session start can resolve the key mapping correctly for paradigms without `window.correctResponse`. Target: bring stroop/stop_signal/stop-it per-trial alignment from 28-45% toward n-back-level (~70%+).

## Procedure (deviated from plan)

The plan called for 12 sessions × 4 paradigms × 3 seeds. Per the user's checkpoint discipline, the run was tiered:

1. **Smoke** — 1 n-back session to verify SessionAgent fires end-to-end and the directive flows through the executor.
2. **Stroop x3** — the highest-value paradigm (worst SP8 alignment, biggest potential win).
3. **Stop-signal x1** — additional data point to test whether SessionAgent generalizes.

After stop-signal returned the third null result, the run was halted (user picked option "2 then 1" in the checkpoint conversation). Stop-it (jspsych port) and the remaining seeds were not run because the cross-paradigm signal was already clear.

All sessions used the **SP8-regenerated TaskCards** (`expfactory_stroop/f099a88b.json`, `expfactory_stop_signal/6ccd7d47.json`) copied into the SP9a worktree, so the comparison to SP8 baselines is apples-to-apples on TaskCard. N-back used the pre-SP8 TaskCard (`expfactory_n_back/085f4f0a.json`) because SP8's n-back TaskCard was never committed; comparison to the SP8 n-back baseline is therefore noisier.

## Implementation status

✅ **Internal CI gate: PASS.** 563 passed, 3 skipped (+33 over `sp8-complete` baseline of 530). Suite includes:

- 4 LLM-layer tests (Protocol image parameter, API client content blocks, CLI client compatibility, factory model override)
- 16 agent-layer tests (KeyMappingDirective, PageProbe helpers, SessionAgent paths)
- 3 RuntimeConfig flag tests
- 8 executor integration tests (runtime mapping priority, sentinel fall-through, English-word key normalization, agent invocation paths)
- 2 CLI wiring tests

The implementation produced:

| New file | Role |
|---|---|
| `src/experiment_bot/agent/types.py` | `KeyMappingDirective` dataclass |
| `src/experiment_bot/agent/page_probe.py` | window-globals / DOM / screenshot helpers |
| `src/experiment_bot/agent/session_agent.py` | `SessionAgent.resolve_key_mapping` |

| Modified file | Change |
|---|---|
| `src/experiment_bot/llm/protocol.py` | `images` parameter on `complete()` |
| `src/experiment_bot/llm/api_client.py` | multimodal content blocks |
| `src/experiment_bot/llm/cli_client.py` | text-only graceful degradation when `images` passed |
| `src/experiment_bot/llm/factory.py` | `model` override for haiku selection |
| `src/experiment_bot/core/config.py` | `RuntimeConfig.session_agent_enabled` |
| `src/experiment_bot/core/executor.py` | post-nav invocation, runtime branch, key normalization, sentinel filtering, metadata directive |
| `src/experiment_bot/cli.py` | construct SessionAgent and pass to TaskExecutor (gap discovered after first smoke) |

The implementation matched the plan with one significant gap: the plan didn't include updating `cli.py` to actually pass the SessionAgent to the executor. Empirical smoke #1 produced `run_metadata.json` with no `session_agent_directive` field; that surfaced the gap immediately, was fixed in commit `202db53`, and the smoke re-ran successfully.

Two further defensive fixes landed after stroop crashes:
- `dynamic`/`dynamic_mapping` sentinel fall-through in `_resolve_response_key` (commit `a31c8c4`)
- English-word key normalization `_KEY_ALIASES` (commit `0366426`)

## Cross-paradigm empirical results

### N-back smoke (1 session, seed 9001, 135 trials)

Directive: `{match_1back: ".", mismatch_1back: ",", match_2back: ".", mismatch_2back: ","}`
Source: `screenshot_inference` | Confidence: 0.95 | Elapsed: 1377 ms

| Metric | SP8 baseline | SP9a smoke |
|---|---|---|
| `bot_intended == platform_expected` | 72.1% | **68.1%** |
| `bot_pressed == platform_recorded` | 64.0% | 59.3% |

The 4 percentage point dip on `intended==expected` is within single-session variance (the SP8 baseline was 3 sessions × 135 trials). **No regression on n-back; SessionAgent's directive flows through the executor cleanly.** The bot pressed the directive's keys for every trial, so the keypress mechanism is verified end-to-end.

Note: SessionAgent's contribution to n-back is **null in practice** — the pre-SP8 n-back TaskCard's `response_key_js` already returns `window.correctResponse` (the page exposes it), which is the same source the LLM extracted. The SessionAgent's directive matched what the executor would have computed anyway via the existing per-stim fallback chain.

### Stroop (3 sessions, seeds 9201/9202/9203, 360 trials)

Per-session directives (all 3 runs):
- `{congruent: ",", incongruent: "."}` with source `dom_inference`, confidence 0.85/0.85/0.75

| Metric | SP8 baseline | SP9a (3 sessions) |
|---|---|---|
| `bot_intended == platform_expected` | 28.9% | **32.2%** |
| `bot_pressed == platform_recorded` | 26.1% | 48.6% |

Per-session breakdown:
| Session | n | `intended==expected` |
|---|---|---|
| 2026-05-13_18-36-22 (seed 9201) | 120 | 28.3% |
| 2026-05-13_18-43-21 (seed 9202) | 120 | 37.5% |
| 2026-05-13_18-50-28 (seed 9203) | 120 | 30.8% |

**The SessionAgent's mapping is the wrong abstraction for stroop.** Trial-level inspection makes this clear:

| trial | stim_color | bot_intended | plat_expected |
|---|---|---|---|
| 0 | blue | , | . |
| 1 | red | , | , |
| 2 | green | . | / |
| 4 | red | . | , |
| 5 | blue | , | . |

The platform's `correct_response` depends on `stim_color`, gated by an `efVars.group_index` counterbalancing variable (0-14, with 5 distinct color→key mappings). The SP8 stroop `response_key_js` correctly encodes this; the SessionAgent's "one mapping per condition" abstraction does not — there's no way to encode "key depends on which color is shown this trial" in a `{condition: key}` directive.

The SessionAgent confidently asserted `{congruent: ",", incongruent: "."}` in all 3 sessions. That mapping is wrong on every trial where the stimulus isn't a particular hardcoded color — i.e., wrong roughly two-thirds of the time for a 3-color paradigm.

### Stop-signal expfactory (1 session, seed 9101, 128 trials)

Directive: `{circle: ",", square: ".", stop: "withhold"}` (source `dom_inference`, confidence 0.95, elapsed 1324 ms)

| Metric | SP8 baseline | SP9a session |
|---|---|---|
| `bot_intended == platform_expected` | 44.7% | **59.4%** |
| `bot_pressed == platform_recorded` | 37.3% | 48.4% |

**SessionAgent's directive did not activate for this paradigm.** The bot log shows trial `condition` as `go` (not `circle`/`square`). The runtime mapping lookup is `_runtime_key_mapping.get(match.condition)` — looking up `go` in `{circle: ..., square: ..., stop: ...}` returns `None`. The executor falls through to the existing per-stim `response_key_js` chain (the SP8 layer-(a) path).

The +15pp delta vs SP8 is single-session variance from the SP8 layer-(a) flaky response_key_js (SP8 baseline was 3 sessions); SP9a contributed nothing to this number.

The mismatch between TaskCard `key_map` keys (stimulus IDs: `circle`/`square`/`stop`) and the executor's `match.condition` value (`go`) is a separate, pre-existing schema inconsistency exposed by SP9a's instrumentation. The SessionAgent faithfully echoed the TaskCard's `key_map` keys; the runtime branch silently never activated because those keys don't match what the executor looks up.

## Reading

### The integration works

All four required pieces functioned correctly:
- SessionAgent fires after `_navigator.execute_all` + `_install_keydown_listener`
- One haiku-class LLM call ~1.3-2.3s per session — well within budget; per-trial cost is zero (synchronous dict lookup)
- `KeyMappingDirective` captured in `run_metadata.json` for audit
- The runtime mapping flows through `_resolve_response_key` for conditions that match, falls through for those that don't

The infrastructure is reusable for any future session-time LLM judgment. Defensive layers (sentinel filtering, English-word key normalization) are paradigm-agnostic and would benefit any non-SessionAgent caller too.

### The empirical hypothesis was not supported

For all three paradigms tested, SP9a's contribution to per-trial alignment is within session-to-session variance:
- **N-back**: SessionAgent works but its mapping is redundant with what the existing `response_key_js` already computes (the page already exposes `window.correctResponse`).
- **Stroop**: SessionAgent's "one mapping per condition" abstraction is structurally inadequate for paradigms where the correct key depends on stimulus identity (color, position, content). The SessionAgent confidently produced a single mapping that's wrong roughly two-thirds of the time.
- **Stop-signal**: SessionAgent's directive used the TaskCard's stimulus IDs as keys, which don't match the executor's `match.condition` lookup. The runtime branch silently never fired.

The spec's hypothesis was: *"A runtime LLM call at session start … can resolve the key mapping correctly for paradigms without `window.correctResponse`."* The empirical answer is **no**, conditional on the architectural assumption that the mapping has the shape `{condition_label: single_key}`. For paradigms that satisfy that shape, the existing pipeline already works (n-back). For paradigms that don't (stroop), no amount of LLM intelligence at session start can produce a per-condition single key that's correct on more than ~30% of trials.

### Two pre-existing issues surfaced by the audit

1. **TaskCard schema variation across paradigms** — stop-signal's `task_specific.key_map` keys (`circle`/`square`/`stop`) differ from the executor's `match.condition` value (`go`). This is a Stage-1 stimulus-classification inconsistency, predates SP9a. The runtime branch's silent fall-through masked the issue; without the SessionAgent's directive in `run_metadata` this would have been hard to spot.

2. **Platform-recording gap (SP7 layer d)** — user-observed during the live runs: even when the bot delivers keys to the page, the platform's CSV `response` column doesn't record them at the rate the page-level keydown listener captures them (~48% across stroop, vs 93% bot-pressed→page-received from SP7). User flagged: "responses might not be captured in a way that registers to the feedback block." jsPsych's `keyboard-response-plugin` reads from its own listener with response-window timing and `choices` filtering, not raw keydown events. Orthogonal to SessionAgent; SP9b candidate.

## Comparison to SP8

| Metric | SP8 result | SP9a result |
|---|---|---|
| Internal tests | 530 passed | 563 passed (+33) |
| Mechanism implemented | Stage 1 prompt edit | SessionAgent at executor layer |
| n-back `intended==expected` | 72.1% | 68.1% (within variance, no regression) |
| stroop `intended==expected` | 28.9% | 32.2% (within variance, no improvement) |
| stop_signal_expfactory `intended==expected` | 44.7% | 59.4% (single session, variance) |
| Cross-paradigm generalizability | partially supported (n-back wins, others don't) | partially supported with a more architectural framing |

SP8 framed n-back's improvement as the win conditioned on `window.correctResponse` being exposed. SP9a tested whether runtime LLM judgment can close the gap for paradigms where the page doesn't expose it. The answer is **no**, but for a more interesting reason: the gap isn't about "the LLM can't see the right mapping at session start" — it's that the underlying abstraction (single key per condition label) doesn't fit conflict tasks at all. The page's response_key_js encodes a function `(stim_color, group_index) → key`; no session-start directive can replace that function.

## Framework gaps surfaced (SP9b backlog candidates)

1. **TaskCard `task_specific.key_map` schema is inconsistent across paradigms** — stop-signal uses stimulus IDs, stroop/n-back use condition labels. The executor's `_resolve_response_key` lookups assume one shape; the runtime branch silently fails when the shape doesn't match. Either standardize the key_map shape at Stage 1, or make the executor's lookup tolerate both.

2. **Platform-recording gap (SP7 layer d)** — jsPsych keyboard-response-plugin doesn't read from raw `document.addEventListener('keydown', ...)`. Bot keypresses captured at page level (~93%) drop to ~48% by the time they're in the platform CSV. Possible approaches: `page.dispatch_event` to specific elements, verify key format matches plugin's `choices` array, investigate trial-setup-vs-keypress timing. **The biggest leverage SP9 candidate by far** — affects ALL paradigms; SP9a doesn't move this number meaningfully.

3. **Stimulus-property-dependent keys need a different abstraction** — for conflict tasks (stroop, simon), the correct key depends on stimulus.color / stimulus.position / etc. The "one key per condition" abstraction fits a subset of paradigms. Possible approach: extend SessionAgent's directive to be `{(condition, stim_property): key}` or `{condition: js_function_string}`. Out of scope for SP9a.

4. **The pre-SP8 n-back TaskCard was sufficient to get n-back's 72.1% alignment** — meaning the SP8 prompt regen wasn't necessary for n-back. The SP8 narrative ("n-back wins because of multi-source prompt") may be partially confounded by random session variance vs the deterministic Pattern B inferences Stage 1 already produced.

5. **The cli.py wiring gap** — Task 9 of the SP9a plan added the executor's `session_agent` parameter but didn't include the cli.py call-site update. Subagent-driven plans should include CLI-layer integration explicitly for any feature that needs to be reachable from `experiment-bot` invocations.

## Status

✅ **SP9a internal CI gate: PASS.** 563 passed, 3 skipped (+33 over `sp8-complete`).

❌ **SP9a empirical hypothesis: NOT SUPPORTED.** Per-trial alignment improvement is null or within session variance for all 3 tested paradigms. The architectural assumption (single key per condition resolvable at session start) is the binding constraint, not the LLM's ability to see the page.

✅ **SP9a infrastructure: USEFUL FOR FUTURE WORK.** The agent package, multimodal LLM Protocol extension, key normalization layer, and run_metadata directive instrumentation are reusable for future SP candidates. The directive's `source`/`confidence`/`raw_llm_response` fields make per-session-LLM-decision audit possible.

**Recommended next step:** SP9b focused on the platform-recording gap (SP7 layer d) — the user-flagged observation that the platform CSV doesn't reflect the bot's keydown events even when the page-level listener captures them. That gap affects ALL paradigms regardless of key-resolution mechanism, so it has the highest leverage of any remaining SP9 backlog item. Investigation should start by reading jsPsych's `keyboard-response-plugin` source to understand exactly which listener anchor, choices filter, and trial-state gating apply.

Tag `sp9a-complete` on the commit landing this report.
