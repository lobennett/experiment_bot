"""Platform-aware navigation defaults for Stage 1 (SP15 Part A).

When Stage 1's LLM emits an under-specified navigation.phases array (empty or
shorter than the known canonical sequence for a hosting platform), backfill
with the platform's canonical phases. The defaults are infrastructure
recognition (fullscreen plugin, instructions plugin, etc.) — not paradigm-
specific knowledge — so they generalize across any paradigm on the same
platform without violating G1.

Defaults are derived from committed dev TaskCards that already pass Stage 6.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformDefault:
    name: str
    url_patterns: tuple[str, ...]   # regex patterns matched against URL
    phases: list[dict]              # canonical nav phases (flat schema)


# Extracted from taskcards/expfactory_stroop/f40e356e.json
_EXPFACTORY_PHASES: list[dict] = [
    {"phase": "", "action": "wait",     "target": "",                           "key": "",      "steps": [], "duration_ms": 500},
    {"phase": "", "action": "click",    "target": "#jspsych-fullscreen-btn",    "key": "",      "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                           "key": "",      "steps": [], "duration_ms": 1500},
    {"phase": "", "action": "keypress", "target": "",                           "key": "Enter", "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                           "key": "",      "steps": [], "duration_ms": 3000},
    {"phase": "", "action": "click",    "target": "#jspsych-instructions-next", "key": "",      "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                           "key": "",      "steps": [], "duration_ms": 3000},
    {"phase": "", "action": "click",    "target": "#jspsych-instructions-next", "key": "",      "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                           "key": "",      "steps": [], "duration_ms": 1000},
    {"phase": "", "action": "keypress", "target": "",                           "key": "Enter", "steps": [], "duration_ms": 0},
]

# Extracted verbatim from taskcards/cognitionrun_stroop/e62646a9.json navigation.phases
_COGNITION_RUN_PHASES: list[dict] = [
    {"phase": "", "action": "keypress", "target": "", "key": " ", "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "", "key": "",  "steps": [], "duration_ms": 800},
    {"phase": "", "action": "keypress", "target": "", "key": " ", "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "", "key": "",  "steps": [], "duration_ms": 800},
    {"phase": "", "action": "keypress", "target": "", "key": " ", "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "", "key": "",  "steps": [], "duration_ms": 800},
    {"phase": "", "action": "keypress", "target": "", "key": " ", "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "", "key": "",  "steps": [], "duration_ms": 800},
    {"phase": "", "action": "keypress", "target": "", "key": " ", "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "", "key": "",  "steps": [], "duration_ms": 800},
]

# Extracted verbatim from taskcards/stopit_stop_signal/d930eda9.json navigation.phases
_STOPIT_PHASES: list[dict] = [
    {"phase": "fullscreen",        "action": "click",    "target": "#jspsych-fullscreen-btn",    "key": "",  "steps": [], "duration_ms": 0},
    {"phase": "wait_fullscreen",   "action": "wait",     "target": "",                           "key": "",  "steps": [], "duration_ms": 1500},
    {"phase": "instructions_page1","action": "click",    "target": "#jspsych-instructions-next", "key": "",  "steps": [], "duration_ms": 500},
    {"phase": "instructions_page2","action": "click",    "target": "#jspsych-instructions-next", "key": "",  "steps": [], "duration_ms": 500},
    {"phase": "block_start",       "action": "keypress", "target": "",                           "key": " ", "steps": [], "duration_ms": 500},
    {"phase": "get_ready",         "action": "wait",     "target": "",                           "key": "",  "steps": [], "duration_ms": 2500},
]


PLATFORM_NAV_DEFAULTS: tuple[PlatformDefault, ...] = (
    PlatformDefault(
        name="expfactory",
        url_patterns=(r"deploy\.expfactory\.org", r"expfactory\.org/preview/"),
        phases=_EXPFACTORY_PHASES,
    ),
    PlatformDefault(
        name="cognition.run",
        url_patterns=(r"\.cognition\.run",),
        phases=_COGNITION_RUN_PHASES,
    ),
    PlatformDefault(
        name="kywch.github.io",
        url_patterns=(r"kywch\.github\.io",),
        phases=_STOPIT_PHASES,
    ),
)


def _match_platform(url: str) -> PlatformDefault | None:
    for d in PLATFORM_NAV_DEFAULTS:
        for pat in d.url_patterns:
            if re.search(pat, url):
                return d
    return None


def apply_platform_defaults(partial: dict, url: str) -> dict:
    """Backfill canonical platform nav phases when the partial's
    navigation.phases is empty or shorter than the platform default.

    Returns the (possibly modified) partial. Does NOT mutate input.
    """
    default = _match_platform(url)
    if default is None:
        return partial
    nav = partial.get("navigation", {}) or {}
    current_phases = nav.get("phases", []) or []
    if len(current_phases) >= len(default.phases):
        # LLM emitted at least as many phases — trust it; may have paradigm-
        # specific knowledge the platform default doesn't capture.
        return partial
    out = dict(partial)
    out["navigation"] = dict(nav)
    out["navigation"]["phases"] = list(default.phases)
    return out
