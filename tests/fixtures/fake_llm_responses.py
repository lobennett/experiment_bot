"""Canned LLM responses for reasoner stage tests."""

STAGE1_STROOP_RESPONSE = """
{
  "task": {"name": "Stroop", "constructs": ["cognitive control"], "reference_literature": []},
  "stimuli": [
    {"id": "stroop_congruent", "description": "color matches word",
     "detection": {"method": "dom_query", "selector": ".congruent"},
     "response": {"key": null, "condition": "congruent", "response_key_js": "..."}}
  ],
  "navigation": {"phases": []},
  "runtime": {},
  "task_specific": {"key_map": {"red": "r", "blue": "b"}},
  "performance": {"accuracy": {"congruent": 0.97, "incongruent": 0.92}},
  "pilot_validation_config": {"min_trials": 20, "target_conditions": ["congruent", "incongruent"]}
}
"""
