import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from click.testing import CliRunner
from experiment_bot.cli import main


def _minimal_taskcard_payload():
    return {
        "schema_version": "2.0",
        "produced_by": {"model": "x", "prompt_sha256": "", "scraper_version": "1.0",
                        "source_sha256": "", "timestamp": "2026-04-23T12:00:00Z",
                        "taskcard_sha256": ""},
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [], "navigation": {"phases": []}, "runtime": {},
        "task_specific": {}, "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500.0, "sigma": 60.0, "tau": 80.0},
                "rationale": "",
            }
        },
        "temporal_effects": {}, "between_subject_jitter": {},
        "reasoning_chain": [], "pilot_validation": {},
    }


def test_cli_loads_taskcard_and_runs_executor(tmp_path):
    runner = CliRunner()

    fake_taskcard_path = tmp_path / "taskcards" / "stroop"
    fake_taskcard_path.mkdir(parents=True)
    (fake_taskcard_path / "abcd1234.json").write_text(
        json.dumps(_minimal_taskcard_payload())
    )

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock()

    fake_client = MagicMock()
    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor), \
         patch("experiment_bot.cli.build_default_client", return_value=fake_client):
        result = runner.invoke(main, [
            "http://example.com/stroop",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
        ])
    assert result.exit_code == 0, result.output
    fake_executor.run.assert_awaited_once_with("http://example.com/stroop")


def test_cli_errors_on_missing_taskcard(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, [
        "http://example.com/x",
        "--label", "nonexistent",
        "--taskcards-dir", str(tmp_path / "empty_taskcards"),
        "--headless",
    ])
    assert result.exit_code != 0
    assert "TaskCard" in result.output or "not found" in result.output.lower()


def test_cli_samples_session_params_at_start(tmp_path):
    """Session-level draw of mu/sigma/tau happens before executor runs."""
    runner = CliRunner()
    fake_taskcard_path = tmp_path / "taskcards" / "stroop"
    fake_taskcard_path.mkdir(parents=True)
    (fake_taskcard_path / "abcd1234.json").write_text(
        json.dumps(_minimal_taskcard_payload())
    )

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock()

    sampled_params = {"default": {"mu": 510.0, "sigma": 65.0, "tau": 85.0}}
    fake_client = MagicMock()
    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor) as exec_cls, \
         patch("experiment_bot.cli.sample_session_params",
               return_value=sampled_params) as samp, \
         patch("experiment_bot.cli.build_default_client", return_value=fake_client):
        result = runner.invoke(main, [
            "http://example.com/x",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
            "--seed", "12345",
        ])
    assert result.exit_code == 0, result.output
    samp.assert_called_once()
    # Session_seed and session_params must reach the executor so they
    # land in run_metadata.json — that's what makes a run reproducible.
    _, kwargs = exec_cls.call_args
    assert kwargs.get("seed") == 12345
    assert kwargs.get("session_params") == sampled_params


def test_cli_no_calibration_flag_disables_calibration(tmp_path):
    """--no-calibration threads calibrate=False into the executor."""
    label_dir = tmp_path / "taskcards" / "stroop"
    label_dir.mkdir(parents=True)
    (label_dir / "abcd1234.json").write_text(json.dumps(_minimal_taskcard_payload()))
    fake_executor = MagicMock()
    fake_executor.run = AsyncMock()
    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor) as exec_cls, \
         patch("experiment_bot.cli.build_default_client", return_value=MagicMock()):
        result = CliRunner().invoke(main, [
            "http://example.com/stroop", "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"), "--headless",
            "--no-calibration",
        ])
    assert result.exit_code == 0, result.output
    assert exec_cls.call_args.kwargs.get("calibrate") is False
    # default (no flag) leaves calibration on
    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor) as exec_cls2, \
         patch("experiment_bot.cli.build_default_client", return_value=MagicMock()):
        CliRunner().invoke(main, [
            "http://example.com/stroop", "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"), "--headless",
        ])
    assert exec_cls2.call_args.kwargs.get("calibrate") is True


def test_cli_replay_by_hash_loads_exact_card(tmp_path):
    """--taskcard-sha256 routes through load_by_hash to the exact recorded card."""
    from experiment_bot.taskcard.hashing import taskcard_sha256

    label_dir = tmp_path / "taskcards" / "stroop"
    label_dir.mkdir(parents=True)
    payload = _minimal_taskcard_payload()
    h = taskcard_sha256(payload)
    payload["produced_by"]["taskcard_sha256"] = h
    (label_dir / f"{h[:8]}.json").write_text(json.dumps(payload))
    # A second, newer card so load_latest (mtime) would pick the WRONG one;
    # the hash must override that.
    other = _minimal_taskcard_payload()
    other["task"]["name"] = "stroop_variant"
    (label_dir / "ffffffff.json").write_text(json.dumps(other))

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock()
    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor), \
         patch("experiment_bot.cli.build_default_client", return_value=MagicMock()):
        result = runner_invoke = CliRunner().invoke(main, [
            "http://example.com/stroop",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--taskcard-sha256", h[:8],
            "--headless",
        ])
    assert result.exit_code == 0, result.output
    fake_executor.run.assert_awaited_once()


def test_cli_replay_by_hash_unknown_hash_errors(tmp_path):
    """A bad --taskcard-sha256 fails via load_by_hash (not the mtime path)."""
    label_dir = tmp_path / "taskcards" / "stroop"
    label_dir.mkdir(parents=True)
    (label_dir / "abcd1234.json").write_text(json.dumps(_minimal_taskcard_payload()))

    result = CliRunner().invoke(main, [
        "http://example.com/stroop",
        "--label", "stroop",
        "--taskcards-dir", str(tmp_path / "taskcards"),
        "--taskcard-sha256", "deadbeefdeadbeef",
        "--headless",
    ])
    assert result.exit_code != 0
    assert "content hash" in result.output.lower()


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "experiment-bot" in result.output.lower() or "usage" in result.output.lower()


def test_cli_shows_url_argument():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "url" in result.output.lower()


def test_cli_shows_label_option():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--label" in result.output


def test_cli_missing_url():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code != 0  # Should fail without URL


# --- SP21: --behavior-program wiring ---
from experiment_bot.cli import _available_keys_from_taskcard


def test_available_keys_from_taskcard():
    class _TC:
        task_specific = {"key_map": {"go": "z", "stop": "withhold"}}
        stimuli = [{"response": {"key": "m", "condition": "go"}},
                   {"response": {"key": None, "condition": "stop"}}]
    keys = _available_keys_from_taskcard(_TC())
    assert set(keys) == {"z", "m"}  # withhold sentinels and None excluded


def test_available_keys_from_taskcard_excludes_dynamic_sentinel():
    """C1: 'dynamic'/'dynamic_mapping' key_map values (executor sentinels for
    per-trial JS key resolution) must not leak into the static key inventory,
    case-insensitively."""
    class _TC:
        task_specific = {"key_map": {"go": "dynamic", "stop": "Dynamic_Mapping"}}
        stimuli = [{"response": {"key": "DYNAMIC", "condition": "go"}},
                   {"response": {"key": "m", "condition": "stop"}}]
    keys = _available_keys_from_taskcard(_TC())
    assert set(keys) == {"m"}


def test_behavior_program_flag_builds_session(tmp_path):
    prog = tmp_path / "p.py"
    prog.write_text(Path("tests/fixtures/toy_participant.py").read_text())

    captured = {}

    class _FakeExecutor:
        def __init__(self, *a, **kw):
            captured.update(kw)

        async def run(self, url):
            return None

    with patch("experiment_bot.cli.TaskExecutor", _FakeExecutor), \
         patch("experiment_bot.cli.load_latest") as load_tc, \
         patch("experiment_bot.cli.sample_session_params", return_value={}), \
         patch("experiment_bot.cli.build_default_client", return_value=None):
        load_tc.return_value = MagicMock(
            task_specific={"key_map": {"go": "z"}}, stimuli=[],
            response_distributions={}, to_dict=lambda: {})
        result = CliRunner().invoke(main, [
            "http://x", "--label", "t", "--headless", "--seed", "7",
            "--no-llm-client", "--behavior-program", str(prog)])
    assert result.exit_code == 0, result.output
    bp = captured["behavior_provider"]
    assert bp is not None and bp.seed == 7
