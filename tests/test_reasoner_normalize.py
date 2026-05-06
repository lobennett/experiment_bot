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


def test_normalize_task_adds_name_when_missing():
    p = {"task": {"constructs": ["x"], "reference_literature": []}}
    out = normalize_partial(p)
    assert out["task"]["name"] == "unknown"


def test_normalize_task_uses_title_alt():
    p = {"task": {"title": "Stroop Task"}}
    out = normalize_partial(p)
    assert out["task"]["name"] == "Stroop Task"


def test_normalize_task_uses_task_name_alt():
    p = {"task": {"task_name": "Stop Signal"}}
    out = normalize_partial(p)
    assert out["task"]["name"] == "Stop Signal"


def test_normalize_task_preserves_existing_name():
    p = {"task": {"name": "Real Name", "title": "Wrong"}}
    out = normalize_partial(p)
    assert out["task"]["name"] == "Real Name"


def test_normalize_task_adds_missing_constructs_and_lit():
    p = {"task": {"name": "x"}}
    out = normalize_partial(p)
    assert out["task"]["constructs"] == []
    assert out["task"]["reference_literature"] == []


def test_normalize_navigation_wraps_list():
    p = {"navigation": [{"phase": "instructions", "action": "click"}]}
    out = normalize_partial(p)
    assert "phases" in out["navigation"]
    assert len(out["navigation"]["phases"]) == 1
    assert out["navigation"]["phases"][0]["phase"] == "instructions"


def test_normalize_navigation_preserves_phases_dict():
    p = {"navigation": {"phases": [{"phase": "x"}]}}
    out = normalize_partial(p)
    # Original `phase` value is preserved; defaults for the strict schema are added.
    assert out["navigation"]["phases"][0]["phase"] == "x"
    assert out["navigation"]["phases"][0]["action"] == ""
    assert out["navigation"]["phases"][0]["target"] == ""


def test_normalize_navigation_phase_maps_type_to_action():
    p = {"navigation": [{"type": "click", "selector": "#btn"}]}
    out = normalize_partial(p)
    phase = out["navigation"]["phases"][0]
    assert phase["action"] == "click"
    assert phase["target"] == "#btn"


def test_normalize_navigation_phase_maps_duration_to_duration_ms():
    p = {"navigation": [{"type": "wait", "duration": 500}]}
    out = normalize_partial(p)
    phase = out["navigation"]["phases"][0]
    assert phase["action"] == "wait"
    assert phase["duration_ms"] == 500


def test_normalize_navigation_phase_maps_singleton_step_to_steps():
    """LLM repeat action uses singleton `step`; we coerce to `steps` list."""
    p = {"navigation": [{"type": "repeat", "times": 4, "step": {"type": "keypress", "key": " "}}]}
    out = normalize_partial(p)
    phase = out["navigation"]["phases"][0]
    assert phase["action"] == "repeat"
    assert isinstance(phase["steps"], list)
    assert len(phase["steps"]) == 1
    # The nested step's `type` was also normalized to `action`
    assert phase["steps"][0]["action"] == "keypress"
    assert phase["steps"][0]["key"] == " "


def test_normalize_navigation_handles_none():
    p = {}
    out = normalize_partial(p)
    assert out["navigation"] == {"phases": []}


def test_normalize_navigation_handles_empty_dict():
    p = {"navigation": {}}
    out = normalize_partial(p)
    assert out["navigation"] == {"phases": []}
