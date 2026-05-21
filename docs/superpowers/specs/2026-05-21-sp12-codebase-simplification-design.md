# SP12: Codebase simplification + antagonistic audit — design

**Author:** Logan Bennett
**Date:** 2026-05-21
**Status:** draft, pending plan
**Branch policy:** work continues on `sp11/playwright-recommit` until
phase-complete, then tag `sp12-complete`. (SP12 inherits the SP11
worktree; no new branch.)

## 1. Goal

Reduce the experiment_bot codebase to what is **absolutely necessary
for current production runs**, with explicit hardcoded-bits findings
and minimal runtime visibility, so a new reader (or Logan) can walk
the pipeline end-to-end quickly. Validated post-cleanup by 5 sessions
× 4 SP11 paradigms, compared against the current Phase 7 N=5
baseline (`docs/sp11-phase7-results.md`).

This is not a re-architecture. It is a **prune + narrate** pass.
Surviving code is the same code in shape; it's just less of it.

## 2. Scope

In scope:
- Top-down walk of every module exercised in a production run.
- Aggressive removal of dead code, circuitous branching, unused CLI
  flags, one-shot SP-era scripts, deprecated experimental paths,
  duplicated logic, over-abstracted helpers with single call sites.
- Consolidation of the 11 SP11 phase deliverable docs into one
  `sp11-complete.md`; archive of the rest.
- Static audit for hardcoded paradigm knowledge (jsPsych selectors,
  Stroop labels, magic numbers, paradigm-specific JS strings).
  Findings logged inline to `docs/sp12-hardcoded-findings.md` as
  the walk produces them.
- Minimal runtime-visibility additions: a one-page
  `docs/pipeline-flow.md`, narrated stdout (~6 lines/session), a
  small `run_trace.json` alongside `bot_log.json`.
- Post-cleanup re-measurement: 5 sessions × 4 SP11 paradigms,
  comparison report via the existing
  `scripts/phase7_analysis.py`.

Out of scope:
- Held-out paradigm re-tests (static audit only this SP).
- New abstractions or architectural redesigns of surviving code.
- Changes to `docs/scope-of-validity.md` claims, norms files, or
  pre-registered metrics.
- Cleanup of held-out paradigm TaskCards (`expfactory_flanker`,
  `expfactory_n_back`) — only the 4 SP11 paradigms are measured.

## 3. Approach

### Walk-and-prune in one pass

Starting from `experiment-bot <url> --label X`, trace every module
that executes during a production run, top-down. For each module:

1. Read top-to-bottom; produce a brief "what this does" summary.
2. List candidate removals + rationale.
3. Checkpoint to Logan with the candidate list (small message,
   not a doc).
4. If no objection, delete with one small commit per logical
   removal. Each commit message names the rationale.
5. Run `uv run pytest`; resolve breakage before continuing.
6. Append hardcoded-paradigm findings to
   `docs/sp12-hardcoded-findings.md`.

Big modules (>500 LOC — currently `executor.py` at 1295, `config.py`
at 838, `core/distributions.py` borderline at 360) get split into
sub-walks so checkpoints stay reviewable. Sub-walk boundaries are
named at module entry, before reading.

### Walk order

1. `scripts/` (low-risk one-shot deletes)
2. `docs/` consolidation (SP11 phase docs → one `sp11-complete.md`)
3. `cli.py`
4. `core/executor.py` (sub-walks: init, navigation, session-agent,
   calibration call site, trial loop, finalization)
5. `core/config.py`
6. `calibration/` (deliverer, estimator, runner, drop-from-scope)
7. `output/writer.py`
8. `core/distributions.py` (sampler)
9. `core/stimulus.py`, `core/phase_detection.py`
10. `navigation/navigator.py`, `navigation/stuck.py`
11. `agent/session_agent.py`, `agent/page_probe.py`, `agent/types.py`
12. `llm/` (protocol, cli_client, api_client, factory)
13. `taskcard/` (loader, types, sampling, hashing)
14. `reasoner/` (last; offline-only, doesn't run during sessions)
15. `effects/` (handlers, registry, validation_metrics)
16. `validation/` (oracle, platform_adapters, eisenberg)

### Why this order

The Reasoner is last because production runs don't traverse it
(it's offline, before sessions). Cleanup there may force TaskCard
regeneration. By the time we get to it, the runtime path is
clean, and we can decide TaskCard-regeneration policy with the
runtime audit done.

## 4. Phases

### Phase 1 — Walk-and-prune (the bulk of the work)

Per Section 3. Output: shrunken codebase + `sp12-hardcoded-findings.md`
+ per-module checkpoint messages (transient, not committed).

Test gate: `uv run pytest` is run AT LEAST at the end of each
module's walk; the implementer may run it more often (e.g., after
each removal commit) at discretion. A module's walk does not
"complete" until pytest is green.

### Phase 2 — Runtime visibility (minimal)

Three small additions:

1. **`docs/pipeline-flow.md`** — single-page walkthrough of the CLI
   → `bot_log.json` lifecycle with code references. Written during
   Phase 1 incrementally (one section per module walked), so the
   doc IS the walk's deliverable.
2. **Narrated stdout** — ~6 lines per session, one per major stage:
   `navigate / agent / calibration / trial loop / wait completion /
   save`. Consolidate + reduce verbosity of existing logging.
   `--verbose` retained for debug; default is the 6-line readout.
3. **`run_trace.json`** — small JSON beside `bot_log.json` recording
   stage timings + key per-stage decisions (e.g., calibration model,
   N CDP fires, agent directive summary). Per-trial details remain
   in `bot_log.json` — `run_trace.json` is one entry per stage, not
   per trial.

Test gate: at least one synthetic test asserts the stdout has all
6 stages on a clean run, and `run_trace.json` is written.

### Phase 3 — Re-measurement

5 sessions × 4 SP11 paradigms = 20 sessions. Regenerate TaskCards
ONLY if Phase 1 touched the Reasoner outputs (Stages 1–5 prompts,
schema, or config-emission shape). Run the surviving
`scripts/phase7_analysis.py` (possibly renamed to
`scripts/analyze_sessions.py` during Phase 1) and compare against
`docs/sp11-phase7-results.md`.

Pass criterion: post-cleanup per-paradigm metrics fall within the
SD of the current Phase 7 N=5 means. Honest framing per
[[feedback_honest_generalization_findings]] memory — surface drifts
explicitly, do not soften.

Sequential, not parallel (carries the SP11 Phase 7 spec discipline).

### Phase 4 — Deliverable

- `docs/sp12-deliverable.md` — summary of removals (per-module),
  before/after LOC, link to re-measurement report, link to
  `sp12-hardcoded-findings.md`.
- Tag `sp12-complete`.
- Update `docs/reviewer-1-charter.md` "Last reviewed at" to
  `sp12-complete`.
- Append SP12 entry to CLAUDE.md's sub-project history.

## 5. What survives, what doesn't

Working hypothesis — Phase 1 walk will confirm.

### Likely deletes

**Scripts (one-shot SP-era helpers):**
- `scripts/phase7_sweep.py`
- `scripts/phase7_aggregate.py`
- `scripts/phase7_baseline_snapshots.py`
- `scripts/check_parameter_drift.py`
- `scripts/probe_cognitionrun_export.py`
- `scripts/probe_stopit_jspsych6.py`
- `scripts/keypress_audit.py` (superseded by `audit_alignment.py`)
- `scripts/batch_run.sh`, `scripts/test_run.sh`
- `scripts/__deprecated__/` (already archived)
- `figure1_bot_vs_human.png`, `figure2_sequential_effects.png`
  (regenerable from current data if needed)

**Docs (consolidate):**
- Per-phase SP11 deliverables (`sp11-phase{2,3,3-cognitionrun-probe,
  4a-spike,4b,5a,5a-stopit-probe,5b,5b-drift-report,6,6-audit-planning,
  7,7-results,8-writeup-template}.md`) collapse to `sp11-complete.md`
- Optionally archive originals to `docs/archive/sp11/` for git
  history continuity

**Code:**
- `--no-calibration` and `--skip-calibration-pass` CLI flags
  (Phase 7 pre/post-cal arms; experiment is done)
- `RuntimeConfig.calibration_run_pass` /
  `RuntimeConfig.calibration_apply_to_sampler` if same
- `task_specific.sp11_supported` machinery if the cognitionrun fix
  rendered it unused
- `validation/eisenberg.py` if not exercised in current runs
- Multiple TaskCard SHAs per paradigm folder (keep latest only)
- `.variance_study/` work dirs (research artifacts; archive or
  delete)
- Helper modules with a single call site (collapsed back into
  caller)

**Output dirs (gitignored already; local-only cleanup):**
- `output/phase7_smoke*/`, `output/cognitionrun_diag*/`,
  `output/phase7_n5/` (after Phase 3 re-measurement supersedes)

### Likely survives

**Scripts:**
- `scripts/audit_alignment.py`
- `scripts/phase7_analysis.py` (possibly renamed)
- `scripts/launch.sh`

**Docs:**
- `scope-of-validity.md`, `sp11-backlog.md`, `generalization-audit.md`,
  `effect-library-audit.md`, `reviewer-1-charter.md`
- New: `pipeline-flow.md`, `sp12-hardcoded-findings.md`,
  `sp12-deliverable.md`, `sp11-complete.md`

**Code:** all of `src/experiment_bot/` after walk-and-prune trims
internals. No whole-module deletes expected.

## 6. Re-measurement details

| Setting | Value |
|---|---|
| Paradigms | `expfactory_stroop`, `expfactory_stop_signal`, `stopit_stop_signal`, `cognitionrun_stroop` |
| Sessions per paradigm | 5 |
| Calibration arm | post-cal (default; the `--no-calibration` flag may be removed in Phase 1) |
| Output root | `output/sp12_remeasure/` |
| Analysis tool | `scripts/phase7_analysis.py` (or renamed) |
| Comparison baseline | `docs/sp11-phase7-results.md` per-paradigm aggregates |
| Pass criterion | Post-cleanup per-paradigm metric means within the SD of the current Phase 7 N=5 means |
| TaskCard regen | Only if Phase 1 touched Reasoner outputs; if regen happens, use Stage 6 pilot (no `--skip-pilot`) |

## 7. Risk + mitigation

| Risk | Mitigation |
|---|---|
| Delete something used in production | One small commit per removal; full pytest after each module; Phase 3 re-measurement is the smoke test |
| Reasoner cleanup forces TaskCard regen mid-flight | Reasoner is last in the walk order; if changes accumulate, regen happens in Phase 3 before re-measurement |
| Aggressive removal cuts something Logan wants kept | Each module's checkpoint is a veto opportunity; the kill list in Section 5 is the working hypothesis Logan has already seen and approved |
| Post-cleanup metrics drift outside the SD band | Surface explicitly per honest-generalization-findings memory; investigate before claiming SP12 complete |

## 8. Pre-registration / freeze

This spec is frozen at its first commit on the sp11/playwright-recommit
branch. No edits to Section 4 (phases), Section 6 (re-measurement
config), or Section 7 (pass criterion) after Phase 3 data exists.
Edits to Section 5 (kill list) DURING Phase 1 are expected as the
walk surfaces what was missed or what should be kept; those edits
must land in a commit before the affected module's removal commit.

## 9. Estimated work

- Phase 1 (walk-and-prune): half a day to a full day of focused work
- Phase 2 (visibility): 2–3 h
- Phase 3 (re-measurement): ~2 h sequential runtime + analysis
- Phase 4 (deliverable): 1 h

## 10. Open questions

None at design time. Anything that surfaces during Phase 1 walk gets
captured in the per-module checkpoint and resolved with Logan
before continuing.
