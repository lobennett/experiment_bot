from experiment_bot.reasoner.normalize import normalize_partial


def test_normalize_maps_name_to_id():
    p = {"stimuli": [{"name": "go_left", "detection": {}, "response": {}}]}
    out = normalize_partial(p)
    assert out["stimuli"][0]["id"] == "go_left"


def test_normalize_maps_condition_to_id_when_no_name():
    p = {"stimuli": [{"condition": "stop", "detection": {}, "response": {}}]}
    out = normalize_partial(p)
    assert out["stimuli"][0]["id"] == "stop"


def test_normalize_keeps_existing_id():
    p = {"stimuli": [{"id": "explicit_id", "name": "ignored", "detection": {}, "response": {}}]}
    out = normalize_partial(p)
    assert out["stimuli"][0]["id"] == "explicit_id"


def test_normalize_adds_missing_description():
    p = {"stimuli": [{"id": "x", "detection": {}, "response": {}}]}
    out = normalize_partial(p)
    assert out["stimuli"][0]["description"] == ""


def test_normalize_maps_detection_type_to_method():
    p = {"stimuli": [{"id": "x", "detection": {"type": "js_eval", "expression": "..."}, "response": {}}]}
    out = normalize_partial(p)
    det = out["stimuli"][0]["detection"]
    assert det["method"] == "js_eval"
    assert det["selector"] == "..."
    assert "type" not in det
    assert "expression" not in det


def test_normalize_keeps_existing_detection_method():
    p = {"stimuli": [{"id": "x", "detection": {"method": "dom_query", "selector": "#stim"}, "response": {}}]}
    out = normalize_partial(p)
    det = out["stimuli"][0]["detection"]
    assert det["method"] == "dom_query"
    assert det["selector"] == "#stim"


def test_normalize_fills_response_condition_from_top_level():
    p = {"stimuli": [{"condition": "go", "detection": {}, "response": {"key": "f"}}]}
    out = normalize_partial(p)
    assert out["stimuli"][0]["response"]["condition"] == "go"


def test_normalize_fills_response_condition_from_id_when_no_top_level_condition():
    p = {"stimuli": [{"id": "go_left", "detection": {}, "response": {}}]}
    out = normalize_partial(p)
    assert out["stimuli"][0]["response"]["condition"] == "go_left"


def test_normalize_preserves_existing_response_condition():
    p = {"stimuli": [{"id": "stop", "condition": "wrong", "detection": {},
                      "response": {"condition": "correct_one"}}]}
    out = normalize_partial(p)
    assert out["stimuli"][0]["response"]["condition"] == "correct_one"


def test_normalize_does_not_mutate_input():
    p = {"stimuli": [{"name": "x", "detection": {"type": "js_eval"}, "response": {}}]}
    snapshot = {"stimuli": [{"name": "x", "detection": {"type": "js_eval"}, "response": {}}]}
    normalize_partial(p)
    assert p == snapshot


def test_normalize_handles_empty_stimuli():
    p = {"stimuli": []}
    out = normalize_partial(p)
    assert out["stimuli"] == []


def test_normalize_handles_missing_stimuli_key():
    p = {}
    out = normalize_partial(p)
    assert out.get("stimuli", []) == []
