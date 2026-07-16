"""
Generative participant model for a two-box spatial cueing task.

A star appears in the left or right box; the participant presses one of two
keys (index/middle finger) according to the star's location. Before the star,
a spatial cue may highlight neither box (nocue), both boxes (doublecue), the
star's box (valid), or the opposite box (invalid).

The model produces:
  * ex-Gaussian RT distributions (right-skewed, human-like),
  * an alerting effect (nocue slower than doublecue),
  * an orienting effect (valid fastest, invalid slowest),
  * stable individual differences across seeds (speed, skew, effect sizes,
    accuracy, lapse rate),
  * practice speed-up early on and mild fatigue late,
  * slow autocorrelated drift in speed across trials,
  * post-error slowing,
  * occasional anticipations (fast guesses) and lapses (very slow responses
    or omissions),
  * a small error rate that is slightly elevated on invalid-cue trials.
"""

import numpy as np


class _Participant:
    # RTs are measured from target onset; the target stays up 1000 ms and the
    # trial accepts responses for 1500 ms, so anything slower is an omission.
    RESPONSE_WINDOW_MS = 1450.0
    MIN_RT_MS = 160.0

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(int(seed) & 0x7FFFFFFF)
        r = self.rng

        # --- stable individual differences (drawn once per participant) ---
        # Ex-Gaussian RT parameters, anchored to the doublecue condition.
        self.mu = float(np.clip(r.normal(400.0, 45.0), 300.0, 560.0))
        self.sigma = float(np.clip(r.normal(45.0, 12.0), 20.0, 90.0))
        self.tau = float(np.clip(r.normal(90.0, 30.0), 35.0, 200.0))

        # Cueing effects (ms), relative to doublecue.
        alerting = max(0.0, r.normal(28.0, 12.0))     # nocue slower
        orienting = max(0.0, r.normal(18.0, 8.0))     # valid faster
        invalid_cost = max(0.0, r.normal(26.0, 11.0)) # invalid slower
        self.cond_shift = {
            "nocue": alerting,
            "doublecue": 0.0,
            "valid": -orienting,
            "invalid": invalid_cost,
        }

        # Accuracy / vigilance profile.
        self.p_error_base = float(np.clip(r.normal(0.025, 0.012), 0.004, 0.08))
        self.p_lapse = float(np.clip(r.normal(0.018, 0.010), 0.002, 0.06))
        self.p_anticipate = float(np.clip(r.normal(0.012, 0.008), 0.0, 0.05))

        # Sequential / temporal dynamics.
        self.post_error_slow = max(0.0, r.normal(35.0, 12.0))
        self.practice_amp = max(0.0, r.normal(30.0, 12.0))   # early speed-up
        self.practice_tau = float(np.clip(r.normal(35.0, 10.0), 15.0, 70.0))
        self.fatigue_slope = max(0.0, r.normal(0.06, 0.05))  # ms per trial

        self._drift = 0.0   # slow AR(1) wandering of overall speed
        self._n = 0         # trials seen

    # ------------------------------------------------------------------
    def _wrong_key(self, ctx):
        """A plausible incorrect keypress: another key from the inventory."""
        others = [k for k in (ctx.available_keys or ()) if k != ctx.correct_key]
        if others:
            return others[int(self.rng.integers(len(others)))]
        return ctx.correct_key  # nothing else known to press

    def _sample_rt(self, shift_ms):
        rt = (self.mu + shift_ms
              + self.rng.normal(0.0, self.sigma)
              + self.rng.exponential(self.tau))
        return float(np.clip(rt, self.MIN_RT_MS, self.RESPONSE_WINDOW_MS))

    # ------------------------------------------------------------------
    def respond(self, ctx):
        r = self.rng
        trial = self._n
        self._n += 1

        # Slow autocorrelated drift in overall speed (attention waxes/wanes).
        self._drift = 0.97 * self._drift + r.normal(0.0, 4.5)

        # If the trial doesn't ask for a keypress, stay quiet.
        if ctx.correct_key is None and not ctx.response_elements:
            return (None, 600.0)

        shift = self.cond_shift.get(ctx.condition, 0.0)
        shift += self._drift
        shift -= self.practice_amp * np.exp(-trial / self.practice_tau) * -1.0 \
            if False else 0.0  # (kept explicit below)
        # practice speed-up then fatigue
        shift -= self.practice_amp * float(np.exp(-trial / self.practice_tau))
        shift += self.practice_amp  # re-anchor so trial-0 starts slower
        shift += self.fatigue_slope * trial

        # Post-error slowing (only after an actual erroneous response).
        if ctx.prev_correct is False and ctx.prev_rt_ms is not None:
            shift += self.post_error_slow

        # --- anticipation: fast guess before processing the target ---
        if r.random() < self.p_anticipate:
            rt = float(r.uniform(self.MIN_RT_MS, 280.0))
            key = ctx.correct_key if r.random() < 0.5 else self._wrong_key(ctx)
            return (key, rt)

        # --- lapse: attention elsewhere -> omission or very slow response ---
        if r.random() < self.p_lapse:
            if r.random() < 0.55:
                return (None, self.RESPONSE_WINDOW_MS)
            rt = float(r.uniform(850.0, self.RESPONSE_WINDOW_MS))
            key = ctx.correct_key if r.random() < 0.85 else self._wrong_key(ctx)
            return (key, rt)

        # --- normal trial ---
        p_err = self.p_error_base * (1.6 if ctx.condition == "invalid" else 1.0)
        rt = self._sample_rt(shift)
        if r.random() < p_err:
            # Errors tend to be a touch faster than correct responses.
            rt = float(max(self.MIN_RT_MS, rt - abs(r.normal(30.0, 25.0))))
            return (self._wrong_key(ctx), rt)
        return (ctx.correct_key, rt)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
