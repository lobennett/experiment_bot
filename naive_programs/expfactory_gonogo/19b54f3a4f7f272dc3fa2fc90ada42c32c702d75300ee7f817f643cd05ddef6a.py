import numpy as np


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class GoNoGoParticipant:
    """A healthy adult doing a go/no-go task.

    Go stimulus (filled square, 6/7 of trials) -> press the spacebar.
    No-go stimulus (outlined square, 1/7 of trials) -> withhold.

    The behavioral signatures modeled here:
      * fast, right-skewed (ex-Gaussian) go response times,
      * occasional attentional omissions on go trials,
      * prepotent-response ("commission") failures on no-go trials that
        become more likely after long runs of go trials,
      * commission errors that are quicker than correct go responses,
      * post-error slowing, and a gentle practice-related speed-up.

    The trial lasts up to 1500 ms (stim shown 1000 ms), so any intended
    response slower than that window is recorded as a miss.
    """

    def __init__(self, seed):
        r = np.random.RandomState(int(seed) & 0xFFFFFFFF)
        self.rng = r

        # --- go response-time distribution (ex-Gaussian), per participant ---
        self.mu_go = _clamp(r.normal(400.0, 45.0), 285.0, 560.0)
        self.sigma_go = _clamp(r.normal(45.0, 10.0), 18.0, 85.0)
        self.tau_go = _clamp(r.normal(95.0, 32.0), 40.0, 210.0)

        # attentional omissions on go trials (failure to press at all)
        self.go_omission = _clamp(r.normal(0.020, 0.015), 0.002, 0.09)

        # baseline prepotent-response failure rate on no-go trials
        self.commission_base = _clamp(r.normal(0.20, 0.08), 0.04, 0.45)
        # how sharply commission risk grows with the current go run-length
        self.prepotency_gain = _clamp(r.normal(0.05, 0.02), 0.01, 0.10)
        # commission errors are faster than correct go responses
        self.ng_speedup = _clamp(r.normal(0.90, 0.05), 0.78, 1.0)

        # post-error slowing multiplier applied to the next go response
        self.pes = _clamp(r.normal(1.06, 0.03), 1.0, 1.20)

        # gradual practice speed-up (fraction of RT shaved off by the end)
        self.practice_gain = _clamp(r.normal(0.06, 0.03), 0.0, 0.15)
        self._horizon = 250.0

        self.trial_window = 1500.0  # trial_duration ceiling (ms)
        self.rt_floor = 150.0       # below this = implausible anticipation

        self._consec_go = 0
        self._prev_error = False
        self._go_key = " "

    # ---- helpers ---------------------------------------------------------
    def _sample_go_rt(self):
        return (self.rng.normal(self.mu_go, self.sigma_go)
                + self.rng.exponential(self.tau_go))

    def _floored(self, rt):
        if rt < self.rt_floor:
            return self.rt_floor + self.rng.random_sample() * 30.0
        return rt

    def _resolve_go_key(self, ctx):
        # The go key is whatever key a go trial expects. Learn it from a go
        # trial's correct_key; fall back to the spacebar / first available key.
        keys = ctx.available_keys or ()
        if ctx.correct_key is not None:
            self._go_key = ctx.correct_key
        elif " " in keys:
            self._go_key = " "
        elif keys:
            self._go_key = keys[0]
        return self._go_key

    # ---- per-trial decision ---------------------------------------------
    def respond(self, ctx):
        go_key = self._resolve_go_key(ctx)

        frac = min(1.0, ctx.trial_index / self._horizon)
        speed_factor = 1.0 - self.practice_gain * frac

        if ctx.condition == "go":
            key, rt = self._go_trial(go_key, speed_factor)
            self._consec_go += 1
        else:
            key, rt = self._nogo_trial(go_key, speed_factor)
            self._consec_go = 0

        return key, rt

    def _go_trial(self, go_key, speed_factor):
        # occasional attentional lapse -> no response
        if self.rng.random_sample() < self.go_omission:
            self._prev_error = True
            return None, self.trial_window

        rt = self._sample_go_rt() * speed_factor
        if self._prev_error:
            rt *= self.pes
        rt = self._floored(rt)

        if rt >= self.trial_window:
            # too slow: the platform never registers the press
            self._prev_error = True
            return None, self.trial_window

        self._prev_error = False
        return go_key, float(rt)

    def _nogo_trial(self, go_key, speed_factor):
        # prepotency accumulates across a run of consecutive go trials
        extra = self.prepotency_gain * max(0, self._consec_go - 3)
        p_commit = _clamp(self.commission_base + extra, 0.0, 0.65)

        if self.rng.random_sample() < p_commit:
            rt = self._floored(
                self._sample_go_rt() * speed_factor * self.ng_speedup)
            if rt >= self.trial_window:
                # the impulsive press slipped past the window -> withheld
                self._prev_error = False
                return None, self.trial_window
            self._prev_error = True
            return go_key, float(rt)

        # successful inhibition
        self._prev_error = False
        return None, self.trial_window


def make_participant(seed):
    """Return a participant object. Same seed => identical behavior."""
    return GoNoGoParticipant(seed)
