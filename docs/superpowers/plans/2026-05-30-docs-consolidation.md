# Docs Consolidation (Approach C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate `docs/` into an onboarding-focused set (README as the canonical start-to-finish pipeline guide), establish a single living results doc so per-run docs stop re-accumulating, fix stale/false docs, and add a dead-reference guard.

**Architecture:** Build the dead-link guard FIRST (`scripts/check_doc_links.py`) so it validates every subsequent task. Then migrate evidence, create the living `validation-results.md`, rewrite README, merge/delete stale docs, fix the charter's broken pointers, clean CLAUDE.md, and run the guard + suite as the final gate. Almost entirely doc/content work + one small Python script.

**Tech Stack:** Python 3.12 (`uv run`), `pytest`, Markdown. No runtime/framework changes.

**Spec:** `docs/superpowers/specs/2026-05-30-docs-consolidation-design.md`

**Reviewer note (project convention):** dispatch the spec-compliance reviewer after each task; SKIP the code-quality reviewer (memory `feedback_skip_code_quality_reviewer`).

**Do NOT push** during execution — the user reviews and pushes (FF main) at the end.

---

## File Structure

- **Create** `scripts/check_doc_links.py` — dead intra-repo reference guard (+ `tests/test_check_doc_links.py`). (Task 1)
- **Create** `docs/results-data/` — raw machine artifacts (moved from `docs/phase7-baselines/`, `docs/sp12-remeasure-results.json`). (Task 2)
- **Create** `docs/validation-results.md` — single living evidence doc. (Task 3)
- **Modify** `README.md`; **delete** `docs/how-it-works.md`, `docs/pipeline-flow.md`. (Task 4)
- **Create** `docs/stage3-citation-history.md`; **delete** `docs/stage3-citation-integrity-2026-05.md`, `docs/retrieval-stage3-smoke.md`. (Task 5)
- **Modify** `docs/scope-of-validity.md`; **delete** `docs/heldout-nback-test.md`, `docs/clean-run-2026-05-06.md`. (Task 6)
- **Modify** `docs/reviewer-1-charter.md`. (Task 7)
- **Modify** `CLAUDE.md`. (Task 8)
- **Delete** `docs/superpowers/plans/2026-05-29-canonical-recall-stage3.md`, `docs/superpowers/plans/2026-05-29-retrieval-grounded-stage3.md`. (Task 9)
- **Verify** (Task 10).

---

## Task 1: `scripts/check_doc_links.py` — dead-reference guard

**Files:**
- Create: `scripts/check_doc_links.py`
- Test: `tests/test_check_doc_links.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_doc_links.py
from pathlib import Path
from scripts.check_doc_links import find_dangling


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "taskcards" / "x").mkdir(parents=True)
    (tmp_path / "taskcards" / "x" / "abc12345.json").write_text("{}")
    (tmp_path / "docs" / "real.md").write_text("ok")
    return tmp_path


def test_resolvable_refs_pass(tmp_path):
    repo = _repo(tmp_path)
    src = repo / "README.md"
    src.write_text("See `docs/real.md` and `taskcards/x/abc12345.json`.")
    assert find_dangling([src], repo) == []


def test_dangling_ref_is_caught(tmp_path):
    repo = _repo(tmp_path)
    src = repo / "CLAUDE.md"
    src.write_text("Tracked in `docs/sp6-results.md` (deleted).")
    bad = find_dangling([src], repo)
    assert ("CLAUDE.md", "docs/sp6-results.md") in [(s, r) for s, r in bad]


def test_illustrative_placeholders_are_skipped(tmp_path):
    repo = _repo(tmp_path)
    src = repo / "CLAUDE.md"
    # R-1 rule examples: uppercase placeholders / angle brackets — not real refs
    src.write_text("Never create docs/clean-run-DATE.md or docs/spNN-results.md or docs/<paradigm>-test.md")
    assert find_dangling([src], repo) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_check_doc_links.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.check_doc_links'`.

- [ ] **Step 3: Implement `scripts/check_doc_links.py`**

```python
#!/usr/bin/env python3
"""Fail on dead intra-repo references in the high-traffic docs.

Scans README.md, CLAUDE.md, and docs/*.md (top level) for references to repo
files — docs/*.md, taskcards/<hash>.json, scripts/*.py — and reports any that
do not resolve on disk. Illustrative/example paths (uppercase placeholders like
DATE/NN/YYYY, or <…>/* ) are skipped. Exit 1 if any dangling reference is found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REF_RE = re.compile(r"(docs/[\w./-]+\.md|taskcards/[\w./-]+\.json|scripts/[\w./-]+\.py)")
# Illustrative refs use uppercase placeholders (DATE, NN, YYYY) or <…>/*; real
# doc/taskcard/script paths are lowercase + digits.
PLACEHOLDER_RE = re.compile(r"[A-Z<>*]")


def find_dangling(sources: list[Path], repo: Path) -> list[tuple[str, str]]:
    bad: list[tuple[str, str]] = []
    for src in sources:
        if not src.exists():
            continue
        for m in REF_RE.finditer(src.read_text()):
            ref = m.group(1)
            if PLACEHOLDER_RE.search(ref):
                continue  # illustrative example, not a real reference
            if not (repo / ref).exists():
                bad.append((str(src.relative_to(repo)), ref))
    return bad


def _default_sources(repo: Path) -> list[Path]:
    return [repo / "README.md", repo / "CLAUDE.md", *sorted((repo / "docs").glob("*.md"))]


def main() -> int:
    bad = find_dangling(_default_sources(REPO), REPO)
    if bad:
        print("Dangling intra-repo references found:")
        for src, ref in bad:
            print(f"  {src}: {ref}")
        return 1
    print("check_doc_links: OK — all references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_check_doc_links.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the guard against the real repo (expect it to FAIL now — that's the work to do)**

Run: `uv run python scripts/check_doc_links.py; echo "exit=$?"`
Expected: prints the current dangling refs (CLAUDE.md's ~16 `docs/sp*.md`, charter's `scripts/keypress_audit.py`) and `exit=1`. This is the pre-consolidation baseline; Task 10 must make it `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_doc_links.py tests/test_check_doc_links.py
git commit -m "feat(scripts): check_doc_links.py — dead intra-repo reference guard"
```

---

## Task 2: Move raw evidence artifacts to `docs/results-data/`

**Files:**
- Move: `docs/phase7-baselines/` → `docs/results-data/phase7-baselines/`
- Move: `docs/sp12-remeasure-results.json` → `docs/results-data/sp12-remeasure-results.json`

- [ ] **Step 1: Move with git**

```bash
mkdir -p docs/results-data
git mv docs/phase7-baselines docs/results-data/phase7-baselines
git mv docs/sp12-remeasure-results.json docs/results-data/sp12-remeasure-results.json
```

- [ ] **Step 2: Verify the move**

Run: `ls docs/results-data/ docs/results-data/phase7-baselines/`
Expected: `sp12-remeasure-results.json`, `phase7-baselines/`; and `baseline_summary.json` + per-paradigm subdirs under phase7-baselines.

- [ ] **Step 3: Commit**

```bash
git add -A docs/results-data docs/phase7-baselines docs/sp12-remeasure-results.json
git commit -m "chore(docs): move raw baseline artifacts to docs/results-data/"
```

---

## Task 3: `docs/validation-results.md` — the single living evidence doc

**Files:**
- Create: `docs/validation-results.md`
- Read for migration: `docs/results-data/phase7-baselines/baseline_summary.json`, `docs/results-data/sp12-remeasure-results.json`, `validation/latest_batch/*.json` (this session's N=5/6), the L20 SSRT finding in `scope-of-validity.md`.

- [ ] **Step 1: Gather the numbers to migrate**

Run (inspect the migration sources):
```bash
uv run python -c "import json; print(json.dumps(json.load(open('docs/results-data/phase7-baselines/baseline_summary.json')), indent=1))" | head -60
ls validation/latest_batch/
```
Expected: the N=5 phase7 baselines + this session's 4 latest-batch validation reports (stroop_rdoc, stop_signal_rdoc, stroop_online_(cognition.run), stop_signal_kywch_jspsych).

- [ ] **Step 2: Write `docs/validation-results.md`**

Two sections, exactly as the spec's component 2:
- **`## Current baselines`** — a Markdown table, one row per paradigm (4 dev + held-out n-back, + held-out stop_signal_with_integrated_memory if present), columns: `paradigm | platform | latest N | as-run command | rt_distribution | sequential/PES | signature (SSRT) | overall`. Fill rt/PES/SSRT/overall from the latest-batch validation reports (N=5/6); for paradigms only covered by phase7/sp12, use those. Rows are OVERWRITTEN in place on future batches.
- **`## Run log`** — reverse-chronological, ONE entry per batch. Newest entry = this session's run: date 2026-05-30, the parallel 5×4 run (background id from `/tmp/run5_all.sh`), the four URLs/commands, N=5 (stopit via `experiment-transformed-first.html`), the regenerated TaskCard hashes (`45751cfe`/`e29f22de`/`b16c7891`/`6fc729c3`), `output/<task_name>/` paths, one-line verdict (2/4 pass; Stroop tail-width + kywch SSRT artifacts — see scope L20), and a link to `docs/results-data/`. Add the phase7 (N=5, 2026-05-19) + sp12-remeasure (N=5, 2026-05-22) as the next two entries. Keep ~3 entries; note older detail lives in git history.

Begin the file with a one-line header stating it is the single living results doc and that batches OVERWRITE rows / prepend one run-log entry (cite CLAUDE.md R-1).

- [ ] **Step 3: Verify references resolve**

Run: `uv run python scripts/check_doc_links.py 2>&1 | grep -E "validation-results|results-data" || echo "no new dangling refs from validation-results"`
Expected: no dangling refs originating from `validation-results.md` (TaskCard hashes cited must be ones that exist on disk; `output/*` paths are not checked by the guard).

- [ ] **Step 4: Commit**

```bash
git add docs/validation-results.md
git commit -m "docs: add validation-results.md — single living results doc (Approach C)"
```

---

## Task 4: README.md — canonical onboarding + chronological pipeline

**Files:**
- Modify: `README.md`
- Delete: `docs/how-it-works.md`, `docs/pipeline-flow.md`

- [ ] **Step 1: Rewrite the "How It Works" section into a chronological pipeline**

Replace README's current brief "How It Works" with an end-to-end walkthrough absorbing `how-it-works.md` (concepts) + `pipeline-flow.md` (module detail), in chronological order and **current vocabulary** (no "config generation"; use Reasoner/TaskCard):
1. **Reasoner** (offline; Stages 1–6: structural → behavioral → citations → DOI-verify → sensitivity → pilot) → emits a TaskCard. Name the CLI: `experiment-bot-reason`.
2. **TaskCard** — versioned JSON contract (stimuli, navigation, response_distributions, temporal_effects, citations). Loaded newest-by-mtime from `taskcards/<label>/`.
3. **Executor** — `experiment-bot`; drives the live URL via Playwright (PilotSession), samples humanlike RTs, adaptive nav → writes `output/<task_name>/<ts>/` (experiment_data.*, bot_log.json, run_metadata.json).
4. **Oracle** — `experiment-bot-validate`; reads the platform export via per-paradigm adapters, scores vs `norms/<class>.json`.
Add a short "Design principles" paragraph (G1 generalizability, G2 generic mechanisms, G4 anti-circularity).

- [ ] **Step 2: Fix dated vocabulary + Further Reading**

- Replace the line "For a detailed technical description, see `docs/how-it-works.md`." with a pointer to the new in-README pipeline section.
- Update the intro paragraph "inferred by Claude at config generation time" → "inferred by the Reasoner (from the cognitive-psychology literature) into a TaskCard".
- Update "Further Reading" to: `docs/scope-of-validity.md` (claims & limits), `docs/validation-results.md` (current results), `docs/reviewer-1-charter.md` (adversarial review), `docs/stage3-citation-history.md` (citation provenance). Remove the how-it-works / pipeline-flow links.

- [ ] **Step 3: Delete the absorbed docs**

```bash
git rm docs/how-it-works.md docs/pipeline-flow.md
```

- [ ] **Step 4: Verify**

Run: `uv run python scripts/check_doc_links.py 2>&1 | grep -E "how-it-works|pipeline-flow" || echo "no refs to deleted how-to docs"`
Expected: no remaining references to the deleted docs (Step 2 removed README's; Task 8 handles CLAUDE.md if any).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/how-it-works.md docs/pipeline-flow.md
git commit -m "docs(readme): absorb how-it-works + pipeline-flow into chronological pipeline guide"
```

---

## Task 5: `docs/stage3-citation-history.md` — consolidate Stage-3 history

**Files:**
- Create: `docs/stage3-citation-history.md`
- Delete: `docs/stage3-citation-integrity-2026-05.md`, `docs/retrieval-stage3-smoke.md`

- [ ] **Step 1: Write the consolidated history**

One compact narrative (~40–70 lines) covering, in order: (a) the **fabrication finding** (Stage 3 chose values then retro-cited; prompt demanded verbatim quotes → invented DOIs + real-DOI/fake-quote; from `stage3-citation-integrity-2026-05.md`); (b) the **retrieval-grounded rebuild** (Python-retrieved pool, cite-by-pool_idx, abstain); (c) **canonical-recall** (propose→verify + citation-ranked search; from `retrieval-stage3-smoke.md`); (d) the **current honest state** (real title-verified canonical citations, 0 abstract-supported revisions → values remain model_prior). Preserve the key DOIs/examples from the smoke as illustration.

- [ ] **Step 2: Delete the two originals**

```bash
git rm docs/stage3-citation-integrity-2026-05.md docs/retrieval-stage3-smoke.md
```

- [ ] **Step 3: Verify no dangling refs to the originals**

Run: `grep -rn "stage3-citation-integrity-2026-05\|retrieval-stage3-smoke" README.md CLAUDE.md docs/*.md || echo "no inbound refs remain"`
Expected: none (if any found, fix in the referencing file — note CLAUDE.md is handled in Task 8).

- [ ] **Step 4: Commit**

```bash
git add docs/stage3-citation-history.md docs/stage3-citation-integrity-2026-05.md docs/retrieval-stage3-smoke.md
git commit -m "docs: consolidate Stage-3 citation history into one doc"
```

---

## Task 6: scope-of-validity §6 note + cite validation-results; delete heldout-nback + clean-run

**Files:**
- Modify: `docs/scope-of-validity.md`
- Delete: `docs/heldout-nback-test.md`, `docs/clean-run-2026-05-06.md`

- [ ] **Step 1: Add the corrected n-back note to §6 (Generalization protocol)**

Add one paragraph preserving the anti-overfitting why-trail from `heldout-nback-test.md`, reframed as resolved: the n-back navigation gap (0 trials, fullscreen-prompt blocker) **surfaced 2026-05-06** and was **closed by the SP13–16 Stage-6 walker + adaptive nav (see L1)** — `taskcards/expfactory_n_back/085f4f0a.json` now captures 68 trials; the zero-trial hard-fail guard + no-stimulus click-fallback were the deliberately *generic* responses, and paradigm-specific fullscreen/jsPsych shims were refused.

- [ ] **Step 2: Make L6/L8 cite validation-results for numbers**

In `scope-of-validity.md`, where L6/L8 (pilot integration / platform-adapter authority) state specific counts, keep the **conclusion** and replace embedded numbers with "see `docs/validation-results.md` for current baselines". Repoint any reference to `clean-run-2026-05-06.md` → `docs/validation-results.md`.

- [ ] **Step 3: Delete the two docs**

```bash
git rm docs/heldout-nback-test.md docs/clean-run-2026-05-06.md
```

- [ ] **Step 4: Verify inbound refs fixed**

Run: `grep -rn "heldout-nback-test\|clean-run-2026-05-06" README.md docs/*.md || echo "no inbound refs in README/docs"`
Expected: none in README/docs (CLAUDE.md handled in Task 8).

- [ ] **Step 5: Commit**

```bash
git add docs/scope-of-validity.md docs/heldout-nback-test.md docs/clean-run-2026-05-06.md
git commit -m "docs(scope): fold corrected n-back note into §6; cite validation-results; drop heldout-nback + clean-run"
```

---

## Task 7: reviewer-1-charter.md — fix broken pointers

**Files:**
- Modify: `docs/reviewer-1-charter.md`

- [ ] **Step 1: Repoint the reading list / orientation method (§3–§4)**

Replace the instruction to "read the SP-results docs in `docs/` in numerical order" / "the latest SP-results doc is the framework's current self-assessment" with: read `docs/validation-results.md` (current self-assessment), `docs/scope-of-validity.md` (claims & limits L1–L20), and CLAUDE.md's Sub-project history. Remove "SP7 doc taxonomy" (Probe C, §6) and "SP3 → SP_latest results docs" (Probe H) references.

- [ ] **Step 2: Replace the removed script reference (§5 MVR step 4, §6 step 6)**

Replace `scripts/keypress_audit.py` (deleted in SP12) with `scripts/audit_alignment.py` (the surviving per-trial alignment audit).

- [ ] **Step 3: Bump the maintenance state (§10)**

Change "Last reviewed at: `sp12-complete`" → "`sp16-complete`" (and note the docs consolidation in the maintenance log line if one exists). Do NOT add measured values — the charter stays answer-key-free.

- [ ] **Step 4: Verify charter refs resolve**

Run: `uv run python scripts/check_doc_links.py 2>&1 | grep -i "reviewer-1-charter" || echo "charter refs OK"`
Expected: no dangling refs from the charter (keypress_audit replaced; reading-list now points to existing files).

- [ ] **Step 5: Commit**

```bash
git add docs/reviewer-1-charter.md
git commit -m "docs(charter): fix broken pointers (reading list, audit script, sp16-complete)"
```

---

## Task 8: CLAUDE.md — remove dangling refs, repoint, add doc-workflow rules

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: List the dangling sp*.md references to remove**

Run: `grep -noE "docs/sp[0-9a-z][-a-z0-9]*\.md" CLAUDE.md | sort -u`
Expected: ~16 `docs/sp*.md` paths (all deleted earlier).

- [ ] **Step 2: Clean the references**

In CLAUDE.md's "Sub-project history" + "Documents to read before starting": remove inline `docs/sp*.md` links (keep the narrative SP summaries themselves — only strip the dead doc pointers). Repoint the "provenance for the current shareable dataset" line → `docs/validation-results.md`. Remove/repoint any `how-it-works.md`, `pipeline-flow.md`, `heldout-nback-test.md`, `clean-run-2026-05-06.md`, `stage3-citation-integrity-2026-05.md`, `retrieval-stage3-smoke.md` references to their consolidated homes (README pipeline section / validation-results / scope §6 / stage3-citation-history).

- [ ] **Step 3: Add the three doc-workflow rules**

Under the operational/style rules, add:
- **R-1 One results file:** new measurement batches UPDATE `docs/validation-results.md` (overwrite the Current-baselines row, prepend one Run-log entry, drop superseded). Never create `docs/clean-run-DATE.md` / `docs/spNN-results.md` / `docs/<paradigm>-test.md`.
- **R-2 Numbers in one place:** a measured value lives in `docs/validation-results.md` (prose) or `docs/results-data/` (raw JSON), not in scope-of-validity, CLAUDE.md, or README — those cite it.
- **R-3 History note, not history file:** when a gap is later closed, edit ONE line in scope §6 + the relevant L-item ("surfaced DATE, closed by SPxx, see Lk") and delete the standalone trip-report.
(Write the R-1 examples with uppercase placeholders so `check_doc_links.py` skips them.)

- [ ] **Step 4: Verify**

Run: `uv run python scripts/check_doc_links.py; echo "exit=$?"`
Expected: `exit=0` — all references in README + CLAUDE.md + docs/*.md now resolve.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): drop dangling sp*.md refs; repoint to validation-results; add R-1/R-2/R-3 doc-workflow rules"
```

---

## Task 9: Delete the two executed superpowers plans

**Files:**
- Delete: `docs/superpowers/plans/2026-05-29-canonical-recall-stage3.md`, `docs/superpowers/plans/2026-05-29-retrieval-grounded-stage3.md`

- [ ] **Step 1: Delete**

```bash
git rm docs/superpowers/plans/2026-05-29-canonical-recall-stage3.md docs/superpowers/plans/2026-05-29-retrieval-grounded-stage3.md
```

- [ ] **Step 2: Commit**

```bash
git commit -m "docs: remove the two executed Stage-3 implementation plans (specs kept)"
```

---

## Task 10: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Dead-reference guard passes**

Run: `uv run python scripts/check_doc_links.py; echo "exit=$?"`
Expected: `check_doc_links: OK` and `exit=0`.

- [ ] **Step 2: Full test suite green**

Run: `uv run python -m pytest -q 2>&1 | tail -3`
Expected: `790 passed` + the 3 new `test_check_doc_links` tests (= 793), `7 skipped`, 0 failures.

- [ ] **Step 3: Manual sanity sweep**

Run: `git ls-files 'docs/*.md' README.md CLAUDE.md; ls docs/results-data docs/superpowers/specs docs/superpowers/plans`
Expected end state: `docs/` top-level = `scope-of-validity.md`, `validation-results.md`, `reviewer-1-charter.md`, `stage3-citation-history.md`; `docs/results-data/` populated; `docs/superpowers/specs/` = 3 specs; `docs/superpowers/plans/` empty (or absent). README reads start-to-finish; no doc restates numbers that live in validation-results.

- [ ] **Step 4: Report (no push)**

Summarize the resulting tree + confirm guard+suite green. Leave the push (FF main) for the user.

---

## Self-Review

**Spec coverage:** Spec components 1–11 → Tasks: 1 (component 11 guard), 2 (component 3 results-data), 3 (component 2 validation-results), 4 (component 1 README + deletes), 5 (component 9 stage3 history), 6 (components 5+6+7 scope note/cite + heldout/clean-run deletes), 7 (component 4 charter), 8 (component 8 CLAUDE.md), 9 (component 10 plans). ✓ All covered.

**Placeholder scan:** Task 1 ships full script + test code. Doc tasks specify exact structure, sources, deletions, and a concrete `check_doc_links.py`/grep verification each — the prose content is the execution deliverable, not a code blank. No "TBD"/"handle edge cases".

**Type/name consistency:** `find_dangling(sources, repo)` + `_default_sources(repo)` + `PLACEHOLDER_RE` defined in Task 1, used by the same names in its tests and Task 10. `docs/validation-results.md`, `docs/results-data/`, `docs/stage3-citation-history.md`, R-1/R-2/R-3 named consistently across tasks. Guard built in Task 1 and is the gate in Tasks 3/4/6/7/8/10.

**Order:** guard first (Task 1) → it legitimately reports `exit=1` until Task 8 finishes, then `exit=0` at Task 10. Intentional and noted.
