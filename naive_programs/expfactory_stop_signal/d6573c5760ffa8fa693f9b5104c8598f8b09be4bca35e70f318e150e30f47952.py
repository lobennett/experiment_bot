"""
Computational model of a healthy adult performing the RDoC stop-signal task
(expfactory / jsPsych, poldracklab-stop-signal plugin).

Task facts encoded in the model:
  - Go trials require a 2-choice shape discrimination (comma/period keys);
    stimulus 1000 ms, response window 1500 ms, response does not end trial.
  - Stop trials (1/3 of trials) present a stop signal after a staircased SSD
    (start 250 ms, +/-50 ms, bounds 0-1000); participant must withhold.
  - Behavior follows the independent horse-race model (Logan & Cowan 1984):
    the go process (ex-Gaussian RT) races a stop process (SSD + SSRT).
    Failed stops therefore have faster RTs than go responses; the staircase
    drives inhibition toward ~50%.

Individual differences (per seed): ex-Gaussian go RT parameters, SSRT mean
and variability, stop-signal trigger failure rate, choice error rate,
omission (lapse) rate, post-stop-signal and post-error slowing magnitudes,
practice speed-up, slow fatigue drift, and RT autocorrelation.
"""

import random


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


class _Participant:
    def __init__(self, seed):
        rng = random.Random(seed)
        self.rng = rng

        # --- Go process: ex-Gaussian RT (includes proactive slowing that
        #     participants show in stop-signal contexts vs. pure choice RT).
        self.mu = _clip(rng.gauss(470.0, 55.0), 340.0, 640.0)
        self.sigma = _clip(rng.gauss(62.0, 14.0), 30.0, 110.0)
        self.tau = _clip(rng.gauss(150.0, 45.0), 60.0, 300.0)

        # --- Stop process
        self.ssrt_mean = _clip(rng.gauss(225.0, 30.0), 150.0, 320.0)
        self.ssrt_sd = _clip(rng.gauss(32.0, 10.0), 12.0, 65.0)
        # Occasional failures to trigger the stop process at all
        self.p_trigger_fail = _clip(rng.gauss(0.035, 0.03), 0.0, 0.15)

        # --- Response reliability on go trials
        self.p_choice_error = _clip(rng.gauss(0.030, 0.018), 0.003, 0.12)
        self.p_omission = _clip(rng.gauss(0.020, 0.015), 0.0, 0.08)

        # --- Sequential effects
        self.post_stop_slowing = _clip(rng.gauss(38.0, 22.0), 0.0, 120.0)
        self.post_error_slowing = _clip(rng.gauss(48.0, 26.0), 0.0, 150.0)

        # --- Slow dynamics
        self.practice_boost = _clip(rng.gauss(60.0, 30.0), 0.0, 150.0)
        self.practice_decay = _clip(rng.gauss(0.12, 0.05), 0.05, 0.30)
        self.fatigue_per_trial = _clip(rng.gauss(0.18, 0.15), -0.10, 0.60)
        self.ar_coef = _clip(rng.gauss(0.22, 0.10), 0.0, 0.50)
        self.ar_noise_sd = _clip(rng.gauss(18.0, 6.0), 6.0, 40.0)
        self._ar_state = 0.0

        # Keys observed so far (task reveals them trial by trial)
        self._known_keys = []

    # ------------------------------------------------------------------ #
    def _note_keys(self, ctx):
        for k in tuple(ctx.available_keys) + (ctx.correct_key,):
            if k is not None and k not in self._known_keys:
                self._known_keys.append(k)

    def _sample_go_rt(self, ctx):
        rng = self.rng
        rt = self.mu + rng.gauss(0.0, self.sigma) + rng.expovariate(1.0 / self.tau)

        # trial-to-trial autocorrelation (arousal fluctuation)
        self._ar_state = (self.ar_coef * self._ar_state
                          + rng.gauss(0.0, self.ar_noise_sd))
        rt += self._ar_state

        # practice speed-up early in the session, slow fatigue later
        t = ctx.trial_index
        rt += self.practice_boost * pow(2.718281828, -self.practice_decay * t)
        rt += self.fatigue_per_trial * t

        # sequential adjustments driven by the previous trial's outcome
        if ctx.prev_condition == "stop" or ctx.prev_interrupted:
            rt += self.post_stop_slowing * rng.uniform(0.5, 1.5)
        if ctx.prev_correct is False:
            rt += self.post_error_slowing * rng.uniform(0.5, 1.5)

        return max(rt, 180.0 + rng.uniform(0.0, 40.0))

    def _pick_key(self, ctx):
        """Choose the key actually pressed (with occasional choice errors)."""
        rng = self.rng
        correct = ctx.correct_key
        if correct is None:
            # Stop trial: the prepotent go response to the shape. We cannot
            # see the shape, so draw from the known response set.
            pool = self._known_keys or list(ctx.available_keys)
            return rng.choice(pool) if pool else None
        if rng.random() < self.p_choice_error:
            others = [k for k in self._known_keys if k != correct]
            if not others:
                others = [k for k in ctx.available_keys if k != correct]
            if others:
                return rng.choice(others)
        return correct

    # ------------------------------------------------------------------ #
    def respond(self, ctx):
        self._note_keys(ctx)
        rng = self.rng

        rt = self._sample_go_rt(ctx)

        # attentional lapse -> omission; also, responses landing beyond the
        # 1500 ms trial window are never recorded by the platform
        if rng.random() < self.p_omission or rt > 1450.0:
            return (None, min(rt, 1490.0))

        key = self._pick_key(ctx)
        if key is None:
            return (None, rt)
        return (key, float(rt))

    def on_interrupt(self, ctx, ssd_ms, intended):
        key, rt = intended if intended is not None else (None, None)
        if key is None:
            return None  # was going to omit anyway

        rng = self.rng

        # sometimes the stop process is simply never triggered
        if rng.random() < self.p_trigger_fail:
            return (key, rt)

        # independent horse race: stop finishes at SSD + SSRT (trial-varying)
        ssrt = max(80.0, rng.gauss(self.ssrt_mean, self.ssrt_sd))
        if rt < ssd_ms + ssrt:
            return (key, rt)  # go process won: failed stop, fast RT
        return None           # stop process won: successful inhibition


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
