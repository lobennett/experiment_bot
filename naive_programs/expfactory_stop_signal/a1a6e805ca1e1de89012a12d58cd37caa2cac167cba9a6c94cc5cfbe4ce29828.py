import numpy as np

MIN_RT = 150.0
GO_WINDOW_MS = 1500.0  # response window for a shape (from the task source)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class _Participant:
    """A single healthy adult performing the stop-signal task.

    Go process: an ex-Gaussian go-RT generator (the classic shape of choice
    RTs). Stop process: an independent-race stop mechanism (Logan & Cowan) --
    on a stop trial the response leaks through only when the go process would
    have finished before SSD + a (noisy) stop-signal reaction time. Because the
    task staircases SSD on the stop rate, this yields ~50% inhibition, a
    monotone inhibition function, and signal-respond RTs faster than go RTs.
    Each seed draws its own stable trait values, so participants differ.
    """

    def __init__(self, seed):
        rng = np.random.default_rng(abs(int(seed)))
        self.rng = rng

        # --- Go process (ex-Gaussian: normal mu/sigma + exponential tau) ---
        self.go_mu = _clamp(rng.normal(430.0, 35.0), 340.0, 540.0)
        self.go_sigma = _clamp(rng.normal(55.0, 12.0), 25.0, 95.0)
        self.go_tau = _clamp(rng.normal(90.0, 28.0), 40.0, 185.0)

        # --- Stop process (latency of the internal stop signal) ---
        self.ssrt_mean = _clamp(rng.normal(215.0, 30.0), 140.0, 320.0)
        self.ssrt_sd = _clamp(rng.normal(25.0, 6.0), 10.0, 45.0)

        # --- Error tendencies on go trials ---
        self.choice_err = _clamp(rng.normal(0.030, 0.018), 0.004, 0.090)
        self.omission = _clamp(rng.normal(0.012, 0.010), 0.000, 0.050)

        # --- Trial-to-trial adjustments ---
        self.post_stop_slow = _clamp(rng.normal(25.0, 15.0), 0.0, 70.0)
        self.post_error_slow = _clamp(rng.normal(30.0, 18.0), 0.0, 85.0)
        # gentle drift/arousal so RTs are not perfectly stationary
        self.drift = 0.0
        self.drift_ar = 0.96
        self.drift_sd = _clamp(rng.normal(12.0, 4.0), 4.0, 24.0)

        # learned shape-signature -> correct key (built from go trials)
        self._shape_key = {}

    # ---- helpers -------------------------------------------------------
    def _sample_go_rt(self):
        rt = self.rng.normal(self.go_mu, self.go_sigma)
        rt += self.rng.exponential(self.go_tau)
        rt += self.drift
        return max(MIN_RT, rt)

    def _step_drift(self):
        self.drift = self.drift * self.drift_ar + self.rng.normal(0.0, self.drift_sd)

    @staticmethod
    def _sig(ctx):
        s = ctx.stimulus_text
        if not s:
            return None
        return " ".join(str(s).split())

    def _pick_key(self, ctx, avoid=None):
        opts = [k for k in ctx.available_keys if k != avoid]
        if not opts:
            return avoid
        return opts[int(self.rng.integers(len(opts)))]

    # ---- required interface -------------------------------------------
    def respond(self, ctx):
        self._step_drift()
        rt = self._sample_go_rt()

        # sequential effects
        if ctx.prev_condition == "stop":
            rt += self.post_stop_slow
        if ctx.prev_correct == 0 and ctx.prev_correct is not None:
            rt += self.post_error_slow

        sig = self._sig(ctx)

        if ctx.correct_key is not None:
            # ---- GO trial ----
            if sig is not None:
                self._shape_key[sig] = ctx.correct_key
            # occasional full omission
            if self.rng.random() < self.omission:
                return (None, max(MIN_RT, rt))
            # occasional wrong-key error (fast, impulsive)
            if self.rng.random() < self.choice_err:
                wrong = self._pick_key(ctx, avoid=ctx.correct_key)
                return (wrong, max(MIN_RT, rt * 0.92))
            return (ctx.correct_key, rt)

        # ---- STOP trial: prepare the would-be go response ----
        intended_key = None
        if sig is not None and sig in self._shape_key:
            intended_key = self._shape_key[sig]
        if intended_key is None:
            intended_key = self._pick_key(ctx)  # unknown shape -> best guess
        # rare failure to even prepare a response
        if self.rng.random() < self.omission:
            return (None, max(MIN_RT, rt))
        return (intended_key, rt)

    def on_interrupt(self, ctx, ssd_ms, intended):
        # `intended` is exactly what respond() returned for this stop trial.
        if intended is None:
            return None
        key, go_rt = intended
        if key is None:
            return None  # nothing was prepared -> naturally withheld

        # Independent race: stop wins if it finishes before the go process.
        ssrt = max(40.0, self.rng.normal(self.ssrt_mean, self.ssrt_sd))
        stop_finish = float(ssd_ms) + ssrt

        # A go response can only have surfaced if it also fit in the window.
        if go_rt < stop_finish and go_rt <= GO_WINDOW_MS:
            return (key, go_rt)  # failed stop (signal-respond)
        return None  # successful inhibition


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
