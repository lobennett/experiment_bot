import json
from pathlib import Path
from unittest.mock import patch, AsyncMock
from click.testing import CliRunner
from experiment_bot.reasoner.cli import main


def test_reason_cli_writes_taskcard(tmp_path):
    runner = CliRunner()
    fake_partial = {
        "schema_version": "2.0",
        "produced_by": {"model": "claude-opus-4-7", "prompt_sha256": "p",
                        "scraper_version": "1.0.0", "source_sha256": "s",
                        "timestamp": "2026-04-23T12:00:00Z", "taskcard_sha256": ""},
        "task": {"name": "x", "constructs": [], "reference_literature": []},
        "stimuli": [], "navigation": {"phases": []}, "runtime": {},
        "task_specific": {}, "performance": {"accuracy": {"d": 0.9}},
        "response_distributions": {}, "temporal_effects": {},
        "between_subject_jitter": {}, "reasoning_chain": [],
        "pilot_validation": {},
    }

    class FakeBundle:
        url = "http://x"
        source_files = {}
        description_text = ""
        hint = ""
        metadata = {}

    with patch("experiment_bot.reasoner.cli.scrape_experiment_source",
               new=AsyncMock(return_value=FakeBundle())), \
         patch("experiment_bot.reasoner.cli.build_default_client",
               return_value=object()), \
         patch("experiment_bot.reasoner.cli.ReasonerPipeline") as Pipe:
        instance = Pipe.return_value
        instance.run = AsyncMock(return_value=fake_partial)
        result = runner.invoke(main, [
            "http://x", "--label", "stroop", "--taskcards-dir", str(tmp_path),
        ])
    assert result.exit_code == 0, result.output
    files = list((tmp_path / "stroop").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["task"]["name"] == "x"


def test_reason_cli_wraps_partial_when_envelope_missing(tmp_path):
    runner = CliRunner()
    # Partial with NO schema_version / produced_by / reasoning_chain — Reasoner
    # output that hasn't been envelope-wrapped yet. CLI should add the envelope.
    bare_partial = {
        "task": {"name": "x", "constructs": [], "reference_literature": []},
        "stimuli": [], "navigation": {"phases": []}, "runtime": {},
        "task_specific": {}, "performance": {"accuracy": {"d": 0.9}},
        "response_distributions": {}, "temporal_effects": {},
        "between_subject_jitter": {},
    }

    class FakeBundle:
        url = "http://x"
        source_files = {}
        description_text = ""
        hint = ""
        metadata = {}

    with patch("experiment_bot.reasoner.cli.scrape_experiment_source",
               new=AsyncMock(return_value=FakeBundle())), \
         patch("experiment_bot.reasoner.cli.build_default_client",
               return_value=object()), \
         patch("experiment_bot.reasoner.cli.ReasonerPipeline") as Pipe:
        instance = Pipe.return_value
        instance.run = AsyncMock(return_value=bare_partial)
        result = runner.invoke(main, [
            "http://x", "--label", "stroop", "--taskcards-dir", str(tmp_path),
        ])
    assert result.exit_code == 0, result.output
    saved = json.loads(next((tmp_path / "stroop").glob("*.json")).read_text())
    assert saved["schema_version"] == "2.0"
    assert "produced_by" in saved


def test_reason_cli_writes_reasoning_chain_to_taskcard(tmp_path):
    runner = CliRunner()
    fake_partial = {
        "task": {"name": "x", "constructs": [], "reference_literature": []},
        "stimuli": [], "navigation": {"phases": []}, "runtime": {},
        "task_specific": {}, "performance": {"accuracy": {"d": 0.9}},
        "response_distributions": {}, "temporal_effects": {},
        "between_subject_jitter": {},
        "_reasoning_chain": [
            {"step": "stage1_structural", "inference": "stroop", "evidence_lines": [], "confidence": "high", "input_hash": ""},
            {"step": "stage2_behavioral", "inference": "ex-gauss", "evidence_lines": [], "confidence": "medium", "input_hash": ""},
        ],
    }

    class FakeBundle:
        url = "http://x"
        source_files = {}
        description_text = ""
        hint = ""
        metadata = {}

    with patch("experiment_bot.reasoner.cli.scrape_experiment_source",
               new=AsyncMock(return_value=FakeBundle())), \
         patch("experiment_bot.reasoner.cli.build_default_client",
               return_value=object()), \
         patch("experiment_bot.reasoner.cli.ReasonerPipeline") as Pipe:
        instance = Pipe.return_value
        instance.run = AsyncMock(return_value=fake_partial)
        result = runner.invoke(main, [
            "http://x", "--label", "stroop", "--taskcards-dir", str(tmp_path),
        ])
    assert result.exit_code == 0, result.output
    saved = json.loads(next((tmp_path / "stroop").glob("*.json")).read_text())
    assert len(saved["reasoning_chain"]) == 2
    assert saved["reasoning_chain"][0]["step"] == "stage1_structural"
