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
    """Stage 2 wraps each parameter in a {value: <inner>, rationale, ...}
    envelope. Some envelopes wrap dict values (temporal_effects.*); some
    wrap bare numbers (performance.*) — both are valid since SP4a's
    schema generalization. This helper unwraps either shape; non-envelope
    nodes pass through unchanged so the validator can still apply.
    """
    if isinstance(node, dict) and "value" in node:
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

    # temporal_effects: every key must be a registered mechanism (or, if
    # extending via register_effect() in code, a key listed in schema).
    # An unrecognized key means the runtime won't apply the effect — the
    # same configured-but-non-firing failure mode that motivated this
    # validator. Common cause: LLM regressing to old paradigm-named keys
    # like `congruency_sequence` / `post_error_slowing` that were
    # removed from the registry.
    te_props = props.get("temporal_effects", {}).get("properties", {})
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    known_mechanisms = set(te_props.keys()) | set(EFFECT_REGISTRY.keys())
    for mech, entry in (partial.get("temporal_effects") or {}).items():
        if mech not in known_mechanisms:
            errors.append((
                f"temporal_effects.{mech}",
                f"unknown mechanism {mech!r}; the bot's library exposes "
                f"only: {sorted(known_mechanisms)}. The runtime will "
                f"silently ignore any key not in this list.",
            ))
            continue
        if mech not in te_props:
            # Registered in code but not in schema — accept without
            # shape check (no jsonschema definition to enforce).
            continue
        value = _value_only(entry)
        # Skip shape check if the mechanism is disabled — the LLM may
        # emit a placeholder value with no other fields, and that's fine.
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

    # performance.accuracy / omission_rate: each value must be a number in
    # [0,1]. Caught regression: LLM emitting {target, rationale} dicts
    # nested under each condition instead of plain floats — the executor's
    # PerformanceConfig.get_accuracy() returns whatever is at
    # accuracy[condition] and the trial loop crashes with TypeError when
    # it tries to compare random() < dict.
    perf_schema = props.get("performance")
    perf = partial.get("performance") or {}
    if perf_schema and isinstance(perf, dict) and perf:
        for sub in ("accuracy", "omission_rate"):
            sub_schema = perf_schema.get("properties", {}).get(sub)
            sub_value = perf.get(sub)
            if sub_schema and isinstance(sub_value, dict) and sub_value:
                try:
                    jsonschema.validate(sub_value, sub_schema)
                except jsonschema.ValidationError as e:
                    path = ".".join(str(p) for p in e.absolute_path)
                    err_path = f"performance.{sub}"
                    if path:
                        err_path += f".{path}"
                    errors.append((err_path, e.message))

    # task_specific.key_map: each value is a string the executor presses
    # as a literal Playwright key (or a withhold/dynamic sentinel). Caught
    # regression: LLM emitting prose like 'dynamic (ArrowLeft for left
    # arrow, ArrowRight for right arrow; resolved per stimulus_id)' which
    # the executor faithfully tries to press, raising
    # `Keyboard.press: Unknown key`. The schema's pattern + maxLength
    # catches descriptive strings without prescribing which keys are
    # paradigm-appropriate.
    ts_schema = props.get("task_specific", {}).get("properties", {})
    km_schema = ts_schema.get("key_map")
    km_value = (partial.get("task_specific") or {}).get("key_map")
    if km_schema and isinstance(km_value, dict) and km_value:
        try:
            jsonschema.validate(km_value, km_schema)
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path)
            err_path = "task_specific.key_map"
            if path:
                err_path += f".{path}"
            errors.append((err_path, e.message))

    # response_distributions: each condition's declared `distribution` must
    # have matching param keys. Catches mismatches that would KeyError at
    # runtime (e.g. lognormal missing sigma, or ex_gaussian missing tau).
    # Keys confirmed from core/distributions.py _build_sampler dispatch.
    _FAMILY_PARAMS: dict[str, frozenset[str]] = {
        "ex_gaussian": frozenset({"mu", "sigma", "tau"}),
        "lognormal": frozenset({"mu", "sigma"}),
        "shifted_wald": frozenset({"drift_rate", "boundary", "shift_ms"}),
    }
    for cond, entry in (partial.get("response_distributions") or {}).items():
        family = entry.get("distribution", "ex_gaussian") if isinstance(entry, dict) else "ex_gaussian"
        value = _value_only(entry) if isinstance(entry, dict) else {}
        if not isinstance(value, dict):
            continue
        required = _FAMILY_PARAMS.get(family)
        if required is None:
            errors.append((
                f"response_distributions.{cond}.distribution",
                f"unknown distribution family {family!r}; supported: "
                f"{sorted(_FAMILY_PARAMS)}",
            ))
            continue
        got = frozenset(k for k in value if k != "distribution")
        missing = required - got
        if missing:
            errors.append((
                f"response_distributions.{cond}.value",
                f"distribution={family!r} requires params {sorted(required)}; "
                f"missing: {sorted(missing)}",
            ))

    # Between-subject variance: when response_distributions are declared, at
    # least one variance channel must be non-zero, or every session in a
    # cohort collapses onto the same parameter draw (the frozen N=30 paper
    # dataset's cohort SDs came out 5-10x below human between-subject SDs
    # for exactly this reason). Two channels exist: the shared
    # `between_subject_jitter` block (consumed by the executor) and
    # per-parameter `between_subject_sd` on each response distribution
    # (consumed by sample_session_params). The gate checks PRESENCE only —
    # magnitudes stay literature-derived, never validator-prescribed.
    rd = partial.get("response_distributions") or {}
    if rd:
        bsj_value = _value_only(partial.get("between_subject_jitter") or {})
        has_jitter = isinstance(bsj_value, dict) and any(
            isinstance(bsj_value.get(k), (int, float)) and bsj_value[k] > 0
            for k in ("rt_mean_sd_ms", "rt_condition_sd_ms", "accuracy_sd", "omission_sd")
        )
        def _entry_has_sd(entry) -> bool:
            if not isinstance(entry, dict):
                return False
            sd = entry.get("between_subject_sd") or {}
            return isinstance(sd, dict) and any(
                isinstance(v, (int, float)) and v > 0 for v in sd.values()
            )
        if not has_jitter and not any(_entry_has_sd(e) for e in rd.values()):
            errors.append((
                "between_subject_jitter",
                "no between-subject variance declared: between_subject_jitter "
                "is zero/absent and no response_distributions[*]."
                "between_subject_sd is non-zero. A cohort of sessions would "
                "be near-identical pseudo-replicates of one parameter draw. "
                "Declare between-subject variability (either channel) at a "
                "magnitude supported by the literature for this paradigm.",
            ))

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
