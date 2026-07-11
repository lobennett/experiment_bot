"""
Generative participant model for a cued task-switching experiment.

Each seed instantiates a distinct simulated adult participant. The model
maintains internal state across trials (previous task/cue inferred from
the visible cue text, its own recent accuracy, slow drifts in alertness)
and produces per-trial (key, rt_ms) decisions with realistic structure:
right-skewed RT distributions, costs for switching task or cue,
congruency interference once the two task rules have been learned,
post-error slowing, occasional lapses and omissions, practice speedup,
and slow trial-to-trial fluctuation.

Imports: stdlib only (math, random). Deterministic per seed.
"""

import math
import random


# Cue vocabulary for the two tasks (as shown on screen above the digit).
_CUE_TO_TASK = {
    "odd-even": "parity",
    "parity": "parity",
    "high-low": "magnitude",
    "magnitude": "magnitude",
}


def _parse_cue(text):
    """Return (task, cue_token) inferred from the trial's visible text."""
    if not text:
        return None, None
    low = text.lower()
    # Check hyphenated cue names first so "odd-even" is not shadowed.
    for token in ("odd-even", "high-low", "parity", "magnitude"):
        if token in low:
            return _CUE_TO_TASK[token], token
    return None, None


def _parse_digit(text):
    """Return the first digit visible in the trial text, if any."""
    if not text:
        return None
    for ch in text:
        if ch.isdigit():
            d = int(ch)
            if d != 0 and d != 5:
                return d
    return None


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class Participant:
    # Response window facts implied by the task code: the stimulus stays
    # up 1000 ms and the trial accepts responses for 1500 ms.
    RESPONSE_DEADLINE = 1500.0

    def __init__(self, seed):
        rng = random.Random(("cued_ts_participant", int(seed)))
        self.rng = rng

        # --- stable individual differences ---------------------------------
        # Ex-Gaussian RT core (correct, task-repeat trials).
        self.mu = _clip(rng.gauss(640.0, 85.0), 470.0, 900.0)
        self.sigma = _clip(rng.gauss(65.0, 18.0), 30.0, 130.0)
        self.tau = _clip(rng.gauss(130.0, 45.0), 50.0, 320.0)

        # Reconfiguration costs.
        self.task_switch_cost = _clip(rng.gauss(130.0, 55.0), 15.0, 320.0)
        self.cue_switch_cost = _clip(rng.gauss(40.0, 22.0), 0.0, 120.0)
        self.incongruency_cost = _clip(rng.gauss(45.0, 25.0), 0.0, 130.0)

        # Error model.
        self.base_err = _clip(rng.gauss(0.05, 0.025), 0.008, 0.18)
        self.switch_err_boost = _clip(rng.gauss(0.045, 0.03), 0.0, 0.15)
        self.incong_err_boost = _clip(rng.gauss(0.04, 0.025), 0.0, 0.12)
        self.lapse_rate = _clip(rng.gauss(0.015, 0.01), 0.0, 0.05)

        # Omissions (too slow / attention gap).
        self.miss_rate = _clip(rng.gauss(0.02, 0.015), 0.0, 0.08)

        # Sequential effects.
        self.post_error_slow = _clip(rng.gauss(70.0, 35.0), 0.0, 220.0)
        self.post_error_care = _clip(rng.gauss(0.35, 0.15), 0.0, 0.7)

        # Practice / fatigue over the session.
        self.practice_gain = _clip(rng.gauss(55.0, 30.0), 0.0, 140.0)
        self.fatigue_per_100 = _clip(rng.gauss(8.0, 8.0), -8.0, 30.0)

        # Slow AR(1) drift in readiness (shared variance across nearby trials).
        self.drift = 0.0
        self.drift_rho = 0.985
        self.drift_sd = _clip(rng.gauss(18.0, 6.0), 6.0, 40.0)

        # --- episodic state --------------------------------------------------
        self.prev_task = None
        self.prev_cue = None
        self.last_was_error = False
        self.trials_seen = 0
        # Learned S-R rules, filled in from observed correct keys:
        # rules["parity"][digit % 2] -> key ; rules["magnitude"][digit > 5] -> key
        self.rules = {"parity": {}, "magnitude": {}}

    # ------------------------------------------------------------------ RTs
    def _sample_rt(self, mean_shift, careful):
        mu = self.mu + mean_shift + self.drift
        rt = self.rng.gauss(mu, self.sigma) + self.rng.expovariate(1.0 / self.tau)
        if careful:
            rt += self.rng.gauss(30.0, 15.0)
        return _clip(rt, 220.0, self.RESPONSE_DEADLINE - 20.0)

    def _session_shift(self, trial_index):
        t = max(0, int(trial_index)) if isinstance(trial_index, int) else 0
        practice = -self.practice_gain * (1.0 - math.exp(-t / 40.0))
        fatigue = self.fatigue_per_100 * (t / 100.0)
        return practice + fatigue

    # ------------------------------------------------------------ congruency
    def _congruency(self, task, digit):
        """Return 'cong', 'incong', or None if it cannot be evaluated yet."""
        if task is None or digit is None:
            return None
        other = "magnitude" if task == "parity" else "parity"
        own_feat = (digit % 2) if task == "parity" else (digit > 5)
        oth_feat = (digit % 2) if other == "parity" else (digit > 5)
        own_key = self.rules[task].get(own_feat)
        oth_key = self.rules[other].get(oth_feat)
        if own_key is None or oth_key is None:
            return None
        return "cong" if own_key == oth_key else "incong"

    def _learn(self, task, digit, correct_key):
        if task is None or digit is None or correct_key is None:
            return
        feat = (digit % 2) if task == "parity" else (digit > 5)
        self.rules[task][feat] = correct_key

    # --------------------------------------------------------------- respond
    def respond(self, ctx):
        rng = self.rng
        self.trials_seen += 1

        # Advance the slow readiness drift once per trial.
        self.drift = self.drift_rho * self.drift + rng.gauss(0.0, self.drift_sd)

        correct = getattr(ctx, "correct_key", None)
        available = tuple(getattr(ctx, "available_keys", ()) or ())
        text = getattr(ctx, "stimulus_text", None)
        trial_index = getattr(ctx, "trial_index", 0) or 0
        prev_correct = getattr(ctx, "prev_correct", None)

        # Clickable-option trials: pick the first option after a reading pause.
        elements = tuple(getattr(ctx, "response_elements", ()) or ())
        if elements and correct is None:
            rt = _clip(rng.gauss(1600.0, 500.0), 400.0, 6000.0)
            return ("click", 0, float(rt))

        # Trials with no scorable response (nothing to press): stay quiet.
        if correct is None and not available:
            return (None, float(_clip(rng.gauss(800.0, 200.0), 100.0, 4000.0)))

        # ---- read the cue, classify the transition -------------------------
        task, cue = _parse_cue(text)
        digit = _parse_digit(text)

        if task is not None and self.prev_task is not None:
            if task != self.prev_task:
                transition = "task_switch"
            elif cue is not None and self.prev_cue is not None and cue != self.prev_cue:
                transition = "cue_switch"
            else:
                transition = "repeat"
        elif task is None and self.prev_task is None and self.trials_seen > 1:
            # Cue not visible to the model: assume the empirical switch mix.
            transition = "task_switch" if rng.random() < 0.5 else "repeat"
        else:
            transition = "first"

        congr = self._congruency(task, digit)

        # ---- assemble RT shift and error probability ------------------------
        shift = self._session_shift(trial_index)
        err_p = self.base_err
        if transition == "task_switch":
            shift += self.task_switch_cost
            err_p += self.switch_err_boost
        elif transition == "cue_switch":
            shift += self.cue_switch_cost
            err_p += 0.3 * self.switch_err_boost
        elif transition == "first":
            shift += 120.0 + rng.gauss(0.0, 40.0)
        if congr == "incong":
            shift += self.incongruency_cost
            err_p += self.incong_err_boost

        careful = False
        made_error_last = self.last_was_error or (prev_correct is False)
        if made_error_last:
            shift += self.post_error_slow
            err_p *= (1.0 - self.post_error_care)
            careful = True

        err_p = _clip(err_p, 0.003, 0.45)

        # ---- update memory before returning ---------------------------------
        self._learn(task, digit, correct)
        if task is not None:
            self.prev_task = task
            self.prev_cue = cue

        # ---- omission --------------------------------------------------------
        if rng.random() < self.miss_rate:
            self.last_was_error = True
            return (None, float(self.RESPONSE_DEADLINE - 1.0))

        # ---- lapse: fast guess unrelated to the rule -------------------------
        if rng.random() < self.lapse_rate:
            pool = list(available) if available else ([correct] if correct else [])
            if correct and correct not in pool:
                pool.append(correct)
            key = rng.choice(pool) if pool else correct
            rt = _clip(rng.gauss(self.mu - 150.0 + self.drift, self.sigma),
                       220.0, self.RESPONSE_DEADLINE - 20.0)
            self.last_was_error = (key != correct)
            return (key, float(rt))

        # ---- rule-based decision --------------------------------------------
        if rng.random() < err_p:
            wrong = [k for k in available if k != correct]
            if not wrong and correct in (",", "."):
                wrong = ["." if correct == "," else ","]
            if wrong:
                key = rng.choice(wrong)
                # Errors tend to be a bit faster than corrects (premature).
                rt = self._sample_rt(shift - 60.0, careful=False)
                self.last_was_error = True
                return (key, float(rt))

        rt = self._sample_rt(shift, careful)
        self.last_was_error = False
        return (correct, float(rt))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)
