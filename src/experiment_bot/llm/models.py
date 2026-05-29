from __future__ import annotations
import os

# Single authoritative model id for the project.
# Override via EXPERIMENT_BOT_MODEL env var for testing or model upgrades.
DEFAULT_MODEL: str = os.environ.get("EXPERIMENT_BOT_MODEL", "claude-opus-4-8")
