import math
import random


class _StopSignalParticipant:
    """Simulates one healthy adult doing a shape go / star stop-signal task.

    Go responses come from an ex-Gaussian finishing-time process; stopping is
    an independent race (SSD + stop latency vs. the prepared go finishing
    time), with occasional failures to launch the stop process at all.
    The participant also shows human control dynamics: proactive slowing in
    a stop-signal context, extra slowing after stop trials and errors,
    gradual speed-up early on (practice) and mild fatigue late, occasional
    attention lapses, and rare choice errors that tend to be fast.
    """

    def __init__(self, seed):
        rng = random.Random(seed * 7919 + 13)
        self.rng = rng

        # --- go process (ex-Gaussian), per-participant ---
        self.mu = rng.gauss(410.0, 45.0)
        self.sigma = max(25.0, rng.gauss(55.0, 15.0))
        self.tau = max(35.0, rng.gauss(110.0, 40.0))

        # --- stop process ---
        self.ssrt_mean = max(150.0, rng.gauss(235.0, 30.0))
        self.ssrt_sd = max(15.0, rng.gauss(35.0, 12.0))
        self.p_trigger_fail = min(0.20, max(0.0, rng.gauss(0.05, 0.03)))

        # --- errors / lapses ---
        self.p_choice_error = min(0.12, max(0.004, rng.gauss(0.03, 0.015)))
        self.p_lapse = min(0.06, max(0.0, rng.gauss(0.015, 0.010)))

        # --- control dynamics ---
        self.proactive_base = max(0.0, rng.gauss(40.0, 28.0))
        self.slow_state = self.proactive_base  # adaptive slowing, ms
        self.post_stop_slow = max(0.0, rng.gauss(35.0, 20.0))
        self.post_error_slow = max(0.0, rng.gauss(55.0, 25.0))
        self.stop_fail_bump = max(0.0, rng.gauss(25.0, 15.0))

        # --- practice / fatigue ---
        self.practice_boost = max(0.0, rng.gauss(70.0, 30.0))
        self.fatigue_rate = max(0.0, rng.gauss(0.12, 0.08))  # ms per trial

        # response window from the task source (trial_duration = 1500 ms)
        self.deadline = 1500.0
        self.min_rt = max(160.0, rng.gauss(200.0, 15.0))

        # learned shape -> key mapping (from go trials, where the correct
        # key is knowable); used on trials where no correct key is given
        self.mapping = {}
        self._pending_stop_fail = False

    # ------------------------------------------------------------------ #

    def _shape_of(self, ctx):
        text = getattr(ctx, "stimulus_text", None)
        if not text:
            return None
        t = text.lower()
        for shape in ("circle", "square"):
            if shape in t:
                return shape
        return None

    def _sample_go_rt(self, ctx):
        rng = self.rng
        rt = rng.gauss(self.mu, self.sigma) + rng.expovariate(1.0 / self.tau)
        # adaptive proactive slowing + transient post-event slowing
        rt += self.slow_state
        prev_cond = getattr(ctx, "prev_condition", None)
        prev_correct = getattr(ctx, "prev_correct", None)
        if getattr(ctx, "prev_interrupted", None):
            rt += self.post_stop_slow * (0.7 + 0.6 * rng.random())
        elif prev_cond == "stop":
            rt += self.post_stop_slow * (0.4 + 0.4 * rng.random())
        if prev_correct is False:
            rt += self.post_error_slow * (0.6 + 0.8 * rng.random())
        # practice speed-up early, mild fatigue late
        ti = getattr(ctx, "trial_index", 0) or 0
        rt += self.practice_boost * math.exp(-ti / 12.0)
        rt += min(90.0, self.fatigue_rate * ti)
        return max(self.min_rt, rt)

    def _update_slow_state(self, ctx):
        # after a failed stop, people slow down; otherwise slowing decays
        # gently back toward the participant's baseline
        if self._pending_stop_fail:
            self.slow_state += self.stop_fail_bump
            self._pending_stop_fail = False
        self.slow_state = (
            self.proactive_base + (self.slow_state - self.proactive_base) * 0.90
        )
        self.slow_state = max(0.0, min(200.0, self.slow_state))

    # ------------------------------------------------------------------ #

    def respond(self, ctx):
        rng = self.rng
        self._update_slow_state(ctx)

        shape = self._shape_of(ctx)
        key = ctx.correct_key
        if key is not None and shape is not None:
            self.mapping[shape] = key
        if key is None:
            # stop trials expose no correct key; respond to the shape from
            # the mapping learned on go trials, else guess
            if shape is not None and shape in self.mapping:
                key = self.mapping[shape]
            elif ctx.available_keys:
                key = rng.choice(list(ctx.available_keys))
            else:
                return (None, 1.0)

        # occasional attentional lapse -> no response prepared
        if rng.random() < self.p_lapse:
            return (None, 1.0)

        rt = self._sample_go_rt(ctx)

        # too slow for the response window -> recorded as an omission
        if rt >= self.deadline - 10.0:
            return (None, 1.0)

        # rare choice errors, typically on the fast side
        if rng.random() < self.p_choice_error:
            others = [k for k in ctx.available_keys if k != key]
            if others:
                key = rng.choice(others)
                rt = max(self.min_rt, rt * (0.85 + 0.10 * rng.random()))

        return (key, rt)

    def on_interrupt(self, ctx, ssd_ms, intended):
        if intended is None or intended[0] is None:
            return None
        # sometimes the stop process never launches (trigger failure)
        if self.rng.random() < self.p_trigger_fail:
            self._pending_stop_fail = True
            return intended
        ssrt = max(120.0, self.rng.gauss(self.ssrt_mean, self.ssrt_sd))
        stop_finish = ssd_ms + ssrt
        if stop_finish < intended[1]:
            # stop process wins the race: withhold
            return None
        # go process already finished first: response escapes
        self._pending_stop_fail = True
        return intended


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _StopSignalParticipant(int(seed))
