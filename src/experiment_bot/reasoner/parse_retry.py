"""Defensive JSON-parse helper for Reasoner stages.

Stage 2 has had an inline parse-retry loop since SP1.5 — when the LLM
returns malformed/empty JSON, Stage 2 appends the parser's error to
the user prompt and asks the LLM to regenerate. This module
generalizes that pattern for application to Stages 1, 3, 5, 6 (pilot
refinement) and the norms_extractor — all of which currently do
``json.loads(_extract_json(resp.text))`` with no retry path and so
fail hard on transient LLM noise.

Stage 2 is left untouched in SP4b; this helper is the model
implementation a future SP can consolidate Stage 2 onto if priorities
shift.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from experiment_bot.llm.protocol import LLMClient

logger = logging.getLogger(__name__)


class ParseRetryExceededError(ValueError):
    """Raised when parse_with_retry exhausts its retry budget. Carries
    the per-attempt history so debug logs can show what the LLM
    produced on each attempt."""

    def __init__(self, stage_name: str, history: list[tuple[int, str, str]]):
        self.stage_name = stage_name
        self.history = history  # list of (attempt_num, parser_error_msg, raw_response_truncated)
        attempt_lines = [
            f"  attempt {n}: {err}\n    raw: {raw[:120]}..."
            for n, err, raw in history
        ]
        super().__init__(
            f"parse_with_retry({stage_name!r}) exhausted retry budget after "
            f"{len(history)} attempts:\n" + "\n".join(attempt_lines)
        )


async def parse_with_retry(
    client: LLMClient,
    *,
    system: str,
    user: str,
    stage_name: str,
    max_retries: int = 3,
) -> dict[str, Any]:
    """LLM call → JSON parse → on parse failure, append parser error
    and retry up to ``max_retries`` times.

    Args:
        client: LLM client (must support ``await client.complete(system, user, output_format)``).
        system: System prompt.
        user: User prompt (modified across retries — original is preserved as base).
        stage_name: Diagnostic label included in error messages and logs.
        max_retries: Maximum number of retry attempts after the initial call (so total
            calls = max_retries + 1, or up to max_retries if max_retries is the budget cap).

    Returns:
        Parsed JSON dict.

    Raises:
        ParseRetryExceededError: After ``max_retries`` attempts all produce
        non-parseable output. Carries the per-attempt history.
    """
    # Local import to avoid a circular dependency: stage1_structural
    # now imports parse_with_retry, but `_extract_json` lives in
    # stage1_structural for historical reasons (other stages import it
    # from there too). Deferring keeps the import edge one-way at
    # module load time.
    from experiment_bot.reasoner.stage1_structural import _extract_json

    base_user = user
    user_msg = base_user
    history: list[tuple[int, str, str]] = []
    for attempt in range(1, max_retries + 1):
        resp = await client.complete(system=system, user=user_msg, output_format="json")
        try:
            return json.loads(_extract_json(resp.text))
        except json.JSONDecodeError as e:
            history.append((attempt, str(e), resp.text or ""))
            if attempt == max_retries:
                logger.warning(
                    "parse_with_retry(%s): exhausted %d attempts.",
                    stage_name, max_retries,
                )
                raise ParseRetryExceededError(stage_name, history) from None
            logger.info(
                "parse_with_retry(%s): attempt %d failed JSON parse "
                "(`%s` at line %d, col %d); retrying.",
                stage_name, attempt, e.msg, e.lineno, e.colno,
            )
            user_msg = (
                base_user
                + "\n\n## Parse error from previous attempt\n"
                f"Your previous output could not be parsed as JSON: "
                f"`{e.msg}` at line {e.lineno}, column {e.colno}. "
                "Regenerate the complete response, ensuring valid "
                "JSON syntax (no trailing commas, all strings closed, "
                "no unterminated objects/arrays).\n"
            )
    # Unreachable — the loop either returns or raises above.
    raise AssertionError("parse_with_retry: unreachable code path")
