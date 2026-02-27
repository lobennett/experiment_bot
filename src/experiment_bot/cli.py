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
    url: str,
    hint: str,
    label: str,
    headless: bool,
    regenerate: bool,
    rt_mean: float | None,
    accuracy: float | None,
) -> None:
    from anthropic import AsyncAnthropic

    from experiment_bot.core.analyzer import Analyzer
    from experiment_bot.core.cache import ConfigCache
    from experiment_bot.core.executor import TaskExecutor
    from experiment_bot.core.scraper import scrape_experiment_source

    cache = ConfigCache()
    config = None if regenerate else cache.load(url, label)

    if config is None:
        click.echo(f"Scraping source from {url}...")
        bundle = await scrape_experiment_source(url=url, hint=hint)

        click.echo("Analyzing task with Claude...")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise click.ClickException("ANTHROPIC_API_KEY environment variable not set")

        client = AsyncAnthropic(api_key=api_key)
        analyzer = Analyzer(client=client)
        config = await analyzer.analyze(bundle)

        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

        cache.save(url, config, label)
        click.echo("Config generated and cached.")
    else:
        click.echo("Using cached config.")
        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

    import numpy as np
    from experiment_bot.core.distributions import jitter_distributions
    config = jitter_distributions(config, np.random.default_rng())
    click.echo("Applied between-subject parameter jitter")

    click.echo(f"Running task at {url}")
    executor = TaskExecutor(config, headless=headless)
    await executor.run(url)
    click.echo("Done!")


@click.command()
@click.argument("url")
@click.option("--hint", default="", help="Hint about the task (e.g., 'stop signal task')")
@click.option("--label", default="", help="Cache label (default: URL hash)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--regenerate-config", is_flag=True, default=False, help="Force regenerate config")
@click.option("--rt-mean", type=float, default=None, help="Override mean RT (mu) in ms")
@click.option("--accuracy", type=float, default=None, help="Override go accuracy (0-1)")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
def main(url: str, hint: str, label: str, headless: bool, regenerate_config: bool, rt_mean: float | None, accuracy: float | None, verbose: bool):
    """experiment-bot: Execute human-like behavior on web-based cognitive tasks.

    URL is the experiment page to complete.
    """
    _setup_logging(verbose)
    asyncio.run(_run_task(url, hint, label, headless, regenerate_config, rt_mean, accuracy))
