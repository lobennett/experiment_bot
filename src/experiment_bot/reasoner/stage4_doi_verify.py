from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
from experiment_bot.reasoner.openalex import verify_doi


def _iter_citations(partial: dict):
    for section in ("response_distributions", "temporal_effects"):
        for k, v in partial.get(section, {}).items():
            for cit in v.get("citations", []):
                yield cit
    for cit in partial.get("between_subject_jitter", {}).get("citations", []):
        yield cit


async def run_stage4(partial: dict) -> dict:
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
    return result
