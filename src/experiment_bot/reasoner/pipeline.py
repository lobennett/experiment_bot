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
from experiment_bot.reasoner.stage6_pilot import run_pilot
from experiment_bot.taskcard.types import ReasoningStep


class ReasonerPipeline:
    """Runs stages 1-6, persisting partial state after each so --resume works.

    Stages 1-5 produce the TaskCard's structural and behavioral fields.
    Stage 6 runs a thin driver-based smoke against the experiment URL via
    the SP10 TaskExecutor and writes a `pilot.md` alongside the TaskCard.
    Under SP10, iterative TaskCard refinement is no longer attempted — a
    DiagnosticDriver firing means a driver fix is the right action.

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
        pilot_max_retries: int = 1,
        taskcards_dir: Path | None = None,
    ):
        self._client = client
        self._work_dir = Path(work_dir)
        # Note: `run_pilot` here is the legacy ctor arg (bool flag toggling
        # whether to run Stage 6). The actual pilot function is imported
        # above; keep the attribute name `_run_pilot` to preserve external
        # tests / call sites.
        self._run_pilot = run_pilot
        self._pilot_headless = pilot_headless
        # Retained for backward CLI compatibility; SP10 pilot does not
        # retry (refinement is gone), so this is currently a no-op.
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
        for n in (5, 4, 3, 2, 1):
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

        # Initialize the reasoning chain (preserved from saved partial if present)
        partial.setdefault("_reasoning_chain", [])

        if start_after < 1:
            partial, step = await run_stage1(self._client, bundle)
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 1, partial)
        if start_after < 2:
            partial, step = await run_stage2(self._client, partial)
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 2, partial)
        if start_after < 3:
            partial, step = await run_stage3(self._client, partial)
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 3, partial)
        if start_after < 4:
            partial, step = await run_stage4(partial)
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 4, partial)
        if start_after < 5:
            partial, step = await run_stage5(self._client, partial)
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 5, partial)
        if self._run_pilot and start_after < 6:
            # SP10 thin smoke: build a temporary TaskCard from the partial,
            # let TaskExecutor drive the live session via its driver, then
            # write pilot.md alongside the TaskCard. No refinement loop.
            step = await self._run_pilot_stage(partial, bundle, label)
            partial.setdefault("_reasoning_chain", []).append(step.to_dict())
            self._save(label, 6, partial)
        return partial

    async def _run_pilot_stage(
        self, partial: dict, bundle: SourceBundle, label: str,
    ) -> ReasoningStep:
        """Build a temp TaskCard from `partial`, run the SP10 smoke, persist
        pilot.md, and return a ReasoningStep describing the outcome."""
        from experiment_bot.reasoner.normalize import normalize_partial
        from experiment_bot.taskcard.types import TaskCard

        # The partial may be missing the TaskCard envelope (schema_version,
        # produced_by, between_subject_jitter, etc.) — wrap defensively so
        # TaskCard.from_dict succeeds. The wrapped fields are placeholder-
        # only; the real envelope is written by cli.py at TaskCard save time.
        snapshot = normalize_partial(dict(partial))
        snapshot.setdefault("schema_version", "2.0")
        snapshot.setdefault("produced_by", {
            "model": "claude-opus-4-7", "prompt_sha256": "",
            "scraper_version": "1.0.0", "source_sha256": "",
            "timestamp": "", "taskcard_sha256": "",
        })
        snapshot.setdefault("reasoning_chain", [])
        snapshot.setdefault("pilot_validation", {})
        snapshot.setdefault("between_subject_jitter", {})
        snapshot.setdefault("response_distributions", {})
        snapshot.setdefault("temporal_effects", {})
        # _reasoning_chain (private) is internal pipeline state; strip
        # before TaskCard.from_dict since TaskCard expects only the
        # public `reasoning_chain` key.
        snapshot.pop("_reasoning_chain", None)
        try:
            tc = TaskCard.from_dict(snapshot)
        except Exception as e:
            # If the partial is too incomplete to even build a TaskCard,
            # record the failure but don't crash the pipeline.
            pilot_md = (
                f"# Pilot — {snapshot.get('task', {}).get('name', '?')}\n\n"
                f"Status: **FAIL**\n"
                f"Could not build TaskCard from partial: {e}\n"
            )
            self._write_pilot_md(label, pilot_md)
            return ReasoningStep(
                step="stage6_pilot",
                inference=f"Pilot skipped: partial -> TaskCard build failed ({e})",
                evidence_lines=[],
                confidence="low",
            )

        result = await run_pilot(
            tc, bundle.url, headless=self._pilot_headless,
        )
        self._write_pilot_md(label, result.pilot_md)
        inference = (
            f"Pilot {result.status}: trials={result.n_trials}"
            + (f", diagnostic={result.diagnostic_report_path}" if result.diagnostic_report_path else "")
            + (f", error={result.error}" if result.error else "")
        )
        return ReasoningStep(
            step="stage6_pilot",
            inference=inference,
            evidence_lines=[
                f"status={result.status}",
                f"n_trials={result.n_trials}",
                f"diagnostic_report_path={result.diagnostic_report_path}",
                f"error={result.error}",
            ],
            confidence="high" if result.status == "pass" else "low",
        )

    def _write_pilot_md(self, label: str, pilot_md: str) -> None:
        out_dir = self._taskcards_dir / label
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "pilot.md").write_text(pilot_md)
