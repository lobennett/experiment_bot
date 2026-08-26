# Participant programs

The generated code that decides how to behave. One accepted program per
experiment.

Each program defines `make_participant(seed)`. The returned object answers
`respond(ctx)` with a key and a reaction time for every trial, and — on
tasks with a stop signal — decides in `on_interrupt(...)` whether it
manages to stop in time. Programs may use only the standard library and
numpy, cannot read files or the network or the clock, and produce identical
behavior for identical seeds. One seed is one synthetic participant.

Three files share each hash:

| File | Contents |
|---|---|
| `<hash>.py` | the program |
| `<hash>.transcript.json` | the model used, the exact prompt sent, and the raw reply |
| `<hash>.simgate.json` | the mechanical check report |

Every attempt is kept, including ones that failed the check. That is the
point: the record shows what was asked and everything that came back, so
nobody has to take "we didn't iterate on the behavior" on trust.

Programs are written by `experiment-bot-naive-gen`.
