"""Step 2 of the AI pipeline (PRD §11): templated extraction, one prompt
per content_type, each returning a distinct structured schema. Never a
generic "summarize this" — that's how you lose "80CCD(1B)".

Takes optional in-memory media. Many reels never speak their list items
aloud — they display them on screen over music — so transcript-in returns
nothing useful and video-in is the only way to read them (PRD §11, prompt
rule 2). The media is a plain `MediaPayload` from whichever adapter
produced it; this module stays platform-agnostic (CLAUDE.md rule 1).
"""
from __future__ import annotations

from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from pipeline.media import MediaPayload

MODEL = "gemini-2.0-flash"

ContentType = Literal["listicle", "tutorial", "recipe", "explainer", "news", "entertainment"]

# Rules from PRD §11 that apply to every template, prepended to every prompt.
_SHARED_RULES = """You extract structured information from a social video's transcript
and/or on-screen text for a save-and-retrieve app. Follow these rules exactly:

1. Extract, don't invent. If the video doesn't say it, it isn't in the summary.
   Omit rather than fill gaps. Never guess a number, name, or fact that isn't present.
2. The input may include on-screen text separately from spoken transcript — many
   listicles never speak the items aloud, they display them over music. Treat
   on-screen text as equally authoritative as speech.
3. Preserve exact specifics: numbers, brand names, section codes, amounts, units.
   Losing "80CCD(1B)" or "$50" destroys the value of the summary.
4. Set is_time_sensitive=true if the content involves tax, law, pricing, medical
   advice, or anything else that can go stale and mislead if acted on later.
5. Generate a punchy, widget-safe title under 60 characters.
"""

_TYPE_INSTRUCTIONS: dict[ContentType, str] = {
    "listicle": "Extract the headline and each list item with its point and supporting detail.",
    "tutorial": "Extract the goal, the ordered steps, and any tools/materials needed.",
    "recipe": "Extract the ingredient list, the ordered method, and total time in minutes if stated.",
    "explainer": "Extract the core question being answered, the answer, and supporting key points.",
    "news": "Extract a headline, a short summary, and the key facts (who/what/when/numbers).",
    "entertainment": "Extract a one-line description of what happens. Do not overanalyze.",
}


class ListicleItem(BaseModel):
    point: str
    detail: str


class ListicleSummary(BaseModel):
    headline: str
    items: list[ListicleItem] = Field(default_factory=list)


class TutorialSummary(BaseModel):
    goal: str
    steps: list[str] = Field(default_factory=list)
    tools_needed: list[str] = Field(default_factory=list)


class RecipeSummary(BaseModel):
    ingredients: list[str] = Field(default_factory=list)
    method: list[str] = Field(default_factory=list)
    time_min: int | None = None


class ExplainerSummary(BaseModel):
    question: str
    answer: str
    key_points: list[str] = Field(default_factory=list)


class NewsSummary(BaseModel):
    headline: str
    summary: str
    key_facts: list[str] = Field(default_factory=list)


class EntertainmentSummary(BaseModel):
    description: str


_SCHEMA_BY_TYPE: dict[ContentType, type[BaseModel]] = {
    "listicle": ListicleSummary,
    "tutorial": TutorialSummary,
    "recipe": RecipeSummary,
    "explainer": ExplainerSummary,
    "news": NewsSummary,
    "entertainment": EntertainmentSummary,
}

_ENVELOPE_SCHEMAS: dict[ContentType, dict] = {
    "listicle": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "is_time_sensitive": {"type": "BOOLEAN"},
            "headline": {"type": "STRING"},
            "items": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {"point": {"type": "STRING"}, "detail": {"type": "STRING"}},
                    "required": ["point", "detail"],
                },
            },
        },
        "required": ["title", "is_time_sensitive", "headline", "items"],
    },
    "tutorial": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "is_time_sensitive": {"type": "BOOLEAN"},
            "goal": {"type": "STRING"},
            "steps": {"type": "ARRAY", "items": {"type": "STRING"}},
            "tools_needed": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["title", "is_time_sensitive", "goal", "steps"],
    },
    "recipe": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "is_time_sensitive": {"type": "BOOLEAN"},
            "ingredients": {"type": "ARRAY", "items": {"type": "STRING"}},
            "method": {"type": "ARRAY", "items": {"type": "STRING"}},
            "time_min": {"type": "INTEGER", "nullable": True},
        },
        "required": ["title", "is_time_sensitive", "ingredients", "method"],
    },
    "explainer": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "is_time_sensitive": {"type": "BOOLEAN"},
            "question": {"type": "STRING"},
            "answer": {"type": "STRING"},
            "key_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["title", "is_time_sensitive", "question", "answer"],
    },
    "news": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "is_time_sensitive": {"type": "BOOLEAN"},
            "headline": {"type": "STRING"},
            "summary": {"type": "STRING"},
            "key_facts": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["title", "is_time_sensitive", "headline", "summary"],
    },
    "entertainment": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "is_time_sensitive": {"type": "BOOLEAN"},
            "description": {"type": "STRING"},
        },
        "required": ["title", "is_time_sensitive", "description"],
    },
}


class SummaryResult(BaseModel):
    title: str
    is_time_sensitive: bool
    content: dict

    def to_jsonb(self) -> dict:
        """Shape stored in items.summary — content fields flattened, per PRD §10."""
        return self.content


def _build_contents(text: str, media: MediaPayload | None) -> list:
    """Video first, then whatever text we have. An empty caption is still worth
    sending as a label, but never as the only input when media is available."""
    parts: list = []
    if media is not None:
        parts.append(types.Part.from_bytes(data=media.data, mime_type=media.mime_type))
        parts.append(
            types.Part.from_text(
                text=(
                    "Read the on-screen text in the video as well as the speech. "
                    f"Post caption (may be empty): {text}"
                )
            )
        )
    else:
        parts.append(types.Part.from_text(text=text))
    return [types.Content(role="user", parts=parts)]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def summarize(
    client: genai.Client,
    content_type: ContentType,
    text: str,
    media: MediaPayload | None = None,
) -> SummaryResult:
    """Templated extraction for one content_type. Raises on repeated API
    failure — callers should catch and mark the item as failed."""
    schema_model = _SCHEMA_BY_TYPE[content_type]
    envelope_schema = _ENVELOPE_SCHEMAS[content_type]
    prompt = _SHARED_RULES + "\n" + _TYPE_INSTRUCTIONS[content_type]

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=_build_contents(text, media),
        config=types.GenerateContentConfig(
            system_instruction=prompt,
            response_mime_type="application/json",
            response_schema=envelope_schema,
            temperature=0.0,
        ),
    )

    import json

    raw = json.loads(response.text)
    title = raw.pop("title")
    is_time_sensitive = raw.pop("is_time_sensitive")
    content = schema_model.model_validate(raw).model_dump()

    return SummaryResult(title=title, is_time_sensitive=is_time_sensitive, content=content)
