"""
Computational model of a healthy adult participant performing a go/nogo task
(6:1 go:nogo, spacebar response to filled square, withhold to outlined square,
1000 ms stimulus / 1500 ms response window, practice + 3 test blocks).

Each seed instantiates a distinct participant with stable traits (speed,
variability, inhibitory control, lapse rate, fatigue) plus trial-to-trial
dynamics (prepotency build-up over go runs, post-error slowing and control
up-regulation, slow autocorrelated drift, early practice speed-up).
"""

import numpy as np


class _Participant:
    def __init__(self, seed):
        self.rng = np.random.default_rng(int(seed))
        r = self.rng

        # --- stable individual traits -------------------------------------
        # ex-Gaussian RT parameters for correct go responses
        self.mu = float(np.clip(r.normal(380.0, 45.0), 290.0, 520.0))
        self.sigma = float(np.clip(r.normal(45.0, 12.0), 22.0, 85.0))
        self.tau = float(np.clip(r.normal(95.0, 35.0), 35.0, 220.0))
        # inhibitory control: baseline probability of a commission on nogo
        self.p_commit = float(np.clip(r.beta(2.2, 6.5), 0.03, 0.60))
        # attention: go-trial omission and lapse (very slow response) rates
        self.p_omit = float(np.clip(r.beta(1.3, 55.0), 0.002, 0.10))
        self.p_lapse = float(np.clip(r.beta(1.5, 40.0), 0.002, 0.12))
        # slow time-on-task drift (ms per trial) and early practice speed-up
        self.fatigue = float(np.clip(r.normal(0.10, 0.09), -0.05, 0.35))
        self.practice_amp = float(np.clip(r.normal(45.0, 22.0), 0.0, 120.0))
        self.practice_tau = float(np.clip(r.normal(14.0, 5.0), 6.0, 30.0))
        # sequential dynamics
        self.pes = float(np.clip(r.normal(55.0, 25.0), 0.0, 150.0))          # post-error slowing (ms)
        self.run_speed = float(np.clip(r.normal(4.0, 2.0), 0.0, 10.0))       # ms faster per consecutive go
        self.run_commit = float(np.clip(r.normal(0.020, 0.012), 0.0, 0.06))  # commission boost per consecutive go
        self.post_err_ctrl = float(np.clip(r.normal(0.55, 0.12), 0.3, 0.9))  # commission multiplier after an error
        # failed inhibitions are faster than correct go responses
        self.commit_speed = float(np.clip(r.normal(0.90, 0.04), 0.78, 1.00))

        # --- evolving state ------------------------------------------------
        self._n = 0            # trials completed
        self._go_run = 0       # consecutive go trials immediately preceding now
        self._just_erred = False
        self._drift = 0.0      # slow AR(1) RT drift
        self._go_key = " "     # learned from ctx.correct_key on go trials

    # -- helpers -----------------------------------------------------------
    def _exgauss(self, mu, sigma, tau):
        return float(self.rng.normal(mu, sigma) + self.rng.exponential(tau))

    def _mu_now(self):
        mu = self.mu
        mu += self.practice_amp * float(np.exp(-self._n / self.practice_tau))
        mu += self.fatigue * self._n
        mu += self._drift
        mu -= self.run_speed * min(self._go_run, 6)
        if self._just_erred:
            mu += self.pes
        return mu

    def _advance(self, condition, correct):
        self._drift = 0.97 * self._drift + float(self.rng.normal(0.0, 7.0))
        self._n += 1
        if condition == "go":
            self._go_run += 1
        else:
            self._go_run = 0
        self._just_erred = not correct

    # -- trial types ---------------------------------------------------------
    def _go_trial(self, ctx):
        if ctx.correct_key is not None:
            self._go_key = ctx.correct_key
        # occasional outright omission (attention elsewhere)
        p_omit = min(0.5, self.p_omit + 0.0002 * self._n)
        if self.rng.random() < p_omit:
            self._advance("go", correct=False)
            return (None, 900.0)
        rt = self._exgauss(self._mu_now(), self.sigma, self.tau)
        if self.rng.random() < self.p_lapse:
            rt += float(self.rng.exponential(250.0))
        rt = max(160.0, rt)
        if rt > 1470.0:
            # too slow for the 1500 ms window -> effectively a miss
            self._advance("go", correct=False)
            return (None, 1200.0)
        self._advance("go", correct=True)
        return (self._go_key, float(rt))

    def _nogo_trial(self, ctx):
        p = self.p_commit + self.run_commit * min(self._go_run, 6)
        if self._just_erred:
            p *= self.post_err_ctrl
        p = float(np.clip(p, 0.0, 0.85))
        if self.rng.random() < p:
            # failed inhibition: fast, tight RT distribution
            rt = self._exgauss(self._mu_now() * self.commit_speed,
                               self.sigma, self.tau * 0.5)
            rt = float(np.clip(rt, 160.0, 1300.0))
            self._advance("nogo", correct=False)
            return (self._go_key, rt)
        self._advance("nogo", correct=True)
        return (None, 1000.0)

    def _other_trial(self, ctx):
        # defensive fallback for any unexpected phase the task exposes
        rt = float(np.clip(self._exgauss(750.0, 180.0, 250.0), 300.0, 4000.0))
        if ctx.correct_key is not None:
            return (ctx.correct_key, rt)
        if getattr(ctx, "response_elements", ()):
            return ("click", 0, rt)
        if ctx.available_keys:
            return (ctx.available_keys[0], rt)
        return (None, rt)

    # -- contract entry point ------------------------------------------------
    def respond(self, ctx):
        cond = (ctx.condition or "").strip().lower()
        if cond == "go":
            return self._go_trial(ctx)
        if cond == "nogo":
            return self._nogo_trial(ctx)
        return self._other_trial(ctx)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
