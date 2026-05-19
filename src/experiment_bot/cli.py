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


# Module-level imports of the loader/sampler/executor so tests can patch them
from experiment_bot.taskcard.loader import load_latest
from experiment_bot.taskcard.sampling import sample_session_params
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.agent.session_agent import SessionAgent
from experiment_bot.llm.factory import build_default_client


def _build_session_agent() -> SessionAgent | None:
    """Try to build a SessionAgent backed by a haiku-class LLM client.

    Returns None when no client is available (no claude CLI on PATH and
    no ANTHROPIC_API_KEY) — the executor degrades to the static
    response_key resolution chain.
    """
    try:
        client = build_default_client(model="claude-haiku-4-5")
    except RuntimeError as e:
        logging.getLogger(__name__).warning(
            "Could not build LLM client for SessionAgent: %s. "
            "Proceeding without runtime key-mapping resolution.", e,
        )
        return None
    return SessionAgent(client=client)


async def _run_task(
    url: str,
    label: str,
    headless: bool,
    taskcards_dir: Path,
    seed: int | None,
    no_calibration: bool = False,
    skip_calibration_pass: bool = False,
) -> None:
    try:
        taskcard = load_latest(taskcards_dir, label=label)
    except FileNotFoundError as e:
        raise click.ClickException(
            f"No TaskCard found for label '{label}' in {taskcards_dir}. "
            f"Run `experiment-bot-reason {url} --label {label}` to generate one."
        ) from e

    # SP11 Phase 5b: drop-from-scope check. Refuse to run sessions for
    # paradigms the regeneration pipeline marked sp11_supported=False.
    sp11_supported = taskcard.task_specific.get("sp11_supported", True)
    if sp11_supported is False:
        raise click.ClickException(
            f"TaskCard for '{label}' is marked sp11_supported=False. "
            f"This paradigm failed the pilot-time alignment check during "
            f"Phase 5b regeneration. See docs/sp11-phase5b-deliverable.md "
            f"and the TaskCard's task_specific.sp11_unsupported_reason "
            f"field for details. To run anyway, edit the TaskCard "
            f"manually (the Phase 7 analysis will exclude unsupported "
            f"paradigms regardless)."
        )

    # SP11 Phase 5b: apply CLI calibration overrides.
    if no_calibration:
        # Pre-cal arm: run the pass for descriptive offset, but don't
        # apply to sampler. This is the experimental control for the
        # post-cal arm in Phase 7.
        taskcard.runtime.calibration_apply_to_sampler = False
    if skip_calibration_pass:
        # Test escape hatch: skip the calibration pass entirely.
        taskcard.runtime.calibration_run_pass = False

    # Draw session-level distributional parameters and stamp them into the
    # TaskCard's response_distributions[*].value so the executor's existing
    # ResponseSampler picks them up.
    if seed is None:
        seed = int.from_bytes(os.urandom(8), "big")
    sampled = sample_session_params(taskcard.to_dict(), seed=seed)
    for cond, params in sampled.items():
        if cond in taskcard.response_distributions:
            taskcard.response_distributions[cond].value.update(params)
    click.echo(f"Seed: {seed} | Sampled session parameters for {len(sampled)} conditions")

    session_agent = _build_session_agent()

    click.echo(f"Running task at {url}")
    executor = TaskExecutor(
        taskcard, headless=headless,
        seed=seed, session_params=sampled,
        session_agent=session_agent,
    )
    await executor.run(url)
    click.echo("Done!")


@click.command()
@click.argument("url")
@click.option("--label", required=True, help="TaskCard label (folder under taskcards/)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--taskcards-dir", default="taskcards",
              help="Directory containing TaskCard subfolders (default: taskcards/)")
@click.option("--seed", type=int, default=None,
              help="Random seed for session-level parameter sampling (default: random)")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
@click.option("--no-calibration", is_flag=True, default=False,
              help="Phase 7 pre-cal arm: run calibration pass for "
                   "descriptive offset, but do not apply to sampled RTs.")
@click.option("--skip-calibration-pass", is_flag=True, default=False,
              help="Test escape hatch: skip the calibration pass entirely. "
                   "Not for production use.")
def main(url: str, label: str, headless: bool, taskcards_dir: str,
         seed: int | None, verbose: bool, no_calibration: bool,
         skip_calibration_pass: bool):
    """experiment-bot: Execute a previously-reasoned TaskCard against URL.

    Use `experiment-bot-reason` to generate the TaskCard first.
    """
    _setup_logging(verbose)
    asyncio.run(_run_task(
        url, label, headless, Path(taskcards_dir), seed,
        no_calibration=no_calibration,
        skip_calibration_pass=skip_calibration_pass,
    ))
