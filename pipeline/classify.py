"""Step 1 of the AI pipeline (PRD §11): cheap classification before any
expensive summarization call. This is the cost-control gate — everything
downstream only runs when is_informational is true.
"""
from __future__ import annotations

from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from pipeline.llm_log import log_call

ContentType = Literal["listicle", "tutorial", "recipe", "explainer", "news", "entertainment"]

MODEL = "gemini-3.5-flash-lite"

_SYSTEM_PROMPT = """You classify social video captions/transcripts for a save-and-retrieve app.

Given the text, decide:
- content_type: the single best fit from listicle, tutorial, recipe, explainer, news, entertainment
- is_informational: true only if the content teaches or informs something concrete
  (facts, steps, numbers, how-to). Memes, jokes, vibes-only, and pure entertainment
  are is_informational=false even if a content_type still applies.
- topics: 1-5 short lowercase tags (e.g. "tax", "finance", "india", "python")
- confidence: your confidence in this classification, 0 to 1

Do not invent information beyond what's in the text."""


class ClassificationResult(BaseModel):
    content_type: ContentType
    is_informational: bool
    topics: list[str] = Field(default_factory=list)
    confidence: float


_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "content_type": {
            "type": "STRING",
            "enum": ["listicle", "tutorial", "recipe", "explainer", "news", "entertainment"],
        },
        "is_informational": {"type": "BOOLEAN"},
        "topics": {"type": "ARRAY", "items": {"type": "STRING"}},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["content_type", "is_informational", "topics", "confidence"],
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def classify(client: genai.Client, text: str) -> ClassificationResult:
    """Classify a caption/transcript. Raises on repeated API failure — callers
    should catch and mark the item as failed rather than let this crash a handler."""
    with log_call(MODEL, "classify") as logged:
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )
        logged.append(response)
    return ClassificationResult.model_validate_json(response.text)
