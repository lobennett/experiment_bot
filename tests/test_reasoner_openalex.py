import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from experiment_bot.reasoner.openalex import verify_doi


@pytest.mark.asyncio
async def test_verify_doi_returns_true_on_match():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "title": "Effective analysis of reaction time data",
        "publication_year": 2008,
        "authorships": [{"author": {"display_name": "Robert Whelan"}}],
    })
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, meta = await verify_doi(
            doi="10.1016/j.cognition.2008.07.011",
            expected_authors="Whelan, R.",
            expected_year=2008,
        )
    assert ok is True
    assert meta["title"] == "Effective analysis of reaction time data"


@pytest.mark.asyncio
async def test_verify_doi_returns_false_on_404():
    fake_response = MagicMock()
    fake_response.status_code = 404
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, meta = await verify_doi("10.0000/nonexistent", "Anyone", 2020)
    assert ok is False


@pytest.mark.asyncio
async def test_verify_doi_returns_false_on_year_mismatch():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "title": "Some paper",
        "publication_year": 1999,
        "authorships": [{"author": {"display_name": "Jane Doe"}}],
    })
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, _ = await verify_doi("10.0000/x", "Doe, J.", 2020)
    assert ok is False


@pytest.mark.asyncio
async def test_verify_doi_returns_false_on_network_error():
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(side_effect=Exception("network down"))
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, meta = await verify_doi("10.0000/x", "Anyone", 2020)
    assert ok is False


@pytest.mark.asyncio
async def test_verify_doi_returns_false_on_author_mismatch():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "title": "x",
        "publication_year": 2020,
        "authorships": [{"author": {"display_name": "Some Other Person"}}],
    })
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, _ = await verify_doi("10.0000/x", "Smith, J.", 2020)
    assert ok is False
