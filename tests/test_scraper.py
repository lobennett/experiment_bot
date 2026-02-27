import pytest
from unittest.mock import AsyncMock, patch

from experiment_bot.core.scraper import scrape_experiment_source
from experiment_bot.core.config import SourceBundle


@pytest.mark.asyncio
async def test_scrape_basic_html():
    """Scraper should fetch URL HTML and return a SourceBundle."""
    html = '<html><body><script src="/js/experiment.js"></script></body></html>'

    mock_response = AsyncMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None

    mock_js_response = AsyncMock()
    mock_js_response.text = "var x = 1;"
    mock_js_response.status_code = 200
    mock_js_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[mock_response, mock_js_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("experiment_bot.core.scraper.httpx.AsyncClient", return_value=mock_client):
        bundle = await scrape_experiment_source(
            url="https://example.com/experiment/",
            hint="A stop signal task",
        )

    assert isinstance(bundle, SourceBundle)
    assert bundle.url == "https://example.com/experiment/"
    assert bundle.hint == "A stop signal task"
    assert "experiment.js" in bundle.source_files
    assert bundle.description_text == html


@pytest.mark.asyncio
async def test_scrape_resolves_relative_urls():
    """Scraper should resolve relative URLs against the base URL."""
    from urllib.parse import urljoin
    assert urljoin("https://example.com/exp/", "js/experiment.js") == "https://example.com/exp/js/experiment.js"
    assert urljoin("https://example.com/exp/", "../css/style.css") == "https://example.com/css/style.css"
