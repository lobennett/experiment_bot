import pytest
from experiment_bot.reasoner.validate import Stage1ValidationError, validate_stage1_output


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
