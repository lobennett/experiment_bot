from __future__ import annotations

from experiment_bot.platforms.base import Platform
from experiment_bot.platforms.expfactory import ExpFactoryPlatform
from experiment_bot.platforms.psytoolkit import PsyToolkitPlatform

_REGISTRY: dict[str, type[Platform]] = {
    "expfactory": ExpFactoryPlatform,
    "psytoolkit": PsyToolkitPlatform,
}


def get_platform(name: str) -> Platform:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown platform: {name}. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]()
