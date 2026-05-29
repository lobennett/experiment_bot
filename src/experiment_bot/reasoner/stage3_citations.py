from __future__ import annotations
import copy
import json
import logging
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.parse_retry import parse_with_retry
from experiment_bot.taskcard.types import ReasoningStep

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _enumerate_parameters(partial: dict) -> list[str]:
    """Return paths like 'response_distributions/<condition>/mu'.

    The 'enabled' subkey of temporal effects is excluded — it's a boolean,
    not a numeric parameter that needs literature grounding.
    """
    paths = []
    for cond, dist in partial.get("response_distributions", {}).items():
        for p in dist.get("value", {}):
            paths.append(f"response_distributions/{cond}/{p}")
    for eff, body in partial.get("temporal_effects", {}).items():
        for p in body.get("value", {}):
            if p == "enabled":
                continue
            paths.append(f"temporal_effects/{eff}/{p}")
    bsj = partial.get("between_subject_jitter", {}).get("value", {})
    for p in bsj:
        paths.append(f"between_subject_jitter/_/{p}")
    return paths


async def run_stage3(client: LLMClient, partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 3: citations + literature_range + between_subject_sd per parameter (batched)."""
    system = (PROMPTS_DIR / "stage3_citations.md").read_text()
    paths = _enumerate_parameters(partial)
    user = (
        "## Parameters needing citations\n"
        + json.dumps({"paths": paths, "current_values": partial}, indent=2)
    )
    citations_map = await parse_with_retry(
        client, system=system, user=user, stage_name="stage3_citations",
    )

    result = copy.deepcopy(partial)
    for path, body in citations_map.items():
        # Citation-map keys are "<section>/<key>/<param>" for
        # response_distributions and temporal_effects, but
        # between_subject_jitter is keyed by section alone. Parse leniently:
        # the LLM sometimes emits a short or malformed path; skip those with a
        # warning rather than crashing the whole pipeline on one bad citation
        # (mirrors the Stage 4 defensive philosophy).
        parts = path.split("/")
        section = parts[0]
        key = parts[1] if len(parts) > 1 else None
        if section == "response_distributions":
            if key is None or key not in result.get("response_distributions", {}):
                logger.warning("stage3: skipping citation path %r (no matching response_distributions key)", path)
                continue
            target = result["response_distributions"][key]
        elif section == "temporal_effects":
            if key is None or key not in result.get("temporal_effects", {}):
                logger.warning("stage3: skipping citation path %r (no matching temporal_effects key)", path)
                continue
            target = result["temporal_effects"][key]
        elif section == "between_subject_jitter":
            target = result.get("between_subject_jitter")
            if not isinstance(target, dict):
                logger.warning("stage3: skipping citation path %r (between_subject_jitter not a dict)", path)
                continue
        else:
            logger.warning("stage3: skipping citation path %r (unknown section %r)", path, section)
            continue
        # Merge — accumulate citations across params for the same key, but
        # de-duplicate by (DOI, quote) so that different quotes from the same
        # paper (e.g. supporting different sub-parameters) are both preserved.
        existing_keys = {
            (c.get("doi"), c.get("quote")) for c in target.get("citations", [])
        }
        for new_cit in body.get("citations", []):
            key_pair = (new_cit.get("doi"), new_cit.get("quote"))
            if key_pair not in existing_keys:
                target.setdefault("citations", []).append(new_cit)
                existing_keys.add(key_pair)
        if body.get("literature_range") is not None:
            target.setdefault("literature_range", {}).update(body["literature_range"])
        if body.get("between_subject_sd") is not None:
            target.setdefault("between_subject_sd", {}).update(body["between_subject_sd"])

    n_cits = 0
    for section in ("response_distributions", "temporal_effects"):
        for v in result.get(section, {}).values():
            n_cits += len(v.get("citations", []))
    n_cits += len(result.get("between_subject_jitter", {}).get("citations", []))

    step = ReasoningStep(
        step="stage3_citations",
        inference=(
            f"Produced {n_cits} citations across {len(paths)} numeric parameters "
            f"with literature_range and between_subject_sd."
        ),
        evidence_lines=[],
        confidence="medium",
    )
    return result, step
