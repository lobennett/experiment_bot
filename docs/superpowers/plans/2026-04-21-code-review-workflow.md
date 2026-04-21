# Code Review, Analysis Audit, and Batch Run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and fix the task-agnosticism claims of the `experiment-bot` core/prompts/pilot layer, audit the analysis notebook for per-platform correctness, then produce a 60-run validation dataset (15 × 4 tasks).

**Architecture:** Three-phase workflow: (0) bootstrap — bump model to Opus 4.7, wait for user's `.env`, generate 1 smoke run per task so later phases have reference output; (1) agnosticism + quality review of `src/experiment_bot/core/`, `prompts/`, `navigation/`, and the pilot loop, fixing everything inline; (2) analysis notebook audit — static, executed, and against field-standard metric references, with user iteration; (3) sequential 15-run-per-task batch.

**Tech Stack:** Python 3.12, uv, Playwright, pytest, Anthropic SDK, jupyter.

**Spec:** `docs/superpowers/specs/2026-04-21-code-review-design.md`

---

## Task 1: Bump Claude model from Opus 4.6 to 4.7

**Files:**
- Modify: `src/experiment_bot/core/analyzer.py:68`
- Test: `tests/test_analyzer.py` (verify default model)

- [ ] **Step 1: Read current model string**

Run: `rg -n 'claude-opus' src/ tests/`
Expected: single hit in `src/experiment_bot/core/analyzer.py:68` on `model: str = "claude-opus-4-6"`. If there are hits elsewhere (tests, CLI, docs), list them — they all need to change.

- [ ] **Step 2: Write/update test asserting default model**

Add or update a test in `tests/test_analyzer.py`:

```python
def test_analyzer_default_model_is_opus_4_7():
    from experiment_bot.core.analyzer import Analyzer
    a = Analyzer(client=None)
    assert a._model == "claude-opus-4-7"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_analyzer.py::test_analyzer_default_model_is_opus_4_7 -v`
Expected: FAIL with `assert 'claude-opus-4-6' == 'claude-opus-4-7'`.

- [ ] **Step 4: Change the default**

Edit `src/experiment_bot/core/analyzer.py:68` so the signature reads:

```python
    def __init__(self, client, model: str = "claude-opus-4-7", max_retries: int = 3):
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_analyzer.py::test_analyzer_default_model_is_opus_4_7 -v`
Expected: PASS.

- [ ] **Step 6: Run the full test suite to confirm no regression**

Run: `uv run pytest tests/ -q`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/core/analyzer.py tests/test_analyzer.py
git commit -m "chore: upgrade Claude model to Opus 4.7

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Wait for .env configuration

**Files:** `.env` (user-authored)

This task is a hard gate. Do NOT proceed until the user confirms the key is in place.

- [ ] **Step 1: Ask user to configure `.env`**

Post to user:

> Please copy `.env.example` to `.env` and paste your Team MAX API key into `ANTHROPIC_API_KEY`. Reply "done" when ready.

- [ ] **Step 2: Confirm `.env` exists without reading the key**

Run: `test -f /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.env && echo "OK" || echo "MISSING"`
Expected: `OK`.

- [ ] **Step 3: Confirm the env var resolves for the task runner**

Run: `cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot && uv run python -c "import os, dotenv; dotenv.load_dotenv(); k=os.environ.get('ANTHROPIC_API_KEY',''); print('len=', len(k), 'prefix=', k[:7] if k else 'EMPTY')"`
Expected: non-zero length, prefix `sk-ant-` or similar. Do NOT print the full key.

---

## Task 3: Phase 0 smoke run — 1 instance per task

**Files:** produces `output/{task}/{timestamp}/` directories, updates `cache/{label}/config.json`.

This exercises the new model + pilot loop on all four registered tasks and produces reference `experiment_data.*` files for Phase 1/2.

- [ ] **Step 1: Inspect current cache so we can diff after regeneration**

Run: `ls -la cache/*/config.json && for f in cache/*/config.json; do echo "=== $f"; jq -r '.task.name' "$f"; done`
Expected: lists 4 current cached configs with their task names.

- [ ] **Step 2: Run the test_run.sh script (regenerates + 1 run each, headless, sequential)**

Run: `bash scripts/test_run.sh 2>&1 | tee /tmp/smoke-run.log`
Expected: "RESULTS: 4/4 succeeded, 0 failed" at the end. If any failed, stop and investigate; do not proceed.

- [ ] **Step 3: Verify 4 experiment_data files produced**

Run: `find output -name 'experiment_data.*' -newer /tmp/smoke-run.log 2>/dev/null | wc -l` — if that shows 0 due to mtime quirks, instead list by task: `for t in expfactory_stop_signal expfactory_stroop stopit_stop_signal cognitionrun_stroop; do echo "=== $t"; ls -t output/$t/*/experiment_data.* 2>/dev/null | head -1; done`
Expected: one file per task, freshly created today.

- [ ] **Step 4: Confirm bot_log.json row counts are sensible per task**

Run: `for t in expfactory_stop_signal expfactory_stroop stopit_stop_signal cognitionrun_stroop; do latest=$(ls -td output/$t/*/ 2>/dev/null | head -1); if [ -n "$latest" ]; then n=$(jq 'length' "$latest/bot_log.json"); echo "$t: $n trials (dir=$latest)"; fi; done`
Expected: non-trivial trial counts for each task (stop_signal ~180, stroop ~120, stopit ~288, cognitionrun ~15 — per README).

- [ ] **Step 5: Commit the fresh cache**

```bash
git add cache/
git diff --cached --stat
git commit -m "chore: regenerate cached configs with Opus 4.7

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

If `git diff --cached --stat` is empty (no changes to cache), skip the commit. Output CSVs are already tracked separately.

---

## Task 4: Agnosticism review — `core/executor.py`

**Files:**
- Read: `src/experiment_bot/core/executor.py`
- Modify (likely): `src/experiment_bot/core/executor.py`, `src/experiment_bot/prompts/system.md`, `src/experiment_bot/prompts/schema.json`
- Create: `docs/superpowers/specs/2026-04-21-code-review-findings.md`
- Test: `tests/test_executor.py`

Known smells (from spec): `match.condition == "navigation"` at executor.py:318, `match.condition in ("attention_check", "attention_check_response")` at executor.py:326.

- [ ] **Step 1: Read executor.py end-to-end and note every non-config conditional**

Run: `rg -n '(== ?"|in \()' src/experiment_bot/core/executor.py | rg -v 'response_distributions|dom_query|js_eval|text_content|canvas_state'`
Expected: a short list of candidates. Any that compare `match.condition`, `match.stimulus_id`, `key`, or phase names against Python string literals are review candidates.

- [ ] **Step 2: Start the findings doc**

Create `docs/superpowers/specs/2026-04-21-code-review-findings.md` with header:

```markdown
# Code Review Findings — 2026-04-21

Scope: `src/experiment_bot/core/`, `src/experiment_bot/prompts/`, `src/experiment_bot/navigation/`, and the pilot validation loop.

Standard: task-agnostic, platform-agnostic per the claim in `docs/how-it-works.md`.

## Severity legend
- **Critical** — breaks the agnosticism claim or produces wrong behavior on a novel task.
- **Significant** — hidden contract or default behavior Claude cannot override via config.
- **Minor** — code quality, narrow scope, or test coverage gap.
- **Nit** — style.

## `core/executor.py`
(populated below)
```

- [ ] **Step 3: Decide on each hardcoded condition string**

For `match.condition == "navigation"` (executor.py:318) and `match.condition in ("attention_check", "attention_check_response")` (executor.py:326), pick one of:

**(a) Surface to schema** — require `runtime.navigation_stimulus_condition` (string, optional) and `runtime.attention_check.stimulus_conditions` (list). Fallback to no-op if missing.

**(b) Remove special cases** — treat navigation and attention-check stimuli as regular stimuli. Rely on phase detection + attention_check.response_js for attention, and treat a feedback-screen "Enter" press as advance-behavior rather than a special stimulus.

Default choice: **(a)**, because ripping out the special cases risks regressing the 4 validated tasks. Surface the names in schema + system prompt so Claude explicitly opts in by emitting them. Document the findings either way.

- [ ] **Step 4: Write failing tests for chosen approach**

In `tests/test_executor.py`, add:

```python
def test_navigation_condition_name_is_config_driven(monkeypatch):
    """Executor reads the navigation-stimulus condition name from config, not a hardcoded literal."""
    from experiment_bot.core.executor import TaskExecutor
    from experiment_bot.core.config import TaskConfig
    # Build a minimal config with a custom navigation condition name
    cfg_dict = _minimal_config_dict()  # helper already in the test file
    cfg_dict["runtime"]["navigation_stimulus_condition"] = "advance_screen"
    config = TaskConfig.from_dict(cfg_dict)
    executor = TaskExecutor(config)
    assert executor._navigation_condition_name == "advance_screen"


def test_attention_check_condition_names_are_config_driven():
    from experiment_bot.core.executor import TaskExecutor
    from experiment_bot.core.config import TaskConfig
    cfg_dict = _minimal_config_dict()
    cfg_dict["runtime"]["attention_check"]["stimulus_conditions"] = ["probe", "probe_resp"]
    config = TaskConfig.from_dict(cfg_dict)
    executor = TaskExecutor(config)
    assert "probe" in executor._attention_check_conditions
    assert "probe_resp" in executor._attention_check_conditions
```

(If `_minimal_config_dict` does not exist, add it based on an existing cache config like `cache/expfactory_stroop/config.json`.)

- [ ] **Step 5: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_executor.py::test_navigation_condition_name_is_config_driven tests/test_executor.py::test_attention_check_condition_names_are_config_driven -v`
Expected: FAIL — the attributes don't exist yet.

- [ ] **Step 6: Implement the config plumbing**

Edit `src/experiment_bot/core/config.py`:
- Add `navigation_stimulus_condition: str = ""` to `RuntimeConfig` (after `attention_check`).
- Add `stimulus_conditions: list[str] = field(default_factory=list)` to `AttentionCheckConfig`.
- Update `from_dict` and `to_dict` for both.

Edit `src/experiment_bot/core/executor.py`:
- In `__init__`, compute and store:

```python
self._navigation_condition_name = config.runtime.navigation_stimulus_condition or ""
self._attention_check_conditions = set(
    config.runtime.attention_check.stimulus_conditions
) or {"attention_check", "attention_check_response"}
```

- Replace the two hardcoded checks with `match.condition == self._navigation_condition_name` (guarded by truthiness — empty string disables) and `match.condition in self._attention_check_conditions`.

- [ ] **Step 7: Run tests — both new tests pass, no regressions**

Run: `uv run pytest tests/test_executor.py -v`
Expected: both new tests PASS; all pre-existing tests still PASS.

- [ ] **Step 8: Update schema and system prompt**

Edit `src/experiment_bot/prompts/schema.json`:
- Add `navigation_stimulus_condition` under `runtime` properties (string, default "").
- Add `stimulus_conditions` under `runtime.attention_check` properties (array of string, default []).

Edit `src/experiment_bot/prompts/system.md`:
- Under section 3 (Navigation Flow), add a one-paragraph note: "If the experiment has between-trial advance screens that are easier to detect as stimuli than as phase transitions, you may emit a stimulus whose `response.condition` is the `runtime.navigation_stimulus_condition` string; the executor will treat this as a screen-advance rather than a trial."
- Under section 8 (Attention Checks), add: "If you define stimulus-level attention-check detection, list the `response.condition` values in `runtime.attention_check.stimulus_conditions` so the executor dispatches to the attention-check handler rather than treating them as trials."

- [ ] **Step 9: Record the finding in the findings doc**

Append to `docs/superpowers/specs/2026-04-21-code-review-findings.md` under `## core/executor.py`:

```markdown
### Critical — hardcoded condition strings

- `executor.py:318` compared `match.condition == "navigation"` against a Python literal.
- `executor.py:326` compared `match.condition in ("attention_check", "attention_check_response")` against Python literals.

These were covert contracts: Claude had to emit exactly these strings for the executor to dispatch correctly, but nothing in `schema.json` or `system.md` required them. Novel tasks that emitted differently-named conditions would be silently mis-dispatched.

**Fix:** surfaced both to config:
- `runtime.navigation_stimulus_condition: str` (opt-in).
- `runtime.attention_check.stimulus_conditions: list[str]` (opt-in).
Backward compatibility preserved by defaulting to the legacy names when the list is empty.
```

- [ ] **Step 10: Commit**

```bash
git add src/experiment_bot/core/executor.py src/experiment_bot/core/config.py src/experiment_bot/prompts/schema.json src/experiment_bot/prompts/system.md tests/test_executor.py docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "fix(executor): make navigation and attention-check condition names config-driven

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 11: Audit remaining executor hardcoded values**

For each of the following in `executor.py`, decide whether it's structural or a behavioral default that should be config-authored; record findings in the doc and fix any that are behavioral:

- `asyncio.sleep(1.0)` at line ~321 (navigation click delay) — behavioral.
- `asyncio.sleep(1.5)` at line ~571 in `_handle_attention_check` — behavioral.
- `asyncio.sleep(2.0)` at line ~607 in `_wait_for_completion` — behavioral (settle time).
- `await asyncio.sleep(0.05)` at line ~311 (non-trial stimulus poll) — structural; OK.
- `timeout_s: float = 5.0` in `_wait_for_trial_end` — behavioral.

For each: if it's a behavioral default, surface it to `runtime.timing.*` with a sensible default matching today's value (so nothing breaks) and document the knob in `system.md`. Commit each cluster of related changes separately.

- [ ] **Step 12: Full suite regression**

Run: `uv run pytest tests/ -q`
Expected: green.

---

## Task 5: Agnosticism review — `core/config.py` defaults

**Files:**
- Read: `src/experiment_bot/core/config.py`
- Modify: `src/experiment_bot/core/config.py`, `src/experiment_bot/prompts/system.md`, `src/experiment_bot/prompts/schema.json`
- Test: `tests/test_config.py`, `tests/test_config_temporal.py`

`docs/how-it-works.md` claims: "All defaults are off or zero." Verify and either enforce this or document the exceptions.

- [ ] **Step 1: Enumerate all non-zero, non-empty defaults**

Run: `rg -n 'default(_factory)? ?=' src/experiment_bot/core/config.py | rg -v '= field\(default_factory=list' | rg -v '= ""'`
Expected: a list of numeric / boolean / non-empty defaults.

Each one goes into the findings doc as either "Structural — OK" (e.g., `viewport={"width":1280,"height":800}`) or "Behavioral default — needs review."

- [ ] **Step 2: Candidate behavioral defaults**

Likely flags to record:

- `poll_interval_ms: int = 20`
- `max_no_stimulus_polls: int = 500`
- `stuck_timeout_s: float = 10.0`
- `completion_wait_ms: int = 5000`
- `feedback_delay_ms: int = 2000`
- `omission_wait_ms: int = 2000`
- `rt_floor_ms: float = 150.0`
- `rt_cap_fraction: float = 0.90`
- `advance_keys: list[str] = [" "]`
- `feedback_fallback_keys: list[str] = ["Enter"]`
- `advance_interval_polls: int = 100`
- `failure_rt_cap_fraction: float = 0.85`
- `inhibit_wait_ms: int = 1500`
- `sigma_tau_range: list = [1.0, 1.0]`
- `min_trials: int = 20`
- `max_blocks: int = 1`

- [ ] **Step 3: Triage each**

For each candidate, record in findings doc:

```
### Significant / Minor / Structural — <field>
Default: <value>
Claim check: Does `how-it-works.md` / `system.md` require Claude to set this?
Verdict: <Structural | Require Claude to set | Acceptable default with rationale>
```

Rules of thumb:
- RT-physiology constants (e.g., `rt_floor_ms=150`) are structural — the floor is a physiological claim, not a task-level knob.
- Timing mechanics (`poll_interval_ms`, `stuck_timeout_s`) are structural — they govern how the executor polls, not how the subject behaves.
- Keys (`advance_keys=[" "]`, `feedback_fallback_keys=["Enter"]`) are behavioral defaults. If Claude doesn't populate them, the executor still works but assumes Space/Enter — an assumption that breaks on tasks where advance is a click. Require Claude to populate these if any advance/feedback handling is configured.
- `sigma_tau_range=[1.0, 1.0]` is "off" semantically (no scaling). Structural — OK.
- `failure_rt_cap_fraction=0.85`, `inhibit_wait_ms=1500` are task-specific stop-signal defaults leaked into Python. Move to "require Claude to set if trial_interrupt.detection_condition is non-empty."

- [ ] **Step 4: For each "require Claude to set" finding, add a test**

Example (`tests/test_config.py`):

```python
def test_advance_keys_empty_by_default_when_field_unset_in_dict():
    from experiment_bot.core.config import AdvanceBehaviorConfig
    cfg = AdvanceBehaviorConfig.from_dict({})
    assert cfg.advance_keys == []  # was [" "] — now requires Claude to opt in
```

Run: `uv run pytest tests/test_config.py -k advance_keys_empty -v` → FAIL.

- [ ] **Step 5: Change the defaults**

Edit `src/experiment_bot/core/config.py` to make those defaults empty where appropriate. For every default you change, update `system.md` to require Claude to set it (under the section that already discusses that config area).

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/ -q`
Expected: the new tests pass. Cached configs (from Task 3's smoke run) already contain the fields, so they still load.

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/core/config.py src/experiment_bot/prompts/*.md src/experiment_bot/prompts/*.json tests/
git commit -m "fix(config): remove leaked behavioral defaults from Python dataclasses

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Agnosticism review — `prompts/system.md` and `prompts/schema.json`

**Files:**
- Read: `src/experiment_bot/prompts/system.md`, `src/experiment_bot/prompts/schema.json`
- Modify: same files if framework-specific bias is found

- [ ] **Step 1: Search for jsPsych-specific examples**

Run: `rg -n -i 'jspsych|psytoolkit|labjs|gorilla|cognition\.run' src/experiment_bot/prompts/`
Expected: a list of hits. For each, decide whether it's:
- A single **example among many platforms** — OK.
- A **sole example** that biases Claude toward jsPsych — add parallel examples for other frameworks.
- A **selector default** like `#jspsych-content` that presupposes jsPsych — flag as Critical and generalize.

- [ ] **Step 2: Cross-check each schema field against system.md**

Run: `jq -r 'paths | map(tostring) | join(".")' src/experiment_bot/prompts/schema.json | head -60`
Expected: list of schema paths. For each path, confirm system.md explains how Claude should populate it, and that nothing in `config.py` silently fills it in with a Python default.

Record any path that is:
- In schema but not documented in system.md → Add doc.
- In system.md but not in schema → Add schema entry or remove from docs.
- Populated by Python default and not mentioned in system.md → Covered by Task 5.

- [ ] **Step 3: Record findings**

Append to findings doc under `## prompts/`:

```markdown
### <severity> — <finding>
Path in schema: <path>
Observation: <what's wrong>
Fix: <what was done>
```

- [ ] **Step 4: Apply fixes**

Edit `system.md` and `schema.json` per findings.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/prompts/ docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "fix(prompts): remove framework-specific bias, align schema with system.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Agnosticism review — `core/pilot.py`

**Files:**
- Read: `src/experiment_bot/core/pilot.py`, invocation in `cli.py:58-92`
- Modify: `src/experiment_bot/core/pilot.py` if bias found
- Test: `tests/test_pilot.py`

- [ ] **Step 1: Read pilot.py end-to-end**

Open `src/experiment_bot/core/pilot.py`. Look for:
- Hardcoded stimulus counts, block counts, or condition labels.
- Assumptions about the container selector (`#jspsych-content`) or DOM shape.
- Assumptions about how a "pilot trial" differs from a real trial — the pilot should be structurally identical except for early termination.
- Assumptions about what a successful pilot looks like (the cli.py criterion is "all target conditions observed AND trials_completed > 0 AND all selectors fired at least once" — is that complete?).

- [ ] **Step 2: Check pilot interaction with novel paradigms**

Concretely: imagine running the pilot on a task-switching paradigm (multiple cue-stimulus conditions). Does the pilot loop:
- Support > 2 target conditions? (yes, via `target_conditions: list[str]`)
- Support multi-block practice? (`max_blocks` — confirm)
- Abort gracefully if no stimulus matches in N polls?

Record findings.

- [ ] **Step 3: Apply fixes if needed; otherwise record "No issues"**

Edit `pilot.py` per findings. Update tests if signatures change.

- [ ] **Step 4: Run pilot tests**

Run: `uv run pytest tests/test_pilot.py -v`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/pilot.py tests/test_pilot.py docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "review(pilot): agnosticism audit [fixes/no-op]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(If no changes, skip the commit.)

---

## Task 8: Agnosticism review — `core/scraper.py`

**Files:**
- Read: `src/experiment_bot/core/scraper.py`
- Modify: `src/experiment_bot/core/scraper.py` if gaps found
- Test: `tests/test_scraper.py`

- [ ] **Step 1: Read scraper.py and list what it scrapes**

Open `src/experiment_bot/core/scraper.py`. Identify:
- What HTML elements are followed (`<script src>`, `<link href>`, others?).
- Whether inline `<script>` blocks are captured.
- Whether iframes, dynamic imports, or lazy-loaded resources are reachable.
- The 30KB per-file truncation — does it apply before or after deduping?

- [ ] **Step 2: Verify each of the 4 validated tasks is adequately captured**

Run (in a Python shell or one-off script):
```python
import asyncio
from experiment_bot.core.scraper import scrape_experiment_source
for url in [
    "https://deploy.expfactory.org/preview/9/",
    "https://deploy.expfactory.org/preview/10/",
    "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html",
    "https://strooptest.cognition.run/",
]:
    bundle = asyncio.run(scrape_experiment_source(url=url, hint=""))
    print(url, "files:", len(bundle.source_files),
          "total KB:", sum(len(v) for v in bundle.source_files.values()) // 1024)
```

Record file counts and sizes. If any task's critical trial-definition script is truncated by the 30KB cap, flag as Significant and raise the cap for that file type.

- [ ] **Step 3: Check inline script handling**

Use `rg -n 'script' src/experiment_bot/core/scraper.py` to confirm whether the scraper extracts the inline `<script>...</script>` contents from the page HTML. If not, this is a gap for platforms that inline their trial definitions.

Record finding.

- [ ] **Step 4: Apply fix if needed**

If inline scripts are missed, add extraction logic. Add a test in `tests/test_scraper.py` that feeds a small HTML fixture with inline script and asserts the content is captured.

- [ ] **Step 5: Run scraper tests**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/core/scraper.py tests/test_scraper.py docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "review(scraper): agnosticism audit [fixes/no-op]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(If no changes, skip the commit.)

---

## Task 9: Agnosticism review — remaining core + navigation files

**Files:**
- Read: `src/experiment_bot/core/analyzer.py`, `cache.py`, `distributions.py`, `phase_detection.py`, `stimulus.py`, `src/experiment_bot/navigation/navigator.py`, `stuck.py`, `src/experiment_bot/output/data_capture.py`, `writer.py`
- Modify: any of the above if issues found

- [ ] **Step 1: Quick read + rg scan for hardcoded strings/paths**

Run: `rg -n '(== ?"[a-z]|" ?in \(|querySelector|\.key ?== ?\")' src/experiment_bot/core/ src/experiment_bot/navigation/ src/experiment_bot/output/ | rg -v '^src/experiment_bot/core/executor.py'`
Expected: short list of candidates. Most are likely structural (JS extraction patterns, data-capture method dispatch) rather than task-specific.

- [ ] **Step 2: Record each candidate in findings doc**

Per file, write `### <file>` heading and either:
- `No issues found` — short note.
- One or more findings with severity + fix.

- [ ] **Step 3: Apply fixes if needed**

Implement any Critical/Significant findings. Minor findings may be deferred; Nit findings discarded.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/ tests/ docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "review(core): agnosticism audit of remaining files

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(If no changes, skip.)

---

## Task 10: Quality pass — error handling, dead code, test gaps

**Files:** same source tree

- [ ] **Step 1: Find bare except blocks**

Run: `rg -n 'except Exception' src/experiment_bot/ -B1 -A3`
Expected: list of handlers. Each should be one of:
- Narrowed to a specific exception type (preferred if the failure is predictable).
- Justified with a one-line comment explaining WHY silent swallow is correct (typically: JS eval against a context that may have been torn down by navigation).

Fix any that lack justification.

- [ ] **Step 2: Check for dead code**

Run: `rg -n 'def |class ' src/experiment_bot/ --type py | wc -l` and use your judgment. Look for utility functions defined but never referenced. Remove them (trust code-simplifier mindset: YAGNI).

- [ ] **Step 3: Check test coverage for agnosticism contracts**

For each field that Task 5 moved to "require Claude to set," add one test that loads each of the 4 cached configs and asserts the field is non-empty. This prevents regression where a cache goes stale.

Example in `tests/test_config.py`:

```python
import json
from pathlib import Path
import pytest

@pytest.mark.parametrize("label", [
    "expfactory_stop_signal",
    "expfactory_stroop",
    "stopit_stop_signal",
    "cognitionrun_stroop",
])
def test_cached_config_has_advance_keys(label):
    cfg_path = Path(f"cache/{label}/config.json")
    if not cfg_path.exists():
        pytest.skip(f"{label} cache not present")
    data = json.loads(cfg_path.read_text())
    keys = data.get("runtime", {}).get("advance_behavior", {}).get("advance_keys", [])
    assert keys, f"{label} has empty advance_keys — Claude did not populate"
```

- [ ] **Step 4: Run full suite**

Run: `uv run pytest tests/ -q`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/ tests/ docs/
git commit -m "chore(core): quality pass — narrow excepts, remove dead code, lock contracts

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(If no changes, skip.)

---

## Task 11: Finalize findings doc and decide on re-smoke

**Files:**
- Modify: `docs/superpowers/specs/2026-04-21-code-review-findings.md`

- [ ] **Step 1: Review findings doc for completeness**

Every file reviewed in Tasks 4–10 should have a section with either findings or "No issues found." Severity counts at the top.

- [ ] **Step 2: Add an executive summary**

Prepend a summary paragraph at the top with: total findings by severity, whether the agnosticism claim in `how-it-works.md` holds as-written or needs amendment, and a recommendation (e.g., "Critical issues all fixed; claim holds with the caveats noted under §X").

- [ ] **Step 3: Decide whether re-smoke is needed**

If any Phase 1 fix altered config.py schema, prompts/system.md, prompts/schema.json, OR changed executor behavior in a way that would change `experiment_data.*` output format, re-run Task 3 to regenerate the smoke dataset:

Run: `bash scripts/test_run.sh 2>&1 | tee /tmp/smoke-run-2.log`

If fixes did NOT touch output format (most likely case — agnosticism fixes are internal), skip re-smoke.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "docs: finalize code review findings summary

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Analysis notebook — static audit of per-platform dataframe handling

**Files:**
- Read: `scripts/analysis.ipynb`, `data/human/archive_rdoc/stop_signal.csv`, `data/human/archive_rdoc/stroop.csv`
- Modify: `scripts/analysis.ipynb` if bugs found

- [ ] **Step 1: Convert notebook cells to a reviewable form**

Run: `uv run jupyter nbconvert --to script scripts/analysis.ipynb --stdout > /tmp/analysis.py`
Open `/tmp/analysis.py` and read each platform section.

- [ ] **Step 2: For each of the 4 platforms, record in findings doc:**

```markdown
## Analysis notebook

### <Platform name>

**Bot column mapping:** <col → use>
**Human column mapping:** <col → use>
**Exclusion filter:** <applied to bot? human? what condition?>
**Trial filter:** <test phase only? practice excluded?>
**RT cleaning:** <min/max cutoffs, correct-only filter for Stroop RT?>
**Metrics:** <list>
**Issues:** <list or "None">
```

- [ ] **Step 3: Specifically cross-check these conventions**

- Stroop `congruent_rt` / `incongruent_rt` on **correct trials only**. If the notebook computes across all trials, flag.
- Stop Signal `go_rt` excludes stop trials entirely and excludes go-omissions. If omissions are included in the mean, flag.
- `mean_stop_failure_RT` restricted to stop trials with responses, not all stop trials.
- `go_omission_rate` = #(go with no response) / #(go trials total).
- Sequential effects excludes cross-block trial pairs.

- [ ] **Step 4: Record all issues found; do NOT fix yet**

Findings go into `docs/superpowers/specs/2026-04-21-code-review-findings.md` under `## Analysis notebook`. Fixes happen in Task 13 after the notebook has been executed and runtime issues are also on the table, so all analysis fixes land in one commit.

---

## Task 13: Analysis notebook — execute and fix runtime + static issues

**Files:**
- Modify: `scripts/analysis.ipynb`

- [ ] **Step 1: Execute the notebook end-to-end**

Run: `uv run jupyter nbconvert --to notebook --execute scripts/analysis.ipynb --output /tmp/analysis-executed.ipynb 2>&1 | tee /tmp/analysis-exec.log`
Expected: 0 errors. If errors, note which cell and error type in findings.

- [ ] **Step 2: Fix every error and static issue from Task 12**

Open the notebook in Jupyter (`uv run jupyter lab scripts/analysis.ipynb`) or edit cells directly via the JSON. For each fix:
- Show the before/after in a sub-bullet in the findings doc.
- Keep fixes minimal — per-platform logic is intentionally per-platform.

- [ ] **Step 3: Re-execute to verify fixes**

Run: `uv run jupyter nbconvert --to notebook --execute scripts/analysis.ipynb --output /tmp/analysis-executed-2.ipynb`
Expected: 0 errors.

- [ ] **Step 4: Spot-check the computed metrics against bot_log + experiment_data**

For one task (e.g., expfactory_stroop), hand-compute mean congruent RT from `experiment_data.csv` and confirm the notebook's reported number matches within rounding.

- [ ] **Step 5: Commit**

```bash
git add scripts/analysis.ipynb docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "fix(analysis): correct per-platform dataframe handling bugs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Analysis notebook — verify metrics against field standards

**Files:** `scripts/analysis.ipynb`

- [ ] **Step 1: For each metric, state the field-standard definition**

Record in findings doc under a new `### Metric definitions check` subsection:

- **Mean RT** — mean response time on correct trials where a response was made, per condition.
- **Accuracy** — fraction of responded trials where response matched target.
- **Omission rate** — fraction of trials with no response within the response window.
- **SSRT (integration method, Verbruggen et al. 2019)** — `SSRT = nth_percentile(go_RT_distribution, P(respond|stop)) − mean(SSD)`, where `P(respond|stop)` is the stop-failure rate, and the go RT distribution includes go-omissions set to the maximum go RT (per convention).
- **Post-error slowing (Dutilh et al. 2012 'robust' method)** — paired-difference mean: `mean(RT_{t+1} | error_t) − mean(RT_{t−1} | error_t)`, restricted to within-block, correct-surrounding pairs.
- **Lag-1 RT autocorrelation** — Pearson r between `RT_t` and `RT_{t−1}` on consecutive within-block correct trials.
- **Gratton (condition repetition) effect** — RT(switch) − RT(repeat), within-block only.

- [ ] **Step 2: Compare notebook implementation against each definition**

For each metric, read the implementation and record divergences:

```markdown
### <Metric> — divergence or match
Field definition: <above>
Notebook implementation: <quote or paraphrase>
Divergence: <specific difference or "None">
Fix: <what was done, or "awaiting user references" if uncertain>
```

- [ ] **Step 3: Present divergence list to user and ask for references**

Post to user:

> Analysis audit complete. I found the following divergences from field-standard metric definitions: <list>. Can you share references for any of these where you want me to match a specific source (rather than my best reading of the literature)?

- [ ] **Step 4: Wait for user references**

- [ ] **Step 5: Apply any requested alignments**

Edit notebook cells, re-execute, verify numbers change as expected.

- [ ] **Step 6: Commit**

```bash
git add scripts/analysis.ipynb docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "fix(analysis): align metric definitions with field-standard references

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Iterate on analysis feedback from user

**Files:** `scripts/analysis.ipynb`, findings doc

- [ ] **Step 1: Collect all open user feedback**

Scroll back through the conversation since Task 14. List every comment from the user that requests an analysis change.

- [ ] **Step 2: Address each comment**

For each, note in findings doc:
- Comment (verbatim).
- Resolution (the fix or "no action — reason").
- Commit SHA.

- [ ] **Step 3: Re-execute notebook, confirm no new errors**

Run: `uv run jupyter nbconvert --to notebook --execute scripts/analysis.ipynb --output /tmp/analysis-executed-final.ipynb`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add scripts/analysis.ipynb docs/superpowers/specs/2026-04-21-code-review-findings.md
git commit -m "fix(analysis): address user review feedback

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Phase 3 batch run — 15 × 4 tasks sequential

**Files:** produces `output/{task}/{timestamp}/` ×60, updates `data/bot/*.csv`

- [ ] **Step 1: Sanity check before launch**

Run: `ls cache/*/config.json | wc -l` — expect 4.
Run: `uv run pytest tests/ -q` — expect green.
Run: `find output -name 'experiment_data.*' | wc -l` — record the pre-run count.

- [ ] **Step 2: Launch in background**

Run (in background via Bash tool's `run_in_background: true`):

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot
bash scripts/batch_run.sh --count 15 --headless --regenerate 2>&1 | tee /tmp/batch-run.log
```

Do not sleep or poll; the Bash tool notifies on completion.

- [ ] **Step 3: On completion, parse the log**

Run: `tail -5 /tmp/batch-run.log`
Expected: `DONE: N/60 succeeded, M failed` with M ≤ 6 (10% threshold).

If M > 6: stop, report to user, do not proceed to post-batch notebook run.

- [ ] **Step 4: Confirm row counts**

Run: `find output -name 'experiment_data.*' | wc -l` — should be pre-run count + 60 (minus any failures).

- [ ] **Step 5: Re-execute the analysis notebook on the full dataset**

Run: `uv run jupyter nbconvert --to notebook --execute scripts/analysis.ipynb --output /tmp/analysis-post-batch.ipynb`
Expected: 0 errors; `data/bot/stop_signal.csv` and `data/bot/stroop.csv` now include ~30 rows each (15 per platform × 2 platforms per task type).

- [ ] **Step 6: Commit updated bot CSVs and notebook outputs**

```bash
git add data/bot/*.csv scripts/analysis.ipynb
git commit -m "feat: add 60-run validation dataset (15 × 4 tasks, Opus 4.7)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Report to user**

Post summary:

> Batch complete: <N>/60 succeeded, <M> failed. Bot CSVs updated at `data/bot/stop_signal.csv` and `data/bot/stroop.csv`. Notebook re-executed; figures refreshed. Findings doc at `docs/superpowers/specs/2026-04-21-code-review-findings.md`.

---

## Execution notes

**If a batch run fails partway:** `batch_run.sh` already continues past individual failures. If the failure rate creeps up (e.g., > 3 failures in the first 12 runs = 25% rate), abort and investigate before wasting more wall-clock.

**If Claude API rate-limited:** `--regenerate` only triggers on the first run per task (4 total API calls). Subsequent 56 runs use cache. Unlikely to hit Team MAX rate limit but if so, re-run from the last completed task by editing `TASKS` in the script temporarily or running the tasks individually.

**Resumability:** there is no built-in resume. If the machine sleeps or the process dies, note the completed count and re-invoke with fewer remaining instances.

**Worktree:** this plan should be executed in a worktree if you want isolation from other work on `main`. Use `superpowers:using-git-worktrees` to create one.
