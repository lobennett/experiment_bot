from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal


SourceLabel = Literal[
    "window_correctresponse",
    "dom_inference",
    "screenshot_inference",
    "llm_failure_fallback",
]


@dataclass
class KeyMappingDirective:
    """Output of SessionAgent.resolve_key_mapping.

    mapping: condition name → key string ready for Playwright key.press()
    source: which inference path produced the mapping
    confidence: LLM-self-reported 0.0-1.0
    raw_llm_response: full LLM text (for audit / debugging)
    elapsed_ms: wall time from probe start to directive ready
    """
    mapping: dict[str, str]
    source: SourceLabel
    confidence: float
    raw_llm_response: str
    elapsed_ms: float

    def to_dict(self) -> dict:
        return asdict(self)
