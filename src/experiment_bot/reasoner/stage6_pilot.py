"""Stage 6: live-DOM pilot validation of the Reasoner's structural output.

Runs the partial TaskCard against the live experiment URL via Playwright,
captures diagnostics (selector match rates, phase firings, DOM snapshots,
condition coverage), and on failure either refines the partial via Claude
or hard-fails — depending on `max_retries`.

The pilot exercises only structural fields (stimuli, navigation,
runtime). It does not sample RTs or check temporal effects. Pilot runs
between Stage 5 (sensitivity) and TaskCard finalization, so refinements
target the same fields Stage 1 produced.
"""
from __future__ import annotations

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
from experiment_bot.core.pilot_session import PilotSession
from experiment_bot.core.stimulus import StimulusLookup
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
`performance.accuracy/omission_rate` — those are set by other Reasoner stages
and the pilot's evidence does not bear on them.

## Navigation phase JSON schema (CRITICAL — get this right)

The navigator consumes a FLAT phase shape. Top-level fields are `action`,
`target`, `key`, `duration_ms`, `steps`, plus an informational `phase` label.
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
`target`, `key`, `duration_ms`, `steps`, plus an informational `phase` label.
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

    async with PilotSession(headless=headless, viewport=config.runtime.timing.viewport) as session:
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
                return partial, ReasoningStep(
                    step="stage6_pilot",
                    inference=inference,
                    evidence_lines=evidence,
                    confidence="high",
                )

            history.append(f"Attempt {attempt + 1}: " + "; ".join(reasons))
            logger.warning("Pilot attempt %d failed: %s", attempt + 1, "; ".join(reasons))

            # Stuck-detection: 2 consecutive identical non-empty fingerprints
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
                    new_phase = _NavPhase.from_dict(new_phase_dict)
                    attempt_result = await session.try_phase(new_phase)
                    if attempt_result.success:
                        accumulated_phases.append(new_phase_dict)
                        partial.setdefault('navigation', {})['phases'] = accumulated_phases
                        nav_refinement_count += 1
                        prior_diffs.append(f"Nav phase {nav_refinement_count}: {new_phase_dict}")
                        if save_partial is not None:
                            save_partial(partial)
                    else:
                        prior_diffs.append(
                            f"(failed) Nav phase: {new_phase_dict}; error={attempt_result.error}"
                        )
                except Exception as e:
                    logger.warning("_propose_next_phase failed: %s — skipping", e)
                    prior_diffs.append(f"(failed) Nav phase error: {e}")
