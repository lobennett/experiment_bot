from __future__ import annotations
import copy
import json
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import _extract_json
from experiment_bot.taskcard.types import ReasoningStep

PROMPTS_DIR = Path(__file__).parent / "prompts"


async def run_stage5(client: LLMClient, partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 5: sensitivity tags per parameter."""
    system = (PROMPTS_DIR / "stage5_sensitivity.md").read_text()
    user = "## Behavioral parameters\n" + json.dumps(partial, indent=2)
    resp = await client.complete(system=system, user=user, output_format="json")
    tags_map = json.loads(_extract_json(resp.text))

    result = copy.deepcopy(partial)
    for path, level in tags_map.items():
        parts = path.split("/")
        if len(parts) == 3:
            section, key, param = parts
        elif len(parts) == 2:
            section, param = parts
            key = None
        else:
            continue  # malformed path; skip
        if section == "response_distributions":
            target = result.get("response_distributions", {}).get(key)
        elif section == "temporal_effects":
            target = result.get("temporal_effects", {}).get(key)
        elif section == "between_subject_jitter":
            target = result.get("between_subject_jitter")
        else:
            continue
        if target is None:
            continue
        # Initialize sensitivity to a dict if it isn't already (Task A1 supports
        # both string and dict forms for ParameterValue.sensitivity).
        existing = target.get("sensitivity")
        if not isinstance(existing, dict):
            target["sensitivity"] = {}
        target["sensitivity"][param] = level

    n_high = 0
    n_total = 0
    for section in ("response_distributions", "temporal_effects"):
        for v in result.get(section, {}).values():
            sens = v.get("sensitivity", {})
            if isinstance(sens, dict):
                n_total += len(sens)
                n_high += sum(1 for s in sens.values() if s == "high")
    bsj_sens = result.get("between_subject_jitter", {}).get("sensitivity", {})
    if isinstance(bsj_sens, dict):
        n_total += len(bsj_sens)
        n_high += sum(1 for s in bsj_sens.values() if s == "high")

    step = ReasoningStep(
        step="stage5_sensitivity",
        inference=f"Tagged sensitivity on {n_total} parameters; {n_high} are high-sensitivity.",
        evidence_lines=[],
        confidence="medium",
    )
    return result, step
