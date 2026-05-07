from __future__ import annotations
import asyncio
import json
import logging
from typing import Literal
from experiment_bot.llm.protocol import LLMResponse

logger = logging.getLogger(__name__)


class ClaudeCLIClient:
    """LLM client that shells out to the `claude --print` CLI.

    Uses the user's existing Max subscription via `claude login`.
    No API key required.
    """

    def __init__(
        self,
        claude_binary: str = "claude",
        model: str = "claude-opus-4-7",
        timeout_s: float = 1200.0,
    ):
        self._binary = claude_binary
        self._model = model
        self._timeout_s = timeout_s

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
    ) -> LLMResponse:
        # Combine system + user; the CLI doesn't separate them. Convention:
        # prepend system as a labeled section so the model can find it.
        prompt = f"[SYSTEM]\n{system}\n[/SYSTEM]\n\n{user}"
        args = [
            self._binary,
            "--print",
            "--output-format",
            "json",
            "--model",
            self._model,
            prompt,
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"claude CLI timed out after {self._timeout_s}s")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            if "usage limit" in err.lower() or "quota" in err.lower():
                raise RuntimeError(f"claude CLI: usage limit reached: {err.strip()}")
            raise RuntimeError(f"claude CLI failed (rc={proc.returncode}): {err.strip()}")

        out = stdout.decode("utf-8", errors="replace")
        try:
            data = json.loads(out)
            text = data.get("result") or data.get("text") or ""
            stop_reason = data.get("stop_reason", "end_turn")
        except json.JSONDecodeError:
            text = out
            stop_reason = "end_turn"
        return LLMResponse(text=text, stop_reason=stop_reason)
