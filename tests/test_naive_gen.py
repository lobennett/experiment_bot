"""SP21 Task 6: generation CLI — archival, extraction, retry-on-gate-fail."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.behavior.gen_cli import (
    extract_python_block, generate, mechanical_facts,
)

TOY_TEXT = Path("tests/fixtures/toy_participant.py").read_text()


def test_extract_python_block():
    assert extract_python_block(f"prose\n```python\n{TOY_TEXT}```\nmore") == TOY_TEXT
    with pytest.raises(ValueError):
        extract_python_block("no code here")


def test_mechanical_facts():
    tc = MagicMock()
    tc.task_specific = {"key_map": {"go": "z", "stop": "withhold"}}
    tc.stimuli = [{"response": {"condition": "go", "key": "z"}},
                  {"response": {"condition": "stop", "key": None}}]
    tc.runtime.trial_interrupt.detection_condition = "stop"
    facts = mechanical_facts(tc)
    assert set(facts["conditions"]) == {"go", "stop"}
    assert facts["key_map"] == {"go": "z"}
    assert facts["has_interrupt"] is True
    assert facts["interrupt_condition"] == "stop"


def test_mechanical_facts_no_interrupt():
    tc = MagicMock()
    tc.task_specific = {"key_map": {"go": "z"}}
    tc.stimuli = [{"response": {"condition": "go", "key": "z"}}]
    tc.runtime.trial_interrupt.detection_condition = None
    facts = mechanical_facts(tc)
    assert facts["has_interrupt"] is False
    assert facts["interrupt_condition"] is None


def test_mechanical_facts_excludes_dynamic_sentinel():
    """C1: key_map entries of 'dynamic'/'dynamic_mapping' (any case) must be
    filtered the same way withhold sentinels are — the executor resolves
    those keys per-trial via JS, never from this static map."""
    tc = MagicMock()
    tc.task_specific = {"key_map": {"go": "dynamic", "stop": "DYNAMIC_MAPPING",
                                    "flank": "z"}}
    tc.stimuli = [{"response": {"condition": "go", "key": None}},
                  {"response": {"condition": "stop", "key": None}},
                  {"response": {"condition": "flank", "key": "z"}}]
    tc.runtime.trial_interrupt.detection_condition = None
    facts = mechanical_facts(tc)
    assert facts["key_map"] == {"flank": "z"}


def test_mechanical_facts_collects_response_elements():
    """Wave B1: click-response stimuli contribute condition -> option-label
    lists so the gate can replay clickable trials."""
    tc = MagicMock()
    tc.task_specific = {"key_map": {}}
    tc.stimuli = [
        {"response": {"condition": "choice", "key": None,
                      "response_elements": [
                          {"label": "Left", "selector": "#l"},
                          {"label": "Right", "selector": "#r"}]}},
        {"response": {"condition": "go", "key": "z"}},
    ]
    tc.runtime.trial_interrupt.detection_condition = None
    facts = mechanical_facts(tc)
    assert facts["response_elements"] == {"choice": ["Left", "Right"]}


def _fake_client(responses):
    client = MagicMock()
    client.model = "claude-fable-5"
    client.complete = AsyncMock(
        side_effect=[MagicMock(text=r) for r in responses])
    return client


def _fake_scrape(monkeypatch):
    import experiment_bot.behavior.gen_cli as g
    bundle = MagicMock()
    bundle.description_text = "<html>task</html>"
    bundle.source_files = {}
    monkeypatch.setattr(g, "scrape_experiment_source",
                        AsyncMock(return_value=bundle))


def _fake_taskcard(monkeypatch):
    import experiment_bot.behavior.gen_cli as g
    tc = MagicMock()
    tc.task_specific = {"key_map": {"go": "z"}}
    tc.stimuli = [{"response": {"condition": "go", "key": "z"}}]
    tc.runtime.trial_interrupt.detection_condition = None
    tc.to_dict.return_value = {"task_specific": {"key_map": {"go": "z"}}}
    loader = MagicMock(return_value=tc)
    monkeypatch.setattr(g, "_load_structural_taskcard", loader)
    return loader


def test_generate_archives_program_and_transcript(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    path = asyncio.run(generate("http://x", "toy", client, out_root=tmp_path))
    assert path.exists() and path.suffix == ".py"
    sha = path.stem
    transcript = json.loads((tmp_path / "toy" / f"{sha}.transcript.json").read_text())
    assert transcript["model"] == "claude-fable-5"
    assert "task source" in transcript["prompt"].lower() or transcript["prompt"]
    assert (tmp_path / "toy" / f"{sha}.simgate.json").exists()


def test_generate_records_taskcard_sha256_in_transcript(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    from experiment_bot.taskcard.hashing import taskcard_sha256 as compute_hash
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    path = asyncio.run(generate("http://x", "toy", client, out_root=tmp_path))
    sha = path.stem
    transcript = json.loads((tmp_path / "toy" / f"{sha}.transcript.json").read_text())
    expected = compute_hash({"task_specific": {"key_map": {"go": "z"}}})
    assert transcript["taskcard_sha256"] == expected


def test_generate_passes_taskcard_sha256_to_loader(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch)
    loader = _fake_taskcard(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    asyncio.run(generate("http://x", "toy", client, out_root=tmp_path,
                        taskcard_sha256="deadbeef"))
    loader.assert_called_once_with("toy", "taskcards", taskcard_sha256="deadbeef")


def test_generate_retries_on_gate_failure_then_fails(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    crash = "def make_participant(seed):\n    raise ValueError('boom')\n"
    client = _fake_client([f"```python\n{crash}```"] * 3)
    with pytest.raises(RuntimeError, match="gate"):
        asyncio.run(generate("http://x", "toy", client, out_root=tmp_path))
    assert client.complete.await_count == 3  # initial + 2 retries, all archived
    assert len(list((tmp_path / "toy").glob("*.transcript.json"))) == 3


# --- Wave C2: mechanical source slimming wired into generation ---

def test_generate_records_slimming_manifest_in_transcript(tmp_path, monkeypatch):
    """Every attempt's transcript archives the slimming manifest (what was
    included/excluded from the prompt's page source, and the budget)."""
    from experiment_bot.behavior.source_slim import DEFAULT_SOURCE_BUDGET
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    path = asyncio.run(generate("http://x", "toy", client, out_root=tmp_path))
    sha = path.stem
    transcript = json.loads((tmp_path / "toy" / f"{sha}.transcript.json").read_text())
    assert transcript["slimming"]["budget"] == DEFAULT_SOURCE_BUDGET
    assert transcript["slimming"]["entry"]["truncated"] is False
    assert transcript["slimming"]["files"] == []


def test_generate_source_budget_excludes_oversized_file(tmp_path, monkeypatch):
    """source_budget flows into the slimmer: an oversized vendor file is
    excluded from the prompt but recorded in the manifest."""
    import experiment_bot.behavior.gen_cli as g
    bundle = MagicMock()
    bundle.description_text = "<html><script src='vendor.min.js'></script></html>"
    bundle.source_files = {"vendor.min.js": "var a=1;" * 4000,
                           "task.js": "var task = true;\n"}
    monkeypatch.setattr(g, "scrape_experiment_source",
                        AsyncMock(return_value=bundle))
    _fake_taskcard(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    path = asyncio.run(generate("http://x", "toy", client, out_root=tmp_path,
                                source_budget=2_000))
    sha = path.stem
    transcript = json.loads((tmp_path / "toy" / f"{sha}.transcript.json").read_text())
    assert "var a=1;var a=1;" not in transcript["prompt"]
    assert "var task = true;" in transcript["prompt"]
    by_name = {f["name"]: f for f in transcript["slimming"]["files"]}
    assert by_name["vendor.min.js"]["included"] is False
    assert by_name["task.js"]["included"] is True


# --- Wave C4: K-program generation ---

def test_generate_programs_k2_archives_two_transcripts_and_gates(tmp_path, monkeypatch):
    """K=2 with distinct replies: two passing programs, each with its own
    transcript + gate record, one scrape for the whole batch."""
    from experiment_bot.behavior.gen_cli import generate_programs
    import experiment_bot.behavior.gen_cli as g
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    variant = TOY_TEXT + "\n# independent variant\n"
    client = _fake_client([f"```python\n{TOY_TEXT}```",
                           f"```python\n{variant}```"])
    passed, failures = asyncio.run(generate_programs(
        "http://x", "toy", client, n_programs=2, out_root=tmp_path))
    assert failures == []
    assert len(passed) == 2
    assert len({p.stem for p in passed}) == 2  # distinct hashes
    out = tmp_path / "toy"
    transcripts = list(out.glob("*.transcript.json"))
    assert len(transcripts) == 2
    assert len(list(out.glob("*.simgate.json"))) == 2
    indices = sorted(json.loads(t.read_text())["program_index"] for t in transcripts)
    assert indices == [0, 1]
    assert g.scrape_experiment_source.await_count == 1


def test_generate_programs_duplicate_program_is_not_independent(tmp_path, monkeypatch):
    """A slot whose passing code is byte-identical to an earlier slot's is a
    failure (not an independent program), but its transcript+gate are still
    archived (all attempts archived)."""
    from experiment_bot.behavior.gen_cli import generate_programs
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"] * 2)
    passed, failures = asyncio.run(generate_programs(
        "http://x", "toy", client, n_programs=2, out_root=tmp_path))
    assert len(passed) == 1
    assert len(failures) == 1 and "not independent" in failures[0]
    out = tmp_path / "toy"
    assert len(list(out.glob("*.py"))) == 1  # same content -> same path
    assert len(list(out.glob("*.transcript.json"))) == 2
    assert len(list(out.glob("*.simgate.json"))) == 2


def test_cli_exits_nonzero_when_fewer_than_k_pass(monkeypatch):
    from click.testing import CliRunner
    import experiment_bot.behavior.gen_cli as g
    monkeypatch.setattr(g, "build_default_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(g, "generate_programs",
                        AsyncMock(return_value=([Path("a.py")], ["program 1: gate"])))
    result = CliRunner().invoke(
        g.main, ["http://x", "--label", "toy", "--n-programs", "2"])
    assert result.exit_code != 0
    assert "PASS -> a.py" in result.output


def test_cli_exits_zero_when_all_k_pass(monkeypatch):
    from click.testing import CliRunner
    import experiment_bot.behavior.gen_cli as g
    monkeypatch.setattr(g, "build_default_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(g, "generate_programs",
                        AsyncMock(return_value=([Path("a.py"), Path("b.py")], [])))
    result = CliRunner().invoke(
        g.main, ["http://x", "--label", "toy", "--n-programs", "2"])
    assert result.exit_code == 0
    assert "PASS -> a.py" in result.output and "PASS -> b.py" in result.output


# --- Final-review N1/N2: real committed TaskCards through the real loader ---
# The dict-shaped mocks above hid two generation-path crashes: typed
# StimulusConfig objects yielded zero conditions, and the stroop cards'
# empty-string detection_condition spliced a false interrupt note into the
# prompt. These tests pin the real-card contract.

def test_mechanical_facts_real_stroop_card():
    from experiment_bot.taskcard.loader import load_by_hash
    card = load_by_hash(Path("taskcards"), label="expfactory_stroop",
                        sha256="45751cfe")
    facts = mechanical_facts(card)
    assert "congruent" in facts["conditions"]
    assert "incongruent" in facts["conditions"]
    # Stroop has no interrupt signal; its card carries detection_condition ""
    # which must normalize to None, never True.
    assert facts["interrupt_condition"] is None
    assert facts["has_interrupt"] is False


def test_mechanical_facts_real_stop_signal_card():
    from experiment_bot.taskcard.loader import load_by_hash
    card = load_by_hash(Path("taskcards"), label="expfactory_stop_signal",
                        sha256="e29f22de")
    facts = mechanical_facts(card)
    assert "go" in facts["conditions"]
    assert facts["interrupt_condition"] == "stop"
    assert facts["has_interrupt"] is True


def test_available_keys_real_cards():
    from experiment_bot.cli import _available_keys_from_taskcard
    from experiment_bot.taskcard.loader import load_by_hash
    dyn = load_by_hash(Path("taskcards"), label="expfactory_stroop",
                       sha256="45751cfe")
    cog = load_by_hash(Path("taskcards"), label="cognitionrun_stroop",
                       sha256="b16c7891")
    # All-dynamic card: empty static inventory (keys observed at runtime).
    assert all(k not in ("dynamic", "dynamic_mapping")
               for k in _available_keys_from_taskcard(dyn))
    assert {"b", "g", "r", "y"}.issubset(set(_available_keys_from_taskcard(cog)))


# --- Wave A4a: gen_cli replays the pilot-observed condition stream ---

def _capture_run_gate(monkeypatch):
    import experiment_bot.behavior.gen_cli as g
    captured = {}
    real_report = MagicMock()
    real_report.passed = True
    real_report.to_dict.return_value = {"passed": True}

    def _fake_run_gate(prog, **kwargs):
        captured.update(kwargs)
        return real_report
    monkeypatch.setattr(g, "run_gate", _fake_run_gate)
    return captured


def test_generate_passes_pilot_condition_stream_to_gate(tmp_path, monkeypatch):
    """When the card's pilot artifacts include pilot_observations.json, the
    gate replays that observed sequence."""
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    captured = _capture_run_gate(monkeypatch)
    taskcards_dir = tmp_path / "taskcards"
    (taskcards_dir / "toy").mkdir(parents=True)
    (taskcards_dir / "toy" / "pilot_observations.json").write_text(
        json.dumps({"condition_stream": ["go", "go", "go"]}))
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    asyncio.run(generate("http://x", "toy", client, out_root=tmp_path / "prog",
                        taskcards_dir=str(taskcards_dir)))
    assert captured["condition_stream"] == ["go", "go", "go"]


def test_generate_passes_response_elements_to_gate(tmp_path, monkeypatch):
    """Wave B1: the card's click-response option labels reach run_gate."""
    _fake_scrape(monkeypatch)
    import experiment_bot.behavior.gen_cli as g
    tc = MagicMock()
    tc.task_specific = {"key_map": {}}
    tc.stimuli = [{"response": {"condition": "choice", "key": None,
                                "response_elements": [
                                    {"label": "Left", "selector": "#l"}]}}]
    tc.runtime.trial_interrupt.detection_condition = None
    tc.to_dict.return_value = {}
    monkeypatch.setattr(g, "_load_structural_taskcard", MagicMock(return_value=tc))
    captured = _capture_run_gate(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    asyncio.run(generate("http://x", "toy", client, out_root=tmp_path / "prog",
                        taskcards_dir=str(tmp_path / "taskcards")))
    assert captured["response_elements"] == {"choice": ["Left"]}


def test_mechanical_facts_collects_correct_sequence():
    """Sequence-response: a click-response stimulus that also exposes
    correct_sequence_js contributes a plausible target index sequence
    (0..N-1 over its options) so the gate can synthesize sequence trials."""
    tc = MagicMock()
    tc.task_specific = {"key_map": {}}
    tc.stimuli = [
        {"response": {"condition": "recall", "key": None,
                      "response_elements": [
                          {"label": "A", "selector": "#a"},
                          {"label": "B", "selector": "#b"},
                          {"label": "C", "selector": "#c"}],
                      "correct_sequence_js": "window.targetOrder"}},
        {"response": {"condition": "choice", "key": None,
                      "response_elements": [
                          {"label": "L", "selector": "#l"}]}},
    ]
    tc.runtime.trial_interrupt.detection_condition = None
    facts = mechanical_facts(tc)
    assert facts["correct_sequence"] == {"recall": [0, 1, 2]}


def test_mechanical_facts_global_correct_sequence_js():
    """A global task_specific.correct_sequence_js flags every click-response
    condition as a sequence trial."""
    tc = MagicMock()
    tc.task_specific = {"key_map": {}, "correct_sequence_js": "window.order"}
    tc.stimuli = [
        {"response": {"condition": "recall", "key": None,
                      "response_elements": [
                          {"label": "A", "selector": "#a"},
                          {"label": "B", "selector": "#b"}]}},
    ]
    tc.runtime.trial_interrupt.detection_condition = None
    facts = mechanical_facts(tc)
    assert facts["correct_sequence"] == {"recall": [0, 1]}


def test_mechanical_facts_no_correct_sequence_by_default():
    tc = MagicMock()
    tc.task_specific = {"key_map": {"go": "z"}}
    tc.stimuli = [{"response": {"condition": "go", "key": "z"}}]
    tc.runtime.trial_interrupt.detection_condition = None
    facts = mechanical_facts(tc)
    assert facts["correct_sequence"] == {}


def test_generate_passes_correct_sequence_to_gate(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch)
    import experiment_bot.behavior.gen_cli as g
    tc = MagicMock()
    tc.task_specific = {"key_map": {}}
    tc.stimuli = [{"response": {"condition": "recall", "key": None,
                                "response_elements": [
                                    {"label": "A", "selector": "#a"},
                                    {"label": "B", "selector": "#b"}],
                                "correct_sequence_js": "window.order"}}]
    tc.runtime.trial_interrupt.detection_condition = None
    tc.to_dict.return_value = {}
    monkeypatch.setattr(g, "_load_structural_taskcard", MagicMock(return_value=tc))
    captured = _capture_run_gate(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    asyncio.run(generate("http://x", "toy", client, out_root=tmp_path / "prog",
                        taskcards_dir=str(tmp_path / "taskcards")))
    assert captured["correct_sequence"] == {"recall": [0, 1]}


def test_generate_condition_stream_none_without_sidecar(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    captured = _capture_run_gate(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    asyncio.run(generate("http://x", "toy", client, out_root=tmp_path / "prog",
                        taskcards_dir=str(tmp_path / "taskcards")))
    assert captured.get("condition_stream") is None


def test_generate_filters_unknown_conditions_from_stream(tmp_path, monkeypatch):
    """Sidecar labels not in the card's condition vocabulary are dropped
    (e.g. structural-only conditions the gate isn't briefed on)."""
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    captured = _capture_run_gate(monkeypatch)
    taskcards_dir = tmp_path / "taskcards"
    (taskcards_dir / "toy").mkdir(parents=True)
    (taskcards_dir / "toy" / "pilot_observations.json").write_text(
        json.dumps({"condition_stream": ["go", "navigation", "go"]}))
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    asyncio.run(generate("http://x", "toy", client, out_root=tmp_path / "prog",
                        taskcards_dir=str(taskcards_dir)))
    assert captured["condition_stream"] == ["go", "go"]
