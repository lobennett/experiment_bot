from click.testing import CliRunner
from experiment_bot.cli import main


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


def test_cli_shows_hint_option():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--hint" in result.output


def test_cli_missing_url():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code != 0  # Should fail without URL
