from __future__ import annotations
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Stage1ValidationError(ValueError):
    """Raised when Stage 1 output is missing executor-required fields."""


class Stage2SchemaError(ValueError):
    """Raised when Stage 2 output violates the runtime schema contract.

    The error string includes a list of every violation found, formatted
    so the LLM can correct each one when given the message back as
    feedback in a refinement turn.
    """

    def __init__(self, errors: list[tuple[str, str]]):
        self.errors = errors
        lines = [f"  - {path}: {msg}" for path, msg in errors]
        super().__init__(
            "Stage 2 output failed schema validation:\n" + "\n".join(lines)
        )


_SCHEMA_PATH = Path(__file__).parent.parent / "prompts" / "schema.json"


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def _value_only(node):
    """Stage 2 wraps each parameter in a {value: {...}, citations, ...}
    envelope. The runtime schema describes the inner value object. This
    helper unwraps an envelope to its value dict; non-envelope dicts pass
    through unchanged so the schema can apply.
    """
    if isinstance(node, dict) and "value" in node and isinstance(node["value"], dict):
        return node["value"]
    return node


def validate_stage2_schema(partial: dict) -> None:
    """Validate Stage 2's behavioral fields against the runtime schema
    contract. Currently checks:

    - `temporal_effects.<mechanism>.value` against the mechanism's
      schema.json subschema. Catches the silently-non-firing-effect
      bug — e.g. a `post_event_slowing.triggers[]` entry with
      `condition`+`slowing_ms` instead of the runtime-required
      `event`+`slowing_ms_min`+`slowing_ms_max`.
    - `between_subject_jitter.value` against its schema.json
      properties (field names, types, minima).

    Field names and enum values come from the bot's runtime contract
    (what the executor reads) — not paradigm knowledge. The validator
    never prescribes which mechanisms to enable or which event sources
    to include; it only enforces the shape an enabled config must take.

    Raises Stage2SchemaError listing every violation found. The error
    message is suitable for inclusion in a refinement-turn user prompt
    so the LLM can self-correct without paradigm-specific coaching.
    """
    import jsonschema

    schema = _load_schema()
    props = schema.get("properties", {})
    errors: list[tuple[str, str]] = []

    # temporal_effects: each known mechanism's value object against its
    # subschema. Unknown mechanism names are ignored — the registry is
    # open by design and new mechanisms register without editing schema.
    te_props = props.get("temporal_effects", {}).get("properties", {})
    for mech, entry in (partial.get("temporal_effects") or {}).items():
        if mech not in te_props:
            continue
        value = _value_only(entry)
        # Skip if the mechanism is disabled — the LLM may emit a
        # placeholder value with no other fields, and that's fine.
        if isinstance(value, dict) and value.get("enabled") is False:
            continue
        try:
            jsonschema.validate(value, te_props[mech])
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path)
            err_path = f"temporal_effects.{mech}.value"
            if path:
                err_path += f".{path}"
            errors.append((err_path, e.message))

    # between_subject_jitter: the value object against its schema.
    bsj_schema = props.get("between_subject_jitter")
    if bsj_schema:
        bsj_entry = partial.get("between_subject_jitter") or {}
        value = _value_only(bsj_entry)
        if isinstance(value, dict) and value:
            try:
                jsonschema.validate(value, bsj_schema)
            except jsonschema.ValidationError as e:
                path = ".".join(str(p) for p in e.absolute_path)
                err_path = "between_subject_jitter.value"
                if path:
                    err_path += f".{path}"
                errors.append((err_path, e.message))

    if errors:
        raise Stage2SchemaError(errors)


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

    # stimuli: each must have non-empty detection.selector so the executor can detect it
    for stim in partial.get("stimuli", []):
        sel = stim.get("detection", {}).get("selector", "")
        if not sel:
            raise Stage1ValidationError(
                f"stimulus {stim.get('id', '<unnamed>')!r}: detection.selector is empty. "
                f"The executor cannot detect this stimulus on the page. "
                f"Provide a CSS selector (for method='dom_query') or JS expression "
                f"(for method='js_eval'/'canvas_state')."
            )
