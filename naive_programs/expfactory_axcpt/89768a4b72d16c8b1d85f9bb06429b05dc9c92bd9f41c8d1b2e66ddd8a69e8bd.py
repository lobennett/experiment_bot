import math
import random


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class _Participant:
    """Simulated healthy adult performing a cued letter task (cue-probe pairs).

    Conditions are cue-probe combinations (AX / AY / BX / BY). AX requires the
    target response; everything else requires the non-target response. The
    model captures the classic behavioral signatures of such tasks:

    - Errors concentrate on AY (the cue induces a prepared target response
      that must be overridden) and, to a lesser degree, BX (the probe itself
      pulls toward the target response).
    - RTs: AY slowest, AX baseline, BX slightly slow, BY fastest.
    - Errors tend to be fast, prepotent responses.
    - Practice speeds responding early on; mild fatigue slows it late.
    - Post-error slowing after mistakes.
    - Slowly drifting alertness (autocorrelated RT fluctuations) and
      occasional omissions (lapses / responses slower than the window).

    Every parameter is drawn per seed so distinct seeds behave like distinct
    people (fast-and-sloppy vs. slow-and-careful, etc.).
    """

    def __init__(self, seed):
        rng = random.Random(seed)
        self.rng = rng

        # Ex-Gaussian RT core (per-participant)
        self.mu = _clip(rng.gauss(420.0, 45.0), 320.0, 560.0)
        self.sigma = _clip(rng.gauss(45.0, 12.0), 20.0, 90.0)
        self.tau = _clip(rng.gauss(110.0, 35.0), 40.0, 250.0)

        # Condition-specific RT shifts (ms)
        self.shift = {
            "AX": 0.0,
            "AY": _clip(rng.gauss(110.0, 35.0), 40.0, 220.0),
            "BX": _clip(rng.gauss(35.0, 20.0), -10.0, 100.0),
            "BY": _clip(rng.gauss(-25.0, 15.0), -80.0, 20.0),
        }

        # Asymptotic error probabilities per condition
        self.p_err = {
            "AX": _clip(rng.gauss(0.035, 0.020), 0.005, 0.12),
            "AY": _clip(rng.gauss(0.110, 0.050), 0.020, 0.30),
            "BX": _clip(rng.gauss(0.050, 0.030), 0.005, 0.18),
            "BY": _clip(rng.gauss(0.015, 0.010), 0.002, 0.06),
        }

        # Attentional lapses -> omissions
        self.p_lapse = _clip(rng.gauss(0.015, 0.010), 0.0, 0.06)

        # Learning / fatigue / sequential effects
        self.practice_gain = _clip(rng.gauss(35.0, 15.0), 0.0, 80.0)   # ms saved
        self.fatigue_slope = _clip(rng.gauss(0.15, 0.10), 0.0, 0.5)    # ms/trial late
        self.pes = _clip(rng.gauss(45.0, 20.0), 0.0, 120.0)            # post-error slowing
        self.err_boost_early = rng.uniform(0.3, 1.0)                   # extra early errors

        # AR(1) alertness drift
        self.drift = 0.0
        self.drift_sd = _clip(rng.gauss(8.0, 4.0), 2.0, 20.0)
        self.drift_decay = 0.9

    def respond(self, ctx):
        rng = self.rng
        t = ctx.trial_index
        cond = ctx.condition

        # Slowly wandering alertness
        self.drift = self.drift_decay * self.drift + rng.gauss(0.0, self.drift_sd)

        # Full attentional lapse: no response at all
        if rng.random() < self.p_lapse:
            return (None, rng.uniform(900.0, 1400.0))

        # Decide whether this trial is an error (more likely early, pre-learning)
        p_err = self.p_err.get(cond, 0.03)
        p_err = min(0.5, p_err * (1.0 + self.err_boost_early * math.exp(-t / 8.0)))
        make_error = rng.random() < p_err

        # Assemble the RT mean for this trial
        mu = self.mu + self.shift.get(cond, 0.0)
        mu -= self.practice_gain * (1.0 - math.exp(-t / 25.0))
        if t > 60:
            mu += self.fatigue_slope * (t - 60)
        if ctx.prev_correct is False:
            mu += self.pes
        mu += self.drift
        if make_error:
            # Errors are typically fast, prepotent responses
            mu -= rng.uniform(10.0, 60.0)

        rt = rng.gauss(mu, self.sigma) + rng.expovariate(1.0 / self.tau)

        # Responses slower than the response window are recorded as misses
        if rt >= 1450.0:
            return (None, rng.uniform(900.0, 1400.0))
        rt = max(180.0, rt)

        if make_error:
            wrong = [k for k in ctx.available_keys if k != ctx.correct_key]
            if wrong:
                return (rng.choice(wrong), rt)
            # Wrong key not yet known: the error surfaces as an omission
            return (None, rt)

        return (ctx.correct_key, rt)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
