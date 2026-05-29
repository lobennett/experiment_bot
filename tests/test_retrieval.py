import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from experiment_bot.reasoner.retrieval import search_works, _reconstruct_abstract, RetrievedWork


def test_reconstruct_abstract_from_inverted_index():
    inv = {"Stroop": [0], "interference": [1], "is": [2], "robust": [3]}
    assert _reconstruct_abstract(inv) == "Stroop interference is robust"
    assert _reconstruct_abstract(None) == ""
    assert _reconstruct_abstract({}) == ""


def _mk_client(json_obj, status=200):
    resp = MagicMock(); resp.status_code = status; resp.json = MagicMock(return_value=json_obj)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_search_works_parses_openalex_hit_with_abstract():
    oa = {"results": [{
        "doi": "https://doi.org/10.1037/x", "publication_year": 2009,
        "title": "Ex-Gaussian analysis of Stroop RT",
        "authorships": [{"author": {"display_name": "Jane Heathcote"}}],
        "abstract_inverted_index": {"mu": [0], "near": [1], "500": [2], "ms": [3]},
    }]}
    with patch("httpx.AsyncClient", return_value=_mk_client(oa)):
        works = await search_works("stroop ex-gaussian", per_page=5)
    assert len(works) == 1
    w = works[0]
    assert w.doi == "10.1037/x"          # normalized: scheme/host stripped
    assert w.year == 2009 and "Heathcote" in w.authors
    assert w.abstract == "mu near 500 ms" and w.source == "openalex"


@pytest.mark.asyncio
async def test_search_works_network_error_returns_empty():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(side_effect=RuntimeError("offline"))
    with patch("httpx.AsyncClient", return_value=client):
        assert await search_works("anything") == []


@pytest.mark.asyncio
async def test_search_works_falls_back_to_crossref_when_openalex_empty():
    # OpenAlex returns no results; CrossRef returns one item.
    oa_empty = {"results": []}
    cr = {"message": {"items": [{
        "DOI": "10.1037/y", "title": ["A real review of conflict tasks"],
        "published": {"date-parts": [[2015]]},
        "author": [{"family": "Smith", "given": "J."}],
        "abstract": "<jats:p>Conflict effects summarized.</jats:p>",
    }]}}
    calls = {"n": 0}
    resp_oa = MagicMock(); resp_oa.status_code = 200; resp_oa.json = MagicMock(return_value=oa_empty)
    resp_cr = MagicMock(); resp_cr.status_code = 200; resp_cr.json = MagicMock(return_value=cr)
    async def _get(url, *a, **k):
        calls["n"] += 1
        return resp_oa if "openalex" in url else resp_cr
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(side_effect=_get)
    with patch("httpx.AsyncClient", return_value=client):
        works = await search_works("conflict tasks")
    assert len(works) == 1 and works[0].source == "crossref"
    assert works[0].doi == "10.1037/y" and "Smith" in works[0].authors
    assert "Conflict effects" in works[0].abstract  # JATS tags stripped
