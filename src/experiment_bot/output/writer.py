from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from experiment_bot.core.config import TaskConfig

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "output"


def _safe_segment(name: str) -> str:
    """Collapse a free-text task name to one filesystem-safe path segment:
    path separators and other unsafe characters become '_' (no nesting),
    and an empty result falls back to 'session'."""
    safe = "".join("_" if c in '/\\:' else c for c in (name or "")).strip()
    return safe or "session"


def _resolved_default_output_dir() -> Path:
    """Honor EXPERIMENT_BOT_OUTPUT_DIR env var when set (a sweep wrapper
    uses this to redirect each arm's sessions into its own subtree).
    Falls back to the repo-relative default."""
    env_dir = os.environ.get("EXPERIMENT_BOT_OUTPUT_DIR")
    if env_dir:
        return Path(env_dir)
    return DEFAULT_OUTPUT_DIR


class OutputWriter:
    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = _resolved_default_output_dir()
        self._base_dir = base_dir
        self._run_dir: Path | None = None
        self._trials: list[dict] = []
        # Structured per-stage trace, written to
        # run_trace.json beside bot_log.json in finalize().
        self._trace_stages: list[dict] = []

    def create_run(self, task_name: str, config: TaskConfig) -> Path:
        # Sanitize to a single, filesystem-safe path segment: a "/" in the
        # card's task name (e.g. "Go/No-Go (RDoC)") would otherwise nest the
        # session two levels deep and hide it from per-task tooling.
        task_name = _safe_segment(task_name)
        # Include microseconds so concurrent runs that start in the
        # same second don't collide on the directory name.
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        self._run_dir = self._base_dir / task_name / timestamp
        self._run_dir.mkdir(parents=True, exist_ok=False)
        (self._run_dir / "screenshots").mkdir(exist_ok=True)
        config_path = self._run_dir / "config.json"
        config_path.write_text(json.dumps(config.to_dict(), indent=2))
        self._trials = []
        logger.info(f"Output directory: {self._run_dir}")
        return self._run_dir

    def log_trial(self, trial_data: dict) -> None:
        self._trials.append(trial_data)

    def record_trace(
        self,
        stage: str,
        data: dict,
        duration_s: float | None = None,
    ) -> None:
        """Append a structured stage entry to the run trace.

        Entries are written to ``run_trace.json`` in ``finalize()``.
        Each entry captures ``stage`` (e.g. navigate, calibration,
        trial_loop, wait_completion, save), a ``data`` dict of
        stage-specific payload, and an optional ``duration_s``
        measured by the caller via ``time.monotonic()``.
        """
        self._trace_stages.append({
            "stage": stage,
            "data": data,
            "duration_s": duration_s,
        })

    def save_task_data(self, data: str, filename: str) -> None:
        if self._run_dir:
            path = self._run_dir / filename
            path.write_text(data)
            logger.info(f"Saved experiment data to {path}")

    def save_screenshot(self, data: bytes, name: str) -> None:
        if self._run_dir:
            (self._run_dir / "screenshots" / name).write_bytes(data)

    def save_metadata(self, metadata: dict) -> None:
        if self._run_dir:
            (self._run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))

    def mark_incomplete(self, reason: str) -> None:
        """Best-effort `.incomplete` marker: a partially-saved session must be
        visibly broken, not plausible-looking. Downstream analysis and the
        collection script (scripts/naive_run.sh) exclude marked sessions."""
        if self._run_dir:
            try:
                (self._run_dir / ".incomplete").write_text(reason)
            except OSError:
                logger.error("Could not write .incomplete marker", exc_info=True)

    def finalize(self) -> None:
        if self._run_dir:
            log_path = self._run_dir / "bot_log.json"
            log_path.write_text(json.dumps(self._trials, indent=2))
            logger.info(f"Saved {len(self._trials)} trial logs to {log_path}")
            # Structured per-stage trace beside bot_log.json
            trace_path = self._run_dir / "run_trace.json"
            trace_path.write_text(
                json.dumps({"stages": self._trace_stages}, indent=2)
            )

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir
