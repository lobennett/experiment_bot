from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.taskcard.types import ReasoningStep
from experiment_bot.reasoner.normalize import normalize_partial
from experiment_bot.reasoner.validate import (
    Stage1ValidationError,
    validate_stage1_output,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


REQUIRED_FIELDS_CHECKLIST = """
## REQUIRED runtime fields you MUST populate

The executor will fail or skip steps if any of these are empty. Use the
experiment's source code to determine the right values; do NOT use generic
defaults.

- `runtime.advance_behavior.advance_keys` (list of key names) — keys the bot
  presses to advance instruction or feedback screens. Examples: `[" "]` for
  jsPsych Space-advance, `["Enter"]` for ExpFactory custom HTML. Required
  unless `feedback_selectors` is populated and covers all advance.

- `runtime.advance_behavior.feedback_fallback_keys` (list of key names) —
  fallback keys when no `feedback_selectors` button matches. Same conventions
  as `advance_keys`.

- `runtime.data_capture.method` (string: "js_expression" | "button_click" | "")
  — how the bot extracts the experiment's recorded data after completion.
  - "js_expression": provide `runtime.data_capture.expression` (a JS expression
    that returns the data as a string). Common: `jsPsych.data.get().json()` for
    jsPsych-7, `jsPsych.data.get().csv()` for csv. STOP-IT calls a custom
    `jsPsych.data.getInteractionData()`.
  - "button_click": provide `runtime.data_capture.button_selector` (a CSS
    selector for the "show data" button) and `result_selector` (selector for
    the result element). cognition.run typically uses `#data` as result.
  - "" only if the experiment has no native data save and the bot's bot_log.json
    is the only data source. Choose with caution.

- `runtime.data_capture.format` (string: "csv" | "tsv" | "json") — required
  alongside `method` when `method != ""`.

## REQUIRED task metadata

- `task.paradigm_classes` (list of strings) — abstract classes the paradigm
  belongs to. Open-ended vocabulary; used to filter which paradigm-specific
  sequential effects apply. Examples:
  - `["conflict"]` for Stroop, Flanker, Simon, Eriksen tasks (anything with a
    manipulable congruency dimension).
  - `["interrupt"]` for stop-signal, go/no-go tasks.
  - `["task_switching"]` for cued or alternating-runs paradigms.
  - `["memory"]` for n-back, list-recall paradigms.
  - `["speeded_choice"]` is the universal class — always include it for any
    speeded-response paradigm. (Most tasks should have at least one specific
    class plus `"speeded_choice"`.)
"""


def _extract_json(text: str) -> str:
    """Strip markdown fences and locate first JSON object."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        return text[first:last + 1]
    return text


def _build_stage1_prompt(bundle: SourceBundle) -> str:
    parts = [f"## Experiment URL: {bundle.url}"]
    if bundle.hint:
        parts.append(f"## Hint: {bundle.hint}")
    parts.append(f"## Page HTML\n{bundle.description_text[:5000]}")
    for fname, content in bundle.source_files.items():
        parts.append(f"## File: {fname}\n{content[:60000]}")
    parts.append(REQUIRED_FIELDS_CHECKLIST)
    parts.append(
        "Produce ONLY the structural fields of a TaskConfig: task, stimuli, "
        "navigation, runtime (with the REQUIRED fields above), task_specific "
        "(with key_map and trial_timing if applicable), performance.accuracy/"
        "omission, and a pilot_validation_config block. Do NOT produce "
        "response_distributions, temporal_effects, or any behavioral parameters "
        "yet — those come in stage 2. Return JSON only."
    )
    return "\n\n".join(parts)


async def run_stage1(
    client: LLMClient, bundle: SourceBundle, max_retries: int = 3,
) -> tuple[dict, ReasoningStep]:
    """Stage 1 of the Reasoner: produce structural TaskConfig fields.

    Returns (partial, ReasoningStep). The partial is normalized
    (key aliases mapped to canonical keys) before validation.

    On validation failure, re-prompts the LLM with the validator's error
    message attached (up to `max_retries` retries). Raises
    Stage1ValidationError if validation still fails after the retries are
    exhausted, with the accumulated error history included so the caller
    can see what the LLM kept getting wrong.
    """
    system_prompt = (PROMPTS_DIR / "system.md").read_text()
    base_user = _build_stage1_prompt(bundle)
    user = base_user
    errors: list[str] = []

    for attempt in range(max_retries + 1):
        resp = await client.complete(system=system_prompt, user=user, output_format="json")
        partial = json.loads(_extract_json(resp.text))
        normalized = normalize_partial(partial)
        try:
            validate_stage1_output(normalized)
        except Stage1ValidationError as e:
            errors.append(f"attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise Stage1ValidationError(
                    f"Stage 1 validation failed after {max_retries + 1} attempts. "
                    f"Errors:\n  - " + "\n  - ".join(errors)
                )
            user = (
                base_user
                + "\n\n## Previous attempts failed validation\n"
                + "Fix these issues and produce corrected JSON:\n  - "
                + "\n  - ".join(errors)
            )
            continue
        break

    n_stimuli = len(normalized.get("stimuli", []))
    task_name = normalized.get("task", {}).get("name", "?")
    inference = (
        f"Identified paradigm '{task_name}' with {n_stimuli} stimuli. "
        f"Source files: {', '.join(bundle.source_files.keys())[:200]}."
    )
    if errors:
        inference += f" Validator-retry resolved {len(errors)} prior failure(s)."
    step = ReasoningStep(
        step="stage1_structural",
        inference=inference,
        evidence_lines=list(bundle.source_files.keys())[:5],
        confidence="high",
    )
    return normalized, step
