# SP9a — Session-time runtime LLM for key-mapping resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-call-per-session LLM agent that runs after navigation completes and resolves the `condition → key` mapping for the trial loop. Cache the directive in the executor so per-trial lookup remains a synchronous dict access. Per-session LLM overhead ~2-5 seconds at setup, zero added latency during stimulus presentation.

**Architecture:** New `src/experiment_bot/agent/` package — `types.py` (`KeyMappingDirective` dataclass), `page_probe.py` (DOM/window-globals/screenshot helpers), `session_agent.py` (`SessionAgent.resolve_key_mapping`). Extend the existing `LLMClient` Protocol with optional `images` parameter; add multimodal support in `ClaudeAPIClient`. Add `session_agent_enabled` flag to `RuntimeConfig`. Integrate one new call site in `TaskExecutor.run()` (after `_install_keydown_listener`) and one branch in `_resolve_response_key` (check runtime mapping before existing fallbacks). No changes to the Stage 1-6 Reasoner pipeline or prompts.

**Tech Stack:** Python 3.12 / uv; pytest + pytest-asyncio; Playwright (async API); existing `LLMClient` / `ClaudeAPIClient` / `ClaudeCLIClient` infrastructure; anthropic SDK content-block multimodal shape.

Reference: spec at `docs/superpowers/specs/2026-05-12-sp9a-session-agent-design.md`. Parent results at `docs/sp8-results.md`. User feedback memo at `~/.claude/projects/-Users-lobennett-grants-r01-rdoc-projects-experiment-bot/memory/feedback_avoid_paradigm_overfitting.md`: SessionAgent's interface and probe helpers MUST be paradigm-agnostic.

**Held-out policy reminder:** the cross-paradigm empirical run produces descriptive evidence. If a paradigm doesn't improve, document it as a finding and triage to a future SP. Do NOT iterate on the SessionAgent prompt within SP9a to chase per-paradigm passes.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `src/experiment_bot/llm/protocol.py` | LLMClient Protocol | Modified — add `images: list[bytes] \| None = None` parameter (Task 1) |
| `src/experiment_bot/llm/api_client.py` | API client | Modified — multimodal content blocks when images present (Task 2) |
| `src/experiment_bot/llm/cli_client.py` | CLI client | Modified — log-and-skip when images passed; preserves text path (Task 3) |
| `src/experiment_bot/llm/factory.py` | Client factory | Modified — accept `model: str \| None = None` override (Task 4) |
| `src/experiment_bot/agent/__init__.py` | Package marker | Created (Task 5) |
| `src/experiment_bot/agent/types.py` | `KeyMappingDirective` dataclass | Created (Task 5) |
| `src/experiment_bot/agent/page_probe.py` | DOM/globals/screenshot helpers | Created (Task 6) |
| `src/experiment_bot/agent/session_agent.py` | `SessionAgent` class | Created (Task 7) |
| `src/experiment_bot/core/config.py` | `RuntimeConfig` | Modified — `session_agent_enabled: bool = True` (Task 8) |
| `src/experiment_bot/core/executor.py` | `TaskExecutor` | Modified — constructor accepts agent, post-nav invocation, `_resolve_response_key` runtime branch, metadata directive (Task 9) |
| `tests/test_llm_protocol.py` | Existing | Modified — add `images` parameter compatibility test (Task 1) |
| `tests/test_llm_api_client.py` | Existing | Modified — multimodal-call test (Task 2) |
| `tests/test_llm_cli_client.py` | Existing | Modified — images-passed-logs-warning test (Task 3) |
| `tests/test_llm_factory.py` | Existing | Modified — model override test (Task 4) |
| `tests/test_session_agent.py` | Unit tests for agent layer | Created (Tasks 5, 6, 7) |
| `tests/test_executor_session_agent_integration.py` | Integration tests | Created (Task 9) |
| `output/<paradigm>/<timestamp>/` × 12 | Smoke sessions | Generated (Task 10; gitignored) |
| `docs/sp9a-results.md` | Empirical report | Created (Task 10) |
| `CLAUDE.md` | Sub-project history | Modified (Task 11) |
| `docs/reviewer-1-charter.md` | Charter | Modified — "Last reviewed at" bump (Task 11) |

---

## Paradigm reference

The four paradigms used in SP9a's empirical run (URLs verified from `scripts/launch.sh`; same as SP8's working set, expfactory_flanker and cognitionrun_stroop excluded per spec section 6):

| Label | URL | TaskCard hash (from SP8) | Paradigm class |
|---|---|---|---|
| `expfactory_n_back` | `https://deploy.expfactory.org/preview/5/` | `8198382d` | working_memory |
| `expfactory_stop_signal` | `https://deploy.expfactory.org/preview/9/` | `6ccd7d47` | response_inhibition |
| `stopit_stop_signal` | `https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html` | `39e97714` | response_inhibition |
| `expfactory_stroop` | `https://deploy.expfactory.org/preview/10/` | `f099a88b` | conflict |

---

## Task 0: Set up SP9a worktree

**Files:**
- Worktree: `.worktrees/sp9a` on branch `sp9a/session-agent`, branched off tag `sp8-complete`

Steps 1-3 below are executed by the controller before subagent dispatch. Subsequent tasks assume the worktree exists at `.worktrees/sp9a` and the engineer is operating inside it.

- [ ] **Step 1: Create worktree from sp8-complete**

```bash
git worktree add .worktrees/sp9a -b sp9a/session-agent sp8-complete
```

- [ ] **Step 2: Cherry-pick SP9a spec + this plan onto sp9a branch**

```bash
cd .worktrees/sp9a
git cherry-pick 5c90c9f  # SP9a spec
git cherry-pick <plan-commit>  # this plan (commit landed after plan is written)
```

- [ ] **Step 3: Sync deps and verify clean baseline**

```bash
cd .worktrees/sp9a
uv sync
uv run pytest -q
```

Expected: 530 passed (matches `sp8-complete` baseline).

---

## Task 1: Extend LLMClient Protocol with optional `images` parameter

**Files:**
- Modify: `src/experiment_bot/llm/protocol.py`
- Modify: `tests/test_llm_protocol.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_protocol.py`:

```python
def test_llm_client_protocol_accepts_images_parameter():
    """Concrete clients must accept an optional images=list[bytes] parameter.
    The Protocol uses default None so existing callers stay compatible."""
    import inspect
    from experiment_bot.llm.protocol import LLMClient

    sig = inspect.signature(LLMClient.complete)
    assert "images" in sig.parameters
    assert sig.parameters["images"].default is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_protocol.py::test_llm_client_protocol_accepts_images_parameter -v
```

Expected: FAIL with `AssertionError: 'images' in sig.parameters` (the parameter doesn't exist yet).

- [ ] **Step 3: Extend Protocol**

Replace the full contents of `src/experiment_bot/llm/protocol.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class LLMResponse:
    text: str
    stop_reason: str = "end_turn"


class LLMClient(Protocol):
    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
        images: list[bytes] | None = None,
    ) -> LLMResponse:
        ...
```

- [ ] **Step 4: Run all LLM tests to verify no regression**

```bash
uv run pytest tests/test_llm_protocol.py tests/test_llm_api_client.py tests/test_llm_cli_client.py -v
```

Expected: PASS (new test passes; existing tests pass because images defaults to None and concrete clients still take **kwargs implicitly via Protocol duck typing — but the concrete signatures must match in subsequent tasks).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/llm/protocol.py tests/test_llm_protocol.py
git commit -m "$(cat <<'EOF'
feat(llm): add optional images parameter to LLMClient Protocol

SP9a's SessionAgent passes a screenshot to the LLM for keymap
inference. Extending the Protocol with images=None lets existing
callers continue working while the API client adds multimodal
content-block support.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add image support to ClaudeAPIClient

**Files:**
- Modify: `src/experiment_bot/llm/api_client.py`
- Modify: `tests/test_llm_api_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_api_client.py`:

```python
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock
from experiment_bot.llm.api_client import ClaudeAPIClient


@pytest.mark.asyncio
async def test_api_client_sends_images_as_base64_content_blocks():
    """When images=list[bytes] is passed, the API client builds a
    content-block list with one text block and one image block per image."""
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.stop_reason = "end_turn"

    fake_sdk = MagicMock()
    fake_sdk.messages.create = AsyncMock(return_value=fake_response)

    client = ClaudeAPIClient(client=fake_sdk, model="claude-haiku-4-5")
    png_bytes = b"\x89PNG\r\n\x1a\nfake-image-data"
    await client.complete(system="sys", user="usr", images=[png_bytes])

    call_kwargs = fake_sdk.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "usr"}
    assert content[1]["type"] == "image"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["media_type"] == "image/png"
    assert content[1]["source"]["data"] == base64.b64encode(png_bytes).decode("ascii")


@pytest.mark.asyncio
async def test_api_client_no_images_keeps_string_content():
    """Without images, content is a plain string (backward compatibility)."""
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.stop_reason = "end_turn"

    fake_sdk = MagicMock()
    fake_sdk.messages.create = AsyncMock(return_value=fake_response)

    client = ClaudeAPIClient(client=fake_sdk, model="claude-haiku-4-5")
    await client.complete(system="sys", user="usr")

    call_kwargs = fake_sdk.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["content"] == "usr"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_llm_api_client.py::test_api_client_sends_images_as_base64_content_blocks tests/test_llm_api_client.py::test_api_client_no_images_keeps_string_content -v
```

Expected: First test FAILS because `complete()` doesn't accept `images`. Second test may PASS (it tests existing behavior) — verify both before proceeding.

- [ ] **Step 3: Update ClaudeAPIClient**

Replace the full contents of `src/experiment_bot/llm/api_client.py` with:

```python
from __future__ import annotations

import base64
from typing import Literal

from experiment_bot.llm.protocol import LLMResponse


class ClaudeAPIClient:
    def __init__(self, client, model: str = "claude-opus-4-7"):
        self._client = client
        self._model = model

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
        images: list[bytes] | None = None,
    ) -> LLMResponse:
        # output_format is informational only for the API path; the prompt
        # itself instructs Claude to return JSON when desired.
        if images:
            content: list[dict] | str = [{"type": "text", "text": user}]
            for img in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(img).decode("ascii"),
                    },
                })
        else:
            content = user
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = resp.content[0].text
        return LLMResponse(text=text, stop_reason=getattr(resp, "stop_reason", "end_turn"))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_llm_api_client.py -v
```

Expected: All tests pass (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/llm/api_client.py tests/test_llm_api_client.py
git commit -m "$(cat <<'EOF'
feat(llm): ClaudeAPIClient supports multimodal content blocks

When images=list[bytes] is passed, the user content is a list of one
text block plus one image block per PNG. Existing string-content
callers are unaffected (images defaults to None → string content).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: ClaudeCLIClient logs and skips when images are passed

**Files:**
- Modify: `src/experiment_bot/llm/cli_client.py`
- Modify: `tests/test_llm_cli_client.py`

Rationale: The `claude --print` CLI's multimodal handling is not reliable enough for an SP9a-grade dependency. The CLI client accepts the `images` parameter for Protocol compatibility but logs a warning and proceeds with text-only. SessionAgent users who want multimodal MUST use the API client (set `EXPERIMENT_BOT_LLM_CLIENT=api` and `ANTHROPIC_API_KEY`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_cli_client.py`:

```python
import json
import logging
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from experiment_bot.llm.cli_client import ClaudeCLIClient


@pytest.mark.asyncio
async def test_cli_client_accepts_images_kwarg_for_protocol_compatibility(caplog):
    """The CLI client must accept images=list[bytes] for Protocol compatibility.
    It logs a warning and proceeds with text-only (no CLI multimodal yet)."""
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(json.dumps({"result": "ok"}).encode(), b"")
    )
    proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        client = ClaudeCLIClient(claude_binary="claude")
        with caplog.at_level(logging.WARNING, logger="experiment_bot.llm.cli_client"):
            result = await client.complete(system="sys", user="usr", images=[b"png-bytes"])
        assert result.text == "ok"
        assert any(
            "images" in r.message and "text-only" in r.message
            for r in caplog.records
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm_cli_client.py::test_cli_client_accepts_images_kwarg_for_protocol_compatibility -v
```

Expected: FAIL — `complete()` doesn't accept `images` kwarg.

- [ ] **Step 3: Update ClaudeCLIClient**

Replace the full contents of `src/experiment_bot/llm/cli_client.py` with:

```python
from __future__ import annotations
import asyncio
import json
import logging
from typing import Literal
from experiment_bot.llm.protocol import LLMResponse

logger = logging.getLogger(__name__)


class ClaudeCLIClient:
    """LLM client that shells out to the `claude --print` CLI.

    Uses the user's existing Max subscription via `claude login`.
    No API key required.
    """

    def __init__(
        self,
        claude_binary: str = "claude",
        model: str = "claude-opus-4-7",
        timeout_s: float = 1200.0,
    ):
        self._binary = claude_binary
        self._model = model
        self._timeout_s = timeout_s

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
        images: list[bytes] | None = None,
    ) -> LLMResponse:
        if images:
            logger.warning(
                "ClaudeCLIClient received %d image(s); CLI multimodal is not "
                "supported. Proceeding text-only. Use ClaudeAPIClient "
                "(EXPERIMENT_BOT_LLM_CLIENT=api) for screenshots.",
                len(images),
            )
        # Combine system + user; the CLI doesn't separate them. Convention:
        # prepend system as a labeled section so the model can find it.
        prompt = f"[SYSTEM]\n{system}\n[/SYSTEM]\n\n{user}"
        args = [
            self._binary,
            "--print",
            "--output-format",
            "json",
            "--model",
            self._model,
            prompt,
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"claude CLI timed out after {self._timeout_s}s")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            if "usage limit" in err.lower() or "quota" in err.lower():
                raise RuntimeError(f"claude CLI: usage limit reached: {err.strip()}")
            raise RuntimeError(f"claude CLI failed (rc={proc.returncode}): {err.strip()}")

        out = stdout.decode("utf-8", errors="replace")
        try:
            data = json.loads(out)
            text = data.get("result") or data.get("text") or ""
            stop_reason = data.get("stop_reason", "end_turn")
        except json.JSONDecodeError:
            text = out
            stop_reason = "end_turn"
        return LLMResponse(text=text, stop_reason=stop_reason)
```

- [ ] **Step 4: Run all CLI client tests**

```bash
uv run pytest tests/test_llm_cli_client.py -v
```

Expected: All pass (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/llm/cli_client.py tests/test_llm_cli_client.py
git commit -m "$(cat <<'EOF'
feat(llm): ClaudeCLIClient accepts images kwarg for Protocol compat

Logs a warning and proceeds text-only; CLI multimodal is not supported
in SP9a. SessionAgent users who want screenshots set
EXPERIMENT_BOT_LLM_CLIENT=api.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add model override to build_default_client factory

**Files:**
- Modify: `src/experiment_bot/llm/factory.py`
- Modify: `tests/test_llm_factory.py`

Rationale: SessionAgent should default to `claude-haiku-4-5` (fast, cheap) rather than the framework default `claude-opus-4-7`. Adding a `model` override to the factory lets executor code request the SessionAgent client without rewriting client construction.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_factory.py`:

```python
import os
import pytest
from unittest.mock import patch
from experiment_bot.llm.factory import build_default_client


def test_build_default_client_accepts_model_override():
    """Callers can request a specific model. The returned client carries
    that model through to its model attribute."""
    with patch("shutil.which", return_value="/path/to/claude"):
        client = build_default_client(model="claude-haiku-4-5")
    assert client._model == "claude-haiku-4-5"


def test_build_default_client_defaults_to_client_default_model():
    """No model override → client uses its own default."""
    with patch("shutil.which", return_value="/path/to/claude"):
        client = build_default_client()
    # ClaudeCLIClient default is claude-opus-4-7
    assert client._model == "claude-opus-4-7"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_llm_factory.py::test_build_default_client_accepts_model_override -v
```

Expected: FAIL — `build_default_client` takes no arguments.

- [ ] **Step 3: Update factory**

Replace the full contents of `src/experiment_bot/llm/factory.py` with:

```python
from __future__ import annotations
import os
import shutil
from experiment_bot.llm.cli_client import ClaudeCLIClient
from experiment_bot.llm.api_client import ClaudeAPIClient


def build_default_client(model: str | None = None):
    """Pick LLM client based on environment.

    Resolution order:
      1. EXPERIMENT_BOT_LLM_CLIENT="cli" -> CLI (require claude on PATH)
      2. EXPERIMENT_BOT_LLM_CLIENT="api" -> API (require ANTHROPIC_API_KEY)
      3. Default: CLI if claude on PATH, else API if key present, else raise.

    Args:
        model: Optional model override. When provided, both CLI and API
            paths construct the client with this model id instead of
            their respective defaults.
    """
    explicit = os.environ.get("EXPERIMENT_BOT_LLM_CLIENT", "").lower()
    has_cli = shutil.which("claude") is not None
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if explicit == "cli":
        if not has_cli:
            raise RuntimeError("EXPERIMENT_BOT_LLM_CLIENT=cli but `claude` not on PATH")
        return _build_cli_client(model)
    if explicit == "api":
        if not has_api_key:
            raise RuntimeError("EXPERIMENT_BOT_LLM_CLIENT=api but ANTHROPIC_API_KEY unset")
        return _build_api_client(model)

    if has_cli:
        return _build_cli_client(model)
    if has_api_key:
        return _build_api_client(model)
    raise RuntimeError(
        "no LLM client available: neither `claude` on PATH nor ANTHROPIC_API_KEY set"
    )


def _build_cli_client(model: str | None) -> ClaudeCLIClient:
    if model is None:
        return ClaudeCLIClient()
    return ClaudeCLIClient(model=model)


def _build_api_client(model: str | None) -> ClaudeAPIClient:
    from anthropic import AsyncAnthropic
    api_key = os.environ["ANTHROPIC_API_KEY"]
    sdk = AsyncAnthropic(api_key=api_key)
    if model is None:
        return ClaudeAPIClient(client=sdk)
    return ClaudeAPIClient(client=sdk, model=model)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_llm_factory.py -v
```

Expected: All pass (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/llm/factory.py tests/test_llm_factory.py
git commit -m "$(cat <<'EOF'
feat(llm): build_default_client accepts optional model override

SessionAgent will request a haiku-class client for cost reasons,
while the rest of the framework continues to use the opus default.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create KeyMappingDirective dataclass

**Files:**
- Create: `src/experiment_bot/agent/__init__.py`
- Create: `src/experiment_bot/agent/types.py`
- Create: `tests/test_session_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_agent.py`:

```python
"""Unit tests for the SP9a SessionAgent layer (types, page_probe, session_agent).

The agent module is paradigm-agnostic — its interface accepts a Page
and a TaskCard dict, and returns a KeyMappingDirective without knowing
which paradigm is loaded.
"""
from __future__ import annotations
import pytest

from experiment_bot.agent.types import KeyMappingDirective


def test_directive_dataclass_to_dict_roundtrip():
    """to_dict() emits the canonical run_metadata.json shape."""
    d = KeyMappingDirective(
        mapping={"congruent": "z", "incongruent": "/"},
        source="screenshot_inference",
        confidence=0.85,
        raw_llm_response="raw response text",
        elapsed_ms=2847.3,
    )
    got = d.to_dict()
    assert got == {
        "mapping": {"congruent": "z", "incongruent": "/"},
        "source": "screenshot_inference",
        "confidence": 0.85,
        "raw_llm_response": "raw response text",
        "elapsed_ms": 2847.3,
    }


def test_directive_source_must_be_one_of_known_values():
    """The source literal narrows to the documented set."""
    # Doesn't raise — typing-level constraint only, but the dataclass
    # still accepts the value at runtime. We exercise each known value
    # to make sure the dataclass is constructable with each.
    for src in (
        "window_correctresponse",
        "dom_inference",
        "screenshot_inference",
        "llm_failure_fallback",
    ):
        d = KeyMappingDirective(
            mapping={"x": "y"},
            source=src,
            confidence=1.0,
            raw_llm_response="",
            elapsed_ms=0.0,
        )
        assert d.source == src
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_session_agent.py -v
```

Expected: FAIL — `experiment_bot.agent.types` does not exist.

- [ ] **Step 3: Create package and types**

Create `src/experiment_bot/agent/__init__.py`:

```python
```

(Empty file — package marker.)

Create `src/experiment_bot/agent/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal


SourceLabel = Literal[
    "window_correctresponse",
    "dom_inference",
    "screenshot_inference",
    "llm_failure_fallback",
]


@dataclass
class KeyMappingDirective:
    """Output of SessionAgent.resolve_key_mapping.

    mapping: condition name → key string ready for Playwright key.press()
    source: which inference path produced the mapping
    confidence: LLM-self-reported 0.0-1.0
    raw_llm_response: full LLM text (for audit / debugging)
    elapsed_ms: wall time from probe start to directive ready
    """
    mapping: dict[str, str]
    source: SourceLabel
    confidence: float
    raw_llm_response: str
    elapsed_ms: float

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_session_agent.py -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/agent/__init__.py src/experiment_bot/agent/types.py tests/test_session_agent.py
git commit -m "$(cat <<'EOF'
feat(agent): KeyMappingDirective dataclass for SessionAgent output

Carries the runtime-resolved condition→key mapping plus provenance
(source path, LLM confidence, raw response, wall time) for audit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Create PageProbe helpers

**Files:**
- Create: `src/experiment_bot/agent/page_probe.py`
- Modify: `tests/test_session_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session_agent.py`:

```python
from unittest.mock import AsyncMock

from experiment_bot.agent import page_probe


@pytest.mark.asyncio
async def test_snapshot_window_globals_returns_dict_from_page_evaluate():
    """snapshot_window_globals evaluates a JS expression that returns a
    dict of matching window keys → string-truncated values."""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={
        "correctResponse": "f",
        "responseKey": "j",
    })
    got = await page_probe.snapshot_window_globals(page)
    assert got == {"correctResponse": "f", "responseKey": "j"}
    # JS must filter on the response/correct/key/stim regex and stringify values
    js = page.evaluate.call_args.args[0]
    assert "response|correct|key|stim" in js
    assert "200" in js  # value truncation length


@pytest.mark.asyncio
async def test_snapshot_window_globals_returns_empty_dict_on_evaluate_failure():
    """If evaluate raises (page torn down, etc.), return {} not raise."""
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    got = await page_probe.snapshot_window_globals(page)
    assert got == {}


@pytest.mark.asyncio
async def test_snapshot_dom_summary_truncates_to_20kb():
    """DOM summary is capped at 20480 characters."""
    page = AsyncMock()
    page.content = AsyncMock(return_value="x" * 50000)
    got = await page_probe.snapshot_dom_summary(page)
    assert len(got) <= 20480


@pytest.mark.asyncio
async def test_snapshot_dom_summary_returns_full_when_under_limit():
    """Small DOM returns unchanged."""
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>tiny</body></html>")
    got = await page_probe.snapshot_dom_summary(page)
    assert got == "<html><body>tiny</body></html>"


@pytest.mark.asyncio
async def test_capture_screenshot_returns_bytes_from_page():
    """capture_screenshot is a thin wrapper around page.screenshot()."""
    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG-bytes")
    got = await page_probe.capture_screenshot(page)
    assert got == b"\x89PNG-bytes"
    # Must request PNG with viewport-only (not full_page)
    kwargs = page.screenshot.call_args.kwargs
    assert kwargs.get("type") == "png"
    assert kwargs.get("full_page") is False


@pytest.mark.asyncio
async def test_capture_screenshot_returns_empty_bytes_on_failure():
    """If screenshot raises, return b'' not raise."""
    page = AsyncMock()
    page.screenshot = AsyncMock(side_effect=Exception("page closed"))
    got = await page_probe.capture_screenshot(page)
    assert got == b""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_session_agent.py -v
```

Expected: FAIL — `experiment_bot.agent.page_probe` doesn't exist.

- [ ] **Step 3: Create page_probe.py**

Create `src/experiment_bot/agent/page_probe.py`:

```python
"""Read-only probes of a live Playwright page.

All helpers are paradigm-agnostic: they read whatever the page exposes
and return it. SessionAgent calls them to build the LLM prompt; the
LLM does the paradigm-specific interpretation.
"""
from __future__ import annotations

import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)

_DOM_TRUNCATION_LIMIT = 20480

_WINDOW_GLOBALS_JS = """
(() => {
  const out = {};
  const re = /response|correct|key|stim/i;
  for (const k of Object.keys(window)) {
    if (!re.test(k)) continue;
    try {
      const v = window[k];
      let s;
      if (v === null) s = "null";
      else if (typeof v === "object") s = JSON.stringify(v);
      else s = String(v);
      out[k] = s.length > 200 ? s.slice(0, 200) + "...[trunc]" : s;
    } catch (e) {
      out[k] = "<error reading: " + String(e) + ">";
    }
  }
  return out;
})()
"""


async def snapshot_window_globals(page: Page) -> dict:
    """Return a dict of window.* keys matching /response|correct|key|stim/i.

    Values are stringified and truncated to 200 chars. Returns {} on
    evaluation failure (page torn down, JS error, etc.).
    """
    try:
        return await page.evaluate(_WINDOW_GLOBALS_JS)
    except Exception as e:
        logger.warning("snapshot_window_globals failed: %s", e)
        return {}


async def snapshot_dom_summary(page: Page) -> str:
    """Return up to 20KB of page.content().

    No structural parsing — just a truncated raw HTML string. The LLM
    handles the rest.
    """
    try:
        content = await page.content()
    except Exception as e:
        logger.warning("snapshot_dom_summary failed: %s", e)
        return ""
    if len(content) > _DOM_TRUNCATION_LIMIT:
        return content[:_DOM_TRUNCATION_LIMIT]
    return content


async def capture_screenshot(page: Page) -> bytes:
    """Return a viewport-only PNG. Returns b'' on failure."""
    try:
        return await page.screenshot(type="png", full_page=False)
    except Exception as e:
        logger.warning("capture_screenshot failed: %s", e)
        return b""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_session_agent.py -v
```

Expected: All page_probe tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/agent/page_probe.py tests/test_session_agent.py
git commit -m "$(cat <<'EOF'
feat(agent): PageProbe helpers (window globals, DOM, screenshot)

Read-only paradigm-agnostic snapshots of the live page. All three
helpers return safe defaults ({}/""/b'') on Playwright failure so
SessionAgent can compose its prompt without try/except plumbing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Create SessionAgent class

**Files:**
- Create: `src/experiment_bot/agent/session_agent.py`
- Modify: `tests/test_session_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session_agent.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock

from experiment_bot.agent.session_agent import SessionAgent
from experiment_bot.llm.protocol import LLMResponse


def _scripted_client(text: str):
    """Stub LLMClient whose complete() returns LLMResponse(text=text)."""
    client = MagicMock()
    client.complete = AsyncMock(return_value=LLMResponse(text=text))
    return client


def _stub_page(globals_dict: dict, dom: str, screenshot: bytes):
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=globals_dict)
    page.content = AsyncMock(return_value=dom)
    page.screenshot = AsyncMock(return_value=screenshot)
    return page


@pytest.mark.asyncio
async def test_resolve_key_mapping_returns_directive_from_llm_response():
    """Happy path: LLM returns valid JSON with mapping + source + confidence."""
    llm_text = json.dumps({
        "mapping": {"congruent": "z", "incongruent": "/"},
        "source": "screenshot_inference",
        "confidence": 0.85,
    })
    client = _scripted_client(llm_text)
    page = _stub_page({}, "<html></html>", b"png")
    task_card = {"task_specific": {"key_map": {"congruent": "z", "incongruent": "/"}}}

    agent = SessionAgent(client=client)
    directive = await agent.resolve_key_mapping(page=page, task_card=task_card)

    assert directive.mapping == {"congruent": "z", "incongruent": "/"}
    assert directive.source == "screenshot_inference"
    assert directive.confidence == 0.85
    assert directive.raw_llm_response == llm_text
    assert directive.elapsed_ms > 0


@pytest.mark.asyncio
async def test_resolve_key_mapping_handles_llm_failure_returns_static_fallback():
    """When LLM.complete raises, return a directive with source='llm_failure_fallback'
    and mapping taken from task_card.task_specific.key_map."""
    client = MagicMock()
    client.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
    page = _stub_page({}, "<html></html>", b"png")
    task_card = {"task_specific": {"key_map": {"congruent": "z", "incongruent": "/"}}}

    agent = SessionAgent(client=client)
    directive = await agent.resolve_key_mapping(page=page, task_card=task_card)

    assert directive.source == "llm_failure_fallback"
    assert directive.mapping == {"congruent": "z", "incongruent": "/"}
    assert directive.confidence == 0.0


@pytest.mark.asyncio
async def test_resolve_key_mapping_handles_malformed_llm_response():
    """When the LLM returns non-JSON or missing fields, fall back to static."""
    client = _scripted_client("not-json-at-all")
    page = _stub_page({}, "<html></html>", b"png")
    task_card = {"task_specific": {"key_map": {"congruent": "z"}}}

    agent = SessionAgent(client=client)
    directive = await agent.resolve_key_mapping(page=page, task_card=task_card)

    assert directive.source == "llm_failure_fallback"
    assert directive.mapping == {"congruent": "z"}


@pytest.mark.asyncio
async def test_resolve_key_mapping_passes_screenshot_to_llm():
    """SessionAgent must call client.complete with images=[screenshot_bytes]."""
    llm_text = json.dumps({
        "mapping": {"a": "b"},
        "source": "screenshot_inference",
        "confidence": 0.9,
    })
    client = _scripted_client(llm_text)
    page = _stub_page({}, "<html></html>", b"\x89PNG-screenshot-bytes")
    task_card = {"task_specific": {"key_map": {}}}

    agent = SessionAgent(client=client)
    await agent.resolve_key_mapping(page=page, task_card=task_card)

    call_kwargs = client.complete.call_args.kwargs
    assert call_kwargs["images"] == [b"\x89PNG-screenshot-bytes"]


@pytest.mark.asyncio
async def test_resolve_key_mapping_truncates_dom_in_prompt():
    """A 100KB DOM is truncated when included in the user prompt."""
    llm_text = json.dumps({"mapping": {"a": "b"}, "source": "dom_inference", "confidence": 0.5})
    client = _scripted_client(llm_text)
    page = _stub_page({}, "x" * 100000, b"png")
    task_card = {"task_specific": {"key_map": {}}}

    agent = SessionAgent(client=client)
    await agent.resolve_key_mapping(page=page, task_card=task_card)

    user_prompt = client.complete.call_args.kwargs["user"]
    # The prompt embeds the DOM (truncated to 20KB) plus framing text.
    # Total prompt length should be well under 50KB.
    assert len(user_prompt) < 50000


@pytest.mark.asyncio
async def test_resolve_key_mapping_includes_window_globals_in_prompt():
    """When the page exposes window.correctResponse, the JSON-stringified
    globals dict is in the user prompt — the LLM can see it directly."""
    llm_text = json.dumps({
        "mapping": {"congruent": "f", "incongruent": "j"},
        "source": "window_correctresponse",
        "confidence": 0.95,
    })
    client = _scripted_client(llm_text)
    page = _stub_page(
        {"correctResponse": "f", "stimType": "congruent"},
        "<html></html>", b"png",
    )
    task_card = {"task_specific": {"key_map": {}}}

    agent = SessionAgent(client=client)
    await agent.resolve_key_mapping(page=page, task_card=task_card)

    user_prompt = client.complete.call_args.kwargs["user"]
    assert "correctResponse" in user_prompt
    assert "stimType" in user_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_session_agent.py -v
```

Expected: SessionAgent tests FAIL — module doesn't exist.

- [ ] **Step 3: Create session_agent.py**

Create `src/experiment_bot/agent/session_agent.py`:

```python
"""SessionAgent — one-call-per-session LLM that resolves the key mapping.

Runs after navigation completes and before the trial loop begins. The
result is a KeyMappingDirective cached in the executor; per-trial
key resolution is a synchronous dict lookup, so paradigms with fast
stimulus presentation (stop-signal) are unaffected by LLM latency.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from playwright.async_api import Page

from experiment_bot.agent.page_probe import (
    capture_screenshot,
    snapshot_dom_summary,
    snapshot_window_globals,
)
from experiment_bot.agent.types import KeyMappingDirective
from experiment_bot.llm.protocol import LLMClient

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a cognitive-task analyst. Your job is to determine which keyboard key the page expects for each named condition in a cognitive psychology experiment.

You receive:
1. A TaskCard fragment with the claimed condition→key mapping (may be stale or counterbalanced wrong).
2. A snapshot of selected window.* properties from the live page.
3. A truncated DOM dump.
4. A screenshot of the current page state (the experiment is loaded but no stimulus is yet shown).

Return ONLY valid JSON in this exact shape (no markdown, no commentary):

{
  "mapping": {"<condition_name>": "<key>", ...},
  "source": "window_correctresponse" | "dom_inference" | "screenshot_inference",
  "confidence": <float 0.0-1.0>
}

Use the condition names exactly as they appear in the TaskCard fragment's key_map.
Use Playwright-friendly key strings ("ArrowLeft", "f", "j", " " for space, etc.).
Pick the "source" that best describes how you inferred the mapping:
- "window_correctresponse" if a window.* variable directly named the correct key
- "dom_inference" if the DOM made the mapping unambiguous
- "screenshot_inference" if the screenshot was load-bearing for the decision
"""


class SessionAgent:
    """One-call-per-session LLM agent for key-mapping resolution."""

    def __init__(self, client: LLMClient):
        self._client = client

    async def resolve_key_mapping(
        self,
        page: Page,
        task_card: dict,
        observed_stimulus_examples: list[dict] | None = None,
    ) -> KeyMappingDirective:
        """Probe the page, ask the LLM, return a directive.

        Never raises: any failure (LLM error, malformed JSON, missing
        fields) is caught and returns a directive with
        source='llm_failure_fallback' and mapping=task_card's static
        key_map. The executor's existing fallback chain still runs for
        any condition not in the returned mapping.
        """
        start = time.perf_counter()
        static_keymap = self._extract_static_keymap(task_card)

        globals_dict = await snapshot_window_globals(page)
        dom = await snapshot_dom_summary(page)
        screenshot = await capture_screenshot(page)

        user_prompt = self._build_user_prompt(
            task_card=task_card,
            globals_dict=globals_dict,
            dom=dom,
            observed_examples=observed_stimulus_examples,
        )

        try:
            resp = await self._client.complete(
                system=_SYSTEM_PROMPT,
                user=user_prompt,
                output_format="json",
                images=[screenshot] if screenshot else None,
            )
            parsed = self._parse_llm_response(resp.text)
            if parsed is None:
                logger.warning(
                    "SessionAgent: LLM response unparseable, using static "
                    "key_map fallback. Response head: %r",
                    resp.text[:200],
                )
                return KeyMappingDirective(
                    mapping=static_keymap,
                    source="llm_failure_fallback",
                    confidence=0.0,
                    raw_llm_response=resp.text,
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                )
            return KeyMappingDirective(
                mapping=parsed["mapping"],
                source=parsed["source"],
                confidence=parsed["confidence"],
                raw_llm_response=resp.text,
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:
            logger.warning("SessionAgent: LLM call failed: %s. Using static fallback.", e)
            return KeyMappingDirective(
                mapping=static_keymap,
                source="llm_failure_fallback",
                confidence=0.0,
                raw_llm_response=f"<exception: {e}>",
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )

    @staticmethod
    def _extract_static_keymap(task_card: dict) -> dict[str, str]:
        ts = task_card.get("task_specific") or {}
        keymap = ts.get("key_map") or {}
        # Filter out dynamic sentinels — the executor's existing
        # fallback chain handles those, but the SessionAgent's
        # "static fallback" should contain real key strings only.
        return {
            k: v for k, v in keymap.items()
            if isinstance(v, str) and v not in ("dynamic_mapping", "dynamic")
        }

    @staticmethod
    def _build_user_prompt(
        task_card: dict,
        globals_dict: dict,
        dom: str,
        observed_examples: list[dict] | None,
    ) -> str:
        ts = task_card.get("task_specific") or {}
        claimed_keymap = ts.get("key_map") or {}
        task_meta = task_card.get("task") or {}
        task_name = task_meta.get("name") or "<unknown>"

        sections = [
            f"# Task: {task_name}",
            "",
            "## Claimed condition→key mapping (from TaskCard)",
            "```json",
            json.dumps(claimed_keymap, indent=2),
            "```",
            "",
            "## Live window.* state (filtered to /response|correct|key|stim/i)",
            "```json",
            json.dumps(globals_dict, indent=2),
            "```",
            "",
            "## DOM snapshot (truncated)",
            "```html",
            dom,
            "```",
            "",
            "## Screenshot",
            "(attached as image)",
            "",
            "Return ONLY the JSON described in the system prompt.",
        ]
        if observed_examples:
            sections.insert(7, "## Observed stimulus examples")
            sections.insert(8, "```json")
            sections.insert(9, json.dumps(observed_examples, indent=2))
            sections.insert(10, "```")
            sections.insert(11, "")
        return "\n".join(sections)

    @staticmethod
    def _parse_llm_response(text: str) -> dict[str, Any] | None:
        """Parse the LLM's JSON output. Tolerates leading/trailing whitespace
        and markdown code fences. Returns None if mapping/source/confidence
        keys are missing or have the wrong types."""
        cleaned = text.strip()
        # Strip ```json ... ``` fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                cleaned = "\n".join(lines[1:-1])
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        mapping = data.get("mapping")
        source = data.get("source")
        confidence = data.get("confidence")
        if not isinstance(mapping, dict):
            return None
        if source not in (
            "window_correctresponse",
            "dom_inference",
            "screenshot_inference",
        ):
            return None
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return None
        return {"mapping": mapping, "source": source, "confidence": confidence}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_session_agent.py -v
```

Expected: All SessionAgent tests PASS (plus the earlier types and page_probe tests).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/agent/session_agent.py tests/test_session_agent.py
git commit -m "$(cat <<'EOF'
feat(agent): SessionAgent resolves key mapping with one LLM call

After navigation completes, SessionAgent probes the page (window
globals, DOM, screenshot), asks the LLM to produce a condition→key
mapping in canonical JSON, and returns a KeyMappingDirective. Any
failure (LLM exception, malformed JSON, missing fields) degrades to
a static fallback from task_specific.key_map so the executor's
existing fallback chain still runs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add session_agent_enabled flag to RuntimeConfig

**Files:**
- Modify: `src/experiment_bot/core/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_runtime_config_session_agent_enabled_defaults_to_true():
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig()
    assert rc.session_agent_enabled is True


def test_runtime_config_session_agent_enabled_roundtrip():
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig(session_agent_enabled=False)
    d = rc.to_dict()
    assert d["session_agent_enabled"] is False
    rc2 = RuntimeConfig.from_dict(d)
    assert rc2.session_agent_enabled is False


def test_runtime_config_session_agent_enabled_from_dict_defaults_true():
    """Existing TaskCards without the field should default to True."""
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig.from_dict({})
    assert rc.session_agent_enabled is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py::test_runtime_config_session_agent_enabled_defaults_to_true tests/test_config.py::test_runtime_config_session_agent_enabled_roundtrip tests/test_config.py::test_runtime_config_session_agent_enabled_from_dict_defaults_true -v
```

Expected: FAIL — `session_agent_enabled` attribute doesn't exist.

- [ ] **Step 3: Modify RuntimeConfig**

In `src/experiment_bot/core/config.py`, the existing `RuntimeConfig` dataclass spans approximately lines 521-556. Modify it as follows.

Find:

```python
@dataclass
class RuntimeConfig:
    phase_detection: PhaseDetectionConfig = field(default_factory=PhaseDetectionConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    advance_behavior: AdvanceBehaviorConfig = field(default_factory=AdvanceBehaviorConfig)
    trial_interrupt: TrialInterruptConfig = field(default_factory=TrialInterruptConfig)
    data_capture: DataCaptureConfig = field(default_factory=DataCaptureConfig)
    attention_check: AttentionCheckConfig = field(default_factory=AttentionCheckConfig)
    # Condition label used to detect navigation stimuli in the trial loop.
    # Defaults to "" (empty) — when empty, the executor falls back to the legacy
    # hardcoded value "navigation" so existing configs still work.
    navigation_stimulus_condition: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> RuntimeConfig:
        return cls(
            phase_detection=PhaseDetectionConfig.from_dict(d.get("phase_detection", {})),
            timing=TimingConfig.from_dict(d.get("timing", {})),
            advance_behavior=AdvanceBehaviorConfig.from_dict(d.get("advance_behavior", {})),
            trial_interrupt=TrialInterruptConfig.from_dict(d.get("trial_interrupt", {})),
            data_capture=DataCaptureConfig.from_dict(d.get("data_capture", {})),
            attention_check=AttentionCheckConfig.from_dict(d.get("attention_check", {})),
            navigation_stimulus_condition=d.get("navigation_stimulus_condition", ""),
        )

    def to_dict(self) -> dict:
        return {
            "phase_detection": self.phase_detection.to_dict(),
            "timing": self.timing.to_dict(),
            "advance_behavior": self.advance_behavior.to_dict(),
            "trial_interrupt": self.trial_interrupt.to_dict(),
            "data_capture": self.data_capture.to_dict(),
            "attention_check": self.attention_check.to_dict(),
            # Always emit for round-trip stability, matching AttentionCheckConfig policy.
            "navigation_stimulus_condition": self.navigation_stimulus_condition,
        }
```

Replace with:

```python
@dataclass
class RuntimeConfig:
    phase_detection: PhaseDetectionConfig = field(default_factory=PhaseDetectionConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    advance_behavior: AdvanceBehaviorConfig = field(default_factory=AdvanceBehaviorConfig)
    trial_interrupt: TrialInterruptConfig = field(default_factory=TrialInterruptConfig)
    data_capture: DataCaptureConfig = field(default_factory=DataCaptureConfig)
    attention_check: AttentionCheckConfig = field(default_factory=AttentionCheckConfig)
    # Condition label used to detect navigation stimuli in the trial loop.
    # Defaults to "" (empty) — when empty, the executor falls back to the legacy
    # hardcoded value "navigation" so existing configs still work.
    navigation_stimulus_condition: str = ""
    # SP9a: enable session-time runtime LLM for key-mapping resolution.
    # When True (default), TaskExecutor calls SessionAgent once after
    # navigation completes; the resolved mapping takes precedence over
    # the static key_map fallback in _resolve_response_key.
    session_agent_enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> RuntimeConfig:
        return cls(
            phase_detection=PhaseDetectionConfig.from_dict(d.get("phase_detection", {})),
            timing=TimingConfig.from_dict(d.get("timing", {})),
            advance_behavior=AdvanceBehaviorConfig.from_dict(d.get("advance_behavior", {})),
            trial_interrupt=TrialInterruptConfig.from_dict(d.get("trial_interrupt", {})),
            data_capture=DataCaptureConfig.from_dict(d.get("data_capture", {})),
            attention_check=AttentionCheckConfig.from_dict(d.get("attention_check", {})),
            navigation_stimulus_condition=d.get("navigation_stimulus_condition", ""),
            session_agent_enabled=d.get("session_agent_enabled", True),
        )

    def to_dict(self) -> dict:
        return {
            "phase_detection": self.phase_detection.to_dict(),
            "timing": self.timing.to_dict(),
            "advance_behavior": self.advance_behavior.to_dict(),
            "trial_interrupt": self.trial_interrupt.to_dict(),
            "data_capture": self.data_capture.to_dict(),
            "attention_check": self.attention_check.to_dict(),
            # Always emit for round-trip stability, matching AttentionCheckConfig policy.
            "navigation_stimulus_condition": self.navigation_stimulus_condition,
            "session_agent_enabled": self.session_agent_enabled,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All three new tests PASS plus all existing tests.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): RuntimeConfig.session_agent_enabled flag (default True)

Tests and ablation runs can toggle the SessionAgent off via this flag
without touching executor wiring. Defaults to True so existing
TaskCards opt in automatically.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Integrate SessionAgent into TaskExecutor

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Create: `tests/test_executor_session_agent_integration.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_executor_session_agent_integration.py`:

```python
"""Integration tests for the SP9a SessionAgent ↔ TaskExecutor wiring.

These tests build a stub TaskExecutor by bypassing __init__ (using
__new__) and patching only the fields the test exercises. The pattern
mirrors tests/test_executor_keypress_diagnostic.py.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.agent.types import KeyMappingDirective
from experiment_bot.core.executor import TaskExecutor


def _stub_match(condition: str, response_key: str = "", stimulus_id: str = "stim1") -> SimpleNamespace:
    return SimpleNamespace(
        condition=condition,
        response_key=response_key,
        stimulus_id=stimulus_id,
    )


def _stub_config_with_static_keymap(key_map: dict) -> SimpleNamespace:
    """Build the minimum config view _resolve_response_key reads from."""
    return SimpleNamespace(
        task_specific={"key_map": dict(key_map)},
        stimuli=[],
    )


def _stub_executor_for_resolve_response_key(
    config,
    runtime_key_mapping: dict | None,
    static_key_map: dict | None = None,
) -> TaskExecutor:
    stub = TaskExecutor.__new__(TaskExecutor)
    stub._config = config
    stub._runtime_key_mapping = runtime_key_mapping
    stub._key_map = static_key_map if static_key_map is not None else dict(config.task_specific.get("key_map", {}))
    stub._seen_response_keys = set()
    return stub


@pytest.mark.asyncio
async def test_resolve_response_key_prefers_runtime_mapping_over_static():
    """When self._runtime_key_mapping is set and contains the condition,
    return that key without consulting per-stim JS or static fallback."""
    cfg = _stub_config_with_static_keymap({"congruent": "a", "incongruent": "b"})
    runtime_mapping = {"congruent": "f", "incongruent": "j"}
    stub = _stub_executor_for_resolve_response_key(cfg, runtime_mapping)

    got = await stub._resolve_response_key(_stub_match("congruent"), page=None)

    assert got == "f"  # runtime mapping wins
    assert "f" in stub._seen_response_keys


@pytest.mark.asyncio
async def test_resolve_response_key_falls_back_when_condition_missing_from_runtime_mapping():
    """When the runtime mapping lacks the condition, the existing fallback
    chain (static key_map, etc.) still runs."""
    cfg = _stub_config_with_static_keymap({"congruent": "a", "novel_cond": "x"})
    runtime_mapping = {"congruent": "f"}  # 'novel_cond' missing
    stub = _stub_executor_for_resolve_response_key(cfg, runtime_mapping)

    got = await stub._resolve_response_key(_stub_match("novel_cond"), page=None)

    assert got == "x"  # static fallback


@pytest.mark.asyncio
async def test_resolve_response_key_uses_static_when_runtime_mapping_is_none():
    """When _runtime_key_mapping is None (SessionAgent disabled / not run),
    behavior is identical to pre-SP9a."""
    cfg = _stub_config_with_static_keymap({"congruent": "a"})
    stub = _stub_executor_for_resolve_response_key(cfg, runtime_key_mapping=None)

    got = await stub._resolve_response_key(_stub_match("congruent"), page=None)

    assert got == "a"


@pytest.mark.asyncio
async def test_invoke_session_agent_caches_directive_into_runtime_mapping():
    """When _invoke_session_agent is called with a stub agent, its directive's
    mapping ends up in self._runtime_key_mapping and the directive itself
    in self._session_agent_directive."""
    directive = KeyMappingDirective(
        mapping={"congruent": "z", "incongruent": "/"},
        source="screenshot_inference",
        confidence=0.85,
        raw_llm_response="raw",
        elapsed_ms=2000.0,
    )
    agent = MagicMock()
    agent.resolve_key_mapping = AsyncMock(return_value=directive)

    stub = TaskExecutor.__new__(TaskExecutor)
    stub._session_agent = agent
    stub._taskcard = None
    stub._config = SimpleNamespace(
        task_specific={},
        runtime=SimpleNamespace(session_agent_enabled=True),
    )
    stub._config.to_dict = lambda: {"task_specific": {}, "task": {"name": "test"}}
    stub._runtime_key_mapping = None
    stub._session_agent_directive = None

    page = AsyncMock()
    await stub._invoke_session_agent(page)

    assert stub._runtime_key_mapping == {"congruent": "z", "incongruent": "/"}
    assert stub._session_agent_directive is directive
    agent.resolve_key_mapping.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_session_agent_skipped_when_flag_disabled():
    """When config.runtime.session_agent_enabled is False, _invoke_session_agent
    does NOT call the agent and leaves _runtime_key_mapping as None."""
    agent = MagicMock()
    agent.resolve_key_mapping = AsyncMock()

    stub = TaskExecutor.__new__(TaskExecutor)
    stub._session_agent = agent
    stub._taskcard = None
    stub._config = SimpleNamespace(
        task_specific={},
        runtime=SimpleNamespace(session_agent_enabled=False),
    )
    stub._config.to_dict = lambda: {}
    stub._runtime_key_mapping = None
    stub._session_agent_directive = None

    page = AsyncMock()
    await stub._invoke_session_agent(page)

    assert stub._runtime_key_mapping is None
    assert stub._session_agent_directive is None
    agent.resolve_key_mapping.assert_not_called()


@pytest.mark.asyncio
async def test_invoke_session_agent_skipped_when_no_agent_attached():
    """When the executor was built without a session agent (e.g. tests
    that don't need one), _invoke_session_agent is a no-op."""
    stub = TaskExecutor.__new__(TaskExecutor)
    stub._session_agent = None
    stub._taskcard = None
    stub._config = SimpleNamespace(
        task_specific={},
        runtime=SimpleNamespace(session_agent_enabled=True),
    )
    stub._config.to_dict = lambda: {}
    stub._runtime_key_mapping = None
    stub._session_agent_directive = None

    page = AsyncMock()
    await stub._invoke_session_agent(page)

    assert stub._runtime_key_mapping is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_executor_session_agent_integration.py -v
```

Expected: All FAIL — `_runtime_key_mapping`, `_session_agent`, `_session_agent_directive`, `_invoke_session_agent` don't exist on TaskExecutor; `_resolve_response_key` doesn't check runtime mapping.

- [ ] **Step 3: Modify TaskExecutor constructor**

Open `src/experiment_bot/core/executor.py`. Find the `__init__` signature (currently lines 63-69):

```python
    def __init__(
        self,
        config,  # TaskCard or TaskConfig
        seed: int | None = None,
        headless: bool = False,
        session_params: dict | None = None,
    ):
```

Replace with:

```python
    def __init__(
        self,
        config,  # TaskCard or TaskConfig
        seed: int | None = None,
        headless: bool = False,
        session_params: dict | None = None,
        session_agent=None,  # SP9a: SessionAgent instance for runtime key resolution
    ):
```

Then find the end of `__init__` (currently around line 124, right after the `_attention_check_conditions` block). After:

```python
        self._attention_check_conditions: set[str] = set(
            config.runtime.attention_check.stimulus_conditions
        ) or {"attention_check", "attention_check_response"}
```

Append:

```python

        # SP9a: SessionAgent runtime key resolution
        self._session_agent = session_agent
        self._runtime_key_mapping: dict[str, str] | None = None
        self._session_agent_directive = None  # KeyMappingDirective | None
```

- [ ] **Step 4: Add `_invoke_session_agent` method to TaskExecutor**

Open `src/experiment_bot/core/executor.py`. After the `_resolve_key_mapping` static method (currently ends around line 132), add this new method:

```python
    async def _invoke_session_agent(self, page: Page) -> None:
        """SP9a: run the SessionAgent once per session after navigation.

        Caches the resolved condition→key mapping into self._runtime_key_mapping
        and the full directive (for run_metadata) into self._session_agent_directive.
        Skipped when session_agent_enabled is False or no agent was attached.
        """
        if not getattr(self._config.runtime, "session_agent_enabled", True):
            return
        if self._session_agent is None:
            return
        try:
            task_card_dict = (
                self._taskcard.to_dict()
                if self._taskcard is not None
                else self._config.to_dict()
            )
        except Exception:
            task_card_dict = {}
        directive = await self._session_agent.resolve_key_mapping(
            page=page,
            task_card=task_card_dict,
        )
        self._runtime_key_mapping = directive.mapping
        self._session_agent_directive = directive
        logger.info(
            "SessionAgent: source=%s confidence=%.2f mapping=%s",
            directive.source, directive.confidence, directive.mapping,
        )
```

- [ ] **Step 5: Modify `_resolve_response_key` to check runtime mapping first**

In `src/experiment_bot/core/executor.py`, find `_resolve_response_key` (line 168). The current implementation starts:

```python
    async def _resolve_response_key(self, match: StimulusMatch, page: Page | None = None) -> str | None:
        """Resolve the actual key to press for a stimulus match.

        Resolution order:
        1. Static key from stimulus config
        2. Per-stimulus response_key_js (evaluated on page)
        3. Global task_specific.response_key_js (evaluated on page)
        4. Static key_map fallback

        Returns None when no key is found OR when the resolved value is a
        withhold sentinel ("", None, "none", "null" — case-insensitive).
        Callers must treat None as "do not press any key".
        """
        # Static key from config
        if match.response_key and match.response_key not in ("dynamic_mapping", "dynamic"):
            self._seen_response_keys.add(match.response_key)
            return match.response_key
```

Replace the docstring and the first conditional block with:

```python
    async def _resolve_response_key(self, match: StimulusMatch, page: Page | None = None) -> str | None:
        """Resolve the actual key to press for a stimulus match.

        Resolution order:
        0. SP9a runtime mapping (SessionAgent's directive, if any)
        1. Static key from stimulus config
        2. Per-stimulus response_key_js (evaluated on page)
        3. Global task_specific.response_key_js (evaluated on page)
        4. Static key_map fallback

        Returns None when no key is found OR when the resolved value is a
        withhold sentinel ("", None, "none", "null" — case-insensitive).
        Callers must treat None as "do not press any key".
        """
        # SP9a: SessionAgent runtime mapping has priority
        runtime_map = getattr(self, "_runtime_key_mapping", None)
        if runtime_map is not None:
            runtime_key = runtime_map.get(match.condition)
            if runtime_key and not self._is_withhold_sentinel(runtime_key):
                self._seen_response_keys.add(runtime_key)
                return runtime_key

        # Static key from config
        if match.response_key and match.response_key not in ("dynamic_mapping", "dynamic"):
            self._seen_response_keys.add(match.response_key)
            return match.response_key
```

- [ ] **Step 6: Wire SessionAgent invocation into the `run()` flow**

In `src/experiment_bot/core/executor.py`, find the existing post-navigation block (around line 306-308):

```python
                # Phase 1: Navigate instructions
                logger.info("Navigating instructions...")
                await self._navigator.execute_all(page, self._config.navigation)

                await self._install_keydown_listener(page)
```

Replace with:

```python
                # Phase 1: Navigate instructions
                logger.info("Navigating instructions...")
                await self._navigator.execute_all(page, self._config.navigation)

                await self._install_keydown_listener(page)

                # SP9a: one-call-per-session LLM key-mapping resolution
                await self._invoke_session_agent(page)
```

- [ ] **Step 7: Persist directive into run_metadata.json**

In `src/experiment_bot/core/executor.py`, find the `finally:` metadata block (around line 343-355):

```python
            finally:
                metadata = {
                    "task_name": task_name,
                    "task_url": task_url,
                    "total_trials": self._trial_count,
                    "headless": self._headless,
                    "session_seed": self._session_seed,
                    "session_params": self._session_params,
                }
                if self._taskcard is not None:
                    pb = getattr(self._taskcard, "produced_by", None)
                    metadata["taskcard_sha256"] = getattr(pb, "taskcard_sha256", "") if pb else ""
                self._writer.save_metadata(metadata)
                self._writer.finalize()
                await browser.close()
```

Replace with:

```python
            finally:
                metadata = {
                    "task_name": task_name,
                    "task_url": task_url,
                    "total_trials": self._trial_count,
                    "headless": self._headless,
                    "session_seed": self._session_seed,
                    "session_params": self._session_params,
                }
                if self._taskcard is not None:
                    pb = getattr(self._taskcard, "produced_by", None)
                    metadata["taskcard_sha256"] = getattr(pb, "taskcard_sha256", "") if pb else ""
                if self._session_agent_directive is not None:
                    metadata["session_agent_directive"] = self._session_agent_directive.to_dict()
                self._writer.save_metadata(metadata)
                self._writer.finalize()
                await browser.close()
```

- [ ] **Step 8: Run integration tests to verify they pass**

```bash
uv run pytest tests/test_executor_session_agent_integration.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 9: Run the full test suite to check for regressions**

```bash
uv run pytest -q
```

Expected: 530 + new tests pass. Specifically the SP8 baseline (530) plus +2 protocol/factory tests (Task 1, 4), +2 API client tests (Task 2), +1 CLI client test (Task 3), +1 factory tests (Task 4) [tracked as 2], +2 directive tests (Task 5), +6 page_probe tests (Task 6), +6 SessionAgent tests (Task 7), +3 config tests (Task 8), +6 integration tests (Task 9). Expected new total: ~558-560 passed.

If any pre-existing test fails, debug before committing.

- [ ] **Step 10: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_session_agent_integration.py
git commit -m "$(cat <<'EOF'
feat(executor): wire SessionAgent into TaskExecutor

After navigation completes (between _install_keydown_listener and the
trial loop), the executor calls SessionAgent.resolve_key_mapping once
per session. The resulting condition→key mapping is cached in
self._runtime_key_mapping; _resolve_response_key checks it first
before the existing static / per-stim JS / global JS fallback chain.

The full directive (mapping, source, confidence, raw response,
elapsed_ms) is persisted into run_metadata.json so post-hoc analysis
can cross-tabulate inference path against per-trial alignment.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Empirical smoke run + audit + results report

**Files:**
- Generated: `output/<paradigm>/<timestamp>/` × 12 (gitignored)
- Create: `docs/sp9a-results.md`

Manual execution. The engineer runs 12 smoke sessions (4 paradigms × 3 seeds), re-runs the SP7 keypress audit, and writes the results report.

- [ ] **Step 1: Confirm SessionAgent is enabled and API client is selected**

```bash
cd .worktrees/sp9a
export EXPERIMENT_BOT_LLM_CLIENT=api
# ANTHROPIC_API_KEY must already be set
echo "Client: $EXPERIMENT_BOT_LLM_CLIENT"
echo "API key set: $([[ -n $ANTHROPIC_API_KEY ]] && echo yes || echo no)"
```

If `API key set: no`, source the user's `.env` or export the key before proceeding.

- [ ] **Step 2: Run smoke sessions, 4 paradigms × 3 seeds**

Run each in turn (do NOT parallelize — the API rate limits and the screenshot capture share the local display):

```bash
# expfactory_n_back (SP8 hash 8198382d)
uv run experiment-bot run --label expfactory_n_back --seed 9001
uv run experiment-bot run --label expfactory_n_back --seed 9002
uv run experiment-bot run --label expfactory_n_back --seed 9003

# expfactory_stop_signal (SP8 hash 6ccd7d47)
uv run experiment-bot run --label expfactory_stop_signal --seed 9101
uv run experiment-bot run --label expfactory_stop_signal --seed 9102
uv run experiment-bot run --label expfactory_stop_signal --seed 9103

# expfactory_stroop (SP8 hash f099a88b)
uv run experiment-bot run --label expfactory_stroop --seed 9201
uv run experiment-bot run --label expfactory_stroop --seed 9202
uv run experiment-bot run --label expfactory_stroop --seed 9203

# stopit_stop_signal (SP8 hash 39e97714)
uv run experiment-bot run --label stopit_stop_signal --seed 9301
uv run experiment-bot run --label stopit_stop_signal --seed 9302
uv run experiment-bot run --label stopit_stop_signal --seed 9303
```

For each session, verify the run_dir contains `experiment_data.{csv,json}`, `bot_log.json`, and `run_metadata.json` with a non-empty `session_agent_directive` field.

If a session crashes or produces zero trials, retry once with a fresh seed offset by +500 (e.g., 9501 instead of 9001) and document the retry in the results report. If it crashes twice, document the failure and exclude that session from the audit.

- [ ] **Step 3: Run keypress audit per paradigm**

```bash
uv run python scripts/keypress_audit.py --paradigm expfactory_n_back --since 2026-05-12_18-00 > /tmp/sp9a_nback_audit.txt
uv run python scripts/keypress_audit.py --paradigm expfactory_stop_signal --since 2026-05-12_18-00 > /tmp/sp9a_stop_signal_audit.txt
uv run python scripts/keypress_audit.py --paradigm expfactory_stroop --since 2026-05-12_18-00 > /tmp/sp9a_stroop_audit.txt
uv run python scripts/keypress_audit.py --paradigm stopit_stop_signal --since 2026-05-12_18-00 > /tmp/sp9a_stopit_audit.txt
```

(Replace `--since 2026-05-12_18-00` with the actual ISO-prefix of when the SP9a run window began.)

Aggregate the four files into one table — each row = paradigm, n trials, bot_pressed == page_received, page_received == platform_recorded, bot_pressed == platform_recorded, bot_intended == platform_expected.

- [ ] **Step 4: Cross-tabulate directive source against per-trial alignment**

For each session, read `run_metadata.json` and note `session_agent_directive.source`. Group sessions by source and compute `bot_intended == platform_expected` per source. This is the SP9a-specific analysis the spec calls out — does `screenshot_inference` correlate with success on stroop/stop-signal?

```bash
uv run python -c "
import json, glob
sessions = {}
for p in sorted(glob.glob('output/*/2026-05-12_*/run_metadata.json')):
    m = json.load(open(p))
    directive = m.get('session_agent_directive', {})
    sessions[p] = {
        'task': m.get('task_name'),
        'source': directive.get('source'),
        'confidence': directive.get('confidence'),
        'mapping': directive.get('mapping'),
    }
for p, info in sessions.items():
    print(p, info)
"
```

- [ ] **Step 5: Write `docs/sp9a-results.md`**

The report MUST include:

1. **Date / run window / tag-target.**
2. **Procedure** — exact seeds run, exact commands, what was excluded and why.
3. **Per-paradigm 4-way audit table** comparing SP8 baseline to SP9a (use the spec's "comparison table" shape).
4. **Cross-tab of directive source vs alignment** (from Step 4).
5. **Reading** — what improved, what didn't, what's surprising.
6. **Comparison to SP8** in the same shape as `docs/sp8-results.md`'s comparison block.
7. **Framework gaps surfaced** (SP9b candidates) — anything new SP9a's instrumentation revealed.
8. **Status** — internal CI gate (test count expected ~558-560), external descriptive evidence (PASS/MIXED/FAIL), recommended next step.

Honest framing: if 3 of 4 paradigms hit the ≥65% target, it's PASS. If 1 of 4, it's MIXED. If 0 of 4, it's FAIL — and the report names which SP9b candidate would attack the gap.

- [ ] **Step 6: Commit the report and tag**

```bash
git add docs/sp9a-results.md
git commit -m "$(cat <<'EOF'
docs(sp9a): cross-paradigm empirical results — SessionAgent runtime LLM

[1-3 sentence headline summary of what improved and what didn't]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Tag and push are handled in Task 11.

---

## Task 11: Documentation + tag + push

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/reviewer-1-charter.md`

- [ ] **Step 1: Append SP9a entry to CLAUDE.md sub-project history**

In `CLAUDE.md`, find the existing SP9 (planned) entry under "Sub-project history":

```
- **SP9** (planned): architectural cleanup brainstorm. User raised
  during SP8 brainstorm — codebase has accumulated parallel retry
  mechanisms, oneOf envelopes, per-paradigm adapters, six Reasoner
  stages, and defensive fallback layers. Runtime-LLM partition is a
  key design consideration: per-trial LLM calls infeasible for
  speeded paradigms; setup/ITI/transition decisions are fair game.
  SP8 extended the SP9 backlog: Stage 4 openalex.py defensive fix,
  Stage 6 pilot timing fragility, DOM-derived fallback unreliability
  for paradigms without `window.correctResponse`.
```

Replace with:

```
- **SP9a**: Session-time runtime LLM for key-mapping resolution. New
  `src/experiment_bot/agent/` package — `SessionAgent.resolve_key_mapping`
  runs once per session after navigation completes, probes the live page
  (DOM + window globals + screenshot), and asks an LLM (haiku-class via
  `EXPERIMENT_BOT_LLM_CLIENT=api`) to produce a `KeyMappingDirective`.
  Executor caches the directive's mapping into `_runtime_key_mapping`;
  `_resolve_response_key` checks it before the existing static / per-stim
  JS / global JS fallback chain. Per-trial cost: synchronous dict lookup
  (no LLM call mid-trial), so fast paradigms (stop-signal) are
  unaffected. Stage 1-6 Reasoner pipeline preserved exactly — TaskCard
  regeneration from fresh repo still works.
  Internal: [N] passed (was 530). External: see `docs/sp9a-results.md`
  for cross-paradigm comparison vs SP8. Tag `sp9a-complete`.
- **SP9** (continuing): architectural cleanup backlog. Remaining items
  carried over from SP8: Stage 4 openalex.py list/string defensive fix
  (SP9b candidate); Stage 6 pilot timing fragility (SP9b candidate);
  expfactory_flanker + cognitionrun_stroop revival (blocked by SP9b
  Stage 4 fix). Codebase-cleanup themes (parallel retry mechanisms,
  oneOf envelopes, per-paradigm adapters, six Reasoner stages) remain
  for future SPs as their leverage cases are surfaced empirically.
```

Replace the placeholder `[N]` with the actual passing test count from `uv run pytest --co -q | tail -1`.

- [ ] **Step 2: Bump reviewer-1-charter.md "Last reviewed at" line**

In `docs/reviewer-1-charter.md`, find the line:

```
Last reviewed at: sp8-complete (SP9 architectural-cleanup brainstorm pending)
```

Replace with:

```
Last reviewed at: sp9a-complete (SP9b openalex defensive fix + pilot timing remain in backlog)
```

If the SessionAgent introduces a new probe candidate (e.g., "does the directive's `confidence` field calibrate with per-trial alignment?"), add it to the threat model section. If not, leave that section unchanged.

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md docs/reviewer-1-charter.md
git commit -m "$(cat <<'EOF'
docs(claude.md,reviewer-1): mark SP9a complete; SP9b backlog remains

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Tag and push**

```bash
git tag sp9a-complete
git push origin sp9a/session-agent
git push origin sp9a-complete
```

Expected: branch and tag both land on origin. Verify with `git ls-remote origin sp9a-complete`.

---

## Self-review notes

Self-review against the spec:

**1. Spec coverage:**
- ✓ Section 1 (motivation) — covered in plan header
- ✓ Section 2 (architecture) — Tasks 1-9 implement every named module + integration
- ✓ Section 3 (speed handling) — Task 9 caches the mapping; per-trial lookup is synchronous (proven by integration tests)
- ✓ Section 4 (test strategy) — unit tests in Tasks 5-7, integration tests in Task 9, empirical run in Task 10
- ✓ Section 5 (deliverables) — Tasks 0, 9, 10, 11 cover workspace, files, metadata, tag
- ✓ Section 6 (out of scope) — no task touches Stage 4/6, TaskCards, cognitionrun_stroop, flanker, prompts

**2. Placeholder scan:** the report-headline line in Task 10 Step 6 (`[1-3 sentence headline...]`) and the test-count `[N]` in Task 11 Step 1 are intentional — they're values determined by the empirical run, not specifiable in advance. Both have explicit instructions for what to write.

**3. Type consistency:**
- `KeyMappingDirective` is created in Task 5 with fields `mapping, source, confidence, raw_llm_response, elapsed_ms`; used identically in Task 7 (SessionAgent), Task 9 (executor metadata), and Task 10 (results audit).
- `SessionAgent.resolve_key_mapping(page, task_card, observed_stimulus_examples=None)` signature matches across Tasks 7 and 9.
- `RuntimeConfig.session_agent_enabled` is `bool` with default `True` — referenced consistently in Tasks 8 and 9.
- `_runtime_key_mapping: dict[str, str] | None`, `_session_agent_directive`, `_session_agent` attributes are consistently named across Tasks 9's integration test and the executor patch.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-12-sp9a-session-agent.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (spec compliance, then code quality), fast iteration in this session.

**2. Inline Execution** — execute tasks inline using `superpowers:executing-plans`, batch execution with checkpoints for review.

Which approach?
