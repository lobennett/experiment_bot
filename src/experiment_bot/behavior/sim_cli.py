"""experiment-bot-naive-sim: run the mechanical gate on a program."""
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
@click.option("--has-interrupt", is_flag=True, default=False,
              help="Deprecated alone; implied by --interrupt-condition. Kept for "
                   "backward compatibility with existing invocations.")
@click.option("--interrupt-condition", "interrupt_condition", default=None,
              help="Condition label whose trials fire on_interrupt (implies "
                   "--has-interrupt).")
@click.option("--trials", default=1000, show_default=True)
@click.option("--response-elements", "response_elements_json", default=None,
              help='JSON condition->[option labels] map for click-response '
                   'tasks, e.g. \'{"choice": ["Left", "Right"]}\'')
@click.option("--correct-sequence", "correct_sequence_json", default=None,
              help='JSON condition->[target element indices] map for '
                   'sequence-response tasks, e.g. \'{"recall": [0, 1, 2]}\'. '
                   'Carried into ctx.correct_sequence for those conditions.')
def main(program: Path, conditions: str, key_map_json: str,
         has_interrupt: bool, interrupt_condition: str | None, trials: int,
         response_elements_json: str | None,
         correct_sequence_json: str | None):
    """Mechanical simulation gate; writes <sha>.simgate.json next to PROGRAM."""
    has_interrupt = has_interrupt or interrupt_condition is not None
    report = run_gate(program, conditions=conditions.split(","),
                      key_map=json.loads(key_map_json),
                      has_interrupt=has_interrupt, n_trials=trials,
                      interrupt_condition=interrupt_condition,
                      response_elements=(json.loads(response_elements_json)
                                         if response_elements_json else None),
                      correct_sequence=(json.loads(correct_sequence_json)
                                        if correct_sequence_json else None))
    out = program.parent / f"{report.program_sha256}.simgate.json"
    out.write_text(json.dumps(report.to_dict(), indent=2))
    click.echo(f"{'PASS' if report.passed else 'FAIL'} -> {out}")
    if not report.passed:
        for f in report.failures:
            click.echo(f"  - {f}")
        raise SystemExit(1)
