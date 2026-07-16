"""Stage 6: live-DOM pilot validation of the Reasoner's structural output.

Runs the partial TaskCard against the live experiment URL via Playwright,
captures diagnostics (selector match rates, phase firings, DOM snapshots,
condition coverage), and on failure either refines the partial via Claude
or hard-fails — depending on `max_retries`.

The pilot exercises only structural fields (stimuli, navigation,
runtime). It does not sample RTs or model behavior. Pilot runs after
Stage 1 and before TaskCard finalization, so refinements target the
same fields Stage 1 produced.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
from pathlib import Path
from typing import Callable

from experiment_bot.core.config import (
    NavigationConfig, PerformanceConfig, PilotConfig, RuntimeConfig,
    SourceBundle, StimulusConfig, TaskConfig, TaskMetadata,
)
from experiment_bot.core.pilot import PilotDiagnostics, PilotRunner, _NO_MATCH_EARLY_STOP
from experiment_bot.core.pilot_session import (
    HUMAN_READING_DELAY_RANGE, PilotSession,
)
from experiment_bot.core.stimulus import StimulusLookup
from experiment_bot.output.data_capture import ConfigDrivenCapture
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.normalize import normalize_partial
from experiment_bot.reasoner.parse_retry import parse_with_retry
from experiment_bot.taskcard.types import ReasoningStep

logger = logging.getLogger(__name__)


class PilotValidationError(RuntimeError):
    """Raised when pilot validation fails after exhausting refinement retries."""


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

**APPEND ordering rule** (load-bearing). When adding a new `navigation.phases`
entry, APPEND it to the END of the existing array — never prepend, reorder, or
replace an existing entry. The navigator executes phases in array order, and
that order matches the order screens appear during the experiment. The DOM
snapshot you're looking at is the screen the bot reached AFTER all previously-
listed phases ran successfully, so any new phase you add belongs LAST. If you
think a new phase should run before an existing one, you are wrong — the
existing phase already advanced the bot past its target screen.

Fix ONLY structural fields: `stimuli`, `navigation`, `runtime.advance_behavior`,
`runtime.phase_detection`, `runtime.data_capture`, `task_specific`. Do NOT modify
`response_distributions`, `temporal_effects`, `between_subject_jitter`, or
`performance.accuracy/omission_rate` — those fields are not structural and
the pilot's evidence does not bear on them.

## Navigation phase JSON schema (CRITICAL — get this right)

The navigator consumes a FLAT phase shape. Top-level fields are `action`,
`target`, `key`, `value`, `duration_ms`, `steps`, plus an informational
`phase` label.
Do NOT nest under `action.type`/`action.selector` — that nested shape is
silently ignored by the navigator and produces no behavior (a common failure
mode that wastes refinement budget).

Supported `action` values and the fields each uses:

- **click** — uses `target` (CSS selector). The navigator clicks the first
  matching visible element. Times out at 1.5s if not visible; subsequent
  refinements should pick a different target if this one disappeared.
  ```json
  {{"phase": "fullscreen_prompt", "action": "click", "target": "#jspsych-fullscreen-btn", "key": "", "duration_ms": 0, "steps": []}}
  ```

- **keypress** (also accepts `press`) — uses `key` (Playwright key name like
  `" "` for Space, `"Enter"`, `"ArrowRight"`).
  ```json
  {{"phase": "instructions", "action": "keypress", "target": "", "key": " ", "duration_ms": 0, "steps": []}}
  ```

- **wait** — uses `duration_ms` (integer milliseconds).
  ```json
  {{"phase": "", "action": "wait", "target": "", "key": "", "duration_ms": 800, "steps": []}}
  ```

- **fill** — uses `target` (CSS selector for a text input/textarea) and
  `value` (the text to type into it). Use this when a form field blocks
  progress (consent/demographic forms); for required form fields, propose
  plausible neutral values.
  ```json
  {{"phase": "entry_form", "action": "fill", "target": "input[name='code']", "key": "", "value": "anon", "duration_ms": 0, "steps": []}}
  ```

- **select** — uses `target` (CSS selector) and `value` (the option's value
  or visible label) to pick a dropdown option. With an EMPTY `value`, the
  navigator clicks the target instead — use that form for radio buttons and
  checkboxes.
  ```json
  {{"phase": "entry_form", "action": "select", "target": "select#choice", "key": "", "value": "Other", "duration_ms": 0, "steps": []}}
  ```

- **sequence** — uses `steps` (array of nested flat phases). Useful when one
  logical advance requires several keystrokes/clicks in order. Each step is a
  flat phase dict with its own `action`/`target`/`key`/`duration_ms` fields.
  ```json
  {{"phase": "instructions_multi_page", "action": "sequence", "target": "", "key": "", "duration_ms": 0,
   "steps": [
     {{"action": "keypress", "key": " ", "duration_ms": 0}},
     {{"action": "wait", "duration_ms": 500}},
     {{"action": "keypress", "key": " ", "duration_ms": 0}}
   ]}}
  ```

When in doubt: use a single `click` phase with the exact CSS selector visible in
the DOM snapshot. Add unused fields as empty strings / 0 / `[]` to keep the
shape consistent — the navigator ignores them.

Return ONLY a JSON object containing the field(s) you changed. Unchanged fields
should be omitted; the pipeline will splice your output into the existing
partial. Return JSON only, no preamble.
"""


NAVIGATION_REFINEMENT_PROMPT = """\
You are advancing an experiment-bot through one screen of an experiment. The
bot ran all known navigation phases and is now stuck at the screen described
in the DOM snapshot below. Your job: propose ONE additional navigation phase
to APPEND to the current sequence.

## Current DOM (the screen the bot is stuck on)
{dom_snapshot}

## Phases already executed (in order)
{accumulated_phases}

## Prior refinement attempts (chronological)
{prior_diffs_section}

## Instructions

Identify what's blocking THIS specific screen. Propose ONE new navigation
phase that gets the bot off this screen.

Do NOT undo earlier progress — if prior attempts are listed above, the bot
is now in a DIFFERENT state. If you see yourself trying the same change twice,
something else is blocking; switch to a different observation.

## Navigation phase JSON schema (CRITICAL — get this right)

The navigator consumes a FLAT phase shape. Top-level fields are `action`,
`target`, `key`, `value`, `duration_ms`, `steps`, plus an informational
`phase` label.
Do NOT nest under `action.type`/`action.selector` — that nested shape is
silently ignored by the navigator and produces no behavior (a common failure
mode that wastes refinement budget).

Supported `action` values and the fields each uses:

- **click** — uses `target` (CSS selector). The navigator clicks the first
  matching visible element. Times out at 1.5s if not visible; subsequent
  refinements should pick a different target if this one disappeared.
  ```json
  {{"phase": "fullscreen_prompt", "action": "click", "target": "#jspsych-fullscreen-btn", "key": "", "duration_ms": 0, "steps": []}}
  ```

- **keypress** (also accepts `press`) — uses `key` (Playwright key name like
  `" "` for Space, `"Enter"`, `"ArrowRight"`).
  ```json
  {{"phase": "instructions", "action": "keypress", "target": "", "key": " ", "duration_ms": 0, "steps": []}}
  ```

- **wait** — uses `duration_ms` (integer milliseconds).
  ```json
  {{"phase": "", "action": "wait", "target": "", "key": "", "duration_ms": 800, "steps": []}}
  ```

- **fill** — uses `target` (CSS selector for a text input/textarea) and
  `value` (the text to type into it). Use this when a form field blocks
  progress (consent/demographic forms); for required form fields, propose
  plausible neutral values.
  ```json
  {{"phase": "entry_form", "action": "fill", "target": "input[name='code']", "key": "", "value": "anon", "duration_ms": 0, "steps": []}}
  ```

- **select** — uses `target` (CSS selector) and `value` (the option's value
  or visible label) to pick a dropdown option. With an EMPTY `value`, the
  navigator clicks the target instead — use that form for radio buttons and
  checkboxes.
  ```json
  {{"phase": "entry_form", "action": "select", "target": "select#choice", "key": "", "value": "Other", "duration_ms": 0, "steps": []}}
  ```

- **sequence** — uses `steps` (array of nested flat phases). Useful when one
  logical advance requires several keystrokes/clicks in order. Each step is a
  flat phase dict with its own `action`/`target`/`key`/`duration_ms` fields.
  ```json
  {{"phase": "instructions_multi_page", "action": "sequence", "target": "", "key": "", "duration_ms": 0,
   "steps": [
     {{"action": "keypress", "key": " ", "duration_ms": 0}},
     {{"action": "wait", "duration_ms": 500}},
     {{"action": "keypress", "key": " ", "duration_ms": 0}}
   ]}}
  ```

**APPEND ordering rule** (load-bearing). APPEND the new phase to the END of
the existing sequence — never prepend, reorder, or replace an existing entry.
The navigator executes phases in array order. The DOM snapshot above is the
screen the bot reached AFTER all previously-listed phases ran successfully, so
the new phase belongs LAST.

When in doubt: use a single `click` phase with the exact CSS selector visible
in the DOM snapshot. Add unused fields as empty strings / 0 / `[]` to keep
the shape consistent — the navigator ignores them.

Return ONLY one JSON object matching the flat navigation-phase schema —
the single phase to APPEND to the existing sequence. Do NOT return an array,
do NOT return a full TaskCard edit. Return JSON only.
"""


STIMULUS_REFINEMENT_PROMPT = """\
The bot reached the experiment's trial-rendering phase but none of the
configured stimulus selectors matched the DOM. Propose ONE selector update.

## Current DOM (the trial-rendering screen)
{dom_snapshot}

## Current stimulus configurations (id -> selector)
{stim_table}

## Prior refinement attempts (chronological)
{prior_diffs_section}

## Instructions

Examine the DOM. Identify which stimulus is currently rendered (it should
match one of the conditions in the stim table). Propose ONE selector update.

Return ONLY a JSON object: {{"stim_id": "<id>", "new_selector": "<css or js>",
"detection_method": "dom_query" | "js_eval" | "text_content"}}. No preamble.
"""


# Extra single-phase refinement rounds granted when the C3 replay gate
# fails after a passing live pilot (each round: propose ONE phase from the
# replay's stuck DOM, append, re-replay).
_REPLAY_REFINE_BUDGET = 2

# Minimum seconds between replay advance actions (executor-faithful pacing;
# see replay_navigation docstring note on anti-skim guards).
_REPLAY_ADVANCE_SPACING_S = 2.0

# Poll budget for the paced replay: pacing allows ~1 advance per
# _REPLAY_ADVANCE_SPACING_S, so a multi-screen instruction flow needs a
# time-commensurate budget (1200 polls x 50ms ~= 60s of wall clock plus
# locator latencies) rather than the walker's shorter early-stop budget.
_REPLAY_MAX_POLLS = 1200


async def replay_navigation(url, navigation, lookup, *, advance_behavior=None,
                            headless=True, viewport=None,
                            max_polls=_REPLAY_MAX_POLLS,
                            reading_delay_range=HUMAN_READING_DELAY_RANGE,
                            ) -> tuple[bool, str]:
    """Fresh-browser, executor-shaped replay: run the finalized navigation.phases
    serially via the unified PilotSession engine (exactly as the executor's entry
    nav does), then poll for a trial stimulus WHILE pressing advance_keys
    periodically — mirroring the executor's trial loop, which presses advance keys
    when no stimulus matches (e.g. to dismiss a "press enter to begin practice"
    interstitial that nav legitimately leaves the bot on). Returns
    (reached, final_dom): reached is True iff a trial stimulus is rendered;
    final_dom is the page snapshot at exit so a gate failure can seed one
    more walker refinement round (see run_stage6's replay-refine loop).

    The advance-key behavior is load-bearing: nav phases get the bot to the brink
    of the trial block, but the final transition into trials is driven by the
    executor's trial-loop advance behavior, NOT by a baked-in nav phase (response
    and block-start keys are dynamic). Without modeling it here the replay would
    be STRICTER than the executor and reject cards the executor can actually run.
    """
    advance_keys = list(getattr(advance_behavior, "advance_keys", []) or [])
    feedback_selectors = list(getattr(advance_behavior, "feedback_selectors", []) or [])
    interval = getattr(advance_behavior, "advance_interval_polls", 10) or 10
    # Executor-faithful pacing: the executor separates advance actions by its
    # navigation delays (~1s+); an unpaced replay advancing every ~0.5s trips
    # anti-skim guards ("read too quickly" re-read loops on RDoC-style
    # instruction flows) that the executor never trips. Held-out flanker
    # surfaced this. Keep advance actions >= _REPLAY_ADVANCE_SPACING_S apart.
    last_advance = 0.0
    async with PilotSession(headless=headless, viewport=viewport,
                            reading_delay_range=reading_delay_range) as session:
        await session.goto(url)
        for phase in navigation.phases:
            await session.try_phase(phase)  # skip-on-fail, like the executor
        misses = 0
        for _ in range(max_polls):
            probe = await session.probe_stimulus(lookup)
            if probe.match is not None:
                return True, ""
            misses += 1
            import time as _time
            if misses % interval == 0 and (_time.monotonic() - last_advance) >= _REPLAY_ADVANCE_SPACING_S:
                last_advance = _time.monotonic()
                for k in advance_keys:
                    await session.press(k)
                # Mirror the executor's full advance behavior (executor.py
                # instructions-screen handling): after the keys, click the
                # first visible advance control — the card's feedback
                # selectors, then the platform's multi-page instructions
                # pager Next control. Held-out flanker surfaced the gap —
                # jsPsych's multi-page instructions pager advances by
                # BUTTON, so a keys-only replay is stricter than the
                # executor and rejects cards the executor can run.
                await session.click_advance_control(tuple(feedback_selectors))
            await asyncio.sleep(0.05)  # 50ms between polls, let DOM transition settle
        return False, await session.dom_snapshot()


async def _validate_phase_predicates(session, phase_detection, trial_html, after_nav_html):
    """Evaluate the card's phase predicates against recorded pilot DOM
    snapshots in a throwaway page (A2 hardening: LLM-written predicates can
    be wrong yet silently harmless-or-harmful; observed live as a 'test'
    predicate that never fired during real trials).

    Returns (hard_fail_msg | None, warnings). Advisory except the one lethal
    case: a 'complete' predicate that fires on the trial DOM would end live
    sessions mid-task. A page-construction error degrades the whole check to
    a skipped-note (the predicates are advisory to the executor since
    trial-ness derives from structural roles, not phases)."""
    try:
        page = await session.context.new_page()
    except Exception as e:  # noqa: BLE001 — advisory check must not sink a passing pilot
        return None, [f"phase_predicate check skipped: {type(e).__name__}: {e}"]
    warnings: list[str] = []
    try:
        async def _fires(js: str, html: str) -> bool:
            if not js:
                return False
            await page.set_content(html)
            try:
                return bool(await page.evaluate(f"!!({js})"))
            except Exception:  # noqa: BLE001 — malformed predicate == does not fire
                return False

        complete_js = getattr(phase_detection, "complete", "") or ""
        test_js = getattr(phase_detection, "test", "") or ""
        practice_js = getattr(phase_detection, "practice", "") or ""
        if trial_html:
            if await _fires(complete_js, trial_html):
                return (
                    "phase_detection.complete fires on the recorded trial DOM — "
                    "live sessions would be declared complete mid-task",
                    warnings,
                )
            if not (await _fires(test_js, trial_html)
                    or await _fires(practice_js, trial_html)):
                warnings.append(
                    "phase_predicate_warning: neither 'test' nor 'practice' "
                    "fires on the recorded trial DOM"
                )
        if after_nav_html and await _fires(complete_js, after_nav_html):
            warnings.append(
                "phase_predicate_warning: 'complete' fires on the "
                "after-navigation DOM"
            )
    finally:
        try:
            await page.close()
        except Exception:  # noqa: BLE001
            pass
    return None, warnings


def _partial_to_pilot_config(partial: dict) -> TaskConfig:
    """Build a TaskConfig from a Reasoner partial that's runnable for pilot.

    Only structural fields are populated; response_distributions and
    temporal_effects are left empty since pilot doesn't sample RTs.

    The partial may carry the raw mid-pipeline shape (key aliases, missing
    sub-dicts, list-vs-dict mismatches) — normalize first so downstream
    dataclass constructors get canonical input. Stage 6 is the final
    stage, so normalizing here is idempotent with the cli.py post-pipeline
    normalize call.
    """
    p = normalize_partial(partial)
    pilot_dict = p.get("pilot_validation_config", p.get("pilot", {}))
    return TaskConfig(
        task=TaskMetadata.from_dict(p.get("task", {})),
        stimuli=[StimulusConfig.from_dict(s) for s in p.get("stimuli", [])],
        response_distributions={},  # pilot doesn't sample RTs
        performance=PerformanceConfig.from_dict(
            p.get("performance", {"accuracy": {}})
        ),
        navigation=NavigationConfig.from_dict(p.get("navigation", {"phases": []})),
        task_specific=p.get("task_specific", {}),
        pilot=PilotConfig.from_dict(pilot_dict),
        runtime=RuntimeConfig.from_dict(p.get("runtime", {})),
    )


def _capture_row_count(data: str, fmt: str) -> int:
    """Count trial rows in a captured export string (Wave A1).

    - ``json``: a list counts its elements; a dict counts its longest
      list-valued entry (wrapper objects like ``{"trials": [...]}``);
      any other parsed shape counts 0. Invalid JSON raises
      ``ValueError("unparseable ...")``.
    - delimited (csv/tsv and anything else): non-empty lines minus one
      assumed header line — a header-only (or single-line) export counts
      0 rows. Conservative on purpose: the gate exists to catch empty
      exports, and a lone line is indistinguishable from a bare header.
    """
    if fmt == "json":
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"unparseable JSON: {e}") from None
        if isinstance(parsed, list):
            return len(parsed)
        if isinstance(parsed, dict):
            lengths = [len(v) for v in parsed.values() if isinstance(v, list)]
            return max(lengths) if lengths else 0
        return 0
    lines = [ln for ln in data.splitlines() if ln.strip()]
    return max(0, len(lines) - 1)


async def _validate_data_capture(session: PilotSession, capture_cfg,
                                 evidence: list[str]) -> None:
    """Data-capture gate (Wave A1): a platform can pass selector/nav
    validation yet produce an EMPTY experiment_data export, failing only
    after a full live session.

    Variant choice (documented per spec): the pilot never FINISHES the
    experiment, so an end-of-experiment capture isn't observable at Stage 6.
    The capture configuration is therefore evaluated MID-PILOT, on the
    walker's live session, after the pilot has completed >= pilot.min_trials
    trials — and must already return parseable output with >= 1 trial row.
    This is the honest, implementable variant: it gates on "the configured
    capture method reads back platform-recorded trial rows", the only thing
    the pilot can actually observe. (A platform that materializes its export
    only at completion would fail here — that limitation is preferred over
    passing cards whose capture config was never exercised.)

    Skips — with an evidence note — when no capture method is configured:
    the executor treats that as "platform saves server-side", not an error.
    """
    if not capture_cfg.method:
        evidence.append("data_capture_gate: skipped (no capture method configured)")
        return
    result = await ConfigDrivenCapture(capture_cfg).capture(session.page)
    if result.failed or not (result.data or "").strip():
        what = ("raised an exception during capture" if result.failed
                else "returned empty output")
        raise PilotValidationError(
            f"Stage-6 data-capture gate: capture method {capture_cfg.method!r} "
            f"{what} on the live pilot session after completed pilot trials. "
            f"The executor would run a full session and export nothing. "
            f"Fix runtime.data_capture (expression/selector) so it reads back "
            f"the platform's recorded trials."
        )
    fmt = capture_cfg.format or "csv"
    try:
        rows = _capture_row_count(result.data, fmt)
    except ValueError as e:
        raise PilotValidationError(
            f"Stage-6 data-capture gate: capture method {capture_cfg.method!r} "
            f"returned unparseable {fmt} output ({e}). "
            f"First 200 chars: {result.data[:200]!r}"
        ) from None
    if rows < 1:
        raise PilotValidationError(
            f"Stage-6 data-capture gate: capture method {capture_cfg.method!r} "
            f"returned parseable {fmt} output but 0 trial rows after completed "
            f"pilot trials. First 200 chars: {result.data[:200]!r}"
        )
    evidence.append(
        f"data_capture_gate: method={capture_cfg.method} format={fmt} rows={rows}"
    )


def _pilot_passed(diagnostics: PilotDiagnostics, config: TaskConfig) -> tuple[bool, list[str]]:
    """Return (passed, reasons_failed). Pass criteria:

    - At least pilot.min_trials trials completed with stimulus matches.
    - All target_conditions observed (if specified).
    - No anomalies of severity (the pilot runner currently logs all
      anomalies as strings; we treat any non-empty anomalies list as
      a failure signal but the diagnostic report is the ground truth).
    """
    reasons: list[str] = []
    min_trials = max(1, config.pilot.min_trials)
    if diagnostics.trials_with_stimulus_match < min_trials:
        reasons.append(
            f"only {diagnostics.trials_with_stimulus_match} trials matched a "
            f"stimulus (need at least {min_trials})"
        )
    if diagnostics.conditions_missing:
        reasons.append(
            f"target conditions never observed: {diagnostics.conditions_missing}"
        )
    if diagnostics.anomalies:
        reasons.append(
            f"pilot recorded {len(diagnostics.anomalies)} anomaly/anomalies: "
            f"{diagnostics.anomalies[:3]}"
        )
    return (len(reasons) == 0, reasons)


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


async def _propose_next_phase(
    client: LLMClient,
    dom: str,
    accumulated_phases: list[dict],
    prior_diffs: list[str],
) -> dict:
    """Ask the LLM for ONE navigation phase to append. Returns the phase dict."""
    prior_section = (
        "\n\n".join(
            f"### Attempt {i + 1}\n```diff\n{d}\n```"
            for i, d in enumerate(prior_diffs)
        )
        if prior_diffs else "(none yet — this is the first refinement)"
    )
    user = NAVIGATION_REFINEMENT_PROMPT.format(
        dom_snapshot=dom[:4000],
        accumulated_phases=json.dumps(accumulated_phases, indent=2)[:3000],
        prior_diffs_section=prior_section,
    )
    return await parse_with_retry(
        client, system="", user=user, stage_name="stage6_nav_refinement",
    )


async def _propose_stimulus_update(
    client: LLMClient,
    dom: str,
    stimuli: list[dict],
    prior_diffs: list[str],
) -> dict:
    """Ask the LLM for ONE stimulus selector update. Returns dict with
    stim_id + new_selector + detection_method."""
    stim_table = "\n".join(
        f"- {s['id']}: method={s.get('detection', {}).get('method', '?')}, "
        f"selector={s.get('detection', {}).get('selector', '?')[:120]}"
        for s in stimuli
    )
    prior_section = (
        "\n\n".join(
            f"### Attempt {i + 1}\n```diff\n{d}\n```"
            for i, d in enumerate(prior_diffs)
        )
        if prior_diffs else "(none yet)"
    )
    user = STIMULUS_REFINEMENT_PROMPT.format(
        dom_snapshot=dom[:4000],
        stim_table=stim_table,
        prior_diffs_section=prior_section,
    )
    return await parse_with_retry(
        client, system="", user=user, stage_name="stage6_stim_refinement",
    )


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge `overlay` into `base`. Dicts merge by key;
    non-dict values from overlay replace those in base. Returns a new dict.
    """
    result = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _save_diagnostic(diagnostics: PilotDiagnostics, taskcards_dir: Path, label: str) -> None:
    """Persist pilot diagnostic markdown alongside the TaskCard JSON."""
    out_dir = Path(taskcards_dir) / label
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pilot.md").write_text(diagnostics.to_report())


def _save_pilot_observations(
    diagnostics: PilotDiagnostics, taskcards_dir: Path, label: str,
) -> None:
    """Persist the pilot-observed per-trial condition sequence (encounter
    order) as a SIDECAR next to pilot.md. A sidecar — not a card field — so
    the canonical content hashes of already-committed cards stay stable.
    The mechanical gate (behavior/simgate.py) replays this stream instead
    of a round-robin when it's available (Wave A4a). Skipped when the pilot
    logged no trials.
    """
    stream = [
        e.get("condition") for e in diagnostics.trial_log
        if isinstance(e.get("condition"), str) and e.get("condition")
    ]
    if not stream:
        return
    out_dir = Path(taskcards_dir) / label
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pilot_observations.json").write_text(
        json.dumps({"condition_stream": stream, "source": "stage6_pilot"}, indent=2)
    )


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


async def run_stage6(
    client: LLMClient,
    partial: dict,
    bundle: SourceBundle,
    *,
    label: str,
    taskcards_dir: Path,
    headless: bool = True,
    max_retries: int = 11,
    save_partial: Callable[[dict], None] | None = None,
) -> tuple[dict, ReasoningStep]:
    """Run pilot validation; refine on failure; persist diagnostic + diffs.

    Owns a single PilotSession for the entire refinement loop. Navigation
    phases accumulate in-session; stimulus selector updates mutate the live
    lookup in-place. Accumulators are spliced into partial only on success.

    Raises PilotValidationError if pilot fails after max_retries refinements
    or if stuck-detection fires (2 consecutive identical DOM fingerprints).

    `save_partial`, when supplied, is called after each successful nav-phase
    append so --resume runs pick up refinements rather than re-walking them.
    """
    config = _partial_to_pilot_config(partial)
    accumulated_phases: list[dict] = list(partial.get('navigation', {}).get('phases', []))
    accumulated_stim_overrides: dict[str, str] = {}
    fingerprint_history: list[str] = []
    prior_diffs: list[str] = []
    history: list[str] = []
    evidence: list[str] = []
    nav_refinement_count = 0
    stim_refinement_count = 0

    async with PilotSession(headless=headless, viewport=config.runtime.timing.viewport,
                            reading_delay_range=HUMAN_READING_DELAY_RANGE) as session:
        await session.goto(bundle.url)
        # Apply initial nav phases on the live session ONCE
        for phase_dict in accumulated_phases:
            from experiment_bot.core.config import NavigationPhase as _NavPhase
            await session.try_phase(_NavPhase.from_dict(phase_dict))

        # Build lookup; we'll mutate its selectors on stim refinements
        lookup = StimulusLookup(config)

        for attempt in range(max_retries + 1):
            # Capture DOM state before polling
            container_sel = config.pilot.stimulus_container_selector or "body"
            after_nav_snap = await session.dom_snapshot(container_sel)

            # Poll stimuli against the live session
            try:
                result = await session.poll_stimuli(
                    lookup,
                    max_polls=_NO_MATCH_EARLY_STOP,
                    advance_keys=config.runtime.advance_behavior.advance_keys,
                )
            except Exception as e:
                result = {
                    "trials_completed": 0,
                    "trials_with_stimulus_match": 0,
                    "conditions_observed": [],
                    "selector_results": {},
                    "phase_results": {},
                    "dom_snapshots": [{"trigger": "crash", "html": after_nav_snap}],
                    "anomalies": [f"poll_stimuli crashed: {e}"],
                    "trial_log": [],
                }

            # Assemble diagnostic from result dict
            target_set = set(config.pilot.target_conditions)
            conditions_observed = result.get("conditions_observed", [])
            diagnostics = PilotDiagnostics(
                trials_completed=result.get("trials_completed", 0),
                trials_with_stimulus_match=result.get("trials_with_stimulus_match", 0),
                conditions_observed=conditions_observed,
                conditions_missing=sorted(target_set - set(conditions_observed)),
                selector_results=result.get("selector_results", {}),
                phase_results=result.get("phase_results", {}),
                dom_snapshots=(
                    [{"trigger": "after_navigation", "html": after_nav_snap}]
                    + result.get("dom_snapshots", [])
                ),
                anomalies=result.get("anomalies", []),
                trial_log=result.get("trial_log", []),
            )
            evidence.append(
                f"attempt_{attempt + 1}: trials={diagnostics.trials_with_stimulus_match}, "
                f"conditions={conditions_observed}, missing={diagnostics.conditions_missing}"
            )
            passed, reasons = _pilot_passed(diagnostics, config)

            if passed:
                # SUCCESS — splice accumulator state into partial
                partial.setdefault('navigation', {})['phases'] = accumulated_phases
                for stim_id, new_sel in accumulated_stim_overrides.items():
                    for s in partial.get('stimuli', []):
                        if s.get('id') == stim_id:
                            s.setdefault('detection', {})['selector'] = new_sel
                _save_diagnostic(diagnostics, taskcards_dir, label)
                _save_pilot_observations(diagnostics, taskcards_dir, label)
                # A2: check the card's phase predicates against the pilot's
                # recorded DOMs (hard-fail only on complete-fires-on-trial-DOM).
                _trial_html = next(
                    (s.get("html", "") for s in (diagnostics.dom_snapshots or [])
                     if s.get("trigger") == "first_stimulus_match"),
                    next((s.get("html", "") for s in (diagnostics.dom_snapshots or [])
                          if s.get("trigger") != "after_navigation"), ""),
                )
                _hard_fail, _pred_warnings = await _validate_phase_predicates(
                    session, config.runtime.phase_detection, _trial_html, after_nav_snap,
                )
                if _hard_fail:
                    raise PilotValidationError(
                        f"Stage-6 phase-predicate gate: {_hard_fail}"
                    )
                evidence.extend(_pred_warnings)
                if _pred_warnings:
                    _pmd = Path(taskcards_dir) / label / "pilot.md"
                    with open(_pmd, "a") as _fh:
                        _fh.write(
                            "\n### Phase-predicate warnings\n"
                            + "\n".join(f"- {w}" for w in _pred_warnings) + "\n"
                        )
                if attempt == 0 and not accumulated_stim_overrides:
                    inference = (
                        f"Pilot passed first attempt: "
                        f"{diagnostics.trials_with_stimulus_match} trials, "
                        f"conditions {conditions_observed} all observed."
                    )
                else:
                    inference = (
                        f"Pilot passed after {nav_refinement_count} navigation "
                        f"refinement(s), {stim_refinement_count} selector update(s): "
                        f"{diagnostics.trials_with_stimulus_match} trials, "
                        f"conditions {conditions_observed}."
                    )
                # C3: prove the finalized nav is executor-replayable (fresh browser).
                # A gate failure feeds the replay's stuck DOM back into the
                # walker's refinement proposer for a bounded number of extra
                # single-phase rounds (surfaced by held-out flanker: Stage 1
                # omitted advance_keys, leaving a final "press enter to begin"
                # interstitial that neither nav phases nor advance-key presses
                # crossed — one proposed keypress phase heals it replayably).
                from experiment_bot.core.stimulus import StimulusLookup as _StimulusLookup
                replay_diffs: list[str] = []
                for replay_round in range(1 + _REPLAY_REFINE_BUDGET):
                    replay_config = _partial_to_pilot_config(partial)
                    reached, replay_dom = await replay_navigation(
                        bundle.url, replay_config.navigation, _StimulusLookup(replay_config),
                        advance_behavior=replay_config.runtime.advance_behavior,
                        headless=headless, viewport=replay_config.runtime.timing.viewport,
                    )
                    if reached:
                        break
                    if replay_round == _REPLAY_REFINE_BUDGET:
                        raise PilotValidationError(
                            "Stage-6 replay gate: finalized navigation.phases did not reach "
                            "trial rendering in a fresh-browser executor-shaped replay, and "
                            f"{_REPLAY_REFINE_BUDGET} replay-refine round(s) did not heal it. "
                            "See pilot.md."
                        )
                    try:
                        new_phase = await _propose_next_phase(
                            client, replay_dom, accumulated_phases, replay_diffs,
                        )
                    except Exception as e:  # noqa: BLE001 — budget-bounded; fall through to gate error
                        logger.warning("replay-refine proposal failed: %s", e)
                        continue
                    accumulated_phases.append(new_phase)
                    partial.setdefault('navigation', {})['phases'] = accumulated_phases
                    diff_text = (
                        f"# Replay-gate refinement round {replay_round + 1}\n"
                        f"# (appended after the live pilot passed; replay could not reach trials)\n\n"
                        + json.dumps(new_phase, indent=2)
                    )
                    replay_diffs.append(diff_text)
                    _diff_dir = Path(taskcards_dir) / label
                    _diff_dir.mkdir(parents=True, exist_ok=True)
                    (_diff_dir / f"pilot_replay_refinement_{replay_round + 1}.diff").write_text(diff_text)
                    evidence.append(
                        f"replay_refine_{replay_round + 1}: appended phase "
                        f"{new_phase.get('phase', '?')!r} ({new_phase.get('action', '?')})"
                    )
                # Wave A1: data-capture gate — after the replay gate passes,
                # exercise the card's capture config on the walker's live
                # session (which has completed pilot trials). See
                # _validate_data_capture for the mid-pilot variant rationale.
                await _validate_data_capture(
                    session, config.runtime.data_capture, evidence,
                )
                return partial, ReasoningStep(
                    step="stage6_pilot",
                    inference=inference,
                    evidence_lines=evidence,
                    confidence="high",
                )

            history.append(f"Attempt {attempt + 1}: " + "; ".join(reasons))
            logger.warning("Pilot attempt %d failed: %s", attempt + 1, "; ".join(reasons))

            # Stuck-detection: 3 consecutive identical non-empty fingerprints.
            # SP15 raised the threshold from 2 to 3: under the persistent-session
            # walker, the LLM's first refinement after a stuck-DOM may "succeed"
            # at session.try_phase (no Playwright error) but not actually advance
            # the DOM (e.g., keypress Enter on a screen with a Next button — the
            # press fires but the page ignores it). Three identical fingerprints
            # gives the LLM ONE more chance after seeing its own no-op diff in
            # prior_diffs to try a different action.
            fp = diagnostics.dom_fingerprint
            fingerprint_history.append(fp)
            if (
                len(fingerprint_history) >= 3
                and fingerprint_history[-1]
                and fingerprint_history[-1] == fingerprint_history[-2] == fingerprint_history[-3]
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

            # Decide refinement type
            current_dom = diagnostics.dom_snapshots[-1].get("html", "") if diagnostics.dom_snapshots else ""
            if diagnostics.trials_completed > 0 and diagnostics.trials_with_stimulus_match == 0:
                # Stimulus refinement: trials rendering but no selector matches
                try:
                    update = await _propose_stimulus_update(
                        client, current_dom, partial.get('stimuli', []), prior_diffs,
                    )
                    stim_id = update.get('stim_id')
                    new_sel = update.get('new_selector')
                    new_method = update.get('detection_method', 'dom_query')
                    if stim_id and new_sel:
                        lookup.update_selector(stim_id, new_sel, new_method)
                        accumulated_stim_overrides[stim_id] = new_sel
                        stim_refinement_count += 1
                        prior_diffs.append(f"Stim update {stim_id}: selector={new_sel[:120]}")
                except Exception as e:
                    logger.warning("_propose_stimulus_update failed: %s — skipping", e)
                    prior_diffs.append(f"(failed) Stim update error: {e}")
            else:
                # Navigation refinement: bot stuck on a pre-trial screen
                try:
                    new_phase_dict = await _propose_next_phase(
                        client, current_dom, accumulated_phases, prior_diffs,
                    )
                    from experiment_bot.core.config import NavigationPhase as _NavPhase
                    # Defensive fill for missing optional fields
                    new_phase_dict.setdefault('steps', [])
                    new_phase_dict.setdefault('key', '')
                    new_phase_dict.setdefault('target', '')
                    new_phase_dict.setdefault('duration_ms', 0)
                    new_phase_dict.setdefault('phase', '')
                    # Probe the live trial stimulus before/after so we can tell a
                    # genuine nav advance from a demo-trial RESPONSE (which must NOT
                    # be baked into navigation.phases — that produces executor-
                    # unreplayable cards). Spec C2 / audit genbottle-001.
                    before_probe = await session.probe_stimulus(lookup)
                    new_phase = _NavPhase.from_dict(new_phase_dict)
                    attempt_result = await session.try_phase(new_phase)
                    after_probe = await session.probe_stimulus(lookup)
                    response_keys = set((partial.get("task_specific", {}).get("key_map", {}) or {}).values())
                    from experiment_bot.reasoner.nav_classify import classify_phase_outcome
                    outcome = classify_phase_outcome(
                        before_match=before_probe.match, after_match=after_probe.match,
                        phase=new_phase_dict, response_keys=response_keys,
                    )
                    if attempt_result.success and outcome == "nav_advance":
                        accumulated_phases.append(new_phase_dict)
                        partial.setdefault('navigation', {})['phases'] = accumulated_phases
                        nav_refinement_count += 1
                        prior_diffs.append(f"Nav phase {nav_refinement_count}: {new_phase_dict}")
                        if save_partial is not None:
                            save_partial(partial)
                    elif attempt_result.success and outcome == "trial_response":
                        # Executed a demo-trial response, not a nav advance: do NOT
                        # append to navigation.phases. The action still advanced the
                        # pilot through a practice trial; the loop continues.
                        prior_diffs.append(f"(trial-response, not nav) {new_phase_dict}")
                    else:
                        prior_diffs.append(
                            f"(failed) Nav phase: {new_phase_dict}; error={attempt_result.error}"
                        )
                    # Persist this refinement's proposed phase + outcome for
                    # post-hoc debugging. One file per refinement attempt.
                    _diff_dir = Path(taskcards_dir) / label
                    _diff_dir.mkdir(parents=True, exist_ok=True)
                    _diff_path = _diff_dir / f"pilot_refinement_{attempt + 1}.diff"
                    _diff_path.write_text(
                        f"# Attempt {attempt + 1} navigation refinement\n"
                        f"# outcome={outcome}\n"
                        f"# success={attempt_result.success}\n"
                        f"# error={attempt_result.error}\n\n"
                        + json.dumps(new_phase_dict, indent=2)
                    )
                except Exception as e:
                    logger.warning("_propose_next_phase failed: %s — skipping", e)
                    prior_diffs.append(f"(failed) Nav phase error: {e}")
