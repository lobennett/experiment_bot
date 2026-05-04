from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import click

from experiment_bot.core.scraper import scrape_experiment_source
from experiment_bot.llm.factory import build_default_client
from experiment_bot.reasoner.pipeline import ReasonerPipeline
from experiment_bot.taskcard.loader import save_taskcard
from experiment_bot.taskcard.types import TaskCard


@click.command()
@click.argument("url")
@click.option("--label", required=True, help="Cache label for this task")
@click.option("--hint", default="", help="Optional paradigm hint")
@click.option("--taskcards-dir", default="taskcards", help="Where to write TaskCards")
@click.option("--work-dir", default=".reasoner_work", help="Where stage partials live")
@click.option("--resume", is_flag=True, default=False,
              help="Resume from latest saved stage if present")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(url: str, label: str, hint: str, taskcards_dir: str, work_dir: str,
         resume: bool, verbose: bool):
    """Run the 5-stage Reasoner against URL and produce a TaskCard."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(_run(url, label, hint, Path(taskcards_dir), Path(work_dir), resume))


async def _run(url, label, hint, taskcards_dir, work_dir, resume):
    from experiment_bot.reasoner.normalize import normalize_partial
    bundle = await scrape_experiment_source(url=url, hint=hint)
    client = build_default_client()
    pipeline = ReasonerPipeline(client=client, work_dir=work_dir)
    final = await pipeline.run(bundle, label=label, resume=resume)
    if "schema_version" not in final:
        final = _wrap_for_taskcard(final, url)
    final = normalize_partial(final)
    # Promote internal _reasoning_chain to the public reasoning_chain field
    if "_reasoning_chain" in final:
        final["reasoning_chain"] = final.pop("_reasoning_chain")
    tc = TaskCard.from_dict(final)
    out = save_taskcard(tc, taskcards_dir, label=label)
    click.echo(f"TaskCard written: {out}")


def _wrap_for_taskcard(partial: dict, url: str) -> dict:
    """Add the schema_version, produced_by, and reasoning_chain envelope."""
    partial.setdefault("schema_version", "2.0")
    partial.setdefault("produced_by", {
        "model": "claude-opus-4-7",
        "prompt_sha256": "",
        "scraper_version": "1.0.0",
        "source_sha256": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "taskcard_sha256": "",
    })
    partial.setdefault("reasoning_chain", [])
    partial.setdefault("pilot_validation", {})
    return partial
