from __future__ import annotations
import copy
import json
import logging
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import _extract_json
from experiment_bot.reasoner.validate import (
    Stage2SchemaError, validate_stage2_schema,
)
from experiment_bot.taskcard.types import ReasoningStep

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# How many times Stage 2 self-corrects via validator-feedback before
# the pipeline gives up. The first attempt is the initial generation;
# each retry feeds the validator's error list back as a refinement
# turn so the LLM can fix the schema violations on its own.
STAGE2_MAX_REFINEMENTS = 3


async def run_stage2(client: LLMClient, partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 2: behavioral parameters as point estimates with rationale.

    After each LLM call, the output's schema is validated against
    schema.json (temporal-effect mechanism shapes, between-subject
    jitter shape). If validation fails, the validator's error list is
    appended to the user prompt as a refinement turn and Stage 2 is
    re-called; this self-corrects the LLM's output without prescribing
    paradigm-specific content. After STAGE2_MAX_REFINEMENTS attempts,
    the last validation error propagates.
    """
    from experiment_bot.effects.registry import EFFECT_REGISTRY

    system = (PROMPTS_DIR / "stage2_behavioral.md").read_text()

    # The effect catalog injected into the prompt is the bot's full
    # standard library — universal mechanisms only. The Reasoner's job
    # is to translate the literature for THIS task into mechanism
    # configs (modulation tables, trigger lists, magnitudes), enabling
    # only the mechanisms the literature for this paradigm actually
    # documents. Effects whose literature evidence is absent should be
    # left disabled.
    eligible_descriptions = []
    for name, et in EFFECT_REGISTRY.items():
        if et.handler is None:
            continue
        param_list = ", ".join(
            f"{k}: {v.__name__}" for k, v in et.params.items()
        ) if et.params else "(see schema)"
        eligible_descriptions.append(f"- `{name}` (params: {{{param_list}}})")

    paradigm_classes = partial.get("task", {}).get("paradigm_classes", []) or ["speeded_choice"]
    user = (
        "## Stage 1 output (structural)\n"
        + json.dumps(partial, indent=2)
        + "\n\n## Available temporal-effect mechanisms (configure per task from literature)\n"
        + f"paradigm_classes: {paradigm_classes}\n\n"
        + "These are GENERIC mechanisms — the bot's library does not name "
        "any paradigm-specific effect. For each mechanism below, decide "
        "from the literature for THIS paradigm whether it applies, and if "
        "so, configure it (modulation_table entries, trigger lists, "
        "magnitudes) using citations from primary studies. Leave a "
        "mechanism disabled when the literature for this paradigm does "
        "not document the corresponding behavior.\n\n"
        + "\n".join(eligible_descriptions)
        + "\n\nProduce the behavioral parameters as instructed in the system "
        "prompt. Enable mechanisms ONLY when supported by the literature."
    )
    user_msg = user
    n_refinements = 0
    for attempt in range(1, STAGE2_MAX_REFINEMENTS + 1):
        resp = await client.complete(system=system, user=user_msg, output_format="json")
        # Parse step: refinement turns sometimes produce malformed JSON
        # (e.g., truncated output, missing comma). Treat parse errors the
        # same way as schema errors — feed the parser's message back to
        # the LLM and try again, within the same refinement budget.
        try:
            behavioral = json.loads(_extract_json(resp.text))
        except json.JSONDecodeError as e:
            n_refinements = attempt
            if attempt == STAGE2_MAX_REFINEMENTS:
                logger.warning(
                    "Stage 2 still produced unparseable JSON after %d "
                    "attempts; surfacing error.", attempt,
                )
                raise
            logger.info(
                "Stage 2 attempt %d returned non-parseable JSON; refining. "
                "Error: %s", attempt, e,
            )
            user_msg = (
                user
                + "\n\n## Parse error from previous attempt\n"
                "Your previous output could not be parsed as JSON: "
                f"`{e.msg}` at line {e.lineno}, column {e.colno}. "
                "Regenerate the complete Stage 2 JSON, ensuring valid "
                "syntax (no trailing commas, all strings closed, no "
                "unterminated objects/arrays).\n"
            )
            continue
        candidate = copy.deepcopy(partial)
        candidate["response_distributions"] = behavioral["response_distributions"]
        candidate["temporal_effects"] = behavioral.get("temporal_effects", {})
        candidate["between_subject_jitter"] = behavioral.get("between_subject_jitter", {})
        try:
            validate_stage2_schema(candidate)
        except Stage2SchemaError as e:
            n_refinements = attempt
            if attempt == STAGE2_MAX_REFINEMENTS:
                logger.warning(
                    "Stage 2 still has schema violations after %d refinement "
                    "attempts; surfacing error.", attempt,
                )
                raise
            logger.info(
                "Stage 2 attempt %d failed schema validation; refining. "
                "Errors:\n%s", attempt, str(e),
            )
            user_msg = (
                user
                + "\n\n## Validation errors from previous attempt\n"
                "Your previous output failed runtime-schema validation. The "
                "executor reads specific field names and enum values; using "
                "alternative names or compounds means the configured effect "
                "will not fire at runtime. Fix every error below and "
                "regenerate the full Stage 2 JSON. Do not change which "
                "mechanisms you enable; only the SHAPE of each enabled "
                "mechanism's value object.\n\n"
                + str(e)
            )
            continue
        # Validation passed.
        break

    result = candidate
    om = behavioral.get("performance_omission_rate", {})
    result.setdefault("performance", {})["omission_rate"] = om

    n_conditions = len(behavioral.get("response_distributions", {}))
    n_effects_enabled = sum(
        1 for e in behavioral.get("temporal_effects", {}).values()
        if e.get("value", {}).get("enabled")
    )
    inference = (
        f"Produced ex-Gaussian (mu/sigma/tau) parameters for {n_conditions} "
        f"conditions; enabled {n_effects_enabled} temporal effects."
    )
    if n_refinements:
        inference += f" Self-corrected after {n_refinements} schema-validation refinement(s)."
    step = ReasoningStep(
        step="stage2_behavioral",
        inference=inference,
        evidence_lines=[],
        confidence="medium",
    )
    return result, step
