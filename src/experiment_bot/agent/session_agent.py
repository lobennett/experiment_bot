"""SessionAgent — one-call-per-session LLM that resolves the key mapping.

Runs after navigation completes and before the trial loop begins. The
result is a KeyMappingDirective cached in the executor; per-trial
key resolution is a synchronous dict lookup, so paradigms with fast
stimulus presentation (stop-signal) are unaffected by LLM latency.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from playwright.async_api import Page

from experiment_bot.agent.page_probe import (
    capture_screenshot,
    snapshot_dom_summary,
    snapshot_window_globals,
)
from experiment_bot.agent.types import KeyMappingDirective
from experiment_bot.llm.protocol import LLMClient

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a cognitive-task analyst. Your job is to determine which keyboard key the page expects for each named condition in a cognitive psychology experiment.

You receive:
1. A TaskCard fragment with the claimed condition→key mapping (may be stale or counterbalanced wrong).
2. A snapshot of selected window.* properties from the live page.
3. A truncated DOM dump.
4. A screenshot of the current page state (the experiment is loaded but no stimulus is yet shown).

Return ONLY valid JSON in this exact shape (no markdown, no commentary):

{
  "mapping": {"<condition_name>": "<key>", ...},
  "source": "window_correctresponse" | "dom_inference" | "screenshot_inference",
  "confidence": <float 0.0-1.0>
}

Use the condition names exactly as they appear in the TaskCard fragment's key_map.
Use Playwright-friendly key strings ("ArrowLeft", "f", "j", " " for space, etc.).
Pick the "source" that best describes how you inferred the mapping:
- "window_correctresponse" if a window.* variable directly named the correct key
- "dom_inference" if the DOM made the mapping unambiguous
- "screenshot_inference" if the screenshot was load-bearing for the decision
"""


class SessionAgent:
    """One-call-per-session LLM agent for key-mapping resolution."""

    def __init__(self, client: LLMClient):
        self._client = client

    async def resolve_key_mapping(
        self,
        page: Page,
        task_card: dict,
        observed_stimulus_examples: list[dict] | None = None,
    ) -> KeyMappingDirective:
        """Probe the page, ask the LLM, return a directive.

        Never raises: any failure (LLM error, malformed JSON, missing
        fields) is caught and returns a directive with
        source='llm_failure_fallback' and mapping=task_card's static
        key_map. The executor's existing fallback chain still runs for
        any condition not in the returned mapping.
        """
        start = time.perf_counter()
        static_keymap = self._extract_static_keymap(task_card)

        globals_dict = await snapshot_window_globals(page)
        dom = await snapshot_dom_summary(page)
        screenshot = await capture_screenshot(page)

        user_prompt = self._build_user_prompt(
            task_card=task_card,
            globals_dict=globals_dict,
            dom=dom,
            observed_examples=observed_stimulus_examples,
        )

        try:
            resp = await self._client.complete(
                system=_SYSTEM_PROMPT,
                user=user_prompt,
                output_format="json",
                images=[screenshot] if screenshot else None,
            )
            parsed = self._parse_llm_response(resp.text)
            if parsed is None:
                logger.warning(
                    "SessionAgent: LLM response unparseable, using static "
                    "key_map fallback. Response head: %r",
                    resp.text[:200],
                )
                return KeyMappingDirective(
                    mapping=static_keymap,
                    source="llm_failure_fallback",
                    confidence=0.0,
                    raw_llm_response=resp.text,
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                )
            return KeyMappingDirective(
                mapping=parsed["mapping"],
                source=parsed["source"],
                confidence=parsed["confidence"],
                raw_llm_response=resp.text,
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:
            logger.warning("SessionAgent: LLM call failed: %s. Using static fallback.", e)
            return KeyMappingDirective(
                mapping=static_keymap,
                source="llm_failure_fallback",
                confidence=0.0,
                raw_llm_response=f"<exception: {e}>",
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )

    @staticmethod
    def _extract_static_keymap(task_card: dict) -> dict[str, str]:
        ts = task_card.get("task_specific") or {}
        keymap = ts.get("key_map") or {}
        # Filter out dynamic sentinels — the executor's existing
        # fallback chain handles those, but the SessionAgent's
        # "static fallback" should contain real key strings only.
        return {
            k: v for k, v in keymap.items()
            if isinstance(v, str) and v not in ("dynamic_mapping", "dynamic")
        }

    @staticmethod
    def _build_user_prompt(
        task_card: dict,
        globals_dict: dict,
        dom: str,
        observed_examples: list[dict] | None,
    ) -> str:
        ts = task_card.get("task_specific") or {}
        claimed_keymap = ts.get("key_map") or {}
        task_meta = task_card.get("task") or {}
        task_name = task_meta.get("name") or "<unknown>"

        sections = [
            f"# Task: {task_name}",
            "",
            "## Claimed condition→key mapping (from TaskCard)",
            "```json",
            json.dumps(claimed_keymap, indent=2),
            "```",
            "",
            "## Live window.* state (filtered to /response|correct|key|stim/i)",
            "```json",
            json.dumps(globals_dict, indent=2),
            "```",
            "",
            "## DOM snapshot (truncated)",
            "```html",
            dom,
            "```",
            "",
            "## Screenshot",
            "(attached as image)",
            "",
            "Return ONLY the JSON described in the system prompt.",
        ]
        if observed_examples:
            sections.insert(7, "## Observed stimulus examples")
            sections.insert(8, "```json")
            sections.insert(9, json.dumps(observed_examples, indent=2))
            sections.insert(10, "```")
            sections.insert(11, "")
        return "\n".join(sections)

    @staticmethod
    def _parse_llm_response(text: str) -> dict[str, Any] | None:
        """Parse the LLM's JSON output. Tolerates leading/trailing whitespace
        and markdown code fences. Returns None if mapping/source/confidence
        keys are missing or have the wrong types."""
        cleaned = text.strip()
        # Strip ```json ... ``` fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                cleaned = "\n".join(lines[1:-1])
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        mapping = data.get("mapping")
        source = data.get("source")
        confidence = data.get("confidence")
        if not isinstance(mapping, dict):
            return None
        if source not in (
            "window_correctresponse",
            "dom_inference",
            "screenshot_inference",
        ):
            return None
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return None
        return {"mapping": mapping, "source": source, "confidence": confidence}
