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
    monkeypatch.setattr(g, "_load_structural_taskcard",
                        MagicMock(return_value=tc))


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


def test_generate_retries_on_gate_failure_then_fails(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    crash = "def make_participant(seed):\n    raise ValueError('boom')\n"
    client = _fake_client([f"```python\n{crash}```"] * 3)
    with pytest.raises(RuntimeError, match="gate"):
        asyncio.run(generate("http://x", "toy", client, out_root=tmp_path))
    assert client.complete.await_count == 3  # initial + 2 retries, all archived
    assert len(list((tmp_path / "toy").glob("*.transcript.json"))) == 3
