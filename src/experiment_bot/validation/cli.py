"""experiment-bot-validate: score bot sessions against published canonical norms."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import click

from experiment_bot.validation.oracle import validate_session_set
from experiment_bot.validation.platform_adapters import adapter_for_label


def _load_cse_labels(taskcards_dir: Path, label: str) -> tuple[str, str] | None:
    """Read TaskCard for `label`, extract CSE high/low conflict labels if present.

    Returns None if the TaskCard doesn't exist, doesn't have CSE configured,
    or doesn't supply both labels — the oracle will fall back to defaults.
    """
    try:
        from experiment_bot.taskcard.loader import load_latest
        tc = load_latest(taskcards_dir, label)
    except FileNotFoundError:
        return None
    cse_pv = tc.temporal_effects.get("congruency_sequence")
    if cse_pv is None:
        return None
    cse_value = cse_pv.value if hasattr(cse_pv, "value") else cse_pv
    if not cse_value.get("enabled", False):
        return None
    high = cse_value.get("high_conflict_condition", "")
    low = cse_value.get("low_conflict_condition", "")
    if not high or not low:
        return None
    return (high, low)


@click.command()
@click.option("--paradigm-class", required=True, help="Paradigm class (conflict, interrupt, ...)")
@click.option("--label", required=True, help="TaskCard label (matches output/{label}/)")
@click.option("--norms-dir", default="norms", help="Directory holding norms/{class}.json files")
@click.option("--output-dir", default="output", help="Where session subfolders live")
@click.option("--taskcards-dir", default="taskcards", help="Where TaskCard JSONs live")
@click.option("--reports-dir", default="validation", help="Where to write JSON reports")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(paradigm_class, label, norms_dir, output_dir, taskcards_dir, reports_dir, verbose):
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

    cse_labels = _load_cse_labels(Path(taskcards_dir), label)
    trial_loader = adapter_for_label(label)
    if trial_loader is None:
        click.echo(
            f"WARNING: no platform-data adapter registered for label "
            f"'{label}'. Falling back to bot_log.json (may over-/under-"
            f"count platform trials). Add an adapter in "
            f"validation/platform_adapters.py to fix.",
            err=True,
        )
    else:
        click.echo(f"Using platform-data adapter for label '{label}'.")

    report = validate_session_set(
        paradigm_class=paradigm_class,
        session_dirs=session_dirs,
        norms=norms,
        cse_labels=cse_labels,
        trial_loader=trial_loader,
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
