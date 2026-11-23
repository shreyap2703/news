"""FastAPI entry point: JSON API for the React app, plus the built UI when web/dist exists."""

from pathlib import Path, PurePath
from typing import Annotated

import openai
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import StringConstraints
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from .ask import answer_question, describe_error, nvidia_api_key
from .briefing import summarize_headlines
from .models import (
    Article,
    AskRequest,
    BriefingRequest,
    BriefingResponse,
    Category,
    NewsResponse,
    RecommendationsResponse,
)
from .news import (
    CATEGORIES,
    CATEGORIES_BY_ID,
    NewsCategory,
    clear_cache,
    get_article_for_questions,
    get_news,
    get_story_summary,
)
from .recommendations import NoInterestsError, recommend

WEB_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
# One followed topic, muted topic, or publisher name in a recommendations request.
InterestText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class SinglePageApp(StaticFiles):
    """Serves the built UI. Client-side routes such as /login get index.html, so reloading those pages works."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Unknown /api paths and missing files (names with an extension) keep their 404.
            requested = PurePath(path)
            if exc.status_code != 404 or requested.parts[:1] == ("api",) or "." in requested.name:
                raise
            return await super().get_response("index.html", scope)


app = FastAPI(
    title="The Daily Pulse API",
    version="1.0.0",
    description="Recent headlines from publishers' RSS feeds, with Google News RSS as the backup source.",
)


def _find_category(category_id: str) -> NewsCategory:
    category = CATEGORIES_BY_ID.get(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail=f"Unknown news section: {category_id!r}.")
    return category


def _to_api_category(category: NewsCategory) -> Category:
    return Category(id=category.id, label=category.label)


def _openai_error_message(exc: openai.OpenAIError) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return body["message"]
    return str(exc)


@app.get("/api/categories")
def list_categories() -> list[Category]:
    return [_to_api_category(category) for category in CATEGORIES]


@app.get("/api/news")
def read_news(
    category: Annotated[str, Query(description="Section id from /api/categories.")],
    hours: Annotated[int, Query(ge=1, le=168, description="Look-back window in hours.")] = 24,
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum number of headlines.")] = 30,
    q: Annotated[str | None, Query(description="Optional search term to override the default category topic.")] = None,
    refresh: Annotated[bool, Query(description="Clear the 10-minute cache and fetch again.")] = False,
) -> NewsResponse:
    news_category = _find_category(category)
    result = get_news(news_category, hours, limit, refresh=refresh, search=q)
    return NewsResponse(
        category=_to_api_category(news_category),
        hours=hours,
        articles=list(result.articles),
        using_fallback=result.using_fallback,
    )


@app.get("/api/news/summary")
def read_story_summary(
    url: Annotated[str, Query(description="Article URL from a recent /api/news response.")],
) -> Article:
    """Return the story with a short summary combined from several outlets' coverage of it."""
    article = get_story_summary(url)
    if article is None:
        raise HTTPException(status_code=404, detail="Unknown story. Only stories listed by /api/news can be summarized.")
    return article


@app.get("/api/recommendations")
def read_recommendations(
    section: Annotated[
        list[str] | None, Query(max_length=20, description="Section ids from /api/categories, in the reader's order.")
    ] = None,
    topic: Annotated[
        list[InterestText] | None, Query(max_length=20, description="Topics the reader follows; their stories come first.")
    ] = None,
    city: Annotated[
        str | None, Query(max_length=100, description='City or state for local news, for example "Hyderabad, Telangana".')
    ] = None,
    mute: Annotated[
        list[InterestText] | None, Query(max_length=20, description='Topics to leave out, for example "Crime" or "Live blogs".')
    ] = None,
    hide_source: Annotated[
        list[InterestText] | None, Query(alias="hideSource", max_length=50, description="Publishers to leave out.")
    ] = None,
    hours: Annotated[int, Query(ge=1, le=168, description="Look-back window in hours.")] = 24,
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum number of stories.")] = 30,
    refresh: Annotated[bool, Query(description="Clear the 10-minute cache and fetch again.")] = False,
) -> RecommendationsResponse:
    """Return one feed combining the reader's sections, followed topics, and city, each story with its reason."""
    if refresh:
        clear_cache()
    try:
        articles, using_fallback = recommend(
            section or [], topic or [], city or "", mute or [], hide_source or [], hours, limit
        )
    except NoInterestsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RecommendationsResponse(hours=hours, articles=articles, using_fallback=using_fallback)


@app.post(
    "/api/news/ask",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/plain": {}}, "description": "The answer, streamed as plain text."}},
)
def ask_about_article(request: AskRequest) -> StreamingResponse:
    """Answer a question about a listed story from its article's text, with an NVIDIA-hosted model."""
    if not nvidia_api_key():
        raise HTTPException(
            status_code=503,
            detail="Ask AI is not set up yet: start the API server with an NVIDIA API key in NVIDIA_API_KEY "
            "(see the README).",
        )
    found = get_article_for_questions(request.url)
    if found is None:
        raise HTTPException(status_code=404, detail="Unknown story. Refresh the headlines, then ask again.")
    article, text = found
    try:
        answer = answer_question(article, text, request.question, request.history)
    except openai.OpenAIError as exc:
        raise HTTPException(status_code=502, detail=describe_error(exc)) from exc
    # X-Accel-Buffering stops proxies such as nginx from holding the answer back until it is complete.
    return StreamingResponse(
        answer,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.post("/api/briefing")
def create_briefing(request: BriefingRequest) -> BriefingResponse:
    news_category = _find_category(request.category)
    result = get_news(news_category, request.hours, request.limit)
    if not result.articles:
        raise HTTPException(status_code=404, detail="There are no headlines to summarize for this filter.")
    try:
        briefing = summarize_headlines(result.articles, request.api_key.get_secret_value())
    except openai.OpenAIError as exc:
        detail = f"Could not generate the AI briefing: {_openai_error_message(exc)}"
        raise HTTPException(status_code=502, detail=detail) from exc
    return BriefingResponse(briefing=briefing)


# Registered last so the /api routes above take precedence over the static files.
if WEB_DIST_DIR.is_dir():
    app.mount("/", SinglePageApp(directory=WEB_DIST_DIR, html=True), name="web")
else:

    @app.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {
            "message": "The Daily Pulse API is running. Run `npm run dev` in web/ for the UI, "
            "or `npm run build` there and restart this server to serve it from here."
        }
