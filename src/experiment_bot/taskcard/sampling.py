from __future__ import annotations

import numpy as np


def sample_session_params(taskcard: dict, seed: int) -> dict:
    """Draw per-session distributional parameters from TaskCard.

    For each condition's response distribution, draws a single value per
    sub-parameter (mu, sigma, tau, ...) from N(value, between_subject_sd**2),
    clipped to literature_range when provided. Output is fed to the executor's
    ResponseSampler in place of the static config values.
    """
    rng = np.random.default_rng(seed)
    sampled: dict = {}
    for cond, dist in taskcard.get("response_distributions", {}).items():
        v = dist.get("value", {})
        r = dist.get("literature_range") or {}
        sd = dist.get("between_subject_sd") or {}
        sampled[cond] = {}
        for param, mean in v.items():
            spread = float(sd.get(param, 0))
            draw = rng.normal(float(mean), spread) if spread > 0 else float(mean)
            if param in r:
                lo, hi = r[param]
                draw = float(np.clip(draw, lo, hi))
            sampled[cond][param] = float(draw)
    return sampled
