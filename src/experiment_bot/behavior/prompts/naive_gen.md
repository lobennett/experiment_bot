You are writing a computational model of a human research participant.

Below is the source code of a web-based task. Read it and write ONE
self-contained Python program that simulates a typical healthy adult
completing this task. Your program's recorded data should be
indistinguishable from a real participant's platform-recorded data — in
whatever respects you judge matter. You decide every aspect of the
behavioral model: what varies, across what, and by how much. Each seed is
a distinct participant, so participants must differ from each other the
way real people differ.

## Contract (exact)

Your program is a single Python file that defines:

```python
def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
```

The participant object must define:

```python
def respond(self, ctx):
    """Called once per trial. Return (key, rt_ms).

    key: ctx.correct_key, one of ctx.available_keys, or None to make
    no response.
    rt_ms: response time in milliseconds (float > 0).

    ctx fields: condition (str), correct_key (str | None),
    available_keys (tuple[str, ...]), trial_index (int),
    prev_condition, prev_correct, prev_rt_ms, prev_interrupted
    (previous-trial outcome; None on the first trial),
    stimulus_text (str | None): the trial's visible context text
    when the task exposes one, else None.

    On some tasks the full key inventory is not known up front: it is
    discovered trial-by-trial, so ctx.available_keys can grow as the
    task reveals more keys. ctx.correct_key is always valid to press for
    the current trial even if it has not appeared in ctx.available_keys yet.
    """
```

{INTERRUPT_NOTE}

## Hard constraints

- Imports: Python standard library (math, random, itertools, functools,
  collections, dataclasses, statistics, typing) and numpy ONLY.
- Deterministic per seed: seed all randomness from the `seed` argument.
- No file, network, or clock access.
- Return plain tuples; do not import anything from the experiment harness.

## Mechanical facts about this task

- Condition labels your model will see: {CONDITIONS}
- Key map (condition -> correct key): {KEY_MAP}

## Task source

{PAGE_SOURCE}

Reply with ONLY the Python program in a single fenced code block.
