"""Generative participant model for the n-back (letter, delay 1/2) task.

The participant judges, on each trial, whether the current letter matches the
letter shown some number of trials ago (case-insensitive), pressing one of two
keys (comma / period). Which physical key means "match" vs "mismatch" is
resolved per trial by the harness, so this model always works from
ctx.correct_key / ctx.available_keys and the ctx.condition label rather than
any hardcoded key map.

Task timing read from the source: the stimulus is shown 1000 ms and the trial /
response window lasts 1500 ms (response_ends_trial = false), so any decision
slower than ~1500 ms from onset is recorded as a miss.

Each seed is a different person: working-memory ability, response bias
(liberal/conservative), speed, RT spread, lapse rate, and within-session
fatigue are all drawn once per participant.
"""

import math
import numpy as np


def _logit(p):
    return math.log(p / (1.0 - p))


def _logistic(x):
    return 1.0 / (1.0 + math.exp(-x))


# Response window (ms). Trial duration in the task source.
_DEADLINE_MS = 1500.0
# Fastest plausible deliberate keypress.
_MIN_RT_MS = 180.0
# Session length used to scale the fatigue drift (test phase ~120 trials plus
# practice); saturates so longer runs don't blow up.
_FATIGUE_SCALE = 300.0


class NBackParticipant:
    def __init__(self, seed):
        rng = np.random.default_rng(int(seed))
        self.rng = rng
        self.trial_count = 0

        # Latent working-memory ability: drives both accuracy and speed so that
        # sharper participants are both more accurate and a bit faster.
        ability = rng.normal()

        # Response criterion. Positive => liberal (tends to call "match"),
        # which raises hits but costs correct rejections, and vice versa. This
        # produces the realistic negative coupling between the two accuracies.
        bias = rng.normal(0.0, 0.35)

        # Detecting a target (match) is harder than rejecting a non-target.
        hit_logit = _logit(0.86) + 1.0 * ability + rng.normal(0.0, 0.30) + bias
        cr_logit = _logit(0.95) + 0.9 * ability + rng.normal(0.0, 0.30) - bias
        self.hit_rate = float(np.clip(_logistic(hit_logit), 0.50, 0.99))
        self.cr_rate = float(np.clip(_logistic(cr_logit), 0.60, 0.998))

        # Omission (no-response) tendency and how much it grows with fatigue.
        self.lapse = float(np.clip(rng.normal(0.025, 0.020), 0.002, 0.12))
        self.fatigue_lapse = float(rng.uniform(0.0, 0.03))
        # Accuracy erosion by the end of the session.
        self.fatigue_acc = float(rng.uniform(0.0, 0.06))

        # RT model: ex-Gaussian (normal mu/sigma + exponential tail tau).
        self.mu = float(max(470.0 + rng.normal(0.0, 60.0) - 35.0 * ability, 320.0))
        self.sigma = float(max(55.0 + rng.normal(0.0, 15.0), 25.0))
        self.tau = float(max(110.0 + rng.normal(0.0, 40.0), 40.0))

        # Targets (matches) tend to be responded to a little more slowly.
        self.match_slow = float(rng.normal(45.0, 20.0))
        # Post-error slowing after an incorrect previous trial.
        self.pes = float(max(rng.normal(40.0, 25.0), 0.0))
        # Errors are usually a touch faster (more impulsive) than correct ones.
        self.error_speedup = float(max(rng.normal(30.0, 20.0), 0.0))
        # RT lengthening accumulated across the session.
        self.fatigue_rt = float(rng.normal(60.0, 40.0))

    def _sample_rt(self, mu):
        return self.rng.normal(mu, self.sigma) + self.rng.exponential(self.tau)

    def respond(self, ctx):
        rng = self.rng
        self.trial_count += 1
        frac = min(self.trial_count / _FATIGUE_SCALE, 1.0)

        correct_key = ctx.correct_key
        keys = tuple(ctx.available_keys) if ctx.available_keys else ()

        # Trials without a well-defined correct key (rare / non-scored): press a
        # key at a typical latency, or occasionally withhold, without any
        # accuracy notion.
        if correct_key is None:
            if not keys:
                return (None, _DEADLINE_MS)
            if rng.random() < (self.lapse + self.fatigue_lapse * frac):
                return (None, _DEADLINE_MS)
            rt = max(self._sample_rt(self.mu + self.fatigue_rt * frac), _MIN_RT_MS)
            if rt >= _DEADLINE_MS:
                return (None, _DEADLINE_MS)
            return (keys[int(rng.integers(len(keys)))], float(rt))

        cond = (ctx.condition or "").lower()
        is_match = cond == "match"

        # Omission: sometimes no response is made at all.
        lapse = self.lapse + self.fatigue_lapse * frac
        if rng.random() < lapse:
            return (None, _DEADLINE_MS)

        # Probability the response is correct for this condition.
        p_correct = self.hit_rate if is_match else self.cr_rate
        p_correct -= self.fatigue_acc * frac
        p_correct = float(np.clip(p_correct, 0.40, 0.999))
        correct = rng.random() < p_correct

        # Choose the key.
        if correct:
            key = correct_key
        else:
            others = [k for k in keys if k != correct_key]
            key = others[0] if others else correct_key

        # Build the RT mean from the additive effects.
        mu = self.mu + self.fatigue_rt * frac
        if is_match:
            mu += self.match_slow
        if ctx.prev_correct is not None and not ctx.prev_correct:
            mu += self.pes
        if not correct:
            mu -= self.error_speedup
        mu = max(mu, _MIN_RT_MS + 40.0)

        rt = max(self._sample_rt(mu), _MIN_RT_MS)

        # Too slow to register within the response window => recorded as a miss.
        if rt >= _DEADLINE_MS:
            return (None, _DEADLINE_MS)

        return (key, float(rt))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return NBackParticipant(seed)
