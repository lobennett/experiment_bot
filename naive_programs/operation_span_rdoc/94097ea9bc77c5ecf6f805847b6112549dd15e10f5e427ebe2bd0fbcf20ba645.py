"""
Generative participant model for an operation-span style task.

Task structure inferred from the source:
  * "processing" trials: an 8x8 grid is judged symmetric/asymmetric with the
    left/right arrow keys inside a 2.5 s window (the correct key is supplied
    per trial via ctx.correct_key).
  * "recall" trials: a blank 4x4 grid; the participant navigates with arrow
    keys (positions 0-15, row-major, clamped at the edges) and presses
    spacebar to select the 4 remembered cell locations in presentation
    order, within a 7 s response window.
  * "attention_check" trials: press the requested key (15 s limit).

Behavioral model:
  * Stable per-seed traits: processing accuracy/speed (ex-Gaussian RTs),
    lapse rate, memory fidelity with primacy/recency modulation, adjacent-
    cell confusions and occasional order transpositions, motor key-press
    tempo, planning/retrieval pauses, and a mild fatigue drift.
  * Recall navigation: the participant first anchors to the top-left corner
    (edge presses are no-ops, so this is unambiguous from any start), then
    moves item by item, usually one axis at a time, with occasional
    overshoot-and-correct. Under time pressure the tempo compresses, and
    responses that still spill past the window are simply never made
    (yielding realistic incomplete recall on slow trials).
"""

import numpy as np

_OPP = {
    "ArrowLeft": "ArrowRight",
    "ArrowRight": "ArrowLeft",
    "ArrowUp": "ArrowDown",
    "ArrowDown": "ArrowUp",
}


def make_participant(seed: int):
    return _Participant(int(seed))


class _Participant:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        r = self.rng

        # --- stable individual traits ---
        self.proc_acc = float(np.clip(r.normal(0.92, 0.05), 0.70, 0.99))
        self.proc_mu = float(np.clip(r.normal(870, 140), 600, 1450))
        self.proc_sigma = float(np.clip(r.normal(130, 35), 60, 280))
        self.proc_tau = float(np.clip(r.normal(170, 60), 50, 420))
        self.proc_miss = float(np.clip(r.normal(0.02, 0.015), 0.0, 0.08))

        self.mem_p = float(np.clip(r.normal(0.86, 0.07), 0.55, 0.985))
        self.adj_err_p = float(np.clip(r.normal(0.62, 0.10), 0.30, 0.85))
        self.swap_p = float(np.clip(r.normal(0.06, 0.035), 0.0, 0.18))

        self.key_gap = float(np.clip(r.normal(170, 30), 110, 260))
        self.plan_mu = float(np.clip(r.normal(820, 200), 420, 1400))
        self.retrieve_mu = float(np.clip(r.normal(320, 90), 150, 650))

        self.att_acc = float(np.clip(r.normal(0.965, 0.03), 0.80, 1.0))
        self.fatigue = float(np.clip(r.normal(0.8, 0.5), 0.0, 2.5))  # ms/trial

        self.n_trials = 0

    # ------------------------------------------------------------------ #
    def respond(self, ctx):
        self.n_trials += 1
        if getattr(ctx, "correct_sequence", None) is not None:
            return self._recall(ctx)
        cond = (ctx.condition or "").lower()
        if cond == "attention_check" and ctx.correct_key is not None:
            return self._attention(ctx)
        return self._processing(ctx)

    # ------------------------- helpers -------------------------------- #
    def _exg(self, mu, sigma, tau, lo, hi):
        v = self.rng.normal(mu, sigma) + self.rng.exponential(tau)
        return float(min(max(v, lo), hi))

    @staticmethod
    def _neighbors(c):
        row, col = divmod(c, 4)
        out = []
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = row + dr, col + dc
            if 0 <= rr < 4 and 0 <= cc < 4:
                out.append(rr * 4 + cc)
        return out

    def _wrong_key(self, ctx):
        ck = ctx.correct_key
        alts = [k for k in (ctx.available_keys or ()) if k != ck]
        if alts:
            return alts[int(self.rng.integers(len(alts)))]
        low = ck.lower()
        if "left" in low:
            return ck.replace("Left", "Right").replace("left", "right")
        if "right" in low:
            return ck.replace("Right", "Left").replace("right", "left")
        return ck

    # ------------------------- attention check ------------------------ #
    def _attention(self, ctx):
        r = self.rng
        rt = self._exg(3000, 750, 1000, 900, 14200)
        if r.random() < 0.015:
            return None, rt  # zoned out entirely
        if r.random() < self.att_acc:
            return ctx.correct_key, rt
        alts = [k for k in (ctx.available_keys or ()) if k != ctx.correct_key]
        if not alts:
            return ctx.correct_key, rt
        return alts[int(r.integers(len(alts)))], rt

    # ------------------------- symmetry judgment ---------------------- #
    def _processing(self, ctx):
        r = self.rng
        mu = self.proc_mu + self.fatigue * min(self.n_trials, 120)
        rt = self._exg(mu, self.proc_sigma, self.proc_tau, 380, 2450)
        if ctx.correct_key is None:
            keys = list(ctx.available_keys or ("ArrowLeft", "ArrowRight"))
            return keys[int(r.integers(len(keys)))], rt
        if r.random() < self.proc_miss:
            return None, 2400.0
        if r.random() < self.proc_acc:
            return ctx.correct_key, rt
        rt_err = self._exg(mu * 0.97, self.proc_sigma, self.proc_tau, 360, 2450)
        return self._wrong_key(ctx), rt_err

    # ------------------------- serial spatial recall ------------------ #
    def _remembered(self, targets):
        r = self.rng
        n = len(targets)
        out = []
        for i, c in enumerate(targets):
            p = self.mem_p
            if i == 0:
                p = min(1.0, p + 0.05)      # primacy
            elif i == n - 1:
                p = min(1.0, p + 0.02)      # recency
            else:
                p = max(0.0, p - 0.03)
            if r.random() < p:
                out.append(c)
                continue
            if r.random() < self.adj_err_p:
                cand = self._neighbors(c)
            else:
                cand = [x for x in range(16) if x != c]
            fresh = [x for x in cand if x not in out]
            pool = fresh if fresh else cand
            out.append(int(pool[int(r.integers(len(pool)))]))
        if n >= 2 and r.random() < self.swap_p:
            j = int(r.integers(0, n - 1))
            out[j], out[j + 1] = out[j + 1], out[j]
        return out

    def _path_keys(self, start, target):
        r = self.rng
        row, col = divmod(start, 4)
        trow, tcol = divmod(target, 4)
        moves = []
        moves += ["ArrowDown"] * (trow - row) if trow > row else ["ArrowUp"] * (row - trow)
        moves += ["ArrowRight"] * (tcol - col) if tcol > col else ["ArrowLeft"] * (col - tcol)
        horiz_first = r.random() < 0.5
        moves.sort(key=lambda k: (k in ("ArrowUp", "ArrowDown")) == horiz_first)
        # occasional overshoot on the final axis, corrected right after;
        # only when the extra press actually stays on the grid
        if moves and r.random() < 0.07:
            last = moves[-1]
            ok = (
                (last == "ArrowLeft" and tcol > 0)
                or (last == "ArrowRight" and tcol < 3)
                or (last == "ArrowUp" and trow > 0)
                or (last == "ArrowDown" and trow < 3)
            )
            if ok:
                moves += [last, _OPP[last]]
        return moves

    def _recall(self, ctx):
        targets = [int(t) % 16 for t in (ctx.correct_sequence or ())]
        if not targets:
            return []
        recalled = self._remembered(targets)

        actions = []
        # planning pause, then anchor to the top-left corner: three
        # up/left pairs reach cell 0 from anywhere (edge presses no-op)
        gap0 = self._exg(self.plan_mu, 200, 250, 350, 2600)
        for i, k in enumerate(("ArrowUp", "ArrowLeft") * 3):
            g = gap0 if i == 0 else self._exg(self.key_gap * 0.85, 30, 20, 80, 450)
            actions.append((k, g))

        pos = 0
        for cell in recalled:
            first = True
            for k in self._path_keys(pos, cell):
                if first:
                    g = self._exg(self.retrieve_mu, 90, 110, 120, 1400)
                    first = False
                else:
                    g = self._exg(self.key_gap, 30, 25, 80, 500)
                actions.append((k, g))
            g = self._exg(260, 60, 60, 110, 800)
            if first:  # target is the current cell: pause holds retrieval time
                g += self._exg(self.retrieve_mu, 90, 110, 100, 1200)
            actions.append((" ", g))
            pos = cell

        # time pressure: compress tempo if the plan overruns the window,
        # then drop anything that still spills past the deadline
        total = sum(a[1] for a in actions)
        budget = 6700.0
        if total > budget:
            f = max(0.7, budget / total)
            actions = [(k, max(70.0, g * f)) for (k, g) in actions]
        out, t = [], 0.0
        for k, g in actions:
            t += g
            if t > 6900.0:
                break
            out.append((k, float(g)))
        return out
