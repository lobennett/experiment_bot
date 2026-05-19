"""SP11 Phase 7 sweep wrapper — N=30 sequential measurement runs.

Runs the executor across 4 paradigms × 2 calibration arms with retry,
failure-logging, and bot_no_match-rate gating. Per Phase 7 user note 1:

- Target SUCCESSFUL N=30 per paradigm-arm, not attempted N=30.
- Retry up to 3 times before declaring a session failed.
- Discard-and-rerun on `bot_no_match / total_bot > 10%` per session.
- Log every failure reason to `output/phase7/<arm>/session_failures.json`.
- Hard wall-time stop at 48 hr (pause and ask before exceeding).

Per Phase 7 user note 2 (baselines) and note 4 (paired-rate × within-pair),
the post-sweep aggregator (`scripts/phase7_aggregate.py`) is a separate
piece — this script just runs the sessions.

Usage:
  uv run python scripts/phase7_sweep.py \\
      --n 30 --hard-walltime-h 48 \\
      [--paradigm expfactory_stroop] [--arm post_cal]
  # default: all paradigms × both arms
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


PARADIGM_URLS: dict[str, str] = {
    "expfactory_stroop": "https://deploy.expfactory.org/preview/10/",
    "expfactory_stop_signal": "https://deploy.expfactory.org/preview/9/",
    "stopit_stop_signal": (
        "https://kywch.github.io/STOP-IT/jsPsych_version/"
        "experiment-transformed-first.html"
    ),
    "cognitionrun_stroop": "https://strooptest.cognition.run/",
}


@dataclass
class SessionAttempt:
    """One concrete try at running a single session."""
    paradigm: str
    arm: str
    attempt: int
    session_dir: str | None = None
    status: str = "pending"  # "ok" / "executor_error" / "bot_no_match_threshold"
    bot_trials: int = 0
    bot_no_match: int = 0
    bot_no_match_pct: float = 0.0
    duration_s: float = 0.0
    error_message: str | None = None


def session_arm_dir(out_root: Path, paradigm: str, arm: str) -> Path:
    return out_root / arm / paradigm


def discover_latest_session(arm_paradigm_dir: Path) -> Path | None:
    """Find the most recent session subdir under arm/paradigm/. Each
    session dir is timestamp-named by the executor's writer."""
    if not arm_paradigm_dir.exists():
        return None
    candidates = [
        c for c in arm_paradigm_dir.iterdir()
        if c.is_dir() and (c / "bot_log.json").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def evaluate_session_quality(
    session_dir: Path, paradigm: str,
    bot_no_match_threshold_pct: float = 10.0,
) -> tuple[bool, dict]:
    """Run the audit on the session; return (passed, diagnostics).

    A session passes if:
      - bot_log + experiment_data are present
      - executor recorded > 0 trials (hard-fail covered by executor)
      - bot_no_match / total_bot ≤ bot_no_match_threshold_pct

    Returns (passed, info_dict). info_dict carries the counts used.
    """
    # Lazy import — script doesn't need experiment_bot at module load
    from experiment_bot.validation.platform_adapters import (
        test_row_predicate_for_label,
    )
    bot_path = session_dir / "bot_log.json"
    if not bot_path.exists():
        return False, {"reason": "no_bot_log"}
    try:
        bot_rows = json.loads(bot_path.read_text())
    except Exception as e:
        return False, {"reason": f"bot_log_parse_error: {e}"}

    bot_test_trials = [
        t for t in bot_rows
        if t.get("delivery") is not None or (
            t.get("condition") not in (None, "default")
            or (t.get("response_key") and t.get("response_key") != "Enter")
        )
    ]
    if not bot_test_trials:
        return False, {"reason": "no_test_trials", "n_bot": 0}

    # Compute bot_no_match via the audit script's logic
    plat_json = session_dir / "experiment_data.json"
    plat_csv = session_dir / "experiment_data.csv"
    if plat_json.exists():
        plat = json.loads(plat_json.read_text())
    elif plat_csv.exists():
        import csv as _csv
        with plat_csv.open() as f:
            plat = list(_csv.DictReader(f))
    else:
        return False, {"reason": "no_experiment_data"}

    pred = test_row_predicate_for_label(paradigm)
    if pred is None:
        return False, {"reason": f"no_predicate_for_{paradigm}"}
    plat_test = [r for r in plat if pred(r)]
    if not plat_test:
        return False, {"reason": "no_plat_test_rows"}

    # Normalize trial_index ↔ trial_marker_at_fire and pair
    def _norm(v):
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    plat_indices = {_norm(r.get("trial_index")) for r in plat_test}
    plat_indices.discard(None)
    bot_no_match = 0
    bot_fires = 0
    for t in bot_test_trials:
        d = t.get("delivery") or {}
        marker = _norm(d.get("trial_marker_at_fire"))
        if marker is None or d.get("skipped"):
            continue
        bot_fires += 1
        if marker not in plat_indices:
            bot_no_match += 1
    if bot_fires == 0:
        return False, {"reason": "no_bot_fires_with_marker"}
    pct = 100.0 * bot_no_match / bot_fires
    info = {
        "n_bot_fires": bot_fires,
        "bot_no_match": bot_no_match,
        "bot_no_match_pct": pct,
        "threshold_pct": bot_no_match_threshold_pct,
        "n_plat_test": len(plat_test),
    }
    if pct > bot_no_match_threshold_pct:
        info["reason"] = "bot_no_match_threshold_exceeded"
        return False, info
    return True, info


async def run_one_session(
    paradigm: str, url: str, arm: str, *,
    out_root: Path, seed: int | None,
) -> SessionAttempt:
    """Spawn the executor as a subprocess for one session. Captures
    stderr/stdout for failure forensics."""
    arm_dir = session_arm_dir(out_root, paradigm, arm)
    arm_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "uv", "run", "experiment-bot",
        url,
        "--label", paradigm,
        "--headless",
        "--taskcards-dir", "taskcards",
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if arm == "pre_cal":
        cmd.append("--no-calibration")
    # The executor's output writer uses output/<task_name>/<timestamp>/
    # by default. We redirect to our per-arm tree via
    # EXPERIMENT_BOT_OUTPUT_DIR (honored by writer.py).
    env = os.environ.copy()
    env["EXPERIMENT_BOT_OUTPUT_DIR"] = str(arm_dir)

    attempt = SessionAttempt(paradigm=paradigm, arm=arm, attempt=0)
    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(Path.cwd()),
        )
        stdout, stderr = await proc.communicate()
        attempt.duration_s = time.monotonic() - t0
        if proc.returncode != 0:
            attempt.status = "executor_error"
            attempt.error_message = (stderr.decode("utf-8")[-2000:]
                                     or stdout.decode("utf-8")[-2000:])
            return attempt
    except Exception as e:
        attempt.status = "executor_exception"
        attempt.error_message = repr(e)
        attempt.duration_s = time.monotonic() - t0
        return attempt

    # Find the session dir the executor created. Writer writes to
    # <arm_dir>/<task_name>/<timestamp>/; task_name varies per
    # paradigm (executor normalizes via task.name.replace(" ","_").lower()).
    sd: Path | None = None
    for child in arm_dir.iterdir():
        if child.is_dir():
            cand = discover_latest_session(child)
            if cand is not None:
                if sd is None or cand.stat().st_mtime > sd.stat().st_mtime:
                    sd = cand
    if sd is None:
        attempt.status = "no_session_dir_found"
        attempt.error_message = "executor ran but no bot_log.json found"
        return attempt
    attempt.session_dir = str(sd)
    return attempt


def append_failure_log(arm_root: Path, attempts: list[SessionAttempt]) -> None:
    """Append/rewrite the per-arm session_failures.json with all
    non-ok attempts so far."""
    arm_root.mkdir(parents=True, exist_ok=True)
    failures = [asdict(a) for a in attempts if a.status != "ok"]
    (arm_root / "session_failures.json").write_text(
        json.dumps(failures, indent=2) + "\n"
    )


async def run_sweep(args: argparse.Namespace) -> int:
    out_root = args.out_root
    out_root.mkdir(parents=True, exist_ok=True)
    paradigms = (
        [args.paradigm] if args.paradigm
        else list(PARADIGM_URLS.keys())
    )
    arms = (
        [args.arm] if args.arm
        else ["pre_cal", "post_cal"]
    )

    # Skip unsupported paradigms loudly (Phase 5b drop-from-scope)
    from experiment_bot.taskcard.loader import load_latest
    supported_paradigms: list[str] = []
    for label in paradigms:
        try:
            tc = load_latest(Path("taskcards"), label=label)
        except Exception as e:
            logger.warning(f"{label}: TaskCard load failed ({e}); skipping.")
            continue
        if tc.task_specific.get("sp11_supported", True) is False:
            reason = tc.task_specific.get("sp11_unsupported_reason", "(no reason given)")
            logger.warning(f"{label}: sp11_supported=False; skipping. Reason: {reason}")
            continue
        supported_paradigms.append(label)

    deadline = time.monotonic() + args.hard_walltime_h * 3600.0
    sweep_start = time.monotonic()

    # Per (paradigm, arm) state
    attempts_by_arm: dict[tuple[str, str], list[SessionAttempt]] = {}
    successes_by_arm: dict[tuple[str, str], int] = {}

    for paradigm in supported_paradigms:
        for arm in arms:
            key = (paradigm, arm)
            attempts_by_arm[key] = []
            successes_by_arm[key] = 0

    progress_path = out_root / "sweep_progress.json"

    for paradigm in supported_paradigms:
        url = PARADIGM_URLS[paradigm]
        for arm in arms:
            key = (paradigm, arm)
            arm_root = out_root / arm / paradigm
            session_idx = 0
            consecutive_failed_sessions = 0
            while successes_by_arm[key] < args.n:
                if time.monotonic() > deadline:
                    logger.error(
                        f"Hard wall-time stop ({args.hard_walltime_h}h) "
                        f"reached. Aborting sweep. Pause and assess per "
                        f"Phase 7 user note 3."
                    )
                    _write_progress(progress_path, attempts_by_arm,
                                    successes_by_arm, sweep_start,
                                    aborted=True)
                    return 2
                # Per-paradigm-arm circuit breaker: if too many
                # consecutive sessions fail all their retries, the
                # paradigm/arm is structurally broken; abandon it
                # rather than burning wall-time looping forever.
                if consecutive_failed_sessions >= args.arm_failure_threshold:
                    logger.error(
                        f"[{paradigm}/{arm}] CIRCUIT BREAKER: "
                        f"{consecutive_failed_sessions} consecutive sessions "
                        f"failed all retries. Abandoning this paradigm/arm. "
                        f"Sweep continues with remaining paradigms/arms."
                    )
                    _write_progress(progress_path, attempts_by_arm,
                                    successes_by_arm, sweep_start)
                    break
                session_idx += 1
                attempt_n = 0
                last_attempt: SessionAttempt | None = None
                while attempt_n < args.max_retries + 1:
                    attempt_n += 1
                    seed = args.seed_base + 1000 * session_idx + attempt_n
                    logger.info(
                        f"[{paradigm}/{arm}] session {session_idx} "
                        f"(want {successes_by_arm[key] + 1}/{args.n}), "
                        f"attempt {attempt_n}/{args.max_retries + 1}, "
                        f"seed={seed}"
                    )
                    a = await run_one_session(
                        paradigm, url, arm,
                        out_root=out_root, seed=seed,
                    )
                    a.attempt = attempt_n
                    if a.status == "pending" and a.session_dir is not None:
                        passed, info = evaluate_session_quality(
                            Path(a.session_dir), paradigm,
                            bot_no_match_threshold_pct=args.bot_no_match_threshold,
                        )
                        a.bot_trials = info.get("n_bot_fires", 0)
                        a.bot_no_match = info.get("bot_no_match", 0)
                        a.bot_no_match_pct = info.get("bot_no_match_pct", 0.0)
                        if passed:
                            a.status = "ok"
                        else:
                            a.status = info.get(
                                "reason", "bot_no_match_threshold_exceeded"
                            )
                    attempts_by_arm[key].append(a)
                    last_attempt = a
                    if a.status == "ok":
                        successes_by_arm[key] += 1
                        break
                    logger.warning(
                        f"  → attempt failed: status={a.status} "
                        f"(bot_no_match_pct={a.bot_no_match_pct:.1f}%, "
                        f"err={(a.error_message or '')[:120]})"
                    )
                # Track consecutive session failures for the circuit breaker
                if last_attempt is not None and last_attempt.status == "ok":
                    consecutive_failed_sessions = 0
                else:
                    consecutive_failed_sessions += 1
                append_failure_log(arm_root, attempts_by_arm[key])
                _write_progress(progress_path, attempts_by_arm,
                                successes_by_arm, sweep_start)

    _write_progress(progress_path, attempts_by_arm, successes_by_arm,
                    sweep_start, completed=True)
    logger.info(
        f"Sweep completed: "
        + ", ".join(
            f"{k[0]}/{k[1]}={v}/{args.n}"
            for k, v in successes_by_arm.items()
        )
    )
    return 0


def _write_progress(
    path: Path,
    attempts: dict[tuple[str, str], list[SessionAttempt]],
    successes: dict[tuple[str, str], int],
    sweep_start_s: float,
    aborted: bool = False,
    completed: bool = False,
) -> None:
    summary = {
        "elapsed_s": time.monotonic() - sweep_start_s,
        "aborted": aborted,
        "completed": completed,
        "arms": [
            {
                "paradigm": k[0],
                "arm": k[1],
                "successes": successes[k],
                "total_attempts": len(attempts[k]),
                "failures": sum(1 for a in attempts[k] if a.status != "ok"),
            }
            for k in attempts.keys()
        ],
    }
    path.write_text(json.dumps(summary, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=30,
                   help="Target successful sessions per paradigm-arm "
                        "(default: 30).")
    p.add_argument("--max-retries", type=int, default=3,
                   help="Max retries per session before declaring it "
                        "failed (default: 3 = 1 initial + 2 retries; "
                        "user note 1 says 'up to 3 times before "
                        "skipping' — this is 3 attempts total).")
    p.add_argument("--bot-no-match-threshold", type=float, default=10.0,
                   help="Discard-and-rerun threshold for a session's "
                        "bot_no_match percentage (default: 10).")
    p.add_argument("--hard-walltime-h", type=float, default=48.0,
                   help="Hard wall-time stop in hours (default: 48). "
                        "Per Phase 7 user note 3, sweep aborts at this "
                        "limit and asks before continuing.")
    p.add_argument("--arm-failure-threshold", type=int, default=5,
                   help="After this many consecutive session failures "
                        "(all retries exhausted), abandon the current "
                        "paradigm/arm and move on (default: 5). Prevents "
                        "a broken TaskCard from burning the entire "
                        "wall-time budget.")
    p.add_argument("--paradigm",
                   help="Restrict to one paradigm label.")
    p.add_argument("--arm", choices=("pre_cal", "post_cal"),
                   help="Restrict to one calibration arm.")
    p.add_argument("--seed-base", type=int, default=42,
                   help="Seed base; per-attempt seed is "
                        "seed_base + 1000*session_idx + attempt_n.")
    p.add_argument("--out-root", type=Path, default=Path("output/phase7"),
                   help="Sweep output root (default: output/phase7/).")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return asyncio.run(run_sweep(args))


if __name__ == "__main__":
    sys.exit(main())
