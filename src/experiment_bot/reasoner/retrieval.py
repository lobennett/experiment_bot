from __future__ import annotations
import logging
import os
import re
from dataclasses import dataclass

import httpx

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
                    year_from: int | None, mailto: str | None) -> list[RetrievedWork]:
    params = {"search": query, "per-page": str(per_page)}
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
        ))
    return out


async def search_works(query: str, *, per_page: int = 5,
                       year_from: int | None = None,
                       mailto: str | None = None) -> list[RetrievedWork]:
    """Search OpenAlex; fall back to CrossRef when OpenAlex yields nothing.
    NEVER raises — any network/parse error returns []."""
    mailto = mailto or os.environ.get("EXPERIMENT_BOT_OPENALEX_MAILTO")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            works = await _openalex(client, query, per_page, year_from, mailto)
            if not works:
                works = await _crossref(client, query, per_page, mailto)
            return works
    except Exception as e:
        logger.warning("retrieval.search_works failed for %r: %s", query, e)
        return []
