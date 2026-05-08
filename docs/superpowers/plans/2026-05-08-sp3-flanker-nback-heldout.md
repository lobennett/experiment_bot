# SP3 — Held-out generalization test (Flanker + n-back) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empirical evidence that the experiment-bot framework generalizes to two paradigms it was never iterated against — Flanker (within conflict class) and n-back (across to working_memory). Produces TaskCards, 5 smoke sessions per paradigm, validation reports, platform adapters, and a combined `docs/sp3-heldout-results.md`.

**Architecture:** Strict held-out — no prompt edits, no TaskCard tuning. Allowed code changes are mechanical platform adapters and defensive validator fixes only. Failures are documented and triaged to SP4 backlog, not patched in SP3.

**Tech Stack:** Python 3.12 / uv; existing experiment-bot pipeline (`experiment-bot-reason`, `experiment-bot`, `experiment-bot-validate`); Playwright for smoke runs; `pytest` for adapter unit tests; jsonschema-gated Stage 2 already in place from SP2.

Reference: spec at `docs/superpowers/specs/2026-05-08-sp3-flanker-nback-heldout-design.md`. Held-out policy is binding: if the Reasoner fails to produce a working TaskCard for either paradigm, log the failure in the SP3 report and stop. Do not modify prompts, schemas, or stage code to make a held-out paradigm pass.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `taskcards/expfactory_flanker/<hash>.json` | Flanker TaskCard | Created by Reasoner (Task 2) |
| `taskcards/expfactory_n_back/<hash>.json` | N-back TaskCard | Created by Reasoner (Task 8) |
| `output/<task-name>/<timestamp>/` | Per-session output (bot_log.json, experiment_data.{csv,json}, run_metadata.json, screenshots) | Created by Executor (Tasks 4, 10) |
| `src/experiment_bot/validation/platform_adapters.py` | Add `read_expfactory_flanker` and possibly `read_expfactory_n_back` | Modified (Tasks 5, 11) |
| `tests/test_platform_adapters.py` | Adapter unit tests with sample CSV/JSON | Modified (Tasks 5, 11) |
| `validation/sp3_heldout/<label>_<timestamp>.json` | Validation reports | Created by validator (Tasks 6, 12) |
| `docs/sp3-heldout-results.md` | Combined SP3 results doc | Created (Task 13) |

---

## Task 0: Set up SP3 worktree

**Files:**
- Worktree: `.worktrees/sp3` on branch `sp3/heldout-validation`, branched off tag `sp2.5-complete`

`sp2.5-complete` is the post-SP2.5-hardening framework state at commit
`577f685`. It includes the navigator fix and run-metadata
instrumentation that brought bot go-trial accuracy from 77.5% to 95%
on the dev paradigms. The original `sp2-complete` tag predates these
fixes; do **not** branch off it. The sp3 branch additionally
cherry-picks the spec and this plan from `sp2/behavioral-fidelity`,
so both docs are present in the working tree.

Steps 1-3 below have already been executed by the controller and are
checked off. Subsequent tasks assume the worktree exists at
`.worktrees/sp3` and the engineer is operating inside it.

- [x] **Step 1: Tag `sp2.5-complete` at `577f685`** (controller)
- [x] **Step 2: `git worktree add .worktrees/sp3 -b sp3/heldout-validation sp2.5-complete`** (controller)
- [x] **Step 3: Cherry-pick spec + plan commits onto sp3** (controller)

- [ ] **Step 4: Verify the worktree's clean state**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp3
git status
git log --oneline -5
```

Expected: clean working tree on `sp3/heldout-validation`; recent log shows the two cherry-picked docs commits on top of `577f685`.

- [ ] **Step 5: Install dependencies in the new worktree**

```bash
uv sync
```

Expected: dependencies installed into `.worktrees/sp3/.venv`.

- [ ] **Step 6: Verify tests pass on this branch**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: `468 passed, 1 skipped` (matches sp2.5-complete state).

- [ ] **Step 7: Create the SP3 validation reports directory + placeholder**

```bash
mkdir -p validation/sp3_heldout
touch validation/sp3_heldout/.gitkeep
git add validation/sp3_heldout/.gitkeep
git commit -m "chore(sp3): create validation/sp3_heldout/ for held-out reports"
```

---

## Task 1: Clear stale n-back stage partials

**Files:**
- Modify: `.reasoner_work/expfactory_n_back/` (delete stages 1-5)

The `.reasoner_work/expfactory_n_back/` directory contains stage partials from the 2026-05-06 n-back held-out test, predating the audit refactors and SP1.5/SP2 prompts/validators. Those partials would be loaded by `--resume` and produce a TaskCard not actually under the post-audit framework — defeating the purpose of the re-test.

- [ ] **Step 1: Confirm the stale partials**

```bash
ls -la .reasoner_work/expfactory_n_back/
```

Expected: stage1-5.json files dated around 2026-05-06.

- [ ] **Step 2: Delete the stale partials**

```bash
rm -fv .reasoner_work/expfactory_n_back/stage{1,2,3,4,5,6}.json
```

Expected: stage files removed.

- [ ] **Step 3: Verify directory is empty (or doesn't exist)**

```bash
ls .reasoner_work/expfactory_n_back/ 2>&1 || echo "(removed)"
```

Expected: empty or "(removed)".

- [ ] **Step 4: Commit the cleanup (if directory still exists)**

```bash
[ -d .reasoner_work/expfactory_n_back ] && rmdir .reasoner_work/expfactory_n_back || true
git status
```

No commit needed if the directory is already gitignored (it should be — `.reasoner_work/` is in `.gitignore`).

---

## Task 2: Regenerate Flanker TaskCard

**Files:**
- Output: `taskcards/expfactory_flanker/<hash>.json`
- Output: `taskcards/expfactory_flanker/pilot.md`
- Working: `.reasoner-logs/sp3_flanker_regen.log`

This task runs the Reasoner against the Flanker URL with the framework as it stands at `sp2-complete`. No prompt overrides. If Stage 6 pilot needs refinement, that's the framework's normal operation, not paradigm-specific iteration.

- [ ] **Step 1: Confirm no existing Flanker TaskCard**

```bash
ls taskcards/expfactory_flanker/ 2>&1 || echo "(no taskcards yet)"
```

Expected: directory absent or empty (this is a held-out paradigm; nothing should be there).

- [ ] **Step 2: Confirm the Reasoner CLI works on simple input**

```bash
uv run experiment-bot-reason --help 2>&1 | head -10
```

Expected: usage message lists `--label`, `--pilot-max-retries` flags.

- [ ] **Step 3: Run the Reasoner**

```bash
mkdir -p .reasoner-logs
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/3/" \
  --label expfactory_flanker --pilot-max-retries 3 -v \
  > .reasoner-logs/sp3_flanker_regen.log 2>&1
echo "exit=$?"
```

This takes ~5–25 minutes (Reasoner runs Stages 1-5 then Stage 6 pilot, possibly with refinements). The `-v` flag is for diagnostics only; the Reasoner itself runs the same regardless.

Expected on success: `exit=0` and `taskcards/expfactory_flanker/<hash>.json` exists. If `exit=1`, see Step 4.

- [ ] **Step 4: If the Reasoner failed — STOP and document**

If Step 3 returned a non-zero exit, the framework failed to produce a Flanker TaskCard. **Do not retry with different flags or modify any prompt.** Inspect the log:

```bash
grep -E "Stage [0-9]+ attempt|Stage2SchemaError|JSONDecodeError|PilotValidationError|Traceback" \
  .reasoner-logs/sp3_flanker_regen.log | tail -20
```

Document the failure mode in `docs/sp3-heldout-results.md` (Task 13 will set this file up; for now create a placeholder note with the failure type and stage where it occurred). Then skip to Task 7 — n-back is independent, so the test can still produce one data point.

- [ ] **Step 5: Sanity-check the produced TaskCard**

```bash
uv run python -c "
import json, glob
f = glob.glob('taskcards/expfactory_flanker/*.json')[0]
d = json.load(open(f))
print(f'file: {f}')
print(f'  task.name: {d[\"task\"].get(\"name\")}')
print(f'  paradigm_classes: {d[\"task\"].get(\"paradigm_classes\")}')
print(f'  response_distributions: {list(d.get(\"response_distributions\", {}).keys())}')
print(f'  navigation phases: {len(d.get(\"navigation\", {}).get(\"phases\", []))}')
te = d.get('temporal_effects', {})
for k in te:
    val = te[k].get('value', te[k]) if isinstance(te[k], dict) else te[k]
    if isinstance(val, dict): print(f'  {k}.enabled = {val.get(\"enabled\")}')
"
```

Expected: prints task metadata. Confirms operational pass at the Reasoner stage. Do not modify anything based on what's printed; this is descriptive only.

- [ ] **Step 6: Commit the Flanker TaskCard + pilot artifacts**

```bash
git add taskcards/expfactory_flanker/
git commit -m "chore(sp3): held-out Flanker TaskCard from Reasoner pipeline

Regenerated under sp2-complete framework. No prompt overrides; no
TaskCard hand-tuning. Stage 6 pilot refinements (if any) recorded
as pilot_refinement_*.diff for provenance."
```

---

## Task 3: Inspect one Flanker session's data shape (before adapter work)

**Files:**
- Output: `output/<flanker-task-name>/<timestamp>/experiment_data.{csv,json}`

To write a correct platform adapter (Task 5), we need to know what the platform's data export looks like. Run a single Flanker session first and inspect the export shape. (Adapter without ground-truth data would be guesswork.)

- [ ] **Step 1: Run a single Flanker smoke session**

```bash
uv run experiment-bot "https://deploy.expfactory.org/preview/3/" \
  --label expfactory_flanker --headless --seed 1001 \
  > .reasoner-logs/sp3_flanker_session1.log 2>&1
echo "exit=$?"
```

Expected: `exit=0` and a new directory under `output/<flanker-task-name>/<timestamp>/`. The directory name comes from the TaskCard's `task.name`; check it:

```bash
find output -mindepth 2 -maxdepth 2 -type d -newermt "2026-05-08 00:00" | head
```

- [ ] **Step 2: Identify the Flanker output directory**

```bash
FLANKER_OUT=$(find output -mindepth 2 -maxdepth 2 -type d -newermt "2026-05-08 00:00" | head -1)
echo "Flanker output: $FLANKER_OUT"
ls "$FLANKER_OUT"
```

Expected: directory with `bot_log.json`, `config.json`, `experiment_data.{csv|json}`, `run_metadata.json`, `screenshots/`.

- [ ] **Step 3: Inspect the data export schema**

```bash
uv run python << 'PY'
import json, csv
from pathlib import Path
ses = sorted(Path('output').iterdir())[-1]
ses = sorted(p for p in ses.iterdir() if p.is_dir())[-1]
print(f'session: {ses}')
for ext in ('json', 'csv'):
    f = ses / f'experiment_data.{ext}'
    if f.exists():
        print(f'  format: {ext}')
        if ext == 'json':
            data = json.load(open(f))
            print(f'  rows: {len(data) if isinstance(data, list) else "(not a list)"}')
            if isinstance(data, list) and data:
                print(f'  first-row keys: {sorted(data[0].keys())}')
        else:
            rows = list(csv.DictReader(open(f)))
            print(f'  rows: {len(rows)}')
            if rows:
                print(f'  first-row keys: {sorted(rows[0].keys())}')
        break
PY
```

This output drives the adapter design in Task 5. Note three things from the output:

1. The format (CSV or JSON).
2. The set of fields per row.
3. Which fields hold `condition` (typically `congruent` / `incongruent` / similar), `rt`, `correct_trial` or equivalent, and any test-phase filter (typically `exp_stage` or `trial_id`).

- [ ] **Step 4: Commit the first Flanker session**

```bash
git add output/<flanker-task-name>/
git commit -m "chore(sp3): first Flanker smoke session for adapter shape inspection

Single seed=1001 session to reveal platform data-export schema before
writing read_expfactory_flanker adapter."
```

---

## Task 4: Run remaining 4 Flanker smoke sessions

**Files:**
- Output: `output/<flanker-task-name>/<timestamp>/` × 4 more

- [ ] **Step 1: Run sessions sequentially**

```bash
for seed in 1002 1003 1004 1005; do
  echo "=== Flanker session seed=$seed ==="
  uv run experiment-bot "https://deploy.expfactory.org/preview/3/" \
    --label expfactory_flanker --headless --seed "$seed" \
    >> .reasoner-logs/sp3_flanker_sessions.log 2>&1
  echo "  exit=$?"
done
```

Each session takes ~5–15 minutes; total ~20–60 minutes. The `>>` appends so all four sessions log to one file.

Expected: four `exit=0` lines. If any session fails (`exit != 0`), inspect the log; do NOT retry by tweaking the bot — log the failure mode and continue.

- [ ] **Step 2: Confirm 5 Flanker session directories exist**

```bash
find output -mindepth 2 -maxdepth 2 -type d -newermt "2026-05-08 00:00" \
  -path "*expfactory_flanker*" -o -path "*flanker*" 2>/dev/null | wc -l
```

Expected: `5`. If less, document the missing-session count in the SP3 report later.

- [ ] **Step 3: Sanity-check trial counts across sessions**

```bash
uv run python << 'PY'
import json
from pathlib import Path
flanker_dir = next(d for d in Path('output').iterdir()
                    if 'flanker' in d.name.lower())
print(f'paradigm dir: {flanker_dir}')
for ses in sorted(flanker_dir.iterdir()):
    if not ses.is_dir(): continue
    log = json.load(open(ses / 'bot_log.json')) if (ses / 'bot_log.json').exists() else []
    print(f'  {ses.name}: {len(log)} bot trials')
PY
```

Expected: each session has roughly equal trial counts (within 5–10% of each other). Wide variance suggests intermittent navigation issues.

- [ ] **Step 4: Commit the 4 additional sessions**

```bash
git add output/
git commit -m "chore(sp3): 4 additional Flanker smoke sessions (seeds 1002-1005)

5 sessions total per SP3 spec. Held-out: bot config not iterated
between runs."
```

---

## Task 5: Add `read_expfactory_flanker` platform adapter

**Files:**
- Modify: `src/experiment_bot/validation/platform_adapters.py`
- Modify: `tests/test_platform_adapters.py`

The Flanker adapter parses the platform's data export into the canonical trial-dict shape `{condition, rt, correct, omission}` that `validate_session_set` consumes. Pattern after `read_expfactory_stroop` (it shares the same expfactory hosting and data shape).

- [ ] **Step 1: Confirm the data shape matches Stroop's structure**

Re-run Task 3 Step 3 if needed and confirm the Flanker export uses fields like `trial_type`, `trial_id` (or `exp_stage`), `condition`, `rt`, `correct_trial`. If the field names match Stroop's exactly, the adapter is a near-copy of `read_expfactory_stroop` with a different filter selector.

If the field names differ (e.g., the platform uses `correct` instead of `correct_trial`), adjust the adapter accordingly. Document the assumption in the adapter's docstring.

- [ ] **Step 2: Write the failing test (with a sample fixture)**

Create or extend `tests/test_platform_adapters.py` with a Flanker test. The fixture below assumes the JSON shape used by stroop; adapt the field names if Step 1 revealed differences.

Add this test to `tests/test_platform_adapters.py`:

```python
def test_expfactory_flanker_canonicalizes_test_trials(tmp_path):
    """Flanker adapter filters to test trials and produces the canonical
    {condition, rt, correct, omission} schema the oracle expects."""
    import json
    from experiment_bot.validation.platform_adapters import read_expfactory_flanker
    sample = [
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "congruent", "rt": 480, "correct_trial": 1,
         "response": "f", "correct_response": "f"},
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "incongruent", "rt": 562, "correct_trial": 0,
         "response": "f", "correct_response": "j"},
        {"trial_type": "html-keyboard-response", "trial_id": "fixation",
         "condition": "", "rt": None, "correct_trial": None},  # filtered out
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "incongruent", "rt": None, "correct_trial": 0,
         "response": None, "correct_response": "j"},  # omission
    ]
    ses = tmp_path / "session"
    ses.mkdir()
    (ses / "experiment_data.json").write_text(json.dumps(sample))

    trials = read_expfactory_flanker(ses)

    assert len(trials) == 3
    assert trials[0] == {"condition": "congruent", "rt": 480.0, "correct": True, "omission": False}
    assert trials[1] == {"condition": "incongruent", "rt": 562.0, "correct": False, "omission": False}
    assert trials[2] == {"condition": "incongruent", "rt": None, "correct": False, "omission": True}


def test_flanker_adapter_dispatch_registered(tmp_path):
    """The adapter must be reachable through PLATFORM_ADAPTERS by the
    output-directory label name."""
    from experiment_bot.validation.platform_adapters import (
        PLATFORM_ADAPTERS, read_expfactory_flanker,
    )
    # The label key matches the Reasoner-emitted task.name, lower-cased
    # with spaces->underscores. Inspect the regenerated TaskCard's
    # task.name to confirm exact key.
    assert any(v is read_expfactory_flanker for v in PLATFORM_ADAPTERS.values()), \
        "read_expfactory_flanker not registered in PLATFORM_ADAPTERS"
```

- [ ] **Step 3: Run the failing tests**

```bash
uv run pytest tests/test_platform_adapters.py -v 2>&1 | tail -10
```

Expected: both new tests FAIL with `ImportError: cannot import name 'read_expfactory_flanker'`.

- [ ] **Step 4: Implement the adapter**

Add to `src/experiment_bot/validation/platform_adapters.py` (after `read_expfactory_stroop`):

```python
def read_expfactory_flanker(session_dir: Path) -> list[dict]:
    """`taskcards/expfactory_flanker/`. Filter: trial_id == test_trial.

    Reads either experiment_data.json or experiment_data.csv — see
    `read_expfactory_stop_signal` for the format-agnostic pattern.
    Field schema mirrors expfactory_stroop: trial_id, condition,
    rt, correct_trial.
    """
    rows = _load_experiment_rows(session_dir)
    out: list[dict] = []
    for r in rows:
        if r.get("trial_id") != "test_trial":
            continue
        rt = _safe_float(r.get("rt"))
        if r.get("correct_trial") in (0, 1, "0", "1"):
            correct = r.get("correct_trial") in (1, "1")
        else:
            correct = r.get("response") == r.get("correct_response")
        out.append({
            "condition": r.get("condition") or "",
            "rt": rt,
            "correct": correct,
            "omission": rt is None,
        })
    return out
```

And in the `PLATFORM_ADAPTERS` dispatch dict, add the Flanker entry. The exact key depends on the regenerated TaskCard's `task.name`. To find it:

```bash
uv run python -c "
import json, glob
d = json.load(open(glob.glob('taskcards/expfactory_flanker/*.json')[0]))
print(d['task']['name'])
"
```

Then add the corresponding dispatch entry. For example, if the TaskCard's `task.name` is `attention_network_test_(rdoc)` (a common Flanker variant), use:

```python
PLATFORM_ADAPTERS: dict[str, Callable[[Path], list[dict]]] = {
    "stop_signal_rdoc": read_expfactory_stop_signal,
    "stroop_rdoc": read_expfactory_stroop,
    "stop_signal_kywch_jspsych": read_stopit_stop_signal,
    "stop_signal_task_(stop-it,_jspsych_port)": read_stopit_stop_signal,
    "stroop_online_(cognition.run)": read_cognitionrun_stroop,
    # SP3 held-out: Flanker. The exact key matches the regenerated
    # TaskCard's task.name (output-directory convention).
    "<flanker_task_name_from_taskcard>": read_expfactory_flanker,
}
```

Replace `<flanker_task_name_from_taskcard>` with the actual `task.name` from the regenerated TaskCard.

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
uv run pytest tests/test_platform_adapters.py -v 2>&1 | tail -10
```

Expected: both Flanker tests PASS, plus all existing adapter tests still PASS.

- [ ] **Step 6: Run the full suite to confirm no regression**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: `470 passed, 1 skipped` (468 pre-SP3 + 2 new Flanker tests).

- [ ] **Step 7: Sanity-check the adapter on a real Flanker session**

```bash
uv run python << 'PY'
from experiment_bot.validation.platform_adapters import read_expfactory_flanker
from pathlib import Path
flanker_dir = next(d for d in Path('output').iterdir() if 'flanker' in d.name.lower())
ses = sorted(flanker_dir.iterdir())[0]
trials = read_expfactory_flanker(ses)
print(f'{ses.name}: {len(trials)} test trials')
from collections import Counter
print(f'  condition counts: {dict(Counter(t["condition"] for t in trials))}')
print(f'  with rt: {sum(1 for t in trials if t["rt"] is not None)}')
print(f'  correct: {sum(1 for t in trials if t["correct"])}')
PY
```

Expected: non-zero trial count with both `congruent` and `incongruent` conditions present. If trial count is 0, the `trial_id == "test_trial"` filter is wrong — check the actual platform export schema (Task 3 Step 3) and adjust the filter accordingly. Note that this is a defensive bug fix (allowed) not a paradigm-specific iteration (forbidden).

- [ ] **Step 8: Commit**

```bash
git add src/experiment_bot/validation/platform_adapters.py tests/test_platform_adapters.py
git commit -m "feat(adapter): read_expfactory_flanker for SP3 held-out validation

Mirrors read_expfactory_stroop's filter (trial_id == test_trial) and
correctness derivation. Format-agnostic via _load_experiment_rows.
Added to PLATFORM_ADAPTERS dispatch under the regenerated Flanker
TaskCard's task.name."
```

---

## Task 6: Validate Flanker sessions

**Files:**
- Output: `validation/sp3_heldout/<flanker_label>_<timestamp>.json`

- [ ] **Step 1: Identify the Flanker output-directory label**

```bash
FLANKER_LABEL=$(ls output | grep -i flanker | head -1)
echo "FLANKER_LABEL=$FLANKER_LABEL"
```

Use this exact string for the `--label` argument below.

- [ ] **Step 2: Run validation**

```bash
uv run experiment-bot-validate \
  --paradigm-class conflict \
  --label "$FLANKER_LABEL" \
  --output-dir output \
  --reports-dir validation/sp3_heldout \
  -v 2>&1 | tail -20
```

Expected: validator runs without crashing, produces `validation/sp3_heldout/<FLANKER_LABEL>_<timestamp>.json`, prints overall pass/fail and per-pillar status.

- [ ] **Step 3: Inspect the report**

```bash
uv run python << 'PY'
import json, glob
f = sorted(glob.glob('validation/sp3_heldout/*flanker*.json'))[-1]
d = json.load(open(f))
print(f'overall_pass: {d["overall_pass"]}')
for pillar, info in d['pillar_results'].items():
    marker = '✅' if info['pass'] else '❌'
    print(f'  {marker} {pillar}')
    for m, mr in info['metrics'].items():
        ps = '✓' if mr['pass'] is True else ('✗' if mr['pass'] is False else '·')
        bv = mr['bot_value']
        bv_s = f'{bv:.2f}' if isinstance(bv, (int, float)) else str(bv)
        print(f'    {ps} {m}: {bv_s} vs {mr["published_range"]}')
PY
```

This printout becomes part of the SP3 report (Task 13).

- [ ] **Step 4: Commit the validation report**

```bash
git add validation/sp3_heldout/
git commit -m "chore(sp3): Flanker validation report (held-out, conflict class)

5-session run validated against norms/conflict.json. Numbers reported
descriptively per SP3 spec; out-of-range metrics are findings, not
failures."
```

---

## Task 7: Regenerate n-back TaskCard

**Files:**
- Output: `taskcards/expfactory_n_back/<hash>.json`
- Output: `taskcards/expfactory_n_back/pilot.md`
- Working: `.reasoner-logs/sp3_nback_regen.log`

Mirrors Task 2 for n-back. The previous n-back held-out test (2026-05-06) surfaced framework gaps; the audit refactors that followed addressed them. Re-running n-back now closes that loop.

- [ ] **Step 1: Confirm no existing n-back TaskCard**

```bash
ls taskcards/expfactory_n_back/ 2>&1 || echo "(no taskcards yet)"
```

Expected: directory absent or empty. (The 0290bf4c.json TaskCard from the earlier test was deleted in commit `e3a33bc`.)

- [ ] **Step 2: Run the Reasoner**

```bash
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/5/" \
  --label expfactory_n_back --pilot-max-retries 3 -v \
  > .reasoner-logs/sp3_nback_regen.log 2>&1
echo "exit=$?"
```

Same constraints as Task 2 Step 3 — no overrides, ~5–25 min.

- [ ] **Step 3: If the Reasoner failed — STOP and document**

Same procedure as Task 2 Step 4. Inspect:

```bash
grep -E "Stage [0-9]+ attempt|Stage2SchemaError|JSONDecodeError|PilotValidationError|Traceback" \
  .reasoner-logs/sp3_nback_regen.log | tail -20
```

Document the failure mode in `docs/sp3-heldout-results.md` (Task 13). If Flanker (Task 2) also failed, SP3 still produces a deliverable (a report of two framework failures); proceed to Task 13.

- [ ] **Step 4: Sanity-check the produced TaskCard**

```bash
uv run python -c "
import json, glob
f = glob.glob('taskcards/expfactory_n_back/*.json')[0]
d = json.load(open(f))
print(f'file: {f}')
print(f'  task.name: {d[\"task\"].get(\"name\")}')
print(f'  paradigm_classes: {d[\"task\"].get(\"paradigm_classes\")}')
print(f'  response_distributions: {list(d.get(\"response_distributions\", {}).keys())}')
print(f'  navigation phases: {len(d.get(\"navigation\", {}).get(\"phases\", []))}')
"
```

Expected: paradigm_classes include `working_memory` (or similar literature-conventional class name). `navigation.phases` non-empty (the previous test failed because of empty navigation; if non-empty here, audit refactor delivered).

- [ ] **Step 5: Commit**

```bash
git add taskcards/expfactory_n_back/
git commit -m "chore(sp3): held-out n-back TaskCard from Reasoner pipeline

Regenerated under sp2-complete framework. Re-test of held-out
working_memory paradigm (previous run 2026-05-06 surfaced gaps later
addressed in audit refactors)."
```

---

## Task 8: Inspect one n-back session's data shape

**Files:**
- Output: `output/<nback-task-name>/<timestamp>/`

Mirrors Task 3 for n-back.

- [ ] **Step 1: Run a single n-back smoke session**

```bash
uv run experiment-bot "https://deploy.expfactory.org/preview/5/" \
  --label expfactory_n_back --headless --seed 2001 \
  > .reasoner-logs/sp3_nback_session1.log 2>&1
echo "exit=$?"
```

Expected: `exit=0` and a new directory under `output/<nback-task-name>/<timestamp>/`.

- [ ] **Step 2: Identify the n-back output directory**

```bash
NBACK_OUT=$(find output -mindepth 2 -maxdepth 2 -type d -newermt "2026-05-08 00:00" \
  | grep -iE "(n.?back|nback)" | head -1)
echo "n-back output: $NBACK_OUT"
ls "$NBACK_OUT"
```

- [ ] **Step 3: Inspect the data export schema**

```bash
uv run python << 'PY'
import json, csv
from pathlib import Path
nback_dir = next(d for d in Path('output').iterdir()
                  if any(t in d.name.lower() for t in ('n-back', 'n_back', 'nback')))
ses = sorted(p for p in nback_dir.iterdir() if p.is_dir())[-1]
print(f'session: {ses}')
for ext in ('json', 'csv'):
    f = ses / f'experiment_data.{ext}'
    if f.exists():
        print(f'  format: {ext}')
        if ext == 'json':
            data = json.load(open(f))
            print(f'  rows: {len(data) if isinstance(data, list) else "(not a list)"}')
            if isinstance(data, list) and data:
                print(f'  first-row keys: {sorted(data[0].keys())}')
                # n-back uses different field conventions than stop-signal/stroop
                print(f'  trial_type values: {set(r.get("trial_type") for r in data[:50])}')
        else:
            rows = list(csv.DictReader(open(f)))
            print(f'  rows: {len(rows)}')
            if rows:
                print(f'  first-row keys: {sorted(rows[0].keys())}')
        break
PY
```

n-back's typical fields differ from stroop/stop-signal — expect to see `n_back_condition` (1-back vs 2-back), `target` (yes/no match), `correct` instead of `correct_trial`. The adapter (Task 11) will need to handle these.

- [ ] **Step 4: Commit the first n-back session**

```bash
git add output/
git commit -m "chore(sp3): first n-back smoke session for adapter shape inspection"
```

---

## Task 9: Run remaining 4 n-back smoke sessions

**Files:**
- Output: 4 more n-back session directories

Mirrors Task 4 for n-back.

- [ ] **Step 1: Run sessions sequentially**

```bash
for seed in 2002 2003 2004 2005; do
  echo "=== n-back session seed=$seed ==="
  uv run experiment-bot "https://deploy.expfactory.org/preview/5/" \
    --label expfactory_n_back --headless --seed "$seed" \
    >> .reasoner-logs/sp3_nback_sessions.log 2>&1
  echo "  exit=$?"
done
```

- [ ] **Step 2: Confirm 5 n-back session directories**

```bash
NBACK_DIR=$(find output -mindepth 1 -maxdepth 1 -type d \
  | grep -iE "(n.?back|nback)" | head -1)
ls "$NBACK_DIR" | wc -l
```

Expected: `5`.

- [ ] **Step 3: Sanity-check trial counts**

```bash
uv run python << 'PY'
import json
from pathlib import Path
nback_dir = next(d for d in Path('output').iterdir()
                  if any(t in d.name.lower() for t in ('n-back', 'n_back', 'nback')))
print(f'paradigm dir: {nback_dir}')
for ses in sorted(nback_dir.iterdir()):
    if not ses.is_dir(): continue
    log_file = ses / 'bot_log.json'
    log = json.load(open(log_file)) if log_file.exists() else []
    print(f'  {ses.name}: {len(log)} bot trials')
PY
```

- [ ] **Step 4: Commit**

```bash
git add output/
git commit -m "chore(sp3): 4 additional n-back smoke sessions (seeds 2002-2005)"
```

---

## Task 10: Add `read_expfactory_n_back` platform adapter

**Files:**
- Modify: `src/experiment_bot/validation/platform_adapters.py`
- Modify: `tests/test_platform_adapters.py`

n-back's data export likely uses different field names than the existing adapters. Build the adapter with a fixture matching the actual schema observed in Task 8.

- [ ] **Step 1: Determine n-back's actual field names**

From Task 8 Step 3 output, note:
- The format (CSV or JSON).
- The field that holds the condition label (likely `n_back_condition` or `condition` valued like `"target"`/`"non_target"` or `"1back"`/`"2back"`).
- The field that flags correctness (likely `correct` rather than `correct_trial`).
- The trial-phase filter (likely `trial_type` and/or `exp_stage`).

If these match an existing adapter exactly, reuse it (extend the dispatch only). Otherwise, write a new adapter.

- [ ] **Step 2: Write the failing test**

Add this test to `tests/test_platform_adapters.py`. The fixture below uses representative n-back fields; **adjust field names to match what Task 8 Step 3 actually printed.**

```python
def test_expfactory_n_back_canonicalizes_test_trials(tmp_path):
    """n-back adapter filters to test trials and canonicalizes the
    {condition, rt, correct, omission} schema."""
    import json
    from experiment_bot.validation.platform_adapters import read_expfactory_n_back
    sample = [
        {"trial_type": "html-keyboard-response", "exp_stage": "test",
         "condition": "target", "rt": 540, "correct": True},
        {"trial_type": "html-keyboard-response", "exp_stage": "test",
         "condition": "non_target", "rt": 620, "correct": False},
        {"trial_type": "html-keyboard-response", "exp_stage": "practice",  # filtered
         "condition": "target", "rt": 510, "correct": True},
        {"trial_type": "html-keyboard-response", "exp_stage": "test",
         "condition": "non_target", "rt": None, "correct": False},  # omission
    ]
    ses = tmp_path / "session"
    ses.mkdir()
    (ses / "experiment_data.json").write_text(json.dumps(sample))

    trials = read_expfactory_n_back(ses)

    assert len(trials) == 3
    assert trials[0] == {"condition": "target", "rt": 540.0, "correct": True, "omission": False}
    assert trials[1] == {"condition": "non_target", "rt": 620.0, "correct": False, "omission": False}
    assert trials[2] == {"condition": "non_target", "rt": None, "correct": False, "omission": True}


def test_n_back_adapter_dispatch_registered():
    """The n-back adapter must be reachable through PLATFORM_ADAPTERS."""
    from experiment_bot.validation.platform_adapters import (
        PLATFORM_ADAPTERS, read_expfactory_n_back,
    )
    assert any(v is read_expfactory_n_back for v in PLATFORM_ADAPTERS.values()), \
        "read_expfactory_n_back not registered"
```

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest tests/test_platform_adapters.py -v 2>&1 | tail
```

Expected: 2 new tests FAIL with `ImportError`.

- [ ] **Step 4: Implement the adapter**

Add to `src/experiment_bot/validation/platform_adapters.py` (after `read_expfactory_flanker`):

```python
def read_expfactory_n_back(session_dir: Path) -> list[dict]:
    """`taskcards/expfactory_n_back/`. Filter: exp_stage == test.

    n-back's correctness flag is `correct` (boolean) rather than the
    `correct_trial` (0/1) used by stroop/stop-signal. Condition values
    are paradigm-specific (e.g., 'target' vs 'non_target', or '1back'
    vs '2back') — passed through verbatim so the validator's
    contrast-labels machinery can match TaskCard-emitted labels.
    """
    rows = _load_experiment_rows(session_dir)
    out: list[dict] = []
    for r in rows:
        if r.get("exp_stage") != "test":
            continue
        rt = _safe_float(r.get("rt"))
        # Handle both bool and "true"/"false"/"1"/"0" string conventions
        correct_raw = r.get("correct")
        if isinstance(correct_raw, bool):
            correct = correct_raw
        elif isinstance(correct_raw, str):
            correct = correct_raw.lower() in ("true", "1")
        elif isinstance(correct_raw, (int, float)):
            correct = bool(correct_raw)
        else:
            correct = False
        out.append({
            "condition": r.get("condition") or "",
            "rt": rt,
            "correct": correct,
            "omission": rt is None,
        })
    return out
```

Update `PLATFORM_ADAPTERS`:

```python
PLATFORM_ADAPTERS: dict[str, Callable[[Path], list[dict]]] = {
    "stop_signal_rdoc": read_expfactory_stop_signal,
    "stroop_rdoc": read_expfactory_stroop,
    "stop_signal_kywch_jspsych": read_stopit_stop_signal,
    "stop_signal_task_(stop-it,_jspsych_port)": read_stopit_stop_signal,
    "stroop_online_(cognition.run)": read_cognitionrun_stroop,
    "<flanker_task_name>": read_expfactory_flanker,
    # SP3 held-out: n-back. Key matches the regenerated TaskCard's task.name.
    "<n_back_task_name>": read_expfactory_n_back,
}
```

Replace `<n_back_task_name>` with the actual `task.name` from the n-back TaskCard. To find it:

```bash
uv run python -c "
import json, glob
d = json.load(open(glob.glob('taskcards/expfactory_n_back/*.json')[0]))
print(d['task']['name'])
"
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/test_platform_adapters.py -v 2>&1 | tail -10
```

Expected: 4 adapter tests pass (2 Flanker + 2 n-back), no regressions.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: `472 passed, 1 skipped`.

- [ ] **Step 7: Sanity-check on real n-back session data**

```bash
uv run python << 'PY'
from experiment_bot.validation.platform_adapters import read_expfactory_n_back
from pathlib import Path
nback_dir = next(d for d in Path('output').iterdir()
                  if any(t in d.name.lower() for t in ('n-back', 'n_back', 'nback')))
ses = sorted(nback_dir.iterdir())[0]
trials = read_expfactory_n_back(ses)
print(f'{ses.name}: {len(trials)} test trials')
from collections import Counter
print(f'  conditions: {dict(Counter(t["condition"] for t in trials))}')
print(f'  with rt: {sum(1 for t in trials if t["rt"] is not None)}')
print(f'  correct: {sum(1 for t in trials if t["correct"])}')
PY
```

Expected: non-zero trial count. If 0, the filter or field names diverge from the fixture; adjust accordingly (defensive bug fix, not paradigm-specific iteration).

- [ ] **Step 8: Commit**

```bash
git add src/experiment_bot/validation/platform_adapters.py tests/test_platform_adapters.py
git commit -m "feat(adapter): read_expfactory_n_back for SP3 held-out validation

Filters by exp_stage == test. Handles n-back's bool 'correct' flag
(vs the 0/1 'correct_trial' used by stroop/stop-signal). Condition
labels passed through verbatim for label-flexibility per SP2's
generic-mechanism contract."
```

---

## Task 11: Validate n-back sessions

**Files:**
- Output: `validation/sp3_heldout/<n_back_label>_<timestamp>.json`

Mirrors Task 6 for n-back.

- [ ] **Step 1: Identify the n-back output-directory label**

```bash
NBACK_LABEL=$(ls output | grep -iE "(n.?back|nback)" | head -1)
echo "NBACK_LABEL=$NBACK_LABEL"
```

- [ ] **Step 2: Run validation**

```bash
uv run experiment-bot-validate \
  --paradigm-class working_memory \
  --label "$NBACK_LABEL" \
  --output-dir output \
  --reports-dir validation/sp3_heldout \
  -v 2>&1 | tail -20
```

If the n-back TaskCard's `paradigm_classes` doesn't include `working_memory` exactly, use whatever the LLM emitted (e.g., the previous test produced `working_memory` directly). Check via:

```bash
uv run python -c "
import json, glob
d = json.load(open(glob.glob('taskcards/expfactory_n_back/*.json')[0]))
print(d['task']['paradigm_classes'])
"
```

If a different class name (e.g., `working_memory_load`) was emitted, the corresponding norms file may not exist. Note this in the SP3 report — it's a finding about the open paradigm-class taxonomy, not a bug to fix.

- [ ] **Step 3: Inspect the report**

```bash
uv run python << 'PY'
import json, glob
files = sorted(glob.glob('validation/sp3_heldout/*back*.json'))
if not files:
    files = sorted(glob.glob('validation/sp3_heldout/*nback*.json'))
f = files[-1] if files else None
if not f:
    print("no n-back report found")
else:
    d = json.load(open(f))
    print(f'overall_pass: {d["overall_pass"]}')
    for pillar, info in d['pillar_results'].items():
        marker = '✅' if info['pass'] else '❌'
        print(f'  {marker} {pillar}')
        for m, mr in info['metrics'].items():
            ps = '✓' if mr['pass'] is True else ('✗' if mr['pass'] is False else '·')
            bv = mr['bot_value']
            bv_s = f'{bv:.2f}' if isinstance(bv, (int, float)) else str(bv)
            print(f'    {ps} {m}: {bv_s} vs {mr["published_range"]}')
PY
```

- [ ] **Step 4: Commit**

```bash
git add validation/sp3_heldout/
git commit -m "chore(sp3): n-back validation report (held-out, working_memory class)"
```

---

## Task 12: Compute platform-side accuracy summary

**Files:**
- Working: stdout

Useful headline number for the report. Mirrors the post-fix verification we did in SP2.5.

- [ ] **Step 1: Compute accuracy across both held-out paradigms**

```bash
uv run python << 'PY'
"""Platform-side accuracy summary for the SP3 report."""
from experiment_bot.validation.platform_adapters import PLATFORM_ADAPTERS
from pathlib import Path

print('=== SP3 held-out: platform-side accuracy ===')
for label_prefix in ('flanker', 'n-back', 'n_back', 'nback'):
    candidate_dirs = [d for d in Path('output').iterdir()
                       if label_prefix in d.name.lower() and d.is_dir()]
    for d in candidate_dirs:
        # Find a registered adapter
        for key, fn in PLATFORM_ADAPTERS.items():
            if key.lower() == d.name.lower():
                print(f'\n[{d.name}] adapter: {fn.__name__}')
                for ses in sorted(d.iterdir()):
                    if not ses.is_dir(): continue
                    trials = fn(ses)
                    if not trials: continue
                    n = len(trials)
                    correct = sum(1 for t in trials if t.get('correct'))
                    print(f'  {ses.name}: {correct}/{n} = {correct/n:.1%}')
                break
        else:
            print(f'[{d.name}] no adapter registered')
PY
```

This output goes into the SP3 report (Task 13).

- [ ] **Step 2: No commit yet** — the data is consumed by Task 13's report.

---

## Task 13: Write the SP3 results report

**Files:**
- Create: `docs/sp3-heldout-results.md`

Combined report covering both paradigms. Follows the format of `docs/heldout-nback-test.md` but covers two paradigms side-by-side, with comparison to smoke v3 dev paradigms.

- [ ] **Step 1: Gather all the data sources**

The report draws from:
- The two TaskCards (`taskcards/expfactory_flanker/`, `taskcards/expfactory_n_back/`).
- The 10 session directories under `output/<task-name>/<timestamp>/`.
- The two validation reports under `validation/sp3_heldout/`.
- Adapter source from this branch (`src/experiment_bot/validation/platform_adapters.py`).
- Smoke v3 dev-paradigm validation under `validation/smoke_2x4_v2/` (committed) — used as a reference comparison column.

Collect headline numbers using:

```bash
uv run python << 'PY'
import json, glob
print('=== HEADLINE NUMBERS FOR SP3 REPORT ===\n')
for label_pat, cls in [('flanker', 'conflict'), ('n_back', 'working_memory'), ('nback', 'working_memory')]:
    rs = sorted(glob.glob(f'validation/sp3_heldout/*{label_pat}*.json'))
    if not rs: continue
    d = json.load(open(rs[-1]))
    print(f'[{label_pat} | {cls}]')
    print(f'  overall_pass: {d["overall_pass"]}')
    for pillar, info in d['pillar_results'].items():
        for m, mr in info['metrics'].items():
            bv = mr['bot_value']
            bv_s = f'{bv:.2f}' if isinstance(bv, (int, float)) else str(bv)
            print(f'  {pillar}.{m}: {bv_s} vs {mr["published_range"]}')
    print()
PY
```

- [ ] **Step 2: Write the report**

Create `docs/sp3-heldout-results.md` with this structure:

```markdown
# SP3 — Held-out generalization test results (Flanker + n-back)

**Date:** 2026-05-08
**Spec:** `docs/superpowers/specs/2026-05-08-sp3-flanker-nback-heldout-design.md`
**Branch:** `sp3/heldout-validation`
**Tag (after this report):** `sp3-complete`

## Goal

Empirical evidence that the experiment-bot framework generalizes to
two paradigms whose iteration loop never touched: Flanker (conflict
class, within-class held-out) and n-back (working_memory class,
cross-class held-out).

## Procedure

Per the SP3 spec, both paradigms ran:

1. Reasoner pipeline regeneration with no prompt overrides.
2. Five sequential headless smoke sessions.
3. Validation against the corresponding `norms/<class>.json`.

Allowed code changes during SP3 were limited to platform adapters
(`read_expfactory_flanker`, `read_expfactory_n_back`) and defensive
validator fixes. No prompt edits, no TaskCard tuning.

## Results

### Operational pass

| Paradigm | TaskCard produced? | 5 sessions completed? | Validator ran without crash? | Operational pass |
|---|---|---|---|---|
| Flanker | <yes/no> | <5/5> | <yes/no> | <✓/✗> |
| n-back | <yes/no> | <5/5> | <yes/no> | <✓/✗> |

### Behavioral metrics (Flanker, conflict class)

| Metric | Bot (5-session aggregate) | norms/conflict.json range | In range? |
|---|---|---|---|
| rt_distribution.mu | <value> ms | [400, 550] | <✓/✗> |
| rt_distribution.sigma | <value> ms | [25, 60] | <✓/✗> |
| rt_distribution.tau | <value> ms | [70, 160] | <✓/✗> |
| post_error_slowing | <value> ms | [10, 50] | <✓/✗> |
| cse_magnitude | <value> ms | [-45, -10] | <✓/✗> |

### Behavioral metrics (n-back, working_memory class)

| Metric | Bot (5-session aggregate) | norms/working_memory.json range | In range? |
|---|---|---|---|
| rt_distribution.mu | <value> ms | <range or null> | <✓/✗> |
| post_error_slowing | <value> ms | [10, 50] | <✓/✗> |
| lag1_autocorr | <value> | <range or null> | <·> |

(Working-memory norms file is sparse for non-rt-distribution metrics
per SP2.5 trim — additional metrics would need re-extraction with the
n-back paradigm's signature measures, which is SP4 territory.)

### Platform-side accuracy

| Paradigm | Configured | Observed (5-session avg) |
|---|---|---|
| Flanker | <0.95 from TaskCard> | <observed> |
| n-back | <from TaskCard> | <observed> |

### Comparison vs smoke v3 dev paradigms

| Paradigm | go-trial accuracy (target ~95%) | Notes |
|---|---|---|
| expfactory_stop_signal (dev) | 94.2%, 96.7% | smoke v3 |
| expfactory_stroop (dev) | 95.0%, 95.8% | smoke v3 |
| stopit_stop_signal (dev) | 95.3%, 93.8% | smoke v3 |
| **Flanker (held-out)** | <observed> | this run |
| **n-back (held-out)** | <observed> | this run |

## Interpretation

Per the SP3 spec interpretation table:

- **Both paradigms operationally pass:** framework generalizes within
  and across paradigm classes.
- **Either paradigm fails operationally:** specific overfitting found;
  failures named below; fixes ride a future SP4 sub-project.

[Fill in: which combination occurred and what it means.]

## Framework gaps surfaced (SP4 backlog)

[Fill in any gaps observed during SP3, with the implicated framework
component and the failure signature. Each entry mirrors the format of
`docs/sp2-validation-followups.md` items.]

If no gaps surfaced, write: "No new framework gaps observed; both
held-out paradigms pass operationally with behavioral metrics in
expected ranges."

## Artifacts

- TaskCards: `taskcards/expfactory_flanker/<hash>.json`,
  `taskcards/expfactory_n_back/<hash>.json`.
- 10 session directories under `output/`.
- Validation reports: `validation/sp3_heldout/`.
- Adapter code: `src/experiment_bot/validation/platform_adapters.py`
  (`read_expfactory_flanker`, `read_expfactory_n_back`).
- Adapter tests: `tests/test_platform_adapters.py`.

## Status

SP3 deliverable complete. Tag `sp3-complete` applied to this commit.
The next sub-project (SP4) would address the framework gaps surfaced
above, if any.
```

Replace `<...>` placeholders with the actual numbers from the data sources in Step 1.

- [ ] **Step 3: Sanity-check the report has no remaining placeholders**

```bash
grep -nE "<value>|<yes/no>|<5/5>|<observed>|<range|<·>" docs/sp3-heldout-results.md
```

Expected: no output (all placeholders filled). If any remain, fix them. The `[Fill in: ...]` marked sections need to be replaced with actual prose specific to the run.

- [ ] **Step 4: Commit the report**

```bash
git add docs/sp3-heldout-results.md
git commit -m "docs(sp3): held-out generalization test results

Combined report for Flanker (within conflict class) and n-back (across
to working_memory). Per the SP3 spec, this is the deliverable; any
framework gaps logged here are SP4 backlog."
```

---

## Task 14: Tag and push

**Files:**
- Tag: `sp3-complete`

- [ ] **Step 1: Verify clean state**

```bash
git status
uv run pytest 2>&1 | tail -3
```

Expected: clean working tree, all tests passing (472 if both adapters added; 470 if only Flanker; 468 if both regen runs failed and no adapters were added).

- [ ] **Step 2: Tag the SP3-complete milestone**

```bash
git tag -a sp3-complete -m "$(cat <<'EOF'
SP3 (held-out generalization test) — milestone tag

Two held-out paradigms tested under the post-audit framework:
- Flanker (conflict class, within-class held-out)
- n-back (working_memory class, cross-class held-out)

5 sessions per paradigm, no prompt edits, no TaskCard tuning. Mechanical
platform adapters added for Flanker and n-back (validation infrastructure,
not behavioral fidelity).

Results: see docs/sp3-heldout-results.md. Framework gaps (if any) logged
for SP4 backlog.
EOF
)"
```

- [ ] **Step 3: Push branch + tag**

```bash
git push -u origin sp3/heldout-validation
git push origin sp3-complete
```

Expected: branch and tag both pushed without errors.

- [ ] **Step 4: Update CLAUDE.md sub-project history**

```bash
uv run python << 'PY'
from pathlib import Path
content = Path('CLAUDE.md').read_text()
old = """- **SP3** (planned): Additional held-out paradigms (Flanker,
  Sternberg, etc.) to strengthen generalization claim. Not started."""
new = """- **SP3**: Held-out generalization test (Flanker + n-back). Mechanical
  platform adapters added; no prompt edits or TaskCard tuning. Results
  in `docs/sp3-heldout-results.md`. ✓ Complete."""
if old in content:
    Path('CLAUDE.md').write_text(content.replace(old, new))
    print('updated SP3 entry in CLAUDE.md')
else:
    print('SP3 entry not found verbatim — manual edit needed')
PY
```

- [ ] **Step 5: Commit and push CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): mark SP3 complete with results doc reference"
git push
```

---

## Self-review checklist (run before claiming the plan complete)

The plan should map to every spec section. Cross-reference:

- **Spec § Goal:** Tasks 2, 7 (regen) + Tasks 4, 9 (5 sessions each) + Task 13 (report) cover the deliverable.
- **Spec § Definition of held-out:** Tasks 2, 7 explicitly forbid retries with prompt overrides. Task 13's report names framework gaps without fixing them.
- **Spec § Success criteria:** Task 13's report has explicit operational-pass and behavioral-pass tables.
- **Spec § Interpretation table:** Task 13's "Interpretation" section requires picking the relevant row.
- **Spec § Sample size:** Tasks 4 and 9 each run 4 additional sessions (Tasks 3, 8 ran the first one); 5 total per paradigm.
- **Spec § Allowed code changes:** Tasks 5, 10 add adapters and unit tests. No other code modification tasks.
- **Spec § Procedure:** Tasks 2, 3-4, 5, 6 mirror the procedure for Flanker; Tasks 7, 8-9, 10, 11 for n-back.
- **Spec § Deliverables:** All listed artifacts produced by the tasks.
- **Spec § Out of scope:** No tasks for analysis scripts, Eisenberg-Flanker reference data, or larger-N replication.

---

## Notes for the implementing engineer

- The held-out policy is binding. If a TaskCard regen fails, do NOT retry with `--pilot-headed`, longer timeout, or other tuning flags. Document the failure and continue (the n-back side is independent of Flanker, and vice versa).
- Adapters are mechanical bookkeeping: the validator dispatches on output-directory name. Exact dispatch keys depend on the regenerated TaskCard's `task.name`. Find them via the snippets in Tasks 5 and 10.
- The SP3 report is the deliverable. Even if both paradigms fail operationally, write a report explaining the failures — that report is itself useful evidence about generalizability.
