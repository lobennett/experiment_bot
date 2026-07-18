"""
Generative participant model for the RDoC *simple spatial span* task.

The task shows, on each span trial, four brief 4x4 grids each with one black
cell (presentation phase, no response), then a blank 4x4 grid on which the
participant must reproduce the four black-cell locations *in order* by
navigating with the arrow keys and confirming each cell with the spacebar
(7 s response window).

This program models a healthy adult performing that task:
  * spatial working memory that is good but imperfect (serial-position
    effects, order/transposition errors, spatial-neighbour substitutions,
    occasional omissions and rare full lapses),
  * key-path navigation of the grid: the cursor starts at an unknown random
    cell, so the model first "homes" to the top-left corner (arrow presses
    clamp at the edges) and then navigates deterministically to each
    remembered cell before pressing space,
  * plausible movement / selection timing that always fits inside the
    response window,
  * compliant handling of instruction / feedback navigation and attention
    checks.

Each seed is a distinct participant (different memory ability, speed and
error tendencies).
"""

import math
import numpy as np

SIDE = 4               # 4x4 grid
N_CELLS = SIDE * SIDE

UP = "ArrowUp"
DOWN = "ArrowDown"
LEFT = "ArrowLeft"
RIGHT = "ArrowRight"
SELECT = " "           # jsPsych sees the spacebar as event.key === " "


class SpanParticipant:
    def __init__(self, seed):
        self.rng = np.random.RandomState(seed % (2 ** 32))

        # --- stable individual traits -------------------------------------
        # Per-item recall probability (before serial-position weighting).
        self.ability = self._clip(self.rng.normal(0.88, 0.07), 0.60, 0.985)
        # RT scaling: <1 fast, >1 slow.
        self.speed = self._clip(self.rng.normal(1.0, 0.20), 0.62, 1.75)
        # Probability that a given span trial contains an omission (3 items).
        self.p_omit = self._clip(self.rng.normal(0.05, 0.03), 0.005, 0.15)
        # Probability of a full lapse (no response at all) on a span trial.
        self.p_lapse = self._clip(self.rng.normal(0.012, 0.008), 0.0, 0.05)
        # Reliability on easy attention-check items.
        self.attn_acc = self._clip(self.rng.normal(0.975, 0.02), 0.9, 0.999)
        # Serial-position recall multipliers (primacy + recency advantage).
        self.sp_mult = [1.03, 0.92, 0.90, 0.99]

    # ---------------------------------------------------------------- utils
    @staticmethod
    def _clip(x, lo, hi):
        return float(min(max(x, lo), hi))

    def _exg(self, mu, sigma, tau):
        return self.rng.normal(mu, sigma) + self.rng.exponential(tau)

    def _neighbor(self, cell, exclude):
        """A spatially adjacent grid cell (falls back to any free cell)."""
        r, c = divmod(cell, SIDE)
        cand = []
        if c > 0:
            cand.append(cell - 1)
        if c < SIDE - 1:
            cand.append(cell + 1)
        if r > 0:
            cand.append(cell - SIDE)
        if r < SIDE - 1:
            cand.append(cell + SIDE)
        cand = [x for x in cand if x not in exclude]
        if not cand:
            cand = [x for x in range(N_CELLS) if x not in exclude]
        if not cand:
            return cell
        return int(self.rng.choice(cand))

    def _nav_keys(self, cur, target):
        keys = []
        cr, cc = divmod(cur, SIDE)
        tr, tc = divmod(target, SIDE)
        while cr < tr:
            keys.append(DOWN); cr += 1
        while cr > tr:
            keys.append(UP); cr -= 1
        while cc < tc:
            keys.append(RIGHT); cc += 1
        while cc > tc:
            keys.append(LEFT); cc -= 1
        return keys

    # -------------------------------------------------------------- memory
    def _recall(self, true_seq, sub_fn):
        """Return the (possibly erroneous) reproduced sequence.

        An empty list denotes a full lapse (no response)."""
        n = len(true_seq)
        recalled = list(true_seq)
        mult = (self.sp_mult + [0.90] * n)[:n]

        for i in range(n):
            p = self._clip(self.ability * mult[i], 0.45, 0.99)
            if self.rng.rand() > p:
                # Two dominant error modes: order (transposition) vs. item.
                if self.rng.rand() < 0.40 and n >= 2:
                    if i == n - 1:
                        j = i - 1
                    elif i == 0:
                        j = i + 1
                    else:
                        j = i - 1 if self.rng.rand() < 0.5 else i + 1
                    recalled[i], recalled[j] = recalled[j], recalled[i]
                else:
                    recalled[i] = sub_fn(true_seq[i], set(recalled))

        r = self.rng.rand()
        if r < self.p_lapse:
            return []
        if r < self.p_lapse + self.p_omit and n >= 2:
            # Drop one item, weighted toward the later serial positions.
            w = np.arange(1, n + 1, dtype=float)
            w = w / w.sum()
            drop = int(self.rng.choice(np.arange(n), p=w))
            recalled = recalled[:drop] + recalled[drop + 1:]
        return recalled

    # ------------------------------------------------------- span response
    def _grid_response(self, true_seq):
        attempts = self._recall(true_seq, self._neighbor)
        if not attempts:
            return []  # frozen / no response

        actions = []   # ('key', k) or ('click', i)
        gaps = []      # gap (ms) before each action

        sp = self.speed

        def add_key(k, g):
            actions.append(("key", k))
            gaps.append(max(30.0, g))

        # Orientation pause before the first key.
        orient = max(250.0, self._exg(500, 150, 180)) * sp

        # Home to the top-left corner (edge presses clamp harmlessly).
        first = True
        for _ in range(SIDE - 1):
            g = self.rng.uniform(90, 160) * sp
            if first:
                g += orient
                first = False
            add_key(UP, g)
        for _ in range(SIDE - 1):
            add_key(LEFT, self.rng.uniform(90, 160) * sp)

        # Navigate to each remembered cell and confirm it.
        cur = 0
        first_sel = True
        for cell in attempts:
            for k in self._nav_keys(cur, cell):
                add_key(k, max(80.0, self.rng.normal(200, 45)) * sp)
            g = max(140.0, self.rng.normal(360, 110)) * sp
            if first_sel:
                g += max(150.0, self.rng.normal(320, 140)) * sp
                first_sel = False
            add_key(SELECT, g)
            cur = cell

        # Guarantee everything lands inside the 7 s window.
        cap = 6200.0
        total = sum(gaps)
        if total > cap:
            f = cap / total
            gaps = [g * f for g in gaps]

        out = []
        for (typ, val), g in zip(actions, gaps):
            out.append((val, float(g)))
        return out

    def _click_sequence_response(self, true_seq, n_options):
        """Fallback for a click-answered ordered-series trial."""
        def sub(v, ex):
            cand = [x for x in range(n_options) if x not in ex]
            return int(self.rng.choice(cand)) if cand else v

        attempts = self._recall(true_seq, sub)
        if not attempts:
            return []
        out = []
        for idx, cell in enumerate(attempts):
            i = int(cell) % max(1, n_options)
            g = max(180.0, self.rng.normal(650, 220)) * self.speed
            if idx == 0:
                g += max(300.0, self.rng.normal(700, 250)) * self.speed
            out.append(("click", i, float(g)))
        return out

    # ------------------------------------------------------- other trials
    def _choose_click(self, elements):
        low = [str(e).lower() for e in elements]
        for kw in ("continue", "next", "begin", "start",
                   "proceed", "submit", "ok"):
            for i, e in enumerate(low):
                if kw in e:
                    return i
        return len(elements) - 1 if len(elements) > 1 else 0

    def _single_key(self, ctx):
        key = ctx.correct_key
        kl = str(key).lower() if key is not None else ""
        if kl in ("enter", "return"):
            # Navigation / feedback: always advance, after reading a while.
            rt = self._clip(self.rng.normal(2600, 1000), 600, 14000) * \
                math.sqrt(self.speed)
            return (key, float(rt))
        # Attention check ("press the X key"): comply almost always.
        if self.rng.rand() < self.attn_acc or key is None:
            k = key
        else:
            others = [a for a in ctx.available_keys if a != key]
            k = self.rng.choice(others) if others else key
        rt = self._clip(self.rng.normal(2300, 700), 700, 12000) * \
            math.sqrt(self.speed)
        return (k, float(rt))

    # --------------------------------------------------------------- entry
    def respond(self, ctx):
        seq = ctx.correct_sequence
        if seq is not None and len(seq) > 0:
            true_seq = [int(x) for x in seq]
            if ctx.response_elements:
                return self._click_sequence_response(
                    true_seq, len(ctx.response_elements))
            return self._grid_response(true_seq)

        if ctx.response_elements:
            idx = self._choose_click(ctx.response_elements)
            rt = self._clip(self.rng.normal(1600, 600), 400, 10000) * \
                math.sqrt(self.speed)
            return ("click", idx, float(rt))

        if ctx.correct_key is not None:
            return self._single_key(ctx)

        if ctx.available_keys:
            k = self.rng.choice(list(ctx.available_keys))
            rt = self._clip(self.rng.normal(1200, 400), 300, 8000)
            return (k, float(rt))

        # Nothing to press (e.g. a no-response presentation trial).
        return (None, float(self._clip(self.rng.normal(800, 200), 100, 2000)))


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return SpanParticipant(seed)
