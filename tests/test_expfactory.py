import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from experiment_bot.platforms.expfactory import ExpFactoryPlatform


def test_get_task_url():
    platform = ExpFactoryPlatform()
    import asyncio
    url = asyncio.run(platform.get_task_url("9"))
    assert url == "https://deploy.expfactory.org/preview/9/"


def test_parse_script_tags():
    """Extract experiment.js and other script paths from HTML."""
    html = '''
    <html><head>
    <script src="/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/experiment.js"></script>
    <script src="/static/js/jspsych.js"></script>
    <link rel="stylesheet" href="/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/style.css">
    </head></html>
    '''
    platform = ExpFactoryPlatform()
    scripts, styles = platform.parse_resource_tags(html)
    assert any("experiment.js" in s for s in scripts)
    assert any("style.css" in s for s in styles)


def test_build_download_url():
    platform = ExpFactoryPlatform()
    path = "/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/experiment.js"
    url = platform.build_download_url(path)
    assert url == "https://deploy.expfactory.org/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/experiment.js"


@pytest.mark.asyncio
async def test_detect_task_phase_context_destroyed_returns_complete():
    """When page navigation destroys context, detect_task_phase returns COMPLETE."""
    from experiment_bot.core.config import TaskPhase
    platform = ExpFactoryPlatform()
    page = AsyncMock()
    page.query_selector = AsyncMock(side_effect=Exception("Execution context was destroyed"))
    result = await platform.detect_task_phase(page)
    assert result == TaskPhase.COMPLETE


@pytest.mark.asyncio
async def test_detect_task_phase_completion_text():
    """When display element contains completion keywords, returns COMPLETE."""
    from experiment_bot.core.config import TaskPhase
    platform = ExpFactoryPlatform()

    for keyword in ["finished", "complete", "done", "thank you", "the end"]:
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.evaluate = AsyncMock(return_value=f"The experiment is {keyword}.")
        result = await platform.detect_task_phase(page)
        assert result == TaskPhase.COMPLETE, f"Failed for keyword '{keyword}'"
