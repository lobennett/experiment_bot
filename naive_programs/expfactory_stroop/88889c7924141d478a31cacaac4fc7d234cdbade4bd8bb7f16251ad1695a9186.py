"""
Computational model of a healthy adult performing the RDoC Stroop task
(expfactory stroop_rdoc: congruent/incongruent color-word naming,
3-key response, 1000 ms stimulus / 1500 ms response window,
response does NOT end the trial).

Behavioral components modeled:
  - Ex-Gaussian RT distributions (mu/sigma/tau vary across participants)
  - Stroop interference on incongruent trials (RT cost + accuracy cost)
  - Congruency sequence effect (reduced interference after incongruent)
  - Post-error slowing (with error-rate reduction on the following trial)
  - Speed-up after an omission ("Respond Faster!" feedback)
  - Fast word-capture errors on incongruent trials (errors faster than
    correct incongruent responses)
  - Slow trial-to-trial fluctuation (AR(1)) plus gentle fatigue drift and
    an initial settling-in period
  - Attentional lapses producing very slow responses or omissions
  - Hard response deadline: RTs that would exceed the 1500 ms window are
    recorded as no-response, like the real platform.

Each seed yields a distinct participant whose trait parameters are drawn
from population-level distributions.
"""

import math
import random


class StroopParticipant:
    def __init__(self, seed: int):
        rng = random.Random(seed ^ 0x5DEECE66D)
        self.rng = rng

        # --- trait (between-subject) parameters ---
        self.mu = rng.gauss(560.0, 55.0)                  # gaussian component mean (ms)
        self.sigma = max(25.0, rng.gauss(55.0, 14.0))     # gaussian sd (ms)
        self.tau = max(50.0, rng.gauss(130.0, 40.0))      # exponential tail (ms)

        self.stroop = max(25.0, rng.gauss(80.0, 22.0))    # interference cost (ms)
        self.cse = min(0.85, max(0.05, rng.gauss(0.35, 0.15)))  # conflict adaptation

        self.err_con = min(0.08, max(0.004, rng.gauss(0.022, 0.011)))
        self.err_inc = min(0.22, max(0.025, rng.gauss(0.080, 0.030)))

        self.pes = max(5.0, rng.gauss(32.0, 12.0))        # post-error slowing (ms)
        self.post_miss_speedup = max(0.0, rng.gauss(25.0, 10.0))

        self.lapse_p = min(0.05, max(0.001, rng.gauss(0.012, 0.008)))
        self.drift = rng.gauss(0.10, 0.09)                # ms/trial fatigue drift
        self.warmup_amp = max(0.0, rng.gauss(55.0, 20.0)) # settling-in slowing
        self.warmup_tau = 6.0

        # slow autocorrelated attentional state (AR(1))
        self.ar_state = 0.0
        self.ar_rho = min(0.8, max(0.2, rng.gauss(0.55, 0.12)))
        self.ar_sd = max(8.0, rng.gauss(22.0, 7.0))

        self.deadline = 1500.0
        self.motor_floor = 220.0

    # ------------------------------------------------------------------

    def _prev_outcome(self, ctx):
        """Classify the previous trial: 'error', 'miss', or None."""
        if ctx.trial_index == 0 or ctx.prev_condition is None:
            return None
        if ctx.prev_rt_ms is None:
            return "miss"
        if ctx.prev_correct is False:
            return "error"
        return None

    def respond(self, ctx):
        rng = self.rng

        # advance the slow fluctuation
        self.ar_state = self.ar_rho * self.ar_state + rng.gauss(0.0, self.ar_sd)

        inc = ctx.condition == "incongruent"
        prev_inc = ctx.prev_condition == "incongruent"

        # --- interference & conflict adaptation (CSE) ---
        interference = self.stroop if inc else 0.0
        if inc and prev_inc:
            interference *= (1.0 - self.cse)
        # small congruent-trial cost after incongruent (other half of CSE)
        seq_cost = self.cse * 14.0 if (not inc) and prev_inc else 0.0

        # --- sequential adjustments from previous outcome ---
        prev_outcome = self._prev_outcome(ctx)
        adjust = 0.0
        err_scale = 1.0
        if prev_outcome == "error":
            adjust += self.pes
            err_scale = 0.6          # more cautious right after an error
        elif prev_outcome == "miss":
            adjust -= self.post_miss_speedup

        # --- base RT (ex-Gaussian + state + drift + warm-up) ---
        base = (
            self.mu
            + self.ar_state
            + self.drift * ctx.trial_index
            + self.warmup_amp * math.exp(-ctx.trial_index / self.warmup_tau)
        )

        rt = (
            base
            + interference
            + seq_cost
            + adjust
            + rng.gauss(0.0, self.sigma)
            + rng.expovariate(1.0 / self.tau)
        )

        # --- lapses ---
        lapsed = rng.random() < self.lapse_p
        if lapsed:
            rt += rng.uniform(250.0, 900.0)

        # --- error generation ---
        p_err = (self.err_inc if inc else self.err_con) * err_scale
        is_error = (not lapsed) and (rng.random() < p_err)
        if is_error and inc:
            # word-reading capture: fast, bypasses most of the conflict cost
            rt -= interference * 0.8 + rng.uniform(10.0, 50.0)

        rt = max(self.motor_floor + rng.uniform(0.0, 20.0), rt)

        # --- response window: too slow -> omission ---
        if rt >= self.deadline - 15.0:
            return (None, min(rt, self.deadline + 400.0))

        # --- choose the key ---
        correct_key = ctx.correct_key
        if not is_error or correct_key is None:
            return (correct_key, rt)

        alternatives = [k for k in ctx.available_keys if k != correct_key]
        if not alternatives:
            # no known wrong key to press yet; respond correctly instead
            return (correct_key, rt)
        return (rng.choice(alternatives), rt)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return StroopParticipant(seed)
