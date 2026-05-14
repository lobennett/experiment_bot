from __future__ import annotations
import logging
import httpx

logger = logging.getLogger(__name__)

OPENALEX_URL = "https://api.openalex.org/works/doi:{doi}"


async def verify_doi(doi: str, expected_authors: str | list, expected_year: int) -> tuple[bool, dict]:
    """Verify a DOI exists and metadata loosely matches the citation.

    Returns (ok, metadata). ok=True iff:
      - HTTP 200 from OpenAlex
      - publication_year matches expected_year (exact)
      - At least one OpenAlex author display_name shares a surname token with expected_authors

    Network errors and 404s return (False, {}).

    expected_authors may be a string ("Smith, J., Doe, A.") or a list of
    author strings (["Smith, J.", "Doe, A."]) — Stage 3 emits both shapes
    depending on the LLM's response format. We normalize to a single string
    before tokenizing.
    """
    url = OPENALEX_URL.format(doi=doi.strip())
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return False, {}
        meta = resp.json()
    except Exception as e:
        logger.warning("OpenAlex verify failed for %s: %s", doi, e)
        return False, {}

    if meta.get("publication_year") != expected_year:
        return False, meta

    if isinstance(expected_authors, list):
        expected_authors = " ".join(str(a) for a in expected_authors)
    expected_surnames = {
        tok.strip(",.").lower()
        for tok in expected_authors.split()
        if len(tok) > 2 and tok[0].isupper()
    }
    actual_authors = " ".join(
        a["author"]["display_name"]
        for a in meta.get("authorships", [])
    ).lower()
    if expected_surnames and not any(s in actual_authors for s in expected_surnames):
        return False, meta

    return True, meta
