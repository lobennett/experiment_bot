import numpy as np


class _FlankerParticipant:
    """Simulated healthy adult performing a letter flanker task.

    Each seed instantiates a distinct participant with their own speed,
    variability, susceptibility to flanker interference, accuracy,
    lapse rate, and trial-to-trial dynamics (practice, fatigue,
    attention drift, post-error slowing, conflict adaptation).
    """

    # task timing: stimulus visible 1000 ms, response window 1500 ms
    DEADLINE_MS = 1500.0
    MIN_RT_MS = 180.0

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
        r = self.rng

        # --- stable individual traits ---
        # ex-Gaussian RT parameters for correct congruent responses
        self.mu = float(np.clip(r.normal(430.0, 45.0), 330.0, 570.0))
        self.sigma = float(np.clip(r.normal(42.0, 12.0), 18.0, 80.0))
        self.tau = float(np.clip(r.normal(85.0, 35.0), 30.0, 200.0))

        # interference cost on incongruent trials (ms)
        self.flanker_cost = float(np.clip(r.normal(58.0, 18.0), 15.0, 110.0))
        # conflict adaptation: interference shrinks after an incongruent trial
        self.gratton_scale = float(r.uniform(0.45, 0.85))

        # error rates
        self.err_congruent = float(np.clip(r.normal(0.020, 0.012), 0.003, 0.07))
        self.err_incongruent = self.err_congruent + float(
            np.clip(r.normal(0.055, 0.030), 0.01, 0.16)
        )
        # how much faster errors are than correct responses (fast guesses)
        self.error_speedup = float(np.clip(r.normal(90.0, 30.0), 30.0, 160.0))

        # attentional lapses -> omission or very slow response
        self.lapse_rate = float(np.clip(r.normal(0.018, 0.014), 0.0, 0.06))
        # rare anticipatory keypresses
        self.anticipation_rate = float(np.clip(r.normal(0.004, 0.003), 0.0, 0.015))

        # post-error slowing (ms) and post-error accuracy boost
        self.pes = float(np.clip(r.normal(55.0, 25.0), 0.0, 130.0))
        self.pe_acc_gain = float(r.uniform(0.3, 0.7))  # multiplies error prob

        # practice: early speedup that decays out over ~30 trials
        self.practice_amp = float(np.clip(r.normal(45.0, 20.0), 0.0, 110.0))
        self.practice_decay = float(r.uniform(12.0, 35.0))

        # fatigue: slow linear drift late in the session
        self.fatigue_per_trial = float(np.clip(r.normal(0.15, 0.12), 0.0, 0.5))
        self.fatigue_onset = int(r.integers(50, 100))

        # slow AR(1) attention/arousal drift shared across trials
        self.attn = 0.0
        self.attn_rho = float(r.uniform(0.88, 0.97))
        self.attn_sd = float(r.uniform(4.0, 16.0))

    # ------------------------------------------------------------------
    def _wrong_key(self, ctx):
        others = [k for k in ctx.available_keys if k != ctx.correct_key]
        if others:
            return others[int(self.rng.integers(len(others)))]
        return ctx.correct_key  # no known alternative; cannot commit an error

    def _sample_rt(self, mu):
        rt = self.rng.normal(mu, self.sigma) + self.rng.exponential(self.tau)
        return float(max(self.MIN_RT_MS, rt))

    # ------------------------------------------------------------------
    def respond(self, ctx):
        r = self.rng

        # evolve slow attention state
        self.attn = self.attn_rho * self.attn + r.normal(0.0, self.attn_sd)

        incongruent = ctx.condition == "incongruent"
        after_incongruent = ctx.prev_condition == "incongruent"
        after_error = ctx.prev_correct is False

        # --- occasional anticipatory response: fast, ~chance accuracy ---
        if r.random() < self.anticipation_rate and ctx.correct_key is not None:
            rt = float(r.uniform(150.0, 270.0))
            key = ctx.correct_key if r.random() < 0.55 else self._wrong_key(ctx)
            return (key, rt)

        # --- attentional lapse: omission or a very late response ---
        if r.random() < self.lapse_rate:
            if r.random() < 0.6:
                return (None, self.DEADLINE_MS - 1.0)  # missed the window
            rt = float(r.uniform(950.0, self.DEADLINE_MS - 20.0))
            key = ctx.correct_key if r.random() < 0.85 else self._wrong_key(ctx)
            return (key, rt)

        # --- mean RT for this trial ---
        mu = self.mu + self.attn

        if incongruent:
            cost = self.flanker_cost
            if after_incongruent:
                cost *= self.gratton_scale  # conflict adaptation
            mu += cost

        if after_error:
            mu += self.pes  # post-error slowing

        # practice speedup early on, mild fatigue late
        t = ctx.trial_index
        mu += self.practice_amp * np.exp(-t / self.practice_decay)
        if t > self.fatigue_onset:
            mu += self.fatigue_per_trial * (t - self.fatigue_onset)

        # --- accuracy for this trial ---
        p_err = self.err_incongruent if incongruent else self.err_congruent
        if incongruent and after_incongruent:
            p_err *= 0.8  # conflict adaptation also helps accuracy
        if after_error:
            p_err *= self.pe_acc_gain  # more careful after an error
        p_err = float(np.clip(p_err, 0.0, 0.5))

        is_error = r.random() < p_err

        if is_error:
            # errors (esp. flanker-driven on incongruent) tend to be fast
            speedup = self.error_speedup if incongruent else self.error_speedup * 0.5
            rt = self._sample_rt(mu - speedup)
            key = self._wrong_key(ctx)
        else:
            rt = self._sample_rt(mu)
            key = ctx.correct_key

        # responses after the trial deadline are never recorded
        if rt >= self.DEADLINE_MS:
            return (None, self.DEADLINE_MS - 1.0)

        return (key, float(round(rt, 1)))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _FlankerParticipant(seed)
