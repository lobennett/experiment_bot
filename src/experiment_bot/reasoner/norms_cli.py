from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path
import click

from experiment_bot.llm.factory import build_default_client
from experiment_bot.reasoner.norms_extractor import extract_norms


@click.command()
@click.option("--paradigm-class", required=True, help="Paradigm class (conflict, interrupt, ...)")
@click.option("--norms-dir", default="norms", help="Directory to write norms JSON to")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(paradigm_class: str, norms_dir: str, verbose: bool):
    """Extract canonical norms for a paradigm class and write `norms/{class}.json`."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(_run(paradigm_class, Path(norms_dir)))


async def _run(paradigm_class: str, norms_dir: Path):
    client = build_default_client()
    payload = await extract_norms(paradigm_class, llm_client=client)
    norms_dir.mkdir(parents=True, exist_ok=True)
    out_path = norms_dir / f"{paradigm_class}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    click.echo(f"Norms written: {out_path}")
