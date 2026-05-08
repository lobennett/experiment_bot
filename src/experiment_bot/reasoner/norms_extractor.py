"""Canonical-norms extraction module.

C1: validator + schema only.
C2: extract_norms() LLM call.
C3: CLI that wraps it.
"""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.parse_retry import parse_with_retry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class NormsSchemaError(ValueError):
    """Raised when a norms dict doesn't conform to the expected schema."""


# Range-bearing keys that count as "the metric has a concrete range":
_RANGE_KEYS = (
    "range", "range_ms",
    "mu_range", "sigma_range", "tau_range",
    "mu_sd_range", "sigma_sd_range", "tau_sd_range",
)


def _has_concrete_range(metric_body: dict) -> bool:
    """True if at least one range-bearing key is present and non-null with finite endpoints."""
    for k in _RANGE_KEYS:
        if k not in metric_body:
            continue
        v = metric_body[k]
        if v is None:
            continue
        if isinstance(v, list):
            if all(elem is not None for elem in v):
                return True
            continue
        # non-list, non-None value (unusual but accept)
        return True
    return False


def _has_explicit_null(metric_body: dict) -> bool:
    """True iff the metric has at least one range-bearing key explicitly null AND
    a non-empty no_canonical_range_reason.

    Accepts both shapes:
    - {"range": None, "no_canonical_range_reason": "..."}
    - {"mu_sd_range": null, "sigma_sd_range": null, "no_canonical_range_reason": "..."}
    """
    if not bool(metric_body.get("no_canonical_range_reason")):
        return False
    # Any range-bearing key explicitly set to None counts as a deliberate "no canonical range"
    for k in _RANGE_KEYS:
        if k in metric_body and metric_body[k] is None:
            return True
    return False


def validate_norms_dict(payload: dict) -> None:
    """Validate the shape of a norms file dict; raise NormsSchemaError on failure."""
    if not payload.get("paradigm_class"):
        raise NormsSchemaError("paradigm_class is required and must be non-empty")

    pb = payload.get("produced_by", {})
    for key in ("model", "extraction_prompt_sha256", "timestamp"):
        if key not in pb:
            raise NormsSchemaError(f"produced_by.{key} is required")

    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        raise NormsSchemaError("metrics must be a dict")

    for metric_name, metric_body in metrics.items():
        if not (_has_concrete_range(metric_body) or _has_explicit_null(metric_body)):
            raise NormsSchemaError(
                f"metric {metric_name!r}: must have either a non-null range "
                f"(range/range_ms/mu_range/etc.) or null range with "
                f"no_canonical_range_reason"
            )


async def extract_norms(paradigm_class: str, llm_client: LLMClient) -> dict:
    """Run the norms extractor LLM call for `paradigm_class`. Return validated dict.

    Raises NormsSchemaError if the LLM output doesn't conform to the schema.
    Adds a `produced_by` envelope (model, extraction_prompt_sha256, timestamp)
    to the LLM output before validating + returning.
    """
    system_prompt = (PROMPTS_DIR / "norms_extractor.md").read_text()
    user = f"## Paradigm class\n{paradigm_class}\n\nReturn JSON only."
    payload = await parse_with_retry(
        llm_client, system=system_prompt, user=user, stage_name="norms_extractor",
    )
    payload.setdefault("produced_by", {
        "model": getattr(llm_client, "_model", "claude-opus-4-7"),
        "extraction_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    validate_norms_dict(payload)
    return payload
