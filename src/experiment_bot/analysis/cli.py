"""experiment-bot-per-subject: per-subject behavioral metric CSVs + a
human-readable comparison report, for external (cognitive-control) review.

Bot sessions and the Eisenberg-2019 human reference are passed through the
same estimators (see analysis/per_subject.py). One CSV row per subject; a
companion Markdown report positions the bot cohort within the human
between-subject distribution (z, within-1-SD), matching the abstract's design.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import click
import numpy as np

from experiment_bot.analysis import per_subject as ps


def _write_report(out: Path, label: str, kind: str, bot_df, human_df, human_csv: str) -> Path:
    metrics = ps.KIND_METRICS[kind]
    rows = ps.comparison_rows(bot_df, human_df, metrics)
    bot_n = len(bot_df)
    complete_n = int(bot_df["complete"].sum()) if "complete" in bot_df.columns else bot_n
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Per-subject behavioral comparison — {label}",
        "",
        f"_Generated {ts}. Bot N={bot_n} sessions ({complete_n} with the expected "
        f"trial count); human reference = `{human_csv}`._",
        "",
        "**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; "
        "SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = "
        "mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; "
        "lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use "
        "the identical functions.",
        "",
        "| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |",
        "|---|---|---|---|---|",
    ]
    def fmt(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "—"
        return f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}"
    for r in rows:
        zc = "—" if r["z"] is None or np.isnan(r["z"]) else f"{r['z']:+.2f}"
        mark = "—" if r["within_1sd"] is None else ("✅" if r["within_1sd"] else "❌")
        lines.append(
            f"| {r['metric']} | {fmt(r['bot_mean'])} ± {fmt(r['bot_sd'])} ({r['bot_n']}) "
            f"| {fmt(r['human_mean'])} ± {fmt(r['human_sd'])} ({r['human_n']}) | {zc} | {mark} |"
        )
    if kind == "stop_signal":
        in_band = int(human_df["stop_acc_in_band"].sum()) if "stop_acc_in_band" in human_df.columns else None
        lines += [
            "",
            "**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent "
            "product of the platform's SSD staircase, not a bot-controlled quantity. "
            f"Human QC: {in_band}/{len(human_df)} workers have p(respond|signal) within "
            "the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's "
            "N=447 used an exclusion that does not reproduce from this data — workers are "
            "exported unfiltered with the transparent flag.",
        ]
    lines += [
        "",
        "**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is "
        "reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the "
        "full distributions for any further test (KS / equivalence).",
        "",
        "## Exploratory: distribution-level comparison",
        "",
        "_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of "
        "the confirmatory mean-location design above. SD ratio = bot between-subject SD / "
        "human between-subject SD (1.0 = human-like dispersion); KS = two-sample "
        "Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the "
        "within-1-SD mean gate while failing these — matched means with far too little "
        "between-subject variability._",
        "",
        "| metric | SD ratio | KS D | KS p |",
        "|---|---|---|---|",
    ]
    def fmt_p(p):
        if p is None or (isinstance(p, float) and np.isnan(p)):
            return "—"
        return f"{p:.1e}" if p < 0.001 else f"{p:.3f}"
    for r in rows:
        lines.append(
            f"| {r['metric']} | {fmt(r['sd_ratio'])} | {fmt(r['ks_D'])} | {fmt_p(r['ks_p'])} |"
        )
    lines.append("")
    p = out / f"comparison_{label}.md"
    p.write_text("\n".join(lines))
    return p


def _run_one(label, output_dir, human_csv, out_dir):
    spec = ps.PARADIGMS[label]
    kind = spec["kind"]
    bot_df = ps.collect_bot_per_subject(Path(output_dir), label)
    human_df = ps.HUMAN_LOADER[kind](Path(human_csv))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bot_path = out_dir / f"per_subject_{label}_bot.csv"
    human_path = out_dir / f"per_subject_{kind}_human.csv"
    bot_df.to_csv(bot_path, index=False)
    human_df.to_csv(human_path, index=False)
    report = _write_report(out_dir, label, kind, bot_df, human_df, human_csv)
    return bot_df, human_df, bot_path, human_path, report


@click.command()
@click.option("--label", required=True,
              help="Paradigm label, or 'all'. One of: " + ", ".join(ps.PARADIGMS))
@click.option("--output-dir", default="output", help="Where bot session subfolders live")
@click.option("--human-stop", type=click.Path(path_type=Path), default=None,
              help="Eisenberg stop-signal trial-level CSV (for stop-signal labels)")
@click.option("--human-stroop", type=click.Path(path_type=Path), default=None,
              help="Eisenberg Stroop trial-level CSV (for Stroop labels)")
@click.option("--out-dir", default="analysis_out", help="Where to write CSVs + reports")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(label, output_dir, human_stop, human_stroop, out_dir, verbose):
    """Export per-subject metric CSVs + a bot-vs-human comparison report."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    labels = list(ps.PARADIGMS) if label == "all" else [label]
    if label != "all" and label not in ps.PARADIGMS:
        raise click.ClickException(f"Unknown label '{label}'. Choose from: {', '.join(ps.PARADIGMS)} or 'all'.")
    human_for = {"stop_signal": human_stop, "stroop": human_stroop}
    for lab in labels:
        kind = ps.PARADIGMS[lab]["kind"]
        hcsv = human_for[kind]
        if hcsv is None:
            raise click.ClickException(
                f"--human-{'stop' if kind == 'stop_signal' else 'stroop'} is required for label '{lab}'."
            )
        if not Path(hcsv).exists():
            raise click.ClickException(f"Human CSV not found: {hcsv}")
        bot_df, human_df, bp, hp, rep = _run_one(lab, output_dir, hcsv, out_dir)
        click.echo(f"[{lab}] bot N={len(bot_df)} → {bp.name}; human N={len(human_df)} → {hp.name}; report → {rep.name}")
    click.echo(f"Wrote to {out_dir}/")
