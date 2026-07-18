import numpy as np


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return VisualSearchParticipant(seed)


class VisualSearchParticipant:
    """A typical healthy adult doing the visual-search (feature/conjunction) task.

    Observability note: the task's set size (8 vs 24) and whether the target is
    actually present are NOT exposed on ctx (the stimulus is drawn boxes, no
    text; correct_key encodes present/absent but not which direction). So those
    factors are treated as latent variables sampled per trial. This reproduces
    the correct marginal RT distribution per condition (feature ~ pop-out/flat,
    conjunction ~ slower, right-skewed, more errors) even though the per-trial
    set-size slope cannot be conditioned on.
    """

    def __init__(self, seed):
        self.rng = np.random.default_rng(int(seed))
        r = self.rng

        # --- Non-decision / motor floor -------------------------------------
        self.t0 = float(np.clip(r.normal(260, 30), 190, 360))

        # --- Global speed and caution (speed/accuracy trade-off) ------------
        self.speed = float(np.exp(r.normal(0.0, 0.13)))      # ~0.77 .. 1.30
        self.caution = float(r.normal(0.0, 1.0))             # higher -> slower/accurater
        self.ability = float(r.normal(0.0, 1.0))             # higher -> fewer errors

        # --- Feature search: efficient, nearly flat over set size -----------
        self.feat_intercept = float(r.normal(500, 45))
        self.feat_slope = float(abs(r.normal(2.5, 2.0)))     # ms / item

        # --- Conjunction search: serial-like, steeper for target-absent -----
        self.conj_intercept = float(r.normal(560, 60))
        self.conj_slope_present = float(abs(r.normal(22.0, 6.0)))
        self.conj_slope_absent = float(abs(r.normal(40.0, 10.0)))

        # --- Ex-Gaussian right tail -----------------------------------------
        self.tau = float(max(r.normal(130, 35), 60))

        # --- Error / lapse rates --------------------------------------------
        self.err_feature = float(np.clip(r.normal(0.020, 0.010), 0.003, 0.06))
        self.err_conj = float(np.clip(r.normal(0.060, 0.025), 0.010, 0.15))
        self.lapse = float(np.clip(r.normal(0.020, 0.012), 0.002, 0.06))

        # Task response window (trial_duration in the source is 2000 ms;
        # the keyboard listener is active for the whole trial).
        self.deadline = 2000.0

    def _latent_setsize(self):
        # Blocks are balanced 8 vs 24.
        return 8 if self.rng.random() < 0.5 else 24

    def _latent_present(self):
        # Blocks are balanced present vs absent.
        return self.rng.random() < 0.5

    def _sample_rt(self, target_mean, tau):
        """Ex-Gaussian sample with expectation == target_mean."""
        r = self.rng
        mu = target_mean - tau
        sigma = 0.11 * target_mean
        rt = r.normal(mu, sigma) + r.exponential(tau)
        return max(rt, self.t0)

    def respond(self, ctx):
        r = self.rng
        cond = ctx.condition
        keys = tuple(ctx.available_keys) if ctx.available_keys else (",", ".")
        correct_key = ctx.correct_key

        # Alternative key (for commission errors / guesses).
        others = [k for k in keys if k != correct_key]
        other_key = others[0] if others else (keys[0] if keys else correct_key)

        # ---- Latent trial difficulty ---------------------------------------
        setsize = self._latent_setsize()
        present = self._latent_present()

        if cond == "feature":
            target_mean = self.feat_intercept + self.feat_slope * setsize
            if not present:
                target_mean += 25.0 + 1.0 * setsize      # absent a touch slower
            base_err = self.err_feature
            tau = self.tau
        else:
            # conjunction (also the fallback for any unexpected label)
            slope = self.conj_slope_present if present else self.conj_slope_absent
            target_mean = self.conj_intercept + slope * setsize
            base_err = self.err_conj
            tau = self.tau * 1.2                          # heavier tail

        # ---- Global modulators ---------------------------------------------
        target_mean *= (1.0 + 0.06 * self.caution)       # cautious -> slower
        target_mean *= self.speed

        ti = ctx.trial_index if ctx.trial_index is not None else 0
        if ti < 6:                                        # warm-up
            target_mean *= (1.0 + 0.12 * (6 - ti) / 6.0)

        if ctx.prev_correct == 0 or ctx.prev_interrupted:  # post-error slowing
            target_mean *= 1.05

        # ---- Attentional lapse: guess or omission --------------------------
        if r.random() < self.lapse:
            if r.random() < 0.4:
                return (None, self.deadline)
            rt = float(np.clip(self.t0 + r.exponential(tau) + r.normal(420, 130),
                               200.0, self.deadline - 1.0))
            return (keys[int(r.integers(len(keys)))], rt)

        # ---- Sample RT ------------------------------------------------------
        rt = self._sample_rt(target_mean, tau)
        if rt >= self.deadline:                          # missed the window
            return (None, self.deadline)
        rt = float(max(rt, 150.0))

        # If no defined correct key, just emit a plausible keypress.
        if correct_key is None:
            return (keys[int(r.integers(len(keys)))], rt)

        # ---- Correct vs error ----------------------------------------------
        err_p = base_err
        if cond == "conjunction":
            err_p += 0.004 * setsize
            if present and setsize == 24:
                err_p += 0.03                            # fail to find the target
        err_p *= float(np.exp(-0.25 * self.caution - 0.15 * self.ability))
        err_p = float(np.clip(err_p, 0.002, 0.40))

        if r.random() < err_p:
            return (other_key, rt)
        return (correct_key, rt)
