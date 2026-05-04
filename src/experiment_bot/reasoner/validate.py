from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class Stage1ValidationError(ValueError):
    """Raised when Stage 1 output is missing executor-required fields."""


def validate_stage1_output(partial: dict) -> None:
    """Assert that Stage 1's output contains all executor-required runtime fields.

    Called after _extract_json and after normalize_partial. Raises
    Stage1ValidationError naming the first missing required field. Logs a
    warning if data_capture.method is intentionally empty.
    """
    runtime = partial.get("runtime", {})
    advance = runtime.get("advance_behavior", {})

    # advance_keys: required unless feedback_selectors covers all advance
    if not advance.get("advance_keys") and not advance.get("feedback_selectors"):
        raise Stage1ValidationError(
            "runtime.advance_behavior.advance_keys is empty AND "
            "feedback_selectors is empty — the executor will be unable to "
            "advance past instruction/feedback screens. Populate at least one."
        )

    # feedback_fallback_keys: required unless feedback_selectors covers feedback
    if not advance.get("feedback_fallback_keys") and not advance.get("feedback_selectors"):
        raise Stage1ValidationError(
            "runtime.advance_behavior.feedback_fallback_keys is empty AND "
            "feedback_selectors is empty — feedback screens will stall."
        )

    # data_capture: method-dependent subfield requirements
    capture = runtime.get("data_capture", {})
    method = capture.get("method", "")

    if method == "js_expression":
        if not capture.get("expression"):
            raise Stage1ValidationError(
                "runtime.data_capture.method is 'js_expression' but expression is empty."
            )
    elif method == "button_click":
        if not capture.get("button_selector") or not capture.get("result_selector"):
            raise Stage1ValidationError(
                "runtime.data_capture.method is 'button_click' but button_selector "
                "or result_selector is empty."
            )
    elif method == "":
        logger.warning(
            "Stage 1 produced data_capture.method='' — bot will not save "
            "experiment_data.* at completion. Verify this is intentional."
        )
    else:
        raise Stage1ValidationError(
            f"runtime.data_capture.method must be 'js_expression', 'button_click', "
            f"or '', got {method!r}"
        )
