from __future__ import annotations

import logging
from dataclasses import dataclass

from playwright.async_api import Page

from experiment_bot.core.config import TaskConfig, StimulusConfig

logger = logging.getLogger(__name__)


@dataclass
class StimulusMatch:
    stimulus_id: str
    response_key: str | None
    condition: str


@dataclass
class _StimulusRule:
    id: str
    method: str
    selector: str
    alt_method: str
    pattern: str
    response_key: str | None
    condition: str


class StimulusLookup:
    def __init__(self, config: TaskConfig):
        self._rules: list[_StimulusRule] = []
        for stim in config.stimuli:
            self._rules.append(_StimulusRule(
                id=stim.id,
                method=stim.detection.method,
                selector=stim.detection.selector,
                alt_method=stim.detection.alt_method,
                pattern=stim.detection.pattern,
                response_key=stim.response.key,
                condition=stim.response.condition,
            ))

    async def identify(self, page: Page) -> StimulusMatch | None:
        for rule in self._rules:
            matched = await self._check_rule(page, rule)
            if matched:
                return StimulusMatch(
                    stimulus_id=rule.id,
                    response_key=rule.response_key,
                    condition=rule.condition,
                )
        return None

    async def _check_rule(self, page: Page, rule: _StimulusRule) -> bool:
        try:
            if rule.method == "dom_query":
                element = await page.query_selector(rule.selector)
                return element is not None
            elif rule.method == "js_eval":
                result = await page.evaluate(rule.selector)
                return bool(result)
            elif rule.method == "text_content":
                element = await page.query_selector(rule.selector)
                if element:
                    text = await element.text_content()
                    return rule.pattern in (text or "")
                return False
            elif rule.method == "canvas_state":
                result = await page.evaluate(rule.selector)
                return bool(result)
        except Exception as e:
            # Page context may be torn down by navigation
            logger.debug(f"Rule check failed for {rule.id}: {e}")
        return False
