from __future__ import annotations

import hashlib
import json
import logging
from json import JSONDecodeError
from pathlib import Path

from experiment_bot.core.config import TaskConfig

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "cache"


class ConfigCache:
    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self._cache_dir = cache_dir

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _config_path(self, url: str, label: str = "") -> Path:
        key = label if label else self._url_hash(url)
        return self._cache_dir / key / "config.json"

    def load(self, url: str, label: str = "") -> TaskConfig | None:
        path = self._config_path(url, label)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return TaskConfig.from_dict(data)
        except (JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to load cached config: {e}")
            return None

    def save(self, url: str, config: TaskConfig, label: str = "") -> None:
        path = self._config_path(url, label)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config.to_dict(), indent=2))
        logger.info(f"Cached config to {path}")
