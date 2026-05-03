from __future__ import annotations
import json
from pathlib import Path
from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import run_stage1
from experiment_bot.reasoner.stage2_behavioral import run_stage2
from experiment_bot.reasoner.stage3_citations import run_stage3
from experiment_bot.reasoner.stage4_doi_verify import run_stage4
from experiment_bot.reasoner.stage5_sensitivity import run_stage5


class ReasonerPipeline:
    """Runs stages 1-5, persisting partial state after each so --resume works."""

    def __init__(self, client: LLMClient, work_dir: Path):
        self._client = client
        self._work_dir = Path(work_dir)

    def _stage_path(self, label: str, stage_n: int) -> Path:
        return self._work_dir / label / f"stage{stage_n}.json"

    def _save(self, label: str, stage_n: int, partial: dict) -> None:
        path = self._stage_path(label, stage_n)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(partial, indent=2))

    def _resume_from(self, label: str) -> tuple[int, dict] | None:
        for n in (4, 3, 2, 1):
            p = self._stage_path(label, n)
            if p.exists():
                return n, json.loads(p.read_text())
        return None

    async def run(self, bundle: SourceBundle, label: str, resume: bool = False) -> dict:
        partial: dict = {}
        start_after = 0

        if resume:
            res = self._resume_from(label)
            if res is not None:
                start_after, partial = res

        if start_after < 1:
            partial = await run_stage1(self._client, bundle)
            self._save(label, 1, partial)
        if start_after < 2:
            partial = await run_stage2(self._client, partial)
            self._save(label, 2, partial)
        if start_after < 3:
            partial = await run_stage3(self._client, partial)
            self._save(label, 3, partial)
        if start_after < 4:
            partial = await run_stage4(partial)
            self._save(label, 4, partial)
        if start_after < 5:
            partial = await run_stage5(self._client, partial)
            self._save(label, 5, partial)
        return partial
