from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class LLMResponse:
    text: str
    stop_reason: str = "end_turn"


class LLMClient(Protocol):
    @property
    def model(self) -> str:
        ...

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
        images: list[bytes] | None = None,
    ) -> LLMResponse:
        ...
