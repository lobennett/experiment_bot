import numpy as np


class Participant:
    """A simulated healthy adult doing a color-word interference task.

    Each seed instantiates one participant with their own trait
    parameters (baseline speed, interference cost, error proneness,
    lapse rate, learning rate), plus trial-to-trial dynamics: slow
    AR(1) fluctuations in alertness, early-task learning of the
    arbitrary key mapping, conflict adaptation (smaller interference
    after an incongruent trial), post-error slowing, fast
    "word-capture" errors on incongruent trials, and occasional
    attentional lapses that produce no response within the 1500 ms
    response window defined by the task (trial_duration = 1500,
    response does not end the trial, only the first press counts).
    """

    DEADLINE = 1500.0  # stimTrialDuration in the task source

    def __init__(self, seed):
        self.rng = np.random.default_rng(int(seed))
        r = self.rng
        # --- stable individual-difference (trait) parameters ---
        self.base_mu = float(np.clip(r.normal(600.0, 65.0), 460.0, 820.0))
        self.sigma = float(np.clip(r.normal(55.0, 15.0), 30.0, 100.0))
        self.tau = float(np.clip(r.normal(120.0, 40.0), 50.0, 260.0))
        # interference cost on incongruent trials
        self.stroop = float(np.clip(r.normal(85.0, 30.0), 25.0, 180.0))
        # proportion of the interference cost removed after an
        # incongruent trial (conflict adaptation / sequence effect)
        self.cse = float(np.clip(r.normal(0.35, 0.15), 0.0, 0.7))
        self.err_con = float(np.clip(r.normal(0.015, 0.010), 0.002, 0.05))
        self.err_inc = float(np.clip(self.err_con + r.normal(0.045, 0.025), 0.010, 0.16))
        self.lapse = float(np.clip(r.normal(0.012, 0.008), 0.0, 0.05))
        self.pes = float(np.clip(r.normal(55.0, 25.0), 0.0, 140.0))
        # learning the arbitrary color->finger mapping early on
        self.practice_extra = float(np.clip(r.normal(140.0, 50.0), 40.0, 300.0))
        self.practice_decay = float(np.clip(r.normal(0.35, 0.10), 0.15, 0.60))
        # mild slowing late in the session (ms per trial past trial 40)
        self.fatigue = float(np.clip(r.normal(0.25, 0.15), 0.0, 0.7))
        # slow trial-to-trial autocorrelated fluctuation in speed
        self.rho = 0.30
        self.drift_sd = float(np.clip(r.normal(28.0, 8.0), 10.0, 50.0))
        self.drift = 0.0
        self.n_seen = 0

    # ------------------------------------------------------------------
    def _exgauss(self, mu, sigma, tau):
        return float(self.rng.normal(mu, sigma) + self.rng.exponential(tau))

    def _wrong_key(self, ctx):
        opts = [k for k in ctx.available_keys if k != ctx.correct_key]
        if not opts:
            return ctx.correct_key
        return opts[int(self.rng.integers(len(opts)))]

    # ------------------------------------------------------------------
    def respond(self, ctx):
        r = self.rng
        cond = (ctx.condition or "").lower()
        self.n_seen += 1
        # update slow alertness fluctuation every trial
        self.drift = self.rho * self.drift + float(r.normal(0.0, self.drift_sd))

        if cond not in ("congruent", "incongruent"):
            # A non-standard probe (e.g. an instruction/attention item):
            # read it, comply, almost always correctly, at a reading pace.
            rt = float(np.clip(self._exgauss(1400.0, 350.0, 700.0), 400.0, 12000.0))
            if r.random() < 0.04:
                return (self._wrong_key(ctx), rt)
            return (ctx.correct_key, rt)

        inc = cond == "incongruent"

        # occasional attentional lapse -> nothing registered in the window
        if r.random() < self.lapse:
            return (None, self.DEADLINE)

        mu = self.base_mu + self.drift
        mu += self.practice_extra * float(np.exp(-self.practice_decay * (self.n_seen - 1)))
        mu += self.fatigue * max(0, self.n_seen - 40)

        eff = self.stroop
        err_p = self.err_inc if inc else self.err_con
        if ctx.prev_condition == "incongruent":
            # conflict adaptation: control is upregulated after conflict
            eff *= (1.0 - self.cse)
            if inc:
                err_p *= (1.0 - 0.5 * self.cse)
        if inc:
            mu += eff

        if ctx.prev_correct is False:
            # post-error slowing and a touch more caution
            mu += self.pes
            err_p *= 0.7

        if r.random() < err_p:
            if inc and r.random() < 0.75:
                # fast word-capture error: the word wins the race
                rt = self._exgauss(self.base_mu + self.drift - 20.0, self.sigma, 0.5 * self.tau)
            else:
                rt = self._exgauss(mu, self.sigma, self.tau)
            rt = float(np.clip(rt, 250.0, self.DEADLINE - 10.0))
            return (self._wrong_key(ctx), rt)

        rt = self._exgauss(mu, self.sigma, self.tau)
        if rt >= self.DEADLINE - 5.0:
            # correct intention, but too slow to land inside the window
            return (None, self.DEADLINE)
        return (ctx.correct_key, max(rt, 250.0))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)
