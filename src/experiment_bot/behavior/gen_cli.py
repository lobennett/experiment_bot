"""experiment-bot-naive-gen: SP21 naive-arm program generation.

Pre-registered discipline: the first program that passes the mechanical
simulation gate IS the program. Retries (max 2) happen only on gate
failure, every attempt is archived. Never regenerate on behavioral taste.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from experiment_bot.behavior.provider import (
    NON_LITERAL_KEY_SENTINELS, stim_condition_and_key,
)
from experiment_bot.behavior.simgate import run_gate
from experiment_bot.core.scraper import scrape_experiment_source
from experiment_bot.llm.factory import build_default_client
from experiment_bot.taskcard.hashing import taskcard_sha256 as _compute_taskcard_hash

_TEMPLATE = Path(__file__).parent / "prompts" / "naive_gen.md"

_INTERRUPT_NOTE = '''The task also has trials where a mid-trial signal tells
the participant to withhold the response they were preparing. Your
participant must also define:

```python
def on_interrupt(self, ctx, ssd_ms, intended):
    """ssd_ms: ms from trial start to the signal. intended: the
    (key, rt_ms) your respond() returned. Return None to withhold,
    or (key, rt_ms) to respond anyway."""
```'''

# Substituted for {KEY_MAP} when the structural card has no static key_map
# entries left after filtering sentinels (e.g. every condition maps to
# "dynamic"/"dynamic_mapping" — the executor resolves the actual key per
# trial via JS, never from a static map). Kept mechanical: no numbers, no
# phenomenon names, so the neutrality invariants stay green.
_EMPTY_KEY_MAP_NOTE = (
    "no static map — keys are resolved per trial at runtime; "
    "rely on ctx.correct_key each trial"
)

# Prefix prepended to the prompt on a gate-failure retry. Factored into a
# constant so the neutrality invariant tests can scan it for banned terms
# the same way they scan the template.
_RETRY_PREFIX = "\n\n## Previous attempt failed the MECHANICAL gate\n"

# Trailing retry instruction, also scanned by the neutrality invariants.
_RETRY_SUFFIX = "\nFix ONLY these mechanical problems."


def _load_structural_taskcard(label: str, taskcards_dir: str,
                              taskcard_sha256: str | None = None):
    # Same loaders the run CLI uses (src/experiment_bot/cli.py). When a hash
    # is given, load the EXACT structural card by content hash (hermetic
    # generation provenance) instead of the newest-by-mtime card.
    from experiment_bot.taskcard.loader import load_by_hash, load_latest
    if taskcard_sha256:
        return load_by_hash(taskcards_dir, label=label, sha256=taskcard_sha256)
    return load_latest(taskcards_dir, label=label)


def _combined_source(bundle) -> str:
    """Build one text blob from a SourceBundle's page HTML + source files.

    SourceBundle carries no single pre-combined field; this mirrors the
    concatenation pattern used by the Reasoner's Stage 1 prompt builder
    (src/experiment_bot/reasoner/stage1_structural.py::_build_stage1_prompt).
    """
    parts = [f"## Page HTML\n{bundle.description_text[:5000]}"]
    for fname, content in bundle.source_files.items():
        parts.append(f"## File: {fname}\n{content[:60000]}")
    return "\n\n".join(parts)


def extract_python_block(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if not m:
        raise ValueError("LLM reply contains no fenced Python block")
    return m.group(1)


def mechanical_facts(taskcard) -> dict:
    conditions: list[str] = []
    for stim in taskcard.stimuli or []:
        cond, _ = stim_condition_and_key(stim)
        if cond and cond not in conditions:
            conditions.append(cond)
    km = {k: v for k, v in ((taskcard.task_specific or {}).get("key_map") or {}).items()
          if isinstance(v, str) and v.lower() not in NON_LITERAL_KEY_SENTINELS}
    ti = getattr(taskcard.runtime, "trial_interrupt", None)
    # Real non-interrupt cards carry detection_condition == "" (empty string),
    # which must normalize to None: a truthy check, not an is-not-None check,
    # or the prompt gets a false interrupt note (final-review N2).
    interrupt_condition = (getattr(ti, "detection_condition", None) if ti else None) or None
    has_interrupt = interrupt_condition is not None
    return {"conditions": conditions, "key_map": km, "has_interrupt": has_interrupt,
            "interrupt_condition": interrupt_condition}


async def generate(url: str, label: str, client, taskcards_dir: str = "taskcards",
                   out_root: Path = Path("naive_programs"),
                   max_retries: int = 2, taskcard_sha256: str | None = None) -> Path:
    bundle = await scrape_experiment_source(url=url, hint="")
    taskcard = _load_structural_taskcard(label, taskcards_dir, taskcard_sha256=taskcard_sha256)
    tc_hash = _compute_taskcard_hash(taskcard.to_dict())
    facts = mechanical_facts(taskcard)
    prompt = _TEMPLATE.read_text().format(
        PAGE_SOURCE=_combined_source(bundle),
        CONDITIONS=", ".join(facts["conditions"]),
        KEY_MAP=json.dumps(facts["key_map"]) if facts["key_map"] else _EMPTY_KEY_MAP_NOTE,
        INTERRUPT_NOTE=_INTERRUPT_NOTE if facts["has_interrupt"] else "",
    )
    out_dir = Path(out_root) / label
    out_dir.mkdir(parents=True, exist_ok=True)

    last_failures: list[str] = []
    for attempt in range(1 + max_retries):
        user = prompt if attempt == 0 else (
            prompt + _RETRY_PREFIX
            + "\n".join(f"- {f}" for f in last_failures)
            + _RETRY_SUFFIX)
        reply = await client.complete(system="", user=user, max_tokens=16384)
        code = extract_python_block(reply.text)
        # Pure content hash — matches the content-addressing convention used
        # by sim_cli/cli/executor (behavior.provider.program_sha256). Writing
        # the same content twice is idempotent (same path). Retries that
        # re-emit byte-identical code must still each get an archived
        # transcript/simgate record (pre-registered rule: all attempts
        # archived), so those two filenames fall back to an attempt-numbered
        # suffix when the plain name is already taken by an earlier attempt.
        sha = hashlib.sha256(code.encode()).hexdigest()
        prog = out_dir / f"{sha}.py"
        prog.write_text(code)

        transcript_path = out_dir / f"{sha}.transcript.json"
        if transcript_path.exists():
            transcript_path = out_dir / f"{sha}.attempt{attempt}.transcript.json"
        transcript_path.write_text(json.dumps({
            "model": client.model, "attempt": attempt, "url": url,
            "label": label, "prompt": user, "response": reply.text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "taskcard_sha256": tc_hash,
        }, indent=2))
        # run_gate never raises on a broken program (simgate._trace wraps both
        # BehaviorSession construction and the per-trial loop) — a broken
        # program surfaces as report.passed is False, not an exception here.
        report = run_gate(prog, conditions=facts["conditions"],
                          key_map=facts["key_map"],
                          has_interrupt=facts["has_interrupt"],
                          interrupt_condition=facts["interrupt_condition"])
        simgate_path = out_dir / f"{sha}.simgate.json"
        if simgate_path.exists():
            simgate_path = out_dir / f"{sha}.attempt{attempt}.simgate.json"
        simgate_path.write_text(json.dumps(report.to_dict(), indent=2))
        if report.passed:
            return prog
        last_failures = report.failures
    raise RuntimeError(
        f"naive program for {label!r} failed the mechanical gate after "
        f"{1 + max_retries} attempts: {last_failures}")


@click.command()
@click.argument("url")
@click.option("--label", required=True)
@click.option("--model", default="claude-fable-5", show_default=True)
@click.option("--taskcards-dir", default="taskcards", show_default=True)
@click.option("--taskcard-sha256", default=None,
              help="Hermetic generation provenance: load the exact structural "
                   "TaskCard with this content hash (full or unambiguous prefix) "
                   "instead of the newest-by-mtime card.")
def main(url: str, label: str, model: str, taskcards_dir: str,
         taskcard_sha256: str | None):
    """Generate the SP21 naive-arm participant program for LABEL."""
    client = build_default_client(model)
    path = asyncio.run(generate(url, label, client, taskcards_dir=taskcards_dir,
                                taskcard_sha256=taskcard_sha256))
    click.echo(f"PASS -> {path}")
