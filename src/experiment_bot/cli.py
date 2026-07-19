from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import click


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


# Module-level imports of the loader/executor so tests can patch them
from experiment_bot.taskcard.loader import load_latest, load_by_hash
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.llm.factory import build_default_client
from experiment_bot.behavior.provider import (
    BehaviorSession, NON_LITERAL_KEY_SENTINELS, load_program, resolve_program,
    stim_condition_and_key,
)


def _available_keys_from_taskcard(taskcard) -> tuple[str, ...]:
    """Available response keys for a BehaviorSession: key_map values plus
    per-stimulus static response keys, excluding withhold sentinels/None and
    the "dynamic"/"dynamic_mapping" sentinels the executor resolves per-trial
    via JS rather than from this static map (see NON_LITERAL_KEY_SENTINELS).
    """
    keys: set[str] = set()
    km = (taskcard.task_specific or {}).get("key_map") or {}
    keys.update(v for v in km.values() if isinstance(v, str))
    for stim in taskcard.stimuli or []:
        _, k = stim_condition_and_key(stim)
        if isinstance(k, str):
            keys.add(k)
    return tuple(sorted(
        k for k in keys
        if k and k.lower() not in NON_LITERAL_KEY_SENTINELS
    ))


async def _run_task(
    url: str,
    label: str,
    headless: bool,
    taskcards_dir: Path,
    seed: int | None,
    no_llm_client: bool = False,
    keep_open: bool = False,
    taskcard_sha256: str | None = None,
    calibrate: bool = True,
    behavior_program: str = "",
    stealth: bool = False,
) -> None:
    try:
        # Hermetic replay: when a hash is given, load the EXACT card a past
        # session recorded in its run_metadata.json (taskcard_sha256) rather
        # than the newest-by-mtime card. Pair with --seed to reproduce a run.
        if taskcard_sha256:
            taskcard = load_by_hash(taskcards_dir, label=label, sha256=taskcard_sha256)
        else:
            taskcard = load_latest(taskcards_dir, label=label)
    except FileNotFoundError as e:
        raise click.ClickException(
            f"No TaskCard found for label '{label}' in {taskcards_dir}"
            + (f" with content hash '{taskcard_sha256}'." if taskcard_sha256 else
               f". Run `experiment-bot-reason {url} --label {label}` to generate one.")
        ) from e

    if seed is None:
        seed = int.from_bytes(os.urandom(8), "big")

    # The generated participant program IS the behavioral layer; the seed
    # selects the participant it instantiates.
    prog_path = resolve_program(behavior_program)
    provider = BehaviorSession(
        load_program(prog_path), seed=seed,
        available_keys=_available_keys_from_taskcard(taskcard),
        program_path=prog_path,
    )
    click.echo(f"Naive arm: program {prog_path} (sha {provider.program_sha256[:8]})")

    click.echo(f"Running task at {url}")
    llm_client = None if no_llm_client else build_default_client()
    executor = TaskExecutor(
        taskcard, headless=headless, stealth=stealth,
        seed=seed,
        llm_client=llm_client,
        keep_open=keep_open,
        calibrate=calibrate,
        behavior_provider=provider,
    )
    await executor.run(url)
    click.echo("Done!")


@click.command()
@click.argument("url")
@click.option("--label", required=True, help="TaskCard label (folder under taskcards/)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--stealth", is_flag=True, default=False,
              help="Present the browser as a real participant's: headful, real "
                   "Chrome (falls back to bundled Chromium), GPU renderer, no "
                   "WebDriver flag. Makes a bot-detector score behaviour, not "
                   "the automation harness. Forces headful (ignores --headless).")
@click.option("--taskcards-dir", default="taskcards",
              help="Directory containing TaskCard subfolders (default: taskcards/)")
@click.option("--seed", type=int, default=None,
              help="Seed selecting the behavior program's participant (default: random)")
@click.option("--taskcard-sha256", default=None,
              help="Hermetic replay: load the exact TaskCard with this content hash "
                   "(full or unambiguous prefix), e.g. the taskcard_sha256 from a past "
                   "session's run_metadata.json, instead of the newest-by-mtime card. "
                   "Pair with --seed to reproduce that session.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
@click.option("--no-llm-client", is_flag=True, default=False,
              help="Disable LLM client (skips adaptive nav; for deterministic / no-LLM runs)")
@click.option("--keep-open", is_flag=True, default=False,
              help="Leave the browser open after the session ends (inspect final "
                   "state). Close the window or Ctrl+C the process to exit. "
                   "Best with non-headless (omit --headless).")
@click.option("--no-calibration", is_flag=True, default=False,
              help="Skip the startup keypress-latency calibration pass. The pass is "
                   "behaviorally inert on supported platforms (reports too_few_events) "
                   "and on platforms with no pre-trial idle window (e.g. cognition.run) "
                   "its runtime is recorded as the first trial's RT, corrupting it. "
                   "Recommended for cognition.run and any single-block task.")
@click.option("--behavior-program", required=True,
              help="Path (or <label>/<hash-prefix> under naive_programs/) of "
                   "a generated participant program. The program IS the "
                   "behavioral layer; navigation/detection/capture come from "
                   "the TaskCard as usual.")
def main(url: str, label: str, headless: bool, stealth: bool, taskcards_dir: str,
         seed: int | None, verbose: bool, no_llm_client: bool, keep_open: bool,
         taskcard_sha256: str | None, no_calibration: bool,
         behavior_program: str):
    """experiment-bot: Execute a previously-reasoned TaskCard against URL.

    Use `experiment-bot-reason` to generate the TaskCard first.
    """
    _setup_logging(verbose)
    asyncio.run(_run_task(
        url, label, headless, Path(taskcards_dir), seed, no_llm_client, keep_open,
        taskcard_sha256=taskcard_sha256, calibrate=not no_calibration,
        behavior_program=behavior_program, stealth=stealth,
    ))
