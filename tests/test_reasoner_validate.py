import pytest
from experiment_bot.reasoner.validate import (
    Stage1ValidationError, Stage2SchemaError,
    validate_stage1_output, validate_stage2_schema,
)


def _complete_partial() -> dict:
    """SP10 minimal Stage 1 partial — paradigm-agnostic fields only.

    The driver handles platform-specific JS at runtime; Stage 1 emits
    LITERATURE + paradigm metadata + driver recommendation.
    """
    return {
        "task": {"name": "stroop", "paradigm_classes": ["conflict", "speeded_choice"]},
        "stimuli": [
            {"id": "s_congruent", "condition": "congruent"},
            {"id": "s_incongruent", "condition": "incongruent"},
        ],
        "performance": {"accuracy": {"congruent": 0.97, "incongruent": 0.92}},
        "recommended_driver": "JsPsychDriver",
    }


def test_validate_passes_on_complete_partial():
    validate_stage1_output(_complete_partial())  # no exception


def test_validate_fails_on_missing_task_name():
    p = _complete_partial()
    del p["task"]["name"]
    with pytest.raises(Stage1ValidationError, match="task.name"):
        validate_stage1_output(p)


def test_validate_fails_on_missing_paradigm_classes():
    p = _complete_partial()
    p["task"]["paradigm_classes"] = []
    with pytest.raises(Stage1ValidationError, match="paradigm_classes"):
        validate_stage1_output(p)


def test_validate_fails_on_empty_stimuli():
    p = _complete_partial()
    p["stimuli"] = []
    with pytest.raises(Stage1ValidationError, match="stimuli"):
        validate_stage1_output(p)


def test_validate_fails_on_stimulus_missing_id():
    p = _complete_partial()
    p["stimuli"] = [{"condition": "x"}]
    with pytest.raises(Stage1ValidationError, match="id"):
        validate_stage1_output(p)


def test_validate_fails_on_stimulus_missing_condition():
    p = _complete_partial()
    p["stimuli"] = [{"id": "x"}]
    with pytest.raises(Stage1ValidationError, match="condition"):
        validate_stage1_output(p)


def test_validate_accepts_legacy_nested_response_condition():
    """Legacy Stage-1 partials nest condition under response.condition.
    The validator should still accept that shape so older fixtures don't
    spuriously fail under SP10."""
    p = _complete_partial()
    p["stimuli"] = [
        {"id": "s_congruent",
         "detection": {"method": "dom_query", "selector": ".x"},
         "response": {"condition": "congruent"}},
    ]
    validate_stage1_output(p)  # no exception


def test_validate_fails_on_missing_performance_accuracy():
    p = _complete_partial()
    del p["performance"]["accuracy"]
    with pytest.raises(Stage1ValidationError, match="performance.accuracy"):
        validate_stage1_output(p)


def test_validate_fails_on_missing_recommended_driver():
    p = _complete_partial()
    del p["recommended_driver"]
    with pytest.raises(Stage1ValidationError, match="recommended_driver"):
        validate_stage1_output(p)


def test_validate_fails_on_unknown_recommended_driver():
    p = _complete_partial()
    p["recommended_driver"] = "FakeDriver"
    with pytest.raises(Stage1ValidationError, match="recommended_driver"):
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


def test_stage2_validate_rejects_unknown_mechanism_names():
    """Mechanisms not registered in the runtime are dead — silently
    ignored by the executor. The validator must reject any key that
    isn't in EFFECT_REGISTRY."""
    partial = {
        "temporal_effects": {
            "some_future_mechanism": _wrap_value({"enabled": True, "foo": "bar"}),
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    assert "some_future_mechanism" in str(exc.value)
    assert "unknown mechanism" in str(exc.value)


def test_stage2_validate_rejects_old_paradigm_named_keys():
    """Regression: cognitionrun_stroop regen emitted the pre-refactor
    paradigm names (`congruency_sequence`, `post_error_slowing`,
    `post_interrupt_slowing`). The runtime no longer recognizes any
    of these — flagging them prevents silently-non-firing TaskCards."""
    partial = {
        "temporal_effects": {
            "congruency_sequence": _wrap_value({
                "enabled": True, "sequence_facilitation_ms": 18,
                "sequence_cost_ms": 18,
            }),
            "post_error_slowing": _wrap_value({
                "enabled": True, "slowing_ms_min": 10, "slowing_ms_max": 50,
            }),
            "post_interrupt_slowing": _wrap_value({"enabled": False}),
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    msg = str(exc.value)
    assert "congruency_sequence" in msg
    assert "post_error_slowing" in msg
    assert "post_interrupt_slowing" in msg


def test_stage2_validate_accepts_registered_mechanisms_without_schema_entry():
    """If a mechanism is registered via register_effect() but isn't yet
    described in schema.json, validate against the registry only — no
    shape check, but the key passes through cleanly."""
    from experiment_bot.effects.registry import EFFECT_REGISTRY, register_effect
    # Register a fake mechanism for the duration of the test.
    register_effect("dummy_runtime_only", handler=lambda *a: 0.0)
    try:
        partial = {
            "temporal_effects": {
                "dummy_runtime_only": _wrap_value(
                    {"enabled": True, "anything": 42}
                ),
            }
        }
        validate_stage2_schema(partial)  # no raise
    finally:
        EFFECT_REGISTRY.pop("dummy_runtime_only", None)


# ---------------------------------------------------------------------------
# performance.accuracy / .omission_rate — runtime contract is float ∈ [0,1]
# ---------------------------------------------------------------------------


def test_stage2_validate_accepts_well_formed_performance():
    partial = {
        "performance": {
            "accuracy": {"congruent": 0.97, "incongruent": 0.92},
            "omission_rate": {"congruent": 0.005, "incongruent": 0.01},
        }
    }
    validate_stage2_schema(partial)  # no raise


def test_stage2_validate_rejects_nested_accuracy_dict():
    """Regression: stopit_stop_signal regen emitted accuracy.<cond> as
    {target, rationale} dicts; PerformanceConfig.get_accuracy returned
    a dict and the trial loop crashed with TypeError comparing
    random() < dict."""
    partial = {
        "performance": {
            "accuracy": {
                "go": {"target": 0.97,
                       "rationale": "Verbruggen 2019 consensus."},
                "stop_signal": {"target": 0.5, "rationale": "..."},
            },
            "omission_rate": {"go": 0.02, "stop_signal": 0.0},
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    assert "performance.accuracy" in str(exc.value)


def test_stage2_validate_rejects_accuracy_out_of_range():
    partial = {
        "performance": {
            "accuracy": {"go": 1.5},  # not a probability
            "omission_rate": {"go": 0.0},
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    assert "performance.accuracy" in str(exc.value)


# ---------------------------------------------------------------------------
# task_specific.key_map — runtime contract is short alphanumeric key string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("good_value", [
    "f", "j", " ", ".", "ArrowLeft", "ArrowRight", "Space", "Enter",
    "dynamic", "dynamic_mapping", "withhold", "null", "",
])
def test_stage2_validate_accepts_real_key_strings(good_value):
    partial = {"task_specific": {"key_map": {"go": good_value}}}
    validate_stage2_schema(partial)  # no raise


def test_stage2_validate_rejects_descriptive_prose_in_key_map():
    """Regression: stopit_stop_signal regen emitted
    task_specific.key_map.go = 'dynamic (ArrowLeft for left arrow, ...
    resolved per stimulus_id)'. The executor presses values literally,
    so this triggered Playwright `Keyboard.press: Unknown key`."""
    partial = {
        "task_specific": {
            "key_map": {
                "go": "dynamic (ArrowLeft for left arrow, ArrowRight for "
                      "right arrow; resolved per stimulus_id)",
                "stop_signal": "withhold (null)",
            }
        }
    }
    with pytest.raises(Stage2SchemaError) as exc:
        validate_stage2_schema(partial)
    assert "task_specific.key_map" in str(exc.value)


def test_stage2_validate_rejects_overlong_key_string():
    partial = {
        "task_specific": {
            "key_map": {"go": "x" * 50},
        }
    }
    with pytest.raises(Stage2SchemaError):
        validate_stage2_schema(partial)


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
