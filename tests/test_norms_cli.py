import json
from pathlib import Path
from unittest.mock import patch, AsyncMock
from click.testing import CliRunner
from experiment_bot.reasoner.norms_cli import main as norms_main


def test_norms_cli_writes_norms_file(tmp_path):
    runner = CliRunner()
    fake_norms = {
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {
                "mu_range": [430, 580],
                "sigma_range": [40, 90],
                "tau_range": [50, 130],
                "citations": [{"doi": "10.0/x", "authors": "Whelan", "year": 2008,
                                "title": "x", "table_or_figure": "T1", "page": 1,
                                "quote": "...", "confidence": "high"}],
            }
        },
    }
    with patch("experiment_bot.reasoner.norms_cli.build_default_client",
               return_value=object()), \
         patch("experiment_bot.reasoner.norms_cli.extract_norms",
               new=AsyncMock(return_value=fake_norms)):
        result = runner.invoke(norms_main, [
            "--paradigm-class", "conflict",
            "--norms-dir", str(tmp_path),
        ])
    assert result.exit_code == 0, result.output
    out_path = tmp_path / "conflict.json"
    assert out_path.exists()
    saved = json.loads(out_path.read_text())
    assert saved["paradigm_class"] == "conflict"
