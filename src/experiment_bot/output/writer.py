from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from experiment_bot.core.config import TaskConfig

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "output"


class OutputWriter:
    def __init__(self, base_dir: Path = DEFAULT_OUTPUT_DIR):
        self._base_dir = base_dir
        self._run_dir: Path | None = None
        self._trials: list[dict] = []

    def create_run(self, task_name: str, config: TaskConfig) -> Path:
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

    def save_task_data(self, data: str, filename: str = "task_data.csv") -> None:
        if self._run_dir:
            path = self._run_dir / filename
            path.write_text(data)
            logger.info(f"Saved experiment data to {path}")

    def save_experiment_data(self, data) -> None:
        """SP10: persist the driver-retrieved platform data export."""
        if not self._run_dir:
            return
        path = self._run_dir / f"experiment_data.{data.format}"
        if isinstance(data.raw, bytes):
            path.write_bytes(data.raw)
        else:
            path.write_text(data.raw)

    def save_screenshot(self, data: bytes, name: str) -> None:
        if self._run_dir:
            (self._run_dir / "screenshots" / name).write_bytes(data)

    def save_metadata(self, metadata: dict) -> None:
        if self._run_dir:
            (self._run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))

    def finalize(self) -> None:
        if self._run_dir:
            log_path = self._run_dir / "bot_log.json"
            log_path.write_text(json.dumps(self._trials, indent=2))
            logger.info(f"Saved {len(self._trials)} trial logs to {log_path}")

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir
