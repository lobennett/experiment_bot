"""Invariant test: every JSON example in the Stage 2 prompt must
validate against the schema sub-tree the example claims to illustrate.
Anti-examples must fail to validate. Catches prompt-schema drift."""
from __future__ import annotations
import json
import re
from pathlib import Path

import jsonschema
import pytest


PROMPT_PATH = Path("src/experiment_bot/reasoner/prompts/stage2_behavioral.md")
SCHEMA_PATH = Path("src/experiment_bot/prompts/schema.json")

# Fenced block format:
#   ```json schema-example: <path>
#   <json>
#   ```
# Path uses dot-segments; "[]" suffix means "the array's items schema".
_BLOCK_RE = re.compile(
    r"^```json\s+(schema-example|schema-anti-example):\s*([^\n]+?)\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def _resolve_schema_path(schema: dict, path: str) -> dict:
    """Resolve a dot/[]-segment path to the schema sub-tree at that location.
    Examples:
      "performance.accuracy.<condition>"
        → schema.properties.performance.properties.accuracy.additionalProperties
      "temporal_effects.post_event_slowing.triggers[]"
        → ...properties.triggers.items
      "task_specific.key_map"
        → ...properties.task_specific.properties.key_map
    """
    node = schema
    if "properties" in node:
        node = node["properties"]
    segments = path.split(".")
    for seg in segments:
        # Handle <placeholder> segments (e.g., "<condition>"):
        # they mean "additionalProperties" — i.e., per-key schema.
        if seg.startswith("<") and seg.endswith(">"):
            node = node["additionalProperties"]
            continue
        # Handle "[]" suffix on a segment (e.g., "triggers[]"):
        # strip and recurse into items after.
        items_after = seg.endswith("[]")
        if items_after:
            seg = seg[:-2]
        if seg in node:
            node = node[seg]
        elif "properties" in node and seg in node["properties"]:
            node = node["properties"][seg]
        else:
            raise KeyError(f"Schema path segment {seg!r} not found in node keys {sorted(node.keys())}")
        if items_after:
            node = node["items"]
        elif "properties" in node:
            # Auto-descend into properties on the next iteration unless
            # the next segment is a placeholder.
            pass
    return node


def _extract_blocks(text: str):
    """Yield (kind, path, parsed_json) for each fenced example block."""
    for m in _BLOCK_RE.finditer(text):
        kind, path, body = m.group(1), m.group(2), m.group(3)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"Prompt example at {path!r} is not valid JSON: {e}"
            )
        yield kind, path, data


def test_prompt_schema_consistency():
    schema = json.loads(SCHEMA_PATH.read_text())
    prompt = PROMPT_PATH.read_text()

    blocks = list(_extract_blocks(prompt))
    assert blocks, "No schema-example blocks found in stage2_behavioral.md — has the addendum been removed?"

    for kind, path, data in blocks:
        try:
            sub_schema = _resolve_schema_path(schema, path)
        except KeyError as e:
            pytest.fail(f"schema path resolution failed for {path!r}: {e}")
        try:
            jsonschema.validate(data, sub_schema)
            example_validated = True
        except jsonschema.ValidationError as e:
            example_validated = False
            ve_msg = e.message
        if kind == "schema-example":
            assert example_validated, (
                f"prompt example at {path!r} should validate but did not: {ve_msg}\n"
                f"data: {json.dumps(data)}"
            )
        elif kind == "schema-anti-example":
            assert not example_validated, (
                f"prompt anti-example at {path!r} unexpectedly validates against the schema. "
                f"Either the schema accepts it (anti-example is wrong) or the schema is too permissive. "
                f"data: {json.dumps(data)}"
            )


def test_extract_blocks_finds_all_paths():
    """At least these four paths must have at least one example block.
    They correspond to the four SP3-documented failure modes."""
    prompt = PROMPT_PATH.read_text()
    blocks = list(_extract_blocks(prompt))
    paths_seen = {path for _, path, _ in blocks}
    expected_subset = {
        "temporal_effects.post_event_slowing.triggers[]",
        "temporal_effects.lag1_pair_modulation.modulation_table[]",
        "performance.accuracy.<condition>",
        "task_specific.key_map",
    }
    missing = expected_subset - paths_seen
    assert not missing, f"missing prompt examples for paths: {missing}"
