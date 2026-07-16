"""Generative participant model for a cued task-switching experiment.

Each seed instantiates one simulated adult participant. The participant
carries stable individual traits (overall speed, RT variability, error
proneness, sensitivity to task/cue changes, lapse rate) drawn once from
population-level distributions, plus trial-to-trial dynamics: slowing
when the cued task changes, slowing after errors, gradual practice
speed-up and mild fatigue, occasional attentional lapses, and slightly
faster error responses. The model reads the visible cue word (and, when
possible, the digit) from ctx.stimulus_text to infer trial-to-trial task
structure, and incrementally learns the response mapping so that
cross-task response conflict can influence speed and accuracy.
"""

import math
import random
import re


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)


class _Participant:
    # cue token -> task; order matters (compound cues checked first)
    _CUES = (
        ("odd-even", "parity"),
        ("parity", "parity"),
        ("high-low", "magnitude"),
        ("magnitude", "magnitude"),
    )

    def __init__(self, seed):
        rng = random.Random(1000003 * (int(seed) + 17))
        self.rng = rng

        # --- stable individual traits ---
        self.mu = _clip(rng.gauss(640.0, 80.0), 470.0, 860.0)        # RT gaussian mean
        self.sigma = _clip(rng.gauss(90.0, 25.0), 40.0, 170.0)       # RT gaussian sd
        self.tau = _clip(rng.gauss(180.0, 60.0), 70.0, 380.0)        # RT exponential tail
        self.base_err = _clip(rng.gauss(0.065, 0.030), 0.015, 0.20)  # baseline error rate
        self.switch_cost = _clip(rng.gauss(170.0, 60.0), 30.0, 340.0)
        self.cue_cost = _clip(rng.gauss(55.0, 25.0), 0.0, 150.0)
        self.switch_err = _clip(rng.gauss(0.040, 0.020), 0.0, 0.12)
        self.conflict_cost = _clip(rng.gauss(35.0, 15.0), 0.0, 90.0)
        self.conflict_err = _clip(rng.gauss(0.030, 0.015), 0.0, 0.09)
        self.lapse_p = _clip(rng.gauss(0.020, 0.015), 0.002, 0.08)
        self.post_err_slow = _clip(rng.gauss(55.0, 30.0), 0.0, 160.0)
        self.practice_gain = _clip(rng.gauss(70.0, 35.0), 0.0, 180.0)  # early-session slowing
        self.fatigue = _clip(rng.gauss(0.12, 0.12), -0.10, 0.50)       # ms per trial drift

        # --- trial-to-trial state ---
        self.mapping = {}       # (task, stimulus feature) -> learned correct key
        self.prev_task = None
        self.prev_cue = None
        self.last_key = None
        self.last_correct = True
        self.n_seen = 0

    # ------------------------------------------------------------------
    def _parse_cue(self, text):
        t = text.lower()
        for cue, task in self._CUES:
            if cue in t:
                return task, cue
        return None, None

    def _parse_number(self, text):
        m = re.search(r"([1-9])\s*\.\s*png", text.lower())
        if not m:
            m = re.search(r"(?<!\d)([1-9])(?!\d)", text)
        if not m:
            return None
        n = int(m.group(1))
        return n if n != 5 else None

    @staticmethod
    def _feature(task, n):
        if task == "parity":
            return "even" if n % 2 == 0 else "odd"
        return "high" if n > 5 else "low"

    # ------------------------------------------------------------------
    def respond(self, ctx):
        rng = self.rng
        ti = self.n_seen
        self.n_seen += 1

        text = ctx.stimulus_text or ""
        task, cue = self._parse_cue(text)
        number = self._parse_number(text)

        rt = self.mu
        err_p = self.base_err

        # --- task/cue change dynamics ---
        if self.prev_task is None:
            rt += 0.6 * self.switch_cost  # first trial of a run: no task set loaded yet
        elif task is None:
            # cue unreadable: apply the expected mixture of change costs
            rt += 0.5 * self.switch_cost + 0.25 * self.cue_cost
            err_p += 0.5 * self.switch_err
        elif task != self.prev_task:
            rt += self.switch_cost
            err_p += self.switch_err
        elif cue is not None and cue != self.prev_cue:
            rt += self.cue_cost
            err_p += 0.25 * self.switch_err

        # --- cross-task response conflict (mapping learned online) ---
        conflict = None
        if task is not None and number is not None and ctx.correct_key is not None:
            other = "magnitude" if task == "parity" else "parity"
            other_key = self.mapping.get((other, self._feature(other, number)))
            if other_key is not None:
                conflict = other_key != ctx.correct_key
            self.mapping[(task, self._feature(task, number))] = ctx.correct_key
        if conflict is True:
            rt += self.conflict_cost
            err_p += self.conflict_err
        elif conflict is False:
            rt -= 0.3 * self.conflict_cost

        # --- post-error slowing ---
        prev_ok = ctx.prev_correct if ctx.prev_correct is not None else self.last_correct
        if prev_ok is False:
            rt += self.post_err_slow
            err_p = max(0.01, err_p - 0.01)

        # --- practice and fatigue drift ---
        rt += self.practice_gain * math.exp(-ti / 20.0)
        rt += self.fatigue * ti

        # --- stochastic RT (gaussian core + exponential tail) ---
        rt += rng.gauss(0.0, self.sigma) + rng.expovariate(1.0 / self.tau)

        # --- attentional lapses ---
        if rng.random() < self.lapse_p:
            rt += rng.uniform(350.0, 950.0)
            err_p = max(err_p, 0.35)

        # --- choose response ---
        key = ctx.correct_key
        if key is None and ctx.available_keys:
            key = rng.choice(list(ctx.available_keys))

        if rng.random() < _clip(err_p, 0.01, 0.50):
            alts = [k for k in ctx.available_keys if k != ctx.correct_key]
            if alts:
                key = rng.choice(alts)
            rt -= rng.uniform(20.0, 120.0)  # errors run slightly fast

        # response-repetition micro-priming
        if key is not None and key == self.last_key:
            rt -= rng.uniform(0.0, 20.0)

        rt = max(rt, rng.uniform(220.0, 300.0))

        # responses that drift past the response window are effectively omissions
        if rt > 1470.0:
            key = None

        # --- commit state ---
        if task is not None:
            self.prev_task = task
        self.prev_cue = cue
        self.last_key = key
        self.last_correct = key is not None and key == ctx.correct_key

        return (key, float(rt))
