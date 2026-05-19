"""SP11 Phase 5b — drop-from-scope machinery tests."""
from __future__ import annotations

import asyncio
import json

import pytest

from experiment_bot.calibration.drop_from_scope import (
    PilotVerdict,
    append_unsupported_note,
    mark_taskcard_unsupported,
    pilot_with_retry,
)


def _run(coro):
    return asyncio.run(coro)


def test_pilot_with_retry_succeeds_on_first_attempt():
    """When the pilot succeeds, no retries are spent."""
    calls = []

    async def pilot():
        calls.append(1)

    verdict = _run(pilot_with_retry("test_label", pilot))
    assert verdict.supported is True
    assert verdict.n_attempts == 1
    assert verdict.attempts[0].succeeded is True
    assert verdict.final_failure_reason is None
    assert len(calls) == 1


def test_pilot_with_retry_succeeds_on_second_attempt():
    """Transient failure on first attempt; success on retry."""
    counter = {"n": 0}

    async def pilot():
        counter["n"] += 1
        if counter["n"] == 1:
            raise RuntimeError("transient")

    verdict = _run(pilot_with_retry("test_label", pilot))
    assert verdict.supported is True
    assert verdict.n_attempts == 2
    assert verdict.attempts[0].succeeded is False
    assert verdict.attempts[0].failure_reason.startswith("RuntimeError")
    assert verdict.attempts[1].succeeded is True


def test_pilot_with_retry_fails_after_3_attempts():
    """Per user note 3: 1 initial + 2 retries = 3 total attempts."""
    counter = {"n": 0}

    async def pilot():
        counter["n"] += 1
        raise RuntimeError(f"persistent failure {counter['n']}")

    verdict = _run(pilot_with_retry("test_label", pilot, max_retries=2))
    assert verdict.supported is False
    assert verdict.n_attempts == 3
    assert verdict.final_failure_reason is not None
    assert "persistent failure 3" in verdict.final_failure_reason
    assert all(a.succeeded is False for a in verdict.attempts)


def test_pilot_with_retry_custom_retry_count():
    """max_retries is configurable."""
    counter = {"n": 0}

    async def pilot():
        counter["n"] += 1
        raise RuntimeError("always fails")

    verdict = _run(pilot_with_retry("test_label", pilot, max_retries=0))
    assert verdict.n_attempts == 1  # 0 retries = 1 attempt
    assert verdict.supported is False


def test_mark_taskcard_unsupported_writes_flag(tmp_path):
    """mark_taskcard_unsupported sets sp11_supported=False and the
    reason string in task_specific."""
    tc_path = tmp_path / "test_card.json"
    tc_path.write_text(json.dumps({
        "task": {"name": "Test"},
        "task_specific": {"key_map": {"a": "left"}},
    }))
    mark_taskcard_unsupported(tc_path, reason="API drift on stage 4")
    data = json.loads(tc_path.read_text())
    assert data["task_specific"]["sp11_supported"] is False
    assert data["task_specific"]["sp11_unsupported_reason"] == "API drift on stage 4"
    # Existing keys preserved
    assert data["task_specific"]["key_map"] == {"a": "left"}


def test_mark_taskcard_unsupported_creates_task_specific_if_absent(tmp_path):
    """If task_specific is missing entirely, it should be created."""
    tc_path = tmp_path / "card2.json"
    tc_path.write_text(json.dumps({"task": {"name": "T"}}))
    mark_taskcard_unsupported(tc_path, reason="missing data export")
    data = json.loads(tc_path.read_text())
    assert data["task_specific"]["sp11_supported"] is False


def test_append_unsupported_note_creates_doc_with_header(tmp_path):
    """First append: file is created with header + entry."""
    doc = tmp_path / "sp11-unsupported.md"
    append_unsupported_note(
        "stopit_stop_signal",
        "Stage 4 openalex.verify_doi crashes",
        doc_path=doc,
        n_attempts=3,
        iso_timestamp="2026-05-18T12:00:00-0700",
    )
    text = doc.read_text()
    assert "# SP11 unsupported paradigms" in text
    assert "stopit_stop_signal" in text
    assert "Stage 4 openalex.verify_doi crashes" in text
    assert "**Attempts:** 3" in text
    assert "2026-05-18T12:00:00-0700" in text


def test_append_unsupported_note_appends_when_doc_exists(tmp_path):
    """Subsequent append: file is opened in append mode; both entries
    survive."""
    doc = tmp_path / "sp11-unsupported.md"
    append_unsupported_note(
        "paradigm_a", "reason a", doc_path=doc,
        n_attempts=3, iso_timestamp="2026-05-18T12:00:00-0700",
    )
    append_unsupported_note(
        "paradigm_b", "reason b", doc_path=doc,
        n_attempts=3, iso_timestamp="2026-05-18T12:05:00-0700",
    )
    text = doc.read_text()
    assert "paradigm_a" in text
    assert "paradigm_b" in text
    # Only one header
    assert text.count("# SP11 unsupported paradigms") == 1
