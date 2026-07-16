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
async def test_pipeline_runs_stage1(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)
    with patch("experiment_bot.reasoner.pipeline.run_stage1",
               new=AsyncMock(return_value=(
                   {"task": {"name": "x"}, "stimuli": [],
                    "navigation": {"phases": []}, "runtime": {},
                    "task_specific": {}, "performance": {"accuracy": {"d": 0.9}}},
                   ReasoningStep(step="stage1_structural", inference="x")
               ))):
        result = await pipe.run(bundle, label="test")
    assert result["task"]["name"] == "x"


@pytest.mark.asyncio
async def test_pipeline_writes_partial_after_stage1(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)

    async def stage1(client, b):
        return {"_stage": 1}, ReasoningStep(step="stage1_structural", inference="x")

    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1):
        await pipe.run(bundle, label="test")
    saved = json.loads((tmp_path / "work" / "test" / "stage1.json").read_text())
    assert saved["_stage"] == 1


@pytest.mark.asyncio
async def test_pipeline_resumes_from_stage1(tmp_path, bundle):
    """A saved stage1.json partial is reused: run_stage1 must NOT re-fire."""
    fake = AsyncMock()
    work = tmp_path / "work" / "test"
    work.mkdir(parents=True)
    (work / "stage1.json").write_text('{"_stage": 1}')

    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)
    stage1 = AsyncMock(side_effect=AssertionError("stage1 must not re-run on resume"))
    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1):
        result = await pipe.run(bundle, label="test", resume=True)
    assert result["_stage"] == 1


@pytest.mark.asyncio
async def test_pipeline_resume_with_no_partial_starts_fresh(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=False)

    async def stage1(client, b):
        return {"fresh": True}, ReasoningStep(step="stage1_structural", inference="x")

    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1):
        result = await pipe.run(bundle, label="test", resume=True)
    assert result["fresh"] is True


@pytest.mark.asyncio
async def test_pipeline_accumulates_reasoning_chain(tmp_path, bundle):
    """The pipeline collects one ReasoningStep per stage into _reasoning_chain."""
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work", run_pilot=True)

    async def stage1(client, b):
        return {"_stage": 1}, ReasoningStep(step="stage1_structural", inference="s1")

    async def stage6(client, partial, bundle, **kwargs):
        return {**partial, "_stage": 6}, ReasoningStep(step="stage6_pilot", inference="s6")

    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1), \
         patch("experiment_bot.reasoner.pipeline.run_stage6", new=stage6):
        result = await pipe.run(bundle, label="test")
    chain = result.get("_reasoning_chain", [])
    assert [s["step"] for s in chain] == ["stage1_structural", "stage6_pilot"]
