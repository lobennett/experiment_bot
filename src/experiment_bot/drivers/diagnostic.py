"""SP10 DiagnosticDriver — fallback when no platform driver matches."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from playwright.async_api import Page

from experiment_bot.drivers.base import (
    DeliveryResult, DriverError, ExperimentData, NavigationOutcome,
    TrialContext, TrialLoopState, UnsupportedVersionError,
)

logger = logging.getLogger(__name__)


_FINGERPRINT_JS = """
(() => {
  const out = {
    jspsych_keys: Object.keys(window).filter(k =>
      /jspsych|psychojs|cognition|response|trial|stimulus|experiment/i.test(k)
    ).slice(0, 50),
    ids: Array.from(document.querySelectorAll('[id]')).map(e => e.id).slice(0, 30),
    classes: (() => {
      const s = new Set();
      document.querySelectorAll('[class]').forEach(e => {
        e.className.split(/\\s+/).forEach(c => { if (c) s.add(c); });
      });
      return Array.from(s).slice(0, 30);
    })(),
  };
  return out;
})()
"""


class DiagnosticDriver:
    """Last-resort fallback. Writes a structured report and aborts."""

    def __init__(self, report: str, mode: str):
        self._report = report
        self._mode = mode
        # Set by the executor BEFORE setup() is called, pointing at the
        # session output dir. Defaults to cwd for tests that don't set it.
        self._report_dir: Path = Path.cwd()

    @classmethod
    async def can_handle(cls, page: Page) -> bool:
        # Never matches via the registry — invoked directly as a fallback.
        return False

    @classmethod
    async def for_unknown_platform(cls, page: Page) -> "DiagnosticDriver":
        report = await cls._build_unknown_platform_report(page)
        return cls(report=report, mode="unknown_platform")

    @classmethod
    async def for_version_mismatch(
        cls, page: Page, err: UnsupportedVersionError,
    ) -> "DiagnosticDriver":
        report = await cls._build_version_mismatch_report(page, err)
        return cls(report=report, mode="version_mismatch")

    @staticmethod
    async def _fingerprint(page: Page) -> Mapping[str, Any]:
        try:
            return await page.evaluate(_FINGERPRINT_JS)
        except Exception as e:
            logger.warning("DiagnosticDriver fingerprint failed: %s", e)
            return {"jspsych_keys": [], "ids": [], "classes": []}

    @classmethod
    async def _build_unknown_platform_report(cls, page: Page) -> str:
        url = getattr(page, "url", "<unknown>")
        title = await page.title()
        fp = await cls._fingerprint(page)
        return f"""# Driver needed — unknown platform

The bot encountered a page that no registered driver claimed via
`can_handle`. Below is a fingerprint of the page; use it to write a
new driver under `src/experiment_bot/drivers/<platform_name>/`.

## Page

- URL: `{url}`
- Title: `{title}`

## window.* keys matching /jspsych|psychojs|cognition|response|trial|stimulus|experiment/i

```
{json.dumps(fp.get("jspsych_keys", []), indent=2)}
```

## Top DOM IDs

```
{json.dumps(fp.get("ids", []), indent=2)}
```

## Top class tokens

```
{json.dumps(fp.get("classes", []), indent=2)}
```

## Next steps

1. Identify the platform: jsPsych, cognition.run, PsychoJS, or custom.
2. Create `src/experiment_bot/drivers/<platform>/` and implement
   `PlatformDriver` (see `drivers/base.py` for the contract).
3. Vendor selective source files under `vendor/<platform>/<version>/`
   if the platform is open source. Update `vendor/LICENSES.md`.
4. Register the new driver class in
   `src/experiment_bot/drivers/registry.py`'s `REGISTERED_DRIVERS`
   list (specific drivers first).
5. Re-run the bot against this URL.
"""

    @classmethod
    async def _build_version_mismatch_report(
        cls, page: Page, err: UnsupportedVersionError,
    ) -> str:
        url = getattr(page, "url", "<unknown>")
        title = await page.title()
        return f"""# Driver needed — unsupported platform version

A registered driver matched this page's platform but does not have
anchored support for the platform's current version. Add the missing
anchors and update the driver's compatibility table.

## Page

- URL: `{url}`
- Title: `{title}`

## Version mismatch

- Detected: `{err.detected_version}`
- Supported by current driver: `{", ".join(err.supported_versions)}`
- Missing anchor files: `{", ".join(err.missing_anchors)}`

## Next steps

1. Vendor the missing anchor files for the new version (typically
   the keyboard listener API, plugin lifecycle, and data export
   modules from the platform's source).
2. Update the driver's version-compatibility table to include the
   new version.
3. Add tests covering any API differences from previously-supported
   versions.
4. Re-run the bot against this URL.
"""

    async def setup(self, page: Page) -> None:
        """Write the diagnostic report to disk and raise. The executor's
        catch block aborts the session cleanly."""
        report_filename = (
            "driver_needed.md" if self._mode == "unknown_platform"
            else "driver_version_needed.md"
        )
        path = self._report_dir / report_filename
        path.write_text(self._report)
        logger.warning(
            "DiagnosticDriver wrote %s; aborting session.", path,
        )
        kind = f"diagnostic_{self._mode}"
        raise DriverError(
            kind=kind,
            context={"report_path": str(path), "mode": self._mode},
            recoverable=False,
        )

    # All operational methods raise DriverError. setup() is the only
    # method the executor calls before discovering the diagnostic mode.

    async def loop_state(self, page: Page) -> TrialLoopState:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def navigate(self, page: Page) -> NavigationOutcome:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def get_trial_context(self, page: Page) -> TrialContext:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def deliver_response(
        self, page: Page, response: str | None, rt_ms: float | None,
    ) -> DeliveryResult:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def wait_for_trial_end(self, page: Page) -> None:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def wait_for_completion(self, page: Page) -> None:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def retrieve_data(self, page: Page) -> ExperimentData:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def teardown(self, page: Page) -> None:
        # No-op — safe to call even after setup raised.
        return None
