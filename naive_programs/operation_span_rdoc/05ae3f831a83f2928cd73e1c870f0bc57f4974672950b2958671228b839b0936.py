"""Generative participant program for the operation/symmetry span task.

This is a complex working-memory span task with three response-bearing trial
types (surfaced to this program as the conditions `processing`, `recall`, and
`attention_check`):

  * processing  -- an 8x8 grid is shown; the participant judges whether it is
                   symmetric/asymmetric with a two-alternative arrow-key press.
                   A hard, speeded binary decision inside a 2500 ms window.
  * recall      -- after four memorize/processing alternations, a blank 4x4
                   grid is shown; the participant reproduces the ordered set of
                   memorized cells by navigating with arrow keys and confirming
                   each cell with the spacebar (7000 ms window).
  * attention_check -- a between-block prompt asking for a specific key press.

Every seed is a distinct participant. Individual differences are drawn once at
construction (processing speed/accuracy, spatial-memory ability, attentiveness)
and then govern behavior for the whole session.
"""

import numpy as np

ARROW_LEFT = "ArrowLeft"
ARROW_RIGHT = "ArrowRight"
ARROW_UP = "ArrowUp"
ARROW_DOWN = "ArrowDown"
SPACE = " "

GRID_N = 4  # the recall grid is 4x4

# Timing constraints read from the task source.
PROC_WINDOW_MS = 2500.0     # processingTrialDuration
RECALL_WINDOW_MS = 7000.0   # responseBlockDuration
ATTN_WINDOW_MS = 15000.0    # attention-check trial_duration


class _Participant:
    def __init__(self, seed):
        self.rng = np.random.RandomState(int(seed) % (2 ** 32))
        r = self.rng

        # --- Processing task (symmetry judgment): speed & accuracy ---------
        # Symmetry judgments are effortful but the 2.5 s window and the task's
        # speed feedback keep responses fairly quick.
        self.proc_rt_mu = float(np.clip(r.normal(1150.0, 160.0), 750.0, 1650.0))
        self.proc_rt_sigma = self.proc_rt_mu * float(np.clip(r.normal(0.22, 0.04), 0.12, 0.34))
        self.proc_rt_tau = float(np.clip(r.normal(220.0, 80.0), 80.0, 450.0))
        self.proc_acc = float(np.clip(r.normal(0.87, 0.055), 0.70, 0.975))
        self.proc_lapse = float(np.clip(r.normal(0.022, 0.013), 0.0, 0.07))

        # --- Spatial recall: memory ability --------------------------------
        self.mem_ability = float(np.clip(r.normal(0.80, 0.10), 0.48, 0.96))
        self.give_up_rate = float(np.clip(r.normal(0.03, 0.02), 0.0, 0.10))

        # --- Attention checks ----------------------------------------------
        self.attn_acc = float(np.clip(r.normal(0.96, 0.03), 0.84, 0.996))
        self.attn_rt_mu = float(np.clip(r.normal(2900.0, 750.0), 1500.0, 6000.0))
        self.attn_rt_sigma = self.attn_rt_mu * 0.30

    # ---------------------------------------------------------------- utils
    def _ex_gaussian(self, mu, sigma, tau):
        return float(self.rng.normal(mu, sigma) + self.rng.exponential(tau))

    @staticmethod
    def _rc(cell):
        return cell // GRID_N, cell % GRID_N

    def _path(self, a, b):
        """Arrow-key moves from cell a to cell b (horizontal then vertical)."""
        ra, ca = self._rc(a)
        rb, cb = self._rc(b)
        moves = []
        if cb > ca:
            moves += [ARROW_RIGHT] * (cb - ca)
        elif cb < ca:
            moves += [ARROW_LEFT] * (ca - cb)
        if rb > ra:
            moves += [ARROW_DOWN] * (rb - ra)
        elif rb < ra:
            moves += [ARROW_UP] * (ra - rb)
        return moves

    # ------------------------------------------------------------- dispatch
    def respond(self, ctx):
        cond = (getattr(ctx, "condition", "") or "").lower()
        seq = getattr(ctx, "correct_sequence", None)

        if seq is not None:
            return self._recall(ctx, list(seq))
        if "attention" in cond or "check" in cond:
            return self._attention(ctx)
        if "recall" in cond:
            # A recall-labeled trial with no target sequence is a passive
            # memorize/view frame: no response is expected.
            return (None, float(np.clip(self.rng.normal(500.0, 120.0), 150.0, 1000.0)))
        # Everything else is the speeded symmetry (processing) judgment.
        return self._processing(ctx)

    # ----------------------------------------------------------- processing
    def _processing(self, ctx):
        r = self.rng
        correct = getattr(ctx, "correct_key", None)
        keys = getattr(ctx, "available_keys", None) or (ARROW_LEFT, ARROW_RIGHT)

        slow = 1.06 if getattr(ctx, "prev_correct", None) is False else 1.0
        rt = self._ex_gaussian(self.proc_rt_mu * slow, self.proc_rt_sigma, self.proc_rt_tau)

        # Straight lapse (attention flicker) -> no key.
        if r.rand() < self.proc_lapse:
            return (None, float(np.clip(rt, 300.0, PROC_WINDOW_MS - 20.0)))
        # Too slow -> the response window closes with no registered key.
        if rt >= PROC_WINDOW_MS - 20.0:
            return (None, PROC_WINDOW_MS - 20.0)

        rt = float(np.clip(rt, 250.0, PROC_WINDOW_MS - 50.0))

        acc = self.proc_acc * (0.9 if rt < 500.0 else 1.0)
        if correct is not None and r.rand() < acc:
            return (correct, rt)

        alts = [k for k in keys if k != correct]
        if not alts:
            alts = [ARROW_LEFT if correct == ARROW_RIGHT else ARROW_RIGHT]
        return (alts[r.randint(len(alts))], rt)

    # ------------------------------------------------------------ attention
    def _attention(self, ctx):
        r = self.rng
        correct = getattr(ctx, "correct_key", None)
        rt = float(np.clip(self._ex_gaussian(self.attn_rt_mu, self.attn_rt_sigma, 400.0),
                           500.0, ATTN_WINDOW_MS - 500.0))

        if correct is not None and r.rand() < self.attn_acc:
            return (correct, rt)

        keys = getattr(ctx, "available_keys", None)
        if keys:
            alts = [k for k in keys if k != correct]
            if alts:
                return (alts[r.randint(len(alts))], rt)
        # Rare full miss.
        if correct is not None and r.rand() < 0.5:
            return (correct, rt)
        return (None, ATTN_WINDOW_MS - 500.0)

    # --------------------------------------------------------------- recall
    def _recalled_cells(self, seq):
        """Which cells the participant reports, in order, given memory ability."""
        r = self.rng
        # Serial-position weighting: primacy strong, recency weakened by the
        # intervening symmetry (processing) distractor.
        base_mult = [1.06, 0.95, 0.90, 1.00]
        out = []
        used = set()
        for i, tcell in enumerate(seq):
            mult = base_mult[i] if i < len(base_mult) else 0.90
            p = float(np.clip(self.mem_ability * mult, 0.05, 0.985))
            if r.rand() < p:
                cell = tcell
            else:
                cell = self._error_cell(tcell, used)
            out.append(cell)
            used.add(cell)
        return out

    def _error_cell(self, tcell, used):
        r = self.rng
        row, col = self._rc(tcell)
        neighbors = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < GRID_N and 0 <= nc < GRID_N:
                    neighbors.append(nr * GRID_N + nc)
        # Errors are mostly spatial confusions with a nearby cell.
        cands = [c for c in neighbors if c not in used]
        if cands and r.rand() < 0.65:
            return cands[r.randint(len(cands))]
        allc = [c for c in range(GRID_N * GRID_N) if c not in used]
        if not allc:
            allc = list(range(GRID_N * GRID_N))
        return allc[r.randint(len(allc))]

    def _recall(self, ctx, seq):
        r = self.rng
        recalled = self._recalled_cells(seq)

        # Occasionally give up on the final item (submits fewer than 4).
        submit = recalled
        if len(submit) > 1 and r.rand() < self.give_up_rate:
            submit = submit[:-1]

        actions = []
        # The cursor starts on a random cell that we do not observe. Clamp to
        # the top-left corner deterministically (edge presses are no-ops), then
        # navigate from a known origin.
        first_gap = float(np.clip(r.normal(850.0, 250.0), 400.0, 1500.0))
        reset = [ARROW_LEFT, ARROW_LEFT, ARROW_LEFT, ARROW_UP, ARROW_UP, ARROW_UP]
        for i, mv in enumerate(reset):
            gap = first_gap if i == 0 else float(np.clip(r.normal(95.0, 22.0), 45.0, 180.0))
            actions.append((mv, gap))

        cur = 0
        for tcell in submit:
            for mv in self._path(cur, tcell):
                actions.append((mv, float(np.clip(r.normal(100.0, 25.0), 45.0, 190.0))))
            actions.append((SPACE, float(np.clip(r.normal(230.0, 70.0), 110.0, 450.0))))
            cur = tcell

        # Keep the whole path within the 7 s response window.
        total = sum(g for _, g in actions)
        budget = RECALL_WINDOW_MS - 300.0
        if total > budget and total > 0:
            scale = budget / total
            actions = [(k, max(20.0, g * scale)) for k, g in actions]

        return actions


def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
    return _Participant(seed)
