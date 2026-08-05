"""Step 3 of the AI pipeline (PRD §11): embed title + summary text + topics,
never the raw transcript — too noisy for semantic search."""
from __future__ import annotations

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

MODEL = "gemini-embedding-001"
DIMENSIONS = 768


def build_embedding_text(title: str, summary: dict, topics: list[str]) -> str:
    summary_text = " ".join(str(v) for v in _flatten(summary))
    return " | ".join(filter(None, [title, summary_text, " ".join(topics)]))


def _flatten(value) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for v in value.values():
            out.extend(_flatten(v))
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_flatten(v))
        return out
    return [str(value)]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def embed(client: genai.Client, title: str, summary: dict, topics: list[str]) -> list[float]:
    text = build_embedding_text(title, summary, topics)
    response = await client.aio.models.embed_content(
        model=MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
    )
    return response.embeddings[0].values
