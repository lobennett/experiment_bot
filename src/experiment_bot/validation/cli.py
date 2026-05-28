"""experiment-bot-validate: score bot sessions against published canonical norms."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import click

from experiment_bot.validation.oracle import validate_session_set
from experiment_bot.validation.platform_adapters import adapter_for_label


def _load_lag1_contrast_labels(taskcards_dir: Path, label: str) -> tuple[str, str] | None:
    """Extract (high, low) condition labels from the TaskCard's
    `lag1_pair_modulation.modulation_table`, when configured.

    Generic over paradigm — the function reads whatever labels the
    Reasoner emits in the modulation_table, with no condition vocabulary
    baked in. The oracle passes these labels via `contrast_labels` to
    any 2-back contrast metric (e.g. the conflict-class `cse_magnitude`).
    Returns None when the TaskCard is absent, the mechanism is disabled,
    or the table doesn't define a clear (high-after-high, low-after-high)
    pair — the dependent metric then computes as NaN.

    Convention: the entry with `prev == curr` and a negative `delta_ms`
    identifies the high label (facilitation on repetition); the entry
    with `prev != curr` and a positive `delta_ms` identifies the low
    label (cost on alternation). Tables that don't follow this
    convention return None.
    """
    try:
        from experiment_bot.taskcard.loader import load_latest
        tc = load_latest(taskcards_dir, label)
    except FileNotFoundError:
        return None
    pv = tc.temporal_effects.get("lag1_pair_modulation")
    if pv is None:
        return None
    value = pv.value if hasattr(pv, "value") else pv
    if not value.get("enabled", False):
        return None
    table = value.get("modulation_table") or []
    high = None
    for entry in table:
        prev = entry.get("prev")
        curr = entry.get("curr")
        delta = entry.get("delta_ms")
        if prev is None or curr is None or delta is None:
            continue
        if prev == curr and delta < 0:
            high = curr
    if not high:
        return None
    # 'low' is the non-high condition label appearing in the table.
    # Previous logic scanned for "prev != curr and delta > 0" entries,
    # but symmetric tables have two such rows with opposite prev/curr,
    # and the last-write wins picked whichever came last. Take the
    # union of labels and pick the one that isn't `high`.
    labels = set()
    for entry in table:
        for key in ("prev", "curr"):
            v = entry.get(key)
            if v is not None:
                labels.add(v)
    low = next((l for l in labels if l != high), None)
    if not low:
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
@click.option(
    "--allow-bot-log",
    is_flag=True,
    default=False,
    help=(
        "Allow scoring against bot_log.json when no platform-data adapter is registered. "
        "CAUTION: the bot is grading its own homework — results are self-referential. "
        "The bypass is recorded in the report as data_source=bot_log_self_graded."
    ),
)
def main(paradigm_class, label, norms_dir, output_dir, taskcards_dir, reports_dir, verbose,
         allow_bot_log):
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

    contrast_labels = _load_lag1_contrast_labels(Path(taskcards_dir), label)
    trial_loader = adapter_for_label(label)
    if trial_loader is None:
        if not allow_bot_log:
            raise click.ClickException(
                f"No platform-data adapter is registered for label '{label}'. "
                f"Scoring against bot_log.json is REFUSED by default because the "
                f"bot would be grading its own homework — the same log used to drive "
                f"behavior is used to assess it, closing the anti-circularity loop (G4). "
                f"To fix: add an adapter in validation/platform_adapters.py that reads "
                f"the platform's experiment_data.{{csv,json}} export, or add a "
                f"data_capture config in the TaskCard so the executor writes it. "
                f"To bypass (self-graded, recorded in report): re-run with --allow-bot-log."
            )
        # Explicit bypass: bot_log fallback requested; stamp report so the bypass
        # is committed in the artifact, not just a transient stderr line.
        click.echo(
            f"WARNING: --allow-bot-log set for '{label}' (no platform-data adapter). "
            f"Scoring against bot_log.json — bot grades its own homework. "
            f"data_source will be recorded as bot_log_self_graded in the report.",
            err=True,
        )
        trial_source = "bot_log"
        report_data_source_override = "bot_log_self_graded"
    else:
        click.echo(f"Using platform-data adapter for label '{label}'.")
        trial_source = "platform_adapter"
        report_data_source_override = None

    report = validate_session_set(
        paradigm_class=paradigm_class,
        session_dirs=session_dirs,
        norms=norms,
        contrast_labels=contrast_labels,
        trial_loader=trial_loader,
        trial_source=trial_source,
    )

    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(reports_dir) / f"{label}_{ts}.json"
    out.write_text(json.dumps({
        "paradigm_class": report.paradigm_class,
        "overall_pass": report.overall_pass,
        "summary": report.summary,
        "n_supplied": report.n_supplied,
        "n_used": report.n_used,
        "excluded_sessions": report.excluded_sessions,
        # When --allow-bot-log was used, stamp "bot_log_self_graded" so the bypass
        # is recorded in the committed artifact (not just a transient stderr line).
        "data_source": report_data_source_override if report_data_source_override else report.data_source,
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
    if report.overall_pass is None:
        click.echo("Overall pass: unscored (no gating metric — descriptive-only class)")
    else:
        click.echo(f"Overall pass: {report.overall_pass}")
    for name, pillar in report.pillar_results.items():
        marker = "✅" if pillar.pass_ else "❌"
        click.echo(f"  {marker} {name}")
