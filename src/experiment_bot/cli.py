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


async def _run_task(
    url: str,
    label: str,
    headless: bool,
    taskcards_dir: Path,
    seed: int | None,
) -> None:
    try:
        taskcard = load_latest(taskcards_dir, label=label)
    except FileNotFoundError as e:
        raise click.ClickException(
            f"No TaskCard found for label '{label}' in {taskcards_dir}. "
            f"Run `experiment-bot-reason {url} --label {label}` to generate one."
        ) from e

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

    click.echo(f"Running task at {url}")
    executor = TaskExecutor(taskcard, headless=headless)
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
def main(url: str, label: str, headless: bool, taskcards_dir: str,
         seed: int | None, verbose: bool):
    """experiment-bot: Execute a previously-reasoned TaskCard against URL.

    Use `experiment-bot-reason` to generate the TaskCard first.
    """
    _setup_logging(verbose)
    asyncio.run(_run_task(url, label, headless, Path(taskcards_dir), seed))
