# SP8 — Stage 1 multi-source response_key_js prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach Stage 1 to emit `response_key_js` as a multi-source fallback chain (try page's `window.correctResponse` first, computed mapping second). Re-generate TaskCards for all six paradigms and re-run a cross-paradigm audit to measure per-trial alignment improvement.

**Architecture:** Single file edit to `src/experiment_bot/prompts/system.md` (Stage 1's system prompt; loaded by `stage1_structural.py:110`). Add a `## Multi-source response_key_js extraction` section with three pattern examples + one anti-example, fenced and tagged for invariant tests. Plus one new test file. Plus cross-paradigm regen + smoke + audit. No executor code changes; no schema changes; nothing else moves.

**Tech Stack:** Python 3.12 / uv; pytest; Playwright; same Reasoner + Executor as SP7.

Reference: spec at `docs/superpowers/specs/2026-05-12-sp8-stage1-response-key-prompt-design.md`. SP7 findings at `docs/sp7-results.md`. User feedback memo at `~/.claude/projects/-Users-lobennett-grants-r01-rdoc-projects-experiment-bot/memory/feedback_avoid_paradigm_overfitting.md`: instrumentation and prompt examples must be paradigm-agnostic.

**Held-out policy reminder:** the cross-paradigm re-run produces empirical evidence. If a paradigm doesn't improve, document it as a finding and triage to a future SP. Do NOT iterate on the prompt within SP8 to chase per-paradigm passes.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `src/experiment_bot/prompts/system.md` | Stage 1's system prompt | Modified — append `## Multi-source response_key_js extraction` section (Task 2) |
| `tests/test_stage1_response_key_js_prompt.py` | Invariant test | Created (Task 1) |
| `taskcards/expfactory_flanker/<new-hash>.json` | Regenerated TaskCard | Replaces existing (Task 4) |
| `taskcards/expfactory_n_back/<new-hash>.json` | Regenerated TaskCard | Replaces (Task 4) |
| `taskcards/expfactory_stop_signal/<new-hash>.json` | Regenerated TaskCard | Replaces (Task 4) |
| `taskcards/stopit_stop_signal/<new-hash>.json` | Regenerated TaskCard | Replaces (Task 4) |
| `taskcards/expfactory_stroop/<new-hash>.json` | Regenerated TaskCard | Replaces (Task 4) |
| `taskcards/cognitionrun_stroop/<new-hash>.json` | Regenerated TaskCard | Replaces (Task 4) |
| `output/<task-name>/<timestamp>/` × 18 | Smoke sessions | Generated (Task 6; gitignored) |
| `docs/sp8-results.md` | Cross-paradigm audit report | Created (Task 8) |
| `CLAUDE.md` | Sub-project history | Modified (Task 9) |

---

## Paradigm reference

The six paradigms used across SP8's regen + audit (URLs verified from `scripts/launch.sh`):

| Label | URL | Paradigm class |
|---|---|---|
| `expfactory_flanker` | `https://deploy.expfactory.org/preview/3/` | conflict (held-out) |
| `expfactory_n_back` | `https://deploy.expfactory.org/preview/5/` | working_memory (held-out) |
| `expfactory_stop_signal` | `https://deploy.expfactory.org/preview/9/` | response_inhibition (dev) |
| `stopit_stop_signal` | `https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html` | response_inhibition (dev, alt platform) |
| `expfactory_stroop` | `https://deploy.expfactory.org/preview/10/` | conflict (dev) |
| `cognitionrun_stroop` | `https://strooptest.cognition.run/` | conflict (dev, alt platform) |

---

## Task 0: Set up SP8 worktree

**Files:**
- Worktree: `.worktrees/sp8` on branch `sp8/stage1-response-key-prompt`, branched off tag `sp7-complete`

Steps 1-3 below have already been executed by the controller. Subsequent tasks assume the worktree exists at `.worktrees/sp8` and the engineer is operating inside it.

- [x] **Step 1: `git worktree add .worktrees/sp8 -b sp8/stage1-response-key-prompt sp7-complete`** (controller)
- [x] **Step 2: Cherry-pick SP8 spec + this plan onto sp8 branch** (controller)
- [x] **Step 3: `uv sync` and verify clean baseline (524 passed)** (controller)

- [ ] **Step 4: Verify worktree state**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp8
git status
git log --oneline -5
```

Expected: clean working tree on `sp8/stage1-response-key-prompt`; log shows two cherry-picked docs commits on top of `sp7-complete`.

- [ ] **Step 5: Verify tests pass**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: `524 passed, 3 skipped`.

---

## Task 1: Invariant test for the Stage 1 prompt addendum

**Files:**
- Create: `tests/test_stage1_response_key_js_prompt.py`

TDD shape: write the failing tests FIRST so they assert exactly what Task 2 must add to the prompt.

- [ ] **Step 1: Write the test file**

Create `tests/test_stage1_response_key_js_prompt.py`:

```python
"""Invariant tests for the Stage 1 system prompt's
'Multi-source response_key_js extraction' section (SP8).

The section instructs Stage 1 to emit response_key_js as a multi-
source fallback chain: try the page's authoritative runtime variable
(window.correctResponse) first; fall back to computed DOM-derived
mappings only when the runtime variable is undefined.

Tests verify structural presence and basic JS-syntax sanity without
prescribing exact wording. The actual quality of Stage 1's output
across paradigms is verified empirically by the cross-paradigm
re-run in Task 6 of SP8's plan.

No paradigm names appear in this test file (per user-feedback
constraint memorized at
~/.claude/projects/.../memory/feedback_avoid_paradigm_overfitting.md).
"""
from __future__ import annotations
import re
from pathlib import Path


PROMPT_PATH = Path("src/experiment_bot/prompts/system.md")

# Fenced JS blocks tagged with response-key example/anti-example labels:
#   ```javascript response-key-example: runtime-variable
#   ...JS...
#   ```
_BLOCK_RE = re.compile(
    r"^```(?:javascript|js)\s+(response-key-example|response-key-anti-example):\s*([^\n]+?)\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def _blocks() -> list[tuple[str, str, str]]:
    """Return [(kind, label, body), ...] for all fenced blocks in the
    Stage 1 system prompt."""
    text = PROMPT_PATH.read_text()
    return [(m.group(1), m.group(2), m.group(3)) for m in _BLOCK_RE.finditer(text)]


def test_prompt_contains_multi_source_section():
    """The new section's canonical header must be present."""
    text = PROMPT_PATH.read_text()
    assert "Multi-source response_key_js extraction" in text, (
        "Stage 1 prompt missing the SP8 multi-source section header"
    )


def test_prompt_has_runtime_variable_example():
    """At least one runtime-variable example block exists, referencing
    window.correctResponse and a typeof guard."""
    blocks = _blocks()
    candidates = [
        body for kind, label, body in blocks
        if kind == "response-key-example" and "runtime-variable" in label
    ]
    assert candidates, "Missing response-key-example: runtime-variable block"
    body = candidates[0]
    assert "window.correctResponse" in body
    assert "typeof" in body


def test_prompt_has_dom_plus_state_example():
    """At least one dom-plus-state example block exists, and the
    window.correctResponse check appears BEFORE any DOM-derived
    computation (the fallback-chain ordering rule)."""
    blocks = _blocks()
    candidates = [
        body for kind, label, body in blocks
        if kind == "response-key-example" and "dom-plus-state" in label
    ]
    assert candidates, "Missing response-key-example: dom-plus-state block"
    body = candidates[0]
    rv_pos = body.find("window.correctResponse")
    dq_pos = body.find("document.querySelector")
    assert rv_pos != -1, "dom-plus-state example missing window.correctResponse"
    if dq_pos != -1:
        assert rv_pos < dq_pos, (
            "dom-plus-state example must check window.correctResponse BEFORE "
            "any DOM-derived computation (fallback-chain rule)"
        )


def test_prompt_has_static_keymap_explanation():
    """The static-keymap case is described in prose (no JS example).
    The prompt must mention task_specific.key_map and explain when JS
    is unnecessary."""
    text = PROMPT_PATH.read_text()
    assert "task_specific.key_map" in text or "task_specific" in text, (
        "Stage 1 prompt missing reference to task_specific.key_map"
    )


def test_prompt_has_anti_example():
    """At least one anti-example block exists showing the fragile
    static-only-without-fallback pattern that SP7 quantified."""
    blocks = _blocks()
    anti = [body for kind, label, body in blocks if kind == "response-key-anti-example"]
    assert anti, "Missing response-key-anti-example block"


def test_example_js_basic_syntax_sanity():
    """Each example/anti-example block must have balanced parens and
    braces. Catches typos; not a full JS parser."""
    for kind, label, body in _blocks():
        parens = body.count("(") - body.count(")")
        braces = body.count("{") - body.count("}")
        assert parens == 0, f"Unbalanced parens in {kind}: {label}: {parens}"
        assert braces == 0, f"Unbalanced braces in {kind}: {label}: {braces}"
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_stage1_response_key_js_prompt.py -v 2>&1 | tail -15
```

Expected: all 6 tests FAIL — the prompt section doesn't exist yet, so the regex finds no matching blocks and the header check fails.

- [ ] **Step 3: Commit the failing tests (TDD discipline — tests land before the prompt edit)**

```bash
git add tests/test_stage1_response_key_js_prompt.py
git commit -m "test(stage1): invariant tests for multi-source response_key_js section

Six tests asserting the new Stage 1 prompt section's structural
properties: section header present, runtime-variable example with
typeof guard, dom-plus-state example with fallback-chain ordering,
static-keymap explanation in prose, anti-example block, balanced
syntax in all blocks.

No paradigm names referenced (per user-feedback constraint).
Tests fail until Task 2 lands the prompt section."
```

---

## Task 2: Add the `## Multi-source response_key_js extraction` section to Stage 1's prompt

**Files:**
- Modify: `src/experiment_bot/prompts/system.md` (append)

- [ ] **Step 1: Read the current prompt structure**

```bash
wc -l src/experiment_bot/prompts/system.md
head -30 src/experiment_bot/prompts/system.md
```

Note where the existing sections end. The new section appends at the bottom.

- [ ] **Step 2: Append the new section**

Append EXACTLY this content to the end of `src/experiment_bot/prompts/system.md`:

````markdown

## Multi-source response_key_js extraction

When the page's correct response varies per trial (counterbalanced keymaps, runtime stimulus-dependent mappings, etc.), the `response_key_js` field for each stimulus must be shaped as a **multi-source fallback chain**. The chain checks the page's authoritative runtime variable FIRST, then falls back to a computed mapping only when the runtime variable is undefined.

Many platforms expose `window.correctResponse` (or equivalent runtime variable) holding the trial's expected key. When the page provides this, it is the highest-fidelity source — strictly preferred over any computation the bot does from page state. Computing the mapping from DOM and counterbalancing variables can drift from the platform's actual scoring; reading the page's own variable does not.

The three patterns below cover the canonical cases. Pick the one that matches the paradigm's runtime architecture.

### Pattern A — page exposes a runtime correct-key variable

Use this when the source code shows the page setting `window.correctResponse` (or similar variable holding the expected key) at trial start. The bot reads the variable directly; no DOM-derived computation needed.

```javascript response-key-example: runtime-variable
(typeof window.correctResponse !== 'undefined' ? window.correctResponse : null)
```

### Pattern B — page does NOT expose a runtime variable; mapping must be computed from DOM + counterbalancing state

Use this when the page's correct response depends on the displayed stimulus AND a counterbalancing variable (e.g., `window.efVars.group_index`, a participant-condition flag, etc.). Even here, the multi-source rule applies: check the runtime variable FIRST in case the page is in fact setting it. Only fall through to the computed mapping when the runtime variable is absent.

```javascript response-key-example: dom-plus-state
(() => {
  // Prefer the page's runtime variable when defined.
  if (typeof window.correctResponse !== 'undefined') return window.correctResponse;
  // Fallback: compute from DOM + counterbalancing state.
  const m = document.querySelector('<stimulus-img-selector>');
  if (!m) return null;
  const isTargetVariant = (m.src || '').includes('<target-substring>');
  const g = (window.efVars && typeof window.efVars.group_index === 'number')
    ? window.efVars.group_index : 1;
  const isLowGroup = (g >= 0 && g <= 4);
  // Replace the literal keys below with the paradigm's actual keys.
  return isTargetVariant ? (isLowGroup ? '<key-A>' : '<key-B>')
                         : (isLowGroup ? '<key-B>' : '<key-A>');
})()
```

The placeholders (`<stimulus-img-selector>`, `<target-substring>`, `<key-A>`, `<key-B>`) are illustrative. Stage 1 should fill them with the actual selectors, substrings, and key strings extracted from the source code.

### Pattern C — static keymap (no JS needed for response_key_js)

Use this when the source code defines a fixed key per condition with no runtime variability (every congruent trial answered with `f`, every incongruent with `j`, etc.). In this case, leave `response_key_js` empty for the stimulus and emit the literal key strings in `task_specific.key_map`:

```json
"task_specific": {
  "key_map": {
    "congruent": "f",
    "incongruent": "j"
  }
}
```

The executor reads `task_specific.key_map[condition]` when `response_key_js` is empty, so this is the minimal-JS path for paradigms with fixed mappings.

### Anti-example — what NOT to emit

The pattern below is fragile because it computes from DOM state WITHOUT checking for the page's runtime variable first. When the page does expose `window.correctResponse`, this anti-pattern ignores it and instead recomputes a mapping that may not match the platform's actual scoring (causing per-trial response_key drift between bot and platform):

```javascript response-key-anti-example: static-only-without-fallback
(() => {
  // BAD: no check for window.correctResponse before computing.
  const m = document.querySelector('<stimulus-img-selector>');
  return (m.src || '').includes('<target-substring>') ? '<key-A>' : '<key-B>';
})()
```

If `window.correctResponse` is defined on this page, the anti-example's drift is silent — the bot's resolved key differs from the platform's expected on counterbalancing-dependent trials, and the only way to detect this is the SP7-style keypress audit.

Always emit Pattern A or Pattern B (or omit `response_key_js` per Pattern C). Never emit the anti-example shape.
````

Note: the opening four-backtick wrap (`````markdown`) here is the markdown-fence wrapper for the example in THIS plan document. When you write to `system.md`, write the content INSIDE the wrapper (everything starting with `## Multi-source...` and ending with the closing `Never emit...` line). Do NOT include the outer `` ```markdown `` and `` ``` `` lines.

- [ ] **Step 3: Run tests to confirm pass**

```bash
uv run pytest tests/test_stage1_response_key_js_prompt.py -v 2>&1 | tail -15
```

Expected: all 6 tests PASS.

- [ ] **Step 4: Confirm full suite still passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 530 passed, 3 skipped (524 + 6 new).

If existing tests fail (e.g., a prior test asserted the prompt's line count), update those tests carefully — understand WHY they were checking the old shape before changing assertions.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/prompts/system.md
git commit -m "feat(stage1): multi-source response_key_js extraction prompt section

Appends a new section to src/experiment_bot/prompts/system.md
instructing Stage 1 to emit response_key_js as a multi-source
fallback chain (runtime variable first, then DOM-derived
computation). Three patterns (A: runtime-variable only, B: rv-then-
computed, C: static keymap with no JS) plus an anti-example showing
the fragile static-only-without-fallback shape that SP7 quantified.

Paradigm-agnostic: examples use placeholder selectors/substrings/keys
(<stimulus-img-selector>, <target-substring>, <key-A>, <key-B>) so
Stage 1 fills them per-paradigm from source code.

Per SP7 findings, paradigms where the page exposes
window.correctResponse (jsPsych keyboard-response-plugin convention
and similar) should see per-trial alignment improve from ~50% to
near 100% under this prompt."
```

---

## Task 3: Full-suite regression check

**Files:**
- None modified

- [ ] **Step 1: Run the full suite**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 530 passed, 3 skipped.

- [ ] **Step 2: Confirm clean working tree**

```bash
git status
```

Expected: nothing to commit.

- [ ] **Step 3: No commit needed (verification only).**

---

## Task 4: Re-generate all six paradigm TaskCards

**Files:**
- Replace: `taskcards/<paradigm>/<old-hash>.json` × 6 + their pilot.md + pilot_refinement_*.diff
- Working: `.reasoner-logs/sp8_regen_<paradigm>.log` × 6

The Reasoner under the new prompt should produce response_key_js shaped per Pattern A/B (with the runtime-variable check first). Wall time: 5-25 min per paradigm; can be done in parallel pairs.

- [ ] **Step 1: Delete the existing TaskCards**

```bash
for p in expfactory_flanker expfactory_n_back expfactory_stop_signal stopit_stop_signal expfactory_stroop cognitionrun_stroop; do
  rm -rf "taskcards/$p"
done
ls taskcards/ 2>&1
```

Expected: directory `taskcards/` exists but is empty (or contains only `.gitkeep` if present).

- [ ] **Step 2: Clear stale reasoner work directories**

```bash
rm -rf .reasoner_work/expfactory_flanker .reasoner_work/expfactory_n_back \
       .reasoner_work/expfactory_stop_signal .reasoner_work/stopit_stop_signal \
       .reasoner_work/expfactory_stroop .reasoner_work/cognitionrun_stroop
```

- [ ] **Step 3: Run Reasoner for each paradigm (parallel batches of 3 to limit Claude CLI concurrency)**

Batch 1 (held-outs + first dev stop_signal):

```bash
mkdir -p .reasoner-logs
(
  uv run experiment-bot-reason "https://deploy.expfactory.org/preview/3/" \
    --label expfactory_flanker --pilot-max-retries 3 -v \
    > .reasoner-logs/sp8_regen_flanker.log 2>&1 &
  uv run experiment-bot-reason "https://deploy.expfactory.org/preview/5/" \
    --label expfactory_n_back --pilot-max-retries 3 -v \
    > .reasoner-logs/sp8_regen_n_back.log 2>&1 &
  uv run experiment-bot-reason "https://deploy.expfactory.org/preview/9/" \
    --label expfactory_stop_signal --pilot-max-retries 3 -v \
    > .reasoner-logs/sp8_regen_stop_signal.log 2>&1 &
  wait
)
echo "batch 1 done"
```

Wall time: ~5-25 min for the slowest of the three.

Batch 2 (remaining three):

```bash
(
  uv run experiment-bot-reason "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" \
    --label stopit_stop_signal --pilot-max-retries 3 -v \
    > .reasoner-logs/sp8_regen_stopit.log 2>&1 &
  uv run experiment-bot-reason "https://deploy.expfactory.org/preview/10/" \
    --label expfactory_stroop --pilot-max-retries 3 -v \
    > .reasoner-logs/sp8_regen_stroop.log 2>&1 &
  uv run experiment-bot-reason "https://strooptest.cognition.run/" \
    --label cognitionrun_stroop --pilot-max-retries 3 -v \
    > .reasoner-logs/sp8_regen_cognitionrun.log 2>&1 &
  wait
)
echo "batch 2 done"
```

- [ ] **Step 4: Verify all six TaskCards exist**

```bash
ls -la taskcards/*/
```

Expected: each of the six directories contains a `.json` file. If any directory is missing, the corresponding Reasoner run failed — inspect its log:

```bash
grep -E "Stage [0-9]+ attempt|Stage2SchemaError|ParseRetryExceededError|Traceback" \
  .reasoner-logs/sp8_regen_*.log | tail -30
```

Per the held-out policy, failures are findings (document in Task 8's report). Do NOT re-tune the prompt to make a failing regen pass.

If 5 of 6 paradigms regenerate but one fails, continue with the 5 that succeeded; the report will note the failure.

- [ ] **Step 5: Commit the regenerated TaskCards**

```bash
git add taskcards/
git commit -m "chore(sp8): regenerate all six paradigm TaskCards under new prompt

Stage 1's system prompt now instructs the multi-source response_key_js
extraction pattern (SP8 Task 2). The regenerated TaskCards should
show response_key_js shaped as fallback chains starting with
'(typeof window.correctResponse !== ...' for paradigms with dynamic
key resolution.

If any paradigm's regen failed, that's documented in
docs/sp8-results.md (Task 8). Per held-out policy, no SP8 prompt
re-tuning to chase per-paradigm passes."
```

---

## Task 5: Inspect regenerated response_key_js shapes

**Files:**
- Working: stdout (captured for Task 8's report)

Verify that Stage 1 followed the new prompt patterns. This is descriptive, not a CI gate — but the result tells us whether the prompt fix is doing its job at the Stage 1 layer.

- [ ] **Step 1: Print each TaskCard's response_key_js per stimulus**

```bash
uv run python << 'PY'
import json, glob
from pathlib import Path

for paradigm_dir in sorted(Path('taskcards').iterdir()):
    if not paradigm_dir.is_dir(): continue
    tc_files = list(paradigm_dir.glob('*.json'))
    if not tc_files: continue
    d = json.load(open(tc_files[0]))
    print(f'=== {paradigm_dir.name} ({tc_files[0].name}) ===')
    for s in d.get('stimuli', []):
        rkj = s.get('response', {}).get('response_key_js') or ''
        # Classify pattern
        if not rkj:
            pattern = 'C (no JS; static keymap)'
        elif 'window.correctResponse' in rkj and rkj.lstrip().startswith('(typeof'):
            pattern = 'A (runtime-variable only)'
        elif 'window.correctResponse' in rkj:
            pattern = 'B (rv + dom-plus-state)'
        elif 'document.querySelector' in rkj or 'window.' in rkj:
            pattern = 'ANTI (static-only without fallback)'
        else:
            pattern = 'unknown'
        rkj_snippet = (rkj[:80] + '...') if len(rkj) > 80 else rkj
        print(f'  {s["id"]}: pattern={pattern}')
        print(f'    response_key_js={rkj_snippet!r}')
    print()
PY
```

The classification is a heuristic — the test in Task 1 already enforces structural rules for the PROMPT, but verifying Stage 1 actually FOLLOWED them per-paradigm is descriptive.

- [ ] **Step 2: No commit yet** (the inspection output goes into Task 8's report).

Save the printed output for Task 8 (paste it into the results doc).

---

## Task 6: Smoke runs (3 sessions × 6 paradigms)

**Files:**
- Working: `output/<task-name>/<timestamp>/` × 18 (gitignored)
- Working: `.reasoner-logs/sp8_smoke_<paradigm>.log` × 6

Wall time: ~5-15 min per session, 3 sessions per paradigm. Sequential per paradigm; can run multiple paradigms in parallel.

- [ ] **Step 1: Run 3 sessions per paradigm (parallel across paradigms)**

```bash
run_smoke () {
  local label="$1" url="$2" base_seed="$3"
  for i in 1 2 3; do
    seed=$((base_seed + i - 1))
    echo "=== ${label} session seed=${seed} ==="
    uv run experiment-bot "$url" --label "$label" --headless --seed "$seed" \
      >> ".reasoner-logs/sp8_smoke_${label}.log" 2>&1
    echo "  exit=$?"
  done
}

# Batch 1
(
  run_smoke expfactory_flanker        "https://deploy.expfactory.org/preview/3/"  8001 &
  run_smoke expfactory_n_back         "https://deploy.expfactory.org/preview/5/"  8101 &
  run_smoke expfactory_stop_signal    "https://deploy.expfactory.org/preview/9/"  8201 &
  wait
)
# Batch 2
(
  run_smoke stopit_stop_signal "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" 8301 &
  run_smoke expfactory_stroop  "https://deploy.expfactory.org/preview/10/" 8401 &
  run_smoke cognitionrun_stroop "https://strooptest.cognition.run/"        8501 &
  wait
)
echo "all smokes done"
```

Adjust `base_seed` per paradigm to keep seeds unique. The seed-prefix scheme above keeps each paradigm in its own decade.

- [ ] **Step 2: Verify 18 session directories exist (3 per paradigm where regen succeeded)**

```bash
for p in expfactory_flanker expfactory_n_back expfactory_stop_signal stopit_stop_signal expfactory_stroop cognitionrun_stroop; do
  count=$(find output/ -mindepth 2 -maxdepth 2 -type d -newermt "2026-05-12 00:00" \
            | grep -ic "$p" 2>/dev/null || echo 0)
  echo "$p: $count sessions"
done
```

Expected: each paradigm shows 3 sessions (or whatever paradigm-name the TaskCard's task.name maps to in output/).

The output directory name comes from `task.name.replace(' ', '_').lower()` per the executor's convention. The label argument might map to a different output dir name (`flanker_rdoc` vs `expfactory_flanker`); confirm via `ls output/`.

- [ ] **Step 3: No commit yet** (output/ is gitignored; outcomes feed Task 8).

---

## Task 7: Run keypress audit per paradigm

**Files:**
- Working: `.reasoner-logs/sp8_audit_<paradigm>.txt` × 6

- [ ] **Step 1: Run the audit script per paradigm**

```bash
for output_label in $(ls output/); do
  echo "=== audit: $output_label ==="
  uv run python scripts/keypress_audit.py --label "$output_label" --output-dir output \
    2>&1 | tee ".reasoner-logs/sp8_audit_${output_label}.txt"
  echo
done
```

The `output_label` is the directory name under `output/` (matches the TaskCard's task.name convention). For paradigms whose TaskCard task.name doesn't match the adapter dispatch key in `PLATFORM_ADAPTERS`, the audit will report "no adapter registered for label". Note such mismatches in Task 8's report.

- [ ] **Step 2: Save the per-paradigm aggregate `bot_intended == platform_expected` and `bot_pressed == platform_recorded` numbers**

These feed directly into Task 8's report table. The audit script's tail line per paradigm is the source-of-truth.

- [ ] **Step 3: No commit yet** (audit text files are gitignored).

---

## Task 8: Write `docs/sp8-results.md`

**Files:**
- Create: `docs/sp8-results.md`

Cross-paradigm comparison report. Mirrors SP7's structure but covers all six paradigms.

- [ ] **Step 1: Gather the data**

From Task 5: per-paradigm response_key_js pattern classification (A / B / C / anti / unknown).
From Task 7: per-paradigm audit aggregate percentages (4-way agreement).
From SP7's `docs/sp7-results.md`: baseline numbers for Flanker (49.8% / 47.7%).

- [ ] **Step 2: Write the report**

Create `docs/sp8-results.md` with this structure (replace placeholders with actual numbers):

```markdown
# SP8 — Multi-source response_key_js prompt: cross-paradigm results

**Date:** 2026-05-12 (or actual run date)
**Spec:** `docs/superpowers/specs/2026-05-12-sp8-stage1-response-key-prompt-design.md`
**Plan:** `docs/superpowers/plans/2026-05-12-sp8-stage1-response-key-prompt.md`
**Branch:** `sp8/stage1-response-key-prompt` (off `sp7-complete`)
**Tag (after this report lands):** `sp8-complete`

## Goal

Verify that Stage 1's new multi-source response_key_js prompt section produces TaskCards with the runtime-variable-first fallback pattern, and quantify the per-trial alignment improvement across six paradigms.

## Procedure

Stage 1 prompt section appended (Task 2). All six TaskCards regenerated under the new prompt (Task 4). 3 smoke sessions per paradigm (Task 6). `scripts/keypress_audit.py` per paradigm (Task 7). Per-paradigm and cross-paradigm summary below.

## Pattern classification per paradigm

| Paradigm | response_key_js pattern (per stimulus) | Stage 1 followed the new prompt? |
|---|---|---|
| expfactory_flanker | <pattern per stim> | <yes/no/partial> |
| expfactory_n_back | <pattern per stim> | <yes/no/partial> |
| expfactory_stop_signal | <pattern per stim> | <yes/no/partial> |
| stopit_stop_signal | <pattern per stim> | <yes/no/partial> |
| expfactory_stroop | <pattern per stim> | <yes/no/partial> |
| cognitionrun_stroop | <pattern per stim> | <yes/no/partial> |

## Audit aggregate per paradigm (~360 trials per paradigm)

| Paradigm | bot_pressed == page_received | page_received == platform_recorded | bot_pressed == platform_recorded | bot_intended == platform_expected | SP7 Flanker baseline |
|---|---|---|---|---|---|
| expfactory_flanker | <pct> | <pct> | <pct> | <pct> | (49.8%) |
| expfactory_n_back | <pct> | <pct> | <pct> | <pct> | n/a |
| expfactory_stop_signal | <pct> | <pct> | <pct> | <pct> | n/a |
| stopit_stop_signal | <pct> | <pct> | <pct> | <pct> | n/a |
| expfactory_stroop | <pct> | <pct> | <pct> | <pct> | n/a |
| cognitionrun_stroop | <pct> | <pct> | <pct> | <pct> | n/a |

## Reading

[Fill in per-paradigm:]
- Paradigms where bot_intended == platform_expected rose significantly: <list> — Stage 1's multi-source prompt closed the per-trial gap.
- Paradigms where it didn't rise much: <list> — either the page doesn't expose window.correctResponse (Pattern B's fallback is what matters) or Stage 1 didn't follow the new examples cleanly for this paradigm.
- Any paradigm that regressed: <list> — investigation needed (likely unrelated regen noise on other fields).

## Comparison vs SP7 baseline

SP7's Flanker baseline: `bot_intended == platform_expected` = 49.8%. SP8 Flanker: <pct>%. Improvement: <delta> percentage points.

The other five paradigms didn't have an SP7 baseline (only Flanker was audited then), but their SP8 numbers establish baselines for any future SP that regenerates them.

## Cross-paradigm framing

[Fill in:]
- If improvement is broad across paradigms: the multi-source prompt is a generalizable framework-level win.
- If improvement is patchy: identify what predicts the gap (page exposes window.correctResponse vs not; jsPsych vs other framework; etc.).

## Residual gaps for SP9+ candidates

[Fill in based on observations. Possible items:]
- Paradigms where Stage 1 still didn't follow Pattern A/B (Stage 1 prompt-engineering further needed).
- Paradigms where the page doesn't expose any runtime variable (Pattern B's fallback computation is on its own — the same brittleness SP7 quantified, now isolated to that subset).
- The non-keydown-source layer (SP7's layer d), which SP8 doesn't address.

## Internal CI gate status

Test suite at sp8-complete: 530 passed, 3 skipped (was 524 at sp7-complete; +6 new tests for the prompt invariant).

✅ Internal gate: PASS.

## Status

[Fill in based on outcome:]
- Cross-paradigm alignment improvement: <summary>.
- Generalization claim: <strengthened / unchanged / mixed>.
- Recommended next sub-project: <SP9 architectural cleanup as previously discussed, OR a more targeted fix based on SP8's residual findings>.

Tag `sp8-complete` on the commit landing this report.
```

Fill every `<placeholder>` and `[Fill in: ...]` with actual data.

- [ ] **Step 3: Sanity-check no placeholders remain**

```bash
grep -nE "<pct>|<pattern|<yes/no|<list>|<delta>|<summary|\[Fill in" docs/sp8-results.md
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add docs/sp8-results.md
git commit -m "docs(sp8): cross-paradigm response_key_js prompt results

Six paradigms regenerated under the multi-source Stage 1 prompt;
3 smoke sessions per paradigm; 4-way keypress audit per paradigm.
Per-trial alignment numbers compared vs SP7 Flanker baseline.

Per the held-out policy, findings are documented; any paradigm that
didn't improve is named, not chased by SP8 prompt re-tuning."
```

---

## Task 9: Tag, push, update CLAUDE.md

**Files:**
- Tag: `sp8-complete`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify clean state**

```bash
git status
uv run pytest 2>&1 | tail -3
```

Expected: clean working tree; 530 passed, 3 skipped.

- [ ] **Step 2: Tag**

```bash
git tag -a sp8-complete -m "$(cat <<'EOF'
SP8 (multi-source response_key_js prompt) — milestone tag

Stage 1's system prompt now contains a Multi-source response_key_js
extraction section instructing the LLM to emit response_key_js as a
fallback chain: page's runtime variable (window.correctResponse) first,
DOM-derived computation second, static keymap third. Anti-example
shows the fragile static-only-without-fallback shape SP7 quantified.

Internal: 6 new invariant tests asserting the prompt's structural
properties without prescribing exact wording. Suite at 530 passed
(was 524).

External: all six paradigm TaskCards regenerated; 3 smoke sessions
per paradigm; cross-paradigm 4-way keypress audit. See
docs/sp8-results.md for the per-paradigm bot_intended ==
platform_expected and bot_pressed == platform_recorded numbers
compared to SP7's Flanker baseline (49.8% / 47.7%).

Per user-feedback constraint: prompt examples use placeholder
selectors/substrings/keys; the invariant test references no paradigm
names; the smoke + audit run apply uniformly across paradigms.
EOF
)"
```

- [ ] **Step 3: Push**

```bash
git push -u origin sp8/stage1-response-key-prompt
git push origin sp8-complete
```

- [ ] **Step 4: Update CLAUDE.md sub-project history**

Edit `CLAUDE.md`. Find the SP8 candidate entry that SP7 added (currently says "(candidate)"). Replace with:

```markdown
- **SP8**: Stage 1 multi-source `response_key_js` prompt. SP7's named
  layer (a) — bot's response_key_js extraction is ~50% random vs
  platform's expected on dynamic-key paradigms — addressed by adding a
  Multi-source response_key_js extraction section to
  `src/experiment_bot/prompts/system.md` instructing Stage 1 to emit
  response_key_js as a fallback chain (runtime variable first,
  DOM-derived computation second, static keymap third). Internal:
  530 passed (was 524); +6 invariant tests. External: all 6 paradigm
  TaskCards regenerated; 3 smoke sessions per paradigm; cross-paradigm
  audit. See `docs/sp8-results.md`. Tag `sp8-complete`. ✓ Complete.
- **SP9** (planned): architectural cleanup brainstorm. Audit
  accumulated fragility (parallel retry mechanisms, oneOf envelopes,
  per-paradigm adapters, stage count, defensive fallback layers). User
  raised this as a strategic concern during SP8 brainstorm; SP9 is the
  dedicated cycle to map cleanup opportunities and pick the biggest
  wins. Runtime-LLM partition is a key design consideration: per-trial
  LLM calls infeasible for speeded paradigms, but setup/ITI/transition
  decisions are fair game.
```

- [ ] **Step 5: Commit and push**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): mark SP8 complete; SP9 architectural cleanup planned

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Self-review checklist

- **Spec § Goal**: Tasks 1, 2 ship the prompt + tests; Tasks 4, 6, 7 run the cross-paradigm audit; Task 8 reports.
- **Spec § Success criterion (internal CI gate)**: 6 invariant tests in Task 1. Suite goes 524 → 530.
- **Spec § Success criterion (external)**: Tasks 4-8 produce the cross-paradigm evidence.
- **Spec § Architecture (3 touch-points)**: Stage 1 prompt edit (Task 2), invariant test (Task 1), cross-paradigm run (Tasks 4-7).
- **Spec § Test strategy**: invariant tests, manual regen verification (Task 5), cross-paradigm re-run.
- **Spec § Out of scope**: no executor changes, no schema changes, no other Stage prompt edits, no architectural cleanup. ✓
- **Spec § Sub-project boundary check**: code scope is one prompt + one test file; empirical scope is wide but bounded. ✓

---

## Notes for the implementing engineer

- Held-out policy is binding: if a paradigm's regen fails (Reasoner produces no TaskCard), document and continue. Do NOT iterate on the prompt during SP8 to chase per-paradigm passes.
- The prompt's example JS uses placeholders like `<stimulus-img-selector>`, `<target-substring>`, `<key-A>`, `<key-B>` — these are illustrative for the LLM, not literal substitutions Stage 1 emits in TaskCards. Stage 1 fills them with actual selectors/keys per paradigm.
- The Reasoner's Stage 1 LLM call has the prompt as its system message; the user message is the source-code bundle. Adding a section to system.md gives Stage 1 more shape examples to follow but DOESN'T constrain it deterministically.
- Adapter mismatch in Task 7: the `keypress_audit.py` script uses `PLATFORM_ADAPTERS[label]`. The label is the OUTPUT directory name (e.g., `flanker_rdoc`), not the regen `--label` argument (e.g., `expfactory_flanker`). If the audit reports "no adapter registered," the dispatch key needs to be added — likely the task.name changed during regen. Document but don't fix in SP8.
- The audit's `bot_intended == platform_expected` is the headline number SP8 is trying to move. SP7's Flanker baseline was 49.8%; the target is "significantly above 50%, ideally toward 90% for paradigms that expose window.correctResponse."
- Wall-clock estimate: ~30 min for code (Tasks 1-3); ~30-60 min for regens (Task 4 batched in parallel); ~60-180 min for smokes (Task 6 batched); ~30 min for analysis + reporting (Tasks 7-9).
