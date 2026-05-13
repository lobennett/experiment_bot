from __future__ import annotations

import base64
from typing import Literal

from experiment_bot.llm.protocol import LLMResponse


class ClaudeAPIClient:
    def __init__(self, client, model: str = "claude-opus-4-7"):
        self._client = client
        self._model = model

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
        images: list[bytes] | None = None,
    ) -> LLMResponse:
        # output_format is informational only for the API path; the prompt
        # itself instructs Claude to return JSON when desired.
        if images:
            content: list[dict] | str = [{"type": "text", "text": user}]
            for img in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(img).decode("ascii"),
                    },
                })
        else:
            content = user
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = resp.content[0].text
        return LLMResponse(text=text, stop_reason=getattr(resp, "stop_reason", "end_turn"))
