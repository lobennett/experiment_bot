# Behavioral participant

Give an agent a behavioral experiment URL. The skill guides it through the live
browser, records what happened, and saves a task ontology with evidence for each
claim. Browser control and file writing are required.

## Run a task

1. Load [the skill](skills/behavioral-participant/SKILL.md) in your agent, or copy
   its directory into the agent's skill directory.
2. Supply the URL and, optionally, an output directory:

   ```text
   Use behavioral-participant to complete https://deploy.expfactory.org/preview/9/.
   Save the run to participant_runs/new-stop-signal/.
   ```

3. Let the agent read instructions, participate, and collect the platform's
   native export. Each attempt gets its own directory.
4. Inspect `summary.md` for the outcome, `ontology.json` for the task structure,
   and `run.json` for provenance and limitations. Completion requires saved
   terminal-state evidence. Export availability and remote receipt are separate
   outcomes.

Direct mode lets the model decide each response. When tool latency prevents
meaningful participation and autonomous execution is authorized, the skill
uses a frozen, model-authored program that responds locally. Both modes receive
participant-visible information. The manifest records which mode ran.

In Codex, invoke `$behavioral-participant`.
The skill's own files define the workflow; this README is the entry point.

## Inspect the collected outputs

Start with the [evaluation findings](participant_runs/online-battery-20261028/findings.md).
They compare six task types across two platforms and account for all 24 attempts.
Use the [attempt index](participant_runs/online-battery-20261028/summary.md) to
reach each manifest, ontology, evidence bundle, and native export. Open
[report.html](participant_runs/online-battery-20261028/report.html) locally for
filters and embedded downloads. The [smoke test](participant_runs/skill-smoke/summary.md)
is a separate four-trial interface check.

All six task types reached terminal states. Five required local policies;
Tower of Hanoi used direct browser decisions. Short attention checks remained
unreliable, and two tasks produced median response times of 19 ms. These results
establish task operation. Human behavioral validity and unseen-task
generalization remain untested.

## Verify a run

The checker requires Python 3.9 or later and uses the standard library:

```sh
python3 skills/behavioral-participant/scripts/check_run.py \
  participant_runs/online-battery-20261028/preview9/attempt-03
```

A passing check establishes artifact integrity and resolvable evidence links.
Inspect the cited evidence to judge the claims. Use `--seal` only when finalizing
a new run; archived runs already carry their hashes.

To verify the 24 online attempts and the smoke test without changing files:

```sh
for run in participant_runs/online-battery-20261028/*/attempt-* \
           participant_runs/skill-smoke; do
  python3 skills/behavioral-participant/scripts/check_run.py "$run" || exit 1
done
```

With pytest installed, run the skill's eight focused checks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  skills/behavioral-participant/tests
```

## Preserve the record

This branch contains the skill and its outputs. Its root commit is independent
of the original harness. [Archive provenance](participant_runs/README.md)
identifies the source commits, validation scope, and historical files.

Current instructions use one source for each rule and disclose mode-specific
steps through links. This organization follows
[writing-for-agents](https://github.com/mattpocock/skills). Archived instructions,
exports, and observations retain the exact wording captured during each run.
