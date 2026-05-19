# SP11 Phase 4a — CDP keypress feasibility spike

**Probed at:** 2026-05-18T20:54:14-0700
**URL:** `https://deploy.expfactory.org/preview/10/`
**N keypresses fired:** 38
**Outcome:** `kill_switch_passed_clean`
**Threshold band:** ≥85% (proceed_as_planned)
**Fidelity (bot_pressed == platform_recorded):** **100.0%** (38/38)

## Verdict

CDP fidelity = 100.0% (≥85%). Proceed to Phase 4b as planned. CDP alone is materially closing the gap; focus management + listener-target detection add additive improvements rather than carrying the bulk of the lift.

## Phase context (per Phase 4a user note 1)

The spike fired into the **test phase** only, not instructions
or practice. The wait-for-test-phase loop polled
`jsPsych.data.get().values()` until a `trial_id == 'test_trial'`
record appeared AND the current trial was also `test_trial`.
Practice trials timed out naturally (no responses fired during
them).

- Test-phase reached: `True`
- Test trials recorded before spike fired: `2`
- Test trials recorded after spike fired: `40`
- Net new records during spike: `38`

## Keys used

`[',', '.', '/']`

## Per-fire pairing (first 10 of N)

```json
[
  {
    "i": 0,
    "key_fired": ",",
    "trial_index_fired_on": 64,
    "recorded": ",",
    "rt_recorded": 811,
    "match": true
  },
  {
    "i": 1,
    "key_fired": ".",
    "trial_index_fired_on": 67,
    "recorded": ".",
    "rt_recorded": 252,
    "match": true
  },
  {
    "i": 2,
    "key_fired": "/",
    "trial_index_fired_on": 70,
    "recorded": "/",
    "rt_recorded": 251,
    "match": true
  },
  {
    "i": 3,
    "key_fired": ",",
    "trial_index_fired_on": 73,
    "recorded": ",",
    "rt_recorded": 289,
    "match": true
  },
  {
    "i": 4,
    "key_fired": ".",
    "trial_index_fired_on": 76,
    "recorded": ".",
    "rt_recorded": 219,
    "match": true
  },
  {
    "i": 5,
    "key_fired": "/",
    "trial_index_fired_on": 79,
    "recorded": "/",
    "rt_recorded": 225,
    "match": true
  },
  {
    "i": 6,
    "key_fired": ",",
    "trial_index_fired_on": 82,
    "recorded": ",",
    "rt_recorded": 293,
    "match": true
  },
  {
    "i": 7,
    "key_fired": ".",
    "trial_index_fired_on": 85,
    "recorded": ".",
    "rt_recorded": 228,
    "match": true
  },
  {
    "i": 8,
    "key_fired": "/",
    "trial_index_fired_on": 88,
    "recorded": "/",
    "rt_recorded": 241,
    "match": true
  },
  {
    "i": 9,
    "key_fired": ",",
    "trial_index_fired_on": 91,
    "recorded": ",",
    "rt_recorded": 239,
    "match": true
  }
]
```

## Per-fire pairing (last 10)

```json
[
  {
    "i": 28,
    "key_fired": ".",
    "trial_index_fired_on": 148,
    "recorded": ".",
    "rt_recorded": 269,
    "match": true
  },
  {
    "i": 29,
    "key_fired": "/",
    "trial_index_fired_on": 151,
    "recorded": "/",
    "rt_recorded": 278,
    "match": true
  },
  {
    "i": 30,
    "key_fired": ",",
    "trial_index_fired_on": 154,
    "recorded": ",",
    "rt_recorded": 207,
    "match": true
  },
  {
    "i": 31,
    "key_fired": ".",
    "trial_index_fired_on": 157,
    "recorded": ".",
    "rt_recorded": 230,
    "match": true
  },
  {
    "i": 32,
    "key_fired": "/",
    "trial_index_fired_on": 160,
    "recorded": "/",
    "rt_recorded": 304,
    "match": true
  },
  {
    "i": 33,
    "key_fired": ",",
    "trial_index_fired_on": 163,
    "recorded": ",",
    "rt_recorded": 207,
    "match": true
  },
  {
    "i": 34,
    "key_fired": ".",
    "trial_index_fired_on": 166,
    "recorded": ".",
    "rt_recorded": 222,
    "match": true
  },
  {
    "i": 35,
    "key_fired": "/",
    "trial_index_fired_on": 169,
    "recorded": "/",
    "rt_recorded": 259,
    "match": true
  },
  {
    "i": 36,
    "key_fired": ",",
    "trial_index_fired_on": 172,
    "recorded": ",",
    "rt_recorded": 267,
    "match": true
  },
  {
    "i": 37,
    "key_fired": ".",
    "trial_index_fired_on": 175,
    "recorded": ".",
    "rt_recorded": 221,
    "match": true
  }
]
```

## Mismatch sample (first 10 non-matching pairs)

```json
[]
```

## Decision per spec §4 Phase 4a thresholds

- ≥ 85% → proceed to Phase 4b as planned
- 60-85% → proceed with flag (focus + target detection do more lifting)
- < 60% → escalate to project owner

**This run falls in the `≥85% (proceed_as_planned)` band.**

## Phase 8 implication

Phase 4a is a feasibility spike, not a Phase 7 measurement. The
spike's per-fire fidelity number reflects ONE session on ONE
paradigm; Phase 7's N=30 sequential runs will produce the
authoritative §6 H1/H2 numbers per paradigm. The spike's job
is to ensure the rest of Phase 4 isn't built on a fundamentally
broken delivery channel.