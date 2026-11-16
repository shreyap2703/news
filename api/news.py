"""Google News RSS retrieval with a 10-minute cache and bundled fallback headlines."""

import html
import json
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
NEWSAPI_BASE_URL = "https://newsapi.org/v2"


@dataclass(frozen=True)
class NewsCategory:
    id: str
    label: str
    topic: str


CATEGORIES = (
    NewsCategory("world", "Top World News", "world news"),
    NewsCategory("india", "India", "India news"),
    NewsCategory("ipl", "IPL", "Indian Premier League cricket"),
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
        "and how the story may affect business conditions and regional stability. The outcome could "
        "shape company planning, consumer confidence, and the broader economic outlook in the coming days.",
    ),
    (
        # "ai" must be a whole word so headlines containing "said" or "Ukraine" are not tagged as tech.
        re.compile(r"\b(ai\b|technology|model|software|digital)", re.IGNORECASE),
        "Technology leaders are following this development because it could shape adoption, competition, "
        "and the pace of innovation across the digital economy. Analysts are also watching how it may "
        "affect investment, product strategy, and public trust in new tools and platforms.",
    ),
    (
        re.compile(r"\b(election|government|diplomacy|policy|politics)", re.IGNORECASE),
        "The story is being watched closely in political and policy circles because it may affect public "
        "trust, government action, and diplomatic positioning. The broader impact could include new "
        "debates over leadership, accountability, and how institutions respond to pressure.",
    ),
    (
        re.compile(r"\b(space|science|research|climate|weather)", re.IGNORECASE),
        "Researchers and public agencies are monitoring this development because it could influence "
        "scientific understanding, safety planning, and long-term resilience. The wider significance may "
        "extend to forecasting, infrastructure, and how communities prepare for change.",
    ),
    (
        re.compile(r"\b(india|regional|infrastructure|development)", re.IGNORECASE),
        "This story matters for local planning and regional momentum, with attention on growth, services, "
        "and how policy decisions affect daily life. It may also signal how communities, businesses, and "
        "officials respond to the next phase of infrastructure and investment priorities.",
    ),
)

_TAG_RE = re.compile(r"<[^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\w+")

_cache: dict[tuple[str, int], tuple[float, NewsResult]] = {}
_cache_lock = threading.Lock()


def get_news(category: NewsCategory, hours: int, limit: int, refresh: bool = False, search: Optional[str] = None) -> NewsResult:
    """Return up to ``limit`` headlines, served from cache for up to 10 minutes unless ``refresh`` is set."""
    key = (category.id, hours, (search or '').strip().lower())
    with _cache_lock:
        if refresh:
            _cache.clear()
        cached = _cache.get(key)

    if cached is not None and cached[0] > time.monotonic():
        result = cached[1]
    else:
        live_articles = fetch_news_articles(category, hours, search=search, limit=limit)
        if live_articles:
            result, ttl = NewsResult(tuple(live_articles), using_fallback=False), CACHE_TTL_SECONDS
        else:
            result = NewsResult(FALLBACK_HEADLINES.get(category.id, ()), using_fallback=True)
            ttl = FALLBACK_CACHE_TTL_SECONDS
        with _cache_lock:
            _cache[key] = (time.monotonic() + ttl, result)

    return NewsResult(result.articles[:limit], result.using_fallback)


def google_news_url(topic: str, hours: int, search: Optional[str] = None) -> str:
    window = f"{hours // 24}d" if hours % 24 == 0 else f"{hours}h"
    q = search.strip() if search and search.strip() else topic
    query = urlencode({"q": f"{q} when:{window}", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"{GOOGLE_NEWS_RSS_URL}?{query}"


def fetch_google_news(category: NewsCategory, hours: int, search: Optional[str] = None) -> list[Article]:
    """Fetch English headlines from Google News RSS; returns an empty list when the feed is unavailable."""
    try:
        response = requests.get(
            google_news_url(category.topic, hours, search),
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

    image_url = _extract_image_url(entry, url)

    return Article(
        title=title,
        source=source,
        published=to_iso8601(entry.findtext("pubDate")),
        url=url,
        context=summary,
        image_url=image_url,
    )


def _extract_image_url(entry: ET.Element, article_url: str = "") -> str:
    for tag in ("{http://search.yahoo.com/mrss/}thumbnail", "{http://search.yahoo.com/mrss/}content"):
        element = entry.find(tag)
        if element is not None and element.get("url"):
            candidate = _http_url(element.get("url")) or ""
            if candidate and not _is_google_placeholder(candidate):
                return candidate

    if article_url:
        try:
            response = requests.get(
                article_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            )
            response.raise_for_status()
            source_url = _find_source_url(response.text)
            if source_url:
                try:
                    source_response = requests.get(
                        source_url,
                        timeout=REQUEST_TIMEOUT_SECONDS,
                        headers={"User-Agent": "Mozilla/5.0"},
                        allow_redirects=True,
                    )
                    source_response.raise_for_status()
                    match = re.search(
                        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)["\']',
                        source_response.text,
                        re.IGNORECASE,
                    )
                    if match:
                        candidate = _http_url(match.group(1))
                        if candidate and not _is_google_placeholder(candidate):
                            return candidate
                except (requests.RequestException, ValueError):
                    logger.warning("Could not read publisher image metadata for %s", source_url)

            match = re.search(
                r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)["\']',
                response.text,
                re.IGNORECASE,
            )
            if match:
                candidate = _http_url(match.group(1))
                if candidate and not _is_google_placeholder(candidate):
                    return candidate
        except (requests.RequestException, ValueError):
            logger.warning("Could not read article image metadata for %s", article_url)

    return ""


def _find_source_url(html_text: str) -> str:
    patterns = [
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        r'"(?:sourceUrl|sourceURL|articleUrl|articleURL|originalUrl|originalURL|url)"\s*:\s*"([^"\\]+)"',
        r'"(?:sourceUrl|sourceURL|articleUrl|articleURL|originalUrl|originalURL|url)"\s*:\s*"([^"\\]+)"',
    ]

    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            candidate = _http_url(match.group(1))
            if candidate and not _is_google_placeholder(candidate):
                return candidate

    # Some pages expose the real source article in JSON-LD under a generic "url" field.
    for script in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, flags=re.IGNORECASE | re.DOTALL):
        match = re.search(r'"url"\s*:\s*"([^"\\]+)"', script)
        if match:
            candidate = _http_url(match.group(1))
            if candidate and not _is_google_placeholder(candidate):
                return candidate

    return ""


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
    clean_title = re.sub(r"\s+", " ", (title or "").strip())
    clean_title = re.sub(r"^(?:live|latest|breaking|top|news|update|report|reports)\s*[-:–—]?", "", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"^(?:[A-Za-z0-9 &.]+?)\s+-\s+", "", clean_title, count=1)
    clean_title = clean_title.strip().strip("-:–—")

    if not clean_title:
        return (
            f"This report follows {category_label.lower()} developments and highlights what is changing, who is affected, "
            "and why the update matters right now. It explains the immediate stakes for communities, institutions, and markets, "
            "while placing the latest event in a broader context of public pressure, political response, and shifting expectations. "
            "The story also looks at the decisions, statements, and pressures shaping the next steps, as well as the wider consequences "
            "for confidence, planning, and accountability in the days ahead. The update matters because it can reshape how people respond, "
            "how leaders act, and how institutions prepare for the fallout, ripple effects, and follow-up developments that may come next."
        )

    return (
        f"The article focuses on {clean_title.lower()}. It explains what changed, why it matters now, and which actors are most directly involved. The story unpacks the immediate circumstances behind the development, the decisions or events that triggered it, and the pressure points influencing the wider response. It also connects the issue to broader concerns such as public trust, economic conditions, political accountability, or institutional strategy, depending on the subject. In practical terms, the coverage aims to show who is affected, what is at stake, and how the situation could evolve in the coming hours, days, or weeks. It explains the context behind the latest move, the people or institutions driving it, and whether the issue is likely to intensify, settle, or reshape a larger trend. The piece is valuable because it situates a single headline inside a wider pattern, revealing the short-term consequences and the longer-term risk, opportunity, or uncertainty that follows. This matters because the outcome may shape policy choices, business planning, public opinion, or the way institutions react to unfolding events in the near future."
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


def _is_google_placeholder(url: str) -> bool:
    lowered = url.lower()
    if 'googleusercontent.com' in lowered or 'news.google.com' in lowered or 'gstatic.com' in lowered:
        return True
    return False


def _newsapi_key() -> str:
    return (os.environ.get("NEWSAPI_KEY") or "").strip()


def fetch_news_articles(category: NewsCategory, hours: int, search: Optional[str] = None, limit: int = 30) -> list[Article]:
    api_key = _newsapi_key()
    if api_key:
        return _fetch_newsapi_articles(category, hours, search=search, limit=limit)
    return fetch_google_news(category, hours, search=search)


def _fetch_newsapi_articles(category: NewsCategory, hours: int, search: Optional[str] = None, limit: int = 30) -> list[Article]:
    params = _newsapi_params(category, search, limit)
    try:
        response = requests.get(
            f"{NEWSAPI_BASE_URL}/everything",
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("NewsAPI failed for %s: %s", category.topic, exc)
        return []

    if payload.get("status") != "ok":
        logger.warning("NewsAPI rejected request for %s: %s", category.topic, payload)
        return []

    articles: list[Article] = []
    for item in payload.get("articles", []) or []:
        title = clean_text(item.get("title"))
        url = _http_url(item.get("url"))
        if not title or not url:
            continue
        if search and not _matches_search(title, search):
            continue
        if not search and not _category_title_matches(category, title):
            continue
        published = item.get("publishedAt") or ""
        source = clean_text(item.get("source", {}).get("name")) or "NewsAPI"
        raw_context = clean_text(item.get("description"))
        context = raw_context if len(_WORD_RE.findall(raw_context)) >= 40 else build_context(title, category.label)
        image_url = _http_url(item.get("urlToImage")) or ""
        articles.append(
            Article(
                title=title,
                source=source,
                published=published,
                url=url,
                context=context,
                image_url=image_url,
            )
        )
    return articles


def _newsapi_query(category: NewsCategory, search: Optional[str] = None) -> str:
    raw = (search or '').strip()
    if raw:
        return raw
    return category.topic


def _newsapi_params(category: NewsCategory, search: Optional[str] = None, limit: int = 30) -> dict[str, str]:
    query = _newsapi_query(category, search)
    search_terms = [part for part in re.split(r"\s+", query) if part]
    q_in_title = ' '.join(search_terms[:6]) if search_terms else query
    params = {
        'q': query,
        'qInTitle': q_in_title,
        'language': 'en',
        'pageSize': str(min(limit, 30)),
        'sortBy': 'relevancy' if search else 'publishedAt',
        'apiKey': _newsapi_key(),
    }
    if search:
        params['from'] = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        params['from'] = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return params


def _search_tokens(value: Optional[str]) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) > 2]


def _matches_search(text: str, search: Optional[str]) -> bool:
    tokens = _search_tokens(search)
    if not tokens:
        return True
    haystack = (text or "").lower()
    if not haystack:
        return False
    for token in tokens:
        if not re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", haystack):
            return False
    return True


def _category_title_matches(category: NewsCategory, title: str) -> bool:
    if category.id != 'ipl':
        return True
    text = (title or '').lower()
    tokens = (
        r'\bipl\b',
        r'\bindian premier league\b',
        r'\bmumbai indians\b',
        r'\bchennai super kings\b',
        r'\broyal challengers bangalore\b',
        r'\bgujarat titans\b',
        r'\bkolkata knight riders\b',
        r'\brajasthan royals\b',
        r'\bdelhi capitals\b',
        r'\bpunjab kings\b',
        r'\bsunrisers hyderabad\b',
        r'\broyal challengers\b',
        r'(?<![a-z])rcb(?![a-z])',
        r'(?<![a-z])csk(?![a-z])',
        r'(?<![a-z])mi(?![a-z])',
        r'(?<![a-z])kkr(?![a-z])',
        r'(?<![a-z])srh(?![a-z])',
        r'(?<![a-z])dc(?![a-z])',
        r'(?<![a-z])rr(?![a-z])',
        r'(?<![a-z])pbks(?![a-z])',
        r'(?<![a-z])gt(?![a-z])',
        r'(?<![a-z])lsg(?![a-z])',
    )
    return any(re.search(pattern, text) for pattern in tokens)
