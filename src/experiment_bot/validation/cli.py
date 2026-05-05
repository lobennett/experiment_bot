"""experiment-bot-validate: score bot sessions against published canonical norms."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import click

from experiment_bot.validation.oracle import validate_session_set


@click.command()
@click.option("--paradigm-class", required=True, help="Paradigm class (conflict, interrupt, ...)")
@click.option("--label", required=True, help="TaskCard label (matches output/{label}/)")
@click.option("--norms-dir", default="norms", help="Directory holding norms/{class}.json files")
@click.option("--output-dir", default="output", help="Where session subfolders live")
@click.option("--reports-dir", default="validation", help="Where to write JSON reports")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(paradigm_class, label, norms_dir, output_dir, reports_dir, verbose):
    """Score bot sessions against published canonical norms; write a report."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    norms_path = Path(norms_dir) / f"{paradigm_class}.json"
    if not norms_path.exists():
        raise click.ClickException(
            f"No norms file at {norms_path}. Run "
            f"`experiment-bot-extract-norms --paradigm-class {paradigm_class}` first."
        )
    norms = json.loads(norms_path.read_text())

    label_dir = Path(output_dir) / label
    if not label_dir.exists():
        raise click.ClickException(f"No output dir: {label_dir}")
    session_dirs = sorted([p for p in label_dir.iterdir() if p.is_dir()])
    if not session_dirs:
        raise click.ClickException(f"No session subdirs in {label_dir}")

    report = validate_session_set(
        paradigm_class=paradigm_class,
        session_dirs=session_dirs,
        norms=norms,
    )

    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(reports_dir) / f"{label}_{ts}.json"
    out.write_text(json.dumps({
        "paradigm_class": report.paradigm_class,
        "overall_pass": report.overall_pass,
        "summary": report.summary,
        "pillar_results": {
            name: {
                "pass": pillar.pass_,
                "metrics": {
                    mname: {
                        "bot_value": m.bot_value,
                        "published_range": list(m.published_range) if m.published_range else None,
                        "pass": m.pass_,
                    } for mname, m in pillar.metrics.items()
                }
            } for name, pillar in report.pillar_results.items()
        }
    }, indent=2))

    click.echo(f"Validation report: {out}")
    click.echo(f"Overall pass: {report.overall_pass}")
    for name, pillar in report.pillar_results.items():
        marker = "✅" if pillar.pass_ else "❌"
        click.echo(f"  {marker} {name}")
