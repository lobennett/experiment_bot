"""
Computational model of a healthy adult participant performing a short
(15-trial) online Stroop task (cognition.run, jsPsych 7).

Task properties inferred from source:
  - 15 trials, ~50% congruent / 50% incongruent (Math.random per trial)
  - stimulus: colour word in a (matching or mismatching) font colour
  - response: first letter of the FONT COLOUR ('r','g','b','y'),
    no response deadline, response ends trial
  - each trial preceded by 250 ms blank + 500 ms fixation

Behavioural model:
  - Ex-Gaussian RT (mu + sigma + tau) with per-participant parameters
    drawn from population distributions typical of manual 4-choice Stroop.
  - Stroop interference on incongruent trials (per-participant magnitude),
    small facilitation on congruent trials.
  - Congruency sequence effect (reduced interference after incongruent).
  - Start-of-task slowing + practice speed-up over the short block.
  - Post-error slowing.
  - Trial-to-trial RT autocorrelation (slow attentional drift).
  - Occasional attentional lapses (long right-tail RTs).
  - Errors: mostly word-capture on incongruent trials (fast errors),
    rare slips on congruent trials; per-participant error proneness.
"""

import math
import random


class Participant:
    def __init__(self, seed: int):
        rng = random.Random(seed)
        self._rng = rng

        # --- stable individual differences (population-level variation) ---
        # Ex-Gaussian components for a congruent-baseline manual Stroop RT.
        self.mu = rng.gauss(640.0, 80.0)            # central tendency (ms)
        self.mu = max(450.0, min(900.0, self.mu))
        self.sigma = max(35.0, rng.gauss(85.0, 22.0))
        self.tau = max(60.0, rng.gauss(180.0, 70.0))  # right skew

        # Stroop interference (incongruent cost) and congruent facilitation.
        self.interference = max(20.0, rng.gauss(105.0, 45.0))
        self.facilitation = max(0.0, rng.gauss(25.0, 15.0))

        # Congruency sequence effect: interference shrinks after an
        # incongruent trial (per-person proportional reduction).
        self.cse_frac = min(0.8, max(0.0, rng.gauss(0.35, 0.20)))

        # Practice/warm-up over the short block.
        self.first_trial_extra = max(0.0, rng.gauss(220.0, 110.0))
        self.warmup_extra = max(0.0, rng.gauss(90.0, 50.0))   # decays fast
        self.practice_slope = rng.gauss(4.5, 2.5)             # ms per trial

        # Post-error slowing.
        self.pes = max(0.0, rng.gauss(70.0, 40.0))

        # Slow drift / autocorrelation in readiness.
        self.drift = 0.0
        self.drift_sd = max(5.0, rng.gauss(28.0, 12.0))
        self.drift_ar = 0.75

        # Lapses (mind-wandering -> very long RT).
        self.lapse_p = min(0.12, max(0.005, rng.gauss(0.035, 0.025)))
        self.lapse_extra_mean = rng.uniform(350.0, 900.0)

        # Error proneness (individual multiplier on base error rates).
        prone = math.exp(rng.gauss(0.0, 0.5))
        self.p_err_incong = min(0.30, 0.09 * prone)   # word-capture etc.
        self.p_err_cong = min(0.10, 0.02 * prone)     # slips / wrong finger
        # Speed-accuracy: faster people commit slightly more errors.
        speed_z = (640.0 - self.mu) / 80.0
        adj = math.exp(0.25 * speed_z)
        self.p_err_incong = min(0.35, self.p_err_incong * adj)
        self.p_err_cong = min(0.12, self.p_err_cong * adj)

        self._made_error_last = False

    # ------------------------------------------------------------------
    def _ex_gauss(self, mu, sigma, tau):
        r = self._rng
        return r.gauss(mu, sigma) + r.expovariate(1.0 / tau)

    def respond(self, ctx):
        r = self._rng
        cond = (ctx.condition or "").lower()
        incong = "incongruent" in cond

        # -------- error decision --------
        p_err = self.p_err_incong if incong else self.p_err_cong
        # a little more error-prone right after an error (rattled)
        if ctx.prev_correct is False:
            p_err = min(0.5, p_err * 1.3)
        is_error = r.random() < p_err

        # -------- RT --------
        rt = self._ex_gauss(self.mu, self.sigma, self.tau)

        # condition effect, modulated by previous-trial congruency (CSE)
        if incong:
            cost = self.interference
            if ctx.prev_condition and "incongruent" in ctx.prev_condition.lower():
                cost *= (1.0 - self.cse_frac)
            rt += cost * r.uniform(0.6, 1.4)
        else:
            rt -= self.facilitation * r.uniform(0.5, 1.5)

        # warm-up / practice over the 15-trial block
        t = ctx.trial_index
        if t == 0:
            rt += self.first_trial_extra
        rt += self.warmup_extra * math.exp(-t / 2.5)
        rt -= self.practice_slope * min(t, 14)

        # post-error slowing
        if ctx.prev_correct is False:
            rt += self.pes * r.uniform(0.5, 1.5)

        # slow autocorrelated drift in readiness
        self.drift = (self.drift_ar * self.drift
                      + r.gauss(0.0, self.drift_sd * math.sqrt(1 - self.drift_ar ** 2)))
        rt += self.drift

        # occasional lapse -> long RT (no deadline, so still responds)
        if r.random() < self.lapse_p:
            rt += r.expovariate(1.0 / self.lapse_extra_mean)

        # errors on incongruent trials are typically fast (word capture)
        if is_error and incong and r.random() < 0.7:
            rt -= abs(r.gauss(120.0, 60.0))

        rt = max(280.0, rt)

        # -------- key choice --------
        correct = ctx.correct_key
        if not is_error or correct is None:
            key = correct
        else:
            options = [k for k in ("r", "g", "b", "y")
                       if k != correct]
            avail = [k for k in ctx.available_keys if k != correct]
            if avail:
                options = avail
            key = r.choice(options)

        return (key, float(rt))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)
