"""FastAPI entry point: JSON API for the React app, plus the built UI when web/dist exists."""

from pathlib import Path, PurePath
from typing import Annotated

import openai
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from .briefing import summarize_headlines
from .models import BriefingRequest, BriefingResponse, Category, NewsResponse
from .news import CATEGORIES, CATEGORIES_BY_ID, NewsCategory, get_news

WEB_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"


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
    description="Recent headlines from Google News RSS with an optional OpenAI briefing.",
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
