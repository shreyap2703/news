"""Google News RSS retrieval with a 10-minute cache and bundled fallback headlines."""

import html
import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse

import requests

from .models import Article

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
REQUEST_TIMEOUT_SECONDS = 20
CACHE_TTL_SECONDS = 600
# Retry the live feed sooner when it was unavailable.
FALLBACK_CACHE_TTL_SECONDS = 60


@dataclass(frozen=True)
class NewsCategory:
    id: str
    label: str
    topic: str


CATEGORIES = (
    NewsCategory("world", "Top World News", "world news"),
    NewsCategory("india", "India", "India news"),
    NewsCategory("ipl", "IPL", "Indian Premier League cricket news"),
    NewsCategory("ai-technology", "AI & Technology", "AI technology news"),
    NewsCategory("business-economy", "Business & Economy", "global business economy news"),
    NewsCategory("science-space", "Science & Space", "science space news"),
    NewsCategory("politics-geopolitics", "Politics & Geopolitics", "global politics geopolitics news"),
)
CATEGORIES_BY_ID = {category.id: category for category in CATEGORIES}


@dataclass(frozen=True)
class NewsResult:
    articles: tuple[Article, ...]
    using_fallback: bool


def _load_fallback_headlines() -> dict[str, tuple[Article, ...]]:
    path = Path(__file__).with_name("fallback_headlines.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {category_id: tuple(Article(**item) for item in items) for category_id, items in raw.items()}


FALLBACK_HEADLINES = _load_fallback_headlines()

_CONTEXT_RULES = (
    (
        re.compile(r"\b(market|inflation|economy|trade)", re.IGNORECASE),
        "Markets and policymakers are tracking this issue closely, with attention on growth, pricing, "
        "and how the story may affect business conditions and regional stability.",
    ),
    (
        # "ai" must be a whole word so headlines containing "said" or "Ukraine" are not tagged as tech.
        re.compile(r"\b(ai\b|technology|model|software|digital)", re.IGNORECASE),
        "Technology leaders are following this development because it could shape adoption, competition, "
        "and the pace of innovation across the digital economy.",
    ),
    (
        re.compile(r"\b(election|government|diplomacy|policy|politics)", re.IGNORECASE),
        "The story is being watched closely in political and policy circles because it may affect public "
        "trust, government action, and diplomatic positioning.",
    ),
    (
        re.compile(r"\b(space|science|research|climate|weather)", re.IGNORECASE),
        "Researchers and public agencies are monitoring this development because it could influence "
        "scientific understanding, safety planning, and long-term resilience.",
    ),
    (
        re.compile(r"\b(india|regional|infrastructure|development)", re.IGNORECASE),
        "This story matters for local planning and regional momentum, with attention on growth, services, "
        "and how policy decisions affect daily life.",
    ),
)

_TAG_RE = re.compile(r"<[^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\w+")

_cache: dict[tuple[str, int], tuple[float, NewsResult]] = {}
_cache_lock = threading.Lock()


def get_news(category: NewsCategory, hours: int, limit: int, refresh: bool = False) -> NewsResult:
    """Return up to ``limit`` headlines, served from cache for up to 10 minutes unless ``refresh`` is set."""
    key = (category.id, hours)
    with _cache_lock:
        if refresh:
            _cache.clear()
        cached = _cache.get(key)

    if cached is not None and cached[0] > time.monotonic():
        result = cached[1]
    else:
        live_articles = fetch_google_news(category, hours)
        if live_articles:
            result, ttl = NewsResult(tuple(live_articles), using_fallback=False), CACHE_TTL_SECONDS
        else:
            result = NewsResult(FALLBACK_HEADLINES.get(category.id, ()), using_fallback=True)
            ttl = FALLBACK_CACHE_TTL_SECONDS
        with _cache_lock:
            _cache[key] = (time.monotonic() + ttl, result)

    return NewsResult(result.articles[:limit], result.using_fallback)


def google_news_url(topic: str, hours: int) -> str:
    window = f"{hours // 24}d" if hours % 24 == 0 else f"{hours}h"
    query = urlencode({"q": f"{topic} when:{window}", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"{GOOGLE_NEWS_RSS_URL}?{query}"


def fetch_google_news(category: NewsCategory, hours: int) -> list[Article]:
    """Fetch English headlines from Google News RSS; returns an empty list when the feed is unavailable."""
    try:
        response = requests.get(
            google_news_url(category.topic, hours),
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        logger.warning("Google News RSS is unavailable for %r: %s", category.topic, exc)
        return []

    articles = []
    for entry in root.findall("./channel/item"):
        article = _parse_item(entry, category)
        if article is not None:
            articles.append(article)
    return articles


def _parse_item(entry: ET.Element, category: NewsCategory) -> Optional[Article]:
    source_element = entry.find("source")
    source = clean_text(source_element.text if source_element is not None else None) or "Google News"
    raw_title = clean_text(entry.findtext("title"))
    if not raw_title:
        return None

    url = _http_url(entry.findtext("link"))
    title = display_title(_strip_source_suffix(raw_title, source), source, url)
    summary = clean_text(entry.findtext("description"))
    # Google News descriptions usually just repeat the headline and publisher, so fall back to generated context.
    if not summary or _normalize(summary).startswith(_normalize(title)):
        summary = build_context(title, category.label)

    return Article(
        title=title,
        source=source,
        published=to_iso8601(entry.findtext("pubDate")),
        url=url,
        context=summary,
    )


def clean_text(value: Optional[str]) -> str:
    text = html.unescape(_TAG_RE.sub(" ", value or ""))
    return _WHITESPACE_RE.sub(" ", text).strip()


def display_title(title: str, source: str, url: str) -> str:
    """Replace placeholder titles such as "None" with a readable label derived from the URL or source."""
    if title and title.lower() not in {"none", "null"}:
        return title
    path = urlparse(url).path.strip("/") if url else ""
    if path:
        return f"{source} update: {path.replace('-', ' ').replace('/', ' ').title()}"
    return f"Headline from {source}"


def build_context(title: str, category_label: str) -> str:
    for pattern, context in _CONTEXT_RULES:
        if pattern.search(title):
            return context
    return (
        f"This developing update is relevant to {category_label.lower()} coverage and is being watched "
        "for broader economic, political, or social impact."
    )


def to_iso8601(value: Optional[str]) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_source_suffix(title: str, source: str) -> str:
    suffix = f" - {source}"
    if title.endswith(suffix) and len(title) > len(suffix):
        return title[: -len(suffix)].rstrip()
    return title


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _http_url(value: Optional[str]) -> str:
    url = (value or "").strip()
    return url if urlparse(url).scheme in {"http", "https"} else ""
