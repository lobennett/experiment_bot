import pytest
from experiment_bot.reasoner.validate import (
    Stage1ValidationError, Stage2SchemaError,
    validate_stage1_output, validate_stage2_schema,
)


def _complete_partial() -> dict:
    return {
        "runtime": {
            "advance_behavior": {
                "advance_keys": [" "],
                "feedback_fallback_keys": ["Enter"],
                "feedback_selectors": [],
            },
            "data_capture": {
                "method": "js_expression",
                "expression": "jsPsych.data.get().json()",
                "format": "json",
            },
        }
    }


def test_validate_passes_on_complete_partial():
    validate_stage1_output(_complete_partial())  # no exception


def test_validate_fails_on_missing_advance_keys_and_no_feedback_selectors():
    p = _complete_partial()
    p["runtime"]["advance_behavior"]["advance_keys"] = []
    p["runtime"]["advance_behavior"]["feedback_selectors"] = []
    with pytest.raises(Stage1ValidationError, match="advance_keys"):
        validate_stage1_output(p)


def test_validate_passes_when_feedback_selectors_present_but_advance_keys_empty():
    p = _complete_partial()
    p["runtime"]["advance_behavior"]["advance_keys"] = []
    p["runtime"]["advance_behavior"]["feedback_selectors"] = ["#next-button"]
    validate_stage1_output(p)  # no exception


def test_validate_fails_on_missing_data_capture_expression():
    p = _complete_partial()
    p["runtime"]["data_capture"]["expression"] = ""
    with pytest.raises(Stage1ValidationError, match="expression"):
        validate_stage1_output(p)


def test_validate_fails_on_missing_data_capture_button_selectors():
    p = _complete_partial()
    p["runtime"]["data_capture"]["method"] = "button_click"
    p["runtime"]["data_capture"]["expression"] = ""
    p["runtime"]["data_capture"]["button_selector"] = ""
    p["runtime"]["data_capture"]["result_selector"] = ""
    with pytest.raises(Stage1ValidationError, match="button_selector|result_selector"):
        validate_stage1_output(p)


def test_validate_passes_on_method_empty():
    p = _complete_partial()
    p["runtime"]["data_capture"]["method"] = ""
    p["runtime"]["data_capture"]["expression"] = ""
    validate_stage1_output(p)  # method="" is permitted (logs warning)


def test_validate_fails_on_stimulus_with_empty_selector():
    """Stage 1 must produce stimuli with non-empty detection.selector,
    otherwise the executor's stimulus detection cannot fire."""
    p = _complete_partial()
    p["stimuli"] = [{"id": "x", "detection": {"method": "dom_query", "selector": ""},
                      "response": {"condition": "x"}}]
    with pytest.raises(Stage1ValidationError, match="detection.selector"):
        validate_stage1_output(p)


def test_validate_passes_on_stimulus_with_non_empty_selector():
    p = _complete_partial()
    p["stimuli"] = [{"id": "x",
                      "detection": {"method": "dom_query", "selector": "#stim"},
                      "response": {"condition": "x"}}]
    validate_stage1_output(p)


def test_validate_passes_on_no_stimuli_block():
    """If 'stimuli' isn't present, validator shouldn't raise — that's a different error."""
    p = _complete_partial()
    validate_stage1_output(p)


# ---------------------------------------------------------------------------
# Stage 2 schema validation
# ---------------------------------------------------------------------------


def _wrap_value(inner: dict) -> dict:
    """Wrap a runtime-shape dict in the ParameterValue envelope Stage 2
    actually emits."""
    return {"value": inner, "rationale": "", "citations": []}


def test_stage2_validate_accepts_well_formed_post_event_slowing():
    partial = {
        "temporal_effects": {
            "post_event_slowing": _wrap_value({
                "enabled": True,
                "triggers": [
                    {"event": "interrupt", "slowing_ms_min": 80,
                     "slowing_ms_max": 200,
                     "exclusive_with_prior_triggers": True},
                    {"event": "error", "slowing_ms_min": 10,
                     "slowing_ms_max": 50,
                     "exclusive_with_prior_triggers": True},
                ],
            }),
        }
    }
    validate_stage2_schema(partial)  # no raise


def test_stage2_validate_rejects_post_event_slowing_with_string_triggers():
    """Regression: expfactory_stop_signal regen emitted
    triggers: ['successful_stop', 'failed_stop'] — strings not dicts."""
    partial = {
        "temporal_effects": {
            "post_event_slowing": _wrap_value({
                "enabled": True,
                "triggers": ["successful_stop", "failed_stop"],
            }),
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    assert "post_event_slowing" in str(exc.value)


def test_stage2_validate_rejects_post_event_slowing_missing_event_field():
    """Regression: stopit_stop_signal regen emitted
    triggers[0] = {condition: 'stop_signal', slowing_ms: 25, ...} —
    missing required `event` and using `slowing_ms` instead of
    `slowing_ms_min`/`slowing_ms_max`."""
    partial = {
        "temporal_effects": {
            "post_event_slowing": _wrap_value({
                "enabled": True,
                "triggers": [
                    {"condition": "stop_signal",
                     "slowing_ms": 25.0, "decay_trials": 2},
                ],
            }),
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    msg = str(exc.value)
    assert "post_event_slowing" in msg
    # Either missing `event` is reported or extra `condition` is rejected
    assert "event" in msg or "condition" in msg


def test_stage2_validate_rejects_post_event_slowing_with_delta_ms():
    """Regression: expfactory_stroop regen emitted
    triggers[0] = {event: 'error', delta_ms: 30, ...} — uses `delta_ms`
    instead of `slowing_ms_min`/`slowing_ms_max`."""
    partial = {
        "temporal_effects": {
            "post_event_slowing": _wrap_value({
                "enabled": True,
                "triggers": [
                    {"event": "error", "delta_ms": 30.0,
                     "decay_trials": 1},
                ],
            }),
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    # Error must point at the bad trigger field, not just say "object is invalid"
    assert "post_event_slowing" in str(exc.value)


def test_stage2_validate_rejects_post_event_slowing_invalid_event_enum():
    """Schema constrains event to {error, interrupt}; reject anything else."""
    partial = {
        "temporal_effects": {
            "post_event_slowing": _wrap_value({
                "enabled": True,
                "triggers": [
                    {"event": "successful_stop",
                     "slowing_ms_min": 10, "slowing_ms_max": 50},
                ],
            }),
        }
    }
    with pytest.raises(Stage2SchemaError):
        validate_stage2_schema(partial)


def test_stage2_validate_skips_disabled_mechanisms():
    """A mechanism with enabled=False can have a placeholder shape;
    validator should not enforce the full schema on it."""
    partial = {
        "temporal_effects": {
            "post_event_slowing": _wrap_value({"enabled": False}),
            "lag1_pair_modulation": _wrap_value({
                "enabled": False, "modulation_table": []
            }),
        }
    }
    validate_stage2_schema(partial)  # no raise


def test_stage2_validate_ignores_unknown_mechanisms():
    """Effect registry is open — unknown mechanisms aren't in schema.json
    and the validator should not raise on them."""
    partial = {
        "temporal_effects": {
            "some_future_mechanism": _wrap_value({"enabled": True, "foo": "bar"}),
        }
    }
    validate_stage2_schema(partial)  # no raise


def test_stage2_validate_accepts_well_formed_lag1_pair_modulation():
    partial = {
        "temporal_effects": {
            "lag1_pair_modulation": _wrap_value({
                "enabled": True,
                "skip_after_error": True,
                "modulation_table": [
                    {"prev": "incongruent", "curr": "incongruent",
                     "delta_ms": -50},
                    {"prev": "congruent", "curr": "incongruent",
                     "delta_ms": 20},
                ],
            }),
        }
    }
    validate_stage2_schema(partial)  # no raise


def test_stage2_validate_rejects_lag1_with_missing_prev_curr():
    partial = {
        "temporal_effects": {
            "lag1_pair_modulation": _wrap_value({
                "enabled": True,
                "modulation_table": [{"delta_ms": -50}],  # no prev/curr
            }),
        }
    }
    with pytest.raises(Stage2SchemaError):
        validate_stage2_schema(partial)


def test_stage2_validate_error_message_lists_every_violation():
    """Multi-failure message format is suitable for refinement-turn feedback."""
    partial = {
        "temporal_effects": {
            "post_event_slowing": _wrap_value({
                "enabled": True,
                "triggers": ["bad_string"],
            }),
            "lag1_pair_modulation": _wrap_value({
                "enabled": True,
                "modulation_table": [{"delta_ms": 10}],
            }),
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    msg = str(exc.value)
    assert "post_event_slowing" in msg
    assert "lag1_pair_modulation" in msg
