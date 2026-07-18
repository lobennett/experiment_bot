import numpy as np


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _StroopParticipant(int(seed))


class _StroopParticipant:
    """A typical healthy adult doing a color-word (Stroop) task.

    Each trial shows a color word printed in some ink color; the task is to
    report the INK COLOR with one of three keys. The correct key for the
    current trial is always ctx.correct_key. The behavioral signature of a
    real participant here is (a) fast, highly accurate responses on congruent
    trials, (b) slower and slightly more error-prone responses when the word
    and ink conflict (interference), (c) trial-to-trial control adjustments,
    and (d) occasional attentional lapses. All of that is modeled below, with
    stable individual traits drawn once per participant so that different
    seeds behave like different people.
    """

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(seed)
        r = self.rng

        # ---- stable individual traits (drawn once per participant) ----
        # Overall processing speed: congruent-trial baseline (ms).
        self.mu_cong = float(np.clip(r.normal(600.0, 75.0), 440.0, 820.0))
        # Gaussian spread and exponential (right-skew) tail of the RT dist.
        self.sigma = float(np.clip(r.normal(55.0, 12.0), 30.0, 95.0))
        self.tau_cong = float(np.clip(r.normal(110.0, 30.0), 55.0, 210.0))

        # Interference: how much slower / more error-prone when incongruent.
        self.stroop_rt = float(np.clip(r.normal(75.0, 30.0), 15.0, 190.0))
        self.stroop_tau = float(np.clip(r.normal(40.0, 22.0), 0.0, 120.0))

        # Accuracy. Congruent is near-ceiling; incongruent is somewhat lower.
        self.acc_cong = float(np.clip(r.normal(0.990, 0.008), 0.950, 0.999))
        interference_err = float(np.clip(r.normal(0.050, 0.030), 0.005, 0.16))
        self.acc_incong = float(
            np.clip(self.acc_cong - interference_err, 0.800, 0.999)
        )

        # Attentional lapses -> occasional omissions (no response).
        self.lapse = float(np.clip(r.normal(0.012, 0.010), 0.0, 0.05))

        # Trial-to-trial control adjustments.
        # Post-error slowing: participants slow down after a mistake.
        self.post_error_slow = float(np.clip(r.normal(1.08, 0.04), 1.0, 1.25))
        # Congruency-sequence effect: interference is reduced right after an
        # incongruent trial (control carried over). Strength varies by person.
        self.cse = float(np.clip(r.normal(0.40, 0.15), 0.0, 0.70))

        # Warm-up: a little extra slowness at the very start that fades with
        # practice.
        self.warmup_ms = float(np.clip(r.normal(70.0, 30.0), 0.0, 160.0))
        self.warmup_scale = float(r.uniform(20.0, 45.0))

        # Task constraints (from the source): the trial lasts 1500 ms, so a
        # response later than that is never registered.
        self.deadline = 1500.0
        self.min_rt = 180.0

    def _ex_gaussian(self, mu: float, sigma: float, tau: float) -> float:
        return float(self.rng.normal(mu, sigma) + self.rng.exponential(tau))

    def _wrong_key(self, ctx):
        keys = ctx.available_keys
        if not keys:
            return None
        alts = [k for k in keys if k != ctx.correct_key]
        if not alts:
            return None
        return alts[int(self.rng.integers(len(alts)))]

    def respond(self, ctx):
        incong = ctx.condition == "incongruent"

        # Congruency-sequence effect: shrink interference after an incongruent
        # trial (heightened control carries over).
        cse_factor = 1.0
        if incong and ctx.prev_condition == "incongruent":
            cse_factor = 1.0 - self.cse

        # ---- assemble the RT distribution for this trial ----
        mu = self.mu_cong
        tau = self.tau_cong
        if incong:
            mu += self.stroop_rt * cse_factor
            tau += self.stroop_tau * cse_factor

        # Practice warm-up (decays over the first trials).
        mu += self.warmup_ms * float(np.exp(-ctx.trial_index / self.warmup_scale))

        # Post-error slowing.
        if ctx.prev_correct is False:
            mu *= self.post_error_slow

        # ---- accuracy for this trial ----
        acc = self.acc_incong if incong else self.acc_cong
        if incong and cse_factor < 1.0:
            # Heightened control also reduces errors, not just RT.
            acc = min(0.999, acc + (1.0 - acc) * self.cse)

        # Attentional lapse -> omission.
        if self.rng.random() < self.lapse:
            return (None, self.deadline)

        correct = self.rng.random() < acc

        if correct:
            rt = self._ex_gaussian(mu, self.sigma, tau)
        else:
            # Errors tend to be a bit faster (automatic word-reading capture).
            rt = self._ex_gaussian(mu * 0.90, self.sigma, tau * 0.80)

        rt = max(self.min_rt, rt)

        # A response past the response window is not registered.
        if rt >= self.deadline:
            return (None, self.deadline)

        if correct or ctx.correct_key is None:
            return (ctx.correct_key, rt)

        wrong = self._wrong_key(ctx)
        if wrong is None:
            return (ctx.correct_key, rt)
        return (wrong, rt)
