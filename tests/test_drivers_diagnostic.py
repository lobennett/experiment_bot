"""SP10: DiagnosticDriver writes structured reports for unknown
platforms or unsupported versions; raises DriverError on any
operational method (setup, loop_state, etc.)."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from experiment_bot.drivers.base import DriverError, UnsupportedVersionError
from experiment_bot.drivers.diagnostic import DiagnosticDriver


def _fake_page(url="http://example.com/test"):
    page = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value="Unknown Task")
    page.evaluate = AsyncMock(return_value={
        "jspsych_keys": [], "ids": ["main", "content"], "classes": ["wrapper"],
    })
    page.screenshot = AsyncMock(return_value=b"\x89PNG-fake")
    return page


@pytest.mark.asyncio
async def test_for_unknown_platform_builds_a_report():
    page = _fake_page()
    driver = await DiagnosticDriver.for_unknown_platform(page)
    assert driver._mode == "unknown_platform"
    assert "Unknown Task" in driver._report
    assert "main" in driver._report
    assert "wrapper" in driver._report


@pytest.mark.asyncio
async def test_for_version_mismatch_builds_a_report():
    page = _fake_page()
    err = UnsupportedVersionError(
        detected_version="9.0",
        supported_versions=("7.3", "8.0"),
        missing_anchors=["vendor/jspsych/9.0/"],
    )
    driver = await DiagnosticDriver.for_version_mismatch(page, err)
    assert driver._mode == "version_mismatch"
    assert "9.0" in driver._report
    assert "7.3" in driver._report
    assert "vendor/jspsych/9.0/" in driver._report


@pytest.mark.asyncio
async def test_setup_raises_driver_error_so_executor_aborts_cleanly(tmp_path):
    page = _fake_page()
    driver = await DiagnosticDriver.for_unknown_platform(page)
    driver._report_dir = tmp_path  # write the report into the tmp dir
    with pytest.raises(DriverError) as excinfo:
        await driver.setup(page)
    assert excinfo.value.kind in ("diagnostic_unknown_platform", "diagnostic_version_mismatch")
    # Report was written
    report_files = list(tmp_path.glob("driver_*.md"))
    assert len(report_files) == 1


@pytest.mark.asyncio
async def test_operational_methods_raise_driver_error():
    page = _fake_page()
    driver = await DiagnosticDriver.for_unknown_platform(page)
    for method_name in ("loop_state", "navigate", "get_trial_context"):
        method = getattr(driver, method_name)
        with pytest.raises(DriverError):
            await method(page)


@pytest.mark.asyncio
async def test_can_handle_returns_false_so_diagnostic_never_matches_in_registry():
    # DiagnosticDriver is not in REGISTERED_DRIVERS; this is a safety check.
    assert await DiagnosticDriver.can_handle(_fake_page()) is False
