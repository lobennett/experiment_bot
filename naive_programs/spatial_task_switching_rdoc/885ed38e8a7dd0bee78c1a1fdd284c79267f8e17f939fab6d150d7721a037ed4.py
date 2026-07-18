import numpy as np


def make_participant(seed: int):
    """Return a participant object whose behavior is fixed by `seed`."""
    return Participant(seed)


class Participant:
    """A generative model of one healthy adult doing spatial task-switching.

    The page shows a shape in one of four screen quadrants. Which feature
    (form vs. color) is judged depends on the quadrant, and the two answers
    map onto the comma / period keys. The harness resolves the correct key
    per trial (ctx.correct_key), so this model only has to decide (a) whether
    it answers correctly, (b) whether it answers at all, and (c) how long it
    takes -- as a function of the trial-to-trial control demand encoded in
    ctx.condition.

    Timing the model lives under (from the task source):
      fixation 500 ms -> cue 150 ms -> stimulus (visible 1000 ms) with a
      1500 ms response window that does NOT end early on a keypress.
    A sampled RT beyond the 1500 ms deadline becomes an omission.
    """

    RESPONSE_DEADLINE_MS = 1500.0
    RT_FLOOR_MS = 180.0

    # Relative control demand of each condition. task_stay_cue_stay is the
    # easy baseline; changing the cue (but not the task) costs a little;
    # changing the task itself costs the most.
    _ORDER = {
        "task_stay_cue_stay": 0,
        "task_stay_cue_switch": 1,
        "task_switch_cue_switch": 2,
    }

    def __init__(self, seed: int):
        self.rng = np.random.RandomState(seed)
        r = self.rng

        # ---- stable individual traits (participants differ here) ----
        # Overall processing speed: ex-Gaussian mu/sigma/tau for the baseline
        # condition. tau carries the long right tail real RT distributions have.
        self.mu = float(r.normal(430, 55))          # ms, Gaussian center
        self.sigma = float(r.uniform(28, 55))       # ms, Gaussian spread
        self.tau = float(r.normal(135, 35))         # ms, exponential tail
        self.mu = max(self.mu, 300.0)
        self.tau = max(self.tau, 60.0)

        # Switch costs (ms added to mu), scaled by a personal "flexibility":
        # more flexible people pay smaller costs. Cue-switch < task-switch.
        flex = float(r.uniform(0.6, 1.4))
        self.cue_switch_cost = max(0.0, float(r.normal(55, 18))) * flex
        self.task_switch_cost = max(0.0, float(r.normal(140, 40))) * flex

        # Accuracy: baseline error rate, plus extra errors under higher demand.
        self.base_err = float(np.clip(r.normal(0.055, 0.02), 0.01, 0.14))
        self.cue_switch_err = max(0.0, float(r.normal(0.02, 0.012)))
        self.task_switch_err = max(0.0, float(r.normal(0.055, 0.025)))

        # Attentional lapses -> occasional omissions independent of demand.
        self.lapse_rate = float(np.clip(r.normal(0.012, 0.008), 0.0, 0.05))

        # Fast-guess tendency: a small share of very fast, near-chance responses.
        self.guess_rate = float(np.clip(r.normal(0.02, 0.015), 0.0, 0.08))

        # Post-error caution: slow down and get more careful after a mistake.
        self.post_error_slowing = max(0.0, float(r.normal(45, 20)))

        # A mild warm-up: the first handful of trials run a touch slower.
        self._trials_seen = 0

    # ------------------------------------------------------------------ #

    def _demand(self, condition):
        """Map a condition label to (rt_cost_ms, extra_error_prob)."""
        level = self._ORDER.get(condition, None)
        if level == 0:
            return 0.0, 0.0
        if level == 1:
            return self.cue_switch_cost, self.cue_switch_err
        if level == 2:
            return self.task_switch_cost, self.task_switch_err
        # Unknown / "na" (e.g. first trial of a block): treat as baseline.
        return 0.0, 0.0

    def _sample_rt(self, mu_shift):
        rt = (self.mu + mu_shift
              + self.rng.normal(0.0, self.sigma)
              + self.rng.exponential(self.tau))
        return rt

    def _other_key(self, ctx):
        """Pick a plausible wrong key (the alternative response option)."""
        keys = tuple(k for k in ctx.available_keys if k is not None)
        alts = [k for k in keys if k != ctx.correct_key]
        if alts:
            return alts[self.rng.randint(len(alts))]
        if keys:
            return keys[self.rng.randint(len(keys))]
        return ctx.correct_key

    def respond(self, ctx):
        self._trials_seen += 1

        rt_cost, extra_err = self._demand(ctx.condition)

        # Post-error slowing / extra caution after a mistake or an omission.
        careful = False
        if ctx.prev_correct == 0 or ctx.prev_interrupted:
            rt_cost += self.post_error_slowing
            careful = True

        # Brief warm-up over the first few trials.
        if self._trials_seen <= 4:
            rt_cost += (5 - self._trials_seen) * 12.0

        # ---- attentional lapse: no response at all ----
        if self.rng.random() < self.lapse_rate:
            return (None, self.RESPONSE_DEADLINE_MS)

        # ---- fast guess: quick, near-chance response ----
        if self.rng.random() < self.guess_rate:
            rt = float(np.clip(self.rng.normal(280, 60),
                               self.RT_FLOOR_MS, self.RESPONSE_DEADLINE_MS))
            key = ctx.correct_key if self.rng.random() < 0.5 else self._other_key(ctx)
            if key is None:
                key = self._other_key(ctx)
            return (key, rt)

        # ---- ordinary decision ----
        err_p = self.base_err + extra_err
        if careful:
            err_p *= 0.75  # post-error accuracy tends to recover a bit
        err_p = float(np.clip(err_p, 0.0, 0.6))

        rt = self._sample_rt(rt_cost)

        # RT beyond the response window -> omission (missed response).
        if rt > self.RESPONSE_DEADLINE_MS:
            return (None, self.RESPONSE_DEADLINE_MS)

        rt = max(rt, self.RT_FLOOR_MS)

        if ctx.correct_key is None:
            # No defined correct key this trial: respond at random.
            return (self._other_key(ctx), float(rt))

        if self.rng.random() < err_p:
            # Errors tend to be slightly faster (premature commitment).
            rt = max(self.RT_FLOOR_MS, rt - abs(self.rng.normal(25, 20)))
            return (self._other_key(ctx), float(rt))

        return (ctx.correct_key, float(rt))
