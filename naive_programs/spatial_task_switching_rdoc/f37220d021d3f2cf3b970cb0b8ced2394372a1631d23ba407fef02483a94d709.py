"""
Generative participant model for a quadrant-based task-switching experiment.

Structure of the task (from the page source):
  - Each trial: 500 ms fixation -> 150 ms spatial cue -> stimulus shown 1000 ms,
    response window fixed at 1500 ms (response does not end the trial).
  - Responses are the comma / period keys.
  - Between test blocks there are attention-check screens (press a named letter,
    15 s window) which arrive with a non-comma/period correct key.

The model is an ex-Gaussian RT generator with per-participant trait parameters
(speed, variability, skew, accuracy, lapse/omission rates, post-error slowing,
practice speed-up, slow fatigue, and a slowly drifting attentional state).
Each seed draws its own traits, so seeds differ the way people differ.
"""

import math

import numpy as np

TASK_KEYS = (",", ".")


class Participant:
    def __init__(self, seed):
        self.rng = np.random.default_rng(np.random.SeedSequence(int(seed)))
        r = self.rng

        # --- trait parameters (one draw per participant) ---
        # Ex-Gaussian RT components (ms) for the choice task.
        self.mu = float(np.clip(r.normal(770.0, 95.0), 560.0, 1020.0))
        self.sigma = float(np.clip(r.normal(85.0, 25.0), 40.0, 170.0))
        self.tau = float(np.clip(r.normal(170.0, 70.0), 60.0, 400.0))

        # Accuracy and failure modes.
        self.base_acc = float(np.clip(r.normal(0.905, 0.050), 0.70, 0.985))
        self.lapse_p = float(np.clip(r.normal(0.030, 0.020), 0.003, 0.10))
        self.omit_p = float(np.clip(r.normal(0.015, 0.012), 0.0, 0.06))

        # Sequential effects.
        self.pes = float(np.clip(r.normal(45.0, 25.0), 0.0, 130.0))
        self.post_err_acc_boost = float(np.clip(r.normal(0.020, 0.010), 0.0, 0.05))

        # Slow dynamics across the session.
        self.practice_gain = float(np.clip(r.normal(0.09, 0.05), 0.0, 0.20))
        self.fatigue_slope = float(np.clip(r.normal(0.00025, 0.0002), 0.0, 0.0009))

        # AR(1) attentional drift (ms offset on the RT mean).
        self.drift = 0.0
        self.drift_rho = 0.97
        self.drift_sd = float(np.clip(r.normal(18.0, 8.0), 4.0, 45.0))

        # Attention-check behavior.
        self.att_acc = float(np.clip(r.normal(0.96, 0.03), 0.80, 1.0))
        self.att_speed = float(np.clip(r.normal(3200.0, 700.0), 1500.0, 6000.0))

        self.n = 0  # trials seen

    # ------------------------------------------------------------------ #

    def _task_rt(self, prev_error):
        """One ex-Gaussian RT sample with practice, fatigue, drift, PES, lapses."""
        r = self.rng
        practice = 1.0 - self.practice_gain * (1.0 - math.exp(-self.n / 40.0))
        fatigue = 1.0 + self.fatigue_slope * self.n
        self.drift = self.drift_rho * self.drift + r.normal(0.0, self.drift_sd)
        mu = self.mu * practice * fatigue + self.drift
        if prev_error:
            mu += self.pes
        rt = r.normal(mu, self.sigma) + r.exponential(self.tau)
        if r.random() < self.lapse_p:
            # momentary attentional lapse: a long right-tail excursion
            rt += r.exponential(350.0)
        return rt

    def _wrong_key(self, ctx, correct_key):
        """Pick the competing response (the other of comma/period if possible)."""
        alts = [k for k in TASK_KEYS if k != correct_key]
        avail = [k for k in ctx.available_keys if k != correct_key]
        # prefer the paired task key; fall back to any other available key
        for k in alts:
            if not ctx.available_keys or k in ctx.available_keys:
                return k
        if avail:
            return avail[int(self.rng.integers(len(avail)))]
        return alts[0] if alts else None

    def _attention_check(self, ctx):
        """'Press the X key' screens: slow, deliberate, near-ceiling accuracy."""
        r = self.rng
        rt = self.att_speed + r.normal(0.0, 600.0) + r.exponential(900.0)
        rt = float(min(max(rt, 900.0), 14000.0))
        if r.random() < self.att_acc:
            return (ctx.correct_key, rt)
        others = [k for k in ctx.available_keys if k != ctx.correct_key]
        if others and r.random() < 0.5:
            return (others[int(r.integers(len(others)))], rt)
        return (None, rt)

    # ------------------------------------------------------------------ #

    def respond(self, ctx):
        self.n += 1
        ck = ctx.correct_key

        if ck is None:
            # no defined correct response: withhold
            return (None, 1000.0)

        if ck not in TASK_KEYS:
            return self._attention_check(ctx)

        r = self.rng
        prev_error = ctx.prev_correct is False
        rt = self._task_rt(prev_error)

        # Omission: either a true check-out, or the sampled RT overruns the
        # fixed 1500 ms response window.
        if r.random() < self.omit_p or rt >= 1470.0:
            return (None, float(min(max(rt, 600.0), 1500.0)))

        rt = float(max(rt, 275.0))

        p_correct = self.base_acc + (self.post_err_acc_boost if prev_error else 0.0)
        # premature responses carry a guessing penalty
        if rt < self.mu - 1.8 * self.sigma:
            p_correct -= 0.10
        p_correct = min(max(p_correct, 0.05), 0.995)

        if r.random() < p_correct:
            return (ck, rt)

        # errors run slightly faster than correct responses
        rt = float(max(rt * 0.93, 275.0))
        return (self._wrong_key(ctx, ck), rt)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)
