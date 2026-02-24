import pytest
import asyncio
from experiment_bot.platforms.psytoolkit import PsyToolkitPlatform


TASK_URLS = {
    "stopsignal": "https://www.psytoolkit.org/experiment-library/stopsignal.html",
    "taskswitching_cued": "https://www.psytoolkit.org/experiment-library/taskswitching_cued.html",
}


def test_get_task_url_stopsignal():
    platform = PsyToolkitPlatform()
    url = asyncio.run(platform.get_task_url("stopsignal"))
    assert "psytoolkit.org" in url


def test_get_zip_url():
    platform = PsyToolkitPlatform()
    url = platform.get_zip_url("stopsignal")
    assert url == "https://www.psytoolkit.org/doc_exp/stopsignal.zip"


def test_get_library_url():
    platform = PsyToolkitPlatform()
    url = platform.get_library_url("taskswitching_cued")
    assert url == "https://www.psytoolkit.org/experiment-library/taskswitching_cued.html"


def test_get_demo_url():
    platform = PsyToolkitPlatform()
    url = platform.get_demo_url("stopsignal")
    assert url == "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html"


def test_get_task_url_returns_demo_url():
    platform = PsyToolkitPlatform()
    url = asyncio.run(platform.get_task_url("stopsignal"))
    assert url == "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html"
