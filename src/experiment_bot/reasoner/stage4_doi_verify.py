from __future__ import annotations
import asyncio
import copy
import logging
from datetime import datetime, timezone
from experiment_bot.reasoner.openalex import verify_doi
from experiment_bot.taskcard.types import ReasoningStep

logger = logging.getLogger(__name__)


def _iter_citations(partial: dict):
    for section in ("response_distributions", "temporal_effects"):
        for k, v in partial.get(section, {}).items():
            for cit in v.get("citations", []):
                yield cit
    for cit in partial.get("between_subject_jitter", {}).get("citations", []):
        yield cit


async def run_stage4(partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 4: verify each citation's DOI via OpenAlex. Non-blocking on failures.

    Malformed citations (missing doi/authors/year) are skipped with a warning
    rather than raising KeyError.
    """
    result = copy.deepcopy(partial)

    async def _verify_one(cit: dict):
        doi = cit.get("doi")
        authors = cit.get("authors")
        year = cit.get("year")
        if not doi or authors is None or year is None:
            logger.warning(
                "stage4: skipping malformed citation (missing doi/authors/year): %r",
                {k: cit.get(k) for k in ("doi", "authors", "year", "title")},
            )
            cit["doi_verified"] = False
            cit["doi_verified_at"] = datetime.now(timezone.utc).isoformat()
            return
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            logger.warning("stage4: citation year is not int-convertible: %r", year)
            cit["doi_verified"] = False
            cit["doi_verified_at"] = datetime.now(timezone.utc).isoformat()
            return
        ok, _meta = await verify_doi(
            doi=doi,
            expected_authors=authors,
            expected_year=year_int,
        )
        cit["doi_verified"] = bool(ok)
        cit["doi_verified_at"] = datetime.now(timezone.utc).isoformat()

    citations = list(_iter_citations(result))
    if citations:
        await asyncio.gather(*[_verify_one(c) for c in citations])

    n_total = len(citations)
    n_verified = sum(1 for c in citations if c.get("doi_verified"))
    n_skipped = sum(
        1 for c in citations
        if not c.get("doi") or c.get("authors") is None or c.get("year") is None
    )
    step = ReasoningStep(
        step="stage4_doi_verify",
        inference=(
            f"Submitted {n_total} citations to OpenAlex; "
            f"{n_verified} verified, {n_skipped} skipped (malformed)."
        ),
        evidence_lines=[],
        confidence="high",
    )
    return result, step
