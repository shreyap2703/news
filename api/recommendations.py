"""Recommendations: one feed combining the sections, followed topics, and city a reader chose after sign-up."""

import logging
import re
from collections.abc import Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from .models import Article, RecommendationReason, RecommendedArticle
from .news import CATEGORIES, CATEGORIES_BY_ID, COPY_MIN_SIMILARITY, NewsCategory, get_news
from .summarizer import headline_similarity, normalize

logger = logging.getLogger(__name__)

# The interests are read in parallel; most come from the cache that the headlines page shares.
INTEREST_WORKERS = 8
# Topics and the city are searches across every section's feeds, so the section they run under only names their
# cache entry.
SEARCH_SECTION = CATEGORIES[0]
# Searches the shared search cannot narrow down (see _needs_mention_check) look through this many stories instead.
CHECKED_SEARCH_LIMIT = 200

_interest_pool = ThreadPoolExecutor(max_workers=INTEREST_WORKERS, thread_name_prefix="recommendations")

# How to recognise the topics that the welcome page offers to mute (MUTE_OPTIONS in web/src/preferences.ts): by the
# headline, which says what a story is mainly about, and for live blogs and opinion pieces also by the address.
_MUTED_TOPICS: dict[str, tuple[str, str]] = {
    "celebrity gossip": (r"\b(?:celebrit(?:y|ies)|celebs?|gossip|bollywood|hollywood|red carpet|kardashians?|tabloids?)\b", ""),
    "crime": (
        r"\b(?:crimes?|criminals?|murder(?:s|ed|ers?)?|homicides?|stab(?:s|bed|bings?)?|robber(?:s|y|ies)?|robbed|"
        r"burglar(?:s|y|ies)?|kidnapp?(?:ed|ers?|ings?)?|rap(?:e|ed|es|ists?)|gunm[ae]n|shot dead|thefts?|thie(?:f|ves)|"
        r"serial killers?)\b",
        "",
    ),
    "crypto": (r"\b(?:crypto\w*|bitcoins?|ethereum|blockchains?|nfts?|stablecoins?|binance|coinbase|dogecoin|altcoins?)\b", ""),
    "elections": (
        r"\b(?:elections?|electoral|electorates?|midterms?|ballots?|voters?|voting|polling|polls?|by-?elections?|"
        r"re-?elect(?:ed|ion)?)\b",
        "",
    ),
    "live blogs": (
        # "Live updates", "as it happened", "Ukraine war live: …", and "… – US politics live".
        r"\blive\s*(?:updates?|blog|coverage)\b|\bas it happened\b|^[^:|–—]{0,60}\blive\s*[:|–—]|[-–—]\s[^-–—]*\blive\s*$",
        r"/live/|/liveblog/|live-?blog|live-updates?",
    ),
    "opinion pieces": (
        r"^(?:opinion|comment|editorial|op-?ed)\s*[:|–—-]|^the [\w' ]+ view on\b",
        r"/commentisfree/|/opinions?/|/op-?eds?/|/editorials?/|/columns?/",
    ),
}
_MUTED_RULES = {
    label: (re.compile(title, re.IGNORECASE), re.compile(url, re.IGNORECASE) if url else None)
    for label, (title, url) in _MUTED_TOPICS.items()
}


class NoInterestsError(ValueError):
    """Raised when the reader has no section, topic, or city to recommend from."""


@dataclass(frozen=True)
class _Interest:
    reason: RecommendationReason
    category: NewsCategory
    search: Optional[str] = None


@dataclass(frozen=True)
class _Reading:
    articles: list[Article]
    # Whether these are the section's bundled backup headlines, shown while its feeds are unavailable.
    backup: bool = False


def recommend(
    sections: Sequence[str],
    topics: Sequence[str],
    city: str,
    muted: Sequence[str],
    hidden_sources: Sequence[str],
    hours: int,
    limit: int,
) -> tuple[list[RecommendedArticle], bool]:
    """Return up to ``limit`` stories for the reader's interests, and whether any of them are backup headlines.

    Each round takes the next new story from every interest in turn, followed topics first, so that no single interest
    fills the feed. Stories from hidden publishers or about muted topics are left out, and a story is shown once even
    when several interests (or several outlets' copies of it) bring it in.
    """
    interests = _interests(sections, topics, city)
    if not interests:
        raise NoInterestsError("Choose at least one section, topic, or city to get recommendations.")
    readings = list(_interest_pool.map(lambda interest: _read(interest, hours, limit), interests))
    muted_rules = _muted_rules(muted)
    hidden = {_source_key(source) for source in hidden_sources if source.strip()}

    def wanted(article: Article) -> bool:
        return _source_key(article.source) not in hidden and not _is_muted(article, muted_rules)

    queues: list[tuple[_Interest, bool, Iterator[Article]]] = [
        (interest, reading.backup, (article for article in reading.articles if wanted(article)))
        for interest, reading in zip(interests, readings)
    ]
    chosen: list[RecommendedArticle] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    used_backup = False

    def is_new(article: Article) -> bool:
        if article.url in seen_urls or normalize(article.title) in seen_titles:
            return False
        return all(headline_similarity(article.title, other.title)[2] < COPY_MIN_SIMILARITY for other in chosen)

    while queues and len(chosen) < limit:
        remaining = []
        for interest, backup, stories in queues:
            story = next((article for article in stories if is_new(article)), None)
            if story is None:
                continue
            seen_urls.add(story.url)
            seen_titles.add(normalize(story.title))
            chosen.append(RecommendedArticle(**story.model_dump(), reason=interest.reason))
            used_backup = used_backup or backup
            remaining.append((interest, backup, stories))
            if len(chosen) == limit:
                break
        queues = remaining
    return chosen, used_backup


def _interests(sections: Sequence[str], topics: Sequence[str], city: str) -> list[_Interest]:
    """Followed topics first (the welcome page promises their stories are shown first), then the sections in the order
    the reader picked them, then local news for the city."""
    interests = [
        _Interest(RecommendationReason(kind="topic", label=topic), SEARCH_SECTION, topic) for topic in _unique(topics)
    ]
    for section_id in _unique(sections):
        category = CATEGORIES_BY_ID.get(section_id)
        if category is not None:
            reason = RecommendationReason(kind="section", label=category.label, section_id=category.id)
            interests.append(_Interest(reason, category))
    # "Hyderabad, Telangana" is searched as "Hyderabad": local reports rarely name the state as well.
    place = " ".join(city.split(",")[0].split())
    if place:
        interests.append(_Interest(RecommendationReason(kind="city", label=place), SEARCH_SECTION, place))
    return interests


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        value = " ".join(value.split())
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def _read(interest: _Interest, hours: int, limit: int) -> _Reading:
    """Return an interest's stories, newest first: its section's headlines, or the stories its search finds."""
    try:
        if interest.search is None:
            result = get_news(interest.category, hours, limit)
            return _Reading(list(result.articles), backup=result.using_fallback)
        check = _needs_mention_check(interest.search)
        result = get_news(interest.category, hours, CHECKED_SEARCH_LIMIT if check else limit, search=interest.search)
        # A search that finds nothing live returns its section's backup headlines, which have nothing to do with it.
        if result.using_fallback:
            return _Reading([])
        articles = [article for article in result.articles if not check or _mentions(article, interest.search)]
        return _Reading(articles[:limit])
    except Exception:
        # One interest that fails should not cost the reader the others.
        logger.exception("Could not read the stories for %r", interest.reason.label)
        return _Reading([])


def _needs_mention_check(term: str) -> bool:
    """Whether the shared search ignores this term, and so returns every story for it.

    It only looks for words of three or more Latin letters or digits, so "AI", "UK", and non-Latin text are checked
    here instead.
    """
    return not any(len(token) > 2 for token in re.findall(r"[a-z0-9]+", term.casefold()))


def _mentions(article: Article, term: str) -> bool:
    # Only the headline counts: short terms such as "AI" turn up in passing in many stories' descriptions.
    title = article.title.casefold()
    tokens = re.findall(r"[a-z0-9]+", term.casefold())
    if not tokens:
        return term.casefold() in title
    return all(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", title) for token in tokens)


def _muted_rules(muted: Iterable[str]) -> list[tuple[re.Pattern[str], Optional[re.Pattern[str]]]]:
    """The patterns for each muted topic; topics without a rule of their own are looked for in the headline as written."""
    rules = []
    for label in _unique(muted):
        rule = _MUTED_RULES.get(label.casefold())
        rules.append(rule or (re.compile(rf"(?<!\w){re.escape(label)}(?!\w)", re.IGNORECASE), None))
    return rules


def _is_muted(article: Article, rules: Iterable[tuple[re.Pattern[str], Optional[re.Pattern[str]]]]) -> bool:
    return any(title.search(article.title) or (url is not None and url.search(article.url)) for title, url in rules)


def _source_key(source: str) -> str:
    """Name publishers the same whichever feed names them: "BBC News" and "BBC" give "bbc", "The Times of India" and
    "Times of India" give "timesofindia"."""
    key = re.sub(r"^the\s+", "", source.strip().casefold())
    key = re.sub(r"\s+(?:news|english)$", "", key)
    return re.sub(r"[\W_]+", "", key)
