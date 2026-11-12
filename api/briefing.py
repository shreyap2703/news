"""Optional OpenAI briefing generated from the current headlines."""

from typing import Sequence

from openai import OpenAI

from .models import Article

BRIEFING_MODEL = "gpt-4.1-mini"
MAX_BRIEFING_HEADLINES = 20
REQUEST_TIMEOUT_SECONDS = 60
BRIEFING_PROMPT = (
    "Create a concise, neutral news briefing from these headlines. "
    "Group related stories, distinguish confirmed facts from developing reports, "
    "explain why the major stories matter, and do not invent details. "
    "Mention that readers should open the original sources for full context.\n\n"
)


def summarize_headlines(articles: Sequence[Article], api_key: str) -> str:
    """Summarize headlines (not full articles) with the caller's own key, which is never stored."""
    headlines = "\n".join(f"- {article.title} ({article.source})" for article in articles[:MAX_BRIEFING_HEADLINES])
    with OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.responses.create(model=BRIEFING_MODEL, input=BRIEFING_PROMPT + headlines)
    return response.output_text
