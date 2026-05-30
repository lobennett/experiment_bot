# Docs consolidation (Approach C) — design spec

**Status:** approved (Focused consolidation; README as canonical guide; Full Approach C for results/charter).
**Goal:** Consolidate `docs/` into a clean, onboarding-focused set that shows the pipeline start-to-finish, keeps a distinct reviewer-facing surface, and establishes a **single living home for results** so per-run docs stop re-accumulating and going stale.

## Target structure (end state)

```
README.md                          # canonical onboarding + chronological pipeline (absorbs how-it-works + pipeline-flow)
docs/
  scope-of-validity.md             # claims + limits (L1–L20) + held-out protocol; CITES validation-results for numbers
  validation-results.md            # NEW — the ONE living evidence doc (Current baselines table + thin run log)
  reviewer-1-charter.md            # adversarial-review governance; kept, pointers updated
  stage3-citation-history.md       # NEW — consolidates the 2 Stage-3 history docs
  results-data/                    # NEW — raw machine artifacts only (baseline JSON, per-batch verdict JSON)
    baseline_summary.json
    sp12-remeasure-results.json
    phase7-baselines/…             # landing-page captures (moved from docs/phase7-baselines/)
  superpowers/specs/               # 3 design specs (2 current Stage-3 + this one); plans deleted
scripts/check_doc_links.py         # NEW — fails on dead docs/*.md or taskcards/<hash>.json references
```

## Components

### 1. README.md — canonical onboarding + pipeline (absorb how-it-works + pipeline-flow)
Rewrite/expand the existing "How It Works" section into a **chronological** end-to-end walkthrough, updating dated vocabulary ("config generation" → Reasoner/TaskCard):
1. **Reasoner** (offline, Stages 1–6: structural → behavioral → citations → DOI-verify → sensitivity → pilot) → emits a TaskCard.
2. **TaskCard** — the versioned JSON contract (stimuli, navigation, response_distributions, temporal_effects, citations).
3. **Executor** — drives the live URL via Playwright, samples humanlike RTs, adaptive nav → platform data + bot_log.
4. **Oracle** — scores platform data against meta-analytic norms.
Plus the generic-mechanism / anti-circularity principles (G1–G5 in brief). Keep the current Quick Start / CLI / Batch / Output / Analyzing sections. Update "Further Reading" to the consolidated set (scope-of-validity, validation-results, reviewer-1-charter, stage3-citation-history). Remove the `how-it-works.md` link.
**Delete:** `docs/how-it-works.md`, `docs/pipeline-flow.md` (content absorbed).

### 2. docs/validation-results.md — the single living evidence sink (NEW)
Two sections, **never per-run files**:
- **Current baselines** — a table keyed by paradigm (4 dev + each held-out): latest N, authoritative platform-adapter verdict (per pillar), and the as-run command. Rows **overwritten in place** each new batch.
- **Run log** — reverse-chronological, ONE short entry per batch (date, background id, exact command, N, TaskCard hashes, `output/*` paths, one-line verdict, link to its raw JSON in `results-data/`). Superseded entries **deleted**, not stacked (keep ~last 3 for trend; git history holds the rest).

Migrate existing N=5 evidence into Current baselines (`docs/phase7-baselines/baseline_summary.json`, `docs/sp12-remeasure-results.json`) **and record this session's N=5/6 regenerated-card runs** as the newest run-log entries (the validation reports under `validation/` + the SSRT/L20 finding). Numbers live here; scope-of-validity and README cite, never restate.

### 3. docs/results-data/ — raw artifacts (NEW)
Move `docs/phase7-baselines/` (incl. `baseline_summary.json` + landing captures) and `docs/sp12-remeasure-results.json` here. Prose (validation-results.md) references these; no double narration.

### 4. reviewer-1-charter.md — keep, update pointers (do NOT merge)
It is the only adversarial-review governance contract (C1–C5 falsifiable claims, probes A–I, reviewer thresholds, pre-registration discipline, findings template, the §9 withhold-known-findings rule). Merging it into scope-of-validity would hand the reviewer the answer key and break the rediscovery property. Fix the **broken pointers** only:
- §4 reading list: "read SP-results docs in numerical order / latest = current self-assessment" → redirect to `docs/validation-results.md` (current self-assessment) + `scope-of-validity.md` + CLAUDE.md SP-history.
- §5 MVR step 4 / §6 step 6: `scripts/keypress_audit.py` (deleted) → `scripts/audit_alignment.py` (surviving analog).
- Drop "SP7 doc taxonomy" (Probe C, §6) and "SP3 → SP_latest results docs" (Probe H) pointers.
- §10 "Last reviewed at": `sp12-complete` → `sp16-complete`.
The charter holds **no measured values** (preserves the withhold property).

### 5. heldout-nback-test.md — fold corrected note into scope §6, then delete
The standing doc is now **factually false**: it reports the n-back navigation gap as open (0 trials), but `taskcards/expfactory_n_back/085f4f0a.json` shows 68 trials captured (gap closed by the SP13–16 walker + adaptive nav; scope `L1` already codifies nav as solved), and the cited guard commit `cabd2f7` no longer exists. Preserve only the **anti-overfitting why-trail** (the zero-trial hard-fail guard + no-stimulus click-fallback rationale + the refused fullscreen/jsPsych shims) as a corrected one-paragraph note in `scope-of-validity.md` §6, reframed: "navigation gap surfaced 2026-05-06, closed by SP13–16 (see L1)." Then **delete** the file and fix its inbound references (scope §6 / the two later mentions, CLAUDE.md).

### 6. clean-run-2026-05-06.md — delete
Non-reproducible: all four cited TaskCard hashes (`7efedfd1`/`6829e941`/`9de8a663`/`39b7fb4e`) are missing from disk; the N=2 batch is superseded by phase7-baselines (N=5) and sp12-remeasure (N=5); SP5/6 already root-caused the trial-over-firing bug behind its unexplained PES/CSE findings. **Delete**; repoint CLAUDE.md's "provenance for the current shareable dataset" line → `docs/validation-results.md`. (git history retains the file.)

### 7. scope-of-validity.md — cite, don't restate
L6/L8 keep the **conclusion** ("pilots passed first attempt", "platform adapter authoritative") but the numbers move to `validation-results.md` (cited). Add the corrected n-back history note to §6 (from component 5).

### 8. CLAUDE.md — clean dangling pointers + add doc-workflow rules
- Remove the **16 dangling `docs/sp*.md` references** (SP-history block + Documents-to-read) left by the earlier prune; repoint the dataset-provenance line → `validation-results.md`.
- Add three **doc-workflow rules** under operational rules:
  - **R-1 One results file:** new measurement batches UPDATE `docs/validation-results.md` (overwrite the Current-baselines row, prepend one Run-log entry, drop superseded). Never create `docs/clean-run-DATE.md` / `docs/spNN-results.md` / `docs/<paradigm>-test.md`.
  - **R-2 Numbers in one place:** a measured value lives in `validation-results.md` (prose) or `results-data/` (raw JSON), not in scope-of-validity, CLAUDE.md, or README — those cite it.
  - **R-3 History note, not history file:** when a gap is later closed, edit ONE line in scope §6 + the relevant L-item ("surfaced DATE, closed by SPxx, see Lk") and delete the standalone trip-report.

### 9. docs/stage3-citation-history.md — consolidate the 2 Stage-3 history docs (NEW)
Merge `stage3-citation-integrity-2026-05.md` (fabrication finding) + `retrieval-stage3-smoke.md` (retrieval/canonical-recall smoke) into one compact narrative: fabrication finding → retrieval-grounded rebuild → canonical-recall (propose→verify) → current honest state (0 revisions, real citations). Delete the two originals; update inbound refs.

### 10. docs/superpowers/plans/ — delete the 2 executed plans
Remove `2026-05-29-canonical-recall-stage3.md` and `2026-05-29-retrieval-grounded-stage3.md` (executed step-lists). Keep the 2 design specs + this consolidation spec.

### 11. scripts/check_doc_links.py — dead-reference guard (NEW)
A small script that greps `docs/*.md` + `README.md` + `CLAUDE.md` for `docs/…md` and `taskcards/<hash>.json` references and exits non-zero on any that don't resolve on disk. Runnable in pre-commit/CI. Would have caught today's 16 dangling pointers + the charter's `keypress_audit.py` ref the moment they went stale. Include a focused test.

## Verification
- `scripts/check_doc_links.py` exits 0 (no dangling refs anywhere) after the consolidation.
- `uv run python -m pytest -q` stays green (790 passed) — only `check_doc_links` adds tests.
- Manual: README reads as a coherent start-to-finish onboarding doc; `validation-results.md` shows current N=5/6 baselines; charter pointers all resolve; no doc restates numbers that live in validation-results.

## Decomposition preview (for writing-plans)
1. `scripts/check_doc_links.py` + test (build the guard first; it validates the rest).
2. `docs/results-data/` move (phase7-baselines, sp12-remeasure JSON).
3. `docs/validation-results.md` (Current baselines + run log; migrate phase7/sp12 + this session's N=5/6).
4. README rewrite (absorb how-it-works + pipeline-flow; update Further Reading); delete the two.
5. `docs/stage3-citation-history.md` (merge the two Stage-3 docs); delete originals.
6. scope-of-validity §6 corrected n-back note + L6/L8 cite validation-results; delete heldout-nback + clean-run; fix inbound refs.
7. reviewer-1-charter pointer updates (§4/§5/§6/§10).
8. CLAUDE.md: remove 16 dangling sp*.md refs, repoint provenance, add R-1/R-2/R-3.
9. Delete the 2 executed superpowers plans.
10. Run `check_doc_links.py` + full suite; verify clean.
