from __future__ import annotations

import json
import logging
from pathlib import Path

from experiment_bot.core.config import SourceBundle, TaskConfig
from experiment_bot.core.pilot import PilotDiagnostics

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

REFINEMENT_PROMPT = """You previously generated a TaskConfig for this experiment. A pilot run tested your config against the live experiment. Below is the diagnostic report showing what worked and what didn't.

## Your Original Config
{config_json}

## Pilot Diagnostic Report
{diagnostic_report}

## Original Experiment Source
{source_summary}

## Instructions

Fix the config based on the diagnostic evidence:

1. For selectors that NEVER MATCHED: rewrite them using the actual DOM structure shown in the snapshots. The DOM snapshots show exactly what the experiment renders — write selectors that match this HTML.
2. For missing conditions: examine the DOM snapshots to understand how different conditions are rendered and write detection rules that distinguish them.
3. For phase detection expressions that never fired: check against the DOM and fix.
4. Do NOT change behavioral parameters (RT distributions, accuracy, temporal effects, jitter). Only fix structural/detection issues.
5. Update the pilot section if your understanding of the trial structure has changed.

Return the complete corrected config JSON."""


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
            logger.debug("Claude raw response (first 500 chars): %s", raw_text[:500])

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            try:
                data = json.loads(raw_text)
                return TaskConfig.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Attempt {attempts} failed to parse config: {e}")
                logger.debug("Full raw text that failed: %s", raw_text[:2000])
                if attempts > self._max_retries:
                    raise ValueError(f"Failed to get valid config after {attempts} attempts: {e}") from e

    async def refine(self, config: TaskConfig, diagnostics: PilotDiagnostics, bundle: SourceBundle) -> TaskConfig:
        """Send diagnostic report + original source to Claude for config refinement."""
        config_json = json.dumps(config.to_dict(), indent=2)
        diagnostic_report = diagnostics.to_report()

        source_parts = [f"## Page HTML\n{bundle.description_text[:5000]}"]
        for filename, content in bundle.source_files.items():
            source_parts.append(f"## File: {filename}\n{content[:30000]}")
        source_summary = "\n\n".join(source_parts)

        user_message = REFINEMENT_PROMPT.format(
            config_json=config_json,
            diagnostic_report=diagnostic_report,
            source_summary=source_summary,
        )

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=16384,
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        data = json.loads(raw_text)
        return TaskConfig.from_dict(data)
