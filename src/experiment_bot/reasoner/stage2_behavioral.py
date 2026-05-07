from __future__ import annotations
import copy
import json
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import _extract_json
from experiment_bot.taskcard.types import ReasoningStep

PROMPTS_DIR = Path(__file__).parent / "prompts"


async def run_stage2(client: LLMClient, partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 2: behavioral parameters as point estimates with rationale."""
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
        "any paradigm-specific effect. Configure the mechanisms that the "
        "literature for THIS paradigm documents (e.g. for Stroop you would "
        "configure `lag1_pair_modulation` with a CSE-style modulation table; "
        "for stop-signal you would configure `post_event_slowing` with "
        "interrupt + error triggers). Leave a mechanism disabled if the "
        "literature for this paradigm does not document it.\n\n"
        + "\n".join(eligible_descriptions)
        + "\n\nProduce the behavioral parameters as instructed in the system "
        "prompt. Enable mechanisms ONLY when supported by the literature."
    )
    resp = await client.complete(system=system, user=user, output_format="json")
    behavioral = json.loads(_extract_json(resp.text))

    result = copy.deepcopy(partial)
    result["response_distributions"] = behavioral["response_distributions"]
    result["temporal_effects"] = behavioral.get("temporal_effects", {})
    result["between_subject_jitter"] = behavioral.get("between_subject_jitter", {})
    om = behavioral.get("performance_omission_rate", {})
    result.setdefault("performance", {})["omission_rate"] = om

    n_conditions = len(behavioral.get("response_distributions", {}))
    n_effects_enabled = sum(
        1 for e in behavioral.get("temporal_effects", {}).values()
        if e.get("value", {}).get("enabled")
    )
    step = ReasoningStep(
        step="stage2_behavioral",
        inference=(
            f"Produced ex-Gaussian (mu/sigma/tau) parameters for {n_conditions} "
            f"conditions; enabled {n_effects_enabled} temporal effects."
        ),
        evidence_lines=[],
        confidence="medium",
    )
    return result, step
