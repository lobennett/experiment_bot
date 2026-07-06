from __future__ import annotations
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import click

from experiment_bot.core.config import SourceBundle
from experiment_bot.core.scraper import scrape_experiment_source
from experiment_bot.llm.factory import build_default_client
from experiment_bot.reasoner.pipeline import ReasonerPipeline
from experiment_bot.taskcard.loader import save_taskcard
from experiment_bot.taskcard.types import TaskCard

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.md"


@click.command()
@click.argument("url")
@click.option("--label", required=True, help="Cache label for this task")
@click.option("--hint", default="", help="Optional paradigm hint")
@click.option("--taskcards-dir", default="taskcards", help="Where to write TaskCards")
@click.option("--work-dir", default=".reasoner_work", help="Where stage partials live")
@click.option("--resume", is_flag=True, default=False,
              help="Resume from latest saved stage if present")
@click.option("--skip-pilot", is_flag=True, default=False,
              help="Skip Stage 6 (live-DOM pilot validation). Useful for "
                   "fast iteration without launching a browser.")
@click.option("--pilot-headed", is_flag=True, default=False,
              help="Run the Stage 6 pilot with a visible browser window "
                   "(default: headless).")
@click.option("--pilot-max-retries", type=int, default=11,
              help="Max refinement retries when Stage 6 pilot fails (default: "
                   "11 → 12 total attempts). Stuck-detection aborts early if "
                   "two consecutive attempts hit the same DOM state.")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(url: str, label: str, hint: str, taskcards_dir: str, work_dir: str,
         resume: bool, skip_pilot: bool, pilot_headed: bool,
         pilot_max_retries: int, verbose: bool):
    """Run the Reasoner against URL and produce a structural TaskCard.

    Stage 1 produces structural fields (navigation, stimulus detection,
    keys, runtime) from source code. Stage 6 (pilot) validates the TaskCard
    against the live URL via Playwright and refines on failure. Use
    --skip-pilot to disable Stage 6. Behavior comes from a generated
    participant program (experiment-bot-naive-gen), not from the card.
    """
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(_run(
        url, label, hint, Path(taskcards_dir), Path(work_dir), resume,
        skip_pilot=skip_pilot, pilot_headed=pilot_headed,
        pilot_max_retries=pilot_max_retries,
    ))


async def _run(url, label, hint, taskcards_dir, work_dir, resume,
               *, skip_pilot=False, pilot_headed=False, pilot_max_retries=11):
    from experiment_bot.reasoner.normalize import normalize_partial
    bundle = await scrape_experiment_source(url=url, hint=hint)
    client = build_default_client()
    pipeline = ReasonerPipeline(
        client=client, work_dir=work_dir,
        run_pilot=not skip_pilot,
        pilot_headless=not pilot_headed,
        pilot_max_retries=pilot_max_retries,
        taskcards_dir=taskcards_dir,
    )
    final = await pipeline.run(bundle, label=label, resume=resume)
    if "schema_version" not in final:
        final = _wrap_for_taskcard(final, url, bundle=bundle, llm_client=client)
    final = normalize_partial(final)
    # Promote internal _reasoning_chain to the public reasoning_chain field
    if "_reasoning_chain" in final:
        final["reasoning_chain"] = final.pop("_reasoning_chain")
    # Structural-only pipeline: no stage produces behavioral fields. Emit
    # empty/minimal defaults so TaskCard.from_dict loads the card; the
    # naive executor path never reads them.
    final.setdefault("performance", {"accuracy": {}, "omission_rate": {}})
    final.setdefault("response_distributions", {})
    final.setdefault("temporal_effects", {})
    final.setdefault("between_subject_jitter", {})
    tc = TaskCard.from_dict(final)
    out = save_taskcard(tc, taskcards_dir, label=label)
    click.echo(f"TaskCard written: {out}")


def _wrap_for_taskcard(
    partial: dict,
    url: str,
    *,
    bundle: SourceBundle | None = None,
    llm_client=None,
) -> dict:
    """Add the schema_version, produced_by, and reasoning_chain envelope.

    prompt_sha256: sha256 of the system prompt (prompts/system.md).
    source_sha256: sha256 of the concatenated source_files content from the
        SourceBundle (sorted by filename for determinism). Falls back to
        empty string only when no bundle is provided.
    model: taken from the live client's .model property (never a hardcoded literal).
    """
    partial.setdefault("schema_version", "2.0")
    if "produced_by" not in partial:
        # Compute prompt_sha256 from the system prompt file
        try:
            prompt_text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
            prompt_sha256 = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        except OSError:
            prompt_sha256 = ""

        # Compute source_sha256 from the SourceBundle's concatenated source files
        if bundle is not None and bundle.source_files:
            source_concat = "".join(
                content for _, content in sorted(bundle.source_files.items())
            ).encode("utf-8")
            source_sha256 = hashlib.sha256(source_concat).hexdigest()
        else:
            source_sha256 = ""

        # Resolve model from live client
        if llm_client is not None and hasattr(llm_client, "model"):
            model_id = llm_client.model
        elif llm_client is not None and hasattr(llm_client, "_model"):
            model_id = llm_client._model  # noqa: SLF001  # fallback for legacy objects
        else:
            from experiment_bot.llm.models import DEFAULT_MODEL
            model_id = DEFAULT_MODEL

        partial["produced_by"] = {
            "model": model_id,
            "prompt_sha256": prompt_sha256,
            "scraper_version": "1.0.0",
            "source_sha256": source_sha256,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "taskcard_sha256": "",
        }
    partial.setdefault("reasoning_chain", [])
    partial.setdefault("pilot_validation", {})
    return partial
