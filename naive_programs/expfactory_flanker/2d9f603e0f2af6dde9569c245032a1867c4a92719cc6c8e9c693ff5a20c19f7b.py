import numpy as np


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _FlankerParticipant(int(seed))


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class _FlankerParticipant:
    """A generative model of one healthy adult doing an F/H letter-flanker task.

    The task shows a five-letter string and the participant reports the middle
    letter with one of two keys. Two conditions occur: 'congruent' (flankers
    match the target, e.g. FFFFF/HHHHH) and 'incongruent' (flankers mismatch,
    e.g. HHFHH/FFHFF). Each trial runs on a fixed 1500 ms response window with
    the stimulus visible for the first 1000 ms; the participant almost always
    answers well within that window.

    Behaviour that varies across individuals (each seed is a new person):
      - overall speed (ex-Gaussian mu/sigma/tau of the correct-response RT)
      - the size of the congruency cost (incongruent slower + more errors)
      - baseline error rate and how much errors inflate under incongruence
      - attentional lapse (omission) rate
      - post-error slowing
      - the congruency-sequence effect (flanker cost shrinks after an
        incongruent trial)
      - a warm-up period at the very start of the task
    """

    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        r = self.rng

        # Ex-Gaussian components of the correct-response RT (milliseconds).
        # mean correct RT ~= mu + tau, so a congruent trial lands ~500-560 ms.
        self.mu = _clamp(r.normal(425, 45), 350, 540)
        self.sigma = _clamp(r.normal(45, 10), 22, 80)
        self.tau = _clamp(r.normal(100, 28), 50, 190)

        # Extra time it costs when the flankers conflict with the target.
        self.flanker_rt = _clamp(r.normal(60, 22), 18, 120)

        # Error rates. Incongruent trials are always at least as error-prone.
        self.err_cong = _clamp(r.normal(0.03, 0.015), 0.004, 0.09)
        self.err_incong = _clamp(
            self.err_cong + abs(r.normal(0.06, 0.03)), self.err_cong, 0.22
        )

        # Occasional complete omission (missed the trial entirely).
        self.miss_rate = _clamp(r.normal(0.010, 0.008), 0.0, 0.045)

        # Multiplier applied to RT on the trial after an error.
        self.pes = _clamp(r.normal(1.07, 0.035), 1.0, 1.18)

        # Congruency-sequence effect: fraction of the flanker cost that
        # disappears when the previous trial was already incongruent.
        self.cse = _clamp(r.normal(0.35, 0.20), 0.0, 0.75)

        # Warm-up: everybody starts a little slow, fading over the first trials.
        self.warmup = _clamp(r.normal(0.07, 0.03), 0.0, 0.16)
        self.warmup_scale = float(r.uniform(12, 30))

    def _exgauss(self, mu, sigma, tau):
        return float(self.rng.normal(mu, sigma) + self.rng.exponential(tau))

    def _pick_wrong_key(self, ctx):
        others = [k for k in ctx.available_keys if k != ctx.correct_key]
        if not others:
            return ctx.correct_key
        return str(others[int(self.rng.integers(len(others)))])

    def respond(self, ctx):
        r = self.rng
        incong = ctx.condition == "incongruent"
        prev_err = ctx.prev_correct is not None and not ctx.prev_correct

        # --- attentional lapse: no response at all ---
        if r.random() < self.miss_rate:
            return (None, float(r.uniform(1500, 1800)))

        # --- flanker cost, modulated by the previous trial's congruency ---
        cost = self.flanker_rt if incong else 0.0
        if incong and ctx.prev_condition == "incongruent":
            cost *= (1.0 - self.cse)

        # --- decide correct vs. error ---
        p_err = self.err_incong if incong else self.err_cong
        if prev_err:
            p_err *= 0.6  # more cautious right after a mistake
        correct = r.random() >= p_err

        # --- warm-up and post-error slowing multipliers ---
        warm = 1.0 + self.warmup * float(np.exp(-ctx.trial_index / self.warmup_scale))
        pes = self.pes if prev_err else 1.0

        # --- generate the response time ---
        if correct:
            rt = self._exgauss(self.mu + cost, self.sigma, self.tau)
        elif incong:
            # incongruent errors are mostly fast, impulsive captures by the
            # flanking letters: quicker and less variable than correct RTs.
            rt = self._exgauss(self.mu + 0.35 * cost, self.sigma * 0.9, self.tau * 0.6)
        else:
            # rare congruent errors are quick slips / guesses.
            rt = self._exgauss(self.mu * 0.9, self.sigma, self.tau * 0.7)

        rt = _clamp(rt * warm * pes, 200.0, 2200.0)

        # samples in the slow tail fall past the 1500 ms window -> omission.
        if rt > 1500.0:
            return (None, float(r.uniform(1500, 1800)))

        if correct:
            if ctx.correct_key is not None:
                key = ctx.correct_key
            elif ctx.available_keys:
                key = str(ctx.available_keys[int(r.integers(len(ctx.available_keys)))])
            else:
                return (None, float(r.uniform(1500, 1800)))
        else:
            key = self._pick_wrong_key(ctx)

        return (key, float(rt))
