# Tests

```bash
uv run pytest -q
```

770 tests. Most cover the harness, the participant-program contract, and
the mechanical gate. Two files matter more than the rest:

- `test_naive_prompt_invariants.py`
- `test_system_prompt_invariants.py`

These scan the generation prompt, and every value injected into it, against
a list of banned terms — effect names, distribution families, bare numbers
with units. If a change would tell the model what human behavior looks
like, the suite fails.

Those two files are the experiment's integrity guarantee, not a style
check. Weakening them to make a change pass would invalidate every result
in `docs/results.md`.
