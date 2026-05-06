import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from experiment_bot.reasoner.pipeline import ReasonerPipeline
from experiment_bot.core.config import SourceBundle
from experiment_bot.taskcard.types import ReasoningStep


@pytest.fixture
def bundle():
    return SourceBundle(url="http://example.com", source_files={"main.js": "//"},
                        description_text="<html></html>")


@pytest.mark.asyncio
async def test_pipeline_runs_all_5_stages(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)
    with patch("experiment_bot.reasoner.pipeline.run_stage1",
               new=AsyncMock(return_value=(
                   {"task": {"name": "x"}, "stimuli": [],
                    "navigation": {"phases": []}, "runtime": {},
                    "task_specific": {}, "performance": {"accuracy": {"d": 0.9}}},
                   ReasoningStep(step="stage1_structural", inference="x")
               ))), \
         patch("experiment_bot.reasoner.pipeline.run_stage2",
               new=AsyncMock(side_effect=lambda client, partial: (
                   {**partial,
                    "response_distributions": {"d": {"value": {"mu": 500}, "rationale": ""}},
                    "temporal_effects": {}, "between_subject_jitter": {}},
                   ReasoningStep(step="stage2_behavioral", inference="x")
               ))), \
         patch("experiment_bot.reasoner.pipeline.run_stage3",
               new=AsyncMock(side_effect=lambda client, partial: (
                   partial,
                   ReasoningStep(step="stage3_citations", inference="x")
               ))), \
         patch("experiment_bot.reasoner.pipeline.run_stage4",
               new=AsyncMock(side_effect=lambda partial: (
                   partial,
                   ReasoningStep(step="stage4_doi_verify", inference="x")
               ))), \
         patch("experiment_bot.reasoner.pipeline.run_stage5",
               new=AsyncMock(side_effect=lambda client, partial: (
                   partial,
                   ReasoningStep(step="stage5_sensitivity", inference="x")
               ))):
        result = await pipe.run(bundle, label="test")
    assert result["task"]["name"] == "x"


@pytest.mark.asyncio
async def test_pipeline_writes_partial_after_each_stage(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)

    async def stage1(client, b):
        return {"_stage": 1}, ReasoningStep(step="stage1_structural", inference="x")

    async def stage2(client, p):
        return {**p, "_stage": 2}, ReasoningStep(step="stage2_behavioral", inference="x")

    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1), \
         patch("experiment_bot.reasoner.pipeline.run_stage2", new=stage2), \
         patch("experiment_bot.reasoner.pipeline.run_stage3", new=AsyncMock(side_effect=Exception("boom"))):
        with pytest.raises(Exception, match="boom"):
            await pipe.run(bundle, label="test")
    saved = json.loads((tmp_path / "work" / "test" / "stage2.json").read_text())
    assert saved["_stage"] == 2


@pytest.mark.asyncio
async def test_pipeline_resumes_from_stage(tmp_path, bundle):
    fake = AsyncMock()
    work = tmp_path / "work" / "test"
    work.mkdir(parents=True)
    (work / "stage2.json").write_text('{"_stage": 2}')

    async def stage3(client, p):
        return {**p, "_stage": 3}, ReasoningStep(step="stage3_citations", inference="x")

    async def stage4(p):
        return {**p, "_stage": 4}, ReasoningStep(step="stage4_doi_verify", inference="x")

    async def stage5(client, p):
        return {**p, "_stage": 5}, ReasoningStep(step="stage5_sensitivity", inference="x")

    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)
    with patch("experiment_bot.reasoner.pipeline.run_stage3", new=stage3), \
         patch("experiment_bot.reasoner.pipeline.run_stage4", new=stage4), \
         patch("experiment_bot.reasoner.pipeline.run_stage5", new=stage5):
        result = await pipe.run(bundle, label="test", resume=True)
    assert result["_stage"] == 5


@pytest.mark.asyncio
async def test_pipeline_resume_with_no_partial_starts_fresh(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)

    async def stage1(client, b):
        return {"fresh": True}, ReasoningStep(step="stage1_structural", inference="x")

    async def stage2(client, p):
        return {**p, "_stage": 2}, ReasoningStep(step="stage2_behavioral", inference="x")

    async def stage3(client, p):
        return {**p, "_stage": 3}, ReasoningStep(step="stage3_citations", inference="x")

    async def stage4(p):
        return {**p, "_stage": 4}, ReasoningStep(step="stage4_doi_verify", inference="x")

    async def stage5(client, p):
        return {**p, "_stage": 5}, ReasoningStep(step="stage5_sensitivity", inference="x")

    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1), \
         patch("experiment_bot.reasoner.pipeline.run_stage2", new=stage2), \
         patch("experiment_bot.reasoner.pipeline.run_stage3", new=stage3), \
         patch("experiment_bot.reasoner.pipeline.run_stage4", new=stage4), \
         patch("experiment_bot.reasoner.pipeline.run_stage5", new=stage5):
        result = await pipe.run(bundle, label="test", resume=True)
    assert result["fresh"] is True
    assert result["_stage"] == 5


@pytest.mark.asyncio
async def test_pipeline_accumulates_reasoning_chain(tmp_path, bundle):
    """The pipeline collects one ReasoningStep per stage into _reasoning_chain."""
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)

    async def stage1(client, b):
        return {"_stage": 1}, ReasoningStep(step="stage1_structural", inference="s1")

    async def stage2(client, p):
        return {**p, "_stage": 2}, ReasoningStep(step="stage2_behavioral", inference="s2")

    async def stage3(client, p):
        return {**p, "_stage": 3}, ReasoningStep(step="stage3_citations", inference="s3")

    async def stage4(p):
        return {**p, "_stage": 4}, ReasoningStep(step="stage4_doi_verify", inference="s4")

    async def stage5(client, p):
        return {**p, "_stage": 5}, ReasoningStep(step="stage5_sensitivity", inference="s5")

    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1), \
         patch("experiment_bot.reasoner.pipeline.run_stage2", new=stage2), \
         patch("experiment_bot.reasoner.pipeline.run_stage3", new=stage3), \
         patch("experiment_bot.reasoner.pipeline.run_stage4", new=stage4), \
         patch("experiment_bot.reasoner.pipeline.run_stage5", new=stage5):
        result = await pipe.run(bundle, label="test")
    chain = result.get("_reasoning_chain", [])
    assert len(chain) == 5
    assert [s["step"] for s in chain] == [
        "stage1_structural", "stage2_behavioral", "stage3_citations",
        "stage4_doi_verify", "stage5_sensitivity",
    ]
