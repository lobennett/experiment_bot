# SP12: Codebase simplification + antagonistic audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce experiment_bot to what is absolutely necessary for current production runs, with minimal runtime visibility additions, so a new reader can walk the pipeline end-to-end quickly. Validated post-cleanup by 5 sessions × 4 SP11 paradigms vs the current Phase 7 N=5 baseline.

**Architecture:** Top-down walk from CLI entry (`experiment-bot <url> --label X`). Each module gets a small audit pass: read it, list candidates with rationale, checkpoint to user, delete approved items as small commits, run tests, append findings + a pipeline-flow.md section. Reasoner is touched last because it's offline (doesn't run during sessions). Phase 2 adds narrated stdout + run_trace.json. Phase 3 re-measures the 4 SP11 paradigms.

**Tech Stack:** Python 3.12, uv, Playwright, anthropic SDK, pytest. Worktree: `/Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp11/`.

**Spec:** `docs/superpowers/specs/2026-05-21-sp12-codebase-simplification-design.md`.

---

## File structure (post-SP12 target)

Surviving structure under `src/experiment_bot/` is the same shape as today; only internals shrink. New files appear only in Phase 2:

| File | Purpose |
|---|---|
| `docs/pipeline-flow.md` (new) | One-page walkthrough of `experiment-bot <url>` → `bot_log.json` lifecycle with code refs. Filled in section-by-section during Phase 1 walks. |
| `docs/sp12-hardcoded-findings.md` (new) | Inline-during-walk log of paradigm-specific knowledge, magic numbers, fragile assumptions discovered while reading. |
| `docs/sp12-deliverable.md` (new, end of phase 4) | Summary of removals, before/after LOC, pointer to re-measurement report, pointer to findings doc. |
| `docs/sp11-complete.md` (new, replaces 11 sp11-phase*.md) | Consolidated SP11 history. |
| `src/experiment_bot/output/writer.py` (modified) | Adds `run_trace.json` writer alongside existing `bot_log.json`. |
| Per-module sources under `src/experiment_bot/` | Walked, pruned, possibly renamed (e.g., `scripts/phase7_analysis.py` → `scripts/analyze_sessions.py`). |

---

## Walk protocol (used by every module-walk task in Phase 1)

This is the standard protocol every walk task follows. Apply per-module, then proceed.

1. Run `wc -l <module>` and `grep -rn '<module-public-symbol>' src/ tests/ scripts/` to size the work and identify call sites.
2. Read the module top-to-bottom; produce a 3–5 bullet "what this does" summary.
3. List candidate removals with rationale (one-liner per candidate). Categories: dead code, unused CLI args, circuitous branching, over-abstracted helpers (single call site), hardcoded paradigm knowledge → flag for `sp12-hardcoded-findings.md`.
4. Post the candidate list as a checkpoint message to the user (transient — no commit). Wait for veto.
5. For each surviving candidate, delete with one small commit using this message template: `refactor(sp12): remove <thing> from <module> — <one-line rationale>`. Run `uv run pytest` after the last deletion in the module (more often if preferred).
6. Append paradigm-specific findings (if any) to `docs/sp12-hardcoded-findings.md` as a section under the module's name with line refs.
7. Append a section to `docs/pipeline-flow.md` for this module: 2–4 sentences on its role + 1–2 sentence pointer to key entry function with line ref.
8. Commit the docs additions: `docs(sp12): pipeline-flow + findings for <module>`.

---

## Phase 1 — Walk-and-prune

### Task 1: Scripts cleanup — one-shot SP-era helpers

**Files:**
- Delete: `scripts/phase7_sweep.py`
- Delete: `scripts/phase7_aggregate.py`
- Delete: `scripts/phase7_baseline_snapshots.py`
- Delete: `scripts/check_parameter_drift.py`
- Delete: `scripts/probe_cognitionrun_export.py`
- Delete: `scripts/probe_stopit_jspsych6.py`
- Delete: `scripts/keypress_audit.py`
- Delete: `scripts/batch_run.sh`
- Delete: `scripts/test_run.sh`
- Delete: `scripts/__deprecated__/` (whole subtree)
- Delete: `scripts/figure1_bot_vs_human.png`, `scripts/figure2_sequential_effects.png`
- Delete: `tests/test_phase7_sweep_and_aggregate.py`
- Delete: `tests/test_parameter_drift_script.py`
- Rename: `scripts/phase7_analysis.py` → `scripts/analyze_sessions.py`
- Modify: `scripts/analyze_sessions.py` — drop phase7-specific framing in argparse help text + module docstring; remove `--sweep-roots` defaulting to phase7-specific paths in favor of a generic `--root` flag

- [ ] **Step 1: Confirm nothing imports the scripts being deleted**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp11
grep -rn 'phase7_sweep\|phase7_aggregate\|phase7_baseline_snapshots\|check_parameter_drift\|probe_cognitionrun_export\|probe_stopit_jspsych6\|keypress_audit\|batch_run\|test_run' src/ tests/ scripts/ docs/ 2>&1 | grep -v 'docs/sp11-phase' | grep -v 'docs/superpowers'
```

Expected: only matches in `scripts/` itself + the phase7 deliverable docs (which are themselves slated for consolidation in Task 2). No matches in `src/` or other live code.

- [ ] **Step 2: Delete the scripts and their tests**

```bash
git rm scripts/phase7_sweep.py scripts/phase7_aggregate.py scripts/phase7_baseline_snapshots.py \
       scripts/check_parameter_drift.py scripts/probe_cognitionrun_export.py \
       scripts/probe_stopit_jspsych6.py scripts/keypress_audit.py \
       scripts/batch_run.sh scripts/test_run.sh \
       scripts/figure1_bot_vs_human.png scripts/figure2_sequential_effects.png \
       tests/test_phase7_sweep_and_aggregate.py tests/test_parameter_drift_script.py
git rm -r scripts/__deprecated__/
```

- [ ] **Step 3: Run pytest to confirm nothing broke**

```bash
uv run pytest --ignore=tests/test_phase4b_paradigm_smokes.py -q
```

Expected: tests pass with the count dropping by however many were in the two test files just removed.

- [ ] **Step 4: Rename `phase7_analysis.py` → `analyze_sessions.py` and update its docstring + argparse**

```bash
git mv scripts/phase7_analysis.py scripts/analyze_sessions.py
```

In the renamed file, replace the module docstring + the `--sweep-roots` argument as follows.

Module docstring (replace existing top docstring with this):

```python
"""Per-paradigm session-data analysis vs TaskCard targets + human norms.

For each paradigm, computes empirical performance + temporal metrics
from N session data files and compares them against:
  (a) the TaskCard's targeted parameters (mu/sigma/tau,
      performance.accuracy, temporal_effects magnitudes)
  (b) published human norms (norms/<paradigm_class>.json ranges)

Outputs a Markdown decision report and a JSON dump for downstream use.
"""
```

`--sweep-roots` argument (replace the existing argparse entry):

```python
    p.add_argument("--root", action="append", dest="sweep_roots",
                   type=Path, required=True,
                   help="Session-data root directory containing "
                        "<paradigm>/<task_name>/<timestamp>/ subdirs. "
                        "May be repeated to union across roots.")
```

- [ ] **Step 5: Update help refs in the renamed script's main()**

In `scripts/analyze_sessions.py`, in `main()`, the `args.sweep_roots` field name stays the same (still `sweep_roots`), so no further changes needed there. Test the rename by running:

```bash
uv run python scripts/analyze_sessions.py --help
```

Expected: shows `--root` (not `--sweep-roots`), and the docstring at top is the new generic one. Exits 0.

- [ ] **Step 6: Add the module-walk findings to `docs/pipeline-flow.md`**

Create the file with this content:

```markdown
# experiment_bot pipeline flow

Quick reference for what happens between `experiment-bot <url> --label X`
and the final `bot_log.json` write. Sections are added as SP12 walks
each module.

## Surviving scripts

| Script | Purpose |
|---|---|
| `scripts/launch.sh` | Production launcher; wraps `experiment-bot` with the standard env. |
| `scripts/audit_alignment.py` | Per-session bot-vs-platform pairing audit. Paradigm-aware via `--label`. |
| `scripts/analyze_sessions.py` | Per-paradigm aggregate analysis vs TaskCard + human norms. |

## Pipeline phases (filled in below as SP12 walks each module)

```

- [ ] **Step 7: Add the SP12 hardcoded-findings doc with its header**

Create `docs/sp12-hardcoded-findings.md`:

```markdown
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

```

- [ ] **Step 8: Commit deletions + rename + docs in one logical block**

```bash
git add -A
git commit -m "refactor(sp12): delete one-shot SP-era scripts + rename analyze script

Removed: phase7_sweep.py, phase7_aggregate.py, phase7_baseline_snapshots.py,
check_parameter_drift.py, probe_*.py, keypress_audit.py, batch_run.sh,
test_run.sh, __deprecated__/, figure1+2 PNGs, and the two test files that
covered the deleted scripts. Renamed phase7_analysis.py to analyze_sessions.py
with a generic --root flag and SP-agnostic docstring. Added docs/pipeline-flow.md
and docs/sp12-hardcoded-findings.md scaffolds for the SP12 walk.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 9: Run pytest one final time**

```bash
uv run pytest --ignore=tests/test_phase4b_paradigm_smokes.py -q
```

Expected: still green; count is the pre-task count minus the two test files removed.

---

### Task 2: Docs consolidation — SP11 phase deliverables

**Files:**
- Create: `docs/sp11-complete.md`
- Delete: `docs/sp11-phase2-deliverable.md`, `docs/sp11-phase3-deliverable.md`, `docs/sp11-phase3-cognitionrun-probe.md`, `docs/sp11-phase4a-spike.md`, `docs/sp11-phase4b-deliverable.md`, `docs/sp11-phase5a-deliverable.md`, `docs/sp11-phase5a-stopit-probe.md`, `docs/sp11-phase5b-deliverable.md`, `docs/sp11-phase5b-drift-report.md`, `docs/sp11-phase6-deliverable.md`, `docs/sp11-phase6-audit-planning.md`, `docs/sp11-phase7-results.md`, `docs/sp11-phase7-results.json`, `docs/sp11-phase8-writeup-template.md`
- Keep: `docs/sp11-backlog.md`, `docs/sp11-unsupported.md`

- [ ] **Step 1: List the existing SP11 phase docs**

```bash
ls docs/sp11-phase*
```

Expected output: 14 files (see Files list above).

- [ ] **Step 2: Confirm no live code references these doc filenames**

```bash
grep -rn 'sp11-phase' src/ scripts/ tests/ 2>&1
```

Expected: no matches. (Docs reference each other, but no code does.)

- [ ] **Step 3: Create `docs/sp11-complete.md` with the consolidated summary**

```markdown
# SP11 complete — Playwright recommit + N=5 measurement

**Tag:** `sp11-complete` (pending; tagged at end of SP12 Phase 4 deliverable)
**Branch:** `sp11/playwright-recommit`
**Goal:** return the bot to a Playwright input-layer path, validate
cross-deployment generalization on 4 paradigms, measure post-calibration
behavior.

## What SP11 produced

- **Phase 1:** branch creation, file inventory, cherry-picks from sp10
  (audit_alignment.py + CSE label fix + writer microsecond), URL-label
  adapter aliases.
- **Phase 2:** effects-library gap-fill (practice_effect,
  vigilance_decrement, pink_noise alpha convention, condition_repetition
  deprecation).
- **Phase 3:** calibration pass infrastructure (KeypressDeliverer
  abstraction, estimator, bimodality detection, regression fallback;
  cognition.run probe verified jsPsych 7.3.1).
- **Phase 4a:** CDP feasibility spike — 100% fidelity on expfactory Stroop.
- **Phase 4b:** canonical CDPDeliverer + PlaywrightKeyboardDeliverer +
  PlaywrightGateDismisser + four-step protocol + per-trial delivery.channel
  logging.
- **Phase 5a:** executor wiring + sampler integration + pilot-time
  alignment via deferred Phase 2 live-LLM test (PASSED in 6:22).
- **Phase 5b:** TaskCard regeneration on 4 paradigms + calibration policy
  (auto-invocation default-on, --no-calibration for Phase 7 pre-cal arm),
  drop-from-scope machinery (sp11_supported field), parameter drift report.
- **Phase 5c:** Stroop variance characterization (3 additional regens) +
  scope-of-validity L17 (§6.2 reinterpretation as absolute |z| against
  human reference, not deltas from sp9c).
- **Phase 6:** audit-script generalization — `scripts/audit_alignment.py`
  paradigm-aware via `--label`, trial-counter pairing for sp11
  input-layer logs, rt-match fallback for sp10 legacy. Empirical anchor:
  118/120 paired × 118/118 within-pair = 98.3% effective fidelity on
  the Phase 5a pilot session.
- **Phase 7 N=30 sweep:** Stroop 60/60 perfect, expfactory_stop_signal
  30/30 + 2/30 (network outage overnight), stopit + cognitionrun
  re-runs landed via targeted N=5 sweeps. Final results in
  `docs/sp12-deliverable.md` (SP12 re-measurement supersedes Phase 7
  results).
- **Phase 7 N=5 results (pre-SP12 cleanup baseline):** see git history
  at commit `ffb9f07` (`docs/sp11-phase7-results.md`).

## Scope-of-validity additions accumulated in SP11

L9–L18 in `docs/scope-of-validity.md`. Each is a small disclosure of
a concrete capability or limitation:

- L9: calibration variance ceiling
- L10: calibration channels (CDP primary, keyboard fallback)
- L11: four-step protocol
- L12: trial-marker pairing
- L13: executor delivery + paradigm-configurable dwell
- L14: calibration-adjusted sampling
- L15: drop-from-scope policy
- L16: pre-cal vs post-cal experimental arms
- L17: §6.2 absolute |z| reinterpretation
- L18: audit-script generalization

## Generalization status at SP11 close

3 of 4 paradigms support a cautious cross-deployment claim with
structurally humanlike patterns (Stroop effect, race-model SSRT,
Gratton CSE within norm on expfactory Stroop). Absolute parameters
drift above human norms on Stroop (RTs +200-400 ms) and stopit
(SSRT > 280 ms). cognitionrun shows the Stroop effect but fails on
the sequence-dependency metric (Gratton CSE too negative) and has
an operational calibration defect.

## Backlog rolled into SP12

- Codebase simplification (this SP)
- cognitionrun calibration-pass defect (per `docs/sp11-backlog.md`)
- jsPsych platform-recording gap (memory:
  [[project_jspsych_keypress_layer_d]])

```

- [ ] **Step 4: Delete the 14 individual phase docs**

```bash
git rm docs/sp11-phase2-deliverable.md \
       docs/sp11-phase3-deliverable.md \
       docs/sp11-phase3-cognitionrun-probe.md \
       docs/sp11-phase4a-spike.md \
       docs/sp11-phase4b-deliverable.md \
       docs/sp11-phase5a-deliverable.md \
       docs/sp11-phase5a-stopit-probe.md \
       docs/sp11-phase5b-deliverable.md \
       docs/sp11-phase5b-drift-report.md \
       docs/sp11-phase6-deliverable.md \
       docs/sp11-phase6-audit-planning.md \
       docs/sp11-phase7-results.md \
       docs/sp11-phase7-results.json \
       docs/sp11-phase8-writeup-template.md
```

- [ ] **Step 5: Commit consolidation**

```bash
git add docs/sp11-complete.md
git commit -m "docs(sp12): consolidate 14 SP11 phase docs into sp11-complete.md

The per-phase docs were live-running working notes; their history
is preserved in git but their continued presence in docs/ added
14 nearly-identical headers for a new reader to wade through. The
consolidated sp11-complete.md retains the substantive findings
(scope-of-validity additions, generalization status, backlog).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Confirm no broken doc links**

```bash
grep -rn 'sp11-phase' docs/ 2>&1
```

Expected: no matches. (The only references should be in the git
history of `sp11-complete.md`'s own pointer to commit `ffb9f07`.)

---

### Task 3: `cli.py` walk-and-prune

**Files:**
- Modify: `src/experiment_bot/cli.py`
- Append: `docs/pipeline-flow.md`
- Append: `docs/sp12-hardcoded-findings.md`

- [ ] **Step 1: Size the module + identify call sites**

```bash
wc -l src/experiment_bot/cli.py
grep -rn 'from experiment_bot.cli' src/ tests/ 2>&1
grep -rn 'experiment_bot.cli:main' pyproject.toml
```

Expected: `cli.py` around 150 LOC; main entry point is `experiment_bot.cli:main`; tests reference `from experiment_bot.cli import main`.

- [ ] **Step 2: Read `cli.py` top-to-bottom and list candidate removals**

Open the file. Likely candidates to evaluate:
- `--no-calibration` flag (Phase 7 pre-cal arm; that experiment is done)
- `--skip-calibration-pass` flag (test escape hatch; only used by tests)
- The sp11_supported guard block (referenced via task_specific.sp11_supported)

For each: confirm with `grep -rn '<symbol>' src/ tests/ scripts/ docs/`.

- [ ] **Step 3: Post candidate list as checkpoint to user**

The checkpoint message names each candidate, its grep call-site count, and a one-line rationale. Format:

```
Module: src/experiment_bot/cli.py (NNN LOC)

Removal candidates:
- `--no-calibration` flag — called only by Phase 7 sweep wrapper (already deleted in Task 1); not part of production runs.
- `--skip-calibration-pass` flag — called only by test_cli_phase5b.py (would be removed alongside).
- sp11_supported guard — only triggered when cognitionrun_stroop was scope-dropped; cleaned up in Phase 7 commit c217823.

Survives: --label, --headless, --taskcards-dir, --seed, --verbose.

Veto any candidate?
```

Wait for user response. If approved, proceed.

- [ ] **Step 4: Remove `--no-calibration` flag**

In `src/experiment_bot/cli.py`, remove the `@click.option("--no-calibration", ...)` decorator + the corresponding `no_calibration` parameter from `main()` + the block in `_run_task` that sets `taskcard.runtime.calibration_apply_to_sampler = False`.

Run:

```bash
uv run pytest tests/test_cli_phase5b.py -q
```

Expected: tests previously asserting `--no-calibration` behavior now fail. Either remove those tests (if `--skip-calibration-pass` is also removed) or update them. Plan continues assuming both flags removed.

- [ ] **Step 5: Remove `--skip-calibration-pass` flag**

Same as Step 4 for the `--skip-calibration-pass` flag.

- [ ] **Step 6: Delete the now-obsolete tests**

```bash
git rm tests/test_cli_phase5b.py
```

- [ ] **Step 7: Remove the sp11_supported guard block in `_run_task`**

The guard checks `taskcard.task_specific.get("sp11_supported", True)` and raises a ClickException. Since cognitionrun is now back in scope (Task 2 sp11-complete.md documents this), this guard has no production trigger. Remove the entire `if sp11_supported is False:` block.

Also remove the `drop_from_scope.py` module's CLI-guard-related helpers if they're now unused (this is part of Task 6's calibration walk; just note it here).

- [ ] **Step 8: Run pytest**

```bash
uv run pytest --ignore=tests/test_phase4b_paradigm_smokes.py -q
```

Expected: all green. Count drops by however many tests test_cli_phase5b.py held.

- [ ] **Step 9: Append cli.py section to `docs/pipeline-flow.md`**

Add at the end of the existing pipeline-flow.md:

```markdown
## 1. CLI entry: `cli.py`

The bot launches via `experiment-bot <url> --label X`. The CLI:
1. Loads the latest TaskCard for `<label>` via `taskcard.loader.load_latest`.
2. Samples session-level distributional parameters via
   `taskcard.sampling.sample_session_params(seed=...)`.
3. Builds a SessionAgent via `_build_session_agent()` (returns None if
   no LLM credentials available; the executor degrades gracefully).
4. Constructs a `TaskExecutor`, awaits `executor.run(url)`.

Entry point: `src/experiment_bot/cli.py:main` (click command).
```

- [ ] **Step 10: Append findings (if any) to `docs/sp12-hardcoded-findings.md`**

Likely no hardcoded paradigm knowledge in cli.py — it routes generic. If grep finds nothing of concern, add:

```markdown
## src/experiment_bot/cli.py

(no paradigm-specific values; CLI is paradigm-agnostic.)
```

- [ ] **Step 11: Commit the cli.py walk**

```bash
git add -A
git commit -m "refactor(sp12): cli.py walk-and-prune

Removed --no-calibration and --skip-calibration-pass CLI flags
(Phase 7 pre-cal/test-escape arms; experiment is done). Removed
sp11_supported guard (cognitionrun returned to scope in Phase 7;
the drop-from-scope cli path no longer triggers in production).
Deleted tests/test_cli_phase5b.py (covered the removed flags).
Added pipeline-flow.md section for CLI; cli.py is paradigm-agnostic.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `core/executor.py` walk-and-prune

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Append: `docs/pipeline-flow.md`, `docs/sp12-hardcoded-findings.md`

`executor.py` is 1295 LOC. Per the spec's "sub-walks for big modules" rule, split into sub-walks. Each sub-walk follows the walk protocol from this plan's intro.

- [ ] **Step 1: Size the module + identify call sites**

```bash
wc -l src/experiment_bot/core/executor.py
grep -n '^    async def \|^    def \|^class ' src/experiment_bot/core/executor.py
```

Note the methods + their line ranges. Plan to split into sub-walks at these boundaries.

- [ ] **Step 2: Define sub-walk boundaries**

Based on Step 1's grep output, the planned sub-walks are:
- 4a: `__init__` + class-level constants + `_resolve_key_mapping` + `_setup_keypress_deliverer` (init + delivery setup)
- 4b: `_run_calibration_pass` + `_fire_response_key` (calibration + per-trial fire)
- 4c: `_invoke_session_agent` (LLM key-mapping)
- 4d: `run` orchestration method (~30 lines)
- 4e: `_trial_loop` (main loop)
- 4f: `_execute_trial` (per-trial dispatcher) + `_pick_wrong_key` + `_handle_feedback` + `_log_trial_with_keypress_diag`
- 4g: `_wait_for_completion` + `_install_keydown_listener` + helpers

If the actual method boundaries differ, adjust the sub-walks accordingly.

- [ ] **Step 3 (4a sub-walk): Read init + delivery setup; list candidates**

Read lines 60–250 (approximately). Likely candidates:
- `_seen_response_keys` field — used by calibration default key selection; verify it's still needed if calibration default is changed.
- `_calibration_run`, `_delivery_channel_log`, `_fire_skip_log` instance vars — exercised? confirm in `bot_log` writer.
- `_session_agent_directive` storage — only used in `finally` to write to metadata; could be inlined.

Post checkpoint to user. After approval, delete + commit.

- [ ] **Step 4 (4b sub-walk): Calibration + per-trial fire**

Read `_run_calibration_pass` + `_fire_response_key`. Likely candidates:
- `calibration_run_pass` / `calibration_apply_to_sampler` branching — if both Phase 7-era flags are removed via Task 3, the conditional in `_run_calibration_pass` simplifies.
- The `applied_note = "applied to sampler"` / `"NOT applied (pre-cal arm)"` logging — same.
- `--per-session-timeout-s` was added in Phase 7 wrapper; not in executor, but verify there's no echo here.

Post checkpoint. Delete approved items, run pytest, commit.

- [ ] **Step 5 (4c sub-walk): SessionAgent**

Read `_invoke_session_agent` + `_session_agent_directive` flow. Candidates:
- The agent's negative result handling (SP9a empirical: hypothesis not supported) — is the directive ever USED in production? Confirm via grep on `_runtime_key_mapping`.
- If `_runtime_key_mapping` is consulted in `_resolve_response_key` only and almost-always falls through to static keymap, the entire SessionAgent path may be a candidate for removal.

Post checkpoint with a clear question: is SessionAgent's runtime LLM call earning its keep? If not, removing it shrinks the bot meaningfully. User decides.

- [ ] **Step 6 (4d sub-walk): `run` orchestration**

Read the `async def run` method. Candidates:
- The finally-block metadata payload accumulates many fields; some may be vestigial (e.g., `session_agent_directive` if 4c removes the path).
- The hard-fail-on-zero-trials check — keep (G4: hard-fail on broken state).

- [ ] **Step 7 (4e sub-walk): `_trial_loop`**

Read. Candidates:
- `stuck_detector` — verify it's exercised; if not, remove.
- `consecutive_misses` + `advance_interval_polls` logic — used for instruction advance; verify.
- The phase==INSTRUCTIONS branch + the navigator.execute_all coupling discovered in Phase 7's cognitionrun debug — already understood; document in pipeline-flow.md.

- [ ] **Step 8 (4f sub-walk): `_execute_trial` + helpers**

Read. Candidates:
- The interrupt-failure path (stop-signal-specific?); confirm via grep that `trial_interrupt.detection_condition` is generic, not Stop-Signal-named.
- `_pick_wrong_key` — generic? confirm.
- `_log_trial_with_keypress_diag` — keypress-receipt diagnostic from SP7; confirm it's still adding value or can be folded into the standard log.

- [ ] **Step 9 (4g sub-walk): completion + listeners**

Read. Candidates:
- `_install_keydown_listener` — SP7 diagnostic; if `_log_trial_with_keypress_diag` is removed in 4f, this could go too.
- Various dead helpers if any.

- [ ] **Step 10: After all sub-walks, run full pytest one final time**

```bash
uv run pytest --ignore=tests/test_phase4b_paradigm_smokes.py -q
```

Expected: green.

- [ ] **Step 11: Append the unified executor section to `docs/pipeline-flow.md`**

```markdown
## 2. TaskExecutor: `core/executor.py`

The executor coordinates one bot session. Flow:

1. **Open page** via Playwright → CDP session.
2. **Construct KeypressDeliverer** (`_setup_keypress_deliverer`).
   CDP is default; falls back to page.keyboard.press if CDP
   unavailable (Firefox/WebKit).
3. **Navigate instructions** (`_navigator.execute_all`).
4. **Install keydown listener** (`_install_keydown_listener`) — if
   retained.
5. **SessionAgent** (`_invoke_session_agent`) — if retained.
6. **Calibration pass** (`_run_calibration_pass`) — fires N keys with
   the four-step protocol; estimates offset; installs result on
   sampler if model is non-escalate.
7. **Trial loop** (`_trial_loop`) — polls for stimulus, samples RT,
   fires response via `_fire_response_key`, logs trial.
8. **Completion + finalize** (`_wait_for_completion`, finally-block) —
   captures data, writes bot_log.json + run_metadata.json (+ Phase 2
   adds run_trace.json).

Entry point: `src/experiment_bot/core/executor.py:TaskExecutor.run`.
```

- [ ] **Step 12: Append findings to sp12-hardcoded-findings.md**

Add findings discovered during each sub-walk. Be specific:

```markdown
## src/experiment_bot/core/executor.py

- (example) Line NNN: `response_window_js` evaluation assumes the JS
  expression returns truthy for "open" and falsy for "closed" —
  documented contract.
- (no other paradigm-specific values found.)
```

- [ ] **Step 13: Commit the executor walk**

```bash
git add -A
git commit -m "refactor(sp12): executor.py walk-and-prune

<summary of removed sub-items from sub-walks 4a-4g>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `core/config.py` walk-and-prune

**Files:**
- Modify: `src/experiment_bot/core/config.py`
- Append: `docs/pipeline-flow.md`, `docs/sp12-hardcoded-findings.md`

`config.py` is 838 LOC, mostly dataclasses. Sub-walks by dataclass cluster:
- 5a: top-level (TaskConfig, RuntimeConfig)
- 5b: stimulus/response/distribution clusters
- 5c: temporal effects (Autocorrelation, FatigueDrift, ConditionRepetition, PracticeEffect, VigilanceDecrement, PinkNoise, TemporalEffects)
- 5d: PerformanceConfig + NavigationConfig + PhaseDetectionConfig + TimingConfig + AdvanceBehaviorConfig + TrialInterruptConfig + DataCaptureConfig + AttentionCheckConfig + PilotConfig + BetweenSubjectJitterConfig

- [ ] **Step 1: Size + identify call sites**

```bash
wc -l src/experiment_bot/core/config.py
grep -c '^class ' src/experiment_bot/core/config.py
```

Note the class count.

- [ ] **Step 2: Read top-level (RuntimeConfig, TaskConfig)**

Candidates:
- `calibration_run_pass` and `calibration_apply_to_sampler` fields — if Task 3 removed the CLI flags, these RuntimeConfig fields are dead.
- `delivery_channel` — confirm it's read (executor reads it for `_setup_keypress_deliverer`); keep.
- `session_agent_enabled` — confirm SessionAgent is still wired (Task 4c outcome dictates).

- [ ] **Step 3: Sub-walks 5b–5d**

For each sub-walk, list candidates, checkpoint, delete approved, commit.

- [ ] **Step 4: Run pytest**

```bash
uv run pytest --ignore=tests/test_phase4b_paradigm_smokes.py -q
```

- [ ] **Step 5: Append docs**

```markdown
## 3. TaskCard config: `core/config.py`

Dataclass tree representing the TaskCard JSON. Loaded via
`taskcard.loader.load_latest`. Roundtrip through to_dict/from_dict
preserves fidelity. Each runtime knob has a dataclass field with a
default; the Reasoner emits values for the ones it determines.

Entry point: `src/experiment_bot/core/config.py:TaskConfig.from_dict`.
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(sp12): config.py walk-and-prune

<summary>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `calibration/` walk-and-prune

**Files:**
- Modify or delete: `src/experiment_bot/calibration/deliverer.py`, `cdp_deliverer.py`, `keyboard_deliverer.py`, `estimator.py`, `runner.py`, `drop_from_scope.py`, `playwright_gate_dismisser.py`, `focus.py`
- Append: `docs/pipeline-flow.md`, `docs/sp12-hardcoded-findings.md`

Per the spec, each calibration submodule gets its own sub-walk.

- [ ] **Step 1: Inventory the package**

```bash
wc -l src/experiment_bot/calibration/*.py
grep -rn 'from experiment_bot.calibration' src/ tests/ scripts/
```

- [ ] **Step 2: Walk `deliverer.py` (abstract interface + MockDeliverer)**

Read. Likely keep entirely — it's the abstract interface. Check `MockDeliverer` parameters that may not be exercised:
- `misrecording_rate`, `misrecording_alt_keys` — used by estimator tests
- `bimodal_second_mode` — used by bimodality test

If all parameters are exercised in tests, keep all.

- [ ] **Step 3: Walk `cdp_deliverer.py` (canonical CDP path)**

Read. Likely candidates:
- KEY_TO_CDP_FIELDS entries that are never fired (audit by checking what response_key values get emitted across the 4 paradigms' TaskCards). If e.g. `Backspace` is never fired, remove.
- Fallback paths in `cdp_fields_for` for unmapped letters/digits — keep (G1).

- [ ] **Step 4: Walk `keyboard_deliverer.py`**

Read. Confirm it's still used by tests + Phase 7 sweep flag. If `delivery_channel = "keyboard"` is never set in production runs, the whole module is a candidate for removal (G5: don't keep code for hypothetical needs).

- [ ] **Step 5: Walk `estimator.py`**

Read. Confirm all four model outcomes are exercised:
- `fixed_offset` — likely common
- `regression` — exercised when SD > threshold
- `escalate` — exercised by bimodal detection (cognitionrun-style)
- `too_few_events` — exercised when N < 5

If `regression` is never selected in real runs, the regression code is a candidate.

- [ ] **Step 6: Walk `runner.py`**

Read. Candidates:
- `_summarize_delivery_channels` — used by the writer; confirm.
- `NoGateDismisser`, `MockGateDismisser` — used by tests only; confirm fixture role.

- [ ] **Step 7: Walk `drop_from_scope.py`**

Read. If Task 3 removed the sp11_supported CLI guard, drop_from_scope's `mark_taskcard_unsupported` + `append_unsupported_note` may be entirely unused. Confirm via grep across `src/`, `scripts/`, `tests/`. If unused, delete the whole module + its tests.

- [ ] **Step 8: Walk `playwright_gate_dismisser.py`**

Read. Confirm it's still used by `_run_calibration_pass` (the only call site). Generic — keep.

- [ ] **Step 9: Walk `focus.py`**

Read. The three JS arrows (`JSPSYCH_DISPLAY_FOCUS_JS`, `BODY_FOCUS_JS`, `IFRAME_CONTENT_FOCUS_JS`) are caller-supplied. Confirm any caller actually passes them. If none of the three are referenced outside the module + its tests, the whole module is unused. If so, delete.

- [ ] **Step 10: Run pytest after each removal**

```bash
uv run pytest --ignore=tests/test_phase4b_paradigm_smokes.py -q
```

- [ ] **Step 11: Append docs section**

```markdown
## 4. Calibration: `src/experiment_bot/calibration/`

Optional pre-trial-loop pass that fires N keys to measure platform-side
recording offset. Result is installed on the sampler; subsequent RT
samples are adjusted to compensate. Four model outcomes:

| Model | Trigger | Action |
|---|---|---|
| `fixed_offset` | SD ≤ 30ms, unimodal | shift sampler RT by mean |
| `regression` | SD > 30ms, unimodal | invert linear fit |
| `escalate` | bimodal detected | no adjustment |
| `too_few_events` | < 5 paired events | no adjustment |

Files:
- `deliverer.py` — abstract `KeypressDeliverer` interface
- `cdp_deliverer.py` — Chrome DevTools Protocol implementation (canonical)
- `runner.py` — orchestrator: `run_calibration(deliverer, gate_dismisser)`
- `estimator.py` — fit per-event offsets to one of the 4 models above
- `playwright_gate_dismisser.py` — visible-button + keyboard-fallback gate
- (focus.py, keyboard_deliverer.py, drop_from_scope.py — kept iff exercised)

Entry point: `src/experiment_bot/core/executor.py:TaskExecutor._run_calibration_pass`.
```

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor(sp12): calibration/ walk-and-prune

<summary of per-submodule changes>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `output/writer.py` walk

**Files:**
- Modify: `src/experiment_bot/output/writer.py`
- Append: `docs/pipeline-flow.md`

- [ ] **Step 1: Read + list candidates**

```bash
wc -l src/experiment_bot/output/writer.py
```

Read. Phase 2 adds `run_trace.json` to this file; for the walk, just verify nothing in the current writer is unused. The EXPERIMENT_BOT_OUTPUT_DIR env var is read here — keep it.

- [ ] **Step 2: Checkpoint + delete + commit per protocol.**

- [ ] **Step 3: Append docs section**

```markdown
## 5. Output writer: `output/writer.py`

Writes the per-session output dir at `<output_root>/<task_name>/<timestamp>/`.
Honors `EXPERIMENT_BOT_OUTPUT_DIR` env var (overrides the repo-relative
default — used by orchestration scripts).

Outputs per session:
- `bot_log.json` — per-trial log + per-trial delivery metadata
- `run_metadata.json` — session-level metadata (seed, params, delivery
  channel counts, calibration result summary)
- `config.json` — the TaskCard's effective config for this run
- `experiment_data.{csv,json}` — platform's own data export (saved by
  executor before finalize)
- `screenshots/` — startup + error screenshots
- (Phase 2 adds `run_trace.json` — see Phase 2 plan)

Entry point: `src/experiment_bot/output/writer.py:OutputWriter.create_run`.
```

---

### Task 8: `core/distributions.py` walk

**Files:**
- Modify: `src/experiment_bot/core/distributions.py`
- Append: `docs/pipeline-flow.md`, `docs/sp12-hardcoded-findings.md`

`distributions.py` is 360 LOC — borderline for sub-walks per the spec's >500 threshold. Treat as one walk.

- [ ] **Step 1: Read + list candidates**

Read. Likely keep — the sampler logic is central. Candidates:
- `_apply_calibration_adjustment` — if calibration is preserved, keep.
- `_EXECUTOR_APPLIED_EFFECTS` constant naming `post_event_slowing` — check the comment says "callers configure" and verify no hardcoded values.

- [ ] **Step 2: Checkpoint + delete approved + run pytest + commit**

- [ ] **Step 3: Append docs section**

```markdown
## 6. RT sampler: `core/distributions.py`

Per-condition RT sampling with temporal-effects application. The
sampler:
1. Pulls the per-condition ex-Gaussian / lognormal / shifted-Wald
   distribution from the TaskCard's `response_distributions`.
2. Draws a raw RT.
3. Applies temporal effects in registry order (autocorrelation,
   fatigue_drift, condition_repetition [deprecated], pink_noise,
   practice_effect, vigilance_decrement, lag1_pair_modulation,
   post_event_slowing).
4. Applies calibration adjustment if a CalibrationResult is installed.

Entry point: `core/distributions.py:ResponseSampler.sample_rt`.
```

---

### Task 9: `core/stimulus.py` + `core/phase_detection.py` walks

**Files:**
- Modify: `src/experiment_bot/core/stimulus.py`, `src/experiment_bot/core/phase_detection.py`
- Append: `docs/pipeline-flow.md`

- [ ] **Step 1: stimulus.py walk + commit per protocol**

- [ ] **Step 2: phase_detection.py walk + commit per protocol**

- [ ] **Step 3: Append docs section**

```markdown
## 7. Stimulus detection + phase: `core/stimulus.py`, `core/phase_detection.py`

`StimulusLookup.identify(page)` polls the page DOM/state for any of
the configured stimuli. Each stimulus's `detection` block declares
method (`dom_query`, `js_eval`) and selector. The first match wins.

`detect_phase(page, config)` classifies the current page state into
TaskPhase.{INSTRUCTIONS, FEEDBACK, TEST, COMPLETE, etc.} via the
TaskCard's `phase_detection` JS predicates. The trial loop dispatches
on phase to know whether to fire a response, advance instructions,
or finalize.

Entry point: `core/stimulus.py:StimulusLookup.identify`.
```

---

### Task 10: `navigation/` walk

**Files:**
- Modify: `src/experiment_bot/navigation/navigator.py`, `src/experiment_bot/navigation/stuck.py`
- Append: `docs/pipeline-flow.md`

- [ ] **Step 1: navigator.py walk per protocol**

- [ ] **Step 2: stuck.py walk per protocol**

Note: stuck.py exists alongside navigator.py; if it's small and only used by navigator, evaluate folding it in.

- [ ] **Step 3: Append docs**

```markdown
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
```

---

### Task 11: `agent/` walk

**Files:**
- Modify or delete (depending on Task 4c outcome): `src/experiment_bot/agent/`
- Append: `docs/pipeline-flow.md` (only if retained)

- [ ] **Step 1: Verify SessionAgent's production role**

Per Task 4c (executor sub-walk 4c), determine whether the SessionAgent runtime LLM call is exercised in current production. If Task 4c removed the executor's `_invoke_session_agent` call, the entire `agent/` package becomes unused.

```bash
grep -rn 'from experiment_bot.agent\|SessionAgent' src/ tests/ scripts/
```

- [ ] **Step 2: If unused, delete the package + tests**

```bash
git rm -r src/experiment_bot/agent/
git rm tests/test_session_agent.py  # if exists
```

- [ ] **Step 3: If retained, walk each module + append docs**

If retained, follow the standard walk protocol per module. Docs:

```markdown
## 9. Session-time LLM key resolution: `agent/session_agent.py` (if retained)

`SessionAgent.resolve_key_mapping(page)` runs once per session after
navigation, probes the live page (DOM + window globals + screenshot),
and asks `claude-haiku-4-5` for a `KeyMappingDirective`. The directive's
key map takes precedence over the static TaskCard key_map in
`TaskExecutor._resolve_response_key`.

Entry point: `agent/session_agent.py:SessionAgent.resolve_key_mapping`.
```

- [ ] **Step 4: pytest + commit**

---

### Task 12: `llm/` walk

**Files:**
- Modify: `src/experiment_bot/llm/protocol.py`, `cli_client.py`, `api_client.py`, `factory.py`
- Append: `docs/pipeline-flow.md`

- [ ] **Step 1: Walk each per protocol**

- [ ] **Step 2: Append docs**

```markdown
## 10. LLM client abstraction: `llm/`

Two-implementation client pattern:
- `cli_client.py` — wraps the `claude` CLI binary
- `api_client.py` — wraps the Anthropic Python SDK

`factory.py:build_default_client(model=...)` picks based on env (API
key → SDK; else CLI on PATH). Used by:
- Reasoner pipeline stages (offline, before sessions)
- SessionAgent runtime LLM call (during session, if retained)

Entry point: `llm/factory.py:build_default_client`.
```

---

### Task 13: `taskcard/` walk

**Files:**
- Modify: `src/experiment_bot/taskcard/loader.py`, `types.py`, `sampling.py`, `hashing.py`
- Append: `docs/pipeline-flow.md`

- [ ] **Step 1: Walk each per protocol**

- [ ] **Step 2: Append docs**

```markdown
## 11. TaskCard load + sample: `taskcard/`

- `loader.py` — `load_latest(taskcards_dir, label)` finds the most-recent
  TaskCard JSON for a label (by file mtime).
- `types.py` — `TaskCard` Pydantic / dataclass shape with
  `produced_by` provenance.
- `sampling.py` — `sample_session_params(taskcard_dict, seed)` draws
  between-subject jitter for the session.
- `hashing.py` — SHA256 over the TaskCard for `produced_by.taskcard_sha256`.

Entry point: `taskcard/loader.py:load_latest`.
```

---

### Task 14: `reasoner/` walk (last; offline)

**Files:**
- Modify: `src/experiment_bot/reasoner/*.py`
- Append: `docs/pipeline-flow.md`, `docs/sp12-hardcoded-findings.md`

- [ ] **Step 1: Inventory + decide whether to walk**

```bash
wc -l src/experiment_bot/reasoner/*.py
```

The reasoner is offline — production runs don't traverse it. If the walk is mostly cleanup (removing dead helpers in stage files), proceed. If it's substantive (e.g., simplifying parse_retry or pipeline orchestration), document carefully because changes here force TaskCard regeneration in Phase 3.

- [ ] **Step 2: Walk per sub-stage**

For each of `pipeline.py`, `stage1_structural.py` ... `stage6_pilot.py`, `parse_retry.py`, `validate.py`, `openalex.py`, `scraper.py`, `normalize.py`: list candidates, checkpoint, delete approved, run pytest, commit.

- [ ] **Step 3: If any Stage 1–5 prompt or schema was touched, regenerate TaskCards in Phase 3**

Track which stages were modified. If Stages 1, 2, 3, 4, 5 saw any prompt or output-schema change (not just internal refactor), Phase 3 must regenerate all 4 paradigms' TaskCards before re-measurement.

- [ ] **Step 4: Append docs**

```markdown
## 12. Reasoner pipeline: `reasoner/` (offline, pre-session)

5-stage offline pipeline that produces a TaskCard from a paradigm
URL + literature. Not traversed during sessions.

| Stage | Module | Role |
|---|---|---|
| 1 | stage1_structural.py | Parse page source → stimuli, navigation, runtime |
| 2 | stage2_behavioral.py | Add response_distributions, performance, temporal_effects |
| 3 | stage3_citations.py | Attach literature citations to numeric parameters |
| 4 | stage4_doi_verify.py | Verify citation DOIs via OpenAlex |
| 5 | stage5_sensitivity.py | Tag sensitivity per parameter |
| 6 | stage6_pilot.py | Live-DOM pilot validation against URL (optional via --skip-pilot) |

Entry point: `reasoner/pipeline.py:ReasonerPipeline.run`.
```

---

### Task 15: `effects/` walk

**Files:**
- Modify: `src/experiment_bot/effects/handlers.py`, `registry.py`, `validation_metrics.py`
- Append: `docs/pipeline-flow.md`

- [ ] **Step 1: Walk per protocol**

- [ ] **Step 2: Append docs**

```markdown
## 13. Effects library: `effects/`

Generic temporal-effects mechanisms applied by the sampler.

- `registry.py` — name → handler dispatch
- `handlers.py` — per-mechanism implementations (autocorrelation,
  fatigue_drift, lag1_pair_modulation, post_event_slowing,
  practice_effect, vigilance_decrement, pink_noise)
- `validation_metrics.py` — computation functions for population-level
  metrics (lag1_autocorrelation, post_error_slowing_magnitude, ssrt_integration,
  fit_ex_gaussian, cse_magnitude, lag1_pair_contrast)

Per G2, mechanisms are named in mechanism vocabulary, not paradigm
vocabulary. Conflict-paradigm "CSE" is exposed as `cse_magnitude` in
validation_metrics.py as a thin wrapper around `lag1_pair_contrast`.

Entry point: `effects/registry.py:EFFECT_REGISTRY`.
```

---

### Task 16: `validation/` walk

**Files:**
- Modify: `src/experiment_bot/validation/oracle.py`, `platform_adapters.py`, `eisenberg.py`, `cli.py`
- Append: `docs/pipeline-flow.md`

- [ ] **Step 1: Walk per protocol**

- [ ] **Step 2: eisenberg.py** — likely candidate for removal if not exercised in production. Confirm via grep.

- [ ] **Step 3: Append docs**

```markdown
## 14. Validation oracle: `validation/`

Optional post-session validation. Reads platform data export +
TaskCard, computes per-metric values, gates against norms file ranges.

- `oracle.py` — `METRIC_REGISTRY` dispatch + `compute_session(...)`
- `platform_adapters.py` — paradigm-aware dispatch:
  - `PLATFORM_ADAPTERS` (label → reader function)
  - `TEST_ROW_PREDICATES` (label → raw-row test-trial predicate, used
    by `scripts/audit_alignment.py`)
- `cli.py` — `experiment-bot-validate <session_dir>` standalone validator

Entry point: `validation/oracle.py:compute_session`.
```

---

## Phase 2 — Runtime visibility

### Task 17: Finalize `docs/pipeline-flow.md`

By the end of Phase 1, `pipeline-flow.md` already has 14 sections. This task tightens it.

**Files:**
- Modify: `docs/pipeline-flow.md`

- [ ] **Step 1: Read pipeline-flow.md end-to-end**

Check that each section is 2–4 sentences with a code-ref entry point. Trim verbose sections.

- [ ] **Step 2: Add a 5-line intro at top**

Add above the existing sections:

```markdown
# experiment_bot pipeline flow

A new reader who wants to understand what happens during
`experiment-bot <url> --label <paradigm>` can read this doc top-to-
bottom in ~10 minutes. Each section names a module, what it does in
2–4 sentences, and the entry point function with its line ref.

The bot's flow: CLI → executor.run → navigation → (session agent) →
calibration → trial loop → finalize. Section numbers below match
the order of execution.
```

- [ ] **Step 3: Confirm code-ref entry points resolve**

For each `entry point: <module>:<symbol>` line, verify the symbol exists:

```bash
for ref in $(grep -oE '`[a-z_/.]+:[A-Za-z_.]+`' docs/pipeline-flow.md | tr -d '`'); do
  file="${ref%:*}"
  sym="${ref#*:}"
  grep -q "${sym##*.}" "$file" 2>/dev/null && echo "OK $ref" || echo "MISSING $ref"
done
```

Expected: all `OK`.

- [ ] **Step 4: Commit**

```bash
git add docs/pipeline-flow.md
git commit -m "docs(sp12): finalize pipeline-flow.md (Phase 2 wrap)

Reads top-to-bottom in ~10 min. Each section names a module, what it
does, and the entry point. Code-ref resolution verified.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 18: Narrated stdout — 6-line readout

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Create: `tests/test_executor_narration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_executor_narration.py
"""SP12 Phase 2 — narrated stdout test."""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner


def test_narrated_stdout_has_six_stage_lines(tmp_path, capsys):
    """A clean session emits one stdout line per major stage.

    Expected stages, in order:
      1. navigate
      2. agent
      3. calibration
      4. trial_loop
      5. wait_completion
      6. save
    """
    # Construct a fake-everything executor and assert the narrate
    # method emits 6 lines in the right order.
    from experiment_bot.core.executor import TaskExecutor
    config = MagicMock()
    config.task.name = "test"
    config.runtime.timing.viewport = {"width": 1280, "height": 800}
    ex = TaskExecutor.__new__(TaskExecutor)
    ex._narrate = TaskExecutor._narrate.__get__(ex, TaskExecutor)
    ex._narrate("navigate", "ok")
    ex._narrate("agent", "skipped (no LLM)")
    ex._narrate("calibration", "model=fixed_offset n=30")
    ex._narrate("trial_loop", "trials=120")
    ex._narrate("wait_completion", "ok")
    ex._narrate("save", "written")
    out = capsys.readouterr().out
    lines = [l for l in out.split("\n") if l.startswith("[sp12]")]
    assert len(lines) == 6, f"expected 6 [sp12] lines, got {len(lines)}: {lines}"
    # Order: stage names appear in the order they were narrated
    for i, stage in enumerate(["navigate", "agent", "calibration",
                                "trial_loop", "wait_completion", "save"]):
        assert stage in lines[i], f"line {i} missing stage {stage}: {lines[i]}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_executor_narration.py -v
```

Expected: FAIL with `AttributeError: type object 'TaskExecutor' has no attribute '_narrate'`.

- [ ] **Step 3: Implement `_narrate` on TaskExecutor**

In `src/experiment_bot/core/executor.py`, add this method to TaskExecutor:

```python
    def _narrate(self, stage: str, detail: str) -> None:
        """SP12 Phase 2: narrate one stage transition to stdout.

        Emits a single line per major stage. The full 6-line readout
        is: navigate, agent, calibration, trial_loop, wait_completion,
        save. Suppressible via --verbose (which switches to per-trial
        DEBUG logging instead).
        """
        print(f"[sp12] {stage}: {detail}", flush=True)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_executor_narration.py -v
```

Expected: PASS.

- [ ] **Step 5: Wire `_narrate` at the 6 stage transition points in `TaskExecutor.run`**

Insert calls at:
1. After `await page.goto(task_url, wait_until="networkidle")`:
   `self._narrate("navigate", f"loaded {task_url}")`
2. After `await self._navigator.execute_all(...)` and before SessionAgent:
   `self._narrate("agent", "skipped" if self._session_agent is None else "active")`
3. After `await self._run_calibration_pass(page)`:
   ```python
   cal = self._calibration_run
   if cal is None:
       self._narrate("calibration", "skipped")
   else:
       self._narrate("calibration",
           f"model={cal.result.model} n_paired={cal.result.n_events_correctly_recorded}")
   ```
4. After `await self._trial_loop(page)`:
   `self._narrate("trial_loop", f"trials={self._trial_count}")`
5. After `await self._wait_for_completion(page)`:
   `self._narrate("wait_completion", "ok")`
6. In the finally block after `self._writer.finalize()`:
   `self._narrate("save", f"output={self._writer._run_dir}")`

- [ ] **Step 6: Run the full executor live-LLM test to confirm narration is integrated**

```bash
RUN_LIVE_LLM=1 uv run pytest tests/test_executor.py::test_live_executor_runs_against_regenerated_taskcard -v
```

Expected: PASS, with the 6 `[sp12]` lines visible in stdout.

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_narration.py
git commit -m "feat(sp12): narrated stdout — 6-line per-session readout

One line per stage: navigate, agent, calibration, trial_loop,
wait_completion, save. Tagged '[sp12]' to make grep-friendly.
Live test confirms all 6 emit in a real session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 19: Structured `run_trace.json`

**Files:**
- Modify: `src/experiment_bot/output/writer.py`
- Modify: `src/experiment_bot/core/executor.py`
- Create: `tests/test_run_trace.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_trace.py
"""SP12 Phase 2 — run_trace.json writer test."""
from __future__ import annotations

import json
from pathlib import Path

from experiment_bot.output.writer import OutputWriter


def test_run_trace_records_stage_entries(tmp_path):
    """run_trace.json contains one entry per recorded stage."""
    w = OutputWriter(base_dir=tmp_path)
    # Minimal config stub
    cfg = type("C", (), {"to_dict": lambda self: {}, "task": type(
        "T", (), {"name": "test"})()})()
    w.create_run("test", cfg)
    w.record_trace("navigate", {"loaded": "ok"}, duration_s=1.2)
    w.record_trace("calibration", {"model": "fixed_offset", "n": 30},
                   duration_s=6.5)
    w.finalize()
    trace_path = w._run_dir / "run_trace.json"
    assert trace_path.exists(), "run_trace.json not written"
    trace = json.loads(trace_path.read_text())
    assert len(trace["stages"]) == 2
    assert trace["stages"][0]["stage"] == "navigate"
    assert trace["stages"][0]["duration_s"] == 1.2
    assert trace["stages"][1]["stage"] == "calibration"
    assert trace["stages"][1]["data"]["model"] == "fixed_offset"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_run_trace.py -v
```

Expected: FAIL — `OutputWriter` has no `record_trace`.

- [ ] **Step 3: Implement `record_trace` + `_write_run_trace` on OutputWriter**

In `src/experiment_bot/output/writer.py`, add to OutputWriter:

```python
    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = _resolved_default_output_dir()
        self._base_dir = base_dir
        self._run_dir: Path | None = None
        self._trials: list[dict] = []
        self._trace_stages: list[dict] = []

    def record_trace(self, stage: str, data: dict, duration_s: float | None = None) -> None:
        """SP12 Phase 2: append one stage record to run_trace.json.

        Entries are one-per-stage (not per-trial). Captures stage
        name, structured per-stage data (e.g., calibration model,
        N trials, agent directive summary), and optional duration.
        """
        from datetime import datetime
        self._trace_stages.append({
            "stage": stage,
            "data": dict(data),
            "duration_s": duration_s,
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
```

And in `finalize`, write the trace file:

```python
    def finalize(self) -> None:
        # (existing finalize content here...)
        if self._run_dir is not None:
            trace_path = self._run_dir / "run_trace.json"
            trace_path.write_text(json.dumps(
                {"stages": self._trace_stages}, indent=2) + "\n")
```

(Adjust to integrate cleanly with the existing finalize body; ensure the trace file write happens unconditionally, even when no stages were recorded — empty `{"stages": []}` is fine.)

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_run_trace.py -v
```

Expected: PASS.

- [ ] **Step 5: Wire `record_trace` calls at the 6 executor stages**

In `TaskExecutor.run`, alongside each `self._narrate(...)` call, also call `self._writer.record_trace(stage, data, duration_s=...)`. Use the same data the `_narrate` line carries, structured:

```python
import time

# Track per-stage start times
nav_start = time.monotonic()
await page.goto(task_url, wait_until="networkidle")
self._narrate("navigate", f"loaded {task_url}")
self._writer.record_trace("navigate", {"url": task_url},
                           duration_s=time.monotonic() - nav_start)

# (analogously for agent, calibration, trial_loop, wait_completion, save)
```

- [ ] **Step 6: Live-LLM test confirms run_trace.json is written**

```bash
RUN_LIVE_LLM=1 uv run pytest tests/test_executor.py::test_live_executor_runs_against_regenerated_taskcard -v
```

After the run, verify `output/<task>/<timestamp>/run_trace.json` exists:

```bash
find output -name 'run_trace.json' -newer src/experiment_bot/output/writer.py | head -5
```

Expected: at least one file. Cat one to inspect:

```bash
cat $(find output -name 'run_trace.json' -newer src/experiment_bot/output/writer.py | head -1)
```

Expected: ~6 stage entries.

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/output/writer.py src/experiment_bot/core/executor.py tests/test_run_trace.py
git commit -m "feat(sp12): structured run_trace.json beside bot_log.json

Records one entry per major executor stage (navigate, agent, calibration,
trial_loop, wait_completion, save). Per-trial detail stays in bot_log.json;
trace is intentionally minimal (~6 entries per session).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Re-measurement

### Task 20: TaskCard regeneration decision

**Files:**
- (Read-only check based on Task 14 outcome)

- [ ] **Step 1: Inspect what changed in `reasoner/`**

```bash
git log --oneline ffb9f07..HEAD -- src/experiment_bot/reasoner/ src/experiment_bot/prompts/
```

If any commits modify Stage 1–5 prompts (`src/experiment_bot/prompts/system.md`, `schema.json`) or Stage 1–5 modules in a way that changes Reasoner output, regeneration is required.

- [ ] **Step 2: If regen required, regenerate all 4 SP11 paradigms**

```bash
uv run experiment-bot-reason https://deploy.expfactory.org/preview/10/ --label expfactory_stroop
uv run experiment-bot-reason https://deploy.expfactory.org/preview/9/ --label expfactory_stop_signal
uv run experiment-bot-reason https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html --label stopit_stop_signal
uv run experiment-bot-reason https://strooptest.cognition.run/ --label cognitionrun_stroop
```

(No `--skip-pilot` — Stage 6 catches the kind of TaskCard defects that Phase 7 had to manually patch for stopit + cognitionrun.)

Per-paradigm wall-time: ~10 min each = ~40 min total.

- [ ] **Step 3: If regen not required, skip to Task 21**

---

### Task 21: 5 sessions × 4 paradigms

**Files:**
- (Runs experiment-bot CLI directly; no code changes)

- [ ] **Step 1: Set output root**

```bash
mkdir -p output/sp12_remeasure
export EXPERIMENT_BOT_OUTPUT_DIR=output/sp12_remeasure
```

- [ ] **Step 2: Run 5 sessions for expfactory_stroop**

```bash
for i in 1 2 3 4 5; do
  uv run experiment-bot https://deploy.expfactory.org/preview/10/ \
    --label expfactory_stroop --headless --seed $((42 * i))
done
```

Expected: 5 session dirs under `output/sp12_remeasure/stroop_rdoc/`.

- [ ] **Step 3: Run 5 sessions for expfactory_stop_signal**

```bash
for i in 1 2 3 4 5; do
  uv run experiment-bot https://deploy.expfactory.org/preview/9/ \
    --label expfactory_stop_signal --headless --seed $((42 * i))
done
```

- [ ] **Step 4: Run 5 sessions for stopit_stop_signal**

```bash
for i in 1 2 3 4 5; do
  uv run experiment-bot https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html \
    --label stopit_stop_signal --headless --seed $((42 * i))
done
```

- [ ] **Step 5: Run 5 sessions for cognitionrun_stroop**

```bash
for i in 1 2 3 4 5; do
  uv run experiment-bot https://strooptest.cognition.run/ \
    --label cognitionrun_stroop --headless --seed $((42 * i))
done
```

- [ ] **Step 6: Confirm 20 sessions completed**

```bash
find output/sp12_remeasure -name 'bot_log.json' | wc -l
```

Expected: 20.

---

### Task 22: Analyze post-cleanup data + compare to baseline

**Files:**
- Create: `docs/sp12-remeasure-results.md`
- Use: `scripts/analyze_sessions.py` (renamed from phase7_analysis.py in Task 1)

- [ ] **Step 1: Run the analyzer**

```bash
uv run python scripts/analyze_sessions.py \
  --root output/sp12_remeasure \
  --paradigms expfactory_stroop expfactory_stop_signal stopit_stop_signal cognitionrun_stroop \
  --n 5 \
  --out docs/sp12-remeasure-results.md
```

Expected: writes the report.

- [ ] **Step 2: Compare to Phase 7 N=5 baseline**

Phase 7 N=5 baseline is preserved in git history at commit `ffb9f07`:

```bash
git show ffb9f07:docs/sp11-phase7-results.md > /tmp/sp11-phase7-baseline.md
```

Eyeball-compare the new vs the baseline for each paradigm. Specifically check per-paradigm:
- Mean RTs (within 1 SD of baseline mean?)
- Accuracy
- Stroop effect / SSRT
- Gratton CSE / lag1 autocorr

Pass criterion: post-cleanup per-paradigm metric means within the SD of the Phase 7 N=5 means.

- [ ] **Step 3: Document any drift**

Append a `## Comparison to pre-SP12 baseline` section to `docs/sp12-remeasure-results.md`. If everything's within tolerance, state so. If anything drifted, name the metric + magnitude + likely cause from the SP12 walks.

- [ ] **Step 4: Commit**

```bash
git add docs/sp12-remeasure-results.md
git commit -m "docs(sp12): post-cleanup re-measurement vs Phase 7 N=5 baseline

5 sessions × 4 SP11 paradigms re-run after SP12 walk-and-prune.
<one-sentence summary of comparison: clean drift / within-tolerance>.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Deliverable

### Task 23: Write `docs/sp12-deliverable.md`

**Files:**
- Create: `docs/sp12-deliverable.md`

- [ ] **Step 1: Compute before/after LOC**

```bash
git diff --stat ffb9f07..HEAD -- src/experiment_bot/ scripts/ docs/ | tail -1
git diff --shortstat ffb9f07..HEAD -- src/experiment_bot/ scripts/ docs/
```

Note the line additions, deletions, file count delta. Compute "before" via:

```bash
git ls-tree -r ffb9f07 -- src/experiment_bot/ | wc -l
find src/experiment_bot -name '*.py' -not -path '*__pycache__*' | xargs wc -l | tail -1
```

- [ ] **Step 2: Write the deliverable doc**

```markdown
# SP12 deliverable — codebase simplification + audit + N=5 re-measurement

**Date:** [YYYY-MM-DD when tag is cut]
**Tag:** sp12-complete (at this commit)
**Branch:** sp11/playwright-recommit

## What landed

Top-down walk-and-prune from CLI entry through every module exercised
in a production run. Each module's walk: read, list candidates, user
checkpoint, delete approved with one commit per logical removal, run
tests, append findings to docs/sp12-hardcoded-findings.md.

## Before / after

| Metric | Before SP12 | After SP12 | Delta |
|---|---|---|---|
| Source files | NN | NN | -NN |
| Source LOC | NN | NN | -NN |
| Scripts (excl. surviving 3) | 14 | 0 | -14 |
| SP11 phase docs | 14 | 0 (consolidated to sp11-complete.md) | -14 |
| CLI flags on `experiment-bot` | NN | NN | -NN |

## What survives

(brief summary of the final codebase shape; reference pipeline-flow.md
for the walkthrough)

## What was removed (highlights)

- One-shot SP-era scripts (phase7_*, probe_*, check_parameter_drift,
  keypress_audit, batch_run, test_run, __deprecated__)
- 14 SP11 phase deliverable docs consolidated into sp11-complete.md
- (other notable removals from the walks)

## Hardcoded paradigm findings

See `docs/sp12-hardcoded-findings.md` for the per-module list. Summary
of structural assumptions that would need attention for new platforms:

- (list)

## Runtime visibility

Phase 2 added:
- `docs/pipeline-flow.md` — 14-section walkthrough, ~10-min read
- `[sp12]` stdout narration — 6 lines per session
- `run_trace.json` — structured per-stage trace alongside bot_log.json

## Post-cleanup re-measurement

See `docs/sp12-remeasure-results.md`. 5 sessions × 4 SP11 paradigms
vs the Phase 7 N=5 baseline (commit ffb9f07).

(brief summary of pass/fail)

## Backlog rolled forward

- (anything surfaced during walks that wasn't actioned)
```

- [ ] **Step 3: Commit**

```bash
git add docs/sp12-deliverable.md
git commit -m "docs(sp12): deliverable summary

Codebase shrunk from NN to NN LOC across NN files. 14 one-shot scripts
deleted, 14 SP11 phase docs consolidated, runtime visibility added
(pipeline-flow.md + narrated stdout + run_trace.json). Post-cleanup
re-measurement clean vs Phase 7 N=5 baseline (per
docs/sp12-remeasure-results.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 24: Tag + reviewer-1-charter update + CLAUDE.md history append

**Files:**
- Modify: `docs/reviewer-1-charter.md`
- Modify: `CLAUDE.md`
- Git tag: `sp12-complete`

- [ ] **Step 1: Update `docs/reviewer-1-charter.md` "Last reviewed at"**

```bash
grep -n 'Last reviewed at' docs/reviewer-1-charter.md
```

Find the line and update its value to `sp12-complete`. Commit:

```bash
git add docs/reviewer-1-charter.md
git commit -m "docs(sp12): reviewer-1 charter — Last reviewed at = sp12-complete"
```

- [ ] **Step 2: Append SP12 entry to CLAUDE.md sub-project history**

In `CLAUDE.md`, after the SP11 entry in the "Sub-project history" section, append:

```markdown
- **SP12**: Codebase simplification + antagonistic audit + runtime
  visibility + post-cleanup re-measurement. Top-down walk-and-prune
  from CLI entry through every module exercised in a production run.
  Deleted: one-shot SP-era scripts (phase7_*, probe_*, etc., 14
  scripts total), 14 SP11 phase deliverable docs (consolidated to
  sp11-complete.md), unused CLI flags (--no-calibration,
  --skip-calibration-pass), sp11_supported guard machinery,
  (other major removals). Added: docs/pipeline-flow.md (14-section
  walkthrough), [sp12] stdout narration (6 lines/session),
  run_trace.json (structured per-stage trace), and
  docs/sp12-hardcoded-findings.md (paradigm-specific assumptions
  surfaced during the walk). Post-cleanup re-measurement on 4 SP11
  paradigms × 5 sessions clean vs Phase 7 N=5 baseline. Tag
  `sp12-complete`. ✓ Complete.
```

Commit:

```bash
git add CLAUDE.md
git commit -m "docs(sp12): append SP12 to sub-project history in CLAUDE.md"
```

- [ ] **Step 3: Final pytest**

```bash
uv run pytest --ignore=tests/test_phase4b_paradigm_smokes.py -q
```

Expected: green.

- [ ] **Step 4: Tag `sp12-complete`**

```bash
git tag sp12-complete
git push origin sp12-complete
git push origin sp11/playwright-recommit
```

- [ ] **Step 5: Announce completion**

(no commit; just state to user that SP12 is complete at tag `sp12-complete`)

---

## End of plan
