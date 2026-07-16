import math
import random

# Key semantics on this deployment: with the page's default group assignment
# (efVars is empty, so group_index = 1), "target present" maps to the period
# key and "target absent" maps to the comma key. ctx.correct_key is still the
# per-trial ground truth; these constants are only used to infer whether the
# current display contains a target, which drives search time.
PRESENT_KEY = "."
ABSENT_KEY = ","


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


class _Participant:
    def __init__(self, seed: int):
        self.rng = random.Random(1_000_003 * (int(seed) + 17) + 42)
        r = self.rng

        # --- stable individual traits (one draw per participant) ---
        self.base = _clip(r.gauss(500.0, 55.0), 380.0, 700.0)      # perceptual+motor baseline, ms
        self.conj_extra = _clip(r.gauss(55.0, 25.0), 0.0, 150.0)   # added cost of conjunction displays
        self.conj_rate = _clip(r.gauss(16.0, 5.0), 6.0, 32.0)      # ms per item scanned (conjunction)
        self.exhaust = _clip(r.gauss(0.95, 0.10), 0.70, 1.20)      # thoroughness of target-absent search
        self.feat_rate_p = r.uniform(0.0, 2.5)                     # near-flat set-size slope, feature/found
        self.feat_rate_a = self.feat_rate_p + r.uniform(0.5, 3.0)  # slightly steeper when nothing pops out
        self.sigma = _clip(r.gauss(70.0, 18.0), 35.0, 130.0)       # gaussian RT noise
        self.tau = _clip(r.gauss(120.0, 45.0), 50.0, 300.0)        # exponential RT tail

        self.detect = _clip(r.gauss(0.965, 0.02), 0.88, 0.995)     # P(find target | present)
        self.fa = _clip(r.gauss(0.02, 0.012), 0.002, 0.07)         # P(report present | absent)
        self.slip = _clip(r.gauss(0.012, 0.008), 0.001, 0.04)      # wrong-key motor slip
        self.lapse = _clip(r.gauss(0.02, 0.012), 0.002, 0.06)      # attentional lapse rate

        self.pes = _clip(r.gauss(40.0, 25.0), 0.0, 120.0)          # post-error slowing, ms
        self.warmup = r.uniform(20.0, 90.0)                        # extra ms early in session, decays
        self.warmup_tau = r.uniform(10.0, 40.0)                    # decay constant, in trials
        self.fatigue = r.uniform(0.0, 0.30)                        # slow drift upward, ms per trial

    # ------------------------------------------------------------------
    def respond(self, ctx):
        r = self.rng
        cond = (ctx.condition or "").strip().lower()
        ck = ctx.correct_key

        if cond not in ("feature", "conjunction") or ck not in (PRESENT_KEY, ABSENT_KEY):
            return self._generic(ctx)

        idx = max(0, int(ctx.trial_index or 0))
        present = (ck == PRESENT_KEY)
        # Display size (8 or 24) is not observable through ctx; the task uses
        # them equally often, so draw a latent size per trial.
        n = 8 if r.random() < 0.5 else 24

        # Attentional lapse: either no response at all, or a late stab.
        if r.random() < self.lapse:
            if r.random() < 0.5:
                return (None, 1200.0 + r.random() * 700.0)
            key = PRESENT_KEY if r.random() < 0.5 else ABSENT_KEY
            return (key, 900.0 + r.random() * 950.0)

        # Decision process: search the display, terminate on find or exhaustion.
        if present:
            if r.random() < self._p_detect(cond, n):
                mean = self._search_ms(cond, n, found=True)
                key = PRESENT_KEY
            else:
                # Searched, failed to find the target, gave up -> "absent" (slow miss)
                mean = self._search_ms(cond, n, found=False)
                key = ABSENT_KEY
        else:
            mean = self._search_ms(cond, n, found=False)
            if r.random() < self._p_fa(cond):
                key = PRESENT_KEY
                mean *= 0.85  # false alarms terminate search early
            else:
                key = ABSENT_KEY

        if r.random() < self.slip:
            key = ABSENT_KEY if key == PRESENT_KEY else PRESENT_KEY

        # Session-level dynamics
        mean += self.warmup * math.exp(-idx / self.warmup_tau)
        mean += self.fatigue * idx
        if ctx.prev_correct is False:
            mean += self.pes
        elif ctx.prev_condition is not None and ctx.prev_rt_ms is None:
            mean += 0.6 * self.pes  # slowing after a missed response too

        rt = r.gauss(mean, self.sigma) + r.expovariate(1.0 / self.tau)
        rt = max(240.0 + r.random() * 40.0, rt)

        # The response window closes at 2000 ms; very slow searches sometimes
        # simply don't make it in.
        if rt > 1950.0:
            if r.random() < 0.6:
                return (None, min(rt, 2400.0))
            rt = 1500.0 + r.random() * 440.0

        return (key, float(rt))

    # ------------------------------------------------------------------
    def _p_detect(self, cond, n):
        p = self.detect
        if cond == "feature":
            p = min(0.997, p + 0.02)  # pop-out: near-ceiling detection
        else:
            p -= 0.035 if n == 24 else 0.010
        return _clip(p, 0.75, 0.997)

    def _p_fa(self, cond):
        f = self.fa * (1.3 if cond == "conjunction" else 0.6)
        return _clip(f, 0.001, 0.10)

    def _search_ms(self, cond, n, found):
        if cond == "feature":
            rate = self.feat_rate_p if found else self.feat_rate_a
            return self.base + rate * n
        # Conjunction: serial self-terminating search. On target-present
        # trials roughly half the items are scanned before the target turns
        # up; on target-absent trials (nearly) all of them are.
        if found:
            scanned = n * (0.5 + (self.rng.random() - 0.5) * 0.3)
            return self.base + self.conj_extra + self.conj_rate * scanned
        return self.base + self.conj_extra + self.conj_rate * n * self.exhaust

    # ------------------------------------------------------------------
    def _generic(self, ctx):
        # Non-search trials (e.g. attention checks or other prompted
        # responses): read the prompt, then comply, with rare fumbles.
        r = self.rng
        rt = max(500.0, r.gauss(1400.0, 350.0) + r.expovariate(1.0 / 700.0))
        key = ctx.correct_key
        if key is None:
            if ctx.response_elements:
                return ("click", 0, rt)
            return (None, rt)
        if r.random() < 0.03 and ctx.available_keys:
            alts = [k for k in ctx.available_keys if k != key]
            if alts:
                key = r.choice(alts)
        return (key, float(rt))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
