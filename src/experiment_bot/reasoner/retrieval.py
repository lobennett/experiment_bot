from __future__ import annotations
import logging
import os
import re
from dataclasses import dataclass

import httpx

from experiment_bot.reasoner.openalex import _title_overlap

logger = logging.getLogger(__name__)

_OPENALEX = "https://api.openalex.org/works"
_CROSSREF = "https://api.crossref.org/works"
_ABSTRACT_CAP = 2000


@dataclass
class RetrievedWork:
    doi: str | None
    authors: str
    year: int | None
    title: str
    abstract: str
    source: str  # "openalex" | "crossref"
    cited_by_count: int = 0


def _norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.strip().replace("https://doi.org/", "").replace("http://doi.org/", "").lower() or None


def _reconstruct_abstract(inv: dict | None) -> str:
    """Rebuild text from OpenAlex abstract_inverted_index {token: [positions]}."""
    if not inv:
        return ""
    positioned: list[tuple[int, str]] = []
    for token, posns in inv.items():
        for p in posns:
            positioned.append((p, token))
    positioned.sort(key=lambda t: t[0])
    return " ".join(tok for _, tok in positioned)[:_ABSTRACT_CAP]


def _oa_authors(work: dict) -> str:
    names = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
    return ", ".join(n for n in names if n)


def _strip_jats(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()[:_ABSTRACT_CAP]


async def _openalex(client: httpx.AsyncClient, query: str, per_page: int,
                    year_from: int | None, mailto: str | None,
                    sort_by_citations: bool) -> list[RetrievedWork]:
    params = {"search": query, "per-page": str(per_page)}
    if sort_by_citations:
        params["sort"] = "cited_by_count:desc"
    if year_from:
        params["filter"] = f"from_publication_date:{year_from}-01-01"
    if mailto:
        params["mailto"] = mailto
    resp = await client.get(_OPENALEX, params=params)
    if resp.status_code != 200:
        return []
    out: list[RetrievedWork] = []
    for w in resp.json().get("results", []):
        out.append(RetrievedWork(
            doi=_norm_doi(w.get("doi")),
            authors=_oa_authors(w),
            year=w.get("publication_year"),
            title=w.get("title") or w.get("display_name") or "",
            abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
            source="openalex",
            cited_by_count=w.get("cited_by_count") or 0,
        ))
    return out


async def _crossref(client: httpx.AsyncClient, query: str, per_page: int,
                    mailto: str | None) -> list[RetrievedWork]:
    params = {"query": query, "rows": str(per_page)}
    if mailto:
        params["mailto"] = mailto
    resp = await client.get(_CROSSREF, params=params)
    if resp.status_code != 200:
        return []
    out: list[RetrievedWork] = []
    for it in resp.json().get("message", {}).get("items", []):
        title = (it.get("title") or [""])[0]
        year = None
        dp = it.get("published", {}).get("date-parts", [[None]])
        if dp and dp[0]:
            year = dp[0][0]
        authors = ", ".join(
            f"{a.get('family','')}, {a.get('given','')}".strip(", ")
            for a in it.get("author", [])
        )
        out.append(RetrievedWork(
            doi=_norm_doi(it.get("DOI")),
            authors=authors,
            year=year,
            title=title,
            abstract=_strip_jats(it.get("abstract", "")),
            source="crossref",
            cited_by_count=it.get("is-referenced-by-count") or 0,
        ))
    return out


async def search_works(query: str, *, per_page: int = 5,
                       year_from: int | None = None,
                       mailto: str | None = None,
                       sort_by_citations: bool = True) -> list[RetrievedWork]:
    """Search OpenAlex; fall back to CrossRef when OpenAlex yields nothing.
    OpenAlex results are sorted by citation count (canonical works first) unless
    sort_by_citations=False. NEVER raises — any network/parse error returns []."""
    mailto = mailto or os.environ.get("EXPERIMENT_BOT_OPENALEX_MAILTO")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            works = await _openalex(client, query, per_page, year_from, mailto,
                                    sort_by_citations)
            if not works:
                works = await _crossref(client, query, per_page, mailto)
            return works
    except Exception as e:
        logger.warning("retrieval.search_works failed for %r: %s", query, e)
        return []


async def verify_by_title(authors: str, year: int | None, title: str, *,
                          mailto: str | None = None,
                          title_threshold: float = 0.5) -> RetrievedWork | None:
    """Look a paper up BY TITLE (a model-PROPOSED candidate; the model supplies no
    DOI). Search OpenAlex/CrossRef by title (relevance-ordered), then accept the
    best-overlapping hit only if it has a real DOI, its title-token Jaccard overlap
    is >= title_threshold, and (year is None or the hit's year is within ±1). Return
    a RetrievedWork built from the API's own DOI + abstract, or None. NEVER raises.

    A hallucinated candidate returns no acceptable match, so nothing enters the
    pool. The DOI always comes from the API, never from the model."""
    if not title or not title.strip():
        return None
    try:
        y = int(year) if year is not None else None
    except (TypeError, ValueError):
        y = None
    works = await search_works(title, per_page=5, sort_by_citations=False, mailto=mailto)
    best: RetrievedWork | None = None
    best_overlap = 0.0
    for w in works:
        if not w.doi:
            continue
        overlap = _title_overlap(title, w.title)
        if overlap < title_threshold:
            continue
        if y is not None and w.year is not None and abs(int(w.year) - y) > 1:
            continue
        if overlap > best_overlap:
            best_overlap, best = overlap, w
    return best
