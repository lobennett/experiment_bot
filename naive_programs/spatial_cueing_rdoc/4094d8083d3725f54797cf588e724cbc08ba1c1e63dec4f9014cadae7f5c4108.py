import numpy as np


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)


class Participant:
    """A typical healthy adult performing a Posner-style spatial cueing task.

    The task is a trivial left/right spatial discrimination (star in left box
    -> comma; star in right box -> period), so accuracy sits near ceiling and
    the behaviour of interest lives in the response times. A brief peripheral
    cue precedes each target after a short cue-target interval:

      - valid      : the box where the star will appear is highlighted
                     -> attention is already there, fastest responses
      - doublecue  : both boxes highlighted -> a temporal (alerting) warning
                     with no spatial information, modest speed-up
      - nocue      : no highlight -> baseline
      - invalid    : the opposite box highlighted -> attention must reorient,
                     slowest responses

    Timing constraints read from the task source: the target trial lasts
    1500 ms and does not end on response, the star is visible for 1000 ms, so
    the usable response window is ~1500 ms.
    """

    RESPONSE_WINDOW_MS = 1500.0

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(int(seed))
        r = self.rng

        # --- individual overall speed (ex-Gaussian for the RT shape) ---
        self.mu = float(np.clip(r.normal(430.0, 45.0), 330.0, 620.0))
        self.sigma = float(max(20.0, r.normal(42.0, 10.0)))
        self.tau = float(max(35.0, r.normal(85.0, 25.0)))

        # --- person-specific magnitude of the spatial/alerting effects ---
        cue_scale = float(max(0.25, r.normal(1.0, 0.30)))
        self.effects = {
            "valid": -28.0 * cue_scale,
            "doublecue": -7.0 * cue_scale,
            "nocue": 0.0,
            "invalid": 22.0 * cue_scale,
        }

        # --- accuracy: this discrimination is easy, so it hugs the ceiling ---
        self.base_acc = float(r.uniform(0.965, 0.995))
        self.miss_rate = float(r.uniform(0.002, 0.020))

        # --- trial-history modulations ---
        self.pes = float(max(0.0, r.normal(28.0, 15.0)))          # post-error slowing
        self.total_practice = float(r.uniform(15.0, 45.0))        # warm-up speed-up
        self.practice_tau = float(r.uniform(45.0, 90.0))          # trials to warm up

        self.trial_count = 0

    def _sample_rt(self, base_ms: float) -> float:
        r = self.rng
        return base_ms + float(r.normal(0.0, self.sigma)) + float(r.exponential(self.tau))

    def respond(self, ctx):
        r = self.rng
        cond = ctx.condition

        # centre of the RT distribution for this trial
        base = self.mu + self.effects.get(cond, 0.0)

        # gradual warm-up over the first blocks
        warm = self.total_practice * (1.0 - np.exp(-self.trial_count / self.practice_tau))
        base -= warm

        # slow down right after an error
        if ctx.prev_correct is False and ctx.prev_rt_ms is not None:
            base += self.pes

        rt = self._sample_rt(base)
        self.trial_count += 1

        # occasional attentional lapse -> no response within the window
        if r.random() < self.miss_rate:
            return (None, self.RESPONSE_WINDOW_MS)

        # choose the key
        acc = self.base_acc
        if cond == "invalid":
            acc -= 0.02  # reorienting costs a little accuracy too

        others = [k for k in ctx.available_keys if k != ctx.correct_key]
        if r.random() < acc or not others:
            key = ctx.correct_key if ctx.correct_key is not None else (
                ctx.available_keys[int(r.integers(0, len(ctx.available_keys)))]
                if ctx.available_keys else None
            )
        else:
            key = others[int(r.integers(0, len(others)))]
            rt *= 0.93  # slips tend to be a touch faster

        rt = float(max(180.0, rt))

        # RT past the deadline registers as a miss
        if rt > self.RESPONSE_WINDOW_MS:
            return (None, self.RESPONSE_WINDOW_MS)

        return (key, rt)
