from __future__ import annotations

import json
import logging
from pathlib import Path

from experiment_bot.core.config import TaskConfig

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "cache"


class ConfigCache:
    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self._cache_dir = cache_dir

    def _config_path(self, platform: str, task_id: str) -> Path:
        return self._cache_dir / platform / task_id / "config.json"

    def load(self, platform: str, task_id: str) -> TaskConfig | None:
        path = self._config_path(platform, task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return TaskConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load cached config: {e}")
            return None

    def save(self, platform: str, task_id: str, config: TaskConfig) -> None:
        path = self._config_path(platform, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config.to_dict(), indent=2))
        logger.info(f"Cached config to {path}")
