from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMClient

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


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
    parts.append(
        "Produce ONLY the structural fields of a TaskConfig: task, stimuli, "
        "navigation, runtime, task_specific (with key_map and trial_timing if "
        "applicable), performance.accuracy/omission, and a pilot_validation_config "
        "block. Do NOT produce response_distributions, temporal_effects, or any "
        "behavioral parameters yet — those come in stage 2. Return JSON only."
    )
    return "\n\n".join(parts)


async def run_stage1(client: LLMClient, bundle: SourceBundle) -> dict:
    """Stage 1 of the Reasoner: produce structural TaskConfig fields."""
    system_prompt = (PROMPTS_DIR / "system.md").read_text()
    user = _build_stage1_prompt(bundle)
    resp = await client.complete(system=system_prompt, user=user, output_format="json")
    return json.loads(_extract_json(resp.text))
