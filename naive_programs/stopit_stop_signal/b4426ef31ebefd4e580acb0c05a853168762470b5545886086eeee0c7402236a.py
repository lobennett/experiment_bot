"""
Computational model of a healthy adult completing the STOP-IT stop-signal task
(Verbruggen & Vermeylen jsPsych version; left/right arrow choice RT with a
staircased visual stop signal).

Behavioral model summary
------------------------
- Go RTs: ex-Gaussian (mu + sigma + tau) with slow AR(1) fluctuations
  (trial-to-trial autocorrelation), early practice speed-up, mild late-session
  fatigue, and small block-restart slowing.
- Sequential effects: post-stop-signal slowing (larger after failed stops),
  post-error slowing after go errors (proactive control adjustments typical
  of this task, where instructions explicitly discourage waiting).
- Choice errors: small per-participant rate of pressing the wrong arrow key;
  rare attentional lapses (very slow RTs) and very rare anticipations.
- Omissions: arise naturally when the sampled RT exceeds MAXRT (1250 ms).
- Stopping: independent horse-race model. The stop process finishes at
  SSD + SSRT (SSRT sampled per trial around a per-participant mean of roughly
  200-260 ms). The go response escapes if it wins the race. Occasional
  trigger failures (stop signal not processed) produce signal-respond trials
  even at short SSDs. With the task's 50 ms staircase this yields ~0.5
  p(respond|signal) and signal-respond RTs faster than go RTs, as in real data.
- Individual differences: every trait parameter (speed, variability, SSRT,
  error/lapse/trigger-failure rates, magnitude of sequential effects,
  practice/fatigue slopes) is drawn per seed.
"""

import math
import numpy as np

MAXRT_MS = 1250.0  # task's response window after go-stimulus onset


class Participant:
    def __init__(self, seed: int):
        self.rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
        r = self.rng

        # --- trait parameters (individual differences) ---
        # ex-Gaussian go RT components
        self.mu = float(np.clip(r.normal(490.0, 60.0), 380.0, 680.0))
        self.sigma = float(np.clip(r.normal(60.0, 15.0), 30.0, 110.0))
        self.tau = float(np.clip(r.normal(115.0, 40.0), 40.0, 240.0))

        # stopping
        self.ssrt_mu = float(np.clip(r.normal(225.0, 30.0), 160.0, 320.0))
        self.ssrt_sd = float(np.clip(r.normal(42.0, 12.0), 20.0, 80.0))
        self.p_trigger_fail = float(np.clip(r.beta(2.0, 45.0), 0.005, 0.12))

        # accuracy / attention
        self.p_choice_err = float(np.clip(r.beta(2.0, 55.0), 0.005, 0.10))
        self.p_lapse = float(np.clip(r.beta(1.5, 110.0), 0.002, 0.05))
        self.p_anticipate = float(np.clip(r.beta(1.2, 350.0), 0.0, 0.012))

        # sequential / strategic adjustments (ms)
        self.post_stop_slow = float(np.clip(r.normal(45.0, 20.0), 0.0, 110.0))
        self.post_fail_extra = float(np.clip(r.normal(20.0, 12.0), 0.0, 60.0))
        self.post_err_slow = float(np.clip(r.normal(32.0, 15.0), 0.0, 90.0))

        # time-on-task
        self.practice_gain = float(np.clip(r.normal(55.0, 25.0), 0.0, 130.0))
        self.practice_tc = float(np.clip(r.normal(22.0, 6.0), 10.0, 40.0))
        self.fatigue_per_trial = float(np.clip(r.normal(0.10, 0.08), -0.05, 0.35))
        self.fatigue_onset = int(r.integers(120, 200))

        # slow endogenous fluctuation (AR(1))
        self.phi = float(np.clip(r.normal(0.45, 0.12), 0.10, 0.80))
        self.ar_sd = self.sigma * float(np.clip(r.normal(0.6, 0.15), 0.3, 1.0))
        self.ar_state = 0.0

        # block structure of this task: 32 practice trials, then 4 x 64
        self.block_starts = frozenset([0, 32, 96, 160, 224])
        self.restart_slow = float(np.clip(r.normal(30.0, 12.0), 0.0, 70.0))

    # ------------------------------------------------------------------
    def _wrong_key(self, ctx):
        candidates = [k for k in ctx.available_keys
                      if ctx.correct_key is not None and k != ctx.correct_key]
        if not candidates:
            return ctx.correct_key
        return candidates[int(self.rng.integers(0, len(candidates)))]

    def _go_mean_shift(self, ctx):
        shift = 0.0
        t = ctx.trial_index
        # practice speed-up (slower early on)
        shift += self.practice_gain * math.exp(-t / self.practice_tc)
        # late-session fatigue
        if t > self.fatigue_onset:
            shift += self.fatigue_per_trial * (t - self.fatigue_onset)
        # first trial after a break is a touch slower
        if t in self.block_starts:
            shift += self.restart_slow
        # post-stop-signal slowing (proactive adjustment)
        if ctx.prev_condition == "stop":
            shift += self.post_stop_slow
            if ctx.prev_correct is False:
                shift += self.post_fail_extra
        # post-error slowing after a wrong go response
        elif ctx.prev_condition == "go" and ctx.prev_correct is False:
            shift += self.post_err_slow
        return shift

    # ------------------------------------------------------------------
    def respond(self, ctx):
        r = self.rng

        # update slow AR(1) fluctuation every trial
        innov_sd = self.ar_sd * math.sqrt(max(1e-9, 1.0 - self.phi ** 2))
        self.ar_state = self.phi * self.ar_state + r.normal(0.0, innov_sd)

        # rare anticipation: a fast guess before proper processing
        if r.random() < self.p_anticipate:
            rt = float(r.uniform(130.0, 280.0))
            keys = list(ctx.available_keys) if ctx.available_keys else []
            if ctx.correct_key is not None and ctx.correct_key not in keys:
                keys.append(ctx.correct_key)
            if keys and r.random() < 0.5:
                key = keys[int(r.integers(0, len(keys)))]
            else:
                key = ctx.correct_key
            return (key, rt)

        # ex-Gaussian RT with state and strategic shifts
        rt = (self.mu
              + self._go_mean_shift(ctx)
              + self.ar_state
              + r.normal(0.0, self.sigma)
              + r.exponential(self.tau))

        # occasional attentional lapse: a long extra delay
        if r.random() < self.p_lapse:
            rt += float(r.uniform(250.0, 800.0))

        rt = float(max(160.0, rt))

        # response window: too slow -> omission (platform records no response)
        if rt >= MAXRT_MS:
            return (None, rt)

        # choice of key
        if ctx.correct_key is None:
            return (None, rt)
        if r.random() < self.p_choice_err:
            key = self._wrong_key(ctx)
        else:
            key = ctx.correct_key
        return (key, rt)

    # ------------------------------------------------------------------
    def on_interrupt(self, ctx, ssd_ms, intended):
        key, rt = intended
        # no go response was going to happen anyway
        if key is None:
            return None
        # trigger failure: stop signal not processed, respond as planned
        if self.rng.random() < self.p_trigger_fail:
            return (key, rt)
        # horse race: stop process finishes at SSD + SSRT
        ssrt = max(80.0, float(self.rng.normal(self.ssrt_mu, self.ssrt_sd)))
        if rt < float(ssd_ms) + ssrt:
            # go process wins: signal-respond trial (RT unchanged, hence
            # signal-respond RTs are faster than go RTs on average)
            return (key, rt)
        # stop process wins: successful inhibition
        return None


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)
