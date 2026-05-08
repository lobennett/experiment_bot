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


# Slot-extraction rule for refinement preservation. Each top-level path
# in Stage2SchemaError.errors collapses to one of these slot patterns;
# refinement re-prompts only the failing slots and locks the rest.
# `response_distributions` is prospective: validate.py does not yet emit
# error paths under this prefix, but the rule is in place so adding
# response_distributions schema validation later doesn't require
# touching the slot extractor.
_SLOT_RULES: list[tuple[str, int]] = [
    # (path-prefix-after-split, depth-of-slot-segments)
    ("temporal_effects", 2),       # temporal_effects.<mech>
    ("performance", 2),            # performance.<sub>
    ("task_specific", 2),          # task_specific.<key>
    ("response_distributions", 2), # response_distributions.<cond> (prospective)
    ("between_subject_jitter", 1), # between_subject_jitter (whole)
]


def _extract_failing_slots(errors: list[tuple[str, str]]) -> list[str]:
    """Map a list of (path, message) validation errors to the deduped,
    sorted set of slot keys whose contents need regeneration.

    See the SP4a spec's slot-extraction rule. Multiple errors within
    one slot collapse to a single slot entry.
    """
    slots: set[str] = set()
    for path, _ in errors:
        segments = path.split(".")
        if not segments:
            continue
        head = segments[0]
        depth = next(
            (d for prefix, d in _SLOT_RULES if prefix == head),
            1,  # default: collapse to top-level segment
        )
        slot = ".".join(segments[:depth])
        slots.add(slot)
    return sorted(slots)


def _render_slot_refinement_prompt(
    partial: dict,
    failing_slots: list[str],
    errors: list[tuple[str, str]],
) -> str:
    """Build the refinement prompt for slot-locked refinement.

    Sections:
    1. Previously-validated context (locked): every top-level partial
       field, except those listed in failing_slots, serialized as JSON.
       The LLM is instructed not to modify these.
    2. Failing slots: one line per slot, with the validation error
       messages that surfaced for that slot.
    3. Schema reminder: re-iterates that the prompt's existing
       'Concrete shape examples' section is the canonical source for
       the failing slots' shapes.
    """
    locked_partial = _strip_failing_slots(partial, failing_slots)
    locked_json = json.dumps(locked_partial, indent=2, sort_keys=True)

    error_lines = []
    for slot in failing_slots:
        slot_errors = [
            (p, m) for p, m in errors
            if p.startswith(slot + ".") or p == slot
        ]
        for path, msg in slot_errors:
            error_lines.append(f"  - {path}: {msg}")

    return (
        "## Previously-validated context (do NOT modify)\n"
        "These fields already passed schema validation. Treat them as fixed; "
        "do NOT regenerate them in your response. Your response should "
        "contain ONLY the failing slots listed below.\n\n"
        "```json\n" + locked_json + "\n```\n\n"
        "## Failing slots to fix\n"
        "Regenerate these top-level slots (and only these slots) in your "
        "response. The schema validator's diagnostics for each:\n\n"
        + "\n".join(f"### {slot}" for slot in failing_slots)
        + "\n\nValidation errors:\n"
        + "\n".join(error_lines)
        + "\n\n## Schema reminder\n"
        "The shape requirements for each failing slot are documented in "
        "the 'Concrete shape examples' section of the system prompt. "
        "Use the schema-example blocks verbatim as templates; do NOT "
        "emit any of the schema-anti-example shapes.\n\n"
        "Return a JSON object containing only the failing slots, each "
        "at the same nesting level it appears in the partial above:\n\n"
        "```json\n"
        "{\n"
        + ",\n".join(f'  "{slot.split(".")[0]}": {{ ... }}' for slot in failing_slots[:1])
        + "\n}\n"
        "```\n"
    )


def _strip_failing_slots(partial: dict, failing_slots: list[str]) -> dict:
    """Return a deep copy of partial with each failing slot replaced
    by a placeholder marker (so the LLM sees the slot's location
    without the previous failed content)."""
    out = copy.deepcopy(partial)
    for slot in failing_slots:
        segments = slot.split(".")
        node = out
        for k in segments[:-1]:
            if k not in node or not isinstance(node[k], dict):
                # Slot not present in partial — nothing to strip.
                node = None
                break
            node = node[k]
        if node is None:
            continue
        last = segments[-1]
        if last in node:
            node[last] = "<<TO BE REGENERATED — see failing slots below>>"
    return out


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
    last_errors: list[tuple[str, str]] = []
    candidate: dict | None = None
    # Tracks whether the prompt we just sent was a slot-locked
    # refinement. If True, the response contains ONLY the failing
    # slots; otherwise it's a full Stage 2 output. JSON parse errors
    # always re-prompt with the full Stage 2 prompt + parse-error
    # append (not slot-locked), so this flag resets to False when we
    # take the parse-error retry path.
    awaiting_slot_refinement = False
    for attempt in range(1, STAGE2_MAX_REFINEMENTS + 1):
        resp = await client.complete(system=system, user=user_msg, output_format="json")
        # Parse step: refinement turns sometimes produce malformed JSON
        # (e.g., truncated output, missing comma). Treat parse errors the
        # same way as schema errors — feed the parser's message back to
        # the LLM and try again, within the same refinement budget.
        try:
            response_json = json.loads(_extract_json(resp.text))
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
            # Parse-error retry sends the FULL prompt, so the next
            # response is a full Stage 2 output, not a slot refinement.
            awaiting_slot_refinement = False
            continue

        if not awaiting_slot_refinement:
            # Full Stage 2 output: build the full candidate partial.
            candidate = copy.deepcopy(partial)
            candidate["response_distributions"] = response_json["response_distributions"]
            candidate["temporal_effects"] = response_json.get("temporal_effects", {})
            candidate["between_subject_jitter"] = response_json.get("between_subject_jitter", {})
            # performance_omission_rate is folded back into performance
            # block (existing convention).
            om = response_json.get("performance_omission_rate", {})
            candidate.setdefault("performance", {})["omission_rate"] = om
        else:
            # Refinement pass: response contains ONLY the failing slots.
            # Merge each into the previous candidate. If the LLM omits a
            # slot from its response, .get() resolves to None and the
            # next validation surfaces "None is not of type ..." — the
            # LLM then sees a different error than the original. A
            # future improvement (Tier 2 backlog) is to detect omitted
            # slots before merge and surface a clearer "slot omitted"
            # error; for SP4a the 3-attempt budget bounds the cost.
            assert candidate is not None
            for slot in _extract_failing_slots(last_errors):
                head, _, sub = slot.partition(".")
                if sub:
                    candidate.setdefault(head, {})[sub] = response_json.get(head, {}).get(sub)
                else:
                    candidate[head] = response_json.get(head)

        try:
            validate_stage2_schema(candidate)
            # Validation passed.
            break
        except Stage2SchemaError as e:
            n_refinements = attempt
            last_errors = e.errors
            if attempt == STAGE2_MAX_REFINEMENTS:
                logger.warning(
                    "Stage 2 still has schema violations after %d refinement "
                    "attempts; surfacing error.", attempt,
                )
                raise
            failing_slots = _extract_failing_slots(e.errors)
            logger.info(
                "Stage 2 attempt %d failed schema validation; refining "
                "%d slot(s): %s. Errors:\n%s",
                attempt, len(failing_slots), failing_slots, str(e),
            )
            user_msg = _render_slot_refinement_prompt(
                candidate, failing_slots, e.errors,
            )
            awaiting_slot_refinement = True
            continue

    result = candidate
    n_conditions = len(candidate.get("response_distributions", {}))
    n_effects_enabled = sum(
        1 for e in candidate.get("temporal_effects", {}).values()
        if (e.get("value", {}) if isinstance(e.get("value"), dict) else {}).get("enabled")
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
