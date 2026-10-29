"""A run must carry verifiable evidence before it can be sealed as complete."""
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts/check_run.py"


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location("check_participant_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run(tmp_path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/end.txt").write_text("Task complete")
    (tmp_path / "summary.md").write_text("Synthetic participant completed the task.")
    (tmp_path / "ontology.json").write_text(json.dumps({
        "schema_version": "1.0", "task": {"url": "https://example.org/demo"},
        "nodes": [{"id": "end", "kind": "completion", "label": "Done", "attributes": {},
                   "status": "observed", "evidence_refs": ["e1"]}],
        "relations": [],
        "evidence": [{"id": "e1", "path": "evidence/end.txt", "locator": "line 1",
                      "source_type": "visible_text", "observed_at": "2026-10-28T00:00:00Z",
                      "description": "Terminal screen"}], "unknowns": []}))
    (tmp_path / "events.jsonl").write_text(json.dumps({
        "index": 1, "at": "2026-10-28T00:00:00Z", "kind": "completion",
        "phase_id": "end", "trial_id": None, "observation": "Task complete",
        "action": None, "outcome": None, "evidence_refs": ["e1"], "timing": None}) + "\n")
    (tmp_path / "run.json").write_text(json.dumps({
        "status": "completed", "ended_at": "2026-10-28T00:00:00Z",
        "completion_evidence_refs": ["e1"],
        "data_export": {"status": "unavailable", "paths": [], "reason": "No export offered"},
        "artifacts_sha256": {}}))
    return tmp_path


def update(path, transform):
    data = json.loads(path.read_text())
    transform(data)
    path.write_text(json.dumps(data))


def test_complete_run_can_be_sealed_without_native_export(checker, run):
    checker.check(run, seal=True)
    checker.check(run)
    manifest = json.loads((run / "run.json").read_text())
    assert len(manifest["artifacts_sha256"]) == 4
    (run / "evidence/end.txt").write_text("Task failed")
    with pytest.raises(ValueError, match="hash"):
        checker.check(run)


def test_completion_needs_evidence_and_failed_seal_preserves_manifest(checker, run):
    update(run / "run.json", lambda d: d.update(completion_evidence_refs=[]))
    before = (run / "run.json").read_bytes()
    with pytest.raises(ValueError, match="completion"):
        checker.check(run, seal=True)
    assert (run / "run.json").read_bytes() == before


def test_unresolved_ontology_relation_is_rejected(checker, run):
    update(run / "ontology.json", lambda d: d["relations"].append({
        "subject": "end", "predicate": "follows", "object": "missing",
        "status": "observed", "evidence_refs": ["e1"]}))
    with pytest.raises(ValueError, match="endpoint"):
        checker.check(run, seal=True)


def test_evidence_must_be_inside_run_directory(checker, run, tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside")
    update(run / "ontology.json", lambda d: d["evidence"][0].update(path="../outside.txt"))
    with pytest.raises(ValueError, match="inside"):
        checker.check(run, seal=True)


def test_partial_run_retains_failure_without_completion_claim(checker, run):
    update(run / "run.json", lambda d: d.update(status="partial", completion_evidence_refs=[]))
    checker.check(run, seal=True)
    assert json.loads((run / "run.json").read_text())["status"] == "partial"


def test_resealing_cannot_hide_changed_frozen_policy(checker, run):
    policy = run / "participant.js"
    policy.write_text("original policy")
    update(run / "run.json", lambda d: d.update(
        policy_path="participant.js", policy_sha256=hashlib.sha256(policy.read_bytes()).hexdigest()))
    checker.check(run, seal=True)
    policy.write_text("changed policy")
    with pytest.raises(ValueError, match="policy hash"):
        checker.check(run, seal=True)


def test_new_contract_requires_protocol_snapshot(checker, run):
    update(run / "run.json", lambda d: d.update(schema_version="1.1", mode="direct_browser"))
    with pytest.raises(ValueError, match="protocol"):
        checker.check(run, seal=True)


def test_new_generated_contract_requires_generation_provenance(checker, run):
    (run / "protocol").mkdir()
    source = run / "protocol/SKILL.md"
    source.write_text("Used instructions")
    update(run / "run.json", lambda d: d.update(
        schema_version="1.1", mode="generated_visible_policy",
        skill_sha256={"SKILL.md": hashlib.sha256(source.read_bytes()).hexdigest()}))
    with pytest.raises(ValueError, match="policy"):
        checker.check(run, seal=True)
    (run / "participant.js").write_text("Frozen participant")
    (run / "prompt.md").write_text("Actual prompt")
    (run / "gate.json").write_text('{"status":"passed"}')
    update(run / "run.json", lambda d: d.update(
        policy_path="participant.js",
        policy_sha256=hashlib.sha256((run / "participant.js").read_bytes()).hexdigest(),
        authoring_prompt_path="prompt.md", gate_report_path="gate.json",
        authoring_context="inherited_agent_context"))
    result = checker.check(run, seal=True)
    assert result["legacy_contract"] is False
