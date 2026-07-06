from __future__ import annotations
import json
from pathlib import Path
from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import run_stage1
from experiment_bot.reasoner.stage6_pilot import run_stage6


class ReasonerPipeline:
    """Runs the structural stages (1 and 6), persisting partial state after
    each so --resume works.

    Stage 1 produces the TaskCard's structural fields (task, stimuli,
    navigation, runtime, task_specific, performance). Stage 6 runs a
    live-DOM pilot against the experiment URL via Playwright and either
    passes (saving pilot diagnostic) or refines the structural fields and
    re-pilots (up to `pilot_max_retries`).

    Accumulates a reasoning_chain across stages, stored under the partial's
    `_reasoning_chain` key (preserved on disk for --resume). The CLI later
    promotes this to `reasoning_chain` (no underscore) when constructing
    the TaskCard.
    """

    def __init__(
        self, client: LLMClient, work_dir: Path,
        *,
        run_pilot: bool = True,
        pilot_headless: bool = True,
        pilot_max_retries: int = 11,
        taskcards_dir: Path | None = None,
    ):
        self._client = client
        self._work_dir = Path(work_dir)
        self._run_pilot = run_pilot
        self._pilot_headless = pilot_headless
        self._pilot_max_retries = pilot_max_retries
        # Where to save pilot.md alongside the TaskCard. Defaults to "taskcards"
        # alongside the work dir's parent (matches the CLI default).
        self._taskcards_dir = Path(taskcards_dir) if taskcards_dir else Path("taskcards")

    def _stage_path(self, label: str, stage_n: int) -> Path:
        return self._work_dir / label / f"stage{stage_n}.json"

    def _save(self, label: str, stage_n: int, partial: dict) -> None:
        path = self._stage_path(label, stage_n)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(partial, indent=2))

    def _resume_from(self, label: str) -> tuple[int, dict] | None:
        p = self._stage_path(label, 1)
        if p.exists():
            return 1, json.loads(p.read_text())
        return None

    async def run(self, bundle: SourceBundle, label: str, resume: bool = False) -> dict:
        partial: dict = {}
        start_after = 0

        if resume:
            res = self._resume_from(label)
            if res is not None:
                start_after, partial = res

        # Initialize the reasoning chain (preserved from saved partial if present)
        partial.setdefault("_reasoning_chain", [])

        if start_after < 1:
            partial, step = await run_stage1(self._client, bundle)
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 1, partial)
        if self._run_pilot:
            # Persist refinements back to the resume point so a Stage 6
            # hard-fail can be picked up by --resume from the refined
            # state rather than re-walking refinements from scratch.
            partial, step = await run_stage6(
                self._client, partial, bundle,
                label=label,
                taskcards_dir=self._taskcards_dir,
                headless=self._pilot_headless,
                max_retries=self._pilot_max_retries,
                save_partial=lambda p: self._save(label, 1, p),
            )
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 6, partial)
        return partial
