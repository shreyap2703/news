"""Offline tests for the FastAPI backend: Google News and OpenAI are replaced with fakes."""

import httpx
import openai
import pytest
import requests
from fastapi.testclient import TestClient

from api import main, news

RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Markets rally as inflation cools - Reuters</title>
    <link>https://news.google.com/rss/articles/abc?oc=5</link>
    <pubDate>Thu, 12 Nov 2026 13:55:20 GMT</pubDate>
    <description>&lt;a href="https://news.google.com/rss/articles/abc"&gt;Markets rally as inflation cools&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Reuters&lt;/font&gt;</description>
    <source url="https://www.reuters.com">Reuters</source>
  </item>
  <item>
    <title>Officials said talks will resume - AP News</title>
    <link>javascript:alert(1)</link>
    <pubDate>Thu, 12 Nov 2026 12:00:00 GMT</pubDate>
    <description>Negotiators from both sides will meet next week.</description>
    <source url="https://apnews.com">AP News</source>
  </item>
  <item>
    <title></title>
    <link>https://example.com/untitled</link>
  </item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Start every test with an empty cache and a feed that fails like a network outage."""
    news._cache.clear()

    def no_network(*args, **kwargs):
        raise requests.ConnectionError("network access is disabled in tests")

    monkeypatch.setattr(news.requests, "get", no_network)


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def feed_requests(monkeypatch):
    """Serve RSS_SAMPLE for every feed request and record the requested URLs."""
    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return FakeResponse(RSS_SAMPLE)

    monkeypatch.setattr(news.requests, "get", fake_get)
    return urls


def test_categories_lists_every_section(client):
    response = client.get("/api/categories")

    assert response.status_code == 200
    assert [category["id"] for category in response.json()] == [category.id for category in news.CATEGORIES]


def test_news_parses_google_news_rss(client, feed_requests):
    response = client.get("/api/news", params={"category": "business-economy", "hours": 6})

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == {"id": "business-economy", "label": "Business & Economy"}
    assert body["usingFallback"] is False
    assert len(body["articles"]) == 2
    first, second = body["articles"]
    assert first == {
        "title": "Markets rally as inflation cools",
        "source": "Reuters",
        "published": "2026-11-12T13:55:20Z",
        "url": "https://news.google.com/rss/articles/abc?oc=5",
        "language": "en",
        "context": news.build_context("Markets rally as inflation cools", "Business & Economy"),
    }
    assert second["title"] == "Officials said talks will resume"
    assert second["url"] == ""
    assert second["context"] == "Negotiators from both sides will meet next week."
    assert "when%3A6h" in feed_requests[0]


@pytest.mark.parametrize(
    "feed_response",
    [
        pytest.param(None, id="network-error"),
        pytest.param(FakeResponse(b"", status_code=503), id="http-error"),
        pytest.param(FakeResponse(b"<html>not rss"), id="invalid-xml"),
    ],
)
def test_news_falls_back_when_feed_is_unavailable(client, monkeypatch, feed_response):
    if feed_response is not None:
        monkeypatch.setattr(news.requests, "get", lambda url, **kwargs: feed_response)

    response = client.get("/api/news", params={"category": "india", "limit": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["usingFallback"] is True
    assert [article["title"] for article in body["articles"]] == [
        article.title for article in news.FALLBACK_HEADLINES["india"][:3]
    ]


def test_news_is_cached_until_refresh(client, feed_requests):
    params = {"category": "world", "hours": 24}

    client.get("/api/news", params=params)
    client.get("/api/news", params={**params, "limit": 1})
    assert len(feed_requests) == 1

    client.get("/api/news", params={**params, "refresh": "true"})
    assert len(feed_requests) == 2


@pytest.mark.parametrize(
    ("params", "status_code"),
    [
        ({"category": "unknown"}, 404),
        ({"category": "world", "limit": 51}, 422),
        ({"category": "world", "hours": 0}, 422),
        ({}, 422),
    ],
)
def test_news_rejects_invalid_queries(client, params, status_code):
    assert client.get("/api/news", params=params).status_code == status_code


@pytest.mark.parametrize(("hours", "window"), [(6, "when%3A6h"), (24, "when%3A1d"), (72, "when%3A3d")])
def test_feed_url_uses_look_back_window(hours, window):
    assert window in news.google_news_url("world news", hours)


def test_context_keywords_match_whole_words():
    assert news.build_context("AI chips are in short supply", "Top World News").startswith("Technology leaders")
    assert news.build_context("Officials said Ukraine talks resume", "Top World News").startswith(
        "This developing update"
    )


def test_briefing_requires_api_key(client):
    assert client.post("/api/briefing", json={"category": "world", "apiKey": ""}).status_code == 422


def test_briefing_summarizes_current_headlines(client, monkeypatch):
    calls = []

    def fake_summarize(articles, api_key):
        calls.append((len(articles), api_key))
        return "**Briefing**"

    monkeypatch.setattr(main, "summarize_headlines", fake_summarize)

    response = client.post("/api/briefing", json={"category": "world", "limit": 4, "apiKey": "sk-test"})

    assert response.status_code == 200
    assert response.json() == {"briefing": "**Briefing**"}
    assert calls == [(4, "sk-test")]


def test_briefing_reports_openai_errors(client, monkeypatch):
    def failing_summarize(articles, api_key):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))

    monkeypatch.setattr(main, "summarize_headlines", failing_summarize)

    response = client.post("/api/briefing", json={"category": "world", "apiKey": "sk-test"})

    assert response.status_code == 502
    assert response.json() == {"detail": "Could not generate the AI briefing: Connection error."}
