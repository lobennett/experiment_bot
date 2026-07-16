"""
Computational model of a healthy adult performing a cued task-switching
experiment (parity / magnitude judgments on digits, cued each trial).

Behavioral model (all decided here, per participant):
- Ex-Gaussian RT with per-participant parameters, slow AR(1) drift,
  early-session practice speed-up and mild late fatigue.
- Task-switch and cue-switch RT costs and error-rate increases, inferred
  trial-by-trial from the visible cue words in the stimulus text.
- Response-congruency effect, learned online from observed correct keys
  (a digit whose answer agrees under both tasks is faster / more accurate).
- Post-error slowing, occasional fast guesses, occasional lapses
  (no response), and a hard response deadline (slow responses are missed).
Each seed is a distinct participant: all parameters are drawn from
population distributions using the seed.
"""

import math
import random


def make_participant(seed):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)


class _Participant:
    def __init__(self, seed):
        rng = random.Random(seed)
        self._rng = rng

        def clip(x, lo, hi):
            return max(lo, min(hi, x))

        # --- RT distribution (ex-Gaussian) ---
        self.mu = clip(rng.gauss(620.0, 90.0), 440.0, 880.0)
        self.sigma = clip(rng.gauss(65.0, 18.0), 28.0, 120.0)
        self.tau = clip(rng.gauss(190.0, 65.0), 70.0, 380.0)

        # --- condition effects ---
        self.task_switch_cost = clip(rng.gauss(150.0, 60.0), 30.0, 330.0)
        self.cue_switch_cost = clip(rng.gauss(45.0, 25.0), 0.0, 130.0)
        self.incong_cost = clip(rng.gauss(45.0, 25.0), 0.0, 120.0)
        self.cong_benefit = clip(rng.gauss(20.0, 12.0), 0.0, 60.0)

        # --- accuracy ---
        self.base_err = rng.uniform(0.02, 0.11)
        self.switch_err_add = rng.uniform(0.02, 0.10)
        self.cue_err_add = rng.uniform(0.0, 0.03)
        self.incong_err_add = rng.uniform(0.01, 0.08)

        # --- misc dynamics ---
        self.post_error_slow = clip(rng.gauss(75.0, 35.0), 0.0, 200.0)
        self.lapse_p = rng.uniform(0.004, 0.035)
        self.guess_p = rng.uniform(0.002, 0.015)
        self.practice_gain = rng.uniform(30.0, 130.0)   # ms saved as task is learned
        self.fatigue_slope = rng.uniform(0.0, 0.35)     # ms per trial, late slowing
        self.err_speedup = rng.uniform(0.82, 0.96)      # errors are a bit faster
        self.deadline_ms = 1500.0

        # --- state ---
        self._n = 0                  # trials seen
        self._drift = 0.0            # slow AR(1) RT drift
        self._prev_task = None
        self._prev_cue = None
        self._keymap = {}            # (task, category) -> observed correct key

    # ------------------------------------------------------------------
    def _parse_cue(self, text):
        """Return (task, cue_token) inferred from visible trial text."""
        if not text:
            return None, None
        low = str(text).lower()
        for token, task in (("odd-even", "parity"), ("parity", "parity"),
                            ("high-low", "magnitude"), ("magnitude", "magnitude")):
            if token in low:
                return task, token
        return None, None

    def _parse_digit(self, text):
        if not text:
            return None
        for ch in str(text):
            if ch in "12346789":
                return int(ch)
        return None

    def _sample_rt(self):
        rng = self._rng
        return rng.gauss(self.mu, self.sigma) + rng.expovariate(1.0 / self.tau)

    def _wrong_key(self, ctx, correct):
        keys = [k for k in (getattr(ctx, "available_keys", ()) or ()) if k != correct]
        if keys:
            return self._rng.choice(keys)
        return correct  # nothing else pressable; error dissolves

    # ------------------------------------------------------------------
    def respond(self, ctx):
        rng = self._rng
        self._n += 1

        correct = getattr(ctx, "correct_key", None)
        text = getattr(ctx, "stimulus_text", None)
        task, cue = self._parse_cue(text)
        digit = self._parse_digit(text)

        # ---- switch structure from the visible cue ----
        task_switch = (task is not None and self._prev_task is not None
                       and task != self._prev_task)
        cue_switch = (not task_switch and cue is not None
                      and self._prev_cue is not None and cue != self._prev_cue)

        # ---- congruency, learned from experienced correct keys ----
        congruent = None
        if task in ("parity", "magnitude") and digit is not None and correct is not None:
            par_cat = "even" if digit % 2 == 0 else "odd"
            mag_cat = "high" if digit > 5 else "low"
            my_cat = par_cat if task == "parity" else mag_cat
            other_task = "magnitude" if task == "parity" else "parity"
            other_cat = mag_cat if task == "parity" else par_cat
            known = self._keymap.get((other_task, other_cat))
            if known is not None:
                congruent = (known == correct)
            self._keymap[(task, my_cat)] = correct

        # ---- assemble RT ----
        rt = self._sample_rt()
        if task_switch:
            rt += self.task_switch_cost * rng.uniform(0.6, 1.4)
        elif cue_switch:
            rt += self.cue_switch_cost * rng.uniform(0.5, 1.5)
        if congruent is False:
            rt += self.incong_cost * rng.uniform(0.5, 1.5)
        elif congruent is True:
            rt -= self.cong_benefit * rng.uniform(0.5, 1.5)
        if getattr(ctx, "prev_correct", None) is False:
            rt += self.post_error_slow * rng.uniform(0.5, 1.5)

        # practice / fatigue / slow drift
        rt -= self.practice_gain * math.exp(-self._n / 40.0)
        rt += self.fatigue_slope * self._n
        self._drift = 0.9 * self._drift + rng.gauss(0.0, 15.0)
        rt += self._drift

        # ---- error probability ----
        p_err = self.base_err
        if task_switch:
            p_err += self.switch_err_add
        elif cue_switch:
            p_err += self.cue_err_add
        if congruent is False:
            p_err += self.incong_err_add
        elif congruent is True:
            p_err -= 0.01
        p_err = max(0.005, min(0.45, p_err))

        self._prev_task = task if task is not None else self._prev_task
        self._prev_cue = cue if cue is not None else self._prev_cue

        # ---- trials with no required response: mostly withhold ----
        if correct is None:
            if rng.random() < 0.02:
                keys = list(getattr(ctx, "available_keys", ()) or ())
                if keys:
                    return (rng.choice(keys), max(250.0, min(rt, 1400.0)))
            return (None, max(200.0, min(rt, 1400.0)))

        # ---- lapses: attention drifted, no response this trial ----
        if rng.random() < self.lapse_p:
            return (None, max(200.0, min(rt, self.deadline_ms - 1.0)))

        # ---- fast anticipatory guesses ----
        if rng.random() < self.guess_p:
            guess_rt = rng.uniform(160.0, 320.0)
            if rng.random() < 0.5:
                return (correct, guess_rt)
            return (self._wrong_key(ctx, correct), guess_rt)

        # ---- normal decision ----
        make_error = rng.random() < p_err
        if make_error:
            rt *= self.err_speedup
        rt = max(220.0, rt)

        # too slow for the response window -> recorded as a miss
        if rt >= self.deadline_ms - 20.0:
            return (None, self.deadline_ms - 1.0)

        if make_error:
            return (self._wrong_key(ctx, correct), rt)
        return (correct, rt)
