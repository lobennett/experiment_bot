"""Hand-written reference participant program for tests.

Follows the SP21 naive-program contract exactly: stdlib+numpy only,
deterministic per seed, returns plain (key, rt_ms) tuples.
"""
import numpy as np


def make_participant(seed):
    return _Toy(seed)


class _Toy:
    def __init__(self, seed):
        self._rng = np.random.default_rng(seed)
        self._speed = 500.0 + self._rng.normal(0.0, 50.0)

    def respond(self, ctx):
        rt = max(160.0, self._speed + self._rng.normal(0.0, 60.0))
        if self._rng.random() < 0.05:  # occasional error: press a non-correct key
            others = [k for k in ctx.available_keys if k != ctx.correct_key]
            if others:
                return (others[int(self._rng.integers(len(others)))], rt)
        return (ctx.correct_key, rt)

    def on_interrupt(self, ctx, ssd_ms, intended):
        # Longer SSD -> harder to stop.
        p_stop = max(0.1, 0.9 - ssd_ms / 500.0)
        if self._rng.random() < p_stop:
            return None
        return (intended[0], max(200.0, ssd_ms + 150.0))
