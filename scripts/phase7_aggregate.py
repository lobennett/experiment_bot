"""SP11 Phase 7 aggregator — paired-rate × within-pair-match × §6 gates.

Per Phase 7 user note 4: the headline statistic must be
`effective_fidelity = paired_rate × within_pair_match_rate`, NOT just
the within-pair match. The Phase 5a pilot demonstrated this gap:
118/120 paired (98.3%) × 118/118 within-pair (100%) = 98.3% effective
fidelity, not 100%. Phase 7 reports BOTH and their product per paradigm-
arm.

Inputs:
  - Sweep root with `<arm>/<paradigm>/<task_name>/<timestamp>/` sessions.
  - Each session contains `bot_log.json` + `experiment_data.{json,csv}`.

Output:
  - JSON summary at `docs/sp11-phase7-aggregate.json` and a Markdown
    report at `docs/sp11-phase7-deliverable.md` (or path passed via
    --report).

Usage:
  uv run python scripts/phase7_aggregate.py --sweep-root output/phase7
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


# Import the audit script as a module for shared pairing logic
def _load_audit_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_alignment", Path("scripts/audit_alignment.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def aggregate_arm(
    arm_dir: Path, paradigm: str, audit_module,
) -> dict[str, Any]:
    """Aggregate all sessions under arm_dir/paradigm/<task>/<timestamp>/.
    Returns {n_sessions, totals, per_session: [...]} with paired-rate
    and within-pair-match-rate quantified at session and arm levels."""
    paradigm_root = arm_dir / paradigm
    if not paradigm_root.exists():
        return {"paradigm": paradigm, "n_sessions": 0, "sessions": []}

    sessions: list[Path] = []
    for task_dir in paradigm_root.iterdir():
        if not task_dir.is_dir():
            continue
        for sess_dir in task_dir.iterdir():
            if sess_dir.is_dir() and (sess_dir / "bot_log.json").exists():
                sessions.append(sess_dir)

    per_session: list[dict] = []
    for sd in sorted(sessions):
        try:
            result = audit_module.audit_session(
                sd, label=paradigm, pairing="auto",
            )
        except SystemExit as e:
            # Predicate or pairing mismatch — skip session, record reason.
            per_session.append({"session": str(sd), "error": str(e)})
            continue
        counts = result.get("counts", {})
        method = result.get("method")
        if method == "trial_counter":
            total_bot_trials = result.get("total_bot_trials", 0)
            paired = counts.get("paired", 0)
            in_pair_ok = counts.get("pressed_eq_recorded", 0)
            paired_rate = (paired / total_bot_trials) if total_bot_trials else 0.0
            within_pair_rate = (in_pair_ok / paired) if paired else 0.0
            effective = paired_rate * within_pair_rate
            per_session.append({
                "session": sd.name,
                "method": method,
                "total_bot_trials": total_bot_trials,
                "total_plat_test": result.get("total_plat_test", 0),
                "paired": paired,
                "in_pair_ok": in_pair_ok,
                "paired_rate": paired_rate,
                "within_pair_rate": within_pair_rate,
                "effective_fidelity": effective,
                "per_channel": result.get("per_channel", {}),
            })
        else:
            total = counts.get("total", 0)
            matched = counts.get("matched", 0)
            in_pair_ok = counts.get("pressed_eq_recorded", 0)
            paired_rate = (matched / total) if total else 0.0
            within_pair_rate = (in_pair_ok / matched) if matched else 0.0
            effective = paired_rate * within_pair_rate
            per_session.append({
                "session": sd.name,
                "method": method,
                "total_plat_test": total,
                "matched": matched,
                "in_pair_ok": in_pair_ok,
                "paired_rate": paired_rate,
                "within_pair_rate": within_pair_rate,
                "effective_fidelity": effective,
                "per_channel": result.get("per_channel", {}),
            })

    ok_sessions = [s for s in per_session if "error" not in s]
    if not ok_sessions:
        return {
            "paradigm": paradigm,
            "n_sessions": 0,
            "n_errored": len(per_session) - len(ok_sessions),
            "sessions": per_session,
        }
    means = {
        "paired_rate_mean": sum(s["paired_rate"] for s in ok_sessions) / len(ok_sessions),
        "within_pair_rate_mean": sum(s["within_pair_rate"] for s in ok_sessions) / len(ok_sessions),
        "effective_fidelity_mean": sum(s["effective_fidelity"] for s in ok_sessions) / len(ok_sessions),
        "paired_rate_min": min(s["paired_rate"] for s in ok_sessions),
        "within_pair_rate_min": min(s["within_pair_rate"] for s in ok_sessions),
    }
    return {
        "paradigm": paradigm,
        "n_sessions": len(ok_sessions),
        "n_errored": len(per_session) - len(ok_sessions),
        "summary": means,
        "sessions": per_session,
    }


def render_markdown(
    sweep_root: Path,
    aggregates: dict[str, dict[str, Any]],
    *,
    h1_threshold: float = 0.85,
    h2_threshold: float = 0.75,
) -> str:
    """Render a Markdown report. Headlines:
      - paired_rate (mean across sessions)
      - within_pair_match_rate (mean)
      - effective_fidelity = paired_rate × within_pair_rate
      - §6 H1 (mean effective_fidelity ≥ 0.85) pass/fail
      - §6 H2 (per-paradigm effective_fidelity floor ≥ 0.75) pass/fail
    """
    lines = [
        "# SP11 Phase 7 results",
        "",
        f"**Sweep root:** `{sweep_root}`",
        "",
        "## Headline (per Phase 7 user note 4)",
        "",
        "Reported per paradigm-arm:",
        "- **paired_rate** = paired / total_bot_trials per session, mean across sessions",
        "- **within_pair_rate** = pressed_eq_recorded / paired per session, mean across sessions",
        "- **effective_fidelity** = paired_rate × within_pair_rate (the headline)",
        "",
        "| Paradigm | Arm | N | paired_rate | within_pair | effective_fidelity | H1 (≥0.85) | H2 floor (≥0.75) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for arm in ("pre_cal", "post_cal"):
        for paradigm in sorted(set(p for (p, a) in aggregates.keys() if a == arm)):
            agg = aggregates.get((paradigm, arm))
            if not agg or not agg.get("summary"):
                lines.append(f"| {paradigm} | {arm} | 0 | — | — | — | — | — |")
                continue
            s = agg["summary"]
            n = agg["n_sessions"]
            eff = s["effective_fidelity_mean"]
            h1 = "✓" if eff >= h1_threshold else "✗"
            min_eff_floor = s["paired_rate_min"] * s["within_pair_rate_min"]
            h2 = "✓" if min_eff_floor >= h2_threshold else "✗"
            lines.append(
                f"| {paradigm} | {arm} | {n} | {s['paired_rate_mean']:.3f} | "
                f"{s['within_pair_rate_mean']:.3f} | {eff:.3f} | "
                f"{h1} ({eff:.3f}) | {h2} ({min_eff_floor:.3f}) |"
            )
    lines.append("")
    lines.append("## Per-paradigm-arm details")
    for (paradigm, arm), agg in sorted(aggregates.items()):
        lines.append("")
        lines.append(f"### {paradigm} / {arm}")
        lines.append("")
        lines.append(f"- N sessions: {agg.get('n_sessions', 0)}")
        n_err = agg.get("n_errored", 0)
        if n_err:
            lines.append(f"- N errored: {n_err}")
        if agg.get("summary"):
            s = agg["summary"]
            lines.append(
                f"- paired_rate: mean {s['paired_rate_mean']:.3f}, "
                f"min {s['paired_rate_min']:.3f}"
            )
            lines.append(
                f"- within_pair_rate: mean {s['within_pair_rate_mean']:.3f}, "
                f"min {s['within_pair_rate_min']:.3f}"
            )
            lines.append(f"- effective_fidelity (mean): "
                         f"{s['effective_fidelity_mean']:.3f}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sweep-root", type=Path, default=Path("output/phase7"),
                   help="Sweep output root (default: output/phase7/).")
    p.add_argument("--report", type=Path,
                   default=Path("docs/sp11-phase7-results.md"),
                   help="Markdown report path.")
    p.add_argument("--json-out", type=Path,
                   default=Path("docs/sp11-phase7-aggregate.json"),
                   help="JSON aggregate dump path.")
    p.add_argument("--h1-threshold", type=float, default=0.85,
                   help="§6 H1 threshold for effective_fidelity (default: 0.85).")
    p.add_argument("--h2-threshold", type=float, default=0.75,
                   help="§6 H2 per-paradigm floor (default: 0.75).")
    p.add_argument("--paradigms", nargs="+", default=[
        "expfactory_stroop", "expfactory_stop_signal",
        "stopit_stop_signal", "cognitionrun_stroop",
    ])
    p.add_argument("--arms", nargs="+", default=["pre_cal", "post_cal"])
    args = p.parse_args(argv)

    audit_module = _load_audit_module()
    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    for arm in args.arms:
        arm_dir = args.sweep_root / arm
        for paradigm in args.paradigms:
            agg = aggregate_arm(arm_dir, paradigm, audit_module)
            aggregates[(paradigm, arm)] = agg
            print(f"  {paradigm}/{arm}: N={agg.get('n_sessions', 0)} "
                  f"(errored {agg.get('n_errored', 0)})")

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(
            {f"{p}/{a}": v for (p, a), v in aggregates.items()},
            indent=2, default=str,
        ) + "\n"
    )
    md = render_markdown(
        args.sweep_root, aggregates,
        h1_threshold=args.h1_threshold,
        h2_threshold=args.h2_threshold,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(md)
    print(f"[ok] wrote {args.json_out}")
    print(f"[ok] wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
