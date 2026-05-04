from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
from experiment_bot.reasoner.openalex import verify_doi
from experiment_bot.taskcard.types import ReasoningStep


def _iter_citations(partial: dict):
    for section in ("response_distributions", "temporal_effects"):
        for k, v in partial.get(section, {}).items():
            for cit in v.get("citations", []):
                yield cit
    for cit in partial.get("between_subject_jitter", {}).get("citations", []):
        yield cit


async def run_stage4(partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 4: verify each citation's DOI via OpenAlex. Non-blocking on failures."""
    result = copy.deepcopy(partial)

    async def _verify_one(cit: dict):
        ok, _meta = await verify_doi(
            doi=cit["doi"],
            expected_authors=cit["authors"],
            expected_year=int(cit["year"]),
        )
        cit["doi_verified"] = bool(ok)
        cit["doi_verified_at"] = datetime.now(timezone.utc).isoformat()

    citations = list(_iter_citations(result))
    if citations:
        await asyncio.gather(*[_verify_one(c) for c in citations])

    n_total = len(citations)
    n_verified = sum(1 for c in citations if c.get("doi_verified"))
    step = ReasoningStep(
        step="stage4_doi_verify",
        inference=f"Submitted {n_total} citations to OpenAlex; {n_verified} verified.",
        evidence_lines=[],
        confidence="high",
    )
    return result, step
