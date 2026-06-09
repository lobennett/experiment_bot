"""experiment-bot-compare: z-position bot sessions within a human reference
distribution (the paper abstract's analysis, in the tested package)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import click

from experiment_bot.validation.human_reference import (
    compare_metrics,
    load_human_reference,
)
from experiment_bot.validation.oracle import select_sessions
from experiment_bot.validation.platform_adapters import resolve_trial_loader


@click.command()
@click.option("--label", required=True, help="Session label (matches output/{label}/; selects the platform adapter)")
@click.option("--human-csv", required=True, type=click.Path(exists=True, path_type=Path),
              help="Human reference CSV (session-level summaries, e.g. data/human/stop_signal_rdoc.csv)")
@click.option("--map", "map_path", required=True, type=click.Path(exists=True, path_type=Path),
              help="Comparison map JSON (data/human/comparison_maps/*.json)")
@click.option("--metrics", default=None,
              help="Comma-separated subset of map metrics to compare (default: all). "
                   "Use when a platform's offline export can't support a metric "
                   "(e.g. cognition.run correctness is not recoverable offline).")
@click.option("--output-dir", default="output", help="Where session subfolders live")
@click.option("--taskcards-dir", default="taskcards",
              help="TaskCard dir; a card carrying runtime.platform_export overrides the hand-written adapter")
@click.option("--reports-dir", default="validation", help="Where to write the JSON report")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(label, human_csv, map_path, metrics, output_dir, taskcards_dir, reports_dir, verbose):
    """Compare bot sessions against a human reference distribution.

    For each mapped metric: bot per-session values are pooled into a cohort
    mean and z-positioned within the human between-session distribution
    (z = (bot_mean − human_mean) / human_sd). The human CSV's exclusion
    flags are applied automatically.
    """
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    trial_loader, loader_source = resolve_trial_loader(label, Path(taskcards_dir))
    if trial_loader is None:
        raise click.ClickException(
            f"No platform-data adapter registered for label '{label}' and no "
            f"TaskCard platform_export mapping found. The comparison scores "
            f"the platform's own export (G4); add an adapter in "
            f"validation/platform_adapters.py or regenerate the TaskCard."
        )
    if loader_source == "taskcard_platform_export":
        click.echo(f"Using TaskCard-declared platform_export mapping for label '{label}'.")

    label_dir = Path(output_dir) / label
    if not label_dir.exists():
        raise click.ClickException(f"No output dir: {label_dir}")
    session_dirs = sorted(p for p in label_dir.iterdir() if p.is_dir())
    if not session_dirs:
        raise click.ClickException(f"No session subdirs in {label_dir}")

    # Same cohort-selection rule as the oracle (zero-trial, gross-undercount,
    # .incomplete marker) so the comparison and the validation gate score the
    # SAME session set.
    session_dirs, excluded, _ = select_sessions(session_dirs, trial_loader)
    if excluded:
        click.echo(f"Excluded {len(excluded)} session(s) (same rule as the oracle): "
                   + "; ".join(e["session"] + " [" + e["reason"].split(":")[0] + "]" for e in excluded))
    if not session_dirs:
        raise click.ClickException("No usable sessions after cohort selection")

    human_rows = load_human_reference(human_csv)
    if not human_rows:
        raise click.ClickException(f"No usable rows in {human_csv} after exclusion filter")

    metrics_map = json.loads(Path(map_path).read_text())["metrics"]
    if metrics:
        wanted = {m.strip() for m in metrics.split(",") if m.strip()}
        unknown = wanted - set(metrics_map)
        if unknown:
            raise click.ClickException(f"Unknown metrics {sorted(unknown)}; map has {sorted(metrics_map)}")
        # subtract kinds reference other metrics; keep their operands too
        needed = set(wanted)
        for name in wanted:
            bot = metrics_map[name]["bot"]
            if bot["kind"] == "subtract":
                needed |= {bot["a"], bot["b"]}
        metrics_map = {k: v for k, v in metrics_map.items() if k in needed}
        reported = wanted
    else:
        reported = set(metrics_map)

    results = compare_metrics(session_dirs, trial_loader, human_rows, metrics_map)
    results = {k: v for k, v in results.items() if k in reported}

    click.echo(f"Human reference: {human_csv} ({len(human_rows)} sessions after exclusions)")
    click.echo(f"Bot sessions: {label_dir}")
    header = f"{'metric':<26}{'bot':>14}{'human':>20}{'z':>8}  within 1 SD"
    click.echo(header)
    click.echo("-" * len(header))
    def _fmt(v: float) -> str:
        # Rates/accuracies need more digits than RTs: 1 decimal would print
        # 0.521 as "0.5" and erase the comparison.
        return f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}"

    for name, r in results.items():
        if r["bot_mean"] is None or r["human_mean"] is None:
            click.echo(f"{name:<26}{'not computable':>14}")
            continue
        bot_s = f"{_fmt(r['bot_mean'])}±{_fmt(r['bot_sd'])}" if r["bot_sd"] is not None else _fmt(r["bot_mean"])
        hum_s = f"{_fmt(r['human_mean'])}±{_fmt(r['human_sd'])}" if r["human_sd"] is not None else _fmt(r["human_mean"])
        z_s = f"{r['z']:+.2f}" if r["z"] is not None else "n/a"
        mark = "✅" if r["within_1sd"] else ("❌" if r["within_1sd"] is False else "—")
        click.echo(f"{name:<26}{bot_s:>14}{hum_s:>20}{z_s:>8}  {mark}")

    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(reports_dir) / f"compare_{label}_{ts}.json"
    out.write_text(json.dumps({
        "label": label,
        "human_csv": str(human_csv),
        "human_n_after_exclusions": len(human_rows),
        "map": str(map_path),
        "results": results,
    }, indent=2))
    click.echo(f"Comparison report: {out}")
