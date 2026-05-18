from __future__ import annotations
import logging
import re
from pathlib import Path
from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.taskcard.types import ReasoningStep
from experiment_bot.reasoner.normalize import normalize_partial
from experiment_bot.reasoner.parse_retry import parse_with_retry
from experiment_bot.reasoner.validate import (
    Stage1ValidationError,
    validate_stage1_output,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


REQUIRED_FIELDS_CHECKLIST = """
## REQUIRED fields you MUST populate

The Reasoner produces a TaskCard whose paradigm-agnostic parts the bot
library reads, while a platform driver handles all page-touching
concerns at runtime. Stage 1's job is to extract LITERATURE + paradigm
metadata + driver recommendation.

- `task.name` (string) — the paradigm's task name, lowercase snake_case.

- `task.paradigm_classes` (list of strings) — abstract classes the
  paradigm belongs to (open-ended vocabulary). Always include
  `"speeded_choice"` for any timed-decision task, plus one or more
  specific classes drawn from review-article terminology. See system.md
  "Paradigm classes" for examples.

- `stimuli` (list) — each stimulus needs `id` (snake_case identifier)
  and `condition` (literature-standard condition label, e.g.
  "congruent", "incongruent", "match_1back", "go", "stop"). The driver
  reads platform-specific stimulus details at runtime; Stage 1 only
  needs the abstract identifier + condition label.

- `performance.accuracy` (dict: condition → 0.0-1.0) — per-condition
  target accuracy from the literature.

- `performance.omission_rate` (dict: condition → 0.0-1.0) — optional
  per-condition omission rate.

- `recommended_driver` (string) — `"JsPsychDriver"`,
  `"CognitionRunDriver"`, `"PsychoJsDriver"`, or `"unknown"`. See the
  "Recommended driver" section of the system prompt.

- `pilot_validation_config` (object) — see existing pilot block. Stage
  6 uses this to drive a thin driver-based smoke confirming the
  TaskCard works end-to-end.

The Reasoner does NOT extract platform-specific JS (response_key_js,
stimulus.detection JS, navigation.phases, phase_detection,
attention_check, advance_behavior, data_capture). The driver handles
these at runtime.
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
        "Produce ONLY the paradigm-agnostic structural fields of a TaskConfig: "
        "task (with name and paradigm_classes), stimuli (id + condition for "
        "each), performance.accuracy/omission, recommended_driver, and a "
        "pilot_validation_config block. Do NOT produce response_distributions, "
        "temporal_effects, between_subject_jitter, or any behavioral parameters "
        "yet — those come in Stage 2. Do NOT extract platform-specific JS "
        "(response_key_js, navigation.phases, phase_detection, attention_check, "
        "advance_behavior, data_capture) — the driver handles those at runtime. "
        "Return JSON only."
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
        partial = await parse_with_retry(
            client, system=system_prompt, user=user, stage_name="stage1",
        )
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
