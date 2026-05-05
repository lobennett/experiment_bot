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
    from experiment_bot.effects.registry import eligible_effects, EFFECT_REGISTRY

    system = (PROMPTS_DIR / "stage2_behavioral.md").read_text()

    paradigm_classes = partial.get("task", {}).get("paradigm_classes", []) or ["speeded_choice"]
    eligible = eligible_effects(paradigm_classes)
    eligible_descriptions = []
    for name in sorted(eligible):
        et = EFFECT_REGISTRY[name]
        param_list = ", ".join(f"{k}: {v.__name__}" for k, v in et.params.items())
        eligible_descriptions.append(f"- `{name}` (params: {{{param_list}}})")

    user = (
        "## Stage 1 output (structural)\n"
        + json.dumps(partial, indent=2)
        + "\n\n## Effects applicable to this paradigm\n"
        + f"paradigm_classes: {paradigm_classes}\n"
        + "Eligible effects (universal + paradigm-specific):\n"
        + "\n".join(eligible_descriptions)
        + "\n\nProduce the behavioral parameters as instructed in the system "
        "prompt. Enable only effects empirically documented for this paradigm."
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
