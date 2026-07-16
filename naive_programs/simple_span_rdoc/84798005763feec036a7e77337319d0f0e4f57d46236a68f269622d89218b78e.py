"""
Generative participant model for a spatial span task.

The task alternates fixation + 4x4 grids (one cell black per display, four
displays per trial), then presents a blank 4x4 response grid.  The response
grid starts with a randomly chosen highlighted cell; arrow keys move the
highlight (row-major 4x4, moves off the edge are ignored) and the spacebar
selects the current cell (up to four selections, ~7 s window).

Because the starting highlight position is random and not observable to this
program, every response begins by "homing" to the top-left cell (three Lefts,
three Ups -- out-of-bounds presses are no-ops), which makes the subsequent
navigation deterministic.

Behavioral model:
  * per-item serial recall with primacy/recency weighting; errors are mostly
    spatial (adjacent cell) with some random guesses; occasional order
    transpositions and whole-trial lapses
  * key-press pacing drawn from a lognormal per participant, extra retrieval
    pauses before each item, occasional overshoot-and-correct wiggles,
    mild slowing across the session, occasional slow (inattentive) trials
  * the ~7 s response window is respected: actions that would overrun it are
    dropped, yielding realistic partial/missed responses
  * attention checks answered correctly with high (participant-specific)
    probability at reading-speed latencies; pacing screens (e.g. Enter to
    continue) answered after a plausible reading time
"""

import numpy as np

GRID_W = 4
GRID_N = 16

_OPP = {
    "ArrowLeft": "ArrowRight",
    "ArrowRight": "ArrowLeft",
    "ArrowUp": "ArrowDown",
    "ArrowDown": "ArrowUp",
}


def _neighbors(cell):
    r, c = divmod(cell, GRID_W)
    out = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        rr, cc = r + dr, c + dc
        if 0 <= rr < GRID_W and 0 <= cc < GRID_W:
            out.append(rr * GRID_W + cc)
    return out


def _inbounds_moves(cell):
    r, c = divmod(cell, GRID_W)
    keys = []
    if c > 0:
        keys.append("ArrowLeft")
    if c < GRID_W - 1:
        keys.append("ArrowRight")
    if r > 0:
        keys.append("ArrowUp")
    if r < GRID_W - 1:
        keys.append("ArrowDown")
    return keys


def _path_keys(rng, src, dst):
    r0, c0 = divmod(src, GRID_W)
    r1, c1 = divmod(dst, GRID_W)
    vert = ["ArrowDown" if r1 > r0 else "ArrowUp"] * abs(r1 - r0)
    horiz = ["ArrowRight" if c1 > c0 else "ArrowLeft"] * abs(c1 - c0)
    return vert + horiz if rng.random() < 0.5 else horiz + vert


class Participant:
    def __init__(self, seed):
        self.rng = np.random.default_rng(int(seed))
        r = self.rng
        # Stable individual traits.
        self.item_recall = float(np.clip(r.normal(0.88, 0.08), 0.55, 0.995))
        self.spatial_err_share = float(np.clip(r.normal(0.70, 0.15), 0.20, 0.95))
        self.transpose_p = float(np.clip(r.normal(0.08, 0.05), 0.0, 0.30))
        self.lapse_p = float(np.clip(r.normal(0.03, 0.03), 0.0, 0.15))
        self.press_mu = float(np.clip(r.normal(np.log(170.0), 0.18),
                                      np.log(110.0), np.log(280.0)))
        self.press_sigma = float(np.clip(r.normal(0.25, 0.07), 0.12, 0.45))
        self.plan_mean = float(np.clip(r.normal(650.0, 180.0), 300.0, 1200.0))
        self.retrieve_mean = float(np.clip(r.normal(420.0, 130.0), 150.0, 900.0))
        self.space_extra = float(np.clip(r.normal(160.0, 60.0), 40.0, 350.0))
        self.slowdown = float(np.clip(r.normal(0.0004, 0.0002), 0.0, 0.001))
        self.ac_acc = float(np.clip(r.normal(0.96, 0.04), 0.75, 1.0))
        self.ac_rt_mu = float(np.clip(r.normal(np.log(3200.0), 0.25),
                                      np.log(1800.0), np.log(6000.0)))
        self.read_rt_mu = float(np.clip(r.normal(np.log(3800.0), 0.30),
                                        np.log(1500.0), np.log(9000.0)))

    # ---------------- helpers ----------------

    def _press_gap(self, speed):
        return max(30.0, float(self.rng.lognormal(self.press_mu, self.press_sigma)) * speed)

    def _serial_weights(self, n):
        if n <= 1:
            return [1.0] * n
        w = [1.06 - 0.12 * (i / (n - 1)) for i in range(n)]
        w[-1] += 0.05  # mild recency bump
        return w

    def _recall_sequence(self, targets):
        r = self.rng
        n = len(targets)
        weights = self._serial_weights(n)
        recalled = []
        for i, t in enumerate(targets):
            t = int(t)
            p = min(0.995, self.item_recall * weights[i])
            if r.random() < p:
                recalled.append(t)
            elif r.random() < self.spatial_err_share:
                recalled.append(int(r.choice(_neighbors(t))))
            else:
                others = [c for c in range(GRID_N) if c != t]
                recalled.append(int(r.choice(others)))
        if n >= 2 and r.random() < self.transpose_p:
            j = int(r.integers(0, n - 1))
            recalled[j], recalled[j + 1] = recalled[j + 1], recalled[j]
        return recalled

    # ---------------- trial types ----------------

    def _grid_sequence(self, ctx):
        r = self.rng
        targets = [int(t) for t in ctx.correct_sequence]
        if not targets:
            return []

        # Whole-trial lapse: no response at all.
        if r.random() < self.lapse_p * 0.5:
            return []

        recalled = self._recall_sequence(targets)

        speed = 1.0 + self.slowdown * min(ctx.trial_index, 250)
        slow_trial = 2.0 if r.random() < 0.07 else 1.0

        actions = []
        plan = float(np.clip(r.normal(self.plan_mean, self.plan_mean * 0.25),
                             200.0, 2500.0)) * slow_trial
        # Home to top-left (cell 0); off-grid presses are ignored by the task.
        first = True
        for k in ["ArrowLeft"] * (GRID_W - 1) + ["ArrowUp"] * (GRID_W - 1):
            gap = plan if first else self._press_gap(speed)
            first = False
            actions.append((k, max(30.0, float(gap))))

        cur = 0
        for cell in recalled:
            retrieve = float(np.clip(
                r.normal(self.retrieve_mean, self.retrieve_mean * 0.35),
                80.0, 2000.0)) * slow_trial
            keys = _path_keys(r, cur, cell)
            # Occasional overshoot-and-correct wiggle.
            if keys and r.random() < 0.06:
                moves = _inbounds_moves(cell)
                if moves:
                    k = str(r.choice(moves))
                    keys = keys + [k, _OPP[k]]
            added_retrieve = False
            for k in keys:
                gap = self._press_gap(speed)
                if not added_retrieve:
                    gap += retrieve
                    added_retrieve = True
                actions.append((k, float(gap)))
            space_gap = self._press_gap(speed) + self.space_extra
            if not added_retrieve:
                space_gap += retrieve
            actions.append((" ", max(40.0, float(space_gap))))
            cur = cell

        # Respect the response window: drop actions that would overrun it.
        budget = 6800.0
        total = 0.0
        out = []
        for k, gap in actions:
            total += gap
            if total > budget:
                break
            out.append((k, float(gap)))
        return out

    def _click_sequence(self, ctx):
        r = self.rng
        m = len(ctx.response_elements)
        out = []
        first = True
        for idx in ctx.correct_sequence:
            idx = int(idx)
            if r.random() >= min(0.995, self.item_recall) and m > 1:
                choices = [i for i in range(m) if i != idx]
                idx = int(r.choice(choices))
            base = self.plan_mean if first else self.retrieve_mean + 500.0
            gap = float(np.clip(r.normal(base, 250.0), 250.0, 4000.0))
            first = False
            out.append(("click", idx, gap))
        return out

    def _attention_check(self, ctx):
        r = self.rng
        rt = float(np.clip(r.lognormal(self.ac_rt_mu, 0.35), 700.0, 14000.0))
        if ctx.correct_key is not None and r.random() < self.ac_acc:
            return (ctx.correct_key, rt)
        if r.random() < 0.4:
            return (None, rt)
        pool = [k for k in ctx.available_keys if k != ctx.correct_key]
        if not pool:
            pool = list("asdfjkl")
        return (str(r.choice(pool)), rt)

    # ---------------- entry point ----------------

    def respond(self, ctx):
        r = self.rng
        if ctx.correct_sequence is not None:
            if ctx.response_elements:
                return self._click_sequence(ctx)
            return self._grid_sequence(ctx)
        if ctx.condition == "attention_check":
            return self._attention_check(ctx)
        if ctx.correct_key is not None:
            # Pacing screen (e.g. press Enter to continue): reading-time RT.
            rt = float(np.clip(r.lognormal(self.read_rt_mu, 0.45), 800.0, 13500.0))
            return (ctx.correct_key, rt)
        return (None, 1000.0)


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return Participant(seed)
