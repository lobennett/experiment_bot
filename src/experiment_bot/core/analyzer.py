from __future__ import annotations

import json
import logging
from pathlib import Path

from experiment_bot.core.config import SourceBundle, TaskConfig

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class Analyzer:
    """Sends task source code to Claude Opus and returns a TaskConfig."""

    def __init__(self, client, model: str = "claude-opus-4-6", max_retries: int = 1):
        self._client = client
        self._model = model
        self._max_retries = max_retries
        self._system_prompt = (PROMPTS_DIR / "system.md").read_text()
        self._schema = json.loads((PROMPTS_DIR / "schema.json").read_text())

    def _build_user_message(self, bundle: SourceBundle) -> str:
        parts = [
            f"## Experiment URL: {bundle.url}",
        ]
        if bundle.hint:
            parts.append(f"## User Hint: {bundle.hint}")
        parts.append("")
        parts.append("## Page HTML")
        parts.append(bundle.description_text[:5000])
        parts.append("")

        for filename, content in bundle.source_files.items():
            parts.append(f"## File: {filename}")
            parts.append(content[:30000])
            parts.append("")

        parts.append("## Required Output Schema")
        parts.append(json.dumps(self._schema, indent=2))
        return "\n".join(parts)

    async def analyze(self, bundle: SourceBundle) -> TaskConfig:
        user_message = self._build_user_message(bundle)
        attempts = 0

        while attempts <= self._max_retries:
            attempts += 1
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=16384,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            try:
                data = json.loads(raw_text)
                return TaskConfig.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Attempt {attempts} failed to parse config: {e}")
                if attempts > self._max_retries:
                    raise ValueError(f"Failed to get valid config after {attempts} attempts: {e}") from e
