from __future__ import annotations
import logging
import httpx

logger = logging.getLogger(__name__)

OPENALEX_URL = "https://api.openalex.org/works/doi:{doi}"


_TITLE_STOPWORDS = {
    "the", "a", "an", "of", "and", "to", "in", "on", "for", "with",
    "is", "are", "as", "by", "at", "from", "using", "via",
}


def _title_tokens(title: str) -> set[str]:
    return {
        t for t in "".join(c.lower() if c.isalnum() else " " for c in (title or "")).split()
        if len(t) > 2 and t not in _TITLE_STOPWORDS
    }


def _title_overlap(expected: str, actual: str) -> float:
    """Jaccard overlap of content tokens between two titles (0..1)."""
    a, b = _title_tokens(expected), _title_tokens(actual)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


async def verify_doi(
    doi: str, expected_authors: str | list, expected_year: int,
    expected_title: str | None = None, title_threshold: float = 0.4,
) -> tuple[bool, dict]:
    """Verify a DOI exists AND its metadata matches the citation's claims.

    Returns (ok, metadata). ok=True iff:
      - HTTP 200 from OpenAlex
      - publication_year matches expected_year (exact)
      - At least one OpenAlex author display_name shares a surname token with
        expected_authors
      - TITLE overlap (Jaccard of content tokens) with the OpenAlex title is
        >= title_threshold WHEN expected_title is provided. This catches the
        fabrication mode where a real DOI resolves to a DIFFERENT paper than the
        citation claims (e.g. a DOI that is really an AIC-weights note cited as a
        1/f-noise paper). Without a title check, year+surname coincidence let
        wrong-paper DOIs pass — see docs/stage3-citation-integrity-2026-05.md.

    Network errors and 404s return (False, {}).

    expected_authors may be a string ("Smith, J., Doe, A.") or a list.
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

    if expected_title:
        overlap = _title_overlap(expected_title, meta.get("title") or meta.get("display_name") or "")
        if overlap < title_threshold:
            logger.warning(
                "DOI %s title mismatch (overlap %.2f < %.2f): claimed %r vs OpenAlex %r",
                doi, overlap, title_threshold, expected_title[:60], (meta.get("title") or "")[:60],
            )
            return False, meta

    return True, meta
