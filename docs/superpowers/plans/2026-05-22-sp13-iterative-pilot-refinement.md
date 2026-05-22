# SP13 — Iterative Pilot Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Per `feedback_skip_code_quality_reviewer` memory: run spec-compliance reviewer ONLY; skip the code-quality reviewer dispatch.

**Goal:** Convert Stage 6's one-shot refinement into a sequential walker that advances the bot by one observed DOM state per attempt.

**Architecture:** Reasoner-only change. Stage 6 (`src/experiment_bot/reasoner/stage6_pilot.py`) gains DOM-fingerprint tracking + prior-attempt history; its refinement prompt is rewritten from "fix all structural fields" to "propose the next smallest advance." Pilot pass criteria, TaskCard schema, executor, and resume semantics are unchanged.

**Tech Stack:** Python 3.12, pytest-asyncio, Playwright (already in deps), Claude LLM via `experiment_bot.llm.protocol.LLMClient` (mocked in tests via AsyncMock).

**Spec:** `docs/sp13-spec.md` (commit `ee12089`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/experiment_bot/core/pilot.py` | Modify | Add `dom_fingerprint` property to `PilotDiagnostics` |
| `src/experiment_bot/reasoner/stage6_pilot.py` | Modify | Rewrite `REFINEMENT_PROMPT`; extend `_refine_partial` signature; add fingerprint tracking + stuck-detection to `run_stage6` |
| `src/experiment_bot/reasoner/cli.py` | Modify | Bump `--pilot-max-retries` default 2 → 11 |
| `src/experiment_bot/reasoner/pipeline.py` | Modify | Bump `pilot_max_retries` default 1 → 11 |
| `tests/test_pilot.py` | Modify | Add 3 fingerprint tests |
| `tests/test_reasoner_stage6.py` | Modify | Update `fake_refine` signature in existing test; add 3 new tests (sequential prompt, prior_diffs, stuck-detection) |
| `docs/pipeline-flow.md` | Modify | Update Stage 6 row in the Reasoner table + add 1-paragraph callout |
| `docs/sp13-results.md` | Create | Held-out + regression run results |
| `CLAUDE.md` | Modify | Append SP13 entry to Sub-project history list |

---

## Task 1: PilotDiagnostics.dom_fingerprint

**Files:**
- Modify: `src/experiment_bot/core/pilot.py` (add `import hashlib`, add `dom_fingerprint` property after `match_rate`)
- Test: `tests/test_pilot.py` (append 3 new tests)

**Why:** The stuck-detection guard in Task 3 needs a stable hash of the latest DOM snapshot to recognize "the bot is on the same screen as last attempt." Empty snapshots return `""` (no progress signal — guard treats as "can't decide; let the budget continue").

- [ ] **Step 1: Write the 3 failing tests**

Append to `tests/test_pilot.py`:

```python
import hashlib
# (existing imports already cover PilotDiagnostics)


def _empty_diagnostic() -> PilotDiagnostics:
    return PilotDiagnostics(
        trials_completed=0, trials_with_stimulus_match=0,
        conditions_observed=[], conditions_missing=[],
        selector_results={}, phase_results={}, dom_snapshots=[],
        anomalies=[], trial_log=[],
    )


def test_dom_fingerprint_empty_when_no_snapshots():
    d = _empty_diagnostic()
    assert d.dom_fingerprint == ""


def test_dom_fingerprint_stable_for_same_html():
    d = _empty_diagnostic()
    d.dom_snapshots = [{"trigger": "after_navigation", "html": "<div>x</div>"}]
    expected = hashlib.sha256(b"<div>x</div>").hexdigest()[:16]
    assert d.dom_fingerprint == expected
    assert d.dom_fingerprint == d.dom_fingerprint  # idempotent


def test_dom_fingerprint_reflects_latest_snapshot_only():
    d = _empty_diagnostic()
    d.dom_snapshots = [
        {"trigger": "after_navigation", "html": "<div>welcome</div>"},
        {"trigger": "no_match_50_polls", "html": "<div>welcome</div>"},
    ]
    stuck_fp = d.dom_fingerprint
    d.dom_snapshots.append(
        {"trigger": "no_match_100_polls", "html": "<div>instructions</div>"}
    )
    assert d.dom_fingerprint != stuck_fp
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pilot.py::test_dom_fingerprint_empty_when_no_snapshots tests/test_pilot.py::test_dom_fingerprint_stable_for_same_html tests/test_pilot.py::test_dom_fingerprint_reflects_latest_snapshot_only -v`
Expected: 3 FAILED with `AttributeError: 'PilotDiagnostics' object has no attribute 'dom_fingerprint'`.

- [ ] **Step 3: Implement the property**

In `src/experiment_bot/core/pilot.py`:

Add `import hashlib` to the imports at the top (alphabetically between `asyncio` and `logging`).

After the `match_rate` property (around line 58), add:

```python
    @property
    def dom_fingerprint(self) -> str:
        """Stable hash of the latest DOM snapshot's HTML. Empty string if
        no snapshots captured. Used by Stage 6's stuck-detection guard
        to recognize when refinements aren't moving the bot off a screen.
        """
        if not self.dom_snapshots:
            return ""
        latest = self.dom_snapshots[-1].get("html", "")
        if not latest:
            return ""
        return hashlib.sha256(latest.encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pilot.py -v`
Expected: All tests pass (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/pilot.py tests/test_pilot.py
git commit -m "$(cat <<'EOF'
feat(sp13): PilotDiagnostics.dom_fingerprint for stuck-state detection

Stable 16-char SHA-256 hash of the latest dom_snapshots entry's HTML.
Empty string when no snapshots present. Used by Stage 6's sequential
refinement loop (next task) to recognize when the bot is stuck on the
same DOM state across attempts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Sequential refinement — new prompt + `_refine_partial` signature

**Files:**
- Modify: `src/experiment_bot/reasoner/stage6_pilot.py` (rewrite `REFINEMENT_PROMPT`; add `prior_diffs` keyword-only parameter to `_refine_partial`)
- Test: `tests/test_reasoner_stage6.py` (update existing `fake_refine` to accept `prior_diffs=`; add 2 new tests)

**Why:** The current prompt asks the LLM to fix everything in one pass — it conflates "stuck on fullscreen" with "selectors don't match practice DOM" and tries to solve both before observing the practice DOM. Sequential framing tells the LLM to advance one screen at a time and explicitly shows prior attempts so it doesn't undo earlier progress.

- [ ] **Step 1: Write the 2 new failing tests**

Append to `tests/test_reasoner_stage6.py`:

```python
@pytest.mark.asyncio
async def test_refinement_prompt_uses_sequential_framing(tmp_path):
    """REFINEMENT_PROMPT must instruct the LLM to propose the SMALLEST next
    advance and reference 'Prior Refinement Attempts' for history."""
    from experiment_bot.reasoner.stage6_pilot import REFINEMENT_PROMPT
    assert "smallest" in REFINEMENT_PROMPT.lower(), \
        "prompt must instruct LLM to propose smallest advance"
    assert "Prior Refinement Attempts" in REFINEMENT_PROMPT, \
        "prompt must have a section for prior attempts"
    # Anti-regression: the old "fix all structural fields" framing should be gone.
    assert "Fix accordingly" not in REFINEMENT_PROMPT, \
        "old whole-fix framing should be removed"


@pytest.mark.asyncio
async def test_refine_partial_includes_prior_diffs_in_prompt(tmp_path):
    """When prior_diffs is non-empty, the refinement prompt rendered to the
    LLM must contain the prior diff text so the LLM can see what was tried."""
    from experiment_bot.reasoner.stage6_pilot import _refine_partial
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()
    prior_diff = "--- before_attempt_1\n+++ after_attempt_1\n+ added fullscreen click\n"
    await _refine_partial(
        fake_client, partial, _failing_diagnostic(), _bundle(),
        prior_diffs=[prior_diff],
    )
    # Inspect the prompt that was sent to the LLM
    sent_user = fake_client.complete.await_args.kwargs.get("user") \
                or fake_client.complete.await_args.args[1]
    assert "added fullscreen click" in sent_user, \
        "prior diff text must appear in the refinement prompt"
    assert "Prior Refinement Attempts" in sent_user
```

Also update `test_stage6_persists_refinements_via_save_partial_callback` — its `fake_refine` async function needs to accept the new keyword:

Find this block:
```python
        async def fake_refine(client, p, diag, bundle):
            import copy
            new_p = copy.deepcopy(p)
            new_p[f"_refinement_{len(saved_partials) + 1}"] = "applied"
            return new_p
```

Replace with:
```python
        async def fake_refine(client, p, diag, bundle, *, prior_diffs):
            import copy
            new_p = copy.deepcopy(p)
            new_p[f"_refinement_{len(saved_partials) + 1}"] = "applied"
            return new_p
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `uv run pytest tests/test_reasoner_stage6.py::test_refinement_prompt_uses_sequential_framing tests/test_reasoner_stage6.py::test_refine_partial_includes_prior_diffs_in_prompt -v`
Expected: Both FAILED — prompt doesn't contain "smallest" / "Prior Refinement Attempts", and `_refine_partial` doesn't accept `prior_diffs`.

- [ ] **Step 3: Replace `REFINEMENT_PROMPT` with sequential framing**

In `src/experiment_bot/reasoner/stage6_pilot.py`, REPLACE the entire `REFINEMENT_PROMPT = """..."""` block (currently lines 38-84) with:

```python
REFINEMENT_PROMPT = """\
You are refining an experiment-bot TaskCard one step at a time. The bot ran the
TaskCard against the live experiment URL via Playwright and got stuck. Your job
is to propose the SMALLEST possible advance that moves the bot ONE DOM state
forward — not to fix everything at once.

## Your Current Structural Fields
{partial_json}

## Pilot Diagnostic Report (latest run)
{diagnostic_report}

## Original Experiment Source (excerpt)
{source_summary}

## Prior Refinement Attempts (chronological)
{prior_diffs_section}

## Instructions

Read the latest DOM Snapshot in the diagnostic report — that is the screen the
bot is looking at right now. Identify what's blocking THIS specific screen.

Propose ONE change. Choose the right kind based on what the diagnostic shows:

1. **Bot stuck on an interstitial screen** (fullscreen prompt, instructions with
   a Next/Continue button, consent form, attention check, etc.): add ONE entry
   to `navigation.phases` that clicks the visible button (use the selector
   shown in the DOM snapshot) or presses the right key. Do NOT add multiple
   navigation phases speculatively — the pilot will rerun and reveal the next
   screen.

2. **Bot reached trials but selector_results show 0 matches** (test phase fired
   but no stimulus detected): examine the latest DOM snapshot for the actual
   trial-rendering structure. Update ONE stimulus's `detection.selector` to
   match what's rendered. Do NOT change conditions, response keys, or other
   fields.

3. **Phase_detection expression never fires but should** (e.g. instructions
   phase shows "never fired" yet the DOM shows an instructions screen): update
   that ONE phase_detection JS expression to match what's in the DOM.

If "Prior Refinement Attempts" contains diffs from earlier passes, do NOT undo
them. Build on prior progress: the bot is now in a DIFFERENT state than when
the first refinement ran. If you see yourself trying the same change twice,
something else is blocking; switch to a different observation.

Fix ONLY structural fields: `stimuli`, `navigation`, `runtime.advance_behavior`,
`runtime.phase_detection`, `runtime.data_capture`, `task_specific`. Do NOT modify
`response_distributions`, `temporal_effects`, `between_subject_jitter`, or
`performance.accuracy/omission_rate` — those are set by other Reasoner stages
and the pilot's evidence does not bear on them.

Return ONLY a JSON object containing the field(s) you changed. Unchanged fields
should be omitted; the pipeline will splice your output into the existing
partial. Return JSON only, no preamble.
"""
```

- [ ] **Step 4: Update `_refine_partial` signature and prompt formatting**

In `src/experiment_bot/reasoner/stage6_pilot.py`, find `_refine_partial` (currently lines 143-195). Change the signature and the prompt-rendering to:

```python
async def _refine_partial(
    client: LLMClient,
    partial: dict,
    diagnostics: PilotDiagnostics,
    bundle: SourceBundle,
    *,
    prior_diffs: list[str],
) -> dict:
    """Ask Claude to propose the next smallest advance for the stuck pilot.

    `prior_diffs` is the chronological list of unified-diff strings from
    previous refinement attempts in this run. The LLM uses them to avoid
    undoing earlier progress.

    Returns a NEW partial with refined structural fields spliced in;
    behavioral fields (response_distributions, temporal_effects, etc.)
    are preserved unchanged.
    """
    # Build a minimal source summary (same shape Stage 1 sees)
    source_parts = [f"## Page HTML\n{bundle.description_text[:5000]}"]
    for fname, content in bundle.source_files.items():
        source_parts.append(f"## File: {fname}\n{content[:30000]}")
    source_summary = "\n\n".join(source_parts)

    structural_only = {
        k: v for k, v in partial.items()
        if k in {
            "task", "stimuli", "navigation", "runtime", "task_specific",
            "performance", "pilot_validation_config",
        }
    }
    if prior_diffs:
        prior_diffs_section = "\n\n".join(
            f"### Attempt {i + 1}\n```diff\n{d}\n```"
            for i, d in enumerate(prior_diffs)
        )
    else:
        prior_diffs_section = "(none yet — this is the first refinement)"

    user = REFINEMENT_PROMPT.format(
        partial_json=json.dumps(structural_only, indent=2),
        diagnostic_report=diagnostics.to_report(),
        source_summary=source_summary,
        prior_diffs_section=prior_diffs_section,
    )
    refined = await parse_with_retry(
        client, system="", user=user, stage_name="stage6_pilot_refinement",
    )

    # Splice: deep-merge dict-shaped fields so a partial runtime fix from
    # the LLM (e.g. only data_capture.method changed) doesn't clobber the
    # other sub-fields (advance_behavior, phase_detection, ...). Lists are
    # replaced wholesale; the LLM is expected to return complete lists.
    out = copy.deepcopy(partial)
    for key in (
        "stimuli", "navigation", "runtime", "task_specific",
        "performance", "pilot_validation_config",
    ):
        if key not in refined:
            continue
        if isinstance(refined[key], dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], refined[key])
        else:
            out[key] = refined[key]
    out = normalize_partial(out)
    return out
```

NOTE: the docstring comment about "Don't validate the refined partial..." in the original is preserved as behavior (we don't validate) but the comment can be dropped since the function is now shorter and the rationale is in the spec.

- [ ] **Step 5: Update the existing call site in `run_stage6` (temporary placeholder — Task 3 finalizes this)**

Find the line in `run_stage6`:
```python
        partial = await _refine_partial(client, partial, diagnostics, bundle)
```

Replace with:
```python
        partial = await _refine_partial(
            client, partial, diagnostics, bundle, prior_diffs=[],
        )
```

(Task 3 replaces `prior_diffs=[]` with the real accumulating list.)

- [ ] **Step 6: Run the test suite to verify all tests pass**

Run: `uv run pytest tests/test_reasoner_stage6.py tests/test_pilot.py -v`
Expected: All tests pass (including the updated `test_stage6_persists_refinements_via_save_partial_callback` and the 2 new sequential-framing tests).

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/reasoner/stage6_pilot.py tests/test_reasoner_stage6.py
git commit -m "$(cat <<'EOF'
feat(sp13): sequential refinement prompt + prior_diffs in _refine_partial

REFINEMENT_PROMPT now instructs the LLM to propose the SMALLEST next
advance per attempt instead of fixing everything in one pass. Adds a
"Prior Refinement Attempts" section so the LLM can see what was tried
and avoid undoing earlier progress.

_refine_partial gains a keyword-only `prior_diffs: list[str]` parameter;
run_stage6 passes an empty list for now (next task wires up the
accumulator and stuck-detection).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: run_stage6 stuck-detection + prior_diffs accumulator

**Files:**
- Modify: `src/experiment_bot/reasoner/stage6_pilot.py` (`run_stage6` body)
- Test: `tests/test_reasoner_stage6.py` (1 new test)

**Why:** Sequential refinement is only safe if we cap oscillation. If two consecutive attempts land on the same DOM fingerprint, the refiner cannot move the bot off that screen via observation alone — keep retrying wastes API budget. The accumulating `prior_diffs` list feeds the prompt rewrite from Task 2.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reasoner_stage6.py`:

```python
@pytest.mark.asyncio
async def test_stage6_stuck_detection_aborts_early(tmp_path):
    """When two consecutive failed attempts produce the same dom_fingerprint,
    Stage 6 raises PilotValidationError without consuming the rest of the
    budget — refinements that don't move the bot won't move it by trying
    again. The error message names the stuck state."""
    fake_client = AsyncMock()
    # Refinement returns a no-op so the partial doesn't actually change
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()

    stuck_diag = PilotDiagnostics(
        trials_completed=0,
        trials_with_stimulus_match=0,
        conditions_observed=[],
        conditions_missing=["go"],
        selector_results={"go": {"matches": 0, "polls": 100}},
        phase_results={},
        dom_snapshots=[{"trigger": "no_match_50_polls",
                        "html": "<div>same screen each time</div>"}],
        anomalies=["100 consecutive polls with no stimulus match"],
        trial_log=[],
    )

    pilot_call_count = 0
    async def fake_pilot_run(*args, **kwargs):
        nonlocal pilot_call_count
        pilot_call_count += 1
        return stuck_diag  # identical fingerprint every call

    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(side_effect=fake_pilot_run)
        pr_cls.return_value = pr
        with pytest.raises(PilotValidationError, match="stuck"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=11,  # large budget; guard should fire first
            )
    # Stuck-detection fires after 2nd identical fingerprint → pilot called 2x, NOT 12x.
    assert pilot_call_count == 2, \
        f"expected stuck-detection to abort after 2 pilots, got {pilot_call_count}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_reasoner_stage6.py::test_stage6_stuck_detection_aborts_early -v`
Expected: FAILED — current code runs all 12 attempts without stuck-detection.

- [ ] **Step 3: Add fingerprint tracking + stuck guard + prior_diffs accumulator to `run_stage6`**

In `src/experiment_bot/reasoner/stage6_pilot.py`, REPLACE the body of `run_stage6` after the `pilot_runner = PilotRunner()` line through to the end with:

```python
    pilot_runner = PilotRunner()
    history: list[str] = []
    evidence: list[str] = []
    fingerprint_history: list[str] = []
    prior_diffs: list[str] = []

    for attempt in range(max_retries + 1):
        config = _partial_to_pilot_config(partial)
        try:
            diagnostics = await pilot_runner.run(config, bundle.url, headless=headless)
        except Exception as e:
            diagnostics = PilotDiagnostics.crashed(str(e))

        passed, reasons = _pilot_passed(diagnostics, config)
        evidence.append(
            f"attempt_{attempt + 1}: trials={diagnostics.trials_with_stimulus_match}, "
            f"conditions={diagnostics.conditions_observed}, "
            f"missing={diagnostics.conditions_missing}, "
            f"anomalies={len(diagnostics.anomalies)}"
        )
        if passed:
            _save_diagnostic(diagnostics, taskcards_dir, label)
            if attempt == 0:
                inference = (
                    f"Pilot passed first attempt: "
                    f"{diagnostics.trials_with_stimulus_match} trials matched, "
                    f"conditions {diagnostics.conditions_observed} all observed."
                )
            else:
                inference = (
                    f"Pilot passed after {attempt} refinement(s): "
                    f"{diagnostics.trials_with_stimulus_match} trials matched, "
                    f"conditions {diagnostics.conditions_observed} all observed. "
                    f"See pilot_refinement_*.diff for changes the bot made."
                )
            return partial, ReasoningStep(
                step="stage6_pilot",
                inference=inference,
                evidence_lines=evidence,
                confidence="high",
            )

        history.append(f"Attempt {attempt + 1}: " + "; ".join(reasons))
        logger.warning("Pilot attempt %d failed: %s", attempt + 1, "; ".join(reasons))

        # Stuck-detection: if the last 2 failed attempts produced the same
        # non-empty DOM fingerprint, the refiner isn't moving the bot. Abort
        # early rather than burning the rest of the budget on the same screen.
        fp = diagnostics.dom_fingerprint
        fingerprint_history.append(fp)
        if (
            len(fingerprint_history) >= 2
            and fingerprint_history[-1]
            and fingerprint_history[-1] == fingerprint_history[-2]
        ):
            _save_diagnostic(diagnostics, taskcards_dir, label)
            raise PilotValidationError(
                f"Pilot stuck at same DOM state across {len(fingerprint_history)} "
                f"attempts (fingerprint {fp}); refinements aren't advancing the "
                f"bot. Latest diagnostic saved to {taskcards_dir}/{label}/pilot.md.\n"
                f"Attempt history:\n  - " + "\n  - ".join(history)
            )

        if attempt == max_retries:
            _save_diagnostic(diagnostics, taskcards_dir, label)
            raise PilotValidationError(
                f"Pilot failed after {max_retries + 1} attempts:\n  - "
                + "\n  - ".join(history)
                + f"\n\nLatest diagnostic saved to {taskcards_dir}/{label}/pilot.md"
            )

        # Refine and retry; capture the diff for provenance.
        before = copy.deepcopy(partial)
        partial = await _refine_partial(
            client, partial, diagnostics, bundle, prior_diffs=prior_diffs,
        )
        diff_text = _save_refinement_diff(before, partial, taskcards_dir, label, attempt + 1)
        if diff_text:
            prior_diffs.append(diff_text)
        if save_partial is not None:
            save_partial(partial)
```

- [ ] **Step 4: Update `_save_refinement_diff` to return the diff text**

Currently `_save_refinement_diff` returns `None` (just writes the file). Update it to return the diff string so the run_stage6 loop can accumulate it into `prior_diffs`.

In `src/experiment_bot/reasoner/stage6_pilot.py`, replace `_save_refinement_diff`:

```python
def _save_refinement_diff(
    before: dict, after: dict, taskcards_dir: Path, label: str, attempt: int,
) -> str:
    """Persist a unified diff of the structural fields the bot changed
    during a refinement attempt. Lives alongside pilot.md so the user
    can audit what the refinement loop did at each step. Returns the
    diff text so run_stage6 can also pass it back to the LLM as
    "Prior Refinement Attempts" context.
    """
    import difflib
    out_dir = Path(taskcards_dir) / label
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ("stimuli", "navigation", "runtime", "task_specific",
              "performance", "pilot_validation_config")
    before_lines: list[str] = []
    after_lines: list[str] = []
    for f in fields:
        before_lines.append(f"# {f}")
        before_lines.extend(json.dumps(before.get(f, {}), indent=2).splitlines())
        before_lines.append("")
        after_lines.append(f"# {f}")
        after_lines.extend(json.dumps(after.get(f, {}), indent=2).splitlines())
        after_lines.append("")
    diff_text = "\n".join(difflib.unified_diff(
        before_lines, after_lines,
        fromfile=f"before_attempt_{attempt}",
        tofile=f"after_attempt_{attempt}",
        lineterm="",
    ))
    (out_dir / f"pilot_refinement_{attempt}.diff").write_text(diff_text)
    return diff_text
```

- [ ] **Step 5: Run full Stage 6 test suite**

Run: `uv run pytest tests/test_reasoner_stage6.py tests/test_pilot.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage6_pilot.py tests/test_reasoner_stage6.py
git commit -m "$(cat <<'EOF'
feat(sp13): stuck-detection + prior_diffs accumulator in run_stage6

run_stage6 now tracks dom_fingerprint history across attempts. When two
consecutive failed attempts produce the same non-empty fingerprint, raises
PilotValidationError early with a "Pilot stuck at same DOM state" message
instead of burning the rest of the budget on the same screen.

Each refinement's diff text is captured and passed to the next call's
prior_diffs argument, which surfaces in the LLM prompt's "Prior Refinement
Attempts" section so the refiner can build on (not undo) earlier progress.

_save_refinement_diff now returns the diff text so the accumulator can read
it without re-reading the persisted file.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Bump pilot budget defaults

**Files:**
- Modify: `src/experiment_bot/reasoner/cli.py` (`--pilot-max-retries` default 2 → 11)
- Modify: `src/experiment_bot/reasoner/pipeline.py` (`pilot_max_retries: int = 1` → `= 11`)
- Test: `tests/test_reasoner_stage6.py` (1 new test verifying override still works)

**Why:** With stuck-detection guarding against runaway loops, a 12-total-attempts budget gives the sequential walker room to advance multi-step entry flows (fullscreen → instructions page 1 → instructions page 2 → practice). Dev-4 paradigms unaffected because they pass on attempt 1.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reasoner_stage6.py`:

```python
@pytest.mark.asyncio
async def test_stage6_max_retries_override_respected(tmp_path):
    """Caller-supplied max_retries overrides the function-signature default.
    Verifies the budget is still configurable from the CLI / pipeline."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()
    # Use varying fingerprints so stuck-detection doesn't short-circuit.
    diags = [
        PilotDiagnostics(
            trials_completed=0, trials_with_stimulus_match=0,
            conditions_observed=[], conditions_missing=["go"],
            selector_results={"go": {"matches": 0, "polls": 100}},
            phase_results={}, dom_snapshots=[
                {"trigger": "no_match_50_polls", "html": f"<div>screen-{i}</div>"}],
            anomalies=[], trial_log=[],
        )
        for i in range(5)
    ]
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(side_effect=diags)
        pr_cls.return_value = pr
        with pytest.raises(PilotValidationError, match="4 attempts"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=3,  # override → 4 total attempts
            )
```

- [ ] **Step 2: Run to verify it passes already (no behavior change yet — this is a regression guard)**

Run: `uv run pytest tests/test_reasoner_stage6.py::test_stage6_max_retries_override_respected -v`
Expected: PASS. (The test verifies existing behavior survives the default change.)

- [ ] **Step 3: Bump CLI default**

In `src/experiment_bot/reasoner/cli.py`, find:

```python
@click.option("--pilot-max-retries", type=int, default=2,
              help="Max refinement retries when Stage 6 pilot fails (default: 2).")
```

Replace with:

```python
@click.option("--pilot-max-retries", type=int, default=11,
              help="Max refinement retries when Stage 6 pilot fails (default: "
                   "11 → 12 total attempts). Stuck-detection aborts early if "
                   "two consecutive attempts hit the same DOM state.")
```

Also find the `_run` function signature and update its default:

```python
async def _run(url, label, hint, taskcards_dir, work_dir, resume,
               *, skip_pilot=False, pilot_headed=False, pilot_max_retries=1):
```

Replace with:

```python
async def _run(url, label, hint, taskcards_dir, work_dir, resume,
               *, skip_pilot=False, pilot_headed=False, pilot_max_retries=11):
```

- [ ] **Step 4: Bump pipeline default**

In `src/experiment_bot/reasoner/pipeline.py`, find:

```python
        pilot_max_retries: int = 1,
```

Replace with:

```python
        pilot_max_retries: int = 11,
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/cli.py src/experiment_bot/reasoner/pipeline.py tests/test_reasoner_stage6.py
git commit -m "$(cat <<'EOF'
feat(sp13): bump pilot refinement budget 2 → 11 (12 total attempts)

Sequential refinement (SP13) advances by one DOM state per attempt, so
multi-screen entry flows (fullscreen → instructions → practice) need
more headroom than the 3-attempt cap from one-shot mode. Stuck-detection
caps runaway loops at 2 same-fingerprint attempts, so the upper bound
on wasted API calls per pathological paradigm is small.

Defaults bumped in CLI flag and pipeline constructor; both stay overridable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update `docs/pipeline-flow.md` Stage 6 description

**Files:**
- Modify: `docs/pipeline-flow.md`

**Why:** The Reasoner section's Stage 6 row currently reads "Live-DOM pilot validation against URL (optional via --skip-pilot)" — accurate but doesn't reflect SP13's sequential walker. One-line update + add a brief callout.

- [ ] **Step 1: Update the Stage 6 row in the Reasoner pipeline table**

Find this line in `docs/pipeline-flow.md` (around line 181):

```markdown
| 6 | stage6_pilot.py | Live-DOM pilot validation against URL (optional via --skip-pilot) |
```

Replace with:

```markdown
| 6 | stage6_pilot.py | Live-DOM pilot validation + sequential refinement walker against URL (optional via --skip-pilot) |
```

- [ ] **Step 2: Add a Stage 6 callout paragraph below the entry point line**

Find this section (around line 183):

```markdown
Entry point: `reasoner/pipeline.py:ReasonerPipeline.run`.
```

Insert directly below (before the next `## 12.` section):

```markdown
**Stage 6 refinement (SP13):** When the pilot fails, the refiner is asked
to propose ONE smallest advance — click past a single interstitial screen,
or update a single stimulus selector to match observed DOM. Each attempt
sees prior attempts' diffs so it can build on earlier progress without
undoing it. A DOM-fingerprint guard aborts early if two consecutive
attempts can't move the bot off the same screen. Budget defaults to 12
total attempts (`--pilot-max-retries 11`).
```

- [ ] **Step 3: Commit**

```bash
git add docs/pipeline-flow.md
git commit -m "$(cat <<'EOF'
docs(sp13): update pipeline-flow.md Stage 6 section for sequential refinement

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Held-out validation — re-run `stop_signal_with_integrated_memory`

**Files:**
- Modify: `taskcards/stop_signal_with_integrated_memory/` (the Reasoner may write a new TaskCard if pilot converges, or new pilot.md / refinement diffs if it doesn't)
- The previous artifacts (`66a9b91b.json`, `pilot.md`, `pilot_refinement_1.diff`, `pilot_refinement_2.diff`) MUST be deleted before re-running so old state doesn't contaminate the test.

**Why:** This is the primary external validation. SP13's worth is empirically tested against the paradigm that motivated it.

- [ ] **Step 1: Clean prior held-out artifacts**

Run:
```bash
rm -f taskcards/stop_signal_with_integrated_memory/66a9b91b.json
rm -f taskcards/stop_signal_with_integrated_memory/pilot.md
rm -f taskcards/stop_signal_with_integrated_memory/pilot_refinement_*.diff
rm -rf .reasoner_work/stop_signal_with_integrated_memory
```

- [ ] **Step 2: Re-run the Reasoner with sequential refinement**

Run (in background; this can take 5-15 min depending on how many refinements):
```bash
uv run experiment-bot-reason https://deploy.expfactory.org/preview/80/ \
    --label stop_signal_with_integrated_memory \
    --pilot-max-retries 11 \
    --pilot-headed 2>&1 | tee /tmp/sp13-heldout-run.log
```

`--pilot-headed` makes the browser visible so the user can watch progress, but is optional. If running unattended, drop the flag.

Expected: One of
- **PASS**: Stage 6 converges within budget; TaskCard JSON written to `taskcards/stop_signal_with_integrated_memory/<sha>.json`; `pilot.md` shows trials matched and conditions observed; `pilot_refinement_N.diff` files chronicle the walk.
- **STUCK-DOM FAIL**: PilotValidationError with "stuck at same DOM state" message; latest pilot.md shows where the walker plateaued.
- **BUDGET FAIL**: PilotValidationError with "failed after 12 attempts"; pilot.md and 11 refinement diffs document the walk.

All three are acceptable outcomes per the spec. Capture which one happened for Task 8.

- [ ] **Step 3: Verify artifacts written**

Run: `ls taskcards/stop_signal_with_integrated_memory/`
Expected: At minimum `pilot.md`. If PASS: also a TaskCard JSON. If FAIL: pilot_refinement_*.diff files (one per attempted refinement).

- [ ] **Step 4: Commit held-out artifacts**

```bash
git add taskcards/stop_signal_with_integrated_memory/
git commit -m "$(cat <<'EOF'
chore(sp13): regenerate stop_signal_with_integrated_memory under SP13 walker

Held-out validation re-run after SP13 sequential refinement. Outcome
recorded in docs/sp13-results.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Dev-4 regression smoke

**Files:**
- The Reasoner will write new TaskCard JSONs under each paradigm's existing `taskcards/<label>/` directory; old JSONs (committed in earlier SPs) MUST NOT be deleted — the test is that the new run produces a TaskCard equivalent to the existing one (passes Stage 6 on attempt 1).

**Why:** Per spec pass criteria: dev-4 paradigms must still pass Stage 6 on attempt 1 (sequential mode is backward-compatible for paradigms the bot already handles).

- [ ] **Step 1: Re-run Reasoner against each dev paradigm**

Run each in sequence (NOT parallel — they share the Reasoner work dir). Each takes ~3-5 min.

```bash
# Sequential, fail-fast — if any of these regress, halt and investigate
for label in expfactory_stroop expfactory_stop_signal stopit_stop_signal cognitionrun_stroop; do
    echo "=== Regenerating $label ==="
    rm -rf ".reasoner_work/$label"
    uv run experiment-bot-reason "$(grep '"url"' "taskcards/$label"/*.json | head -1 | sed -E 's/.*"url":[[:space:]]*"([^"]+)".*/\1/')" \
        --label "$label" \
        --pilot-max-retries 11 \
        2>&1 | tee "/tmp/sp13-regression-${label}.log" || { echo "REGRESSION: $label failed"; exit 1; }
done
```

If any paradigm now requires refinements (i.e. Stage 6 didn't pass on attempt 1), inspect `taskcards/<label>/pilot.md` and the refinement diffs — that's a regression and Task 8 must report it honestly.

Expected: All 4 paradigms log "Pilot passed first attempt" in their reasoning step output.

- [ ] **Step 2: Verify no TaskCard JSON contents changed substantively**

The new TaskCard JSONs will have new `produced_by.timestamp` and `taskcard_sha256` (expected) but structural fields should be byte-equivalent. Spot-check one paradigm:

```bash
# Diff structural fields between latest committed TaskCard and the new one
# (ignore produced_by, reasoning_chain, taskcard_sha256 — those are derived).
python3 - <<'PYEOF'
import json, glob
for label in ["expfactory_stroop", "expfactory_stop_signal", "stopit_stop_signal", "cognitionrun_stroop"]:
    cards = sorted(glob.glob(f"taskcards/{label}/*.json"))
    if len(cards) < 2:
        print(f"  {label}: only {len(cards)} TaskCard(s); skipping diff")
        continue
    older, newer = cards[-2], cards[-1]
    a = json.load(open(older)); b = json.load(open(newer))
    for k in ("stimuli", "navigation", "runtime", "task_specific", "performance"):
        if a.get(k) != b.get(k):
            print(f"  {label}: {k} CHANGED between {older} and {newer}")
        else:
            print(f"  {label}: {k} unchanged")
PYEOF
```

Expected: Most fields unchanged. Any change must be explained in Task 8.

- [ ] **Step 3: Commit any new TaskCard JSONs**

```bash
git add taskcards/
git commit -m "$(cat <<'EOF'
chore(sp13): dev-4 paradigm TaskCard regression run (Stage 6 attempt 1 pass)

All 4 dev paradigms regenerated under SP13's sequential refinement mode;
each passed Stage 6 on attempt 1 with no refinements (backward-compatible
behavior preserved). Updated TaskCards differ from prior versions only in
provenance fields (produced_by.timestamp, taskcard_sha256).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If any paradigm needed refinements: do NOT commit; halt and add notes to Task 8 docs documenting the regression.

---

## Task 8: Write `docs/sp13-results.md`

**Files:**
- Create: `docs/sp13-results.md`

**Why:** Per the project's SP-deliverable convention (`docs/sp5-heldout-measurement-results.md`, `docs/sp9a-results.md`, etc.). This is the honest reporting of what SP13 achieved or didn't.

- [ ] **Step 1: Write the results doc**

Create `docs/sp13-results.md`. Outline:

```markdown
# SP13 — Iterative Pilot Refinement: Results

## Internal validation

- Test suite: <N> passed (was <N-7> at SP12-complete). New tests: dom_fingerprint
  (3), sequential-prompt invariant (1), prior_diffs prompt rendering (1),
  stuck-detection (1), max_retries override (1).
- Held-out paradigm re-run: [PASS / STUCK-DOM FAIL / BUDGET FAIL].
- Dev-4 regression: all 4 paradigms passed Stage 6 on attempt 1 [confirm].

## Held-out paradigm outcome: stop_signal_with_integrated_memory

[Describe outcome. If PASS: how many refinements, what each one did
(reading the per-attempt diffs), what the final TaskCard looks like.
If FAIL: at which DOM state did the walker plateau, what was the
diagnostic, what conclusion to draw.]

## Dev-4 regression summary

| Paradigm | Stage 6 attempt 1 result | Refinements needed | Notes |
|---|---|---|---|
| expfactory_stroop | PASS | 0 | |
| expfactory_stop_signal | PASS | 0 | |
| stopit_stop_signal | PASS | 0 | |
| cognitionrun_stroop | PASS | 0 | |

## Comparison to pre-SP13 baseline

Pre-SP13 (commit `1ff0e9e`): held-out paradigm failed at Stage 6 after 3
attempts; TaskCard required `--skip-pilot` + manual nav patch; runtime
session captured 0 trials. Post-SP13: [report new outcome].

## What SP13 demonstrates

[1-2 paragraphs. If the held-out paradigm converged: SP13 closes the
generalization gap surfaced in the pre-SP13 held-out test. If it didn't
converge: SP13 establishes that iterative refinement is necessary but not
sufficient; richer recon (e.g. interaction-driven DOM exploration, canvas
rendering recognition) would be needed for paradigms where observation-via-
snapshot alone can't surface the right selectors. Either outcome is a
scope-of-validity refinement, not a project failure.]

## What SP13 does NOT do

- Does not add executor-side fallbacks (Option B from the brainstorm
  remains deferred).
- Does not add pre-Stage-1 reconnaissance (Option A remains rejected
  per G2 separation).
- Does not change the Stage 6 PilotValidationError gate's role; that
  remains the honest failure surface.

## Stopping recommendation

[PASS: ship; tag sp13-complete. STUCK-DOM FAIL: ship with documented
limitation; the failure mode is now precisely characterized for future
follow-up. BUDGET FAIL: investigate one round — what was the walker
trying? If it was making real per-attempt progress and just ran out of
budget, bump default to 20. If it was oscillating, that's a deeper issue
for a future SP.]
```

Fill in the bracketed sections from the actual run outputs.

- [ ] **Step 2: Commit**

```bash
git add docs/sp13-results.md
git commit -m "$(cat <<'EOF'
docs(sp13): results doc — held-out + dev-4 regression outcomes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Update `CLAUDE.md` sub-project history

**Files:**
- Modify: `CLAUDE.md` (append SP13 entry to the "Sub-project history" list)

**Why:** Per the project convention; every SP-complete tag updates `CLAUDE.md`.

- [ ] **Step 1: Append SP13 entry**

In `CLAUDE.md`, find the SP12 entry in the "Sub-project history" section. After SP12's `Tag sp12-complete. ✓ Complete.` line, before `- **Reviewer-1 charter**:`, insert:

```markdown
- **SP13**: Iterative pilot refinement — Stage 6's one-shot refiner replaced
  with a sequential walker that advances one DOM state per attempt.
  `PilotDiagnostics.dom_fingerprint` enables stuck-detection (2 consecutive
  identical fingerprints → early PilotValidationError). Refinement prompt
  rewritten to "propose the smallest next advance"; prior-attempt diffs are
  forwarded so the LLM doesn't undo earlier progress. Budget bumped 3 → 12
  total attempts. Internal CI: <N> passed (was <N-7>); +7 tests across
  fingerprint, prompt invariants, prior_diffs rendering, stuck-detection,
  budget override. External: held-out paradigm
  `stop_signal_with_integrated_memory` [outcome from Task 8]. Dev-4 paradigms
  pass Stage 6 on attempt 1 (backward-compatible). See `docs/sp13-spec.md`
  and `docs/sp13-results.md`. Tag `sp13-complete`. ✓ Complete.
```

Fill in `<N>` from the test-suite output and `[outcome from Task 8]` from
the held-out run.

- [ ] **Step 2: Commit + tag**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(sp13): append SP13 to sub-project history in CLAUDE.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git tag sp13-complete
```

- [ ] **Step 3: Push commits and tag**

```bash
git push
git push --tags
```

---

## Self-Review (run after writing the plan, fix issues inline)

**1. Spec coverage:** Each spec section maps to a task:
- "PilotDiagnostics gains dom_fingerprint" → Task 1 ✓
- "REFINEMENT_PROMPT switches to sequential framing" → Task 2 ✓
- "_refine_partial accepts prior_diffs" → Task 2 ✓
- "run_stage6 stuck-detection + prior_diffs accumulator" → Task 3 ✓
- "Budget defaults bumped" → Task 4 ✓
- "Reasoning step inference reflects sequential mode" → preserved in Task 3's run_stage6 rewrite (existing wording carried forward) ✓
- "Held-out re-validation" → Task 6 ✓
- "Dev-4 regression" → Task 7 ✓
- "Docs update" → Tasks 5, 8, 9 ✓

**2. Placeholder scan:** None. All code is concrete; commands have expected outputs; commit messages are pre-written. The two bracketed substitutions in Tasks 8-9 (`<N>` tests passing, held-out outcome) are intentional — they get filled from actual run output.

**3. Type consistency:**
- `dom_fingerprint` is `str` everywhere (property return, comparisons, list).
- `prior_diffs` is `list[str]` everywhere (`_refine_partial` parameter, run_stage6 accumulator, test fixture).
- `_save_refinement_diff` return-type changed from `None` to `str` — Task 3 Step 4 updates the function; Task 3's run_stage6 body uses the returned value.

**4. Backward compatibility:** All public signatures with new parameters use keyword-only (`*, prior_diffs`) so existing positional callers (none in production code) won't break silently. Existing `_refine_partial` test stub (`fake_refine` in `test_stage6_persists_refinements_via_save_partial_callback`) is updated in Task 2 Step 1.

Plan is ready.

---

## Execution Handoff

Plan complete. Per `feedback_skip_code_quality_reviewer` memory: use **superpowers:subagent-driven-development** to execute; dispatch the implementer subagent per task, then run the **spec-compliance reviewer ONLY** between tasks (skip the code-quality reviewer stage). Continue until all tasks complete or BLOCKED.
