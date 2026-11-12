"""Request and response schemas shared by the API routes."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr
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
