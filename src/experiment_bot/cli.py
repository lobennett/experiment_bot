from __future__ import annotations

import asyncio
import logging
import os

import click

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_task(
    platform_name: str,
    task_id: str,
    headless: bool,
    regenerate: bool,
    rt_mean: float | None,
    accuracy: float | None,
) -> None:
    from anthropic import AsyncAnthropic

    from experiment_bot.core.analyzer import Analyzer
    from experiment_bot.core.cache import ConfigCache
    from experiment_bot.core.executor import TaskExecutor
    from experiment_bot.platforms.registry import get_platform

    platform = get_platform(platform_name)

    # Check cache
    cache = ConfigCache()
    config = None if regenerate else cache.load(platform_name, task_id)

    if config is None:
        # Download source and analyze
        click.echo(f"Downloading source code for {platform_name}/{task_id}...")
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = await platform.download_source(task_id, Path(tmpdir))

        click.echo("Analyzing task with Claude Opus 4.6...")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise click.ClickException("ANTHROPIC_API_KEY environment variable not set")

        client = AsyncAnthropic(api_key=api_key)
        analyzer = Analyzer(client=client)
        config = await analyzer.analyze(bundle)

        # Apply overrides
        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

        # Cache
        cache.save(platform_name, task_id, config)
        click.echo(f"Config generated and cached.")
    else:
        click.echo(f"Using cached config for {platform_name}/{task_id}")
        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

    # Apply between-subject jitter (fresh random seed per session)
    import numpy as np
    from experiment_bot.core.distributions import jitter_distributions
    config = jitter_distributions(config, np.random.default_rng())
    click.echo("Applied between-subject parameter jitter")

    # Run
    task_url = await platform.get_task_url(task_id)
    click.echo(f"Running task at {task_url}")
    executor = TaskExecutor(config, platform_name=platform_name, headless=headless)
    await executor.run(task_url, platform)
    click.echo("Done!")


@click.group()
def main():
    """experiment-bot: Execute human-like behavior on cognitive tasks."""
    pass


@main.command()
@click.option("--task", required=True, help="Task ID (e.g., 9 for stop signal)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--regenerate-config", is_flag=True, default=False, help="Force regenerate config via API")
@click.option("--rt-mean", type=float, default=None, help="Override mean RT (mu) in ms")
@click.option("--accuracy", type=float, default=None, help="Override go accuracy (0-1)")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
def expfactory(task: str, headless: bool, regenerate_config: bool, rt_mean: float | None, accuracy: float | None, verbose: bool):
    """Run a task from the Experiment Factory platform."""
    _setup_logging(verbose)
    asyncio.run(_run_task("expfactory", task, headless, regenerate_config, rt_mean, accuracy))


@main.command()
@click.option("--task", required=True, help="Task ID (e.g., stopsignal)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--regenerate-config", is_flag=True, default=False, help="Force regenerate config via API")
@click.option("--rt-mean", type=float, default=None, help="Override mean RT (mu) in ms")
@click.option("--accuracy", type=float, default=None, help="Override go accuracy (0-1)")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
def psytoolkit(task: str, headless: bool, regenerate_config: bool, rt_mean: float | None, accuracy: float | None, verbose: bool):
    """Run a task from the PsyToolkit platform."""
    _setup_logging(verbose)
    asyncio.run(_run_task("psytoolkit", task, headless, regenerate_config, rt_mean, accuracy))
