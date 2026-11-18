"""Request and response schemas shared by the API routes."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base model that exposes camelCase JSON keys to the React client."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class Category(ApiModel):
    id: str
    label: str


class Article(ApiModel):
    title: str
    source: str
    published: str = Field(description="ISO 8601 UTC timestamp when the feed provides a parseable date.")
    url: str
    language: str = "en"
    context: str
    image_url: str = ""


class NewsResponse(ApiModel):
    category: Category
    hours: int
    articles: list[Article]
    using_fallback: bool


class BriefingRequest(ApiModel):
    category: str
    hours: int = Field(default=24, ge=1, le=168)
    limit: int = Field(default=30, ge=1, le=50)
    api_key: SecretStr = Field(min_length=1)


class BriefingResponse(ApiModel):
    briefing: str


class AskMessage(ApiModel):
    """An earlier question or answer in the conversation about an article."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class AskRequest(ApiModel):
    url: str = Field(min_length=1, max_length=2048, description="Article URL from a recent /api/news response.")
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    history: list[AskMessage] = Field(default_factory=list, max_length=20)
