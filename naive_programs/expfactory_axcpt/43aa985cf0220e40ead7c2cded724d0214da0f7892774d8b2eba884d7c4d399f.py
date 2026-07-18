"""Generative participant model for the AX-CPT (RDoC) task.

The task presents a cue letter (A or other) then a probe letter (X or other).
Condition labels are AX / BX / AY / BY.  The rule: press the "target" key only
when an A cue is followed by an X probe (the AX condition); otherwise press the
"non-target" key.  ctx.correct_key already encodes the runtime key mapping, so
this model never hardcodes which physical key means what.

Behavioral structure captured:
  * AX (target, frequent) is fast and highly accurate -- it is the practiced,
    expected response.
  * AY is the proactive-interference cell: the A cue primes the target response,
    so a Y probe is slow and error-prone, and those errors are fast (prepotent).
  * BX is the reactive-interference cell: the X probe pulls toward the target
    response despite the B cue -> elevated RT and errors.
  * BY is a low-conflict control: fast and accurate.
  * A latent "proactive tendency" trades AY cost against BX cost across
    participants (some rely more on the cue, some more on the probe).
  * Individual differences in overall speed, overall accuracy, RT variability,
    post-error slowing, and lapse rate make each seed a distinct person.

Only the probe trial carries a correct_key; cue / fixation / other events have
none and receive no key press, the way a real participant leaves the cue alone.
"""

import numpy as np

_TASK_CONDS = ("AX", "BX", "AY", "BY")


class _Participant:
    def __init__(self, seed):
        rng = np.random.RandomState(int(seed) & 0x7FFFFFFF)
        self.rng = rng

        # ---- person-level latent traits -------------------------------------
        overall_speed = rng.normal(0.0, 45.0)      # ms shift, + = slower person
        ability = rng.normal(0.0, 0.025)           # global accuracy offset
        pindex = rng.normal(0.0, 1.0)              # proactive(+) vs reactive(-)

        self.sigma = float(max(28.0, rng.normal(55.0, 12.0)))   # gaussian RT width
        self.tau = float(max(45.0, rng.normal(95.0, 25.0)))     # ex-gaussian tail
        self.post_error_slow = float(max(0.0, rng.normal(32.0, 12.0)))
        self.lapse = float(rng.uniform(0.004, 0.020))           # baseline omissions

        # ---- per-condition correct-response RT (ms) -------------------------
        self.rt = {
            "AX": 440.0 + overall_speed,
            "BY": 475.0 + overall_speed,
            "BX": 545.0 + overall_speed - 20.0 * pindex,
            "AY": 585.0 + overall_speed + 25.0 * pindex,
        }

        # ---- per-condition accuracy -----------------------------------------
        acc = {
            "AX": 0.975 + ability,
            "BY": 0.960 + ability,
            "BX": 0.900 + ability + 0.035 * pindex,   # proactive -> better BX
            "AY": 0.850 + ability - 0.050 * pindex,   # proactive -> worse  AY
        }
        self.acc = {c: float(min(0.995, max(0.55, a))) for c, a in acc.items()}

        # error RTs relative to that cell's correct base (errors are quicker,
        # driven by the prepotent/impulsive response -- strongest for AY).
        self.err_scale = {"AX": 0.95, "BY": 0.90, "BX": 0.85, "AY": 0.80}

        # probe response window from the task source (probe trial_duration).
        self.deadline = 1500.0

    # -------------------------------------------------------------------------
    def _exg(self, mu, sigma, tau):
        return float(self.rng.normal(mu, sigma) + self.rng.exponential(tau))

    @staticmethod
    def _clip(x, lo, hi):
        return float(max(lo, min(hi, x)))

    @staticmethod
    def _other_key(keys, ck):
        for k in keys:
            if k != ck:
                return k
        return None

    # -------------------------------------------------------------------------
    def respond(self, ctx):
        ck = ctx.correct_key
        cond = ctx.condition
        keys = ctx.available_keys or ()

        # --- events that are not the scored AX-CPT probe ---------------------
        if cond not in _TASK_CONDS:
            # e.g. attention-check prompts: comply nearly always, unhurried.
            if ck is not None:
                if self.rng.random() < 0.95:
                    return (ck, self._clip(self._exg(1100.0, 200.0, 350.0),
                                           400.0, 14000.0))
                alt = self._other_key(keys, ck)
                return (alt if alt is not None else ck, 1300.0)
            return (None, 400.0)

        if ck is None:
            # the cue (and any other non-response task frame): withhold response.
            return (None, 400.0)

        # --- probe: the AX-CPT decision --------------------------------------
        base_rt = self.rt[cond]
        acc = self.acc[cond]

        slow = 0.0
        if ctx.prev_correct == 0 and ctx.prev_rt_ms is not None:
            slow += self.post_error_slow      # post-error slowing
            acc = min(0.995, acc + 0.03)      # ...and a touch more caution

        # gentle warm-up: first handful of trials are slower
        if ctx.trial_index is not None and ctx.trial_index < 15:
            slow += (15 - ctx.trial_index) * 1.5

        correct = self.rng.random() < acc
        if correct:
            rt = self._exg(base_rt + slow, self.sigma, self.tau)
            key = ck
        else:
            err_mu = base_rt * self.err_scale[cond] + 0.5 * slow
            rt = self._exg(err_mu, self.sigma, self.tau * 0.8)
            key = self._other_key(keys, ck)
            if key is None:
                key = ck

        rt = self._clip(rt, 220.0, 5000.0)

        # omission: response fell outside the window, or an attentional lapse.
        if rt > self.deadline or self.rng.random() < self.lapse:
            return (None, min(rt, self.deadline))

        return (key, rt)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
