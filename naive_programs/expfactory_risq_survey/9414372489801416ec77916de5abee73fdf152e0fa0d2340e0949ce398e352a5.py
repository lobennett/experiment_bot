import math
import random


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_hash(s):
    """Deterministic polynomial hash (no builtin hash(); stable across runs)."""
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return h


def _norm(s):
    return " ".join((s or "").lower().split())


# Behavior lookup: (substring pattern, lifetime prevalence for an average
# healthy adult, "fun" motive strength if done, "cope" motive strength if done)
_BEHAVIOR_TABLE = [
    ("shoplift",                          0.25, 0.50, 0.25),
    ("speed limit",                       0.50, 0.55, 0.15),
    ("30mph",                             0.50, 0.55, 0.15),
    ("bet on sports",                     0.25, 0.70, 0.10),
    ("cocaine",                           0.04, 0.60, 0.30),
    ("bought drugs",                      0.18, 0.50, 0.30),
    ("did not need",                      0.70, 0.50, 0.40),
    ("unprotected sex",                   0.35, 0.60, 0.20),
    ("physical fight",                    0.30, 0.20, 0.30),
    ("sex for money",                     0.02, 0.30, 0.30),
    ("blacked or passed out",             0.30, 0.50, 0.30),
    ("hallucinogens",                     0.12, 0.70, 0.20),
    ("intoxicated or high",               0.10, 0.30, 0.30),
    ("attacked someone",                  0.015, 0.10, 0.30),
    ("punched or hit",                    0.25, 0.20, 0.40),
    ("hurt yourself on purpose",          0.06, 0.05, 0.80),
    ("afford gambling",                   0.08, 0.50, 0.30),
    ("threatened to physically",          0.18, 0.15, 0.40),
    ("threatened someone with a weapon",  0.025, 0.10, 0.30),
    ("heroin",                            0.01, 0.40, 0.50),
    ("vandalized",                        0.15, 0.50, 0.30),
    ("drinks in 3 hours",                 0.55, 0.60, 0.30),
    ("paid for sex",                      0.04, 0.50, 0.20),
    ("sold drugs",                        0.05, 0.30, 0.20),
    ("robbed",                            0.01, 0.20, 0.20),
    ("plan to kill",                      0.05, 0.00, 0.70),
    ("tried to kill",                     0.03, 0.00, 0.70),
    ("killing yourself",                  0.15, 0.00, 0.70),
    ("kill yourself",                     0.15, 0.00, 0.70),
    ("marijuana",                         0.50, 0.60, 0.40),
    ("stopping eating",                   0.45, 0.30, 0.60),
    ("sexual relationships at the same",  0.15, 0.50, 0.20),
    ("spur of the moment",                0.40, 0.50, 0.30),
    ("multiple drugs",                    0.05, 0.50, 0.40),
    ("lotteries",                         0.60, 0.60, 0.10),
    ("gambled illegally",                 0.03, 0.50, 0.20),
    ("prescription medication",           0.08, 0.30, 0.50),
    ("not hungry",                        0.75, 0.30, 0.60),
    ("red lights",                        0.55, 0.30, 0.10),
    ("stole money",                       0.12, 0.30, 0.30),
]

_LIKERT_ORDER = [
    "strongly disagree",
    "somewhat disagree",
    "equally disagree/agree",
    "somewhat agree",
    "strongly agree",
]

_NAV_FORWARD = ("next", "continue", "submit", "finish", "start", "begin",
                "done", "ok", "complete")
_NAV_BACKWARD = ("previous", "back")


class _Participant:
    def __init__(self, seed):
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        r = self.rng

        # --- stable individual traits -----------------------------------
        # Risk propensity: multiplies the odds of having ever done each
        # risky behavior. Log-normal so most people are near average and a
        # few are markedly higher/lower.
        self.risk = math.exp(r.gauss(0.0, 0.7))
        # Reading speed in characters per second.
        self.char_rate = max(14.0, r.gauss(33.0, 7.0))
        # Decision-time distribution (log-ms).
        self.decide_mu = r.gauss(6.55, 0.22)
        self.decide_sigma = max(0.15, r.gauss(0.35, 0.08))
        # Motor overhead for a click / key press.
        self.motor_ms = r.uniform(150.0, 420.0)
        # Tendency to use scale endpoints rather than middle options.
        self.extremity = r.uniform(0.0, 1.0)
        # How much the participant speeds up as the (long) survey wears on.
        self.final_speed = r.uniform(0.55, 0.95)
        # Probability of a momentary lapse (looked away, sipped coffee...).
        self.lapse_p = r.uniform(0.005, 0.03)

        # --- session state ------------------------------------------------
        self._seen_pages = set()      # text hashes already read
        self._behavior_cache = {}     # behavior text -> profile dict
        self._current_behavior = None
        self._n_responses = 0

    # ------------------------------------------------------------------
    # Behavior profiles
    # ------------------------------------------------------------------
    def _behavior_profile(self, behavior_text):
        key = _norm(behavior_text)
        if key in self._behavior_cache:
            return self._behavior_cache[key]

        p_ever, fun, cope = 0.15, 0.40, 0.30
        for pat, p, f, c in _BEHAVIOR_TABLE:
            if pat in key:
                p_ever, fun, cope = p, f, c
                break

        # Shift the odds by this participant's risk propensity.
        odds = (p_ever / (1.0 - p_ever)) * self.risk
        p_adj = odds / (1.0 + odds)

        # Behavior-specific but seed-stable randomness.
        brng = random.Random(self.seed * 1000003 + _text_hash(key))
        done = brng.random() < p_adj
        profile = {
            "done": done,
            # engagement: how heavily involved with this behavior (if done)
            "engagement": brng.betavariate(1.2, 4.0) if done else 0.0,
            "fun": fun,
            "cope": cope,
            "rng": brng,
        }
        self._behavior_cache[key] = profile
        return profile

    # ------------------------------------------------------------------
    # Response time
    # ------------------------------------------------------------------
    def _rt(self, text):
        t = _norm(text)
        h = _text_hash(t)
        novel = h not in self._seen_pages
        self._seen_pages.add(h)

        read_ms = 0.0
        if t:
            n_chars = min(len(t), 1500)
            novelty = 1.0 if novel else 0.12
            read_ms = (n_chars / self.char_rate) * 1000.0 * novelty

        decide_ms = math.exp(self.rng.gauss(self.decide_mu, self.decide_sigma))

        # Gradual speed-up over the session (long, repetitive survey).
        frac = min(1.0, self._n_responses / 260.0)
        pace = 1.0 - (1.0 - self.final_speed) * frac

        rt = (read_ms + decide_ms) * pace + self.motor_ms

        if self.rng.random() < self.lapse_p:
            rt += self.rng.uniform(2500.0, 14000.0)

        return max(220.0, rt)

    # ------------------------------------------------------------------
    # Option classification / choice
    # ------------------------------------------------------------------
    @staticmethod
    def _find_option(labels, target):
        target = target.lower()
        for i, lab in enumerate(labels):
            if _norm(lab) == target:
                return i
        for i, lab in enumerate(labels):
            if target in _norm(lab):
                return i
        return None

    def _choose_likert(self, labels, stim, profile):
        # Which motive statement is this?
        s = _norm(stim)
        if "upset" in s or "distressed" in s or "overwhelmed" in s:
            motive = "cope"
        elif "excitement" in s or "thrill" in s or "pleasure" in s:
            motive = "fun"
        else:
            motive = "fun"

        if not profile["done"]:
            # Instructions tell never-doers to answer Strongly Disagree.
            target = 0 if self.rng.random() < 0.9 else 1
        else:
            strength = profile[motive]
            mean = 0.4 + 3.2 * strength * (0.5 + profile["engagement"])
            mean = min(4.0, mean)
            val = self.rng.gauss(mean, 1.0)
            target = int(round(min(4.0, max(0.0, val))))
            # Endpoint-preferring responders drift to the extremes.
            if self.rng.random() < 0.30 * self.extremity:
                target = 0 if target <= 2 else 4

        # Map the target level onto the labels actually shown.
        idx = self._find_option(labels, _LIKERT_ORDER[target])
        if idx is not None:
            return idx
        return min(target, len(labels) - 1)

    def _choose_yes_no_na(self, labels, profile):
        if not profile["done"]:
            pick = "n/a" if self.rng.random() < 0.7 else "no"
        else:
            p_yes = min(0.6, 0.04 + 0.5 * profile["engagement"])
            pick = "yes" if self.rng.random() < p_yes else "no"
        idx = self._find_option(labels, pick)
        return idx if idx is not None else self.rng.randrange(len(labels))

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def respond(self, ctx):
        self._n_responses += 1
        stim = ctx.stimulus_text or ""
        rt = self._rt(stim)

        # Track which behavior page we are on.
        s = _norm(stim)
        if "behavior:" in s:
            after = s.split("behavior:", 1)[1]
            self._current_behavior = after.split("(a)")[0][:120].strip()

        elements = tuple(ctx.response_elements or ())

        if elements:
            norm_labels = [_norm(e) for e in elements]

            # Navigation buttons (fullscreen "Continue", page nav, submit).
            fwd = [i for i, lab in enumerate(norm_labels)
                   if any(w in lab for w in _NAV_FORWARD)
                   and not any(w in lab for w in _NAV_BACKWARD)]
            is_question = any("agree" in lab for lab in norm_labels) or (
                self._find_option(elements, "yes") is not None
                and self._find_option(elements, "no") is not None
            )

            if is_question:
                profile = self._behavior_profile(self._current_behavior or stim)
                if any("agree" in lab for lab in norm_labels):
                    idx = self._choose_likert(elements, stim, profile)
                else:
                    idx = self._choose_yes_no_na(elements, profile)
                return ("click", idx, rt)

            if fwd:
                return ("click", fwd[0], rt)

            # Unrecognized option set: pick something plausible.
            return ("click", self.rng.randrange(len(elements)), rt)

        # Keyboard trial: the harness tells us the key that advances things
        # (instructions "Enter", per-character text entry, etc.).
        if ctx.correct_key is not None:
            return (ctx.correct_key, rt)

        if ctx.available_keys:
            return (self.rng.choice(list(ctx.available_keys)), rt)

        return (None, rt)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
