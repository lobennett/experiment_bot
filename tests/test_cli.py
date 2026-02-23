from click.testing import CliRunner
from experiment_bot.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "experiment-bot" in result.output.lower() or "usage" in result.output.lower()


def test_expfactory_help():
    runner = CliRunner()
    result = runner.invoke(main, ["expfactory", "--help"])
    assert result.exit_code == 0
    assert "--task" in result.output


def test_psytoolkit_help():
    runner = CliRunner()
    result = runner.invoke(main, ["psytoolkit", "--help"])
    assert result.exit_code == 0
    assert "--task" in result.output


def test_missing_task_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["expfactory"])
    assert result.exit_code != 0  # Should fail without --task
