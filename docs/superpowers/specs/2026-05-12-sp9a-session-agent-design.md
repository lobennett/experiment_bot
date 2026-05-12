# SP9a — Session-time runtime LLM for key-mapping resolution

**Date:** 2026-05-12
**Parent tag:** `sp8-complete`
**Worktree:** `.worktrees/sp9a` off `sp8-complete`
**Target tag:** `sp9a-complete`

## 1. Motivation

SP8 (`docs/sp8-results.md`) regenerated TaskCards under a multi-source
`response_key_js` prompt. Per-trial alignment (`bot_intended_correct ==
platform_expected`) split by paradigm:

| Paradigm | Alignment | Page exposes `window.correctResponse`? |
|---|---|---|
| n-back | 72.1% | yes |
| stop_signal_expfactory | 44.7% | no |
| stop-it_jspsych | 35.0% | no |
| expfactory_stroop | 28.9% | no (and systematically inverted) |

The Pattern B DOM-derived fallback is unreliable: Stage 1 inferring the
counterbalancing-key mapping from source code is the SP7-identified layer (a)
failure. SP8's prompt fix helps where the page exposes a runtime variable; it
does not help otherwise.

**Hypothesis.** A runtime LLM call at session start — after navigation
completes, before stimuli begin, with access to live DOM + screenshot +
window globals + TaskCard's claimed mapping — can resolve the key mapping
correctly for paradigms without `window.correctResponse`. Target: bring
stroop/stop_signal/stop-it per-trial alignment toward n-back-level (~70%+)
without regressing n-back.

## 2. Architecture

One-call-per-session runtime LLM judgment, complementing (not replacing)
the Stage 1-6 Reasoner pipeline. The framework continues to support
fresh-repo TaskCard regeneration via the existing pipeline; SessionAgent
runs at execution time using whichever TaskCard is loaded.

### Modules (new)

- `src/experiment_bot/agent/__init__.py`
- `src/experiment_bot/agent/types.py` — `KeyMappingDirective` dataclass:
  ```python
  @dataclass
  class KeyMappingDirective:
      mapping: dict[str, str]           # {condition: key}
      source: Literal[
          "window_correctresponse",
          "dom_inference",
          "screenshot_inference",
          "llm_failure_fallback",
      ]
      confidence: float                  # 0.0-1.0, LLM-self-reported
      raw_llm_response: str
      elapsed_ms: float

      def to_dict(self) -> dict: ...
  ```
- `src/experiment_bot/agent/page_probe.py` — async helpers:
  - `async def snapshot_window_globals(page: Page) -> dict` — evaluates
    `Object.keys(window).filter(k => /response|correct|key|stim/i.test(k))`
    and reads their values (truncated to 200 chars each). Read-only;
    state-restoring.
  - `async def snapshot_dom_summary(page: Page) -> str` — `page.content()`
    truncated to 20KB, then heuristic compression: keep `<script>`,
    `<style>` ≤ 2KB each, full body innerHTML up to 10KB.
  - `async def capture_screenshot(page: Page) -> bytes` — PNG, viewport
    only, full color. Returns raw bytes for the multimodal LLM call.
- `src/experiment_bot/agent/session_agent.py` — `SessionAgent` class:
  ```python
  class SessionAgent:
      def __init__(self, client: LLMClient, model: str = "claude-haiku-4-5"):
          self._client = client
          self._model = model

      async def resolve_key_mapping(
          self,
          page: Page,
          task_card: dict,
          observed_stimulus_examples: list[dict] | None = None,
      ) -> KeyMappingDirective:
          """Probe the page, prompt the LLM, return a directive. Never raises:
          LLM failure → directive with source='llm_failure_fallback' and
          mapping=task_card's static keymap."""
  ```

### Modified

- `src/experiment_bot/core/executor.py` — after `await self._navigator
  .execute_all(page, self._config.navigation)` (currently line 306), invoke
  SessionAgent when enabled, cache `directive.mapping` into a new
  `self._runtime_key_mapping: dict[str, str] | None` field. Modify
  `_resolve_response_key` (currently line 168) to check
  `self._runtime_key_mapping` before any per-stimulus / global / static
  fallback. The directive is written to `run_metadata.json` via the
  existing `_writer.update_run_metadata` channel.
- `src/experiment_bot/core/config.py` — add `session_agent_enabled: bool
  = True` to the runtime config block. Flag can be toggled off in tests
  and for ablation comparisons.

### Integration point — exact patch shape

```python
# core/executor.py (after _navigator.execute_all, ~line 306-310)
await self._navigator.execute_all(page, self._config.navigation)
await self._install_keydown_listener(page)  # existing from SP7

if self._session_agent_enabled:
    directive = await self._session_agent.resolve_key_mapping(
        page=page,
        task_card=self._config.to_dict(),
    )
    self._runtime_key_mapping = directive.mapping
    self._writer.update_run_metadata({
        "session_agent_directive": directive.to_dict(),
    })

# _resolve_response_key — runtime mapping checked FIRST
async def _resolve_response_key(self, match: StimulusMatch, page: Page | None = None) -> str | None:
    if self._runtime_key_mapping is not None:
        key = self._runtime_key_mapping.get(match.condition)
        if key:
            self._seen_response_keys.add(key)
            return key
    # Existing fallback chain (per-stimulus response_key, response_key_js,
    # global response_key_js, static keymap) unchanged below.
```

### LLM client

Reuses the existing `LLMClient` Protocol from `src/experiment_bot/llm/
protocol.py`. The SessionAgent calls `client.complete(system=..., user=...,
output_format="json")`. Screenshot is base64-encoded and embedded in the
`user` payload using the multimodal content shape the existing
`ClaudeCLIClient` / `ClaudeAPIClient` already support for Stage 2's
DOM-and-screenshot calls (if either client lacks image support, add it as
part of SP9a; the cli_client may need a small extension).

## 3. Speed handling for fast stimuli

The user-raised concern: stop-signal stimuli can appear with sub-second
windows, so per-trial LLM calls are infeasible.

**Resolution.** SessionAgent's LLM call happens **once per session, at
setup time, after navigation completes and before the first trial begins.**
The result (`directive.mapping`) is cached in `self._runtime_key_mapping`
as a plain Python dict.

During the trial loop, `_resolve_response_key` is a synchronous dict
lookup on the cached mapping. No LLM call per trial. No new network
latency during stimulus polling.

Total LLM overhead per session: ~2-5 seconds at start (one
`claude-haiku-4-5` call with DOM summary + screenshot). This is added to
the navigation-completion-to-first-stimulus gap, which already includes
fullscreen prompts, instruction screens, practice blocks, etc. The user
will not perceive added latency at stimulus presentation.

If the LLM call fails or times out (default timeout: 30s), SessionAgent
returns a directive with `source='llm_failure_fallback'` and
`mapping=task_card`'s static keymap. Executor caches it, `_resolve_
response_key` uses it for the first trial, and the existing SP8 fallback
chain (per-stimulus / global / static) still runs for any condition not
in the mapping. No regression from SP8 state.

Paradigm-agnostic: works equally for fast (stop-signal) and slow (n-back)
paradigms because the LLM cost is amortized over the whole session.

## 4. Test strategy

### Unit tests — `tests/test_session_agent.py` (new)

Deterministic given inputs. Use `AsyncMock` for Playwright page, stub
`LLMClient` returning scripted responses:

1. `test_resolve_key_mapping_uses_window_correctresponse_when_available`
2. `test_resolve_key_mapping_handles_llm_failure_returns_static_fallback`
3. `test_resolve_key_mapping_handles_malformed_llm_response`
4. `test_resolve_key_mapping_includes_screenshot_in_prompt`
5. `test_resolve_key_mapping_truncates_dom_to_20kb`
6. `test_page_probe_window_globals_filters_to_response_state`
7. `test_page_probe_dom_summary_truncates_above_20kb`
8. `test_directive_dataclass_to_dict_roundtrip`

### Integration tests — `tests/test_executor_session_agent_integration.py` (new)

Stub the executor's external surfaces, mock SessionAgent:

1. `test_executor_invokes_session_agent_after_navigator_execute_all`
2. `test_executor_caches_runtime_mapping_from_directive`
3. `test_resolve_response_key_prefers_runtime_mapping_over_static`
4. `test_resolve_response_key_falls_back_when_condition_missing_from_mapping`
5. `test_session_agent_disabled_via_config_flag_skips_invocation`

### Held-out empirical test (manual, descriptive)

Re-run the 4 working TaskCards from SP8. **No TaskCard regen.** 3 smoke
sessions per paradigm × 4 paradigms = 12 sessions.

Seed plan (avoids overlap with SP7/SP8 audit seeds):
- n-back: 9001, 9002, 9003
- stop_signal_expfactory: 9101, 9102, 9103
- expfactory_stroop: 9201, 9202, 9203
- stop-it_jspsych: 9301, 9302, 9303

Re-run the SP7 keypress audit (`scripts/keypress_audit.py`) against the
new sessions. Comparison table written to `docs/sp9a-results.md`:

| Paradigm | SP8 `bot_intended == platform_expected` | SP9a target |
|---|---|---|
| n-back | 72.1% | ≥72% (no regression — already wins via `window.correctResponse`) |
| stop_signal_expfactory | 44.7% | significantly higher (target ~65%+) |
| expfactory_stroop | 28.9% | significantly higher (target ~65%+) |
| stop-it_jspsych | 35.0% | significantly higher (target ~65%+) |

A "significantly higher" descriptive read is honest about what one
session sweep can show. If targets are missed for ≥2 paradigms, SP9a's
report frames it as "runtime LLM at session-start did not close the gap"
and surfaces what the directive *did* return (via run_metadata) so the
next SP can target the specific failure mode.

If improvement is uniform across stroop/stop-signal/stop-it, that is the
strongest empirical evidence yet for the framework's G1 generalizability
claim: runtime intelligence at the framework layer closes paradigm-
conditional gaps the static pipeline can't.

## 5. Deliverables

### Workspace

Branch `.worktrees/sp9a` off `sp8-complete`. Setup follows
`superpowers:using-git-worktrees`.

### Files

**New:**
- `src/experiment_bot/agent/__init__.py`
- `src/experiment_bot/agent/types.py`
- `src/experiment_bot/agent/page_probe.py`
- `src/experiment_bot/agent/session_agent.py`
- `tests/test_session_agent.py` (8 unit tests)
- `tests/test_executor_session_agent_integration.py` (5 integration tests)
- `docs/sp9a-results.md` (empirical results report)

**Modified:**
- `src/experiment_bot/core/executor.py` — SessionAgent invocation after
  `_navigator.execute_all`; `_runtime_key_mapping` field;
  `_resolve_response_key` prefers runtime mapping; constructor accepts
  `session_agent` and `session_agent_enabled` parameters.
- `src/experiment_bot/core/config.py` — `session_agent_enabled: bool =
  True` on the runtime config block.
- `src/experiment_bot/llm/cli_client.py` and/or `api_client.py` — extend
  if image support is incomplete (verify before modifying).
- `CLAUDE.md` — append SP9a to the sub-project history block.
- `docs/reviewer-1-charter.md` — bump "Last reviewed at" to
  `sp9a-complete`; add SP9a to threat model if the SessionAgent's
  failure surface introduces new probe candidates.

### Run metadata

Every session writes `session_agent_directive` into
`output/<paradigm>/<timestamp>/run_metadata.json`:

```json
{
  "session_agent_directive": {
    "mapping": {"congruent": "z", "incongruent": "/"},
    "source": "screenshot_inference",
    "confidence": 0.85,
    "raw_llm_response": "<full text>",
    "elapsed_ms": 2847.3
  }
}
```

This is the audit trail. SP9a's results report cross-tabulates `source`
against `bot_intended == platform_expected` to show which inference path
correlates with success.

### Tag

`sp9a-complete` on the commit landing `docs/sp9a-results.md`.

## 6. Out of scope

Explicitly NOT touching in SP9a:

- **TaskCard regeneration** — user is token-constrained. Reuse SP8's
  TaskCards as-is. Stage 1-6 Reasoner pipeline preserved exactly.
- **Stage 4 `openalex.py` list/string crash** (SP8 backlog #1) — defer
  to a separate SP9b 1-line fix.
- **Stage 6 pilot timing fragility** (SP8 backlog #2) — 1500ms
  navigator timeout is not an SP9a concern.
- **cognitionrun_stroop revival** — no TaskCard from SP8, stays
  excluded. SP9b candidate after Stage 6 fix.
- **expfactory_flanker re-add** — blocked by Stage 4 crash. Once SP9b
  lands the 1-line fix, Flanker can be regenerated and SP9c could
  audit it. In SP9a it stays excluded.
- **Platform-side response recording** (SP7 layer d) — `page_received ==
  platform_recorded` at 26-64% is jsPsych internals; not fixable from
  our side. SP9a does not claim to move this metric.
- **Per-trial runtime LLM calls** — rejected for speed. SessionAgent is
  one-call-per-session at setup.
- **Multi-turn LLM during session** — one call, then exit.
- **Non-keymapping SessionAgent decisions** — stimulus-onset detection,
  fixation handling, attention checks, feedback parsing all stay with
  Stage 1-6 / executor. SP9a's SessionAgent owns `KeyMappingDirective`
  only.
- **Changes to Stage 1 system prompt** — `src/experiment_bot/prompts/
  system.md` stays exactly at SP8 state.

## Open questions deferred to implementation

1. Does the existing `ClaudeCLIClient` already support image payloads, or
   does SP9a need to extend it? Verify in Task 1 of the plan; extend only
   if missing.
2. What does `KeyMappingDirective.mapping`'s key namespace need to match
   — TaskCard's `condition` names from `tc.stimuli[i].condition`, or
   something normalized? Check existing `_resolve_response_key`'s
   `match.condition` source and align.
3. Is there a paradigm where SessionAgent should NOT run (e.g., a
   single-key paradigm where the mapping is trivial)? Probably not — the
   directive is cheap and the failure-fallback path is safe — but
   confirm during implementation.
