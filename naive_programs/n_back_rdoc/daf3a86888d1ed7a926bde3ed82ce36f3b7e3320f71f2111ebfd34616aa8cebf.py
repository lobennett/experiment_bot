"""
Generative participant model for a letter n-back task (delays 1 and 2,
uppercase/lowercase-insensitive match vs. mismatch judgments, fixed
1500 ms response window, buffer trials opening each block).

Each seed instantiates one simulated adult whose latent traits (speed,
ex-Gaussian RT shape, discrimination ability, working-memory load costs,
lapse/omission propensity, sequential effects, fatigue and practice
dynamics, slow alertness drift) are drawn from population distributions,
so different seeds behave like different people while a single seed is
fully reproducible.

The block's n-back delay is never given directly, so the model infers it
the way the task structure reveals it: each block opens with `delay`
buffer trials, so the length of a run of "buffer" conditions tells the
participant whether the coming block is 1-back or 2-back, and load
effects (slower, less accurate responding at delay 2, hitting matches
harder than rejecting mismatches) are applied accordingly.
"""

import math
import random


def _logistic(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


class _Participant:
    RESPONSE_WINDOW_MS = 1500.0
    KNOWN_CONDITIONS = ("match", "mismatch", "buffer")

    def __init__(self, seed):
        r = random.Random((int(seed) * 2654435761 + 0x5EED) % (2 ** 63))
        self.rng = r

        # --- RT traits: ex-Gaussian(mu, sigma, tau) in ms ---
        self.mu = r.gauss(540.0, 65.0)
        self.sigma = max(25.0, r.gauss(60.0, 18.0))
        self.tau = max(35.0, r.gauss(115.0, 45.0))

        # condition-level RT effects
        self.match_rt_shift = r.gauss(15.0, 25.0)      # targets vs. rejections
        self.load_rt_cost = max(0.0, r.gauss(95.0, 45.0))   # 2-back slowing
        self.buffer_rt_shift = r.gauss(30.0, 20.0)     # block-start sluggishness

        # --- accuracy traits (logit scale) ---
        self.cr_logit = r.gauss(3.1, 0.6)              # correct-reject mismatch
        self.hit_logit = r.gauss(2.4, 0.7)             # hit on match (misses > FAs)
        self.load_acc_cost_match = max(0.0, r.gauss(0.9, 0.35))
        self.load_acc_cost_mismatch = max(0.0, r.gauss(0.35, 0.2))
        self.buffer_logit = r.gauss(3.3, 0.7)          # "respond mismatch first"

        # --- lapses, omissions, guesses ---
        self.lapse_p = min(0.12, max(0.002, r.gauss(0.022, 0.016)))
        self.omit_p = min(0.08, max(0.001, r.gauss(0.015, 0.012)))
        self.anticip_p = min(0.02, max(0.0, r.gauss(0.004, 0.004)))
        self.fast_error_p = min(0.9, max(0.1, r.gauss(0.55, 0.15)))

        # --- sequential and slow dynamics ---
        self.post_error_slow = max(0.0, r.gauss(45.0, 25.0))
        self.post_error_acc = max(0.0, r.gauss(0.25, 0.15))
        self.fatigue_rt = max(0.0, r.gauss(0.12, 0.09))        # ms / trial
        self.fatigue_acc = max(0.0, r.gauss(0.0025, 0.0018))   # logit / trial
        self.practice_gain = max(0.0, r.gauss(60.0, 30.0))     # early slowing
        self.drift = 0.0                                       # AR(1) alertness
        self.drift_rho = 0.985
        self.drift_sd = max(2.0, r.gauss(9.0, 4.5))

        # attention-check compliance
        self.check_comply_p = min(0.999, max(0.7, r.gauss(0.96, 0.04)))

        # block/delay bookkeeping
        self.delay = 1
        self.buffer_run = 0
        self.seen_trials = 0

    # ------------------------------------------------------------------ #

    def _exgauss(self):
        r = self.rng
        return r.gauss(self.mu, self.sigma) + r.expovariate(1.0 / self.tau)

    def _other_key(self, ctx):
        alts = [k for k in ctx.available_keys if k != ctx.correct_key]
        if alts:
            return self.rng.choice(alts)
        return None

    def _unknown_trial(self, ctx):
        # e.g. an interleaved probe with an instructed key and a long window:
        # comply after reading, occasionally err or time out.
        r = self.rng
        if ctx.correct_key is not None and r.random() < self.check_comply_p:
            rt = min(14000.0, max(900.0, r.lognormvariate(8.15, 0.45)))
            return (ctx.correct_key, rt)
        keys = list(ctx.available_keys)
        if keys and r.random() < 0.5:
            rt = min(14000.0, max(900.0, r.lognormvariate(8.3, 0.5)))
            return (r.choice(keys), rt)
        return (None, 5000.0)

    # ------------------------------------------------------------------ #

    def respond(self, ctx):
        cond = ctx.condition
        if cond not in self.KNOWN_CONDITIONS:
            return self._unknown_trial(ctx)

        r = self.rng

        # infer the block's n-back delay from the buffer run that opens it
        if cond == "buffer":
            self.buffer_run += 1
        else:
            if self.buffer_run:
                self.delay = max(1, min(2, self.buffer_run))
            self.buffer_run = 0
        load = self.delay if cond != "buffer" else max(1, min(2, self.buffer_run))

        # slow alertness drift (AR(1), ms)
        self.drift = self.drift_rho * self.drift + r.gauss(0.0, self.drift_sd)

        t = self.seen_trials
        self.seen_trials += 1

        if ctx.correct_key is None:
            return (None, 1.0)

        # occasional anticipatory keypress before processing the stimulus
        if r.random() < self.anticip_p and ctx.available_keys:
            return (r.choice(list(ctx.available_keys)),
                    float(r.uniform(150.0, 280.0)))

        # attentional lapse: either miss the trial or guess late
        if r.random() < self.lapse_p:
            if r.random() < 0.55 or not ctx.available_keys:
                return (None, 1200.0)
            rt = min(self.RESPONSE_WINDOW_MS - 15.0,
                     max(700.0, self._exgauss() + 350.0))
            return (r.choice(list(ctx.available_keys)), float(rt))

        # plain omission (drifting off, hand off keys)
        if r.random() < self.omit_p + 0.00008 * t:
            return (None, 1200.0)

        # ---------------- accuracy ----------------
        if cond == "match":
            logit = self.hit_logit - (load - 1) * self.load_acc_cost_match
        elif cond == "mismatch":
            logit = self.cr_logit - (load - 1) * self.load_acc_cost_mismatch
        else:
            logit = self.buffer_logit
        logit -= self.fatigue_acc * t
        logit -= 0.6 * math.exp(-t / 8.0)          # still learning early on
        if ctx.prev_correct is False:
            logit += self.post_error_acc           # careful after an error
        correct = r.random() < _logistic(logit)

        # ---------------- response time ----------------
        rt = self._exgauss()
        rt += (load - 1) * self.load_rt_cost
        if cond == "match":
            rt += self.match_rt_shift
        elif cond == "buffer":
            rt += self.buffer_rt_shift
        rt += self.fatigue_rt * t
        rt += self.practice_gain * math.exp(-t / 12.0)
        rt += self.drift
        if ctx.prev_correct is False:
            rt += self.post_error_slow
        if not correct:
            if r.random() < self.fast_error_p:
                rt -= abs(r.gauss(90.0, 40.0))     # impulsive fast error
            else:
                rt += abs(r.gauss(60.0, 50.0))     # confused slow error

        rt = max(220.0, rt)
        if rt >= self.RESPONSE_WINDOW_MS - 10.0:
            return (None, 1200.0)                  # too slow: window closed

        if correct:
            key = ctx.correct_key
        else:
            key = self._other_key(ctx)
            if key is None:
                return (None, float(min(rt, 1400.0)))

        return (key, float(rt))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
