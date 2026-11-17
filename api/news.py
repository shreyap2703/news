"""Google News RSS retrieval with a 10-minute cache and bundled fallback headlines, plus story summaries built from
several outlets' coverage when a story is opened."""

import json
import logging
import os
import re
import ssl
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from http.cookiejar import DefaultCookiePolicy
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar
from urllib.parse import urlencode, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ConnectTimeoutError, MaxRetryError, NewConnectionError, ReadTimeoutError
from urllib3.util import Retry
from urllib3.util.ssl_ import create_urllib3_context

from .models import Article
from .summarizer import clean_text, headline_keywords, headline_similarity, normalize, pick_summary, summarize_coverage

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
# Google News' own endpoint for turning an article link into the publisher URL it redirects to.
GOOGLE_NEWS_DECODE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
REQUEST_TIMEOUT_SECONDS = 20
CACHE_TTL_SECONDS = 600
# Retry the live feed sooner when it was unavailable.
FALLBACK_CACHE_TTL_SECONDS = 60
NEWSAPI_BASE_URL = "https://newsapi.org/v2"

# Article pages are read in parallel, and a slow publisher must not hold a summary back for long.
ARTICLE_LOOKUP_WORKERS = 16
ARTICLE_REQUEST_TIMEOUT_SECONDS = 10
STORY_SOURCES_DEADLINE_SECONDS = 15
# When no page has arrived by the deadline, the ones still loading get this much longer, rather than no summary.
STORY_SOURCES_GRACE_SECONDS = 15
SUMMARY_WORKERS = 4
# Some publishers answer with HTTP 429 when several requests arrive at once.
MAX_REQUESTS_PER_PUBLISHER = 2
# Google News article pages are large and slow down when many are requested at once.
MAX_GOOGLE_PAGE_REQUESTS = 6
ARTICLE_CACHE_TTL_SECONDS = 6 * 60 * 60
# Look again sooner when a page was unreachable or had nothing usable.
ARTICLE_RETRY_TTL_SECONDS = 600
# A summary built before all of its pages had arrived is rebuilt soon, from the pages that arrived since.
INCOMPLETE_SUMMARY_TTL_SECONDS = 60
MAX_CACHED_ARTICLES = 2000
MAX_LISTED_ARTICLES = 5000
# Google News article pages are about 600 KB and keep the data needed to decode them near the end.
MAX_PAGE_BYTES = 2 * 1024 * 1024
# The opening paragraphs carry a news story's essentials; later ones are kept out of the summary's reach.
MAX_PAGE_PASSAGES = 14
MAX_PASSAGE_CHARS = 1500
# Photos in the page are only used when it names no preview image; smaller images are icons, logos, or avatars.
MIN_CONTENT_IMAGE_PIXELS = 200
# Other outlets' reports of the same story read for its summary, plus copies of the story itself (syndicated wire
# copy) from other outlets, which stand in when the original publisher's page cannot be read.
RELATED_SOURCES = 3
MAX_STORY_COPIES = 2
RELATED_SEARCH_HOURS = 72
RELATED_MAX_HOURS_APART = 48
# Headlines count as the same story when they share this many key terms and this share of the shorter one's terms.
RELATED_MIN_SHARED_TERMS = 3
RELATED_MIN_OVERLAP = 0.4
# Headlines this similar (Jaccard index of key terms) are copies of the same article.
COPY_MIN_SIMILARITY = 0.8
# Sites block automated requests in different ways: some refuse this short User-Agent, while others stall requests
# that claim to be a full browser. Pages are requested with the short one first and retried with the browser one.
SHORT_HEADERS = {"User-Agent": "Mozilla/5.0"}
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


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


@dataclass(frozen=True)
class ArticleDetails:
    """What the publisher's own page says about an article."""

    summary: str = ""
    image_url: str = ""
    # Descriptions first, then the article's opening paragraphs.
    passages: tuple[str, ...] = ()


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

_GOOGLE_NEWS_ARTICLE_PATH_RE = re.compile(r"/(?:rss/)?articles/([A-Za-z0-9_-]+)")
_IMAGE_META_KEYS = ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src")
# Opening a new block element ends an open paragraph, as it does in a browser.
_BLOCK_TAGS = frozenset(
    {"article", "aside", "blockquote", "div", "figure", "footer", "form", "h1", "h2", "h3", "h4", "header", "nav", "ol",
     "section", "table", "ul"}
)
# Elements whose images belong to the story rather than to the site's header, menus, or adverts.
_CONTENT_TAGS = frozenset({"article", "main", "figure"})
# Images whose address, class, or id marks them as part of the site's design rather than a photo.
_NOT_A_PHOTO_RE = re.compile(r"logo|favicon|\bicons?\b|sprite|avatar|badge|pixel|spacer|placeholder|emoji|\.svg\b|\.gif\b", re.I)
# Article pages describe themselves with Open Graph or Twitter tags or JSON-LD; "access blocked" pages do not.
_ARTICLE_MARKUP_RE = re.compile(r"""<meta[^>]+(?:property|name)\s*=\s*["']?(?:og|twitter):|application/ld\+json""", re.I)

_T = TypeVar("_T")


class _LookupCache(Generic[_T]):
    """Runs each lookup once in a thread pool, shares it while it runs, and keeps its result until it expires."""

    def __init__(self, pool: ThreadPoolExecutor, ttl: Callable[[_T], float], max_entries: int) -> None:
        self._pool = pool
        self._ttl = ttl
        self._max_entries = max_entries
        self._entries: dict[str, tuple[float, Future[_T]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, function: Callable[..., _T], *args: object) -> Future[_T]:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is not None:
                started_at, lookup = entry
                if not lookup.done() or started_at + self._ttl(lookup.result()) > now:
                    # Re-inserting keeps recently used entries last, so the least recently used are dropped first.
                    self._entries[key] = entry
                    return lookup
            lookup = self._pool.submit(function, *args)
            self._entries[key] = (now, lookup)
            while len(self._entries) > self._max_entries:
                del self._entries[next(iter(self._entries))]
        return lookup


@dataclass(frozen=True)
class _StorySummary:
    article: Article
    # Whether every page had been read when the summary was built.
    complete: bool


def _details_ttl(details: ArticleDetails) -> float:
    return ARTICLE_CACHE_TTL_SECONDS if details.passages or details.image_url else ARTICLE_RETRY_TTL_SECONDS


def _summary_ttl(summary: _StorySummary) -> float:
    if not summary.complete:
        return INCOMPLETE_SUMMARY_TTL_SECONDS
    return ARTICLE_CACHE_TTL_SECONDS if summary.article.context else ARTICLE_RETRY_TTL_SECONDS


class _QuickRetry(Retry):
    """Retries requests that failed quickly (connection refused or reset, unknown host, HTTP 502-504), but not ones
    that timed out: asking a slow site again only doubles the wait."""

    def increment(self, method: Optional[str] = None, url: Optional[str] = None, *args: Any, **kwargs: Any) -> Retry:
        error = kwargs.get("error")
        if isinstance(error, ReadTimeoutError) or (
            isinstance(error, ConnectTimeoutError) and not isinstance(error, NewConnectionError)
        ):
            raise MaxRetryError(kwargs.get("_pool"), url or "", error) from error
        return super().increment(method, url, *args, **kwargs)


class _PageAdapter(HTTPAdapter):
    """Connections for reading pages: retries brief network failures and verifies certificates as browsers do.

    Python 3.13 made certificate verification stricter (ssl.VERIFY_X509_STRICT). Corporate proxies that inspect
    TLS traffic often issue certificates that fail only those extra checks ("Missing Authority Key Identifier"),
    which left many publishers' pages unreadable. The certificate chain and host name are still verified against
    the usual CA bundle (REQUESTS_CA_BUNDLE or certifi). All connections share one SSL context, so requests made
    through it must not pass their own ``verify``.
    """

    def __init__(self) -> None:
        retries = _QuickRetry(
            total=2,
            connect=1,
            read=1,
            status=1,
            backoff_factor=0.5,
            status_forcelist=(502, 503, 504),
            allowed_methods=None,
            raise_on_status=False,
        )
        super().__init__(pool_connections=64, pool_maxsize=ARTICLE_LOOKUP_WORKERS + SUMMARY_WORKERS, max_retries=retries)

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        context = create_urllib3_context()
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kwargs["ssl_context"] = context
        super().init_poolmanager(*args, **kwargs)


_page_adapter = _PageAdapter()
_sessions = threading.local()


def _session() -> requests.Session:
    """Return this thread's session; sessions are not thread-safe, but they share one thread-safe connection pool."""
    session: Optional[requests.Session] = getattr(_sessions, "session", None)
    if session is None:
        session = _sessions.session = requests.Session()
        session.mount("https://", _page_adapter)
        session.mount("http://", _page_adapter)
        # Like separate requests, nothing is remembered between pages.
        session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
    return session


_cache: dict[tuple[str, int], tuple[float, NewsResult]] = {}
_cache_lock = threading.Lock()

# Page lookups run in their own pool: a story summary waits for several of them, so sharing one pool could deadlock.
_page_lookups: _LookupCache[ArticleDetails] = _LookupCache(
    ThreadPoolExecutor(max_workers=ARTICLE_LOOKUP_WORKERS, thread_name_prefix="article-page"), _details_ttl, MAX_CACHED_ARTICLES
)
_story_summaries: _LookupCache[_StorySummary] = _LookupCache(
    ThreadPoolExecutor(max_workers=SUMMARY_WORKERS, thread_name_prefix="story-summary"), _summary_ttl, MAX_CACHED_ARTICLES
)
_publisher_slots: dict[str, threading.BoundedSemaphore] = {}
_publisher_slots_lock = threading.Lock()
_google_page_slots = threading.BoundedSemaphore(MAX_GOOGLE_PAGE_REQUESTS)
# Article URL -> (article, whether it came from the live feed) for articles that get_news has listed. Summaries are
# only built for these, so the summary endpoint cannot be used to make the server fetch arbitrary pages.
_listed_articles: dict[str, tuple[Article, bool]] = {}
_listed_articles_lock = threading.Lock()


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

    articles = result.articles[:limit]
    _remember_listed(articles, live=not result.using_fallback)
    return NewsResult(articles, result.using_fallback)


def _remember_listed(articles: Iterable[Article], live: bool) -> None:
    with _listed_articles_lock:
        for article in articles:
            if article.url:
                _listed_articles.pop(article.url, None)
                _listed_articles[article.url] = (article, live)
        while len(_listed_articles) > MAX_LISTED_ARTICLES:
            del _listed_articles[next(iter(_listed_articles))]


def get_story_summary(article_url: str) -> Optional[Article]:
    """Return a listed article with a summary combined from several outlets' coverage, or None if it is not listed.

    Backup headlines are returned unchanged. Summaries are cached, and a summary that is already being built is
    shared rather than built twice.
    """
    with _listed_articles_lock:
        entry = _listed_articles.get(article_url)
    if entry is None:
        return None
    article, live = entry
    if not live:
        return article
    return _story_summaries.get(article_url, _summarize_story, article).result().article


def _summarize_story(article: Article) -> _StorySummary:
    """Read the story's own page and other outlets' reports of it, and summarize them together."""
    try:
        related = _related_coverage(article)
        stories = [article, *related]
        lookups = [_page_lookups.get(story.url, _read_article_page, story.url, story.title) for story in stories]
        wait(lookups, timeout=STORY_SOURCES_DEADLINE_SECONDS)
        if not any(lookup.done() and lookup.result().passages for lookup in lookups):
            wait(lookups, timeout=STORY_SOURCES_GRACE_SECONDS)
        details = [lookup.result() if lookup.done() else ArticleDetails() for lookup in lookups]
        summary = summarize_coverage([(story.title, d.passages) for story, d in zip(stories, details)])
        # Without a combined summary, the first page's own description will do: the story's, or else a copy's or
        # another report's.
        fallback = next((d.summary for d in details if d.summary), "")
        image_url = article.image_url or next((d.image_url for d in details if d.image_url), "")
        story = article.model_copy(update={"context": summary or fallback or article.context, "image_url": image_url})
        return _StorySummary(story, complete=all(lookup.done() for lookup in lookups))
    except Exception:
        # This runs in a worker thread: log unexpected errors instead of failing the request.
        logger.exception("Could not summarize the story at %s", article.url)
        return _StorySummary(article, complete=True)


def _related_coverage(article: Article) -> list[Article]:
    """Pick other outlets' reports of the same story, from the cached headlines and, if needed, a Google News search."""
    candidates = {story.url: story for story in _cached_live_articles()}
    copies, related = _pick_related(article, candidates.values())
    if len(related) < RELATED_SOURCES:
        query = " ".join(headline_keywords(article.title))
        if query:
            for story in _read_google_news_feed(google_news_url("", RELATED_SEARCH_HOURS, query), query):
                candidates.setdefault(story.url, story)
            copies, related = _pick_related(article, candidates.values())
    return [*copies, *related]


def _cached_live_articles() -> list[Article]:
    now = time.monotonic()
    with _cache_lock:
        results = [result for expires_at, result in _cache.values() if expires_at > now and not result.using_fallback]
    return [story for result in results for story in result.articles]


def _pick_related(article: Article, candidates: Iterable[Article]) -> tuple[list[Article], list[Article]]:
    """Return up to MAX_STORY_COPIES copies of the story from other outlets, and up to RELATED_SOURCES independent
    reports of it.

    Copies (the same headline from another outlet, usually syndicated wire copy) repeat the story's own text, so only
    a few are kept, as stand-ins for the original page in case that cannot be read.
    """
    copies: list[Article] = []
    scored = []
    for candidate in candidates:
        if candidate.url == article.url or candidate.source == article.source:
            continue
        if _hours_apart(article.published, candidate.published) > RELATED_MAX_HOURS_APART:
            continue
        shared, overlap, jaccard = headline_similarity(article.title, candidate.title)
        if jaccard >= COPY_MIN_SIMILARITY:
            if len(copies) < MAX_STORY_COPIES and all(copy.source != candidate.source for copy in copies):
                copies.append(candidate)
        elif shared >= RELATED_MIN_SHARED_TERMS and overlap >= RELATED_MIN_OVERLAP:
            scored.append((overlap, candidate))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    related: list[Article] = []
    for _, candidate in scored:
        if len(related) == RELATED_SOURCES:
            break
        if any(
            story.source == candidate.source or headline_similarity(story.title, candidate.title)[2] >= COPY_MIN_SIMILARITY
            for story in related
        ):
            continue
        related.append(candidate)
    return copies, related


def _hours_apart(first: str, second: str) -> float:
    """Return how many hours apart two ISO 8601 timestamps are, or 0 when either cannot be read."""
    try:
        first_time = datetime.fromisoformat(first.replace("Z", "+00:00"))
        second_time = datetime.fromisoformat(second.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return abs((first_time - second_time).total_seconds()) / 3600


def _read_article_page(article_url: str, title: str) -> ArticleDetails:
    """Return the summary and image that the publisher gives for an article on its own page."""
    try:
        page_url = article_url
        article_id = _google_news_article_id(article_url)
        if article_id:
            page_url = _resolve_google_news_url(article_url, article_id)
            if not page_url or _google_news_article_id(page_url):
                logger.warning("Could not find the publisher URL behind %s", article_url)
                return ArticleDetails()
        final_url, page_html = _fetch_publisher_page(page_url)
        return _article_details_from_page(page_html, final_url, title)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not read the article page for %s: %s", article_url, exc)
    except Exception:
        # This runs in a worker thread: log unexpected errors instead of failing the headlines request.
        logger.exception("Unexpected error while reading the article page for %s", article_url)
    return ArticleDetails()


def _fetch_publisher_page(url: str) -> tuple[str, str]:
    """Fetch a publisher's page, sending at most MAX_REQUESTS_PER_PUBLISHER requests to one site at a time."""
    host = urlparse(url).hostname or ""
    with _publisher_slots_lock:
        slot = _publisher_slots.get(host)
        if slot is None:
            slot = _publisher_slots[host] = threading.BoundedSemaphore(MAX_REQUESTS_PER_PUBLISHER)
    with slot:
        return _fetch_html(url)


def google_news_url(topic: str, hours: int, search: Optional[str] = None) -> str:
    window = f"{hours // 24}d" if hours % 24 == 0 else f"{hours}h"
    q = search.strip() if search and search.strip() else topic
    query = urlencode({"q": f"{q} when:{window}", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"{GOOGLE_NEWS_RSS_URL}?{query}"


def fetch_google_news(category: NewsCategory, hours: int, search: Optional[str] = None) -> list[Article]:
    """Fetch English headlines from Google News RSS; returns an empty list when the feed is unavailable."""
    return _read_google_news_feed(google_news_url(category.topic, hours, search), category.topic)


def _read_google_news_feed(url: str, topic: str) -> list[Article]:
    try:
        response = _session().get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers=SHORT_HEADERS)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        logger.warning("Google News RSS is unavailable for %r: %s", topic, exc)
        return []

    articles = []
    for entry in root.findall("./channel/item"):
        article = _parse_item(entry)
        if article is not None:
            articles.append(article)
    return articles


def _parse_item(entry: ET.Element) -> Optional[Article]:
    source_element = entry.find("source")
    source = clean_text(source_element.text if source_element is not None else None) or "Google News"
    raw_title = clean_text(entry.findtext("title"))
    if not raw_title:
        return None

    url = _http_url(entry.findtext("link"))
    title = display_title(_strip_source_suffix(raw_title, source), source, url)
    summary = clean_text(entry.findtext("description"))
    # Google News descriptions usually just repeat the headline and publisher. A summary of the story's coverage
    # is built when the story is opened instead (see get_story_summary).
    if not summary or normalize(summary).startswith(normalize(title)):
        summary = ""

    image_url = _extract_image_url(entry)

    return Article(
        title=title,
        source=source,
        published=to_iso8601(entry.findtext("pubDate")),
        url=url,
        context=summary,
        image_url=image_url,
    )


def _extract_image_url(entry: ET.Element) -> str:
    """Return an image embedded in the feed item. Google News items have none; see _read_article_page instead."""
    for tag in ("{http://search.yahoo.com/mrss/}thumbnail", "{http://search.yahoo.com/mrss/}content"):
        element = entry.find(tag)
        if element is not None and element.get("url"):
            candidate = _http_url(element.get("url")) or ""
            if candidate and not _is_google_placeholder(candidate):
                return candidate
    return ""


def _google_news_article_id(url: str) -> str:
    parsed = urlparse(url)
    match = _GOOGLE_NEWS_ARTICLE_PATH_RE.fullmatch(parsed.path)
    return match.group(1) if parsed.hostname == "news.google.com" and match else ""


def _resolve_google_news_url(article_url: str, article_id: str) -> str:
    """Return the publisher URL behind a Google News article link, whose page only redirects with JavaScript."""
    with _google_page_slots:
        _, page_html = _fetch_html(article_url)
    signature = re.search(r'data-n-a-sg="([^"]+)"', page_html)
    timestamp = re.search(r'data-n-a-ts="(\d+)"', page_html)
    if not signature or not timestamp:
        return ""

    request = [
        "garturlreq",
        [
            ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
            "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
        ],
        article_id,
        int(timestamp.group(1)),
        signature.group(1),
    ]
    response = _session().post(
        GOOGLE_NEWS_DECODE_URL,
        data={"f.req": json.dumps([[["Fbv4je", json.dumps(request), None, "generic"]]])},
        headers={**SHORT_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        timeout=ARTICLE_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    # The reply is ")]}'" followed by JSON rows such as ["wrb.fr", "Fbv4je", "[\"garturlres\", \"<url>\", 1]", ...].
    start = response.text.find("[")
    if start < 0:
        return ""
    rows, _ = json.JSONDecoder().raw_decode(response.text, start)
    for row in rows:
        if isinstance(row, list) and len(row) > 2 and row[:2] == ["wrb.fr", "Fbv4je"] and isinstance(row[2], str):
            result = json.loads(row[2])
            if isinstance(result, list) and len(result) > 1 and result[0] == "garturlres" and isinstance(result[1], str):
                return _http_url(result[1])
    return ""


def _fetch_html(url: str) -> tuple[str, str]:
    """Download up to MAX_PAGE_BYTES of an HTML page. Returns (final URL after redirects, HTML).

    Pages are requested with the short User-Agent first. When a site refuses it, with an error (such as 403 or 406) or
    with a page that is not the article (such as "Access blocked"), the page is requested again as a browser. Pages
    that do not exist (404, 410) or that the site rate-limits (429) are not requested again.
    """
    status, final_url, page_html = _download(url, SHORT_HEADERS)
    if 400 <= status < 500 and status not in (404, 410, 429):
        status, final_url, page_html = _download(url, BROWSER_HEADERS)
    elif page_html and not _ARTICLE_MARKUP_RE.search(page_html):
        retry = _download(url, BROWSER_HEADERS)
        if retry[0] < 400 and _ARTICLE_MARKUP_RE.search(retry[2]):
            status, final_url, page_html = retry
    if status >= 400:
        raise requests.HTTPError(f"{status} error for url: {final_url}")
    return final_url, page_html


def _download(url: str, headers: Mapping[str, str]) -> tuple[int, str, str]:
    """Return (HTTP status, final URL, HTML), reading at most MAX_PAGE_BYTES; error pages and non-HTML are not read."""
    with _session().get(url, timeout=ARTICLE_REQUEST_TIMEOUT_SECONDS, headers=headers, stream=True) as response:
        if response.status_code >= 400 or "html" not in response.headers.get("Content-Type", "").lower():
            return response.status_code, response.url, ""
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            body += chunk
            if len(body) >= MAX_PAGE_BYTES:
                break
        return response.status_code, response.url, body.decode("utf-8", errors="replace")


class _ArticlePageParser(HTMLParser):
    """Collects what a page says about its article: <meta> tags, JSON-LD blocks, paragraphs, and photos."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        # (text, whether the paragraph is inside an <article> element)
        self.paragraphs: list[tuple[str, bool]] = []
        # <link rel="image_src"> addresses, and (address, whether inside <article>, <main>, or <figure>) of photos.
        self.image_links: list[str] = []
        self.photos: list[tuple[str, bool]] = []
        self.has_main_content = False
        self._json_ld_parts: Optional[list[str]] = None
        self._paragraph_parts: Optional[list[str]] = None
        self._article_depth = 0
        self._content_depth = 0
        self._in_code = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        values = dict(attrs)
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").strip().lower()
            content = (values.get("content") or "").strip()
            if key and content:
                self.meta.setdefault(key, content)
        elif tag == "link" and "image_src" in (values.get("rel") or "").lower().split() and values.get("href"):
            self.image_links.append(values["href"] or "")
        elif tag == "img":
            source = _photo_source(values)
            if source:
                self.photos.append((source, self._content_depth > 0))
        elif tag == "script" and (values.get("type") or "").strip().lower().startswith("application/ld+json"):
            self._json_ld_parts = []
        elif tag in ("script", "style"):
            self._in_code = True
        elif tag == "p" or tag in _BLOCK_TAGS:
            self._end_paragraph()
            if tag == "p":
                self._paragraph_parts = []
        if tag == "article":
            self._article_depth += 1
        if tag in _CONTENT_TAGS:
            self._content_depth += 1
            self.has_main_content = self.has_main_content or tag != "figure"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_ld_parts is not None:
            self.json_ld.append("".join(self._json_ld_parts))
            self._json_ld_parts = None
        elif tag in ("script", "style"):
            self._in_code = False
        elif tag == "p" or tag in _BLOCK_TAGS:
            self._end_paragraph()
        if tag == "article" and self._article_depth:
            self._article_depth -= 1
        if tag in _CONTENT_TAGS and self._content_depth:
            self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._json_ld_parts is not None:
            self._json_ld_parts.append(data)
        elif self._paragraph_parts is not None and not self._in_code:
            self._paragraph_parts.append(data)

    def _end_paragraph(self) -> None:
        if self._paragraph_parts is not None:
            text = clean_text("".join(self._paragraph_parts))
            if text:
                self.paragraphs.append((text, self._article_depth > 0))
            self._paragraph_parts = None


def _photo_source(attributes: Mapping[str, Optional[str]]) -> str:
    """Return the address of an <img> that may be a photo, or "" for icons, logos, tracking pixels and the like."""
    source = (attributes.get("src") or attributes.get("data-src") or attributes.get("data-lazy-src") or "").strip()
    if not source or source.startswith("data:"):
        candidates = (attributes.get("srcset") or attributes.get("data-srcset") or "").split(",")[0].split()
        source = candidates[0] if candidates else ""
    role = " ".join(value or "" for value in (source, attributes.get("class"), attributes.get("id")))
    if not source or source.startswith("data:") or _NOT_A_PHOTO_RE.search(role):
        return ""
    for dimension in ("width", "height"):
        size = (attributes.get(dimension) or "").strip().removesuffix("px")
        if size.isdigit() and int(size) < MIN_CONTENT_IMAGE_PIXELS:
            return ""
    return source


def _article_details_from_page(page_html: str, page_url: str, title: str) -> ArticleDetails:
    parser = _ArticlePageParser()
    try:
        parser.feed(page_html)
    except AssertionError:
        # Older Python versions raise this on some malformed markup; keep what was read before it.
        pass

    ld_description, ld_body, ld_image = _json_ld_article(parser.json_ld)
    meta = parser.meta
    # Article-level descriptions come first. The plain meta description is last because some sites use their
    # generic site description there.
    descriptions = (ld_description, meta.get("og:description", ""), meta.get("twitter:description", ""))
    summary = pick_summary((*descriptions, ld_body, meta.get("description", "")), title)

    # The article's text: its JSON-LD body, or the paragraphs inside <article> (or the whole page's when it has none).
    if ld_body:
        article_text = [ld_body]
    else:
        in_article = [text for text, inside in parser.paragraphs if inside]
        paragraphs = in_article or [text for text, _ in parser.paragraphs]
        article_text = [text for text in paragraphs if len(text.split()) >= 12]
    passages = [text for text in descriptions if text] or [meta.get("description", "")]
    passages = [text for text in passages if text] + article_text

    # The preview image the page names, else a photo in the story itself, or (on pages without <article> or <main>)
    # the first photo on the page.
    candidates = [meta[key] for key in _IMAGE_META_KEYS if key in meta]
    candidates += [ld_image, *parser.image_links, *(source for source, in_content in parser.photos if in_content)]
    if not parser.has_main_content:
        candidates += [source for source, _ in parser.photos]
    image_url = ""
    for candidate in filter(None, candidates):
        url = _http_url(urljoin(page_url, candidate.strip()))
        if url and not _is_google_placeholder(url):
            image_url = url
            break
    return ArticleDetails(
        summary=summary,
        image_url=image_url,
        passages=tuple(_truncate(text, MAX_PASSAGE_CHARS) for text in passages[:MAX_PAGE_PASSAGES]),
    )


def _truncate(text: str, limit: int) -> str:
    # The ellipsis marks the cut, so a sentence cut short (for example after "4.") is not taken as complete.
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _json_ld_article(blocks: Iterable[str]) -> tuple[str, str, str]:
    """Return the description, body text, and image of the first article described in the page's JSON-LD."""
    description = body = image = ""
    nodes: list[object] = []
    for block in blocks:
        try:
            nodes.append(json.loads(block, strict=False))
        except ValueError:
            continue
    nodes.reverse()
    while nodes:
        node = nodes.pop()
        if isinstance(node, list):
            nodes.extend(reversed(node))
        elif isinstance(node, dict):
            types = node.get("@type")
            type_names = types if isinstance(types, list) else [types]
            if any(isinstance(name, str) and (name.endswith("Article") or name.endswith("BlogPosting")) for name in type_names):
                if not description and isinstance(node.get("description"), str):
                    description = node["description"]
                if not body and isinstance(node.get("articleBody"), str):
                    body = node["articleBody"]
                image = image or _json_ld_image(node.get("image"))
            nodes.extend(reversed([value for value in node.values() if isinstance(value, (dict, list))]))
    return description, body, image


def _json_ld_image(value: object) -> str:
    """Return the first address in a JSON-LD "image" value: a URL, an ImageObject, or a list of them."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _json_ld_image(value.get("url") or value.get("contentUrl"))
    if isinstance(value, list):
        return next((url for url in map(_json_ld_image, value) if url), "")
    return ""


def display_title(title: str, source: str, url: str) -> str:
    """Replace placeholder titles such as "None" with a readable label derived from the URL or source."""
    if title and title.lower() not in {"none", "null"}:
        return title
    path = urlparse(url).path.strip("/") if url else ""
    if path:
        return f"{source} update: {path.replace('-', ' ').replace('/', ' ').title()}"
    return f"Headline from {source}"


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
        # Stories without a usable description get the publisher's summary from the article page instead.
        context = pick_summary((item.get("description") or "",), title)
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
