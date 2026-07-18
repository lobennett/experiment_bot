import numpy as np


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)


class Participant:
    """A healthy adult doing a cued task-switching task.

    Each trial shows a word cue (Parity/Odd-Even -> odd/even judgment, or
    Magnitude/High-Low -> higher/lower-than-5 judgment) followed by a digit,
    answered with one of two keys within a 1500 ms window (digit visible for
    the first 1000 ms). Interspersed attention checks ask for a specific key.

    The correct key for every trial is supplied by the harness (ctx.correct_key),
    so behavior is modeled purely as: which key gets pressed, and when. The
    signature effects of this paradigm are captured explicitly:
      - a right-skewed (ex-Gaussian) response-time distribution,
      - slower responses when the task or the cue changes from the prior trial
        (task-switch cost > cue-switch cost), detected by reading the cue word
        out of the visible stimulus text,
      - errors that are faster than correct responses,
      - occasional omitted responses and slowness-driven misses,
      - mild warm-up speeding and post-error slowing,
      - stable individual differences across seeds.
    """

    def __init__(self, seed: int):
        self.rng = np.random.RandomState(int(seed) % (2 ** 32))
        r = self.rng

        # --- stable individual traits (each seed is a different person) ---
        self.base_rt = float(np.clip(r.normal(690, 85), 470, 980))      # ms
        self.rt_sigma = float(np.clip(r.normal(58, 13), 32, 95))        # gaussian width
        self.rt_tau = float(np.clip(r.normal(135, 40), 60, 260))        # right tail
        self.task_switch_cost = float(np.clip(r.normal(155, 50), 40, 320))
        self.cue_switch_cost = float(np.clip(r.normal(55, 22), 5, 140))
        self.base_acc = float(np.clip(r.normal(0.945, 0.030), 0.80, 0.99))
        self.switch_acc_drop = float(np.clip(r.normal(0.055, 0.025), 0.0, 0.16))
        self.lapse = float(np.clip(r.normal(0.015, 0.010), 0.0, 0.06))  # omission rate
        self.err_speedup = float(np.clip(r.normal(0.85, 0.06), 0.62, 1.0))
        self.post_error_slow = float(np.clip(r.normal(50, 22), 0, 130))
        self.warmup_ms = float(np.clip(r.normal(120, 45), 20, 230))
        self.warmup_n = 18

        # attention-check disposition
        self.ac_rt = float(np.clip(r.normal(2700, 650), 1200, 6000))
        self.ac_acc = float(np.clip(r.normal(0.975, 0.018), 0.90, 0.999))

        # task constants
        self.deadline = 1500.0
        self.min_rt = 250.0

        # running state for switch detection / warm-up
        self.prev_task = None
        self.prev_cue = None
        self.trials_seen = 0

    # ------------------------------------------------------------------ #
    def respond(self, ctx):
        if ctx.condition == "attention_check":
            return self._attention_check(ctx)
        return self._task_trial(ctx)

    # ------------------------------------------------------------------ #
    def _task_trial(self, ctx):
        self.trials_seen += 1
        task, cue = self._read_cue(ctx.stimulus_text)

        # classify transition relative to the previous task trial
        is_task_switch = False
        is_cue_switch = False
        if task is not None and self.prev_task is not None:
            if task != self.prev_task:
                is_task_switch = True
            elif cue is not None and self.prev_cue is not None and cue != self.prev_cue:
                is_cue_switch = True
        if task is not None:
            self.prev_task = task
            self.prev_cue = cue

        # --- mean RT: base + switch cost + warm-up + post-error slowing ---
        mean = self.base_rt
        if is_task_switch:
            mean += self.task_switch_cost
        elif is_cue_switch:
            mean += self.cue_switch_cost
        if self.trials_seen <= self.warmup_n:
            mean += self.warmup_ms * (1.0 - self.trials_seen / float(self.warmup_n))
        if (ctx.prev_condition == "task_switch_trial"
                and ctx.prev_correct is not None and not ctx.prev_correct):
            mean += self.post_error_slow

        # --- accuracy on this trial ---
        acc = self.base_acc
        if is_task_switch:
            acc -= self.switch_acc_drop
        elif is_cue_switch:
            acc -= self.switch_acc_drop * 0.4
        acc = min(max(acc, 0.55), 0.995)

        # omission lapse: register no response at all
        if self.rng.random() < self.lapse:
            return (None, self.deadline)

        correct = self.rng.random() < acc
        if correct or ctx.correct_key is None:
            key = ctx.correct_key
            rt = self._exgaussian(mean)
        else:
            key = self._other_key(ctx.available_keys, ctx.correct_key)
            rt = self._exgaussian(mean * self.err_speedup)  # errors run faster

        rt = float(np.clip(rt, self.min_rt, self.deadline * 3.0))
        if rt >= self.deadline:  # too slow -> no response recorded
            return (None, self.deadline)
        return (key, rt)

    # ------------------------------------------------------------------ #
    def _attention_check(self, ctx):
        ck = ctx.correct_key
        rt = self.rng.normal(self.ac_rt, self.ac_rt * 0.18) + self.rng.exponential(400.0)
        rt = float(np.clip(rt, 700.0, 14000.0))
        if ck is not None and self.rng.random() < self.ac_acc:
            return (ck, rt)
        # rare failure: either a wrong key or a timeout
        if ctx.available_keys and self.rng.random() < 0.5:
            return (self._other_key(ctx.available_keys, ck), rt)
        return (None, 14000.0)

    # ------------------------------------------------------------------ #
    def _read_cue(self, text):
        """Recover (task, cue) from the visible cue word; (None, None) if absent."""
        if not text:
            return None, None
        t = text.lower()
        if "odd-even" in t or "odd\u2013even" in t:
            return "parity", "odd-even"
        if "parity" in t:
            return "parity", "parity"
        if "high-low" in t or "high\u2013low" in t:
            return "magnitude", "high-low"
        if "magnitude" in t:
            return "magnitude", "magnitude"
        return None, None

    def _exgaussian(self, mean):
        return self.rng.normal(mean, self.rt_sigma) + self.rng.exponential(self.rt_tau)

    def _other_key(self, keys, correct_key):
        options = [k for k in keys if k != correct_key]
        if not options:
            return correct_key
        return options[self.rng.randint(len(options))]
