"""experiment-bot-naive-sim: run the SP21 mechanical gate on a program."""
from __future__ import annotations

import json
from pathlib import Path

import click

from experiment_bot.behavior.simgate import run_gate


@click.command()
@click.argument("program", type=click.Path(exists=True, path_type=Path))
@click.option("--conditions", required=True,
              help="Comma-separated condition labels (structural facts)")
@click.option("--key-map", "key_map_json", required=True,
              help='JSON condition->key map, e.g. \'{"go": "z"}\'')
@click.option("--has-interrupt", is_flag=True, default=False)
@click.option("--trials", default=1000, show_default=True)
def main(program: Path, conditions: str, key_map_json: str,
         has_interrupt: bool, trials: int):
    """Mechanical simulation gate; writes <sha>.simgate.json next to PROGRAM."""
    report = run_gate(program, conditions=conditions.split(","),
                      key_map=json.loads(key_map_json),
                      has_interrupt=has_interrupt, n_trials=trials)
    out = program.parent / f"{report.program_sha256}.simgate.json"
    out.write_text(json.dumps(report.to_dict(), indent=2))
    click.echo(f"{'PASS' if report.passed else 'FAIL'} -> {out}")
    if not report.passed:
        for f in report.failures:
            click.echo(f"  - {f}")
        raise SystemExit(1)
